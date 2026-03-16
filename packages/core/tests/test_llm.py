"""Tests for the shared LLM client factory."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import astral_core.llm as llm_mod
import astral_core.observability._resolve as resolve_mod
from astral_core import get_llm_client


class TestGetLlmClient:
    def setup_method(self):
        """Reset module-level state between tests."""
        llm_mod._warned = False
        resolve_mod.reset()

    def test_no_api_key_returns_none(self, monkeypatch):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        assert get_llm_client() is None

    def test_with_api_key_returns_client(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
        monkeypatch.delenv("BRAINTRUST_API_KEY", raising=False)
        monkeypatch.delenv("BRAINTRUST_TRACE", raising=False)
        monkeypatch.delenv("PHOENIX_COLLECTOR_ENDPOINT", raising=False)
        monkeypatch.delenv("PHOENIX_API_URL", raising=False)
        monkeypatch.delenv("ASTRAL_OBSERVABILITY_BACKEND", raising=False)
        mock_client = MagicMock()
        with patch("anthropic.AsyncAnthropic", return_value=mock_client):
            result = get_llm_client()
        assert result is mock_client

    def test_braintrust_wraps_client_when_trace_enabled(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
        monkeypatch.setenv("BRAINTRUST_API_KEY", "bt-key")
        monkeypatch.setenv("BRAINTRUST_TRACE", "1")
        monkeypatch.delenv("PHOENIX_COLLECTOR_ENDPOINT", raising=False)
        monkeypatch.delenv("PHOENIX_API_URL", raising=False)
        monkeypatch.delenv("ASTRAL_OBSERVABILITY_BACKEND", raising=False)

        mock_client = MagicMock()
        wrapped = MagicMock()
        mock_init = MagicMock()
        mock_wrap = MagicMock(return_value=wrapped)

        with (
            patch("anthropic.AsyncAnthropic", return_value=mock_client),
            patch.dict(
                "sys.modules",
                {
                    "braintrust": MagicMock(
                        init_logger=mock_init, wrap_anthropic=mock_wrap
                    )
                },
            ),
        ):
            result = get_llm_client()

        mock_init.assert_called_once_with(project="astral-index")
        mock_wrap.assert_called_once_with(mock_client)
        assert result is wrapped

    def test_no_wrapping_without_trace_env(self, monkeypatch):
        """wrap_anthropic is NOT called when BRAINTRUST_TRACE is unset."""
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
        monkeypatch.setenv("BRAINTRUST_API_KEY", "bt-key")
        monkeypatch.delenv("BRAINTRUST_TRACE", raising=False)
        monkeypatch.delenv("PHOENIX_COLLECTOR_ENDPOINT", raising=False)
        monkeypatch.delenv("PHOENIX_API_URL", raising=False)
        monkeypatch.delenv("ASTRAL_OBSERVABILITY_BACKEND", raising=False)

        mock_client = MagicMock()
        mock_init = MagicMock()
        mock_wrap = MagicMock()

        with (
            patch("anthropic.AsyncAnthropic", return_value=mock_client),
            patch.dict(
                "sys.modules",
                {
                    "braintrust": MagicMock(
                        init_logger=mock_init, wrap_anthropic=mock_wrap
                    )
                },
            ),
        ):
            result = get_llm_client()

        mock_init.assert_not_called()
        mock_wrap.assert_not_called()
        assert result is mock_client

    def test_braintrust_import_error_falls_back(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
        monkeypatch.setenv("BRAINTRUST_API_KEY", "bt-key")
        monkeypatch.setenv("BRAINTRUST_TRACE", "1")
        monkeypatch.delenv("PHOENIX_COLLECTOR_ENDPOINT", raising=False)
        monkeypatch.delenv("PHOENIX_API_URL", raising=False)
        monkeypatch.delenv("ASTRAL_OBSERVABILITY_BACKEND", raising=False)

        mock_client = MagicMock()
        with patch("anthropic.AsyncAnthropic", return_value=mock_client):
            # braintrust not installed — ImportError handled gracefully
            result = get_llm_client()
        assert result is mock_client

    def test_init_logger_called_once(self, monkeypatch):
        """init_logger is called only on the first invocation."""
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
        monkeypatch.setenv("BRAINTRUST_API_KEY", "bt-key")
        monkeypatch.setenv("BRAINTRUST_TRACE", "1")
        monkeypatch.delenv("PHOENIX_COLLECTOR_ENDPOINT", raising=False)
        monkeypatch.delenv("PHOENIX_API_URL", raising=False)
        monkeypatch.delenv("ASTRAL_OBSERVABILITY_BACKEND", raising=False)

        mock_init = MagicMock()
        mock_wrap = MagicMock(side_effect=lambda c: c)

        with (
            patch("anthropic.AsyncAnthropic", return_value=MagicMock()),
            patch.dict(
                "sys.modules",
                {
                    "braintrust": MagicMock(
                        init_logger=mock_init, wrap_anthropic=mock_wrap
                    )
                },
            ),
        ):
            get_llm_client()
            get_llm_client()

        mock_init.assert_called_once()

    def test_anthropic_import_error_returns_none(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
        with patch.dict("sys.modules", {"anthropic": None}):
            result = get_llm_client()
        assert result is None

    def test_no_warning_when_api_key_set_but_trace_off(self, monkeypatch, caplog):
        """No Braintrust warning when API key is set but trace is off."""
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
        monkeypatch.setenv("BRAINTRUST_API_KEY", "bt-key")
        monkeypatch.delenv("BRAINTRUST_TRACE", raising=False)
        monkeypatch.delenv("PHOENIX_COLLECTOR_ENDPOINT", raising=False)
        monkeypatch.delenv("PHOENIX_API_URL", raising=False)
        monkeypatch.delenv("ASTRAL_OBSERVABILITY_BACKEND", raising=False)

        mock_client = MagicMock()
        with patch("anthropic.AsyncAnthropic", return_value=mock_client):
            get_llm_client()

        assert "not set" not in caplog.text
