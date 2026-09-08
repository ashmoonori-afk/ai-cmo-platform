from dataclasses import replace
from pathlib import Path
from typing import Annotated

import typer
from rich.table import Table

from aicmo.capabilities import find_mapping, load_capabilities
from aicmo.evaluate import evaluate_asset, render_report
from aicmo.export import export_local_pack
from aicmo.learning import learn_feedback
from aicmo.mockup import brief_from_answers, render_landing_mockup, render_pdf, render_png
from aicmo.onboarding import OnboardingResult, load_answers, scaffold_client
from aicmo.outcomes import METRICS, import_outcomes, parse_channel, preview_outcomes
from aicmo.paths import parse_safe_id, resolve_inside_repo
from aicmo.photos import photo_preview
from aicmo.primer import render_primer_html
from aicmo.reporter import flush_kb_updates
from aicmo.store import WorkflowStore
from aicmo.web import run_server

from ._shared import console, default_db, make_runner


def photo_preview_cmd(
    run_id: Annotated[str, typer.Argument()],
    repo: Annotated[Path, typer.Option("--repo")] = Path(),
    db: Annotated[Path | None, typer.Option("--db")] = None,
) -> None:
    parse_safe_id("run_id", run_id)
    runner = make_runner(repo.resolve(), db)
    runner.store.initialize()
    runner.verified_photos(run_id)
    html = photo_preview(runner.repo_root, runner.store.get_inputs(run_id))
    target = resolve_inside_repo(runner.repo_root, f"artifacts/{run_id}/photo-preview.html", {})
    target.write_text(html, encoding="utf-8")
    console.print(str(target), markup=False)


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


def learn_feedback_cmd(
    run_id: Annotated[str, typer.Argument(help="Owner-approved and reviewer-passed feedback run")],
    repo: Annotated[Path, typer.Option("--repo")] = Path(),
    db: Annotated[Path | None, typer.Option("--db")] = None,
) -> None:
    runner = make_runner(repo, db)
    target = learn_feedback(runner, run_id)
    console.print(f"approved feedback: {target.relative_to(repo.resolve())}")


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


def outcomes_cmd(
    client: Annotated[str, typer.Option("--client")],
    week_start: Annotated[str, typer.Option("--week-start")],
    source: Annotated[Path, typer.Option("--from", help="Daily counts CSV (UTF-8)")],
    channel: Annotated[str, typer.Option("--channel")] = "naver",
    confirm_sha: Annotated[str | None, typer.Option("--confirm-sha")] = None,
    replace_existing: Annotated[bool, typer.Option("--replace")] = False,
    as_json: Annotated[bool, typer.Option("--json")] = False,
    repo: Annotated[Path, typer.Option("--repo")] = Path(),
    db: Annotated[Path | None, typer.Option("--db")] = None,
) -> None:
    """Preview daily outcomes, then import the confirmed file and database version."""
    root = repo.resolve()
    store = WorkflowStore(db or default_db(root))
    selected = parse_channel(channel)
    if confirm_sha is not None:
        changed = import_outcomes(
            root,
            store,
            client,
            week_start,
            selected,
            source,
            confirm_sha,
            replace=replace_existing,
        )
        console.print(f"outcomes: {changed} daily row(s) saved; unchanged rows preserved")
        return
    preview = preview_outcomes(root, store, client, week_start, selected, source)
    if as_json:
        console.print_json(
            data={
                **preview.model_dump(),
                "confirmation_sha256": preview.confirmation_sha256,
            }
        )
        return
    console.print(f"{client} / {week_start} Monday + 7 days / {channel} / {preview.encoding}")
    table = Table("날짜", "구분", "게시", "문의", "예약", "쿠폰")
    previous = {row.date: row for row in preview.existing}
    for row in preview.rows:
        old = previous.get(row.date)
        for record, label in ((old, "기존"), (row, "입력")):
            if record is not None:
                table.add_row(
                    record.date,
                    label,
                    *[
                        "미입력"
                        if getattr(record, metric) is None
                        else str(getattr(record, metric))
                        for metric in METRICS
                    ],
                )
    console.print(table)
    console.print(
        "Preview only. Empty = unknown; 0 = observed zero. Changed values need --replace."
    )
    console.print(f"source_sha256: {preview.source_sha256}", soft_wrap=True)
    console.print(f"confirmation_sha256: {preview.confirmation_sha256}", soft_wrap=True)


def register(app: typer.Typer) -> None:
    app.command("photo-preview")(photo_preview_cmd)
    app.command("learn-feedback")(learn_feedback_cmd)
    app.command("outcomes")(outcomes_cmd)
    app.command("onboard")(onboard_client)
    app.command("serve")(serve_cmd)
    app.command("primer")(primer_cmd)
    app.command("mockup")(mockup_cmd)
    app.command("evaluate")(evaluate_cmd)
    app.command("kb-flush")(kb_flush)
    app.command("capabilities")(capabilities_cmd)
    app.command("export-local-pack")(export_local_pack_cmd)
