"""Generate the a11y findings report for the docs/ folder."""
from src.lib.resource_paths import project_root
from src.tools.a11y_audit import scan, summary


def main():
    root = project_root()
    findings = scan(root)
    print(f"Scanned: {root}")
    print(summary(findings))
    print()
    for f in findings:
        print(f"  {f.severity:7} {f.code} {f.file}:{f.line} {f.message}")


if __name__ == "__main__":
    main()
