#!/usr/bin/env python3
"""Spec-criterion coverage checker for opn-mcp.

Adapted from the methodology reference implementation
($METHODOLOGY_HOME/templates/ci/check-spec-coverage.py, methodology
ADR 0017) — unmodified apart from this header. Verifies the
traceability rules of methodology §5 (ADR 0006, 0011) for every spec
whose status makes coverage mandatory:

  1. every success criterion (SC-n) maps to at least one test in the
     spec's Traceability table;
  2. every MUST / MUST NOT requirement (R-n) is covered by at least
     one criterion in that table;
  3. every referenced test file exists and cites the SC id it
     verifies;
  4. every Traceability row points at a criterion that exists in the
     spec.

This is a *reference* implementation (ADR 0017): adapt or replace it
per project, and record the choice in the project's tooling ADR. It
assumes the conventions of templates/spec/spec.md — the `- **Status:**`
header line, `**R-n (MUST)**` / `**SC-n**` ids, and a `## Traceability`
table of `| SC-n | R-n, R-m | `tests/...::test_x` |` rows. Test paths
are resolved relative to the repository root (the working directory).

Usage:
    check-spec-coverage.py [--specs-dir specs] [--include-approved]
                           [spec_dir ...]

By default coverage is enforced for specs with status `Implemented`
(complete coverage is what that status *means*); `--include-approved`
also enforces `Approved` specs, for projects that want the gate to
tighten as implementation proceeds. Other statuses are skipped.
Exits 0 if every enforced spec passes, 1 otherwise.
"""

import argparse
import re
import sys
from pathlib import Path

STATUS_RE = re.compile(r"^\s*-\s*\*\*Status:\*\*\s*(.+?)\s*$", re.M)
REQ_RE = re.compile(r"\*\*(R-\d+)\s*\((MUST(?:\s+NOT)?|SHOULD(?:\s+NOT)?|MAY)\)\*\*")
SC_DEF_RE = re.compile(r"^\s*[-*]\s+\*\*(SC-\d+)\*\*", re.M)
HEADING_RE = re.compile(r"^##\s+(.+?)\s*$", re.M)
ENFORCED_DEFAULT = {"implemented"}


def section(text, title):
    """Return the body of the `## <title>` section, or ""."""
    matches = list(HEADING_RE.finditer(text))
    for i, m in enumerate(matches):
        if m.group(1).strip().lower() == title.lower():
            end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            return text[m.end():end]
    return ""


def table_rows(body):
    """Parse markdown table rows into lists of cell strings."""
    rows = []
    for line in body.splitlines():
        line = line.strip()
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if not cells or all(not c for c in cells):
            continue
        if all(re.fullmatch(r":?-{3,}:?", c) for c in cells if c):
            continue  # separator row
        rows.append(cells)
    return rows[1:] if rows else []  # drop the header row


def cites(text, sc_id):
    return re.search(r"\b%s\b" % re.escape(sc_id), text) is not None


def check_spec(spec_path, root):
    """Return a list of failure messages for one spec.md."""
    text = spec_path.read_text(encoding="utf-8")
    failures = []

    musts = {r for r, level in REQ_RE.findall(text)
             if level.startswith("MUST")}
    criteria = set(SC_DEF_RE.findall(section(text, "Success criteria")))
    rows = table_rows(section(text, "Traceability"))

    covered_sc = set()
    covered_req = set()
    for cells in rows:
        if len(cells) < 3:
            failures.append("Traceability row has fewer than 3 cells: %r" % cells)
            continue
        sc_cell, req_cell, test_cell = cells[0], cells[1], cells[2]
        sc_ids = re.findall(r"\bSC-\d+\b", sc_cell)
        if not sc_ids:
            failures.append("Traceability row with no SC id: %r" % cells)
            continue
        refs = re.findall(r"`([^`]+)`", test_cell) or (
            [test_cell] if test_cell.strip() else [])
        for sc in sc_ids:
            if sc not in criteria:
                failures.append(
                    "%s appears in Traceability but is not defined "
                    "under ## Success criteria" % sc)
            if not refs:
                failures.append("%s has no test reference" % sc)
                continue
            covered_sc.add(sc)
            for ref in refs:
                test_file = root / ref.split("::")[0].strip()
                if not test_file.is_file():
                    failures.append(
                        "%s → %s: file not found" % (sc, test_file))
                elif not cites(test_file.read_text(encoding="utf-8"), sc):
                    failures.append(
                        "%s → %s: test file does not cite %s"
                        % (sc, test_file, sc))
        covered_req.update(re.findall(r"\bR-\d+\b", req_cell))

    for sc in sorted(criteria - covered_sc, key=lambda s: int(s[3:])):
        failures.append("%s has no Traceability entry" % sc)
    for req in sorted(musts - covered_req, key=lambda s: int(s[2:])):
        failures.append(
            "%s (MUST/MUST NOT) is not covered by any criterion "
            "in the Traceability table (ADR 0011)" % req)
    if criteria and not rows:
        failures.append("spec has success criteria but no Traceability table")
    return failures


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("spec_dirs", nargs="*", type=Path,
                    help="specific spec folders to check (default: scan --specs-dir)")
    ap.add_argument("--specs-dir", type=Path, default=Path("specs"))
    ap.add_argument("--include-approved", action="store_true",
                    help="also enforce specs with status Approved")
    args = ap.parse_args(argv)

    root = Path.cwd()
    enforced = set(ENFORCED_DEFAULT)
    if args.include_approved:
        enforced.add("approved")

    dirs = args.spec_dirs or (
        sorted(p for p in args.specs_dir.iterdir() if p.is_dir())
        if args.specs_dir.is_dir() else [])
    if not dirs:
        print("no spec folders found under %s — nothing to check" % args.specs_dir)
        return 0

    failed = False
    for d in dirs:
        spec = d / "spec.md"
        if not spec.is_file():
            print("SKIP  %s (no spec.md)" % d)
            continue
        m = STATUS_RE.search(spec.read_text(encoding="utf-8"))
        status = (m.group(1).strip().lower() if m else "")
        if status not in enforced:
            print("SKIP  %s (status: %s)" % (spec, m.group(1).strip() if m else "missing"))
            continue
        failures = check_spec(spec, root)
        if failures:
            failed = True
            print("FAIL  %s" % spec)
            for f in failures:
                print("      - %s" % f)
        else:
            print("PASS  %s" % spec)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
