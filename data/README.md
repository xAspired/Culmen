# Data provenance

Every file in `data/` is listed here with its origin, license, fetch date and
required attribution. Nothing goes into this directory without an entry.

Culmen does **not** vendor operational orbital data. Element sets are
fetched at runtime and cached locally.

| Path | Origin | License / policy | Obtained | Attribution |
|------|--------|------------------|----------|-------------|
| `stations/padova.yaml` | Written for this project | Apache-2.0 (with the code) | — | — |
| `tle/example-leo.tle` | Extract of `SGP4-VER.TLE` from the `sgp4` Python package | Public reference data published with AIAA 2006-6753; the `sgp4` package is MIT | 2026-09-19 | Vallado, Crawford, Hujsak & Kelso, *Revisiting Spacetrack Report #3*, AIAA 2006-6753 |

## Notes on the example element sets

`tle/example-leo.tle` contains **historical verification element sets**, with
epochs in 2006. They exist so the demo and the tests run offline and
deterministically. They must never be used for real planning: Culmen will
flag them, correctly, as far past their epoch.

## Runtime data sources

**CelesTrak** — the intended source for current GP/TLE data.
Policy we commit to:

- use the modern GP endpoints (`/NORAD/elements/gp.php`), not legacy file URLs
- no more than one fetch per group per few hours
- an identifiable `User-Agent` including a contact address
- mandatory local caching, honouring `If-Modified-Since`
- no bulk redistribution of fetched data in this repository

The element sets themselves derive from US Government sources and are not
subject to copyright, but the site's usage policy is respected regardless.

**SatNOGS DB** — the intended source for transmitter, frequency and mode
metadata. **Its data is CC BY-SA.** Including a dump in this repository would
attach ShareAlike obligations to the data (not to our Apache-2.0 code).
Decision: never vendor a dump. Fetch at runtime, cache locally, and attribute
visibly in the UI and here.

**Space-Track** — out of scope for V1. If added: bring-your-own credentials,
no redistribution, documented rate limiting.

## Ground station definitions

`stations/*.yaml` uses Culmen's own Ground Station Definition format,
versioned from the first file (`schema_version: 1`). Users define their own
stations without touching code. Coordinates in the example are approximate
city-centre locations, not real antenna sites.

---

## Populating a real catalogue

The repository ships one example station and two historical element sets. Real
data is fetched into your own working copy and is **gitignored**: Culmen
redistributes no third-party catalogue.

### Element sets — `scripts/fetch_tle.py`

```bash
export CULMEN_CONTACT="you@example.org"
./scripts/fetch_tle.py                 # stations, cubesat, weather, noaa, science
./scripts/fetch_tle.py --group active  # the full catalogue, ~11 000 objects
./scripts/fetch_tle.py --list-cached
```

Standard library only: this runs with the system `python3`, with no virtualenv
and nothing installed.

Files land in `data/tle/` and are imported at startup.

The script is built around CelesTrak's usage policy rather than around speed:

- it **refuses to run without a contact address**, so the User-Agent always
  identifies who is asking;
- it sends **`If-Modified-Since` / `If-None-Match`** from a cached response, so
  an unchanged group costs a 304 and no payload;
- it enforces a **minimum three hours between fetches of the same group**,
  locally, overridable only with an explicit `--force`;
- it never redistributes: what it writes is gitignored.

Attribution: orbital data from CelesTrak (celestrak.org). The element sets
derive from US Government sources and are not subject to copyright; the site's
usage policy applies regardless.

### Ground stations — `scripts/import_stations.py`

```bash
# 1. export a station list from wherever you keep one, as JSON
# 2. look at what you actually have
./scripts/import_stations.py stations.json --inspect

# 3. convert, naming the fields and carrying the attribution
./scripts/import_stations.py stations.json \
    --name-field name --lat-field lat --lon-field lng --alt-field altitude \
    --attribution "SatNOGS Network, CC BY-SA 4.0" --only-online
```

**This takes a file and does not fetch an API itself, on purpose.** The
catalogues worth importing have schemas this project has not verified, and a
converter written against a guessed schema silently produces wrong
coordinates — a station misplaced by 0.1 degrees is 11 km, which moves every
azimuth and elevation derived from it. So `--inspect` shows you the real keys,
the mapping is explicit, and anything that cannot be mapped is **skipped and
listed rather than guessed**.

Imported files go to `data/stations/imported/`, which is gitignored; the
loader reads subdirectories, so they still appear in the app. Stations you
write yourself live directly in `data/stations/` and are committable — they
are your own work under the project's own licence.

Every generated file records where it came from, its attribution, and that the
coordinates have not been independently verified.

**SatNOGS data is CC BY-SA.** That obligation travels with the data, not with
Culmen's Apache-2.0 code: if you redistribute definitions derived from it, the
ShareAlike terms apply to them. This is why the converter takes
`--attribution` and writes it into every file, and why nothing derived is
committed here.
