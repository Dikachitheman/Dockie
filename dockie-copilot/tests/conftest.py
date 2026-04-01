"""
pytest configuration.

Sets asyncio mode and provides shared fixtures.
"""

import pytest


@pytest.fixture
def anyio_backend():
    return "asyncio"
