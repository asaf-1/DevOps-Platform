"""Runbooks for the system prompt: docs/runbooks/*.md, one section per alert family.

A runbook file has front-matter (title, default tags) and `## ` sections.
The HTML comment right under a heading carries the section's id and tags:

    ## Crash loop
    <!-- id: crashloop; tags: crashloop, restart -->

A section tagged `always` (the rules) goes into every prompt that gets a
runbook at all. The other sections are chosen by a tag intersection
between the section's tags and the tags derived from the alert (its labels
plus keywords from the alert name), restricted to the agent's
`knowledge_tags`. No vector database: the runbooks are few, short and
trusted. A file without `## ` headings is one section (the old format).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

_FRONT_MATTER = re.compile(r"\A---\s*\n(.*?)\n---\s*\n", re.S)
_HEADING = re.compile(r"^## +(.+?)\s*$", re.M)
_MARKER = re.compile(r"^<!--\s*id:\s*([A-Za-z0-9_-]+)\s*;\s*tags:\s*([^>]*?)\s*-->[ \t]*\n?", re.M)

ALWAYS = "always"

# Words in an alert name that map to runbook tags.
KEYWORDS = {
    "imagepull": "imagepull",
    "errimagepull": "imagepull",
    "oom": "oom",
    "crashloop": "crashloop",
    "restart": "crashloop",
    "unavailable": "unavailable",
    "notready": "unavailable",
    "tls": "tls",
    "cert": "tls",
    "hpa": "hpa",
    "latency": "latency",
}


@dataclass
class Runbook:
    """One section of a runbook file: what the prompt receives."""

    path: Path
    id: str
    title: str
    tags: set[str]
    body: str

    @property
    def always(self) -> bool:
        return ALWAYS in self.tags


def _sections(path: Path, body: str, file_tags: set[str]) -> list[Runbook]:
    heads = list(_HEADING.finditer(body))
    if not heads:
        return [Runbook(path, path.stem, path.stem, set(file_tags), body.strip())]
    out: list[Runbook] = []
    for i, h in enumerate(heads):
        end = heads[i + 1].start() if i + 1 < len(heads) else len(body)
        text = body[h.end() : end]
        title = h.group(1).strip()
        marker = _MARKER.search(text[:400])
        if marker:
            sid = marker.group(1)
            tags = {t.strip().lower() for t in marker.group(2).split(",") if t.strip()}
            text = text[: marker.start()] + text[marker.end() :]
        else:
            sid = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
            tags = set()
        out.append(Runbook(path, sid, title, tags | file_tags, text.strip()))
    return out


@dataclass
class Knowledge:
    runbooks: list[Runbook] = field(default_factory=list)

    @classmethod
    def load(cls, directory: Path) -> Knowledge:
        books: list[Runbook] = []
        for p in sorted(directory.glob("*.md")):
            text = p.read_text(encoding="utf-8")
            m = _FRONT_MATTER.match(text)
            meta: dict[str, Any] = (yaml.safe_load(m.group(1)) or {}) if m else {}
            body = text[m.end() :] if m else text
            file_tags = {str(t).lower() for t in meta.get("tags", [])}
            books.extend(_sections(p, body, file_tags))
        return cls(books)

    def select(self, alert_tags: set[str], agent_tags: set[str]) -> list[Runbook]:
        """Sections for this alert, restricted to the agent's tags.

        Specific tags (the keyword derived from the alert name, e.g.
        imagepull) win; generic tags (kubernetes, the app name) are only a
        fallback. Otherwise every section would be sent and the prompt
        would grow by thousands of tokens. The always-sections (the rules)
        are not selected here; prompt_section puts them first.
        """
        candidates = [b for b in self.runbooks if not b.always]
        wanted = {t.lower() for t in alert_tags} & {t.lower() for t in agent_tags}
        if not wanted:
            return []
        specific = wanted & set(KEYWORDS.values())
        if specific:
            hits = [b for b in candidates if b.tags & specific]
            if hits:
                return hits
        return [b for b in candidates if b.tags & wanted]

    def prompt_section(self, alert_tags: set[str], agent_tags: set[str]) -> str:
        chosen = self.select(alert_tags, agent_tags)
        if not chosen:
            return ""
        rules = [b for b in self.runbooks if b.always]
        parts = [f"### Runbook: {b.title}\n{b.body}" for b in rules + chosen]
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
