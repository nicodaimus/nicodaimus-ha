"""Data update coordinator for nicodAImus account status."""

from __future__ import annotations

from dataclasses import dataclass

import aiohttp
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from nicodaimus import NicodaimusClient

from .const import ACCOUNT_API_PATH, DEFAULT_SCAN_INTERVAL, LOGGER


@dataclass
class NicodaimusAccountData:
    """Typed container for account status + usage data."""

    tier: str
    tier_name: str
    subscription_status: str
    masked_account: str
    search_day_count: int
    search_day_limit: int
    search_month_count: int
    search_month_limit: int


@dataclass
class NicodaimusRuntimeData:
    """Runtime data stored in config entry."""

    client: NicodaimusClient
    coordinator: NicodaimusStatusCoordinator


def _mask_account(account: str) -> str:
    """Mask account number to ****XXXX (last 4 digits)."""
    if len(account) >= 4:
        return f"****{account[-4:]}"
    return "****"


def _account_api_base(base_url: str) -> str:
    """Derive account API base URL by stripping /v1 suffix."""
    if base_url.endswith("/v1"):
        return base_url[:-3]
    if base_url.endswith("/v1/"):
        return base_url[:-4]
    return base_url


class NicodaimusStatusCoordinator(DataUpdateCoordinator[NicodaimusAccountData]):
    """Coordinator that polls account status and usage."""

    def __init__(
        self,
        hass: HomeAssistant,
        session: aiohttp.ClientSession,
        api_key: str,
        base_url: str,
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            LOGGER,
            name="nicodAImus account status",
            update_interval=DEFAULT_SCAN_INTERVAL,
        )
        self._session = session
        self._api_key = api_key
        self._base_url_root = _account_api_base(base_url)
        self._headers = {"Authorization": f"Bearer {api_key}"}

    async def _async_update_data(self) -> NicodaimusAccountData:
        """Fetch account status and usage from the API."""
        status_url = f"{self._base_url_root}{ACCOUNT_API_PATH}/status"
        usage_url = f"{self._base_url_root}{ACCOUNT_API_PATH}/usage"

        try:
            async with self._session.get(
                status_url, headers=self._headers
            ) as status_resp:
                if status_resp.status == 401:
                    raise ConfigEntryAuthFailed("Invalid API key")
                if status_resp.status == 429:
                    raise UpdateFailed("Rate limited by nicodAImus API")
                if status_resp.status != 200:
                    raise UpdateFailed(f"Status API returned HTTP {status_resp.status}")
                status_data = await status_resp.json()

            async with self._session.get(
                usage_url, headers=self._headers
            ) as usage_resp:
                if usage_resp.status == 401:
                    raise ConfigEntryAuthFailed("Invalid API key")
                if usage_resp.status == 429:
                    raise UpdateFailed("Rate limited by nicodAImus API")
                if usage_resp.status != 200:
                    raise UpdateFailed(f"Usage API returned HTTP {usage_resp.status}")
                usage_data = await usage_resp.json()

        except (aiohttp.ClientError, TimeoutError) as err:
            raise UpdateFailed(f"Could not connect to nicodAImus API: {err}") from err

        # Extract whitelisted fields only
        account_raw = status_data.get("account", "")
        search = usage_data.get("search", {})

        subscription = status_data.get("subscription", {})
        if isinstance(subscription, dict):
            sub_status = subscription.get("status", "none")
        else:
            sub_status = "none"

        return NicodaimusAccountData(
            tier=status_data.get("tier", "unknown"),
            tier_name=status_data.get("tierName", "Unknown"),
            subscription_status=sub_status,
            masked_account=_mask_account(account_raw),
            search_day_count=search.get("dayCount", 0),
            search_day_limit=search.get("dayLimit", 0),
            search_month_count=search.get("monthCount", 0),
            search_month_limit=search.get("monthLimit", 0),
        )
