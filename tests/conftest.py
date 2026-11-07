"""Lets the tests import the project modules (config, intent_classifier, ...)
no matter where pytest is started from."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


import pytest  # noqa: E402

import config  # noqa: E402


@pytest.fixture(autouse=True)
def fast_pin_hashing(monkeypatch):
    """Real hashing uses 200,000 rounds (slow on purpose). Tests use 1,000 so
    they stay fast; one test checks that the real setting is still high."""
    monkeypatch.setattr(config, "PIN_HASH_ITERATIONS", 1000)
