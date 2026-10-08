# Parking Report Helper

[![Tests](https://github.com/reihlinstinct/parking-report-helper/actions/workflows/tests.yml/badge.svg)](https://github.com/reihlinstinct/parking-report-helper/actions/workflows/tests.yml)
[![Last commit](https://img.shields.io/github/last-commit/reihlinstinct/parking-report-helper)](https://github.com/reihlinstinct/parking-report-helper/commits/main)
[![Open issues](https://img.shields.io/github/issues/reihlinstinct/parking-report-helper)](https://github.com/reihlinstinct/parking-report-helper/issues)
[![Closed PRs](https://img.shields.io/github/issues-pr-closed/reihlinstinct/parking-report-helper)](https://github.com/reihlinstinct/parking-report-helper/pulls?q=is%3Apr+is%3Aclosed)
[![Python 3.10-3.13](https://img.shields.io/badge/python-3.10%20to%203.13-blue?logo=python&logoColor=white)](pyproject.toml)
[![Docker](https://img.shields.io/badge/docker-ready-2496ED?logo=docker&logoColor=white)](Dockerfile)
[![License: MIT](https://img.shields.io/github/license/reihlinstinct/parking-report-helper)](LICENSE)
[![Reports filed](https://img.shields.io/endpoint?url=https%3A%2F%2Fraw.githubusercontent.com%2Freihlinstinct%2Fparking-report-helper%2Fbadge-data%2Freports.json)](docs/API106.md)

A dependency-free Python CLI that turns a JSON list of vehicles into Hebrew
parking-violation report drafts for use in Israel. It generates text only; it
does not submit reports by default. Browser automation has been removed; direct API preparation is the reporting route.
The optional 106 API runner supports explicitly approved local submissions; its
reusable private-repo workflow is preview-only until separately enabled. See
[docs/API106.md](docs/API106.md).

## Requirements

Python 3.10 or later, or Docker. No third-party dependencies are needed.

## Install and run

```sh
pip install .
parking-report sample.json
parking-report sample.json --city "Example City" --name "Example Reporter"
parking-report sample.json --no-photo
```

`python -m parking_report sample.json` works too. Supply city and reporter values in
Hebrew when preparing a Hebrew report. Attach supporting photos separately when
submitting to the municipality.

## Docker

The image is based on `python:3.13-slim`, runs as a non-root user, and uses
`parking-report` as its entrypoint. The working directory is `/data`, so mount the
folder that holds your JSON file there:

```sh
docker build -t parking-report-helper .
docker run --rm -v "$PWD:/data:ro" parking-report-helper sample.json
docker run --rm -v "$PWD:/data:ro" parking-report-helper sample.json --city "Example City" --no-photo
```

Run the test suite inside Docker with `docker build --target test .`.

## Intake from private GitHub storage

Store original photos and report.json records in the PRIVATE parking-reports repository.
Its manual workflow checks out its own reports, builds the public helper at a reviewed
commit, and mounts the records read-only. No external credentials are needed. The public
repo never receives private logs or artifacts. See [docs/INTAKE.md](docs/INTAKE.md).

## Municipality reports (Jerusalem)

`--municipality jerusalem` prints copy-paste values for the fields of the Jerusalem
Municipality 106 web form (https://www.jerusalem.muni.il/he/contactus/106/): first
and last name, ID type and number, phones, email, city, street, house number and the
report text. This command only formats text/field values for manual use.
The separately supplied API is supported by `parking-report-106`; no browser
automation remains. You paste the values and attach up
to 3 photos (png, jpg, pdf, tif, gif or doc, 5 MB each) yourself.

```sh
parking-report sample.json --municipality jerusalem --reporter ~/reporter.json
parking-report sample.json --municipality jerusalem --reporter ~/reporter.json --json
```

The reporter file holds your own details and must stay outside this repository:

```json
{"first_name": "...", "last_name": "...", "id_type": "תעודת זהות",
 "id_number": "...", "phone": "...", "phone2": "", "email": "..."}
```

Required values that are not supplied print as `<חסר>`.

### Adding another municipality

Each municipality is one JSON file in `src/parking_report/configs/` with the channel
details (URL, hotline, whether submission is manual), attachment limits and an ordered
`fields` list. A field has a `key`, the form `label`, `required`, and a `source`:
`reporter` (from the reporter file), `config` (a fixed value such as `city`) or
`car`/`report` (derived from the input). Use a file outside the package with
`--municipality path/to/city.json`.

## Code layout

```
src/parking_report/report.py        Car dataclass and report formatting (no I/O)
src/parking_report/municipality.py  config loading, form field values
src/parking_report/cli.py           argparse CLI, installed as `parking-report`
src/parking_report/api106.py        optional direct API transport and state guards
src/parking_report/api_cli.py       offline-first 106 runner
src/parking_report/registry.py      private government registry enrichment
src/parking_report/configs/         per-municipality JSON configs
tests/                              unit, CLI and functional tests
docs/DESIGN.md                      architecture, invariants, test strategy
```

See [docs/DESIGN.md](docs/DESIGN.md) for the layering rules and the safety invariants.

## Input format

The input must be a JSON array of objects. Required fields are nonempty strings:

| Field | Description |
| --- | --- |
| `plate` | Vehicle plate number |
| `street` | Street and building number |
| `datetime` | Date and time in `YYYY-MM-DD HH:MM` or `YYYY-MM-DDTHH:MM` format |

Optional fields are `car_type` and `notes`. The Hebrew examples in `sample.json`
use synthetic plate numbers and an example address. Do not commit real plates,
names, locations, photos, or credentials to this public repository.

## Output and errors

Reports are written to stdout, separated by a blank line. An empty input array
produces no reports. Input errors exit with status 1 and a short error on stderr,
without a traceback or partial reports. Invalid records identify their position
in the array.

## Tests

```sh
pip install .
python -m unittest discover -s tests -v
```

Unit tests cover formatting, intake, config validation, API duplicate/uncertain-result
guards and private registry lookups. Functional tests run the real CLI with
synthetic data and generated photos. No test contacts the municipality. Browser
fill tests, mock-form fixtures, Playwright/stealth dependencies and the read-only
website-probe workflow are removed because 106 reporting now uses the API.

Registry enrichment runs in the private caller repository only. See
[docs/REGISTRY.md](docs/REGISTRY.md) for fields and unknown-result handling.
Reporter fields and API credentials stay in private secrets/env, never public code.
Actual live Actions submission remains disabled.

## Continuous integration

GitHub Actions runs the suite on Python 3.10 to 3.13 for every push and pull request.
A separate job builds the Docker image, runs the tests inside it, and smoke-tests the
container. Nothing is published. Workflows use read-only repository permissions and
need no secrets.

## Duplicate protection

The API runner requires a durable private Git ledger for live use. Stable intake
folder IDs and original-photo hashes cannot be silently reused with changed
inputs. Uncertain creation blocks retries; complete receipts survive new runners.
Private Actions serializes all 106 work; live remains disabled. See
[docs/API106.md](docs/API106.md).

## Render HTTP connectivity check

A non-root Docker web service is available via `Dockerfile.render` (or the `http`
Docker target). It provides bearer-authenticated, manually invoked Login checking
only. Health checks never contact the municipality and report submission is
hard-disabled. No secrets belong in source/images/logs. See
[docs/HTTP106.md](docs/HTTP106.md) for deploy variables, endpoints and free-hosting
limits. No Render signup/deployment or municipal request is performed by CI.

## Other municipal issues and per-report category selection

The API runner accepts `municipal_subject` on each private `report.json`.
Select any subject code from the captured catalog, including broken signs and
graffiti. Non-parking drafts do not require a vehicle plate or request a parking
inspector. Default sidewalk code 1145 stays unchanged. Exact owner review is
still required before filing. See [SUBJECTS.md](docs/SUBJECTS.md) for the record
fields, examples, snapshot limits and approval rules.
