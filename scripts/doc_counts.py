import re
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_ROUTING_ROW = re.compile(r"^\| \d+ \|")


def _markdown_count(directory: Path) -> int:
    return sum(1 for path in directory.glob("*.md") if path.is_file())


def _routing_row_count() -> int:
    lines = (_ROOT / "CLAUDE.md").read_text(encoding="utf-8").splitlines()
    section_start = next(
        index for index, line in enumerate(lines) if line.startswith("## 3.")
    )
    section_end = next(
        index
        for index, line in enumerate(lines[section_start + 1 :], section_start + 1)
        if line.startswith("## 4")
    )
    return sum(1 for line in lines[section_start + 1 : section_end] if _ROUTING_ROW.match(line))


def _test_function_count() -> int:
    return sum(
        path.read_text(encoding="utf-8").count("def test_")
        for path in (_ROOT / "tests").glob("*.py")
        if path.is_file()
    )


def main() -> None:
    playbooks_root = _ROOT / "playbooks"
    playbook_rows = [
        (f"playbooks/{directory.name}", _markdown_count(directory))
        for directory in sorted(path for path in playbooks_root.iterdir() if path.is_dir())
    ]
    rows = [
        ("agents", _markdown_count(_ROOT / "agents")),
        *playbook_rows,
        ("playbooks total", sum(count for _, count in playbook_rows)),
        ("routing rows", _routing_row_count()),
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
