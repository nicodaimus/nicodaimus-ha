"""Shared fixtures for nicodAImus integration tests.

NOTE: Full HA integration tests require Python 3.13+ (for homeassistant>=2025.2).
These tests focus on our business logic (streaming, tool conversion, etc.)
using pure Python mocks, and can run on Python 3.12+.
"""

from __future__ import annotations

from typing import Any

import pytest

from nicodaimus import (
    ChatChunk,
    ChatChoice,
    ChatResponse,
    ChunkChoice,
    ChunkDelta,
    FunctionCall,
    Message,
    ToolCall,
    ToolCallDelta,
    Usage,
)

try:
    from homeassistant.core import HomeAssistant
    from homeassistant.loader import DATA_CUSTOM_COMPONENTS
    from homeassistant.setup import async_setup_component

    @pytest.fixture(autouse=True)
    def auto_enable_custom_integrations(hass: HomeAssistant) -> None:
        """Enable loading custom components in all tests."""
        hass.data.pop(DATA_CUSTOM_COMPONENTS)

    @pytest.fixture(autouse=True)
    async def setup_ha(hass: HomeAssistant) -> None:
        """Set up Home Assistant core component (needed for conversation dep)."""
        assert await async_setup_component(hass, "homeassistant", {})

except ImportError:
    # HA not installed (Python 3.12 pure-unit-test mode)
    pass


def make_chat_response(
    content: str = "Hello!",
    model: str = "auto",
    tool_calls: list[ToolCall] | None = None,
) -> ChatResponse:
    """Build a non-streaming ChatResponse."""
    message = Message(role="assistant", content=content, tool_calls=tool_calls)
    return ChatResponse(
        id="chatcmpl-test123",
        model=model,
        choices=[
            ChatChoice(index=0, message=message, finish_reason="stop"),
        ],
        usage=Usage(prompt_tokens=10, completion_tokens=5, total_tokens=15),
    )


def make_stream_chunks(
    text_parts: list[str] | None = None,
    tool_calls: list[dict[str, Any]] | None = None,
) -> list[ChatChunk]:
    """Build a list of streaming ChatChunk objects."""
    chunks: list[ChatChunk] = []

    # Role chunk
    chunks.append(
        ChatChunk(
            id="chatcmpl-test123",
            model="auto",
            choices=[
                ChunkChoice(
                    index=0,
                    delta=ChunkDelta(role="assistant"),
                )
            ],
        )
    )

    # Text chunks
    if text_parts:
        for part in text_parts:
            chunks.append(
                ChatChunk(
                    id="chatcmpl-test123",
                    model="auto",
                    choices=[
                        ChunkChoice(
                            index=0,
                            delta=ChunkDelta(content=part),
                        )
                    ],
                )
            )

    # Tool call chunks
    if tool_calls:
        for tc in tool_calls:
            chunks.append(
                ChatChunk(
                    id="chatcmpl-test123",
                    model="auto",
                    choices=[
                        ChunkChoice(
                            index=0,
                            delta=ChunkDelta(
                                tool_calls=[
                                    ToolCallDelta(
                                        index=tc.get("index", 0),
                                        id=tc["id"],
                                        type="function",
                                        function=FunctionCall(
                                            name=tc["name"],
                                            arguments=tc["arguments"],
                                        ),
                                    )
                                ]
                            ),
                        )
                    ],
                )
            )

    # Finish chunk
    finish_reason = "tool_calls" if tool_calls else "stop"
    chunks.append(
        ChatChunk(
            id="chatcmpl-test123",
            model="auto",
            choices=[
                ChunkChoice(
                    index=0,
                    delta=ChunkDelta(),
                    finish_reason=finish_reason,
                )
            ],
        )
    )

    # Usage-only chunk (no choices)
    chunks.append(
        ChatChunk(
            id="chatcmpl-test123",
            model="auto",
            choices=[],
            usage=Usage(prompt_tokens=10, completion_tokens=5, total_tokens=15),
        )
    )

    return chunks
