"""Tests for nicodAImus integration setup."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_API_KEY
from homeassistant.core import HomeAssistant
from nicodaimus import NicodaimusAuthError, NicodaimusConnectionError
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.nicodaimus.const import (
    CONF_BASE_URL,
    DEFAULT_BASE_URL,
    DOMAIN,
)


def _make_entry(hass: HomeAssistant) -> MockConfigEntry:
    """Build and add a mock config entry."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="nicodAImus",
        data={
            CONF_API_KEY: "sk-test-key-123456",
            CONF_BASE_URL: DEFAULT_BASE_URL,
        },
    )
    entry.add_to_hass(hass)
    return entry


async def test_setup_entry_success(hass: HomeAssistant) -> None:
    """Test that setup_entry creates client and forwards platforms."""
    entry = _make_entry(hass)

    with patch(
        "custom_components.nicodaimus.NicodaimusClient",
    ) as mock_cls:
        client = mock_cls.return_value
        client.validate_connection = AsyncMock(return_value=True)

        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.LOADED
    assert mock_cls.call_count == 1


async def test_setup_auth_error(hass: HomeAssistant) -> None:
    """Test that auth error during setup marks entry as setup error."""
    entry = _make_entry(hass)

    with patch(
        "custom_components.nicodaimus.NicodaimusClient",
    ) as mock_cls:
        client = mock_cls.return_value
        client.validate_connection = AsyncMock(
            side_effect=NicodaimusAuthError("Invalid key")
        )

        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.SETUP_ERROR


async def test_setup_connection_error(hass: HomeAssistant) -> None:
    """Test that connection error during setup marks entry as not ready."""
    entry = _make_entry(hass)

    with patch(
        "custom_components.nicodaimus.NicodaimusClient",
    ) as mock_cls:
        client = mock_cls.return_value
        client.validate_connection = AsyncMock(
            side_effect=NicodaimusConnectionError("Cannot connect")
        )

        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.SETUP_RETRY


async def test_unload_entry(hass: HomeAssistant) -> None:
    """Test that unloading works cleanly."""
    entry = _make_entry(hass)

    with patch(
        "custom_components.nicodaimus.NicodaimusClient",
    ) as mock_cls:
        client = mock_cls.return_value
        client.validate_connection = AsyncMock(return_value=True)

        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.LOADED

    await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.NOT_LOADED
