from pathlib import Path

import pytest

from platform_api.catalog import Catalog

REPO_ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture(scope="session")
def catalog() -> Catalog:
    return Catalog(REPO_ROOT / "platform" / "catalog")
