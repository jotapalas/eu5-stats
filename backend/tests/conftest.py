from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SAVES = sorted(
    p for d in (
        ROOT,
        ROOT / "tests" / "fixtures"
    ) for p in d.glob("*.eu5")
)
MP_SAVE = ROOT / "tests" / "fixtures" / "test_save.eu5"


def pytest_generate_tests(metafunc):
    if "save_path" in metafunc.fixturenames:
        metafunc.parametrize("save_path", SAVES, ids=[p.name for p in SAVES])


@pytest.fixture(scope="session")
def mp_save_bytes() -> bytes:
    if not MP_SAVE.exists():
        pytest.skip(f"{MP_SAVE.name} not present")
    return MP_SAVE.read_bytes()


@pytest.fixture(scope="session")
def mp_stats(mp_save_bytes):
    from app.eu5.tokens import TokenTable
    from app.stats.extract import extract

    return extract(mp_save_bytes, TokenTable())
