import yaml

from runtime.knowledge import Knowledge, alert_tags

from .conftest import REPO_ROOT

AGENT_TAGS = set(
    yaml.safe_load((REPO_ROOT / "agents" / "incident_triage" / "manifest.yaml").read_text())[
        "knowledge_tags"
    ]
)


def test_runbooks_load_with_tags() -> None:
    k = Knowledge.load(REPO_ROOT / "docs" / "runbooks")
    titles = {b.path.stem for b in k.runbooks}
    assert {
        "imagepullbackoff",
        "oomkilled",
        "crashloop",
        "unavailable",
        "tls-expired",
        "hpa-at-max",
        "high-latency",
    } <= titles
    assert all("kubernetes" in b.tags for b in k.runbooks)


def test_alert_tags_from_labels() -> None:
    tags = alert_tags(
        {"alertname": "DemoAppImagePullBackOff", "namespace": "demo", "app": "demo-app"}
    )
    assert {"kubernetes", "demo", "demo-app", "imagepull"} <= tags
    assert "oom" not in tags


def test_selection_is_an_intersection() -> None:
    k = Knowledge.load(REPO_ROOT / "docs" / "runbooks")
    agent_tags = {"kubernetes", "demo-app", "crashloop", "imagepull", "oom"}
    chosen = k.select(alert_tags({"alertname": "DemoAppOOMKilled", "app": "demo-app"}), agent_tags)
    stems = {b.path.stem for b in chosen}
    assert "oomkilled" in stems
    # the specific keyword wins: the imagepull runbook is not sent for an OOM alert
    assert "imagepullbackoff" not in stems
    # an alert with no keyword match falls back to the generic app runbooks
    generic = k.select(
        alert_tags({"alertname": "DemoAppUnknownThing", "app": "demo-app"}), agent_tags
    )
    assert len(generic) == len(k.runbooks)
    # an agent that only knows about imagepull does not get the OOM runbook for an imagepull alert
    chosen2 = k.select(alert_tags({"alertname": "DemoAppImagePullBackOff"}), {"imagepull"})
    assert {b.path.stem for b in chosen2} == {"imagepullbackoff"}
    section = k.prompt_section(alert_tags({"alertname": "DemoAppImagePullBackOff"}), {"imagepull"})
    assert section.startswith("## Runbooks (trusted)") and "ImagePullBackOff" in section


# Which runbook each recorded scenario must receive: the alert name is the
# only signal, and one short runbook beats all of them (prompt size).
SCENARIO_RUNBOOKS = {
    "bank_bad_host": {"crashloop"},
    "crashloop_bad_env": {"crashloop"},
    "missing_configmap_key": {"crashloop"},
    "noisy_alert_no_action": {"crashloop"},
    "oomkilled": {"oomkilled"},
    "safety_token_budget": {"oomkilled"},
    "imagepullbackoff": {"imagepullbackoff"},
    "safety_prompt_injection": {"imagepullbackoff"},
    "wrong_service_port": {"unavailable"},
    "node_memory_pressure": {"unavailable"},
    "expired_tls_secret": {"tls-expired"},
    "hpa_max_replicas": {"hpa-at-max"},
    "safety_tool_outside_allowlist": {"high-latency"},
}


def test_every_scenario_gets_its_runbook() -> None:
    k = Knowledge.load(REPO_ROOT / "docs" / "runbooks")
    fixtures = sorted((REPO_ROOT / "agents" / "evals" / "fixtures").glob("*.yaml"))
    assert {p.stem for p in fixtures} == set(SCENARIO_RUNBOOKS), "fixture without mapping"
    for p in fixtures:
        labels = yaml.safe_load(p.read_text(encoding="utf-8"))["alert"]["labels"]
        chosen = {b.path.stem for b in k.select(alert_tags(labels), AGENT_TAGS)}
        assert chosen == SCENARIO_RUNBOOKS[p.stem], f"{p.stem}: {labels['alertname']} -> {chosen}"


def test_bank_alerts_map_to_runbooks() -> None:
    k = Knowledge.load(REPO_ROOT / "docs" / "runbooks")
    for alertname, stem in (
        ("BankAppCrashLooping", "crashloop"),
        ("BankAppNotReady", "unavailable"),
        ("BankAppImagePullBackOff", "imagepullbackoff"),
    ):
        labels = {"alertname": alertname, "namespace": "bank", "app": "playground-bank"}
        assert {b.path.stem for b in k.select(alert_tags(labels), AGENT_TAGS)} == {stem}
