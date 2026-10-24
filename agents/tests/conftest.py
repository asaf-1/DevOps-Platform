from pathlib import Path

import pytest

from runtime.manifest import CapabilityMap

REPO_ROOT = Path(__file__).resolve().parents[2]
AGENTS_DIR = REPO_ROOT / "agents"


@pytest.fixture(scope="session")
def capmap() -> CapabilityMap:
    return CapabilityMap.load(
        AGENTS_DIR / "tools" / "capabilities.yaml", AGENTS_DIR / "tools" / "mcp.yaml"
    )
