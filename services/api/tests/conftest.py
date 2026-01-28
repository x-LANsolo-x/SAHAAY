import pytest


@pytest.fixture
def anyio_backend():
    # Force asyncio backend so tests don't require trio.
    return "asyncio"
