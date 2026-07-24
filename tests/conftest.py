"""Test setup — offline, deterministic, isolated.

Offline determinism runs THROUGH the agent loop via the mock provider (not a rules bypass). Data + DBs
live in a throwaway temp dir so tests never touch the real store/audit. Env is set before any frisk import
so the provider + data paths bind to the test values.
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

os.environ["FRISK_PROVIDER"] = "mock"                       # drive the agent deterministically, no API
os.environ.setdefault("FRISK_DATA_DIR", tempfile.mkdtemp(prefix="frisk_test_"))
os.environ.setdefault("FRISK_REDIS_URL", "redis://127.0.0.1:6553/0")  # unreachable -> in-memory fallback

import pytest  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _seed_data():
    from frisk.data import audit, casebank, store
    from frisk.data.generate import write
    write()                       # generate the 20 dossiers into the temp customers dir
    store.migrate(); casebank.migrate(); audit.reset()
    yield
