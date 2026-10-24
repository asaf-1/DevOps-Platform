from runtime.knowledge import Knowledge, alert_tags

from .conftest import REPO_ROOT


def test_runbooks_load_with_tags() -> None:
    k = Knowledge.load(REPO_ROOT / "docs" / "runbooks")
    titles = {b.path.stem for b in k.runbooks}
    assert {"imagepullbackoff", "oomkilled", "crashloop"} <= titles
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
    # an agent that only knows about imagepull does not get the OOM runbook for an imagepull alert
    chosen2 = k.select(alert_tags({"alertname": "DemoAppImagePullBackOff"}), {"imagepull"})
    assert {b.path.stem for b in chosen2} == {"imagepullbackoff"}
    section = k.prompt_section(alert_tags({"alertname": "DemoAppImagePullBackOff"}), {"imagepull"})
    assert section.startswith("## Runbooks (trusted)") and "ImagePullBackOff" in section
