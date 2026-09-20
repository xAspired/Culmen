# ADR 0003 — Apache-2.0 for the project's own code

**Status:** Accepted

## Context

The project should be permissively licensed unless there is a strong reason
for copyleft. Candidates considered: Apache-2.0, MIT, GPLv3.

## Decision

Apache-2.0 for code authored in this repository.

Reasons:

1. **Explicit patent grant.** RF and space hardware are patent-dense fields.
   MIT offers no patent language at all; Apache-2.0 grants and terminates
   patent rights explicitly.
2. **Ecosystem fit.** Orekit, GMAT and CesiumJS are all Apache-2.0. Zero
   friction if any of them is integrated later.
3. **Attribution.** The `NOTICE` mechanism preserves attribution in a way MIT
   does not.

GPLv3 is rejected: it would exclude adoption by commercial operators and
agencies, who are precisely the users whose adoption would give the project
credibility. The value here is in domain correctness, not in preventing
appropriation.

## Consequences

Licensing is separated into four places, which is the arrangement that avoids
the most common failure mode of open scientific projects:

- `LICENSE` — Apache-2.0, our code
- `NOTICE` — required attributions
- `THIRD_PARTY.md` — dependency licenses
- `data/README.md` — provenance, license and fetch date of every data file

**Third-party data is not copyleft-clean by default.** SatNOGS DB content is
CC BY-SA: redistributing a dump would attach ShareAlike obligations to the
*data*, not to our Apache-2.0 code. Decision: never vendor SatNOGS dumps;
fetch at runtime, cache locally, attribute in the UI and in `data/README.md`.
