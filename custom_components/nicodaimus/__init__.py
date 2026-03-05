"""The nicodAImus integration."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_API_KEY, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from nicodaimus import NicodaimusAuthError, NicodaimusClient, NicodaimusConnectionError

from .const import CONF_BASE_URL, DEFAULT_BASE_URL, DOMAIN, LOGGER

PLATFORMS = (Platform.CONVERSATION,)
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

type NicodaimusConfigEntry = ConfigEntry[NicodaimusClient]


async def async_setup_entry(
    hass: HomeAssistant, entry: NicodaimusConfigEntry
) -> bool:
    """Set up nicodAImus from a config entry."""
    session = async_get_clientsession(hass)
    client = NicodaimusClient(
        api_key=entry.data[CONF_API_KEY],
        session=session,
        base_url=entry.data.get(CONF_BASE_URL, DEFAULT_BASE_URL),
    )

    try:
        await client.validate_connection()
    except NicodaimusAuthError as err:
        raise ConfigEntryAuthFailed(err) from err
    except NicodaimusConnectionError as err:
        raise ConfigEntryNotReady(err) from err

    entry.runtime_data = client

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    entry.async_on_unload(entry.add_update_listener(async_update_options))

    return True


async def async_unload_entry(
    hass: HomeAssistant, entry: NicodaimusConfigEntry
) -> bool:
    """Unload nicodAImus."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_update_options(
    hass: HomeAssistant, entry: NicodaimusConfigEntry
) -> None:
    """Update options."""
    await hass.config_entries.async_reload(entry.entry_id)
