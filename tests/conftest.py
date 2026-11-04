import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).parent))

from fixture_http import fixture_get  # noqa: E402
from steward_kit.config import load_config  # noqa: E402
from steward_kit.demo import build_duckdb  # noqa: E402
from steward_kit.sources import fetch_all  # noqa: E402


@pytest.fixture(scope="session")
def cfg():
    return load_config(ROOT / "governance.yml")


@pytest.fixture(scope="session")
def data_dir(tmp_path_factory):
    """data/raw built offline: NHTSA from the test fixture, EPA from the committed real file."""
    d = tmp_path_factory.mktemp("data")
    (d / "raw").mkdir()
    shutil.copy(ROOT / "data" / "raw" / "epa_vehicles_gm.csv", d / "raw" / "epa_vehicles_gm.csv")
    fetch_all(d / "raw", get=fixture_get, pause=0)
    return d


@pytest.fixture(scope="session")
def demo_catalog(tmp_path_factory, data_dir, cfg):
    db = tmp_path_factory.mktemp("db") / "catalog.duckdb"
    cat = build_duckdb(str(db), cfg["catalog"], data_dir=data_dir)
    yield cat
    cat.close()
