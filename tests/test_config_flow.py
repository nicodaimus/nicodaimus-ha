"""Tests for the nicodAImus config flow."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from homeassistant import config_entries
from homeassistant.const import CONF_API_KEY
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from nicodaimus import NicodaimusAuthError, NicodaimusConnectionError

from custom_components.nicodaimus.const import (
    CONF_BASE_URL,
    DEFAULT_BASE_URL,
    DOMAIN,
)


@pytest.fixture
def mock_setup_entry() -> AsyncMock:
    """Mock async_setup_entry."""
    with patch(
        "custom_components.nicodaimus.async_setup_entry",
        return_value=True,
    ) as mock:
        yield mock


# -- User step tests --


async def test_user_step_success(
    hass: HomeAssistant, mock_setup_entry: AsyncMock
) -> None:
    """Test the happy path: valid API key creates an entry."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"

    with patch(
        "custom_components.nicodaimus.config_flow.validate_input",
        new_callable=AsyncMock,
    ):
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_API_KEY: "sk-test-key-123456",
                CONF_BASE_URL: DEFAULT_BASE_URL,
            },
        )

    assert result2["type"] is FlowResultType.CREATE_ENTRY
    assert result2["title"] == "nicodAImus"
    assert result2["data"][CONF_API_KEY] == "sk-test-key-123456"
    assert result2["data"][CONF_BASE_URL] == DEFAULT_BASE_URL
    # Should create a default conversation subentry
    assert len(result2["subentries"]) == 1
    assert result2["subentries"][0]["subentry_type"] == "conversation"
    assert len(mock_setup_entry.mock_calls) == 1


async def test_user_step_invalid_auth(hass: HomeAssistant) -> None:
    """Test that invalid API key shows auth error."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    with patch(
        "custom_components.nicodaimus.config_flow.validate_input",
        new_callable=AsyncMock,
        side_effect=NicodaimusAuthError("Invalid API key"),
    ):
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_API_KEY: "sk-invalid",
                CONF_BASE_URL: DEFAULT_BASE_URL,
            },
        )

    assert result2["type"] is FlowResultType.FORM
    assert result2["errors"] == {"base": "invalid_auth"}


async def test_user_step_cannot_connect(hass: HomeAssistant) -> None:
    """Test that connection error shows cannot_connect."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    with patch(
        "custom_components.nicodaimus.config_flow.validate_input",
        new_callable=AsyncMock,
        side_effect=NicodaimusConnectionError("Connection refused"),
    ):
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_API_KEY: "sk-test",
                CONF_BASE_URL: DEFAULT_BASE_URL,
            },
        )

    assert result2["type"] is FlowResultType.FORM
    assert result2["errors"] == {"base": "cannot_connect"}


async def test_user_step_unknown_error(hass: HomeAssistant) -> None:
    """Test that unexpected errors show unknown."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    with patch(
        "custom_components.nicodaimus.config_flow.validate_input",
        new_callable=AsyncMock,
        side_effect=RuntimeError("Something broke"),
    ):
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_API_KEY: "sk-test",
                CONF_BASE_URL: DEFAULT_BASE_URL,
            },
        )

    assert result2["type"] is FlowResultType.FORM
    assert result2["errors"] == {"base": "unknown"}


async def test_user_step_duplicate_entry(
    hass: HomeAssistant, mock_setup_entry: AsyncMock
) -> None:
    """Test that duplicate API key aborts."""
    # Create first entry
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    with patch(
        "custom_components.nicodaimus.config_flow.validate_input",
        new_callable=AsyncMock,
    ):
        await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_API_KEY: "sk-test-key-123456",
                CONF_BASE_URL: DEFAULT_BASE_URL,
            },
        )

    # Try to create second entry with same key
    result2 = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    with patch(
        "custom_components.nicodaimus.config_flow.validate_input",
        new_callable=AsyncMock,
    ):
        result3 = await hass.config_entries.flow.async_configure(
            result2["flow_id"],
            {
                CONF_API_KEY: "sk-test-key-123456",
                CONF_BASE_URL: DEFAULT_BASE_URL,
            },
        )

    assert result3["type"] is FlowResultType.ABORT
    assert result3["reason"] == "already_configured"


async def test_user_step_retry_after_error(
    hass: HomeAssistant, mock_setup_entry: AsyncMock
) -> None:
    """Test that user can retry after an error and succeed."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    # First attempt fails
    with patch(
        "custom_components.nicodaimus.config_flow.validate_input",
        new_callable=AsyncMock,
        side_effect=NicodaimusConnectionError("timeout"),
    ):
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_API_KEY: "sk-test",
                CONF_BASE_URL: DEFAULT_BASE_URL,
            },
        )
    assert result2["type"] is FlowResultType.FORM
    assert result2["errors"] == {"base": "cannot_connect"}

    # Second attempt succeeds
    with patch(
        "custom_components.nicodaimus.config_flow.validate_input",
        new_callable=AsyncMock,
    ):
        result3 = await hass.config_entries.flow.async_configure(
            result2["flow_id"],
            {
                CONF_API_KEY: "sk-test",
                CONF_BASE_URL: DEFAULT_BASE_URL,
            },
        )

    assert result3["type"] is FlowResultType.CREATE_ENTRY
