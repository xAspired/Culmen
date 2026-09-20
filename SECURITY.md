# Security policy

## Reporting a vulnerability

Report privately, not as a public issue: use GitHub's **"Report a
vulnerability"** button under the Security tab of this repository, which opens
a private advisory.

Please include what an attacker could do, how to reproduce it, and the version
or commit. You will get an acknowledgement; this is a small project maintained
by one person, so a fix may take time, and you will be told honestly if it
will.

Credit is given to reporters who want it.

## What counts as a vulnerability here

Culmen is an analysis tool. It has no accounts, no authentication, and stores
nothing. That removes whole categories of risk and leaves a few real ones:

- **Untrusted input reaching the parsers.** Element sets and station
  definitions come from files and from HTTP bodies. A malformed TLE or a YAML
  file that crashes the service, consumes unbounded memory, or executes
  anything is a vulnerability. The YAML loader is `SafeLoader` for exactly
  this reason.
- **Path traversal** through the station or element-set directories.
- **Denial of service** through a request that is cheap to send and expensive
  to answer — a pass search over a decade with a one-second step, for
  instance. The API caps several of these; a gap in the capping is worth
  reporting.
- **Dependency vulnerabilities** in the runtime dependencies listed in
  `THIRD_PARTY.md`.

## What does not

- **The service has no authentication or authorisation.** That is not an
  oversight: it is a local analysis tool, and it is documented as such. If you
  expose it to a network, that is your deployment decision and putting an
  authenticating proxy in front of it is your responsibility.
- **Wrong numbers are bugs, not vulnerabilities**, and belong in a normal
  issue — unless the wrongness is reachable by an attacker who controls the
  input in a way the operator cannot see.

## A note specific to this kind of software

Culmen plans and validates. **It never transmits, never commands a
spacecraft, and never controls an antenna.** It has no code paths to a radio
or a rotator, by design, and adding one is out of scope (see the README).

But its output can inform decisions about real spacecraft operations, and that
is worth stating plainly: every result carries its assumptions and the checks
behind it precisely so that a person can judge whether to rely on it. If you
find a way to make Culmen produce a *confidently wrong* answer — a verdict
that looks validated but is not, a margin that silently omits a loss, an
assumption that fails to appear in `assumptions[]` — report it. That is the
failure mode this project cares most about, and the one its whole design is
built to prevent.
