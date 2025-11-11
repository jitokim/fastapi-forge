"""LangChain Runnable fallback utilities.

This module provides utilities for creating robust LangChain chains with fallback behavior.
When a primary chain fails, the fallback chain is automatically invoked as a backup.

Example:
    >>> from langchain_core.runnables import RunnableLambda
    >>> from fastapi_forge.langchain import with_runnable_fallback
    >>>
    >>> primary = RunnableLambda(lambda x: x["value"] * 2)
    >>> fallback = RunnableLambda(lambda x: 0)  # Safe default
    >>> chain = with_runnable_fallback(primary, fallback)
    >>> result = chain.invoke({"value": 5})  # Returns 10
"""

import logging
from typing import Any, AsyncIterator, Iterator, Optional

from langchain_core.runnables import Runnable, RunnableConfig
from langchain_core.runnables.utils import Input, Output

logger = logging.getLogger(__name__)


def with_fallback_dict_chain(
    primary_chain: Runnable,
    fallback_chain: Runnable,
) -> Runnable:
    """Create a chain with built-in fallback using LangChain's native mechanism.

    This uses LangChain's built-in `with_fallbacks` method, which is simpler but
    less flexible than `with_runnable_fallback`. Use this when you don't need
    custom switch markers or fine-grained control over fallback behavior.

    Args:
        primary_chain: The primary runnable to execute first
        fallback_chain: The fallback runnable to use if primary fails

    Returns:
        A Runnable that tries primary_chain first, then fallback_chain on failure

    Example:
        >>> from langchain_core.runnables import RunnableLambda
        >>> primary = RunnableLambda(lambda x: 1 / x)
        >>> fallback = RunnableLambda(lambda x: 0)
        >>> chain = with_fallback_dict_chain(primary, fallback)
        >>> chain.invoke(0)  # Returns 0 instead of raising ZeroDivisionError
    """
    return primary_chain.with_fallbacks(
        fallbacks=[fallback_chain],
        exceptions_to_handle=(Exception,),
    )


def with_runnable_fallback(
    primary_chain: Runnable,
    fallback_chain: Runnable,
    *,
    switch_marker: Optional[Any] = None,
) -> Runnable:
    """Create a robust chain with custom fallback behavior and stream support.

    This function wraps two Runnables (primary and fallback) into a single Runnable
    that automatically switches to the fallback when the primary fails. Unlike
    `with_fallback_dict_chain`, this provides full support for streaming operations
    and allows injecting a custom marker when switching to the fallback.

    The fallback mechanism works for all Runnable operations:
    - invoke/ainvoke: Synchronous/asynchronous single invocation
    - stream/astream: Synchronous/asynchronous streaming

    Args:
        primary_chain: The primary runnable to execute first
        fallback_chain: The fallback runnable to use if primary fails
        switch_marker: Optional value to yield in stream mode when switching
                      to fallback. This allows clients to detect the switch.
                      Only applicable for stream/astream operations.

    Returns:
        A Runnable that implements the fallback logic

    Example:
        >>> from langchain_core.runnables import RunnableLambda
        >>> from langchain_core.output_parsers import StrOutputParser
        >>>
        >>> # Create chains with potential failure points
        >>> primary = RunnableLambda(lambda x: x["data"] / x["divisor"])
        >>> fallback = RunnableLambda(lambda x: "Error: division failed")
        >>>
        >>> # Wrap with fallback
        >>> safe_chain = with_runnable_fallback(
        ...     primary,
        ...     fallback,
        ...     switch_marker={"type": "fallback_activated"}
        ... )
        >>>
        >>> # Normal operation
        >>> result = safe_chain.invoke({"data": 10, "divisor": 2})  # Returns 5
        >>>
        >>> # Fallback triggered
        >>> result = safe_chain.invoke({"data": 10, "divisor": 0})
        >>> # Returns "Error: division failed"

    Note:
        All exceptions from the primary chain are caught and logged. The fallback
        chain is expected to be more resilient. If the fallback also fails, the
        exception will propagate to the caller.
    """

    class _RunnableFallback(Runnable[Input, Output]):
        """Internal Runnable implementation with fallback logic."""

        def __init__(self, primary: Runnable, fallback: Runnable):
            self.primary = primary
            self.fallback = fallback

        def invoke(
            self, input: Input, config: Optional[RunnableConfig] = None, **kwargs: Any
        ) -> Output:
            """Synchronously invoke with fallback support."""
            try:
                return self.primary.invoke(input, config=config, **kwargs)
            except Exception as e:
                logger.warning(
                    f"[with_runnable_fallback] primary_chain invoke failed, "
                    f"switching to fallback: {e}"
                )
                return self.fallback.invoke(input, config=config, **kwargs)

        async def ainvoke(
            self, input: Input, config: Optional[RunnableConfig] = None, **kwargs: Any
        ) -> Output:
            """Asynchronously invoke with fallback support."""
            try:
                return await self.primary.ainvoke(input, config=config, **kwargs)
            except Exception as e:
                logger.warning(
                    f"[with_runnable_fallback] primary_chain ainvoke failed, "
                    f"switching to fallback: {e}"
                )
                return await self.fallback.ainvoke(input, config=config, **kwargs)

        async def astream(
            self, input: Input, config: Optional[RunnableConfig] = None, **kwargs: Any
        ) -> AsyncIterator[Output]:
            """Asynchronously stream with fallback support.

            If the primary chain fails during streaming, optionally yields the
            switch_marker before continuing with the fallback chain.
            """
            try:
                async for chunk in self.primary.astream(input, config=config, **kwargs):
                    yield chunk
                return
            except Exception as e:
                logger.warning(
                    f"[with_runnable_fallback] primary_chain astream error, "
                    f"switching to fallback: {e}"
                )
                if switch_marker is not None:
                    yield switch_marker

            async for chunk in self.fallback.astream(input, config=config, **kwargs):
                yield chunk

        def stream(
            self, input: Input, config: Optional[RunnableConfig] = None, **kwargs: Any
        ) -> Iterator[Output]:
            """Synchronously stream with fallback support.

            If the primary chain fails during streaming, optionally yields the
            switch_marker before continuing with the fallback chain.
            """
            try:
                for chunk in self.primary.stream(input, config=config, **kwargs):
                    yield chunk
                return
            except Exception as e:
                logger.warning(
                    f"[with_runnable_fallback] primary_chain stream error, "
                    f"switching to fallback: {e}"
                )
                if switch_marker is not None:
                    yield switch_marker

            for chunk in self.fallback.stream(input, config=config, **kwargs):
                yield chunk

    return _RunnableFallback(primary_chain, fallback_chain)
