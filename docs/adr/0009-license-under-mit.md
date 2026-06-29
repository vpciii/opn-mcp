# ADR 0009: License the server under the MIT License

- **Status:** Accepted
- **Date:** 2026-06-29
- **Deciders:** Vince Ciganik

## Context

The repository had no `LICENSE`. For an unlicensed work the legal default
is **all rights reserved**: others may view a public repository but may not
legally copy, modify, run, or contribute to it. As `opn-mcp` is being made
public to be used and read, that default defeats the purpose — an MCP
server exists to be installed and run by others.

This is `opn-mcp`'s own licensing decision, independent of the global
methodology repository. That repository is prose and templates and is
dedicated to the public domain under CC0 (methodology ADR 0013); source
code is better served by a recognised software license that carries an
explicit warranty disclaimer.

## Decision

**License `opn-mcp` under the MIT License.**

- Add a top-level `LICENSE` with the standard MIT text, copyright the
  project author.
- Declare `license = "MIT"` (SPDX) and `license-files = ["LICENSE"]` in
  `pyproject.toml` so package metadata matches the file.

MIT is permissive (use, modify, distribute, sublicense), short, and
universally recognised — the conventional, low-friction choice for a
small, single-purpose tool meant to be adopted easily.

## Alternatives considered

- **Apache-2.0** — also permissive, adds an explicit patent grant and
  contributor terms. Rejected as heavier than warranted for a project this
  size with no meaningful patent surface; MIT's brevity and ubiquity win.
- **CC0 / public domain** — right for the methodology's prose, but
  unconventional for software: it omits the warranty disclaimer the
  MIT/Apache family provides. Rejected for code.
- **Stay unlicensed** — rejected: all-rights-reserved blocks the reuse the
  project is published to enable.

## Consequences

- Anyone may use, modify, and redistribute the server under the MIT terms,
  provided the copyright notice and warranty disclaimer are preserved.
- Effectively irreversible for code already released under it: prior
  releases remain MIT; any future relicense would apply only going forward
  and to new contributions.
- `pyproject.toml` now advertises the license to packaging tooling.

## References

- methodology ADR 0013 (the methodology repo's CC0 choice — the
  prose-vs-code distinction this ADR mirrors).
- `LICENSE`, `pyproject.toml`.
