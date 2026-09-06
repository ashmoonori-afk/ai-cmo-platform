from dataclasses import replace
from pathlib import Path
from typing import Annotated

import typer

from aicmo.capabilities import find_mapping, load_capabilities
from aicmo.evaluate import evaluate_asset, render_report
from aicmo.export import export_local_pack
from aicmo.mockup import brief_from_answers, render_landing_mockup, render_pdf, render_png
from aicmo.onboarding import OnboardingResult, load_answers, scaffold_client
from aicmo.primer import render_primer_html
from aicmo.reporter import flush_kb_updates
from aicmo.store import WorkflowStore
from aicmo.web import run_server

from ._shared import console, default_db, make_runner


def emit_onboarding(result: OnboardingResult) -> None:
    console.print(f"onboarded {result.client}: {len(result.created)} files created")
    for path in result.created:
        console.print(f"  {path}")
    console.print(f"pdf: {result.pdf_status}")


def onboard_client(
    client: Annotated[str, typer.Option("--client", help="Client slug (folder under clients/)")],
    answers: Annotated[Path, typer.Option("--from", help="Path to the 7-answer JSON file")],
    repo: Annotated[Path, typer.Option("--repo")] = Path(),
    force: Annotated[bool, typer.Option("--force")] = False,
    date: Annotated[str | None, typer.Option("--date")] = None,
    pdf: Annotated[
        bool, typer.Option("--pdf/--no-pdf", help="Generate onboarding primer PDF")
    ] = True,
) -> None:
    loaded = load_answers(answers)
    loaded = replace(loaded, client=client, onboarding_date=date or loaded.onboarding_date)
    result = scaffold_client(repo.resolve(), loaded, force=force, pdf=pdf)
    emit_onboarding(result)


def serve_cmd(
    host: Annotated[str, typer.Option("--host")] = "127.0.0.1",
    port: Annotated[int, typer.Option("--port")] = 8765,
) -> None:
    console.print(f"AI CMO web: http://{host}:{port}  (Ctrl-C to stop)")
    run_server(host, port)


def mockup_cmd(
    source: Annotated[Path, typer.Option("--from", help="Onboarding answers JSON")],
    out: Annotated[Path, typer.Option("--out", help="HTML mockup output path")],
    png: Annotated[Path | None, typer.Option("--png", help="PNG via Playwright")] = None,
) -> None:
    brief = brief_from_answers(load_answers(source))
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render_landing_mockup(brief), encoding="utf-8")
    console.print(f"mockup: {out}")
    if png is not None:
        console.print(f"png: {render_png(out, png)}")


def primer_cmd(
    source: Annotated[Path, typer.Option("--from", help="Onboarding answers JSON")],
    out: Annotated[Path, typer.Option("--out", help="HTML primer output path")],
    pdf: Annotated[Path | None, typer.Option("--pdf", help="PDF output path")] = None,
) -> None:
    answers = load_answers(source)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render_primer_html(answers, date=answers.onboarding_date), encoding="utf-8")
    console.print(f"primer: {out}")
    if pdf is not None:
        console.print(f"pdf: {render_pdf(out, pdf)}")


def evaluate_cmd(
    source: Annotated[Path, typer.Option("--from", help="Asset markdown to score")],
    title: Annotated[str | None, typer.Option("--title")] = None,
    out: Annotated[Path | None, typer.Option("--out", help="Write scorecard markdown")] = None,
) -> None:
    result = evaluate_asset(source.read_text(encoding="utf-8"))
    console.print(f"score: {result.total}/100 — {result.band}")
    for dim in result.dimensions:
        console.print(f"  {dim.name}: {dim.score}/{dim.max}")
    if result.improvements:
        console.print("개선 우선순위 (낮은 점수 먼저):")
        for item in result.improvements:
            console.print(f"  - {item}")
    if out is not None:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(render_report(result, title or source.stem), encoding="utf-8")
        console.print(f"scorecard: {out}")


def kb_flush(
    client: Annotated[str | None, typer.Option("--client")] = None,
    repo: Annotated[Path, typer.Option("--repo")] = Path(),
    db: Annotated[Path | None, typer.Option("--db")] = None,
) -> None:
    repo_root = repo.resolve()
    store = WorkflowStore(db or default_db(repo_root))
    count = flush_kb_updates(repo_root, store, client)
    console.print(f"kb-flush: {count} queued update(s) appended to knowledge-base")


def capabilities_cmd(
    query: Annotated[
        str | None, typer.Argument(help="Natural-language query to match against mapping triggers.")
    ] = None,
    agents: Annotated[bool, typer.Option("--agents", help="List the 13 sub-agents.")] = False,
    as_json: Annotated[bool, typer.Option("--json", help="Machine-readable JSON output.")] = False,
    repo: Annotated[Path, typer.Option("--repo")] = Path(),
) -> None:
    registry = load_capabilities(repo.resolve())
    if query:
        matches = find_mapping(registry, query)
        if as_json:
            console.print_json(data=matches)
            return
        if not matches:
            console.print(f"no mapping matched: {query}")
            return
        for m in matches:
            target = m.get("playbook") or " -> ".join(m.get("chain", []))
            console.print(f"[{m['id']}] {target}")
            console.print(f"    agents: {m['agents']} | model: {m['model']}")
        return
    if agents:
        items = registry["agents"]
        if as_json:
            console.print_json(data=items)
            return
        for a in items:
            console.print(f"{a['name']} ({a['model']}) — {a['role']} [{a['path']}]")
        return
    console.print(
        f"agents: {len(registry['agents'])} | mappings: {len(registry['mappings'])}"
        f" | modules: {len(registry['modules'])}"
    )
    console.print('usage: aicmo capabilities "블로그" | --agents | --json')


def export_local_pack_cmd(
    run_id: Annotated[str, typer.Argument()],
    repo: Annotated[Path, typer.Option("--repo")] = Path(),
    db: Annotated[Path | None, typer.Option("--db")] = None,
) -> None:
    """Save an owner-approved, reviewer-passed local pack as a ZIP (no publishing)."""
    target = export_local_pack(make_runner(repo, db), run_id)
    console.print(str(target), markup=False)


def register(app: typer.Typer) -> None:
    app.command("onboard")(onboard_client)
    app.command("serve")(serve_cmd)
    app.command("primer")(primer_cmd)
    app.command("mockup")(mockup_cmd)
    app.command("evaluate")(evaluate_cmd)
    app.command("kb-flush")(kb_flush)
    app.command("capabilities")(capabilities_cmd)
    app.command("export-local-pack")(export_local_pack_cmd)
