"""Runbooks for the system prompt: docs/runbooks/*.md with front-matter tags.

Selection is a tag intersection between the runbook's tags and the tags
derived from the alert (its labels plus a few keywords from the alert
name). No vector database: the runbooks are few, short and trusted.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

_FRONT_MATTER = re.compile(r"\A---\s*\n(.*?)\n---\s*\n", re.S)

# Words in an alert name that map to runbook tags.
KEYWORDS = {
    "imagepull": "imagepull",
    "errimagepull": "imagepull",
    "oom": "oom",
    "crashloop": "crashloop",
    "restart": "crashloop",
    "unavailable": "crashloop",
}


@dataclass
class Runbook:
    path: Path
    title: str
    tags: set[str]
    body: str


@dataclass
class Knowledge:
    runbooks: list[Runbook] = field(default_factory=list)

    @classmethod
    def load(cls, directory: Path) -> Knowledge:
        books: list[Runbook] = []
        for p in sorted(directory.glob("*.md")):
            text = p.read_text(encoding="utf-8")
            m = _FRONT_MATTER.match(text)
            meta: dict[str, Any] = yaml.safe_load(m.group(1)) or {} if m else {}
            body = text[m.end() :] if m else text
            tags = {str(t).lower() for t in meta.get("tags", [])}
            books.append(Runbook(p, str(meta.get("title", p.stem)), tags, body.strip()))
        return cls(books)

    def select(self, alert_tags: set[str], agent_tags: set[str]) -> list[Runbook]:
        """Runbooks whose tags intersect the alert's tags, restricted to the agent's tags."""
        wanted = {t.lower() for t in alert_tags} & {t.lower() for t in agent_tags}
        if not wanted:
            return []
        return [b for b in self.runbooks if b.tags & wanted]

    def prompt_section(self, alert_tags: set[str], agent_tags: set[str]) -> str:
        chosen = self.select(alert_tags, agent_tags)
        if not chosen:
            return ""
        parts = [f"### Runbook: {b.title}\n{b.body}" for b in chosen]
        return "## Runbooks (trusted)\n\n" + "\n\n".join(parts)


def alert_tags(labels: dict[str, str]) -> set[str]:
    """Tags for an alert: its app/namespace labels plus keywords from the alert name."""
    tags: set[str] = {"kubernetes"}
    for key in ("app", "namespace", "container", "deployment"):
        if labels.get(key):
            tags.add(str(labels[key]).lower())
    name = str(labels.get("alertname", "")).lower()
    for word, tag in KEYWORDS.items():
        if word in name:
            tags.add(tag)
    return tags
