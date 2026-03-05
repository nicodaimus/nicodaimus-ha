"""Base entity for nicodAImus."""

from __future__ import annotations

import json
from collections.abc import AsyncGenerator, Callable
from typing import Any

from homeassistant.components import conversation
from homeassistant.config_entries import ConfigSubentry
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import llm
from homeassistant.helpers.entity import Entity
from nicodaimus import (
    NicodaimusAuthError,
    NicodaimusClient,
    NicodaimusConnectionError,
    NicodaimusError,
)
from voluptuous_openapi import convert

from . import NicodaimusConfigEntry
from .const import (
    CONF_CHAT_MODEL,
    CONF_MAX_TOKENS,
    CONF_TEMPERATURE,
    DEFAULT_MODEL,
    DOMAIN,
    LOGGER,
    MAX_TOOL_ITERATIONS,
    RECOMMENDED_MAX_TOKENS,
    RECOMMENDED_TEMPERATURE,
)


def _format_tool(
    tool: llm.Tool, custom_serializer: Callable[[Any], Any] | None
) -> dict[str, Any]:
    """Format tool specification in OpenAI function-calling format."""
    return {
        "type": "function",
        "function": {
            "name": tool.name,
            "description": tool.description or "",
            "parameters": convert(tool.parameters, custom_serializer=custom_serializer),
        },
    }


def _convert_content_to_messages(
    chat_content: list[conversation.Content],
) -> list[dict[str, Any]]:
    """Convert HA chat_log content into OpenAI-compatible message format."""
    messages: list[dict[str, Any]] = []

    for content in chat_content:
        if isinstance(content, conversation.SystemContent):
            messages.append({"role": "system", "content": content.content})
        elif isinstance(content, conversation.UserContent):
            messages.append({"role": "user", "content": content.content})
        elif isinstance(content, conversation.AssistantContent):
            msg: dict[str, Any] = {"role": "assistant"}
            if content.content:
                msg["content"] = content.content
            if content.tool_calls:
                msg["tool_calls"] = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.tool_name,
                            "arguments": json.dumps(tc.tool_args),
                        },
                    }
                    for tc in content.tool_calls
                ]
            messages.append(msg)
        elif isinstance(content, conversation.ToolResultContent):
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": content.tool_call_id,
                    "content": json.dumps(content.tool_result),
                }
            )

    return messages


async def _transform_stream(
    chat_log: conversation.ChatLog,
    client: NicodaimusClient,
    messages: list[dict[str, Any]],
    model: str,
    tools: list[dict[str, Any]] | None,
    max_tokens: int,
    temperature: float,
) -> AsyncGenerator[conversation.AssistantContentDeltaDict]:
    """Transform the streaming response into HA format.

    Yields AssistantContentDeltaDict dicts as they arrive from the API.
    Accumulates tool call deltas and yields complete tool calls at the end.
    """
    yield {"role": "assistant"}

    # Accumulate tool calls: {index: {id, name, arguments}}
    tool_call_map: dict[int, dict[str, str]] = {}
    input_tokens = 0
    output_tokens = 0

    async for chunk in client.chat_completion_stream(
        messages=messages,
        model=model,
        tools=tools,
        max_tokens=max_tokens,
        temperature=temperature,
    ):
        if not chunk.choices:
            # Usage-only chunk at end of stream
            if chunk.usage:
                input_tokens = chunk.usage.prompt_tokens
                output_tokens = chunk.usage.completion_tokens
            continue

        delta = chunk.choices[0].delta

        # Text content
        if delta.content:
            yield {"content": delta.content}

        # Tool call deltas (arrive in pieces)
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
                        tool_call_map[idx]["arguments"] += tc_delta.function.arguments

    # Yield accumulated tool calls
    if tool_call_map:
        tool_inputs = []
        for _idx in sorted(tool_call_map):
            tc = tool_call_map[_idx]
            try:
                tool_args = json.loads(tc["arguments"]) if tc["arguments"] else {}
            except json.JSONDecodeError:
                LOGGER.warning("Failed to parse tool arguments: %s", tc["arguments"])
                tool_args = {}
            tool_inputs.append(
                llm.ToolInput(
                    id=tc["id"],
                    tool_name=tc["name"],
                    tool_args=tool_args,
                )
            )
        yield {"tool_calls": tool_inputs}

    # Record token usage
    if input_tokens or output_tokens:
        chat_log.async_trace(
            {
                "stats": {
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                }
            }
        )


class NicodaimusBaseLLMEntity(Entity):
    """nicodAImus base LLM entity."""

    _attr_has_entity_name = True
    _attr_name = None

    def __init__(self, entry: NicodaimusConfigEntry, subentry: ConfigSubentry) -> None:
        """Initialize the entity."""
        self.entry = entry
        self.subentry = subentry
        self._attr_unique_id = subentry.subentry_id
        self._attr_device_info = dr.DeviceInfo(
            identifiers={(DOMAIN, subentry.subentry_id)},
            name=subentry.title,
            manufacturer="nicodAImus",
            model=subentry.data.get(CONF_CHAT_MODEL, DEFAULT_MODEL),
            entry_type=dr.DeviceEntryType.SERVICE,
        )

    async def _async_handle_chat_log(
        self,
        chat_log: conversation.ChatLog,
    ) -> None:
        """Generate an answer for the chat log."""
        options = self.subentry.data
        client = self.entry.runtime_data.client

        model = options.get(CONF_CHAT_MODEL, DEFAULT_MODEL)
        max_tokens = options.get(CONF_MAX_TOKENS, RECOMMENDED_MAX_TOKENS)
        temperature = options.get(CONF_TEMPERATURE, RECOMMENDED_TEMPERATURE)

        # Convert HA tools to OpenAI function-calling format
        tools: list[dict[str, Any]] | None = None
        if chat_log.llm_api:
            tools = [
                _format_tool(tool, chat_log.llm_api.custom_serializer)
                for tool in chat_log.llm_api.tools
            ]

        messages = _convert_content_to_messages(chat_log.content)

        for _iteration in range(MAX_TOOL_ITERATIONS):
            try:
                stream_gen = _transform_stream(
                    chat_log,
                    client,
                    messages,
                    model=model,
                    tools=tools,
                    max_tokens=max_tokens,
                    temperature=temperature,
                )

                new_content = [
                    content
                    async for content in chat_log.async_add_delta_content_stream(
                        self.entity_id,
                        stream_gen,
                    )
                ]

                # Rebuild messages with new content for next iteration
                messages.extend(_convert_content_to_messages(new_content))
            except NicodaimusAuthError as err:
                self.entry.async_start_reauth(self.hass)
                raise HomeAssistantError(
                    "Authentication error with nicodAImus API, "
                    "reauthentication required"
                ) from err
            except NicodaimusConnectionError as err:
                raise HomeAssistantError(
                    f"Could not connect to nicodAImus API: {err}"
                ) from err
            except NicodaimusError as err:
                raise HomeAssistantError(
                    f"Error communicating with nicodAImus API: {err}"
                ) from err

            if not chat_log.unresponded_tool_results:
                break
