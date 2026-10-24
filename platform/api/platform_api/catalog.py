"""Load the resource catalog from platform/catalog and validate request inputs."""

from __future__ import annotations

import copy
import json
import os
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator

from .models import CatalogType

REQUIRED_FILES = ("type.yaml", "schema.json", "request.tf.j2")


class CatalogError(ValueError):
    """Catalog is malformed or a request does not fit a type."""


def default_catalog_dir() -> Path:
    """CATALOG_DIR if set, else platform/catalog next to this package's repo root."""
    env = os.environ.get("CATALOG_DIR")
    if env:
        return Path(env)
    return Path(__file__).resolve().parents[2] / "catalog"


class Catalog:
    """All resource types, loaded once from disk."""

    def __init__(self, root: Path | None = None) -> None:
        self.root = (root or default_catalog_dir()).resolve()
        self.types: dict[str, CatalogType] = {}
        self._validators: dict[str, Draft202012Validator] = {}
        self._load()

    def _load(self) -> None:
        if not self.root.is_dir():
            raise CatalogError(f"catalog directory not found: {self.root}")
        for folder in sorted(p for p in self.root.iterdir() if p.is_dir()):
            missing = [f for f in REQUIRED_FILES if not (folder / f).is_file()]
            if missing:
                raise CatalogError(f"{folder.name}: missing {', '.join(missing)}")
            meta = yaml.safe_load((folder / "type.yaml").read_text(encoding="utf-8")) or {}
            schema = json.loads((folder / "schema.json").read_text(encoding="utf-8"))
            Draft202012Validator.check_schema(schema)
            readme_path = folder / "README.md"
            readme = readme_path.read_text(encoding="utf-8") if readme_path.is_file() else ""
            ctype = CatalogType(**meta, schema=schema, readme=readme)
            if ctype.type != folder.name:
                raise CatalogError(f"{folder.name}: type.yaml says type={ctype.type!r}")
            self.types[ctype.type] = ctype
            self._validators[ctype.type] = Draft202012Validator(schema)

    def get(self, type_name: str) -> CatalogType:
        try:
            return self.types[type_name]
        except KeyError:
            raise CatalogError(f"unknown resource type {type_name!r}") from None

    def template_path(self, type_name: str) -> Path:
        self.get(type_name)
        return self.root / type_name / "request.tf.j2"

    def validate_inputs(self, type_name: str, inputs: dict[str, Any]) -> dict[str, Any]:
        """Return the inputs with schema defaults filled in, or raise CatalogError.

        jsonschema does not apply defaults, so top-level property defaults are
        filled here before validation. Nested defaults are not needed by the
        catalog as it stands.
        """
        ctype = self.get(type_name)
        filled = copy.deepcopy(inputs)
        for key, prop in ctype.input_schema.get("properties", {}).items():
            if key not in filled and "default" in prop:
                filled[key] = prop["default"]
        errors = sorted(self._validators[type_name].iter_errors(filled), key=lambda e: list(e.path))
        if errors:
            msgs = [f"{'/'.join(str(p) for p in e.path) or '<root>'}: {e.message}" for e in errors]
            raise CatalogError(f"invalid inputs for {type_name}: " + "; ".join(msgs))
        return filled
