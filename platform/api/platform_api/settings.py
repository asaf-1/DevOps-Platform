"""Runtime settings, read once from the environment. No library, no magic."""

from __future__ import annotations

import os
from pathlib import Path

from pydantic import BaseModel, Field


def _repo_root_default() -> Path:
    # platform/api/platform_api/settings.py -> repo root is three levels up.
    return Path(__file__).resolve().parents[3]


def sqlalchemy_url(url: str) -> str:
    """CloudNativePG hands out postgresql://...; SQLAlchemy needs the psycopg dialect named."""
    for prefix in ("postgresql://", "postgres://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url[len(prefix) :]
    return url


class Settings(BaseModel):
    database_url: str = "sqlite:///./platform.db"
    repo_root: Path = Field(default_factory=_repo_root_default)
    catalog_dir: Path | None = None
    github_repo: str = "asaf-1/DevOps-Platform"
    github_token: str | None = None
    github_base_branch: str = "main"
    github_api_url: str = "https://api.github.com"
    default_environment: str = "local"
    # Apps the platform can smoke-test: name -> base URL inside the cluster.
    smoke_targets: dict[str, str] = Field(
        default_factory=lambda: {
            "bank": "http://agents-playground.bank.svc.cluster.local:4173",
            "demo-app": "http://demo-app.demo.svc.cluster.local",
        }
    )

    @classmethod
    def from_env(cls) -> Settings:
        env = os.environ
        return cls(
            database_url=sqlalchemy_url(
                env.get("DATABASE_URL", cls.model_fields["database_url"].default)
            ),
            repo_root=Path(env["REPO_ROOT"]) if env.get("REPO_ROOT") else _repo_root_default(),
            catalog_dir=Path(env["CATALOG_DIR"]) if env.get("CATALOG_DIR") else None,
            github_repo=env.get("GITHUB_REPO", cls.model_fields["github_repo"].default),
            github_token=env.get("PLATFORM_GITHUB_TOKEN") or None,
            github_base_branch=env.get("GITHUB_BASE_BRANCH", "main"),
            github_api_url=env.get("GITHUB_API_URL", "https://api.github.com"),
            default_environment=env.get("PLATFORM_ENVIRONMENT", "local"),
        )
