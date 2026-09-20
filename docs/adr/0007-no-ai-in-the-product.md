# ADR 0007 — No AI or machine learning inside Culmen

**Status:** Accepted

## Context

Culmen is a planning and validation tool. Its output is used to decide
whether a contact will work. A non-deterministic or non-auditable component
would destroy the property the whole project is built around (ADR 0006).

## Decision

No LLM, no machine learning, no statistical prediction anywhere in the
product. Every output is a deterministic function of its inputs, and
re-running the same inputs with the same `engine_version` reproduces the same
numbers bit-for-bit.

AI is used only as a development aid — design discussion, review, explaining
the mathematics, drafting tests and documentation. Nothing it produces ships
without being checked against an external reference.

## Consequences

- Scheduling uses deterministic ranking, not a learned heuristic (ADR to
  follow when the scheduler lands).
- "Suggested alternatives" in a verdict are rule-derived from the failed
  check, not generated text.
- No model weights, no inference dependency, no network requirement at
  runtime.
