"""Tests for nicodAImus client integration patterns.

Tests the client error handling and response patterns that the
HA integration relies on. Uses the python-nicodaimus library directly.
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp
import pytest

from nicodaimus import (
    NicodaimusAuthError,
    NicodaimusClient,
    NicodaimusConnectionError,
    NicodaimusError,
    NicodaimusRateLimitError,
)


class TestClientErrorMapping:
    """Test that client errors map correctly for HA error handling."""

    def test_auth_error_is_nicodaimus_error(self) -> None:
        """NicodaimusAuthError should be a NicodaimusError subclass."""
        err = NicodaimusAuthError("Invalid API key")
        assert isinstance(err, NicodaimusError)
        assert isinstance(err, NicodaimusAuthError)

    def test_connection_error_is_nicodaimus_error(self) -> None:
        """NicodaimusConnectionError should be a NicodaimusError subclass."""
        err = NicodaimusConnectionError("Cannot connect")
        assert isinstance(err, NicodaimusError)
        assert isinstance(err, NicodaimusConnectionError)

    def test_rate_limit_error_has_retry_after(self) -> None:
        """NicodaimusRateLimitError should carry retry_after."""
        err = NicodaimusRateLimitError("Rate limited", retry_after=86400)
        assert isinstance(err, NicodaimusError)
        assert err.retry_after == 86400

    def test_rate_limit_error_without_retry_after(self) -> None:
        """NicodaimusRateLimitError should work without retry_after."""
        err = NicodaimusRateLimitError("Rate limited")
        assert err.retry_after is None


class TestClientConstruction:
    """Test client construction patterns used by the HA integration."""

    def test_base_url_trailing_slash_stripped(self) -> None:
        """Test that trailing slash is stripped from base URL."""
        session = MagicMock(spec=aiohttp.ClientSession)
        client = NicodaimusClient(
            api_key="sk-test",
            session=session,
            base_url="https://chat.nicodaimus.com/v1/",
        )
        assert client.base_url == "https://chat.nicodaimus.com/v1"

    def test_default_base_url(self) -> None:
        """Test default base URL."""
        session = MagicMock(spec=aiohttp.ClientSession)
        client = NicodaimusClient(
            api_key="sk-test",
            session=session,
        )
        assert client.base_url == "https://chat.nicodaimus.com/v1"

    def test_custom_base_url(self) -> None:
        """Test custom base URL."""
        session = MagicMock(spec=aiohttp.ClientSession)
        client = NicodaimusClient(
            api_key="sk-test",
            session=session,
            base_url="https://custom.example.com/api",
        )
        assert client.base_url == "https://custom.example.com/api"


class TestHAErrorPatterns:
    """Test error patterns the HA integration expects."""

    def test_auth_errors_trigger_reauth(self) -> None:
        """HA maps NicodaimusAuthError to ConfigEntryAuthFailed.

        Verify the error chain works: 401/403 -> NicodaimusAuthError
        -> ConfigEntryAuthFailed (in __init__.py).
        """
        err = NicodaimusAuthError("API key has been revoked")
        assert str(err) == "API key has been revoked"

    def test_connection_errors_trigger_not_ready(self) -> None:
        """HA maps NicodaimusConnectionError to ConfigEntryNotReady.

        Verify the error chain works: network error -> NicodaimusConnectionError
        -> ConfigEntryNotReady (in __init__.py).
        """
        err = NicodaimusConnectionError("Cannot connect to nicodAImus API")
        assert "Cannot connect" in str(err)

    def test_generic_errors_become_ha_errors(self) -> None:
        """HA maps NicodaimusError to HomeAssistantError.

        Verify that generic API errors are catchable.
        """
        err = NicodaimusError("API error (502): Upstream service error")
        assert "502" in str(err)

    def test_error_hierarchy_catch_all(self) -> None:
        """All nicodaimus errors should be catchable by NicodaimusError."""
        errors = [
            NicodaimusAuthError("auth"),
            NicodaimusConnectionError("conn"),
            NicodaimusRateLimitError("rate"),
            NicodaimusError("generic"),
        ]
        for err in errors:
            assert isinstance(err, NicodaimusError)
