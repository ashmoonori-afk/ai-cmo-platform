from pathlib import Path

from aicmo.capabilities import load_capabilities

_ROOT = Path(__file__).resolve().parents[1]


def _markdown_count(directory: Path) -> int:
    return sum(1 for path in directory.glob("*.md") if path.is_file())


def _test_function_count() -> int:
    return sum(
        path.read_text(encoding="utf-8").count("def test_")
        for path in (_ROOT / "tests").glob("*.py")
        if path.is_file()
    )


def main() -> None:
    registry = load_capabilities(_ROOT)
    playbooks_root = _ROOT / "playbooks"
    playbook_rows = [
        (f"playbooks/{directory.name}", _markdown_count(directory))
        for directory in sorted(path for path in playbooks_root.iterdir() if path.is_dir())
    ]
    rows = [
        ("agents (registry)", len(registry["agents"])),
        ("agents (files)", _markdown_count(_ROOT / "agents")),
        *playbook_rows,
        ("playbooks total", sum(count for _, count in playbook_rows)),
        ("capability mappings", len(registry["mappings"])),
        ("executable workflows", len(list((_ROOT / "workflows").glob("*.workflow.yaml")))),
        ("shared prompts", _markdown_count(_ROOT / "prompts" / "shared")),
        ("test functions", _test_function_count()),
    ]
    label_width = max(len(label) for label, _ in rows)

    print(f"{'surface':<{label_width}}  count")
    print(f"{'-' * label_width}  -----")
    for label, count in rows:
        print(f"{label:<{label_width}}  {count:>5}")


if __name__ == "__main__":
    main()
