# ADR 0003: Single curated write tool with anti-lockout refusal

- **Status:** Accepted
- **Date:** 2026-06-09
- **Deciders:** Vince Ciganik

> This ADR **records a pre-existing decision** rather than making a new
> one (brownfield decision capture, `adopting.md` seed step 3).

## Context

The tool surface is driven by LLM agents, including unattended
scheduled ones. A firewall is the worst place for an agent to make an
unintended config change — a wrong rule toggle can lock the operator
out of the box entirely. The project's stated posture is "primarily
read-only".

## Decision

We expose exactly one config-mutating tool: `toggle_dnat_rule`, which
enables/disables an existing DNAT rule by UUID (then applies). Before
toggling, it fetches the rule and **refuses** any whose description
contains `anti-lockout` or `antilockout` (case-insensitive). All other
tools are reads; the few other POSTs (`ping_host`, gateway status,
`get_updates_available(refresh=True)`'s firmware check) trigger
diagnostics, not config changes. No tool creates, deletes, or edits
rules.

## Alternatives considered

- **Full write surface (CRUD on rules/services)** — more useful for
  remediation, rejected: the blast radius of an LLM-driven mistake on
  a firewall outweighs the convenience.
- **No writes at all** — purest posture, rejected: toggling a
  port-forward on/off is the one low-risk, high-value mutation
  (e.g. temporarily closing an exposed service) and is reversible by
  construction.

## Consequences

- Easier: the safety story is auditable in one function; "primarily
  read-only" is enforced in code, not convention; the toggle is
  inherently reversible (toggle back).
- Harder: agents cannot remediate anything beyond DNAT toggles.
- **Known limitation:** the anti-lockout protection is a **string
  match on the rule description**, not a structural check of what the
  rule actually protects. A renamed or undescribed anti-lockout rule
  would not be refused; an unrelated rule mentioning "anti-lockout"
  would be. A future change should replace this with a structural
  check — and per methodology §9, that fix ships with a regression
  test.

## Adoption impact

None — records the existing write surface; any widening of it is a
new ADR.

## References

- `server.py` (`toggle_dnat_rule`)
- ADR 0002 (the unauthenticated SSE transport this write tool sits
  behind)
- `README.md` — "Notes"
