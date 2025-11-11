"""Unit tests for LangChain fallback utilities."""

import logging
from typing import Any, AsyncIterator, Dict, Iterator

import pytest

# Skip tests if langchain is not installed
pytest.importorskip("langchain_core")

from langchain_core.runnables import RunnableLambda

from fastapi_forge.langchain import with_fallback_dict_chain, with_runnable_fallback


class TestWithFallbackDictChain:
    """Tests for with_fallback_dict_chain utility."""

    def test_primary_success(self):
        """Test that primary chain executes successfully when no error occurs."""
        primary = RunnableLambda(lambda x: x["value"] * 2)
        fallback = RunnableLambda(lambda x: 0)

        chain = with_fallback_dict_chain(primary, fallback)
        result = chain.invoke({"value": 5})

        assert result == 10

    def test_fallback_on_primary_failure(self):
        """Test that fallback chain executes when primary fails."""
        primary = RunnableLambda(lambda x: 1 / x["denominator"])
        fallback = RunnableLambda(lambda x: -1)

        chain = with_fallback_dict_chain(primary, fallback)
        result = chain.invoke({"denominator": 0})

        assert result == -1

    def test_preserves_primary_exception_type(self):
        """Test that exception type is preserved in fallback."""

        def raise_value_error(x: Dict[str, Any]) -> int:
            raise ValueError("Test error")

        primary = RunnableLambda(raise_value_error)
        fallback = RunnableLambda(lambda x: -1)

        chain = with_fallback_dict_chain(primary, fallback)
        result = chain.invoke({"value": 1})

        # Fallback should handle the error
        assert result == -1


class TestWithRunnableFallback:
    """Tests for with_runnable_fallback utility."""

    # Invoke tests

    def test_invoke_primary_success(self):
        """Test synchronous invoke with successful primary execution."""
        primary = RunnableLambda(lambda x: x["value"] * 2)
        fallback = RunnableLambda(lambda x: 0)

        chain = with_runnable_fallback(primary, fallback)
        result = chain.invoke({"value": 5})

        assert result == 10

    def test_invoke_fallback_triggered(self):
        """Test synchronous invoke with fallback triggered."""
        primary = RunnableLambda(lambda x: x["value"] / x["divisor"])
        fallback = RunnableLambda(lambda x: -1)

        chain = with_runnable_fallback(primary, fallback)
        result = chain.invoke({"value": 10, "divisor": 0})

        assert result == -1

    def test_invoke_with_multiple_exception_types(self):
        """Test that various exception types trigger fallback."""

        def raise_different_errors(x: Dict[str, Any]) -> int:
            error_type = x.get("error_type")
            if error_type == "value":
                raise ValueError("Value error")
            elif error_type == "key":
                raise KeyError("Key error")
            elif error_type == "type":
                raise TypeError("Type error")
            return 42

        primary = RunnableLambda(raise_different_errors)
        fallback = RunnableLambda(lambda x: -1)
        chain = with_runnable_fallback(primary, fallback)

        assert chain.invoke({"error_type": "value"}) == -1
        assert chain.invoke({"error_type": "key"}) == -1
        assert chain.invoke({"error_type": "type"}) == -1
        assert chain.invoke({"error_type": None}) == 42

    # Async invoke tests

    @pytest.mark.asyncio
    async def test_ainvoke_primary_success(self):
        """Test asynchronous invoke with successful primary execution."""

        async def async_double(x: Dict[str, Any]) -> int:
            return x["value"] * 2

        primary = RunnableLambda(async_double)
        fallback = RunnableLambda(lambda x: 0)

        chain = with_runnable_fallback(primary, fallback)
        result = await chain.ainvoke({"value": 5})

        assert result == 10

    @pytest.mark.asyncio
    async def test_ainvoke_fallback_triggered(self):
        """Test asynchronous invoke with fallback triggered."""

        async def async_divide(x: Dict[str, Any]) -> float:
            return x["value"] / x["divisor"]

        primary = RunnableLambda(async_divide)
        fallback = RunnableLambda(lambda x: -1)

        chain = with_runnable_fallback(primary, fallback)
        result = await chain.ainvoke({"value": 10, "divisor": 0})

        assert result == -1

    # Stream tests

    def test_stream_primary_success(self):
        """Test synchronous streaming with successful primary execution."""

        def stream_numbers(x: Dict[str, Any]) -> Iterator[int]:
            for i in range(x["count"]):
                yield i

        primary = RunnableLambda(stream_numbers)
        fallback = RunnableLambda(lambda x: iter([]))

        chain = with_runnable_fallback(primary, fallback)
        result = list(chain.stream({"count": 3}))

        assert result == [0, 1, 2]

    def test_stream_fallback_triggered(self):
        """Test synchronous streaming with fallback triggered."""

        def stream_with_error(x: Dict[str, Any]) -> Iterator[int]:
            raise ValueError("Stream error")
            yield  # pragma: no cover

        def fallback_stream(x: Dict[str, Any]) -> Iterator[int]:
            for i in range(3):
                yield i * 10

        primary = RunnableLambda(stream_with_error)
        fallback = RunnableLambda(fallback_stream)

        chain = with_runnable_fallback(primary, fallback)
        result = list(chain.stream({"count": 3}))

        assert result == [0, 10, 20]

    def test_stream_with_switch_marker(self):
        """Test synchronous streaming with switch marker on fallback."""

        def stream_with_error(x: Dict[str, Any]) -> Iterator[int]:
            raise ValueError("Stream error")
            yield  # pragma: no cover

        def fallback_stream(x: Dict[str, Any]) -> Iterator[int]:
            yield 100
            yield 200

        primary = RunnableLambda(stream_with_error)
        fallback = RunnableLambda(fallback_stream)

        marker = {"type": "fallback_activated"}
        chain = with_runnable_fallback(primary, fallback, switch_marker=marker)
        result = list(chain.stream({"count": 3}))

        assert marker in result
        assert 100 in result
        assert 200 in result

    def test_stream_partial_success_with_error(self):
        """Test streaming that yields some values before failing."""

        def stream_partial(x: Dict[str, Any]) -> Iterator[int]:
            yield 1
            yield 2
            raise ValueError("Error after partial yield")

        def fallback_stream(x: Dict[str, Any]) -> Iterator[int]:
            yield 100

        primary = RunnableLambda(stream_partial)
        fallback = RunnableLambda(fallback_stream)

        chain = with_runnable_fallback(primary, fallback)
        result = list(chain.stream({"count": 3}))

        # Should have partial results from primary, then fallback
        assert 1 in result
        assert 2 in result
        assert 100 in result

    # Async stream tests

    @pytest.mark.asyncio
    async def test_astream_primary_success(self):
        """Test asynchronous streaming with successful primary execution."""

        async def async_stream_numbers(x: Dict[str, Any]) -> AsyncIterator[int]:
            for i in range(x["count"]):
                yield i

        primary = RunnableLambda(async_stream_numbers)
        fallback = RunnableLambda(lambda x: iter([]))

        chain = with_runnable_fallback(primary, fallback)
        result = [chunk async for chunk in chain.astream({"count": 3})]

        assert result == [0, 1, 2]

    @pytest.mark.asyncio
    async def test_astream_fallback_triggered(self):
        """Test asynchronous streaming with fallback triggered."""

        async def async_stream_with_error(x: Dict[str, Any]) -> AsyncIterator[int]:
            raise ValueError("Stream error")
            yield  # pragma: no cover

        async def async_fallback_stream(x: Dict[str, Any]) -> AsyncIterator[int]:
            for i in range(3):
                yield i * 10

        primary = RunnableLambda(async_stream_with_error)
        fallback = RunnableLambda(async_fallback_stream)

        chain = with_runnable_fallback(primary, fallback)
        result = [chunk async for chunk in chain.astream({"count": 3})]

        assert result == [0, 10, 20]

    @pytest.mark.asyncio
    async def test_astream_with_switch_marker(self):
        """Test asynchronous streaming with switch marker on fallback."""

        async def async_stream_with_error(x: Dict[str, Any]) -> AsyncIterator[int]:
            raise ValueError("Stream error")
            yield  # pragma: no cover

        async def async_fallback_stream(x: Dict[str, Any]) -> AsyncIterator[int]:
            yield 100
            yield 200

        primary = RunnableLambda(async_stream_with_error)
        fallback = RunnableLambda(async_fallback_stream)

        marker = {"type": "fallback_activated", "reason": "test"}
        chain = with_runnable_fallback(primary, fallback, switch_marker=marker)
        result = [chunk async for chunk in chain.astream({"count": 3})]

        assert marker in result
        assert 100 in result
        assert 200 in result

    @pytest.mark.asyncio
    async def test_astream_partial_success_with_error(self):
        """Test async streaming that yields some values before failing."""

        async def async_stream_partial(x: Dict[str, Any]) -> AsyncIterator[int]:
            yield 1
            yield 2
            raise ValueError("Error after partial yield")

        async def async_fallback_stream(x: Dict[str, Any]) -> AsyncIterator[int]:
            yield 100

        primary = RunnableLambda(async_stream_partial)
        fallback = RunnableLambda(async_fallback_stream)

        chain = with_runnable_fallback(primary, fallback)
        result = [chunk async for chunk in chain.astream({"count": 3})]

        # Should have partial results from primary, then fallback
        assert 1 in result
        assert 2 in result
        assert 100 in result

    # Logging tests

    def test_fallback_logging(self, caplog):
        """Test that fallback activation is logged."""
        primary = RunnableLambda(lambda x: 1 / x["value"])
        fallback = RunnableLambda(lambda x: 0)

        chain = with_runnable_fallback(primary, fallback)

        with caplog.at_level(logging.WARNING, logger="fastapi_forge.langchain.fallback"):
            result = chain.invoke({"value": 0})

        assert "switching to fallback" in caplog.text
        assert result == 0

    @pytest.mark.asyncio
    async def test_async_fallback_logging(self, caplog):
        """Test that async fallback activation is logged."""

        async def async_divide(x: Dict[str, Any]) -> float:
            return 1 / x["value"]

        primary = RunnableLambda(async_divide)
        fallback = RunnableLambda(lambda x: 0)

        chain = with_runnable_fallback(primary, fallback)

        with caplog.at_level(logging.WARNING, logger="fastapi_forge.langchain.fallback"):
            result = await chain.ainvoke({"value": 0})

        assert "switching to fallback" in caplog.text
        assert result == 0

    # Edge cases

    def test_fallback_chain_also_fails(self):
        """Test behavior when fallback chain also raises an exception."""
        primary = RunnableLambda(lambda x: 1 / x["value"])
        fallback = RunnableLambda(lambda x: x["missing_key"])

        chain = with_runnable_fallback(primary, fallback)

        with pytest.raises(KeyError):
            chain.invoke({"value": 0})

    def test_none_switch_marker(self):
        """Test that None switch marker is not yielded."""

        def stream_with_error(x: Dict[str, Any]) -> Iterator[int]:
            raise ValueError("Error")
            yield  # pragma: no cover

        primary = RunnableLambda(stream_with_error)
        fallback = RunnableLambda(lambda x: iter([100]))

        # Explicitly pass None
        chain = with_runnable_fallback(primary, fallback, switch_marker=None)
        result = list(chain.stream({"value": 1}))

        assert None not in result
        assert 100 in result

    def test_complex_data_types(self):
        """Test fallback with complex input/output types."""

        def process_complex(x: Dict[str, Any]) -> Dict[str, Any]:
            if x.get("fail"):
                raise ValueError("Processing failed")
            return {"result": x["data"] * 2, "metadata": {"processed": True}}

        def fallback_complex(x: Dict[str, Any]) -> Dict[str, Any]:
            return {"result": 0, "metadata": {"processed": False, "fallback": True}}

        primary = RunnableLambda(process_complex)
        fallback = RunnableLambda(fallback_complex)

        chain = with_runnable_fallback(primary, fallback)

        # Success case
        result = chain.invoke({"data": 5, "fail": False})
        assert result == {"result": 10, "metadata": {"processed": True}}

        # Fallback case
        result = chain.invoke({"data": 5, "fail": True})
        assert result == {"result": 0, "metadata": {"processed": False, "fallback": True}}


class TestIntegration:
    """Integration tests combining multiple features."""

    @pytest.mark.asyncio
    async def test_nested_fallback_chains(self):
        """Test chaining multiple fallback layers."""

        async def primary_fn(x: Dict[str, Any]) -> str:
            if x.get("fail_primary"):
                raise ValueError("Primary failed")
            return "primary"

        async def secondary_fn(x: Dict[str, Any]) -> str:
            if x.get("fail_secondary"):
                raise ValueError("Secondary failed")
            return "secondary"

        async def tertiary_fn(x: Dict[str, Any]) -> str:
            return "tertiary"

        primary = RunnableLambda(primary_fn)
        secondary = RunnableLambda(secondary_fn)
        tertiary = RunnableLambda(tertiary_fn)

        # Create nested fallbacks: primary → secondary → tertiary
        chain_with_secondary = with_runnable_fallback(primary, secondary)
        chain_with_tertiary = with_runnable_fallback(chain_with_secondary, tertiary)

        # Test all paths
        result = await chain_with_tertiary.ainvoke({})
        assert result == "primary"

        result = await chain_with_tertiary.ainvoke({"fail_primary": True})
        assert result == "secondary"

        result = await chain_with_tertiary.ainvoke(
            {"fail_primary": True, "fail_secondary": True}
        )
        assert result == "tertiary"

    def test_with_runnable_config(self):
        """Test that RunnableConfig is properly passed through."""
        from langchain_core.runnables import RunnableConfig

        config_used = {"primary": None, "fallback": None}

        def primary_with_config(x: Dict[str, Any], config: RunnableConfig) -> str:
            config_used["primary"] = config
            raise ValueError("Force fallback")

        def fallback_with_config(x: Dict[str, Any], config: RunnableConfig) -> str:
            config_used["fallback"] = config
            return "fallback"

        primary = RunnableLambda(primary_with_config)
        fallback = RunnableLambda(fallback_with_config)

        chain = with_runnable_fallback(primary, fallback)

        test_config = RunnableConfig(tags=["test"], metadata={"key": "value"})
        result = chain.invoke({"value": 1}, config=test_config)

        assert result == "fallback"
        assert config_used["primary"] is not None
        assert config_used["fallback"] is not None
        assert config_used["primary"]["tags"] == ["test"]
        assert config_used["fallback"]["tags"] == ["test"]
