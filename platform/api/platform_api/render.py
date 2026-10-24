"""Render a request into its one Terraform file (ADR 0005: one file per request)."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, StrictUndefined

from .catalog import Catalog

_IDENT_BAD = re.compile(r"[^a-z0-9_-]")


def tf_ident(value: Any) -> str:
    """Make a safe Terraform identifier (module and output names)."""
    s = _IDENT_BAD.sub("_", str(value).lower())
    if not s or not (s[0].isalpha() or s[0] == "_"):
        s = f"r_{s}"
    return s


def tf_string(value: Any) -> str:
    """Render an optional string input: null, or a quoted HCL string."""
    if value is None:
        return "null"
    s = str(value).replace("\\", "\\\\").replace('"', '\\"')
    return f'"{s}"'


def request_file_path(repo_root: Path, environment: str, request_id: str) -> Path:
    return (
        repo_root / "infra" / "terraform" / "envs" / environment / "requests" / f"{request_id}.tf"
    )


class Renderer:
    """Jinja2 over the catalog's request.tf.j2 templates. Undefined values are errors."""

    def __init__(self, catalog: Catalog) -> None:
        self.catalog = catalog
        self.env = Environment(
            loader=FileSystemLoader(str(catalog.root)),
            undefined=StrictUndefined,
            autoescape=False,
            keep_trailing_newline=True,
            trim_blocks=True,
            lstrip_blocks=True,
        )
        self.env.filters["tf_ident"] = tf_ident
        self.env.filters["tf_string"] = tf_string

    def render(self, type_name: str, request_id: str, inputs: dict[str, Any]) -> str:
        """Validate inputs against the type's schema, then render. Returns the .tf text."""
        filled = self.catalog.validate_inputs(type_name, inputs)
        template = self.env.get_template(f"{type_name}/request.tf.j2")
        text = template.render(request={"id": request_id}, inputs=filled, type=type_name)
        return text if text.endswith("\n") else text + "\n"
