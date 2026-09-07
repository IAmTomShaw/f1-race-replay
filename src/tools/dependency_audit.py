"""
Dependency metadata audit.

This module is a *metadata-only* audit: it parses
``requirements.txt`` and reports pin-style / version-style /
known-bad combinations. It does NOT install or upgrade anything.

The audit produces a ``DependencyReport`` that the ``--diagnostics``
CLI subcommand (PHASE 21) can print to help users troubleshoot
"why does my install not work" without touching their environment.
"""
from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple


# Lines that look like ``package==1.2.3`` or ``package>=1.2``.
_PIN_RE = re.compile(
    r"^\s*(?P<name>[A-Za-z0-9_.\-]+)"
    r"(?P<op>==|>=|<=|~=|!=|>|<)"
    r"(?P<version>[A-Za-z0-9_.\-\+]+)"
    r"\s*(?P<extras>\[.*?\])?\s*$"
)
# Bare name (no version constraint).
_BARE_RE = re.compile(r"^\s*(?P<name>[A-Za-z0-9_.\-]+)\s*$")


# Packages that are known to have version-coupling constraints in
# the F1 Race Replay ecosystem.
KNOWN_CONSTRAINTS: Dict[str, str] = {
    "arcade": "Arcade 3.x has a breaking API vs 2.6.x; this project "
              "pins 2.6.17. Do not upgrade without a migration pass.",
    "pyglet": "pyglet 2.0.dev23 is a pre-release pin. Newer pyglet "
              "versions have API changes; verify Arcade 2.6.17 "
              "compatibility before bumping.",
    "PySide6": "PySide6 6.x is the supported major version; do not "
               "downgrade to PySide2 (different signal/slot API).",
    "fastf1": "FastF1 follows F1 season updates; pin to a specific "
              "minor if reproducibility matters.",
}


class PinKind(str, Enum):
    EXACT = "=="            # ``fastf1==3.0.0`` — strongly pinned
    MIN = ">="              # ``numpy>=1.20`` — lower-bound only
    MAX = "<="
    COMPAT = "~="           # ``numpy~=1.20`` — compatible release
    NEQ = "!="
    GT = ">"
    LT = "<"
    BARE = "bare"           # no version — not recommended for prod
    UNKNOWN = "unknown"


@dataclass
class DependencyEntry:
    name: str
    op: str
    version: str
    raw: str
    kind: PinKind = PinKind.UNKNOWN
    note: Optional[str] = None

    def is_prerelease(self) -> bool:
        return any(tag in self.version.lower()
                   for tag in ("dev", "a", "b", "rc"))


@dataclass
class DependencyReport:
    python_version: str
    entries: List[DependencyEntry] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)

    def summary(self) -> str:
        lines = [
            f"Python: {self.python_version}",
            f"Dependencies: {len(self.entries)}",
        ]
        # Group by kind.
        by_kind: Dict[PinKind, int] = {}
        for e in self.entries:
            by_kind[e.kind] = by_kind.get(e.kind, 0) + 1
        for kind, count in sorted(by_kind.items(), key=lambda x: x[0].value):
            lines.append(f"  {kind.value:>4}: {count}")
        if self.warnings:
            lines.append("")
            lines.append("Warnings:")
            for w in self.warnings:
                lines.append(f"  - {w}")
        if self.recommendations:
            lines.append("")
            lines.append("Recommendations:")
            for r in self.recommendations:
                lines.append(f"  - {r}")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------
def parse_requirements(text: str) -> List[DependencyEntry]:
    """Parse a requirements.txt-like string.

    Lines starting with ``#`` or ``-r`` / ``-e`` are ignored.
    Empty lines are ignored. Inline comments (``#`` after a pin)
    are stripped.
    """
    out: List[DependencyEntry] = []
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line or line.startswith("-"):
            continue
        m = _PIN_RE.match(line)
        if m:
            op = m.group("op")
            kind = {
                "==": PinKind.EXACT,
                ">=": PinKind.MIN,
                "<=": PinKind.MAX,
                "~=": PinKind.COMPAT,
                "!=": PinKind.NEQ,
                ">": PinKind.GT,
                "<": PinKind.LT,
            }[op]
            out.append(DependencyEntry(
                name=m.group("name").lower(),
                op=op,
                version=m.group("version"),
                raw=raw.strip(),
                kind=kind,
            ))
            continue
        m = _BARE_RE.match(line)
        if m:
            out.append(DependencyEntry(
                name=m.group("name").lower(),
                op="",
                version="",
                raw=raw.strip(),
                kind=PinKind.BARE,
            ))
            continue
        out.append(DependencyEntry(
            name=line,
            op="",
            version="",
            raw=raw.strip(),
            kind=PinKind.UNKNOWN,
        ))
    return out


# ---------------------------------------------------------------------------
# Auditor
# ---------------------------------------------------------------------------
def audit_dependencies(entries: Iterable[DependencyEntry],
                       python_version: Optional[str] = None
                       ) -> DependencyReport:
    py = python_version or sys.version.split()[0]
    report = DependencyReport(python_version=py)
    for e in entries:
        report.entries.append(e)
        if e.is_prerelease():
            report.warnings.append(
                f"{e.name} pin '{e.raw}' looks like a pre-release; "
                f"verify it is available on PyPI.")
        if e.kind is PinKind.BARE:
            report.warnings.append(
                f"{e.name} has no version pin; builds will not be "
                f"reproducible.")
        if e.name in KNOWN_CONSTRAINTS:
            e.note = KNOWN_CONSTRAINTS[e.name]
    # Python version check.
    if py:
        major, minor, *_ = (int(p) for p in py.split("."))
        if (major, minor) > (3, 13):
            report.warnings.append(
                f"Python {py} is newer than the documented supported "
                f"range (3.11-3.13); Arcade 2.6.17 and Pyglet 2.0.dev23 "
                f"may not have wheels for this version.")
    # Recommendations.
    if any(e.name == "pyglet" and e.is_prerelease() for e in entries):
        report.recommendations.append(
            "Pyglet is pinned to a pre-release. Consider documenting "
            "a known-good combination or switching to a stable pyglet "
            "release that Arcade 2.6.x supports.")
    if not any(e.kind is PinKind.EXACT for e in entries):
        report.recommendations.append(
            "No exact-pinned dependencies. For reproducible builds, "
            "produce a requirements-lock.txt with exact pins derived "
            "from a known-working environment.")
    return report


def audit_requirements_file(path: Path) -> DependencyReport:
    text = Path(path).read_text(encoding="utf-8")
    entries = parse_requirements(text)
    return audit_dependencies(entries)


__all__ = [
    "DependencyEntry",
    "DependencyReport",
    "PinKind",
    "KNOWN_CONSTRAINTS",
    "parse_requirements",
    "audit_dependencies",
    "audit_requirements_file",
]
