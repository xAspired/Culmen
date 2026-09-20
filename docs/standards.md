# Standards: what we implement, and what we only borrow vocabulary from

No CCSDS or ITU-R document is copied into this repository. This file records
which parts of which standards Culmen actually implements, so a reader can
tell borrowed terminology from claimed conformance.

**Culmen claims conformance to nothing.** It uses these documents as
technical references.

| Standard | Used for | Phase | Status |
|---|---|---|---|
| Vallado et al., *Revisiting Spacetrack Report #3* (AIAA 2006-6753) | SGP4 definition, TEME frame, verification vectors | 1 | **Implemented and verified** against the official test vectors |
| WGS84 (NIMA TR8350.2) | Ellipsoid parameters, geodetic latitude | 2 | Implemented |
| IERS Conventions | Understanding UT1/TT/polar motion; mostly abstracted by Skyfield | 1–2 | Reference only |
| ITU-R P.618 | Rain attenuation and propagation impairments | 5 | Not yet — **required**, not optional, at 8.2 GHz |
| ITU-R P.676 | Gaseous (oxygen, water vapour) atmospheric attenuation | 5 | Not yet — required |
| ITU-R P.372 | Radio noise, antenna noise temperature | 5 | Not yet |
| CCSDS 401.0-B | Bands, modulations, RF system performance | 5 | Reference for parameter ranges |
| CCSDS 130.1-G | TM synchronisation and channel coding; coding gain in required Eb/N0 | 5–6 | Reference |
| CCSDS 902.x (SCCS-SM), 910.x (SLE) | Cross-support vocabulary: service package, provider, user | 7–9 | **Naming only.** No SLE implementation is planned for V1 |

## Why vocabulary matters even without implementation

Using CCSDS terms for scheduling concepts — *service package*, *provider*,
*user* — means anyone from the ground-segment world reads our API and
recognises what it models. Inventing parallel terminology would cost nothing
today and a great deal later.

Conversely, borrowing the vocabulary is not conformance, and this file exists
so nobody mistakes one for the other.
