import pytest

from runtime.manifest import (
    AgentManifest,
    CapabilityMap,
    ManifestViolation,
    load_manifest,
    validate_manifest,
)

from .conftest import AGENTS_DIR


def test_capability_rules_cover_the_real_allowlist(capmap: CapabilityMap) -> None:
    manifest = load_manifest(AGENTS_DIR / "incident_triage" / "manifest.yaml")
    resolved = validate_manifest(manifest, capmap)
    assert resolved["kubernetes.kubectl_get"] == {"capability": "read", "target": "cluster"}
    assert resolved["github.create_pull_request"] == {"capability": "write", "target": "github"}
    assert all(
        v["capability"] == "read" for t, v in resolved.items() if t.startswith("kubernetes.")
    )
    # labels exist for tools this agent does not use today
    assert capmap.capability("grafana.query_loki_logs") == "read"
    assert capmap.capability("local.git_log") == "read"
    assert manifest.mutation == "propose_only"
    assert manifest.allowed_namespaces == ["demo"]


def test_unknown_tool_is_an_error(capmap: CapabilityMap) -> None:
    with pytest.raises(ManifestViolation):
        capmap.capability("kubernetes.no_such_tool_xyz")  # falls to kubernetes.* = write, fine
        capmap.capability("nowhere.tool")


@pytest.mark.parametrize(
    "tool,fragment",
    [
        ("kubernetes.kubectl_delete", "delete on the cluster"),
        ("kubernetes.kubectl_apply", "write on the cluster"),
        ("kubernetes.kubectl_patch", "write on the cluster"),
        ("github.delete_file", "delete on github"),
    ],
)
def test_propose_only_refuses_cluster_writes_and_any_delete(
    capmap: CapabilityMap, tool: str, fragment: str
) -> None:
    manifest = AgentManifest(
        name="bad",
        allowed_namespaces=["demo"],
        allowed_tools=["kubernetes.kubectl_get", tool],
    )
    with pytest.raises(ManifestViolation) as e:
        validate_manifest(manifest, capmap)
    assert tool in str(e.value) and fragment in str(e.value)


def test_github_write_is_allowed_for_proposals(capmap: CapabilityMap) -> None:
    manifest = AgentManifest(
        name="ok",
        allowed_namespaces=["demo"],
        allowed_tools=["github.create_branch", "github.create_pull_request"],
    )
    resolved = validate_manifest(manifest, capmap)
    assert all(v["capability"] == "write" and v["target"] == "github" for v in resolved.values())


def test_no_namespaces_is_a_violation(capmap: CapabilityMap) -> None:
    with pytest.raises(ManifestViolation):
        validate_manifest(AgentManifest(name="x", allowed_tools=["kubernetes.kubectl_get"]), capmap)
