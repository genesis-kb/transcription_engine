"""
Section 7 — Server Lifecycle Tests
=====================================
Integration tests for the server start / stop / queue cycle.

These tests are marked ``server`` and ``integration`` and are skipped
automatically unless the environment variable ``TRANSCRIPTION_SERVER_URL``
is set.  They should NOT run in a regular unit-test CI pass.

Run them manually with:
    pytest -m server -v
"""

import os
import time

import pytest
import requests

pytestmark = [pytest.mark.integration, pytest.mark.server]

# ---------------------------------------------------------------------------
# Guard: skip all tests in this file when no server URL is configured
# ---------------------------------------------------------------------------

SERVER_URL = os.getenv("TRANSCRIPTION_SERVER_URL", "")

if not SERVER_URL:
    pytestmark = [
        pytest.mark.integration,
        pytest.mark.server,
        pytest.mark.skip(reason="TRANSCRIPTION_SERVER_URL is not set — skipping server lifecycle tests"),
    ]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _is_running(url: str, timeout: int = 3) -> bool:
    try:
        r = requests.get(f"{url}/health", timeout=timeout)
        return r.status_code == 200
    except requests.RequestException:
        return False


def _wait_until(condition_fn, timeout=15, interval=1):
    """Poll condition_fn every ``interval`` seconds until True or timeout."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if condition_fn():
            return True
        time.sleep(interval)
    return False


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestServerLifecycle:
    """Group lifecycle tests so they share setup / teardown ordering."""

    def test_health_endpoint_returns_200_when_running(self):
        """If a server is already running, GET /health must return 200."""
        if not _is_running(SERVER_URL):
            pytest.skip("Server is not running — start it first with 'tstbtc server start'")
        r = requests.get(f"{SERVER_URL}/health", timeout=5)
        assert r.status_code == 200

    def test_server_stop_makes_health_unreachable(self):
        """After stopping the server, /health must be unreachable."""
        if not _is_running(SERVER_URL):
            pytest.skip("Server is not running")

        from app.commands.cli_utils import stop_server
        stopped = stop_server(mode="prod")
        assert stopped, "stop_server() returned False"

        # Give the OS a moment to release the port
        became_unreachable = _wait_until(lambda: not _is_running(SERVER_URL), timeout=5)
        assert became_unreachable, "/health still reachable after stop"


    def test_server_start_makes_health_reachable(self):
        """After starting the server, GET /health must return 200."""
        from app.commands.cli_utils import start_server, is_server_running

        if is_server_running(SERVER_URL):
            pytest.skip("Server is already running")

        started = start_server(mode="prod")
        assert started, "start_server() returned False"

        reachable = _wait_until(lambda: _is_running(SERVER_URL), timeout=15)
        assert reachable, "/health not reachable after start"

    def test_get_queue_returns_list(self):
        """GET /transcription/queue/ must return JSON with a 'data' key containing a list."""
        if not _is_running(SERVER_URL):
            pytest.skip("Server is not running")

        r = requests.get(f"{SERVER_URL}/transcription/queue/", timeout=5)
        assert r.status_code == 200
        body = r.json()
        assert "data" in body
        assert isinstance(body["data"], list)

    def test_get_queue_empty_initially(self):
        """On a fresh server, the queue must be empty."""
        if not _is_running(SERVER_URL):
            pytest.skip("Server is not running")

        r = requests.get(f"{SERVER_URL}/transcription/queue/", timeout=5)
        assert r.status_code == 200
        assert r.json()["data"] == []

    def test_auto_start_message_logged(self, capsys, monkeypatch, tmp_path):
        """
        The auto_start_server decorator must print the expected messages
        when the server is not running and auto_server=True.

        This test verifies the log output, not real server startup.
        """
        from unittest.mock import patch, MagicMock

        # Make is_server_running always return False so we enter the auto-start branch
        with patch("app.commands.cli_utils.is_server_running", return_value=False), \
             patch("app.commands.cli_utils.start_server", return_value=True) as mock_start:
            from app.commands.cli_utils import auto_start_server
            import click
            
            assert mock_start.call_count == 0  # Not called yet

            mock_ctx = MagicMock()
            mock_ctx.protected_args = []
            mock_ctx.help_option_names = ["--help", "-h"]
            mock_ctx.command.name = "transcribe"
            mock_ctx.obj = {"auto_server": True}
            mock_ctx.invoke = lambda f, *a, **kw: f(*a, **kw)

            @auto_start_server
            def dummy_func():
                return "execution_result"

            res = dummy_func(mock_ctx)
            assert res == "execution_result"
            assert mock_start.call_count == 1

            captured = capsys.readouterr()
            assert "Auto-starting server for command" in captured.out
            assert "starting" in captured.out or "server" in captured.out

