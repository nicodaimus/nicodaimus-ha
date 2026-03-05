"""Config flow for the nicodAImus integration."""

from __future__ import annotations

from collections.abc import Mapping
import logging
from typing import TYPE_CHECKING, Any

import voluptuous as vol

from homeassistant.config_entries import (
    SOURCE_REAUTH,
    ConfigEntryState,
    ConfigFlow,
    ConfigFlowResult,
    ConfigSubentryFlow,
    SubentryFlowResult,
)
from homeassistant.const import CONF_API_KEY, CONF_LLM_HASS_API, CONF_NAME
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import llm
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    TemplateSelector,
)
from homeassistant.helpers.typing import VolDictType

from nicodaimus import NicodaimusAuthError, NicodaimusClient, NicodaimusConnectionError

from .const import (
    CONF_BASE_URL,
    CONF_CHAT_MODEL,
    CONF_MAX_TOKENS,
    CONF_PROMPT,
    CONF_RECOMMENDED,
    CONF_TEMPERATURE,
    DEFAULT_BASE_URL,
    DEFAULT_CONVERSATION_NAME,
    DEFAULT_MODEL,
    DOMAIN,
    RECOMMENDED_CONVERSATION_OPTIONS,
    RECOMMENDED_MAX_TOKENS,
    RECOMMENDED_TEMPERATURE,
)

if TYPE_CHECKING:
    from . import NicodaimusConfigEntry

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_API_KEY): str,
        vol.Optional(CONF_BASE_URL, default=DEFAULT_BASE_URL): str,
    }
)

STEP_REAUTH_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_API_KEY): str,
    }
)


async def validate_input(hass: HomeAssistant, data: dict[str, Any]) -> None:
    """Validate the user input allows us to connect."""
    session = async_get_clientsession(hass)
    client = NicodaimusClient(
        api_key=data[CONF_API_KEY],
        session=session,
        base_url=data.get(CONF_BASE_URL, DEFAULT_BASE_URL),
    )
    await client.validate_connection()


class NicodaimusConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for nicodAImus."""

    VERSION = 1
    MINOR_VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            self._async_abort_entries_match(
                {CONF_API_KEY: user_input[CONF_API_KEY]}
            )
            try:
                await validate_input(self.hass, user_input)
            except NicodaimusAuthError:
                errors["base"] = "invalid_auth"
            except NicodaimusConnectionError:
                errors["base"] = "cannot_connect"
            except Exception:
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"
            else:
                if self.source == SOURCE_REAUTH:
                    return self.async_update_reload_and_abort(
                        self._get_reauth_entry(), data_updates=user_input
                    )
                return self.async_create_entry(
                    title="nicodAImus",
                    data=user_input,
                    subentries=[
                        {
                            "subentry_type": "conversation",
                            "data": RECOMMENDED_CONVERSATION_OPTIONS,
                            "title": DEFAULT_CONVERSATION_NAME,
                            "unique_id": None,
                        },
                    ],
                )

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors or None,
            description_placeholders={
                "instructions_url": "https://nicodaimus.com/docs/home-assistant",
            },
        )

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        """Perform reauth upon an API authentication error."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Dialog that informs the user that reauth is required."""
        if not user_input:
            return self.async_show_form(
                step_id="reauth_confirm",
                data_schema=STEP_REAUTH_DATA_SCHEMA,
            )
        return await self.async_step_user(user_input)

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle reconfiguration of the integration."""
        errors: dict[str, str] = {}

        if user_input is not None:
            # Merge with existing data (keep API key, update base URL)
            new_data = {**self._get_reconfigure_entry().data, **user_input}
            try:
                await validate_input(self.hass, new_data)
            except NicodaimusAuthError:
                errors["base"] = "invalid_auth"
            except NicodaimusConnectionError:
                errors["base"] = "cannot_connect"
            except Exception:
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"
            else:
                return self.async_update_reload_and_abort(
                    self._get_reconfigure_entry(),
                    data_updates=user_input,
                )

        reconfigure_entry = self._get_reconfigure_entry()
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_BASE_URL,
                        default=reconfigure_entry.data.get(
                            CONF_BASE_URL, DEFAULT_BASE_URL
                        ),
                    ): str,
                }
            ),
            errors=errors or None,
        )

    @classmethod
    @callback
    def async_get_supported_subentry_types(
        cls, config_entry: NicodaimusConfigEntry
    ) -> dict[str, type[ConfigSubentryFlow]]:
        """Return subentries supported by this integration."""
        return {
            "conversation": NicodaimusSubentryFlowHandler,
        }


class NicodaimusSubentryFlowHandler(ConfigSubentryFlow):
    """Flow for managing nicodAImus conversation subentries."""

    options: dict[str, Any]

    @property
    def _is_new(self) -> bool:
        """Return if this is a new subentry."""
        return self.source == "user"

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Add a subentry."""
        self.options = RECOMMENDED_CONVERSATION_OPTIONS.copy()
        return await self.async_step_init()

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Handle reconfiguration of a subentry."""
        self.options = self._get_reconfigure_subentry().data.copy()
        return await self.async_step_init()

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Set initial options."""
        if self._get_entry().state != ConfigEntryState.LOADED:
            return self.async_abort(reason="entry_not_loaded")

        hass_apis: list[SelectOptionDict] = [
            SelectOptionDict(label=api.name, value=api.id)
            for api in llm.async_get_apis(self.hass)
        ]
        if suggested_llm_apis := self.options.get(CONF_LLM_HASS_API):
            if isinstance(suggested_llm_apis, str):
                suggested_llm_apis = [suggested_llm_apis]
            known_apis = {api.id for api in llm.async_get_apis(self.hass)}
            self.options[CONF_LLM_HASS_API] = [
                api for api in suggested_llm_apis if api in known_apis
            ]

        step_schema: VolDictType = {}

        if self._is_new:
            step_schema[
                vol.Required(CONF_NAME, default=DEFAULT_CONVERSATION_NAME)
            ] = str

        step_schema.update(
            {
                vol.Optional(CONF_PROMPT): TemplateSelector(),
                vol.Optional(CONF_LLM_HASS_API): SelectSelector(
                    SelectSelectorConfig(options=hass_apis, multiple=True)
                ),
                vol.Required(
                    CONF_RECOMMENDED,
                    default=self.options.get(CONF_RECOMMENDED, False),
                ): bool,
            }
        )

        if user_input is not None:
            if not user_input.get(CONF_LLM_HASS_API):
                user_input.pop(CONF_LLM_HASS_API, None)

            if user_input[CONF_RECOMMENDED]:
                if self._is_new:
                    return self.async_create_entry(
                        title=user_input.pop(CONF_NAME),
                        data=user_input,
                    )
                return self.async_update_and_abort(
                    self._get_entry(),
                    self._get_reconfigure_subentry(),
                    data=user_input,
                )

            self.options.update(user_input)
            if (
                CONF_LLM_HASS_API in self.options
                and CONF_LLM_HASS_API not in user_input
            ):
                self.options.pop(CONF_LLM_HASS_API)
            return await self.async_step_advanced()

        return self.async_show_form(
            step_id="init",
            data_schema=self.add_suggested_values_to_schema(
                vol.Schema(step_schema), self.options
            ),
        )

    async def async_step_advanced(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Manage advanced options."""
        step_schema: VolDictType = {
            vol.Optional(
                CONF_CHAT_MODEL, default=DEFAULT_MODEL
            ): str,
            vol.Optional(
                CONF_MAX_TOKENS, default=RECOMMENDED_MAX_TOKENS
            ): int,
            vol.Optional(
                CONF_TEMPERATURE, default=RECOMMENDED_TEMPERATURE
            ): NumberSelector(
                NumberSelectorConfig(min=0, max=2, step=0.1)
            ),
        }

        if user_input is not None:
            self.options.update(user_input)
            if self._is_new:
                return self.async_create_entry(
                    title=self.options.pop(CONF_NAME),
                    data=self.options,
                )
            return self.async_update_and_abort(
                self._get_entry(),
                self._get_reconfigure_subentry(),
                data=self.options,
            )

        return self.async_show_form(
            step_id="advanced",
            data_schema=self.add_suggested_values_to_schema(
                vol.Schema(step_schema), self.options
            ),
            last_step=True,
        )
