"""Tests for game.engine.llm — LLM narration enhancer."""

from __future__ import annotations

import json
import random
from http.server import BaseHTTPRequestHandler, HTTPServer
from threading import Thread
from unittest.mock import MagicMock, patch

import pytest

from engine.llm import (
    DEFAULT_BASE_URL,
    LLM_OPT_IN_TAGS,
    MAX_CONSECUTIVE_ERRORS,
    LLMClient,
    LLMPrompt,
    build_llm_prompt,
    enhance_narration,
    llm_config_from_dict,
    llm_config_to_dict,
    should_enhance,
)


# ── build_llm_prompt ────────────────────────────────────────────────


class TestBuildLLMPrompt:
    def test_minimal(self):
        p = build_llm_prompt("Alex scored a goal.")
        assert isinstance(p, LLMPrompt)
        assert "Alex scored a goal." in p.user
        assert p.system  # non-empty

    def test_with_context(self):
        p = build_llm_prompt(
            "Alex scored a goal.",
            arc_summary="Alex has been struggling with form.",
            previous_summary="Lost 2-1 last match.",
            cast_names=["Alex", "Jordan"],
            branch_summary="Player chose to celebrate.",
        )
        assert "Alex has been struggling" in p.user
        assert "Lost 2-1" in p.user
        assert "Alex, Jordan" in p.user
        assert "Alex scored a goal." in p.user

    def test_max_tokens_scales_with_input(self):
        short = build_llm_prompt("Hello world.")
        long_text = " ".join(["word"] * 200)
        long = build_llm_prompt(long_text)
        assert long.max_tokens >= short.max_tokens
        assert long.max_tokens <= 500  # capped

    def test_location_grounds_setting(self):
        """Phase 22: setting pinned in the prompt so small models don't
        drift genre (a locker-bay scene once came back set in a tavern)."""
        p = build_llm_prompt("Alex went quiet.", location="locker_bay")
        assert "Setting: locker bay" in p.user
        # No location → no setting line.
        bare = build_llm_prompt("Alex went quiet.")
        assert "Setting:" not in bare.user

    def test_system_prompt_constrains_genre(self):
        p = build_llm_prompt("Alex went quiet.")
        assert "present day" in p.system
        assert "Do NOT change or invent the setting" in p.system


# ── should_enhance ──────────────────────────────────────────────────


class TestShouldEnhance:
    def test_opt_in_tags(self):
        for tag in LLM_OPT_IN_TAGS:
            assert should_enhance({tag})

    def test_no_opt_in(self):
        assert not should_enhance({"training"})
        assert not should_enhance({"downtime"})
        assert not should_enhance(set())

    def test_mixed_tags(self):
        assert should_enhance({"training", "conflict"})


# ── LLMClient ───────────────────────────────────────────────────────


class TestLLMClient:
    def test_disabled_returns_none(self):
        client = LLMClient(enabled=False)
        prompt = build_llm_prompt("test")
        assert client.generate(prompt) is None

    def test_unavailable_returns_none(self):
        """Connection error → silent fallback."""
        client = LLMClient(base_url="http://localhost:59999/v1", timeout=1)
        prompt = build_llm_prompt("test")
        assert client.generate(prompt) is None

    def test_is_available_when_disabled(self):
        client = LLMClient(enabled=False)
        assert not client.is_available()

    def test_is_available_when_no_server(self):
        client = LLMClient(base_url="http://localhost:59999/v1", timeout=1)
        assert not client.is_available()

    def test_list_models_when_no_server(self):
        client = LLMClient(base_url="http://localhost:59999/v1", timeout=1)
        assert client.list_models() == []

    def test_auto_disable_after_consecutive_errors(self):
        """Client disables itself after MAX_CONSECUTIVE_ERRORS failures."""
        client = LLMClient(base_url="http://localhost:59999/v1", timeout=1)
        prompt = build_llm_prompt("test")
        assert client.enabled is True

        for i in range(MAX_CONSECUTIVE_ERRORS):
            assert client.generate(prompt) is None

        # Should have auto-disabled
        assert client.enabled is False
        assert client._consecutive_errors == MAX_CONSECUTIVE_ERRORS

    def test_success_resets_error_count(self, mock_server):
        """A successful call resets the consecutive error counter."""
        client = LLMClient(base_url=mock_server, model="test-model")
        # Simulate some prior errors
        client._consecutive_errors = MAX_CONSECUTIVE_ERRORS - 1
        prompt = build_llm_prompt("Alex scored a goal.")
        result = client.generate(prompt)
        assert result is not None
        assert client._consecutive_errors == 0
        assert client.enabled is True


# ── LLMClient with a local test server ──────────────────────────────


class _MockLMStudioHandler(BaseHTTPRequestHandler):
    """Minimal handler that mimics the LM Studio OpenAI API."""

    response_text = "Alex scored a brilliant goal, electrifying the crowd."

    def do_GET(self):
        if self.path == "/v1/models":
            body = json.dumps(
                {"data": [{"id": "test-model"}]}
            ).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_error(404)

    def do_POST(self):
        if self.path == "/v1/chat/completions":
            content_len = int(self.headers.get("Content-Length", 0))
            self.rfile.read(content_len)  # consume body
            body = json.dumps(
                {
                    "choices": [
                        {
                            "message": {
                                "role": "assistant",
                                "content": self.response_text,
                            }
                        }
                    ]
                }
            ).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_error(404)

    def log_message(self, format, *args):
        pass  # suppress server logs during tests


@pytest.fixture(scope="module")
def mock_server():
    """Start a local HTTP server for the duration of the test module."""
    server = HTTPServer(("127.0.0.1", 0), _MockLMStudioHandler)
    port = server.server_address[1]
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{port}/v1"
    server.shutdown()


class TestLLMClientWithServer:
    def test_generate_returns_text(self, mock_server):
        client = LLMClient(base_url=mock_server, model="test-model")
        prompt = build_llm_prompt("Alex scored a goal.")
        result = client.generate(prompt)
        assert result is not None
        assert "Alex" in result

    def test_is_available(self, mock_server):
        client = LLMClient(base_url=mock_server)
        assert client.is_available()

    def test_list_models(self, mock_server):
        client = LLMClient(base_url=mock_server)
        models = client.list_models()
        assert "test-model" in models


# ── enhance_narration ───────────────────────────────────────────────


class TestEnhanceNarration:
    def test_skips_non_opt_in_tags(self, mock_server):
        client = LLMClient(base_url=mock_server)
        result = enhance_narration(
            client,
            "Alex trained hard.",
            event_tags={"training"},
            cast_names=["Alex"],
        )
        # Should return the filled template unchanged — no LLM call.
        assert result == "Alex trained hard."

    def test_enhances_opt_in_tags(self, mock_server):
        client = LLMClient(base_url=mock_server)
        result = enhance_narration(
            client,
            "Alex scored a goal.",
            event_tags={"conflict", "postgame"},
            cast_names=["Alex"],
        )
        # Should return the LLM-enhanced version.
        assert result != "Alex scored a goal."
        assert "Alex" in result

    def test_fallback_on_disabled_client(self):
        client = LLMClient(enabled=False)
        result = enhance_narration(
            client,
            "Alex scored a goal.",
            event_tags={"conflict"},
            cast_names=["Alex"],
        )
        assert result == "Alex scored a goal."

    def test_fallback_on_name_mismatch(self, mock_server):
        """If LLM drops all character names, fall back to template."""
        # Patch the handler to return text without any names.
        original = _MockLMStudioHandler.response_text
        _MockLMStudioHandler.response_text = (
            "The player made an incredible play."
        )
        try:
            client = LLMClient(base_url=mock_server)
            result = enhance_narration(
                client,
                "Alex scored a goal.",
                event_tags={"conflict"},
                cast_names=["Alex"],
            )
            # Should fall back because "Alex" isn't in LLM response.
            assert result == "Alex scored a goal."
        finally:
            _MockLMStudioHandler.response_text = original

    def test_no_cast_names_skips_name_check(self, mock_server):
        """If no cast names provided, skip the name check."""
        client = LLMClient(base_url=mock_server)
        result = enhance_narration(
            client,
            "Something happened.",
            event_tags={"vulnerability"},
        )
        # Should use the LLM result even without name check.
        assert result != "Something happened."


# ── Config serialisation ────────────────────────────────────────────


class TestLLMConfig:
    def test_roundtrip(self):
        client = LLMClient(
            base_url="http://example.com/v1",
            model="my-model",
            timeout=5,
            enabled=True,
        )
        d = llm_config_to_dict(client)
        restored = llm_config_from_dict(d)
        assert restored.base_url == client.base_url
        assert restored.model == client.model
        assert restored.timeout == client.timeout
        assert restored.enabled == client.enabled

    def test_defaults_on_empty_dict(self):
        client = llm_config_from_dict({})
        assert client.base_url == DEFAULT_BASE_URL
        assert client.enabled is True


class TestStripReasoning:
    def test_strips_closed_think_block(self):
        from engine.llm import _strip_reasoning

        out = _strip_reasoning("<think>plan plan plan</think>Alex went quiet.")
        assert out == "Alex went quiet."

    def test_strips_unterminated_block_to_empty(self):
        from engine.llm import _strip_reasoning

        assert _strip_reasoning("<think>still thinking when the cap hit") == ""

    def test_plain_content_untouched(self):
        from engine.llm import _strip_reasoning

        assert _strip_reasoning("Alex went quiet.") == "Alex went quiet."
