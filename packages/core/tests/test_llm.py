"""Tests for the shared LLM client factory."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import astral_core.llm as llm_mod
from astral_core import get_llm_client


class TestGetLlmClient:
    def setup_method(self):
        """Reset module-level state between tests."""
        llm_mod._braintrust_initialized = False
        llm_mod._braintrust_warned = False

    def test_no_api_key_returns_none(self, monkeypatch):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        assert get_llm_client() is None

    def test_with_api_key_returns_client(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
        mock_client = MagicMock()
        with patch("anthropic.AsyncAnthropic", return_value=mock_client):
            result = get_llm_client()
        assert result is mock_client

    def test_braintrust_wraps_client(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
        monkeypatch.setenv("BRAINTRUST_API_KEY", "bt-key")
        monkeypatch.setattr(llm_mod, "_braintrust_initialized", False)

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

    def test_braintrust_import_error_falls_back(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
        monkeypatch.setenv("BRAINTRUST_API_KEY", "bt-key")
        monkeypatch.setattr(llm_mod, "_braintrust_initialized", False)

        mock_client = MagicMock()
        with patch("anthropic.AsyncAnthropic", return_value=mock_client):
            # braintrust not installed — ImportError handled gracefully
            result = get_llm_client()
        assert result is mock_client

    def test_init_logger_called_once(self, monkeypatch):
        """init_logger is called only on the first invocation."""
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
        monkeypatch.setenv("BRAINTRUST_API_KEY", "bt-key")
        monkeypatch.setattr(llm_mod, "_braintrust_initialized", False)

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
