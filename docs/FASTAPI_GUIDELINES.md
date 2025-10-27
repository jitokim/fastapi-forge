# FastAPI Development Guidelines

> Comprehensive best practices for production FastAPI applications

This document provides battle-tested guidelines for building high-performance, production-ready FastAPI applications. These practices are derived from real-world experience and are particularly relevant for applications using:

- FastAPI with async/await patterns
- Gunicorn + Uvicorn workers
- LLM integrations and streaming responses
- High-concurrency scenarios
- Production observability requirements

---

## 서버 실행 예시
- Gunicorn 뒤에서 FastAPI를 실행할 때는 `uvicorn.workers.UvicornWorker`를 사용해 비동기 이벤트 루프를 그대로 활용한다.
- 워커 수, timeout, graceful-timeout, keep-alive, 포트는 환경변수로 노출해 배포 환경별로 값을 조정한다.
- 장기 스트리밍이 기본이라면 timeout 120–180초, keep-alive 30–60초 범위에서 실측 데이터를 보며 조정한다.
- `--max-requests`와 `--max-requests-jitter`를 설정해 워커를 주기적으로 리사이클하고 재시작 시점이 몰리지 않게 한다.

```bash
ENV WORKERS=2
ENV WORKER_TIMEOUT=300
ENV GRACEFUL_TIMEOUT=240
ENV PORT=8080

uv run ddtrace-run gunicorn lbox_agent.app.main:app \
  -w ${WORKERS} -k uvicorn.workers.UvicornWorker \
  --bind 0.0.0.0:${PORT} \
  --timeout ${WORKER_TIMEOUT} \
  --graceful-timeout ${GRACEFUL_TIMEOUT} \
  --keep-alive 60 \
  --max-requests 1000 \
  --max-requests-jitter 50
```

## 워커 및 성능 튜닝
- 워커 수는 기본적으로 `2 * CPU 코어 + 1`을 출발점으로 하되, UvicornWorker는 한 워커가 수백 코루틴을 처리하므로 코어 수±2 구간에서 관찰하며 조정한다.
- CPU 사용률, 큐 길이, 워커별 RSS를 모니터링해 여유가 없을 때만 워커를 늘린다. 컨텍스트 스위칭이나 메모리 압박이 커지면 줄인다.
- CPU 집약 작업(임베딩, PDF 파싱 등)은 profiler로 확인한 뒤 별도 백그라운드 큐나 서비스로 분리한다.
- DB 커넥션 풀과 HTTP 클라이언트 풀은 `workers * 동시성`이 업스트림 한도를 넘지 않도록 설정하고, 풀 고갈 메트릭을 수집한다.

## 동시성 및 블로킹 처리
- FastAPI `async def` 내부에서는 비동기 클라이언트를 사용하고, 동기 함수는 `asyncio.to_thread`나 `loop.run_in_executor`로 오프로딩한다.
- 기본 executor 크기는 `min(32, cpu_count + 4)`이므로 블로킹 태스크가 많으면 전용 `ThreadPoolExecutor`를 설정하고 타임아웃·큐 길이를 관찰한다.
- LangChain `ChatModel.invoke()`처럼 동기만 제공되는 API는 다음 패턴으로 감싼다. 비동기 대안(`ainvoke`)이 있으면 우선 사용한다.

```python
@app.post("/invoke")
async def invoke(payload: Payload):
    return await asyncio.to_thread(chat_model.invoke, payload.messages)
```

- 여러 코루틴을 병렬로 실행할 때는 `asyncio.gather(..., return_exceptions=True)`를 사용해 하나의 실패가 전체를 멈추지 않게 한다.
- 이벤트 루프 정지를 감지하려면 감시 태스크를 등록해 주기적인 지연을 측정하고, 임계값을 넘으면 경고 로그를 남긴다.

```python
async def monitor_loop(threshold: float = 0.1) -> None:
    loop = asyncio.get_running_loop()
    last = loop.time()
    while True:
        await asyncio.sleep(threshold)
        diff = loop.time() - last - threshold
        if diff > threshold:
            logger.warning("event_loop_blocked", blocked=diff)
        last = loop.time()
```

**💡 FastAPI Forge Tip**: Use the built-in `EventLoopMonitor` from `fastapi_forge.utils` for production-ready event loop monitoring with stack trace capture!

## 스트리밍 타임아웃 및 Heartbeat
- Gunicorn `--timeout`은 "지정 시간 동안 아무 데이터도 전송되지 않음"을 기준으로 동작하므로, 첫 청크가 지연되면 워커가 바로 종료될 수 있다.
- LLM 출력이 느린 경우 heartbeat 청크를 주기적으로 보내 inactivity 타임아웃을 방지한다.
- Heartbeat 래퍼는 큐 기반으로 구현하고 lifespan에서 싱글톤으로 등록하면 여러 엔드포인트에서 재사용하기 쉽다.

```python
class HeartbeatStreamer:
    def __init__(self, interval: float = 10.0, message: bytes = b"data: [heartbeat]\n\n"):
        self.interval = interval
        self.message = message

    async def wrap(self, generator: AsyncIterator[bytes]) -> AsyncIterator[bytes]:
        queue: asyncio.Queue[bytes | None] = asyncio.Queue()

        async def producer() -> None:
            async for chunk in generator:
                await queue.put(chunk)
            await queue.put(None)

        asyncio.create_task(producer())

        while True:
            try:
                chunk = await asyncio.wait_for(queue.get(), timeout=self.interval)
            except asyncio.TimeoutError:
                yield self.message
                continue
            if chunk is None:
                break
            yield chunk
```

## 라이프사이클 및 DI
- `lifespan` 컨텍스트를 사용해 싱글톤 리소스를 한 번만 초기화하고 종료 시 정리한다. 모든 `start()`에는 짝이 되는 `stop()`을 둔다.
- `app.state`에 설정, 컨테이너, 그래프 등을 저장하고 `Depends` 헬퍼를 통해 엔드포인트에서 직접 초기화 로직을 참조하지 않게 한다.
- OpenTelemetry, Datadog 같은 관측 도구는 시작 시 초기화하고 종료 시 flush/close를 호출해 스팬 손실을 막는다.
- 장기 커넥션은 싱글톤으로 유지하고, 요청 범위 객체는 프로토타입 스코프로 관리해 상태 누수를 방지한다.

**💡 FastAPI Forge Tip**: Use `fastapi_forge.logging.configure_logging()` in your lifespan to set up production-ready JSON logging!

## 외부 HTTP 가드레일
- 통합 대상마다 전용 서비스 클래스를 두고 `httpx.AsyncClient`를 캡슐화한다. `Limits`, `Timeout`, 기본 헤더를 명시한다.
- 클라이언트는 프로세스 수명 동안 재사용하고 shutdown에서 `aclose()`를 호출한다.
- `tenacity`로 짧은 지수 백오프(2회 이하)를 적용해 일시적인 네트워크 오류 또는 5xx 응답만 재시도한다.
- 헬스 신호를 레지스트리로 노출해 불안정한 제공자를 우회하고, 실패 시 구조화된 메타데이터로 로깅한다.

```python
class ExternalAPIService:
    def __init__(self, settings: Settings) -> None:
        limits = httpx.Limits(max_connections=100, max_keepalive_connections=20, keepalive_expiry=60)
        timeout = httpx.Timeout(connect=3.0, read=10.0, write=5.0, pool=3.0)
        self._client = httpx.AsyncClient(base_url=settings.base_url, limits=limits, timeout=timeout)

    async def close(self) -> None:
        if not self._client.is_closed:
            await self._client.aclose()

    @retry(stop=stop_after_attempt(2), wait=wait_exponential(multiplier=0.1, max=0.5), reraise=True,
           retry=retry_if_exception_type(httpx.RequestError))
    async def get(self, path: str) -> httpx.Response:
        return await self._client.get(path)
```

## 관측성 및 로깅
- 서버와 애플리케이션 로그를 JSON 형태로 표준화해 다운스트림 도구가 정확히 파싱하도록 한다.
- 요청 스팬은 `agent-invocation:<operation>`처럼 의미 있는 이름으로 시작하고 사용자·세션 메타데이터를 첨부한다.
- `sys.excepthook`, `threading.excepthook`을 로깅 파이프라인으로 연결해 예외 로그가 빠지지 않게 한다.
- 로깅 구성은 워커 시작 전에 적용해 Gunicorn과 애플리케이션 포맷이 뒤섞이지 않도록 한다.

**💡 FastAPI Forge Features**:
- **JSONFormatter**: Datadog-optimized with progressive truncation (Docker 16KB limit)
- **Smart Filters**: HealthCheckFilter, LangfuseFilter, LangchainFilter
- **Handler Isolation**: Separate Gunicorn ↔ Application logs
- **Datadog APM Integration**: Automatic trace ID injection with `dd.trace_id`

## 장애 억제 및 운영 모니터링
- 업스트림 429/5xx 응답에는 빠른 재시도와 캐시 폴백을 조합해 부하를 증폭시키지 않는다.
- 모델/서비스 가용성을 레지스트리로 관리해 문제가 있는 제공자를 즉시 차단하고 건강한 대상만 선택한다.
- Gunicorn timeout을 API 게이트웨이, 클라이언트 타임아웃과 정렬해 불필요한 대기 시간을 줄인다.
- `/healthz`, `/readyz` 같은 헬스 엔드포인트를 노출하고 p95 지연, 큐 깊이, 워커 재시작 횟수를 지속적으로 모니터링한다.

## 테스트 원칙
- 엔드포인트는 성공·실패 경로를 모두 포함해 테스트하고, 잘못된 입력·전송 오류·내부 예외를 각각 검증한다.
- 테스트용 앱은 필요한 Bean만 주입한 빌더 헬퍼를 사용하고 `app.dependency_overrides`로 의존성을 교체해 격리한다.
- `AsyncClient` 또는 `TestClient`로 엔드포인트를 exercise하고, 구조화된 응답과 로깅 부작용까지 확인한다.
- 테스트는 빠르고 독립적으로 유지하며, 불필요하게 전역 컨테이너에 의존하지 않도록 한다.

## 추가 모범 사례
- 라우터는 `response_model`, status code, 예시를 명시해 OpenAPI 정확도를 유지한다.
- 모듈 계층을 분리해 하위 계층이 상위 조정 로직을 알지 못하게 하고, 설정은 환경변수·시크릿 매니저를 통해 주입한다.
- 미들웨어 순서를 문서화(CORS → TrustedHost → SecurityHeaders 등)하고, 필요 시 정책 변경이 빠르게 전파되게 한다.

---

## Related Resources

- [FastAPI Official Documentation](https://fastapi.tiangolo.com/)
- [Uvicorn Deployment](https://www.uvicorn.org/deployment/)
- [Gunicorn Configuration](https://docs.gunicorn.org/en/stable/configure.html)
- [FastAPI Forge Examples](../examples/)
