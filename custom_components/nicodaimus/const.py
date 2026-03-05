"""Constants for the nicodAImus integration."""

from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.const import CONF_LLM_HASS_API
from homeassistant.helpers import llm

DOMAIN = "nicodaimus"
LOGGER: logging.Logger = logging.getLogger(__package__)

DEFAULT_BASE_URL = "https://chat.nicodaimus.com/v1"
DEFAULT_MODEL = "auto"
DEFAULT_CONVERSATION_NAME = "nicodAImus Conversation"

ACCOUNT_API_PATH = "/account-api"
DEFAULT_SCAN_INTERVAL = timedelta(minutes=5)

CONF_BASE_URL = "base_url"
CONF_CHAT_MODEL = "chat_model"
CONF_MAX_TOKENS = "max_tokens"
CONF_PROMPT = "prompt"
CONF_RECOMMENDED = "recommended"
CONF_TEMPERATURE = "temperature"

RECOMMENDED_MAX_TOKENS = 1024
RECOMMENDED_TEMPERATURE = 0.7

RECOMMENDED_CONVERSATION_OPTIONS = {
    CONF_RECOMMENDED: True,
    CONF_LLM_HASS_API: [llm.LLM_API_ASSIST],
    CONF_PROMPT: llm.DEFAULT_INSTRUCTIONS_PROMPT,
}

# Max number of back and forth with the LLM to generate a response
MAX_TOOL_ITERATIONS = 10
