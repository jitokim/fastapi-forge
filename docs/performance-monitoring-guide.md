# Performance Monitoring & Tuning Guide

FastAPI Forge의 성능 모니터링 도구를 활용한 측정 및 튜닝 가이드

## 목차

1. [개요](#개요)
2. [EventLoopMonitor - 비동기 블로킹 감지](#eventloopmonitor---비동기-블로킹-감지)
3. [GCMonitor - 가비지 컬렉션 모니터링](#gcmonitor---가비지-컬렉션-모니터링)
4. [통합 사용 예시](#통합-사용-예시)
5. [성능 측정 방법론](#성능-측정-방법론)
6. [튜닝 가이드](#튜닝-가이드)
7. [트러블슈팅](#트러블슈팅)

---

## 개요

FastAPI Forge는 두 가지 핵심 모니터링 도구를 제공합니다:

| 도구 | 목적 | 감지 대상 |
|------|------|-----------|
| **EventLoopMonitor** | 비동기 성능 | Event loop blocking (동기 작업) |
| **GCMonitor** | 메모리 관리 | GC 패턴, 메모리 누수 |

### 왜 두 가지 모두 필요한가?

**성능 문제는 두 가지 원인에서 발생합니다:**

1. **CPU/IO Blocking** → EventLoopMonitor가 감지
   - 동기 I/O 작업 (`requests.get()`)
   - CPU 집약 작업 (`time.sleep()`)
   - 블로킹 데이터베이스 쿼리

2. **메모리 부족** → GCMonitor가 감지
   - 과도한 메모리 할당
   - 메모리 누수 (순환 참조)
   - 비효율적인 GC 설정

**함께 사용하면**: 성능 저하의 근본 원인을 정확히 파악할 수 있습니다.

---

## EventLoopMonitor - 비동기 블로킹 감지

### 목적

Python의 `asyncio` event loop는 **단일 스레드**에서 동작합니다. 하나의 작업이 블로킹되면 전체 애플리케이션이 멈춥니다.

**EventLoopMonitor는 이러한 블로킹을 실시간으로 감지합니다.**

### 동작 원리

```python
# 내부 동작
async def _monitor_loop(self):
    while not self._should_stop:
        expected = self.check_interval  # 예: 0.1초
        start = time.perf_counter()

        await asyncio.sleep(expected)  # 0.1초 대기 예상

        actual = time.perf_counter() - start

        if actual > expected + self.threshold:
            # 블로킹 감지! (예: 0.25초 실제 소요)
            self._log_blocking(expected, actual)
```

**핵심**: `asyncio.sleep(0.1)`이 0.1초보다 오래 걸리면 → 누군가 event loop를 블로킹한 것!

### 기본 사용법

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi_forge.utils import EventLoopMonitor

@asynccontextmanager
async def lifespan(app: FastAPI):
    # 시작
    monitor = EventLoopMonitor(
        check_interval=0.1,      # 100ms마다 체크
        threshold=0.05,          # 50ms 이상 지연 시 경고
        log_excess_only=True,    # 문제 발생 시만 로그
        capture_stack_trace=True # 블로킹 코드 위치 캡처
    )
    await monitor.start()
    app.state.event_loop_monitor = monitor

    yield

    # 종료
    await monitor.stop()

app = FastAPI(lifespan=lifespan)
```

### 설정 파라미터

#### 1. `check_interval` (체크 주기)

```python
check_interval=0.1  # 100ms (기본값, 권장)
```

**선택 가이드:**
- **0.05초 (50ms)**: 민감한 감지 (실시간 API)
- **0.1초 (100ms)**: 표준 설정 (대부분의 경우)
- **0.2초 (200ms)**: 낮은 오버헤드 (백그라운드 작업)

**트레이드오프:**
- 짧을수록: 빠른 감지, 높은 오버헤드
- 길수록: 느린 감지, 낮은 오버헤드

#### 2. `threshold` (블로킹 임계값)

```python
threshold=0.05  # 50ms 이상 지연 시 경고
```

**선택 가이드:**
- **0.01초 (10ms)**: 매우 민감 (초저지연 요구)
- **0.05초 (50ms)**: 표준 설정 (웹 API)
- **0.1초 (100ms)**: 관대한 설정 (배치 작업)

**계산 예시:**
```
check_interval=0.1, threshold=0.05 설정 시:
- 예상: 100ms 대기
- 실제: 160ms 소요
- 초과: 60ms (> 50ms threshold) → 경고!
```

#### 3. `log_excess_only` (로깅 모드)

```python
log_excess_only=True  # 문제 발생 시만 로그 (권장)
log_excess_only=False # 모든 체크마다 로그 (디버깅용)
```

#### 4. `capture_stack_trace` (스택 트레이스)

```python
capture_stack_trace=True  # 블로킹 코드 위치 캡처 (권장)
capture_stack_trace=False # 스택 트레이스 비활성화 (성능 우선)
```

### 출력 로그 예시

**블로킹 감지 시:**
```json
{
  "timestamp": "2025-10-30T10:00:00Z",
  "level": "WARNING",
  "logger": "fastapi_forge.utils.blocking_detector",
  "message": "[EVENT_LOOP_BLOCKED] Event loop blocking detected\n\nRunning tasks:\nTask: process_payment\n  File \"handlers.py\", line 42, in process_payment\n    result = requests.get(payment_api)  # 블로킹 코드!",
  "expected_delay_ms": 100.0,
  "actual_delay_ms": 250.0,
  "excess_delay_ms": 150.0,
  "blocking_ratio": 150.0
}
```

### 성능 영향

```
check_interval=0.1 (100ms) 기준:
- CPU 사용: <0.1% per check
- 메모리: 1-2KB per stack trace
- 처리량 영향: 무시 가능
```

---

## GCMonitor - 가비지 컬렉션 모니터링

### 목적

Python의 GC(Garbage Collector)는 메모리를 자동으로 관리하지만, **잘못된 설정이나 메모리 누수**는 성능 저하와 OOM을 유발합니다.

**GCMonitor는 GC 동작을 추적하여 메모리 문제를 조기에 감지합니다.**

### Python GC 기초

Python은 **세대별 가비지 컬렉션(Generational GC)**을 사용합니다:

```
┌─────────────┐
│  Generation 0  │ (young objects)
│  새로 생성된   │ → 대부분 여기서 해제
│  객체들       │
└─────────────┘
      ↓ 생존
┌─────────────┐
│  Generation 1  │ (middle-aged)
│  gen0에서     │ → 일부 여기서 해제
│  살아남은 객체 │
└─────────────┘
      ↓ 생존
┌─────────────┐
│  Generation 2  │ (old objects)
│  장수 객체    │ → 최종 정리
└─────────────┘
```

**GC Threshold (기본값: 700, 10, 10)**:
```
gen0: 700개 객체 생성 시 GC 실행
gen1: gen0 GC 10번 실행 시 GC 실행
gen2: gen1 GC 10번 실행 시 GC 실행
```

### 기본 사용법

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi_forge.monitoring import GCMonitor

@asynccontextmanager
async def lifespan(app: FastAPI):
    # 시작
    gc_monitor = GCMonitor(
        threshold=(500, 5, 5),  # GC threshold 설정
        log_interval=60,        # 60초마다 통계 로그
    )
    await gc_monitor.start()
    app.state.gc_monitor = gc_monitor

    yield

    # 종료
    await gc_monitor.stop()

app = FastAPI(lifespan=lifespan)
```

### 설정 파라미터

#### 1. `threshold` (GC 임계값)

```python
# 환경별 권장 설정
threshold=(500, 5, 5)   # 메모리 제약 (2GB/4workers)
threshold=(650, 8, 8)   # 균형 잡힌 환경 (4GB/4workers)
threshold=(700, 10, 10) # Python 기본값
threshold=None          # 기본값 유지 (튜닝 안 함)
```

**선택 가이드:**

| 환경 | 메모리/Worker | 권장 Threshold | 이유 |
|------|---------------|----------------|------|
| 매우 제약 | < 500MB | (400, 5, 5) | 자주 GC로 OOM 방지 |
| 제약 | 500MB-1GB | (500, 5, 5) | 균형 잡힌 GC |
| 표준 | 1GB-2GB | (650, 8, 8) | 적당한 GC |
| 여유 | > 2GB | (700, 10, 10) | Python 기본값 |

**GC 빈도 비교:**
```
Threshold (700, 10, 10):
- gen0: 700개마다
- gen1: 7,000개마다
- gen2: 70,000개마다

Threshold (500, 5, 5):
- gen0: 500개마다 (30% 더 자주)
- gen1: 2,500개마다 (64% 더 자주)
- gen2: 12,500개마다 (82% 더 자주)
```

#### 2. `log_interval` (로깅 주기)

```python
log_interval=60   # 60초마다 (권장)
log_interval=120  # 2분마다 (낮은 로그 볼륨)
log_interval=30   # 30초마다 (실시간 모니터링)
```

### 출력 로그 예시

**Worker 시작 시 (초기 상태):**
```json
{
  "timestamp": "2025-10-30T10:00:00Z",
  "level": "INFO",
  "message": "GC initial state",
  "worker_pid": 12345,
  "threshold": [700, 10, 10],
  "gen0_collections": 0,
  "gen0_collected": 0,
  "gen0_uncollectable": 0
}
```

**Threshold 설정:**
```json
{
  "timestamp": "2025-10-30T10:00:01Z",
  "level": "INFO",
  "message": "GC threshold configured",
  "worker_pid": 12345,
  "old_threshold": [700, 10, 10],
  "new_threshold": [500, 5, 5]
}
```

**주기적 통계 (60초마다):**
```json
{
  "timestamp": "2025-10-30T10:01:00Z",
  "level": "INFO",
  "message": "GC stats snapshot",
  "worker_pid": 12345,
  "threshold": [500, 5, 5],
  "gen0_collections": 801,
  "gen0_collected": 6128,
  "gen0_uncollectable": 0,
  "gen1_collections": 77,
  "gen1_collected": 1140,
  "gen1_uncollectable": 0,
  "gen2_collections": 6,
  "gen2_collected": 228,
  "gen2_uncollectable": 0
}
```

### GC Stats 필드 의미

| 필드 | 의미 | 정상 범위 | 경고 |
|------|------|-----------|------|
| `collections` | GC 실행 횟수 (누적) | 계속 증가 | 급증 시 부하 증가 |
| `collected` | 수집된 객체 수 (누적) | 계속 증가 | 비율 낮으면 메모리 부족 |
| `uncollectable` | 수집 불가 객체 | **0** | **> 0 시 메모리 누수!** |

**핵심 지표: `uncollectable`**
```python
uncollectable = 0  ✅ 정상 (메모리 누수 없음)
uncollectable > 0  ⚠️ 경고 (순환 참조 문제)
```

---

## 통합 사용 예시

### 최소 설정 (Production 권장)

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi_forge.utils import EventLoopMonitor
from fastapi_forge.monitoring import GCMonitor

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Event Loop 모니터링
    event_loop_monitor = EventLoopMonitor(
        check_interval=0.1,
        threshold=0.05,
        log_excess_only=True,
        capture_stack_trace=True
    )
    await event_loop_monitor.start()
    app.state.event_loop_monitor = event_loop_monitor

    # GC 모니터링
    gc_monitor = GCMonitor(
        threshold=(500, 5, 5),  # 환경에 맞게 조정
        log_interval=60
    )
    await gc_monitor.start()
    app.state.gc_monitor = gc_monitor

    yield

    # 종료
    await gc_monitor.stop()
    await event_loop_monitor.stop()

app = FastAPI(lifespan=lifespan)
```

### 환경 변수 기반 동적 설정

```python
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi_forge.utils import EventLoopMonitor
from fastapi_forge.monitoring import GCMonitor

@asynccontextmanager
async def lifespan(app: FastAPI):
    # 환경 변수에서 설정 읽기
    env = os.getenv("ENV", "production")
    workers = int(os.getenv("WORKERS", "4"))
    memory_gb = float(os.getenv("TOTAL_MEMORY_GB", "2.0"))

    # Event Loop Monitor
    event_loop_monitor = EventLoopMonitor(
        check_interval=float(os.getenv("EVENT_LOOP_CHECK_INTERVAL", "0.1")),
        threshold=float(os.getenv("EVENT_LOOP_THRESHOLD", "0.05")),
        log_excess_only=env == "production",
        capture_stack_trace=True
    )
    await event_loop_monitor.start()

    # GC Monitor - 메모리에 따라 동적 threshold
    memory_per_worker = memory_gb / workers
    if memory_per_worker < 0.8:
        gc_threshold = (400, 5, 5)  # 매우 제약
    elif memory_per_worker < 1.2:
        gc_threshold = (500, 5, 5)  # 제약
    else:
        gc_threshold = (650, 8, 8)  # 표준

    gc_monitor = GCMonitor(
        threshold=gc_threshold,
        log_interval=int(os.getenv("GC_LOG_INTERVAL", "60"))
    )
    await gc_monitor.start()

    app.state.event_loop_monitor = event_loop_monitor
    app.state.gc_monitor = gc_monitor

    yield

    await gc_monitor.stop()
    await event_loop_monitor.stop()

app = FastAPI(lifespan=lifespan)
```

**환경 변수 예시 (.env):**
```bash
ENV=production
WORKERS=4
TOTAL_MEMORY_GB=2.0

# Event Loop Monitor
EVENT_LOOP_CHECK_INTERVAL=0.1
EVENT_LOOP_THRESHOLD=0.05

# GC Monitor
GC_LOG_INTERVAL=60
```

---

## 성능 측정 방법론

### 1. Baseline 측정 (기준선 설정)

**목적**: 정상 상태의 성능 지표를 파악

**절차**:
```
1. 모니터 활성화
2. 정상 부하로 1시간 운영
3. 평균 지표 기록

기록할 지표:
- Event Loop: 평균 지연, 최대 지연, 블로킹 빈도
- GC: gen0/1/2 collections, collected, uncollectable
```

**Datadog 쿼리 예시**:
```
# Event Loop 평균 지연
avg:actual_delay_ms by worker_pid

# GC 빈도
rate(gen0_collections) by worker_pid
```

### 2. Load Testing (부하 테스트)

**목적**: 부하 증가 시 성능 변화 측정

**도구**: k6, Locust, Apache Bench

**k6 예시**:
```javascript
import http from 'k6/http';
import { sleep } from 'k6';

export const options = {
  stages: [
    { duration: '1m', target: 10 },   // Ramp up
    { duration: '5m', target: 50 },   // Steady state
    { duration: '1m', target: 0 },    // Ramp down
  ],
};

export default function () {
  http.get('http://localhost:8000/api/endpoint');
  sleep(1);
}
```

**측정 항목**:
```
부하 10 → 50 증가 시:
- Event Loop 블로킹 증가율
- GC collections 증가율
- Response time P95/P99
- Error rate
```

### 3. 메모리 누수 테스트

**목적**: 장시간 운영 시 메모리 누수 감지

**절차**:
```
1. GCMonitor 활성화
2. 일정 부하로 8시간+ 운영
3. uncollectable 추적

경고 신호:
- uncollectable > 0
- gen2_collected가 계속 증가하지만 메모리는 안 줄어듦
- Worker 재시작 시 메모리 크게 감소
```

**Datadog 알림 설정**:
```
Alert: @gen1_uncollectable:>0 OR @gen2_uncollectable:>0
Message: "Memory leak detected! Check for circular references"
```

### 4. Event Loop 블로킹 분석

**목적**: 블로킹 코드 위치 파악

**절차**:
```
1. capture_stack_trace=True 활성화
2. 블로킹 발생 시 로그 확인
3. 스택 트레이스에서 원인 코드 파악

로그 예시:
Task: process_payment
  File "handlers.py", line 42, in process_payment
    result = requests.get(payment_api)  ← 블로킹 코드!
```

**해결 방법**:
```python
# Before (블로킹)
result = requests.get(payment_api)

# After (비블로킹)
import httpx
async with httpx.AsyncClient() as client:
    result = await client.get(payment_api)
```

---

## 튜닝 가이드

### Event Loop Tuning

#### 문제 1: 빈번한 블로킹 경고

**증상**:
```json
{
  "message": "Event loop blocking detected",
  "excess_delay_ms": 150.0,
  "blocking_ratio": 150.0
}
```

**원인 분석**:
1. 스택 트레이스 확인 → 블로킹 코드 위치
2. 동기 I/O? CPU 집약 작업?

**해결 방법**:

**A. 동기 I/O → 비동기로 변경**
```python
# Before
import requests
response = requests.get(url)  # 블로킹!

# After
import httpx
async with httpx.AsyncClient() as client:
    response = await client.get(url)  # 비블로킹
```

**B. CPU 집약 작업 → ThreadPoolExecutor**
```python
# Before
def heavy_computation():
    return sum(range(10000000))

result = heavy_computation()  # 블로킹!

# After
import asyncio
from concurrent.futures import ThreadPoolExecutor

executor = ThreadPoolExecutor()

async def process():
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(
        executor,
        heavy_computation
    )  # 비블로킹
```

**C. 데이터베이스 → 비동기 드라이버**
```python
# Before (psycopg2)
import psycopg2
conn = psycopg2.connect(...)
cursor = conn.cursor()
cursor.execute("SELECT ...")  # 블로킹!

# After (asyncpg)
import asyncpg
conn = await asyncpg.connect(...)
rows = await conn.fetch("SELECT ...")  # 비블로킹
```

#### 문제 2: False Positive (잘못된 경고)

**증상**: 실제 블로킹 없는데 경고 발생

**원인**: threshold가 너무 낮음

**해결**:
```python
# threshold 완화
EventLoopMonitor(
    check_interval=0.1,
    threshold=0.1,  # 0.05 → 0.1로 증가
)
```

### GC Tuning

#### 문제 1: OOM (Out of Memory)

**증상**:
```bash
[ERROR] Worker (pid:57) was sent SIGKILL! Perhaps out of memory?
```

**진단**:
```
1. GC stats 확인:
   - uncollectable > 0? → 메모리 누수
   - gen2_collections 낮음? → threshold 너무 높음
   - collected/collections 비율 낮음? → 객체가 안 해제됨

2. 메모리 사용 패턴:
   - 시간에 따라 증가? → 누수
   - 부하에 비례? → Capacity 부족
```

**해결 방법**:

**A. Threshold 낮추기 (더 자주 GC)**
```python
# Before
GCMonitor(threshold=(700, 10, 10))

# After (메모리 제약 환경)
GCMonitor(threshold=(500, 5, 5))  # 30-82% 더 자주 GC
```

**B. 메모리 누수 해결 (uncollectable > 0)**
```python
# Before (순환 참조 + __del__)
class Node:
    def __init__(self):
        self.ref = None

    def __del__(self):  # 문제!
        print("Deleting")

a = Node()
b = Node()
a.ref = b
b.ref = a  # 순환 참조 → uncollectable

# After (weakref 사용)
import weakref

class Node:
    def __init__(self):
        self._ref = None

    @property
    def ref(self):
        return self._ref() if self._ref else None

    @ref.setter
    def ref(self, value):
        self._ref = weakref.ref(value) if value else None
```

**C. Worker 수 조정**
```
2GB 메모리, 4 workers:
2GB ÷ 4 = 500MB/worker → 타이트!

옵션 1: Workers 줄이기
2GB ÷ 2 = 1GB/worker → 여유

옵션 2: 메모리 증설
4GB ÷ 4 = 1GB/worker → 여유
```

#### 문제 2: 높은 CPU 사용 (과도한 GC)

**증상**:
- CPU 사용률 높음
- gen0_collections 매우 빈번

**원인**: threshold가 너무 낮음

**해결**:
```python
# Before (너무 자주 GC)
GCMonitor(threshold=(400, 5, 5))

# After
GCMonitor(threshold=(650, 8, 8))  # 완화
```

#### 문제 3: 메모리 누수 지속 (uncollectable > 0)

**진단**:
```python
# Datadog에서 확인
@gen2_uncollectable:>0
```

**해결 절차**:

1. **순환 참조 찾기**
```python
import gc

# GC 디버그 모드 활성화
gc.set_debug(gc.DEBUG_SAVEALL)

# GC 실행
gc.collect()

# uncollectable 객체 확인
for obj in gc.garbage:
    print(type(obj), obj)
```

2. **__del__ 메서드 제거**
```python
# __del__이 있으면 순환 참조 시 uncollectable됨
class MyClass:
    def __del__(self):  # 가능하면 제거
        pass
```

3. **weakref 사용**
```python
import weakref

# 강한 참조 대신 약한 참조 사용
self.parent = weakref.ref(parent)
```

---

## 트러블슈팅

### Event Loop 관련

#### Q1: "Event loop blocking" 경고가 계속 발생해요

**체크리스트**:
1. ☐ 스택 트레이스에서 블로킹 코드 확인
2. ☐ 동기 I/O → 비동기로 변경
3. ☐ CPU 집약 작업 → executor로 이동
4. ☐ threshold 너무 낮지 않은지 확인 (0.05 권장)

#### Q2: 블로킹이 없는데도 경고가 나와요

**원인**: 시스템 부하로 인한 일시적 지연

**해결**:
```python
# threshold 완화
EventLoopMonitor(threshold=0.1)  # 0.05 → 0.1

# 또는 log_excess_only 확인
EventLoopMonitor(log_excess_only=True)
```

#### Q3: 스택 트레이스가 캡처되지 않아요

**확인**:
```python
EventLoopMonitor(
    capture_stack_trace=True  # 이 옵션 확인
)
```

### GC 관련

#### Q1: uncollectable이 0보다 커요

**즉시 확인**:
```python
import gc
gc.set_debug(gc.DEBUG_SAVEALL)
gc.collect()
print(gc.garbage)  # uncollectable 객체 출력
```

**해결**: [메모리 누수 해결](#문제-3-메모리-누수-지속-uncollectable--0) 참고

#### Q2: gen2_collections가 증가하지 않아요

**원인**: threshold가 너무 높거나, 객체가 gen2까지 도달 안 함

**확인**:
```python
# 현재 threshold 확인
import gc
print(gc.get_threshold())

# threshold 낮추기
GCMonitor(threshold=(500, 5, 5))
```

#### Q3: OOM이 계속 발생해요

**단계별 진단**:

1. **메모리 누수 확인**
```
uncollectable > 0? → 메모리 누수
```

2. **GC 빈도 확인**
```
gen0_collections 낮음? → threshold 낮추기
```

3. **Capacity 확인**
```
메모리 사용량이 시간에 비례? → 누수
메모리 사용량이 부하에 비례? → Capacity 부족
```

4. **해결 우선순위**:
```
1순위: 메모리 누수 해결 (uncollectable)
2순위: GC threshold 튜닝
3순위: Worker 수 조정 또는 메모리 증설
```

---

## 모니터링 대시보드 구성

### Datadog Dashboard 예시

**Event Loop Metrics:**
```
# 평균 지연
avg:actual_delay_ms by worker_pid

# 최대 지연
max:actual_delay_ms by worker_pid

# 블로킹 빈도
count:excess_delay_ms:>50 by worker_pid

# 블로킹 비율
(sum:excess_delay_ms) / (sum:actual_delay_ms) * 100
```

**GC Metrics:**
```
# GC 빈도
rate(gen0_collections) by worker_pid
rate(gen1_collections) by worker_pid
rate(gen2_collections) by worker_pid

# 수집 효율
gen0_collected / gen0_collections
gen1_collected / gen1_collections
gen2_collected / gen2_collections

# 메모리 누수
max:gen0_uncollectable by worker_pid
max:gen1_uncollectable by worker_pid
max:gen2_uncollectable by worker_pid
```

**알림 규칙:**
```
# Event Loop 블로킹
Alert: avg(excess_delay_ms):last_5m > 100
Message: "Event loop blocking detected for 5+ minutes"

# 메모리 누수
Alert: max(gen2_uncollectable):last_1m > 0
Message: "Memory leak detected! Uncollectable objects found"

# GC 과부하
Alert: rate(gen0_collections):last_5m > 100
Message: "Excessive GC activity - check memory usage"
```

---

## 참고 자료

### Python 공식 문서
- [asyncio - Asynchronous I/O](https://docs.python.org/3/library/asyncio.html)
- [gc - Garbage Collector interface](https://docs.python.org/3/library/gc.html)

### 관련 도구
- [Datadog APM](https://docs.datadoghq.com/tracing/)
- [Gunicorn](https://docs.gunicorn.org/)
- [k6 Load Testing](https://k6.io/docs/)

### FastAPI Forge
- [GitHub Repository](https://github.com/jitokim/fastapi-forge)
- [Examples](../examples/)

---

**문서 버전**: 1.0
**최종 업데이트**: 2025-10-30
**작성자**: FastAPI Forge Contributors
