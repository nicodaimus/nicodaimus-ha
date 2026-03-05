"""Tests for nicodAImus account status sensors."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp
import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_API_KEY
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import UpdateFailed
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.nicodaimus.const import (
    CONF_BASE_URL,
    DEFAULT_BASE_URL,
    DOMAIN,
)
from custom_components.nicodaimus.coordinator import (
    NicodaimusAccountData,
    NicodaimusStatusCoordinator,
    _account_api_base,
    _mask_account,
)

MOCK_STATUS_RESPONSE = {
    "account": "7109777474669175",
    "tier": "pro",
    "tierName": "nicodAImus Pro",
    "limits": {
        "searchesPerDay": 50,
        "searchesPerMonth": 1500,
    },
    "subscription": {
        "status": "active",
    },
}

MOCK_USAGE_RESPONSE = {
    "search": {
        "day": "2026-03-05",
        "dayCount": 12,
        "dayLimit": 50,
        "month": "2026-03",
        "monthCount": 87,
        "monthLimit": 1500,
    },
    "twitter": {
        "day": "2026-03-05",
        "dayCount": 0,
        "dayLimit": 0,
        "month": "2026-03",
        "monthCount": 0,
        "monthLimit": 0,
    },
}

MOCK_ACCOUNT_DATA = NicodaimusAccountData(
    tier="pro",
    tier_name="nicodAImus Pro",
    subscription_status="active",
    masked_account="****9175",
    search_day_count=12,
    search_day_limit=50,
    search_month_count=87,
    search_month_limit=1500,
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


# --- Unit tests for helper functions ---


def test_mask_account_normal() -> None:
    """Test masking a 16-digit account number."""
    assert _mask_account("7109777474669175") == "****9175"


def test_mask_account_short() -> None:
    """Test masking a short account number."""
    assert _mask_account("12") == "****"


def test_mask_account_empty() -> None:
    """Test masking an empty string."""
    assert _mask_account("") == "****"


def test_mask_account_exactly_four() -> None:
    """Test masking exactly 4 digits."""
    assert _mask_account("1234") == "****1234"


def test_account_api_base_strips_v1() -> None:
    """Test that /v1 suffix is stripped."""
    assert (
        _account_api_base("https://chat.nicodaimus.com/v1")
        == "https://chat.nicodaimus.com"
    )


def test_account_api_base_strips_v1_trailing_slash() -> None:
    """Test that /v1/ suffix is stripped."""
    assert (
        _account_api_base("https://chat.nicodaimus.com/v1/")
        == "https://chat.nicodaimus.com"
    )


def test_account_api_base_no_v1() -> None:
    """Test that base URL without /v1 is returned unchanged."""
    assert (
        _account_api_base("https://chat.nicodaimus.com")
        == "https://chat.nicodaimus.com"
    )


# --- Coordinator data parsing tests ---


class MockResponse:
    """Mock aiohttp response (async context manager)."""

    def __init__(self, status: int, json_data: dict | None = None) -> None:
        """Initialize mock response."""
        self.status = status
        self._json_data = json_data or {}

    async def json(self) -> dict:
        """Return mock JSON data."""
        return self._json_data

    async def __aenter__(self):
        """Enter context manager."""
        return self

    async def __aexit__(self, *args):
        """Exit context manager."""


def _mock_session(*responses: MockResponse) -> MagicMock:
    """Create a mock aiohttp session that returns responses in order.

    aiohttp session.get() returns an async context manager directly
    (not a coroutine), so we use MagicMock with side_effect.
    """
    session = MagicMock()
    session.get = MagicMock(side_effect=list(responses))
    return session


async def test_coordinator_parses_data(hass: HomeAssistant) -> None:
    """Test that coordinator correctly parses status + usage responses."""
    session = _mock_session(
        MockResponse(200, MOCK_STATUS_RESPONSE),
        MockResponse(200, MOCK_USAGE_RESPONSE),
    )

    coordinator = NicodaimusStatusCoordinator(
        hass,
        session=session,
        api_key="7109777474669175",
        base_url="https://chat.nicodaimus.com/v1",
    )

    data = await coordinator._async_update_data()

    assert data.tier == "pro"
    assert data.tier_name == "nicodAImus Pro"
    assert data.subscription_status == "active"
    assert data.masked_account == "****9175"
    assert data.search_day_count == 12
    assert data.search_day_limit == 50
    assert data.search_month_count == 87
    assert data.search_month_limit == 1500


async def test_coordinator_unknown_tier(hass: HomeAssistant) -> None:
    """Test coordinator handles unknown tier gracefully."""
    status = {
        "account": "0000000000001234",
        "tier": "unknown",
        "tierName": "Unknown",
        "subscription": {"status": "none"},
    }
    usage = {
        "search": {
            "dayCount": 0,
            "dayLimit": 0,
            "monthCount": 0,
            "monthLimit": 0,
        },
    }

    session = _mock_session(
        MockResponse(200, status),
        MockResponse(200, usage),
    )

    coordinator = NicodaimusStatusCoordinator(
        hass,
        session=session,
        api_key="0000000000001234",
        base_url="https://chat.nicodaimus.com/v1",
    )

    data = await coordinator._async_update_data()

    assert data.tier == "unknown"
    assert data.tier_name == "Unknown"
    assert data.subscription_status == "none"
    assert data.masked_account == "****1234"


async def test_coordinator_auth_error(hass: HomeAssistant) -> None:
    """Test coordinator raises ConfigEntryAuthFailed on 401."""
    from homeassistant.exceptions import ConfigEntryAuthFailed

    session = _mock_session(MockResponse(401))

    coordinator = NicodaimusStatusCoordinator(
        hass,
        session=session,
        api_key="bad-key",
        base_url="https://chat.nicodaimus.com/v1",
    )

    with pytest.raises(ConfigEntryAuthFailed):
        await coordinator._async_update_data()


async def test_coordinator_rate_limited(hass: HomeAssistant) -> None:
    """Test coordinator raises UpdateFailed on 429."""
    session = _mock_session(MockResponse(429))

    coordinator = NicodaimusStatusCoordinator(
        hass,
        session=session,
        api_key="test-key",
        base_url="https://chat.nicodaimus.com/v1",
    )

    with pytest.raises(UpdateFailed, match="Rate limited"):
        await coordinator._async_update_data()


async def test_coordinator_connection_error(
    hass: HomeAssistant,
) -> None:
    """Test coordinator raises UpdateFailed on connection error."""
    session = MagicMock()
    session.get = MagicMock(
        side_effect=aiohttp.ClientError("Connection refused"),
    )

    coordinator = NicodaimusStatusCoordinator(
        hass,
        session=session,
        api_key="test-key",
        base_url="https://chat.nicodaimus.com/v1",
    )

    with pytest.raises(UpdateFailed, match="Could not connect"):
        await coordinator._async_update_data()


async def test_coordinator_server_error(hass: HomeAssistant) -> None:
    """Test coordinator raises UpdateFailed on 500."""
    session = _mock_session(MockResponse(500))

    coordinator = NicodaimusStatusCoordinator(
        hass,
        session=session,
        api_key="test-key",
        base_url="https://chat.nicodaimus.com/v1",
    )

    with pytest.raises(UpdateFailed, match="HTTP 500"):
        await coordinator._async_update_data()


async def test_coordinator_usage_auth_error(
    hass: HomeAssistant,
) -> None:
    """Test ConfigEntryAuthFailed when usage endpoint returns 401."""
    from homeassistant.exceptions import ConfigEntryAuthFailed

    session = _mock_session(
        MockResponse(200, MOCK_STATUS_RESPONSE),
        MockResponse(401),
    )

    coordinator = NicodaimusStatusCoordinator(
        hass,
        session=session,
        api_key="bad-key",
        base_url="https://chat.nicodaimus.com/v1",
    )

    with pytest.raises(ConfigEntryAuthFailed):
        await coordinator._async_update_data()


# --- Integration tests: sensor entity values ---


async def test_sensor_entities_created(hass: HomeAssistant) -> None:
    """Test that all 4 sensor entities are created on setup."""
    entry = _make_entry(hass)

    with (
        patch(
            "custom_components.nicodaimus.NicodaimusClient",
        ) as mock_cls,
        patch(
            "custom_components.nicodaimus.NicodaimusStatusCoordinator._async_update_data",
            return_value=MOCK_ACCOUNT_DATA,
        ),
    ):
        client = mock_cls.return_value
        client.validate_connection = AsyncMock(return_value=True)

        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.LOADED

    # Check all 4 sensors exist
    tier_state = hass.states.get("sensor.nicodaimus_account_account_tier")
    sub_state = hass.states.get("sensor.nicodaimus_account_subscription_status")
    day_state = hass.states.get("sensor.nicodaimus_account_searches_today")
    month_state = hass.states.get("sensor.nicodaimus_account_searches_this_month")

    assert tier_state is not None
    assert tier_state.state == "nicodAImus Pro"

    assert sub_state is not None
    assert sub_state.state == "active"

    assert day_state is not None
    assert day_state.state == "12"

    assert month_state is not None
    assert month_state.state == "87"
