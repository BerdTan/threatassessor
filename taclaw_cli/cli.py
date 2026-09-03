"""
taclaw — ThreatAssessor CLI

Usage:
  ta analyze <path-or-url>
  ta gate --arch <name>
  ta export --arch <name>
  ta report --arch <name>
  ta enrich --arch <name> --component <label> --type <type> --id <id>
  ta archs
  ta status
  ta brain match --sig <signature> --type <arch-type>
  ta serve
  ta configure
"""

from __future__ import annotations

import json
import os
import sys
import time
import tomllib
from pathlib import Path
from typing import Optional

import httpx
import typer
from rich import print as rprint
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

app = typer.Typer(
    name="ta",
    help="ThreatAssessor CLI — secure-by-design threat intelligence at your fingertips.",
    no_args_is_help=True,
)
brain_app = typer.Typer(help="TA Brain query commands.")
app.add_typer(brain_app, name="brain")

console = Console()

_CONFIG_FILE = Path.home() / ".config" / "taclaw" / "config.toml"


# ── config ────────────────────────────────────────────────────────────────────

def _load_config() -> dict:
    cfg: dict = {}
    if _CONFIG_FILE.exists():
        try:
            cfg = tomllib.loads(_CONFIG_FILE.read_text())
        except Exception:
            pass
    return cfg


def _get_base_url(cfg: dict) -> str:
    return (
        os.environ.get("TA_API_BASE_URL")
        or cfg.get("base_url")
        or "http://localhost:8000"
    )


def _get_api_key(cfg: dict) -> str:
    return (
        os.environ.get("TA_API_KEY")
        or os.environ.get("API_KEY")
        or cfg.get("api_key")
        or ""
    )


def _headers(cfg: dict) -> dict:
    return {"TM-API-KEY": _get_api_key(cfg), "Content-Type": "application/json"}


def _client(cfg: dict) -> httpx.Client:
    return httpx.Client(base_url=_get_base_url(cfg), headers=_headers(cfg), timeout=120)


def _err(msg: str) -> None:
    rprint(f"[bold red]Error:[/bold red] {msg}")
    raise typer.Exit(1)


# ── configure ─────────────────────────────────────────────────────────────────

@app.command()
def configure():
    """Interactively set TA API base URL and API key."""
    cfg = _load_config()
    base = typer.prompt("TA API base URL", default=cfg.get("base_url", "http://localhost:8000"))
    key  = typer.prompt("TA API key", default=cfg.get("api_key", ""), hide_input=True)
    _CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    _CONFIG_FILE.write_text(f'base_url = "{base}"\napi_key = "{key}"\n')
    rprint(f"[green]Config saved to {_CONFIG_FILE}[/green]")


# ── status ────────────────────────────────────────────────────────────────────

@app.command()
def status():
    """Check if the TA API is running."""
    cfg = _load_config()
    try:
        with _client(cfg) as c:
            r = c.get("/health", timeout=5)
        if r.status_code == 200:
            rprint(f"[green]✓ API running[/green] at {_get_base_url(cfg)}")
        else:
            rprint(f"[yellow]API responded {r.status_code}[/yellow]")
    except Exception as exc:
        rprint(f"[red]✗ API unreachable:[/red] {exc}")
        rprint("  Start with: [bold]./scripts/api/api_start.sh[/bold]")
        raise typer.Exit(1)


# ── archs ─────────────────────────────────────────────────────────────────────

@app.command()
def archs():
    """List all analyzed architectures."""
    cfg = _load_config()
    with _client(cfg) as c:
        r = c.get("/api/v1/reports")
    r.raise_for_status()
    data = r.json()
    architectures = data if isinstance(data, list) else data.get("architectures", [])

    table = Table("Name", "Analysed at", "SSP Profile", "Files")
    for arch in architectures:
        table.add_row(
            arch.get("name", ""),
            arch.get("analysed_at", "")[:19].replace("T", " "),
            arch.get("ssp_profile", ""),
            str(arch.get("report_count", "")),
        )
    console.print(table)


# ── gate ──────────────────────────────────────────────────────────────────────

@app.command()
def gate(
    arch: str = typer.Option(..., "--arch", "-a", help="Architecture name"),
    fail_on: str = typer.Option("BLOCK", "--fail-on", help="Exit 1 when gate is BLOCK or higher severity"),
):
    """
    Check the gate result for an existing analysis.

    Exit code 0 = PASS, 1 = BLOCK. Use in CI:

        ta gate --arch my_service && deploy.sh
    """
    cfg = _load_config()
    with _client(cfg) as c:
        r = c.get(f"/api/v1/reports/{arch}/export")
    if r.status_code == 404:
        _err(f"No analysis found for '{arch}'. Run: ta analyze <path>")
    r.raise_for_status()
    bundle = r.json()
    gate_result = bundle.get("gate", {}).get("result", "UNKNOWN")
    risk = bundle.get("gate", {}).get("risk_level", "")
    signals = bundle.get("gate", {}).get("blocking_signals", [])

    color = "green" if gate_result == "PASS" else "red"
    rprint(f"[{color}]Gate: {gate_result}[/{color}]  Risk: {risk}  Arch: {arch}")
    if signals:
        rprint("Blocking signals:")
        for s in signals:
            rprint(f"  • {s}")

    if gate_result != "PASS":
        raise typer.Exit(1)


# ── report ────────────────────────────────────────────────────────────────────

@app.command()
def report(
    arch: str = typer.Option(..., "--arch", "-a", help="Architecture name"),
):
    """Pretty-print a threat assessment summary."""
    cfg = _load_config()
    with _client(cfg) as c:
        r = c.get(f"/api/v1/reports/{arch}/export")
    if r.status_code == 404:
        _err(f"No analysis found for '{arch}'. Run: ta analyze <path>")
    r.raise_for_status()
    bundle = r.json()

    gate_result = bundle.get("gate", {}).get("result", "?")
    risk = bundle.get("gate", {}).get("risk_level", "?")
    attack_paths = bundle.get("assessment", {}).get("attack_paths", [])
    tatb = bundle.get("tatb", {})
    gov = bundle.get("governance", {})

    color = "green" if gate_result == "PASS" else "red"
    panel_text = (
        f"Gate: [{color}]{gate_result}[/{color}]   Risk: {risk}\n"
        f"AIVSS: {gov.get('aivss_composite', 'N/A')}   "
        f"TATB overall: {tatb.get('overall', 'N/A')}"
    )
    rprint(Panel(panel_text, title=f"[bold]{arch}[/bold]"))

    if attack_paths:
        table = Table("Criticality", "Entry", "Target", "Techniques")
        for ap in attack_paths[:10]:
            table.add_row(
                ap.get("criticality") or "?",
                ap.get("entry", "")[:30],
                ap.get("target", "")[:30],
                ", ".join(ap.get("techniques", [])[:3]),
            )
        console.print(table)


# ── export ────────────────────────────────────────────────────────────────────

@app.command()
def export(
    arch: str = typer.Option(..., "--arch", "-a", help="Architecture name"),
    fmt: str = typer.Option("json", "--format", "-f", help="json | md"),
    save: bool = typer.Option(False, "--save", help="Also write ta_export.json to report dir"),
):
    """Export full TA bundle (ta-export/1.0) as JSON or Markdown briefing."""
    cfg = _load_config()
    if fmt == "md":
        with _client(cfg) as c:
            r = c.get(f"/api/v1/reports/{arch}/briefing")
        if r.status_code == 404:
            _err(f"No analysis found for '{arch}'.")
        r.raise_for_status()
        rprint(r.text)
    else:
        with _client(cfg) as c:
            r = c.get(f"/api/v1/reports/{arch}/export", params={"save": str(save).lower()})
        if r.status_code == 404:
            _err(f"No analysis found for '{arch}'.")
        r.raise_for_status()
        print(json.dumps(r.json(), indent=2))


# ── enrich ────────────────────────────────────────────────────────────────────

@app.command()
def enrich(
    arch: str = typer.Option(..., "--arch", "-a"),
    component: str = typer.Option(..., "--component", "-c", help="Component label from your scanner"),
    finding_type: str = typer.Option("other", "--type", "-t", help="cve | technique | vulnerability | other"),
    finding_id: str = typer.Option("", "--id", "-i", help="Finding ID (CVE-XXXX, T1190, …)"),
    severity: str = typer.Option("", "--severity", "-s"),
):
    """Enrich a SAST/VAPT finding with TA threat context for a specific component."""
    cfg = _load_config()
    payload = {
        "arch_name": arch,
        "component": component,
        "finding": {"type": finding_type, "id": finding_id or component, "severity": severity or None},
    }
    with _client(cfg) as c:
        r = c.post("/api/v1/enrich", json=payload)
    if r.status_code == 404:
        _err(f"No analysis found for '{arch}'. Run: ta analyze <path>")
    r.raise_for_status()
    data = r.json()

    rprint(f"\n[bold]Component:[/bold] {component}")
    rprint(f"[bold]Found:[/bold] {data.get('component_found')}  "
           f"[bold]Gate:[/bold] {data.get('ta_export_gate', 'N/A')}")
    rprint(f"\n[bold]Narrative:[/bold] {data.get('risk_narrative', '')}")

    paths = data.get("attack_paths_touching", [])
    if paths:
        table = Table("Criticality", "Entry", "Target", "Techniques")
        for ap in paths[:5]:
            table.add_row(
                ap.get("criticality") or "?",
                ap.get("entry", "")[:30],
                ap.get("target", "")[:30],
                ", ".join(ap.get("techniques", [])[:3]),
            )
        console.print(table)

    controls = data.get("controls_recommended", [])
    if controls:
        rprint("\n[bold]Controls:[/bold]")
        for c in controls[:5]:
            rprint(f"  • {c}")


# ── analyze ───────────────────────────────────────────────────────────────────

@app.command()
def analyze(
    target: str = typer.Argument(help="File path, directory, or git URL"),
    arch_name: Optional[str] = typer.Option(None, "--name", "-n", help="Override architecture name"),
    ssp_profile: str = typer.Option("low_risk_cloud", "--ssp"),
    wait: bool = typer.Option(True, "--wait/--no-wait", help="Wait for completion (TAclaw jobs)"),
):
    """
    Analyze any architecture artifact.

    Single file (.tf, .yaml, .mmd, .md) → POST /api/v1/analyze/artifact (SSE stream).
    Directory or git URL → POST /api/v1/taclaw/run (async job), poll until done.
    """
    cfg = _load_config()
    path = Path(target)
    is_url = target.startswith(("https://", "http://", "git@"))

    if is_url or (path.exists() and path.is_dir()):
        # TAclaw mode
        target_type = "git_url" if is_url else "directory"
        payload = {
            "target": target,
            "target_type": target_type,
            "ssp_profile": ssp_profile,
        }
        if arch_name:
            payload["arch_name"] = arch_name

        with _client(cfg) as c:
            r = c.post("/api/v1/taclaw/run", json=payload)
        if r.status_code not in (200, 201, 202):
            _err(f"TAclaw submission failed ({r.status_code}): {r.text[:200]}")
        job = r.json()
        job_id = job["job_id"]
        effective_arch = job.get("arch_name", arch_name or path.stem)

        rprint(f"[cyan]TAclaw job queued[/cyan] — job_id: {job_id}")
        if not wait:
            rprint(f"Poll with: ta analyze --no-wait  OR  curl .../api/v1/taclaw/jobs/{job_id}")
            return

        # Poll
        with console.status("[bold cyan]TAclaw running...[/bold cyan]") as spinner:
            while True:
                time.sleep(5)
                with _client(cfg) as c:
                    r = c.get(f"/api/v1/taclaw/jobs/{job_id}")
                job_status = r.json()
                pct = job_status.get("progress", 0)
                msg = job_status.get("message", "")
                spinner.update(f"[bold cyan]{pct}%[/bold cyan] {msg}")
                if job_status.get("status") in ("completed", "failed"):
                    break

        if job_status.get("status") == "failed":
            _err(f"TAclaw failed: {job_status.get('error', 'unknown error')}")

        result = job_status.get("result", {})
        gate = result.get("gate", "?")
        color = "green" if gate == "PASS" else "red"
        rprint(f"\n[{color}]Gate: {gate}[/{color}]  Arch: {effective_arch}")
        rprint(f"Artifacts: {result.get('artifacts_found', '?')} found, "
               f"{result.get('graphs_merged', '?')} graphs merged → "
               f"{result.get('composite_nodes', '?')} nodes, {result.get('composite_edges', '?')} edges")
        rprint(f"Formats: {', '.join(result.get('source_formats', []))}")

    else:
        # Single file mode → POST /api/v1/analyze/artifact (SSE stream)
        if not path.exists():
            _err(f"File not found: {target}")

        effective_arch = arch_name or path.stem
        rprint(f"[cyan]Analyzing {path.name}[/cyan] as '{effective_arch}'...")

        files = {"artifact_file": (path.name, path.read_bytes())}
        data = {"ssp_profile": ssp_profile, "arch_name": effective_arch}

        # Stream SSE — consume until 'complete' event
        with httpx.Client(
            base_url=_get_base_url(cfg),
            headers={k: v for k, v in _headers(cfg).items() if k != "Content-Type"},
            timeout=180,
        ) as c:
            with c.stream("POST", "/api/v1/analyze/artifact", files=files, data=data) as resp:
                resp.raise_for_status()
                final_data = None
                for line in resp.iter_lines():
                    if line.startswith("event: complete"):
                        pass
                    elif line.startswith("data: ") and final_data is None:
                        # This may be the progress data; we want the 'complete' data
                        try:
                            parsed = json.loads(line[6:])
                            # complete event has 'confidence' or 'attack_paths'
                            if "confidence" in parsed or "attack_paths" in parsed:
                                final_data = parsed
                        except json.JSONDecodeError:
                            pass
                    elif line.startswith("data: ") and line[6:].strip().startswith("{"):
                        try:
                            parsed = json.loads(line[6:])
                            if "confidence" in parsed or "attack_paths" in parsed:
                                final_data = parsed
                        except json.JSONDecodeError:
                            pass

        if final_data:
            conf = final_data.get("confidence", final_data.get("confidence_breakdown", {}).get("final", "?"))
            aps = len(final_data.get("expected_attack_paths", []) or final_data.get("attack_paths", []))
            rprint(f"[green]Analysis complete[/green] — confidence: {conf}, attack paths: {aps}")
            rprint(f"View report: ta report --arch {effective_arch}")
        else:
            rprint(f"[yellow]Analysis submitted[/yellow] — view with: ta report --arch {effective_arch}")


# ── brain match ───────────────────────────────────────────────────────────────

@brain_app.command("match")
def brain_match(
    sig: str = typer.Option("", "--sig", "-s", help="Topology signature (free text)"),
    arch_type: str = typer.Option("", "--type", "-t", help="Architecture type (cloud, web_app, ai_system, …)"),
    components: Optional[str] = typer.Option(None, "--components", "-c", help="Comma-separated component labels"),
):
    """Query the TA Brain for threat patterns matching a topology signature."""
    cfg = _load_config()
    payload = {
        "topology_signature": sig,
        "arch_type": arch_type,
        "component_labels": [c.strip() for c in (components or "").split(",") if c.strip()],
    }
    with _client(cfg) as c:
        r = c.post("/api/v1/brain/match", json=payload)
    r.raise_for_status()
    data = r.json()
    matched = data.get("matched_patterns", {})
    rprint(Panel(
        f"Match: [bold]{matched.get('had_match', False)}[/bold]   "
        f"Confidence: {matched.get('confidence', 'N/A')}\n"
        f"Techniques: {', '.join((matched.get('techniques') or [])[:5])}\n"
        f"AIVSS floor: {matched.get('aivss_floor', 'N/A')}",
        title="Brain Match",
    ))


# ── serve ─────────────────────────────────────────────────────────────────────

@app.command()
def serve():
    """Start the TA API server (wraps ./scripts/api/api_start.sh)."""
    import subprocess
    script = Path("scripts/api/api_start.sh")
    if not script.exists():
        _err("api_start.sh not found. Are you in the ThreatAssessor project root?")
    subprocess.run(["bash", str(script)], check=True)


# ── main ──────────────────────────────────────────────────────────────────────

def main():
    app()


if __name__ == "__main__":
    main()
