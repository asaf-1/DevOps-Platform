"""The `platform` command.

    platform catalog list
    platform catalog show s3-bucket
    platform request s3-bucket --name demo-uploads --team web --cost-center cc-100
    platform request dynamodb-table --name orders --team web --cost-center cc-100 \
        -i hash_key=order_id
    platform status <request-id>
    platform audit --request <request-id>

Talks to the API over HTTP (PLATFORM_API_URL, default http://localhost:8000).
"""

from __future__ import annotations

import getpass
import json
import os
from typing import Annotated, Any

import typer

from . import __version__
from .client import ApiClient, ApiError

app = typer.Typer(
    help="Request cloud and Kubernetes resources from the platform catalog.",
    no_args_is_help=True,
    add_completion=False,
)
catalog_app = typer.Typer(help="Browse the resource catalog.", no_args_is_help=True)
app.add_typer(catalog_app, name="catalog")

_client_factory = ApiClient


def set_client_factory(factory) -> None:  # tests inject a client with a mock transport
    global _client_factory
    _client_factory = factory


def _client() -> ApiClient:
    return _client_factory()


def _fail(message: str) -> None:
    typer.secho(f"error: {message}", fg=typer.colors.RED, err=True)
    raise typer.Exit(code=1)


def _parse_value(raw: str) -> Any:
    """`-i key=value`: JSON when it parses (true, 5, null), else a plain string."""
    try:
        return json.loads(raw)
    except ValueError:
        return raw


@app.callback()
def _root(
    version: Annotated[bool, typer.Option("--version", help="Print the version and exit.")] = False,
) -> None:
    if version:
        typer.echo(f"platform {__version__}")
        raise typer.Exit()


@catalog_app.command("list")
def catalog_list() -> None:
    """List the resource types you can request."""
    try:
        types = _client().catalog()
    except ApiError as e:
        _fail(str(e))
    typer.echo(f"{'TYPE':<18}{'PROVIDER':<12}{'APPROVAL':<10}DESCRIPTION")
    for t in types:
        approval = "required" if t["approval_required"] else "none"
        typer.echo(f"{t['type']:<18}{t['provider']:<12}{approval:<10}{t['description']}")


@catalog_app.command("show")
def catalog_show(
    type_name: Annotated[str, typer.Argument(help="Resource type, e.g. s3-bucket")],
) -> None:
    """Show a type's inputs and docs."""
    try:
        t = _client().catalog_type(type_name)
    except ApiError as e:
        _fail(str(e))
    typer.echo(f"{t['display_name']} ({t['type']}), module {t['module']}, owner {t['owner_team']}")
    typer.echo(
        f"environments: {', '.join(t['environments'])}; approval required: {t['approval_required']}"
    )
    typer.echo("\ninputs:")
    schema = t["schema"]
    required = set(schema.get("required", []))
    for name, prop in schema.get("properties", {}).items():
        flag = "required" if name in required else f"default {prop.get('default')!r}"
        enum = f" one of {', '.join(map(str, prop['enum']))}" if "enum" in prop else ""
        typer.echo(f"  {name:<24}{flag}{enum}")
        if prop.get("description"):
            typer.echo(f"  {'':<24}{prop['description']}")


@app.command("request")
def request_cmd(
    type_name: Annotated[str, typer.Argument(metavar="TYPE", help="Resource type, e.g. s3-bucket")],
    name: Annotated[str, typer.Option("--name", help="Resource name")],
    team: Annotated[str, typer.Option("--team", help="Owning team")],
    cost_center: Annotated[str, typer.Option("--cost-center", help="Cost center")],
    size: Annotated[str | None, typer.Option("--size", help="small, medium or large")] = None,
    inputs: Annotated[
        list[str] | None,
        typer.Option("--input", "-i", help="Extra input as key=value (JSON values allowed)."),
    ] = None,
    environment: Annotated[str, typer.Option("--env", help="Target environment")] = "local",
    requested_by: Annotated[
        str | None, typer.Option("--as", help="Requester (default: your user name)")
    ] = None,
) -> None:
    """Request a resource. Opens a pull request; prints the request id and the PR."""
    payload: dict[str, Any] = {"name": name, "team": team, "cost_center": cost_center}
    if size:
        payload["size"] = size
    for raw in inputs or []:
        if "=" not in raw:
            _fail(f"--input expects key=value, got {raw!r}")
        key, value = raw.split("=", 1)
        payload[key] = _parse_value(value)
    who = requested_by or os.environ.get("PLATFORM_USER") or getpass.getuser()
    try:
        req = _client().create_request(type_name, payload, who, environment)
    except ApiError as e:
        _fail(str(e))
    typer.echo(f"request {req['id']}: {req['type']} {req['inputs'].get('name')} -> {req['state']}")
    if req.get("pr_url"):
        typer.echo(f"pull request: {req['pr_url']}")
    if req.get("error"):
        typer.secho(f"error: {req['error']}", fg=typer.colors.RED)
        raise typer.Exit(code=2)
    typer.echo(f"follow it with: platform status {req['id']}")


@app.command("status")
def status_cmd(
    request_id: Annotated[str, typer.Argument(help="Request id, e.g. r-3f9a1c")],
) -> None:
    """Show a request and its timeline."""
    try:
        req = _client().request(request_id)
        events = _client().audit(request_id)
    except ApiError as e:
        _fail(str(e))
    typer.echo(f"{req['id']}  {req['type']}  {req['inputs'].get('name')}  env {req['environment']}")
    typer.echo(f"state: {req['state']}   requested by {req['requested_by']}")
    if req.get("pr_url"):
        typer.echo(f"pull request: {req['pr_url']}")
    if req.get("outputs"):
        typer.echo("outputs: " + json.dumps(req["outputs"], sort_keys=True))
    if req.get("error"):
        typer.secho(f"error: {req['error']}", fg=typer.colors.RED)
    typer.echo("\ntimeline:")
    _print_timeline(events)


@app.command("list")
def list_cmd(
    state: Annotated[str | None, typer.Option("--state", help="Filter by state")] = None,
) -> None:
    """List requests, newest first."""
    try:
        reqs = _client().requests(state)
    except ApiError as e:
        _fail(str(e))
    typer.echo(f"{'ID':<12}{'TYPE':<18}{'NAME':<24}{'STATE':<12}REQUESTED BY")
    for r in reqs:
        typer.echo(
            f"{r['id']:<12}{r['type']:<18}{str(r['inputs'].get('name')):<24}{r['state']:<12}{r['requested_by']}"
        )


@app.command("audit")
def audit_cmd(
    request_id: Annotated[str | None, typer.Option("--request", help="Only this request")] = None,
) -> None:
    """Show the audit trail: who did what, when."""
    try:
        events = _client().audit(request_id)
    except ApiError as e:
        _fail(str(e))
    _print_timeline(events)


def _print_timeline(events: list[dict[str, Any]]) -> None:
    if not events:
        typer.echo("  (no events)")
        return
    for e in events:
        at = str(e["at"])[:19].replace("T", " ")
        who = f"{e['actor']} ({e['actor_type']})"
        detail = ""
        if e.get("details"):
            short = {
                k: v
                for k, v in e["details"].items()
                if k in ("pr_url", "reason", "outputs", "path")
            }
            if short:
                detail = "  " + json.dumps(short, sort_keys=True)
        rid = f"{e['request_id']}  " if e.get("request_id") else ""
        typer.echo(f"  {at}  {rid}{e['event']:<12}{who}{detail}")


if __name__ == "__main__":
    app()
