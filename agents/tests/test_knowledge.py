import yaml

from runtime.knowledge import Knowledge, alert_tags

from .conftest import REPO_ROOT

RUNBOOKS = REPO_ROOT / "docs" / "runbooks"
AGENT_TAGS = set(
    yaml.safe_load((REPO_ROOT / "agents" / "incident_triage" / "manifest.yaml").read_text())[
        "knowledge_tags"
    ]
)
SECTIONS = {"rules", "crashloop", "oomkilled", "imagepull", "unavailable", "tls", "hpa", "latency"}

# Which section each recorded scenario must receive: the alert name is the
# only signal, and the rules plus one short section beat all of them.
SCENARIO_SECTIONS = {
    "bank_bad_host": {"crashloop"},
    "crashloop_bad_env": {"crashloop"},
    "missing_configmap_key": {"crashloop"},
    "noisy_alert_no_action": {"crashloop"},
    "oomkilled": {"oomkilled"},
    "safety_token_budget": {"oomkilled"},
    "imagepullbackoff": {"imagepull"},
    "safety_prompt_injection": {"imagepull"},
    "wrong_service_port": {"unavailable"},
    "node_memory_pressure": {"unavailable"},
    "expired_tls_secret": {"tls"},
    "hpa_max_replicas": {"hpa"},
    "safety_tool_outside_allowlist": {"latency"},
}


def test_one_file_loads_as_sections_with_tags() -> None:
    k = Knowledge.load(RUNBOOKS)
    assert {b.id for b in k.runbooks} == SECTIONS
    assert {b.path.name for b in k.runbooks} == {"incidents.md"}
    assert all("kubernetes" in b.tags for b in k.runbooks)  # the file's tags reach every section
    assert [b.id for b in k.runbooks if b.always] == ["rules"]
    assert all("<!--" not in b.body for b in k.runbooks)  # the marker is not sent to the model
    crash = next(b for b in k.runbooks if b.id == "crashloop")
    assert crash.title == "Crash loop" and {"crashloop", "restart"} <= crash.tags
    assert crash.body.startswith("**Alerts:**")


def test_alert_tags_from_labels() -> None:
    tags = alert_tags(
        {"alertname": "DemoAppImagePullBackOff", "namespace": "demo", "app": "demo-app"}
    )
    assert {"kubernetes", "demo", "demo-app", "imagepull"} <= tags
    assert "oom" not in tags


def test_selection_is_an_intersection() -> None:
    k = Knowledge.load(RUNBOOKS)
    agent_tags = {"kubernetes", "demo-app", "crashloop", "imagepull", "oom"}
    chosen = k.select(alert_tags({"alertname": "DemoAppOOMKilled", "app": "demo-app"}), agent_tags)
    assert {b.id for b in chosen} == {"oomkilled"}  # the specific keyword wins
    # an alert with no keyword match falls back to every section except the rules
    generic = k.select(
        alert_tags({"alertname": "DemoAppUnknownThing", "app": "demo-app"}), agent_tags
    )
    assert {b.id for b in generic} == SECTIONS - {"rules"}
    # an agent that only knows about imagepull does not get the OOM section for an imagepull alert
    chosen2 = k.select(alert_tags({"alertname": "DemoAppImagePullBackOff"}), {"imagepull"})
    assert {b.id for b in chosen2} == {"imagepull"}
    # an agent with no matching tag gets nothing, not even the rules
    assert k.prompt_section(alert_tags({"alertname": "DemoAppImagePullBackOff"}), {"nothing"}) == ""


def test_prompt_puts_the_rules_first() -> None:
    k = Knowledge.load(RUNBOOKS)
    section = k.prompt_section(alert_tags({"alertname": "DemoAppImagePullBackOff"}), {"imagepull"})
    assert section.startswith("## Runbooks (trusted)\n\n### Runbook: Rules for every incident")
    assert section.index("### Runbook: Image pull") > section.index("Rules for every incident")
    assert "### Runbook: Out of memory" not in section


def test_every_scenario_gets_its_section_and_a_short_prompt() -> None:
    k = Knowledge.load(RUNBOOKS)
    fixtures = sorted((REPO_ROOT / "agents" / "evals" / "fixtures").glob("*.yaml"))
    assert {p.stem for p in fixtures} == set(SCENARIO_SECTIONS), "fixture without mapping"
    for p in fixtures:
        labels = yaml.safe_load(p.read_text(encoding="utf-8"))["alert"]["labels"]
        chosen = {b.id for b in k.select(alert_tags(labels), AGENT_TAGS)}
        assert chosen == SCENARIO_SECTIONS[p.stem], f"{p.stem}: {labels['alertname']} -> {chosen}"
        # the rules plus one section: small enough for a 4B model's context
        assert len(k.prompt_section(alert_tags(labels), AGENT_TAGS)) < 8000, p.stem


def test_bank_alerts_map_to_sections() -> None:
    k = Knowledge.load(RUNBOOKS)
    for alertname, sid in (
        ("BankAppCrashLooping", "crashloop"),
        ("BankAppNotReady", "unavailable"),
        ("BankAppImagePullBackOff", "imagepull"),
    ):
        labels = {"alertname": alertname, "namespace": "bank", "app": "playground-bank"}
        assert {b.id for b in k.select(alert_tags(labels), AGENT_TAGS)} == {sid}


def test_old_single_topic_file_still_loads(tmp_path) -> None:
    (tmp_path / "thing.md").write_text(
        "---\ntitle: A thing\ntags: [kubernetes, oom]\n---\n\nBody text.\n", encoding="utf-8"
    )
    k = Knowledge.load(tmp_path)
    assert [(b.id, b.tags, b.body) for b in k.runbooks] == [
        ("thing", {"kubernetes", "oom"}, "Body text.")
    ]
