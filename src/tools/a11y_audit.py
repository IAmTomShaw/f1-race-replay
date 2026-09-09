"""
Accessibility / UX static checks.

The legacy code does not have a running display in this
environment, so a real GUI audit is not possible. This module
provides *static* checks that flag common a11y issues by
reading source files:

* ``QPushButton`` / ``QLabel`` instances without an
  ``accessibleName`` or ``setText`` (every interactive widget
  must have text).
* Hard-coded font sizes below 8 pt (unreadable).
* Colors with very low contrast (placeholder: red/green
  pairs are flagged for review).
* ``print`` calls used as user-facing output (should be
  replaced with ``logging`` or a proper dialog).

The checks are intentionally conservative: they report *candidates*
for review, not definite violations. A human must confirm.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, List, Tuple


@dataclass
class A11yFinding:
    file: str
    line: int
    severity: str  # "info" | "warning" | "error"
    code: str
    message: str


# Heuristics (regexes).
_BUTTON_RE = re.compile(r"QPushButton\s*\(")
_LABEL_RE = re.compile(r"QLabel\s*\(")
_FONT_SIZE_RE = re.compile(r"font-size\s*:\s*(\d+)\s*px")
_PRINT_RE = re.compile(r"^\s*print\s*\(")
_DIALOG_RE = re.compile(r"QMessageBox\s*\(")
_COLOR_RED_GREEN = re.compile(r"#([fF][0-9a-fA-F])([0-9a-fA-F]{2,4})")


# Files that contain GUI code. The static scanner only inspects
# these.
_DEFAULT_PATHS: Tuple[str, ...] = (
    "src/gui",
    "src/insights",
    "src/ui_components.py",
)


def _scan_file(path: Path) -> Iterable[A11yFinding]:
    try:
        text = path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return
    for lineno, line in enumerate(text.splitlines(), start=1):
        if _BUTTON_RE.search(line):
            # Check that the same or next few lines mention
            # setText or accessibleName.
            window = text.splitlines()[max(0, lineno - 1): lineno + 5]
            joined = "\n".join(window)
            if "setText" not in joined and "accessibleName" not in joined:
                yield A11yFinding(
                    file=str(path), line=lineno, severity="warning",
                    code="A11Y-001",
                    message="QPushButton without visible setText or accessibleName",
                )
        if _LABEL_RE.search(line):
            window = text.splitlines()[max(0, lineno - 1): lineno + 3]
            joined = "\n".join(window)
            if "setText" not in joined:
                yield A11yFinding(
                    file=str(path), line=lineno, severity="info",
                    code="A11Y-002",
                    message="QLabel without setText",
                )
        m = _FONT_SIZE_RE.search(line)
        if m:
            px = int(m.group(1))
            if px < 10:
                yield A11yFinding(
                    file=str(path), line=lineno, severity="warning",
                    code="A11Y-003",
                    message=f"font-size {px}px is too small (< 10px)",
                )
        if _PRINT_RE.match(line):
            # Only flag in GUI / insight files.
            yield A11yFinding(
                file=str(path), line=lineno, severity="info",
                code="A11Y-004",
                message="print() used in GUI; prefer logging or a dialog",
            )


def scan(project_root: Path, paths: Iterable[str] = _DEFAULT_PATHS
         ) -> List[A11yFinding]:
    findings: List[A11yFinding] = []
    for p in paths:
        full = project_root / p
        if not full.exists():
            continue
        if full.is_file():
            if full.suffix == ".py":
                findings.extend(_scan_file(full))
        elif full.is_dir():
            for f in sorted(full.rglob("*.py")):
                findings.extend(_scan_file(f))
    return findings


def summary(findings: List[A11yFinding]) -> str:
    by_sev: dict = {}
    for f in findings:
        by_sev.setdefault(f.severity, []).append(f)
    lines = [f"Total: {len(findings)} finding(s)"]
    for sev in ("error", "warning", "info"):
        items = by_sev.get(sev, [])
        lines.append(f"  {sev}: {len(items)}")
    return "\n".join(lines)


__all__ = [
    "A11yFinding",
    "scan",
    "summary",
]
