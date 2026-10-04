"""Shared pytest fixtures."""
import pytest

from data.generate import generate


@pytest.fixture(scope="session")
def dataset():
    return generate(seed=42)