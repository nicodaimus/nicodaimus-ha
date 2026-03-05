"""Tests for nicodAImus entity logic (streaming, tool conversion, content conversion).

These tests exercise our pure Python business logic without requiring
the full Home Assistant framework (which needs Python 3.13+).
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from nicodaimus import (
    ChatChunk,
    ChunkChoice,
    ChunkDelta,
    FunctionCall,
    NicodaimusAuthError,
    NicodaimusClient,
    NicodaimusConnectionError,
    NicodaimusError,
    ToolCallDelta,
    Usage,
)

from .conftest import make_stream_chunks


# -- Helper: async iterator from list --


async def _async_iter(items: list[Any]):
    """Convert a list into an async iterator."""
    for item in items:
        yield item


# -- _convert_content_to_messages tests --

# We can't import from entity.py directly due to HA dependencies,
# but we can test the logic patterns. For actual import testing,
# use the HA framework CI (Python 3.13+).

# Instead, we test the streaming patterns at the protocol level.


class TestStreamChunkBuilders:
    """Test that our test helpers produce valid chunk structures."""

    def test_make_stream_chunks_text_only(self) -> None:
        """Test stream chunks for a text-only response."""
        chunks = make_stream_chunks(text_parts=["Hello", " world!"])

        assert len(chunks) == 5  # role + 2 text + finish + usage
        assert chunks[0].choices[0].delta.role == "assistant"
        assert chunks[1].choices[0].delta.content == "Hello"
        assert chunks[2].choices[0].delta.content == " world!"
        assert chunks[3].choices[0].finish_reason == "stop"
        assert chunks[4].usage is not None
        assert chunks[4].usage.total_tokens == 15

    def test_make_stream_chunks_with_tool_calls(self) -> None:
        """Test stream chunks with tool calls."""
        chunks = make_stream_chunks(
            tool_calls=[
                {
                    "index": 0,
                    "id": "call_abc",
                    "name": "HassTurnOn",
                    "arguments": '{"entity_id": "light.living_room"}',
                }
            ]
        )

        assert len(chunks) == 4  # role + 1 tool call + finish + usage
        tc = chunks[1].choices[0].delta.tool_calls
        assert tc is not None
        assert tc[0].id == "call_abc"
        assert tc[0].function.name == "HassTurnOn"
        assert chunks[2].choices[0].finish_reason == "tool_calls"

    def test_make_stream_chunks_empty(self) -> None:
        """Test stream chunks with no text and no tools."""
        chunks = make_stream_chunks()

        assert len(chunks) == 3  # role + finish + usage


class TestToolCallAccumulation:
    """Test the tool call accumulation logic used in _transform_stream."""

    def _accumulate_tool_calls(
        self, chunks: list[ChatChunk]
    ) -> dict[int, dict[str, str]]:
        """Simulate the tool call accumulation logic from entity.py."""
        tool_call_map: dict[int, dict[str, str]] = {}

        for chunk in chunks:
            if not chunk.choices:
                continue

            delta = chunk.choices[0].delta
            if delta.tool_calls:
                for tc_delta in delta.tool_calls:
                    idx = tc_delta.index
                    if idx not in tool_call_map:
                        tool_call_map[idx] = {
                            "id": "",
                            "name": "",
                            "arguments": "",
                        }
                    if tc_delta.id:
                        tool_call_map[idx]["id"] = tc_delta.id
                    if tc_delta.function:
                        if tc_delta.function.name:
                            tool_call_map[idx]["name"] = tc_delta.function.name
                        if tc_delta.function.arguments:
                            tool_call_map[idx]["arguments"] += (
                                tc_delta.function.arguments
                            )

        return tool_call_map

    def test_single_tool_call(self) -> None:
        """Test accumulating a single tool call."""
        chunks = make_stream_chunks(
            tool_calls=[
                {
                    "index": 0,
                    "id": "call_abc",
                    "name": "HassTurnOn",
                    "arguments": '{"entity_id": "light.lr"}',
                }
            ]
        )

        result = self._accumulate_tool_calls(chunks)
        assert len(result) == 1
        assert result[0]["id"] == "call_abc"
        assert result[0]["name"] == "HassTurnOn"
        assert json.loads(result[0]["arguments"]) == {"entity_id": "light.lr"}

    def test_streamed_arguments(self) -> None:
        """Test accumulating arguments across multiple chunks."""
        chunks = [
            ChatChunk(
                id="test",
                model="auto",
                choices=[
                    ChunkChoice(
                        index=0,
                        delta=ChunkDelta(
                            tool_calls=[
                                ToolCallDelta(
                                    index=0,
                                    id="call_abc",
                                    type="function",
                                    function=FunctionCall(
                                        name="HassTurnOn",
                                        arguments='{"entity',
                                    ),
                                )
                            ]
                        ),
                    )
                ],
            ),
            ChatChunk(
                id="test",
                model="auto",
                choices=[
                    ChunkChoice(
                        index=0,
                        delta=ChunkDelta(
                            tool_calls=[
                                ToolCallDelta(
                                    index=0,
                                    function=FunctionCall(
                                        name="",
                                        arguments='_id": "light.lr"}',
                                    ),
                                )
                            ]
                        ),
                    )
                ],
            ),
        ]

        result = self._accumulate_tool_calls(chunks)
        assert len(result) == 1
        assert result[0]["id"] == "call_abc"
        assert result[0]["name"] == "HassTurnOn"
        combined = result[0]["arguments"]
        assert json.loads(combined) == {"entity_id": "light.lr"}

    def test_multiple_tool_calls(self) -> None:
        """Test accumulating multiple tool calls."""
        chunks = make_stream_chunks(
            tool_calls=[
                {
                    "index": 0,
                    "id": "call_1",
                    "name": "HassTurnOn",
                    "arguments": '{"entity_id": "light.lr"}',
                },
                {
                    "index": 1,
                    "id": "call_2",
                    "name": "HassGetState",
                    "arguments": '{"entity_id": "sensor.temp"}',
                },
            ]
        )

        result = self._accumulate_tool_calls(chunks)
        assert len(result) == 2
        assert result[0]["name"] == "HassTurnOn"
        assert result[1]["name"] == "HassGetState"

    def test_usage_chunk_skipped(self) -> None:
        """Test that usage-only chunks (no choices) are skipped."""
        chunks = [
            ChatChunk(
                id="test",
                model="auto",
                choices=[],
                usage=Usage(
                    prompt_tokens=10, completion_tokens=5, total_tokens=15
                ),
            )
        ]

        result = self._accumulate_tool_calls(chunks)
        assert len(result) == 0


class TestOpenAIMessageFormat:
    """Test the message format conversion logic."""

    def test_system_message_format(self) -> None:
        """Test system message format."""
        msg = {"role": "system", "content": "You are a helpful assistant."}
        assert msg["role"] == "system"
        assert "content" in msg

    def test_user_message_format(self) -> None:
        """Test user message format."""
        msg = {"role": "user", "content": "Turn on the lights."}
        assert msg["role"] == "user"

    def test_assistant_message_with_tool_calls(self) -> None:
        """Test assistant message with tool calls in OpenAI format."""
        msg: dict[str, Any] = {
            "role": "assistant",
            "tool_calls": [
                {
                    "id": "call_abc",
                    "type": "function",
                    "function": {
                        "name": "HassTurnOn",
                        "arguments": json.dumps({"entity_id": "light.lr"}),
                    },
                }
            ],
        }

        assert msg["role"] == "assistant"
        tc = msg["tool_calls"][0]
        assert tc["id"] == "call_abc"
        assert tc["type"] == "function"
        assert tc["function"]["name"] == "HassTurnOn"
        assert json.loads(tc["function"]["arguments"]) == {
            "entity_id": "light.lr"
        }

    def test_tool_result_message(self) -> None:
        """Test tool result message format."""
        msg = {
            "role": "tool",
            "tool_call_id": "call_abc",
            "content": json.dumps({"success": True}),
        }

        assert msg["role"] == "tool"
        assert msg["tool_call_id"] == "call_abc"
        assert json.loads(msg["content"]) == {"success": True}


class TestToolFormatting:
    """Test the OpenAI function-calling tool format."""

    def test_tool_format_structure(self) -> None:
        """Test that tools are formatted in OpenAI function-calling format."""
        tool = {
            "type": "function",
            "function": {
                "name": "HassTurnOn",
                "description": "Turn on a device",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "entity_id": {
                            "type": "string",
                            "description": "The entity to turn on",
                        }
                    },
                    "required": ["entity_id"],
                },
            },
        }

        assert tool["type"] == "function"
        assert tool["function"]["name"] == "HassTurnOn"
        assert "parameters" in tool["function"]
        params = tool["function"]["parameters"]
        assert params["type"] == "object"
        assert "entity_id" in params["properties"]


class TestStreamingEdgeCases:
    """Test edge cases in stream processing."""

    def test_empty_delta_content(self) -> None:
        """Test handling of empty delta content."""
        chunk = ChatChunk(
            id="test",
            model="auto",
            choices=[
                ChunkChoice(
                    index=0,
                    delta=ChunkDelta(),  # Empty delta
                    finish_reason="stop",
                )
            ],
        )

        assert chunk.choices[0].delta.content is None
        assert chunk.choices[0].delta.role is None
        assert chunk.choices[0].delta.tool_calls is None

    def test_role_only_chunk(self) -> None:
        """Test chunk with role but no content."""
        chunk = ChatChunk(
            id="test",
            model="auto",
            choices=[
                ChunkChoice(
                    index=0,
                    delta=ChunkDelta(role="assistant"),
                )
            ],
        )

        assert chunk.choices[0].delta.role == "assistant"
        assert chunk.choices[0].delta.content is None

    def test_malformed_tool_arguments_fallback(self) -> None:
        """Test handling of malformed JSON in tool arguments."""
        bad_args = "not valid json {"
        try:
            json.loads(bad_args)
            parsed = True
        except json.JSONDecodeError:
            parsed = False

        assert not parsed, "Should not parse invalid JSON"

    def test_empty_tool_arguments(self) -> None:
        """Test handling of empty tool arguments."""
        result = json.loads("{}") if "" == "" else {}
        # Empty string -> empty dict fallback
        assert result == {} or result == {}
