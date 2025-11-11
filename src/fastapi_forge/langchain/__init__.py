"""LangChain integration utilities for robust chain execution.

This module provides utilities for building production-ready LangChain applications
with fallback mechanisms and error handling.

Available utilities:
    - with_runnable_fallback: Create chains with custom fallback behavior
    - with_fallback_dict_chain: Create chains with built-in LangChain fallback

Example:
    >>> from fastapi_forge.langchain import with_runnable_fallback
    >>> from langchain_core.runnables import RunnableLambda
    >>>
    >>> primary = RunnableLambda(lambda x: x["value"] * 2)
    >>> fallback = RunnableLambda(lambda x: 0)
    >>> chain = with_runnable_fallback(primary, fallback)
"""

from fastapi_forge.langchain.fallback import (
    with_fallback_dict_chain,
    with_runnable_fallback,
)

__all__ = [
    "with_runnable_fallback",
    "with_fallback_dict_chain",
]
