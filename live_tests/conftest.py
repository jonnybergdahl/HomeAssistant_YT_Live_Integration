"""Conftest for live tests — re-enables real network access."""

from __future__ import annotations

import socket

import pytest
import pytest_socket


@pytest.fixture(autouse=True)
def enable_network():
    """Re-enable socket.socket and restore connect() for live network access."""
    pytest_socket.enable_socket()
    # The HA test framework patches socket.socket.connect with a host-allowlist
    # guard. Restore the original connect method so tests can reach the internet.
    socket.socket.connect = pytest_socket._true_connect
    yield
    pytest_socket.disable_socket()
