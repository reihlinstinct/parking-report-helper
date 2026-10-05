# Parking Report Helper

A dependency-free Python CLI that turns a JSON list of vehicles into Hebrew
parking-violation report drafts for use in Israel. It generates text only; it
does not submit reports. An optional browser helper can fill a municipal web form and stops before submitting.

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
report text. No email address or public API is documented for reports, and the form
uses reCAPTCHA, so the tool never submits anything. You paste the values and attach up
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

### Filling the form in a browser (optional)

An optional helper opens the form in a real browser window, fills every field from the
config and your reporter file, attaches photos, and then stops. You review, pass any
verification (captcha) and press submit yourself.

```sh
pip install ".[fill]"
playwright install chromium
parking-report sample.json --municipality jerusalem --reporter ~/reporter.json \
  --fill 1 --photo ~/photo1.jpg --photo ~/photo2.jpg
```

`--fill N` picks car number N from the input (one submission per report). Close the
browser window when you are done. The helper never clicks submit, never solves or
works around captchas or bot protection, and rejects any URL that is not the configured
form or a local test page. Photos are checked against the config limits first. The core
tool stays dependency-free; Playwright is only needed for this extra.

Fields are located by their visible Hebrew label, or by an optional `"selector"` in the
field's config entry. Known limit: the live Jerusalem page returned HTTP 403 to automated
read-only requests while this was written, so the labels and selectors are untested
against the real form. Tests use a local mock form (`tests/fixtures/`). If a field is
not found it is reported on exit and left for you to fill by hand; adjust the label or
add a `selector` in `configs/jerusalem.json`. If the site blocks the automated browser,
use the plain copy-paste output above.

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
src/parking_report/fill.py          optional browser form filling (stops before submit)
src/parking_report/inspect.py       optional read-only field check
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

Unit tests cover report formatting, validation, municipality configs and the URL and
attachment guards. Functional tests (`tests/test_functional_*.py`) run the real CLI on
`sample.json` and, when Playwright is installed (`pip install ".[fill]"` and
`playwright install chromium`), drive headless Chromium against a local fake site: form
filled but never submitted, HTTP 403 and captcha pages reported without retries. They
never contact the real municipality site.

## Continuous integration

GitHub Actions runs the suite on Python 3.10 to 3.13 for every push and pull request.
A separate job builds the Docker image, runs the tests inside it, and smoke-tests the
container. Nothing is published. Workflows use read-only repository permissions and
need no secrets.
