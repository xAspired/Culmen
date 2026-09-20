# Third-party dependencies

Runtime dependencies of `core/`:

| Package | License | Why |
|---------|---------|-----|
| [skyfield](https://rhodesmill.org/skyfield/) | MIT | Time scales, SGP4 driver, TEME→ITRF, topocentric reduction (ADR 0002) |
| [sgp4](https://pypi.org/project/sgp4/) | MIT | The SGP4 propagator itself; also ships Vallado's verification data used as test ground truth |
| [numpy](https://numpy.org/) | BSD-3-Clause | Vectorised propagation over time grids |
| [scipy](https://scipy.org/) | BSD-3-Clause | Brent root finding for AOS/LOS, bounded minimisation for peak elevation |
| [PyYAML](https://pyyaml.org/) | MIT | Ground station definition files |

Development only:

| Package | License |
|---------|---------|
| pytest | MIT |

All of the above are permissive and compatible with Apache-2.0. No copyleft
dependency is present, and none is planned.

Third-party **data** licensing is handled separately, in `data/README.md`.
