# Parking Report Helper

A dependency-free Python CLI that turns a JSON list of vehicles into Hebrew
parking-violation report drafts for use in Israel. It generates text only; it
does not submit reports or attach photos.

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

### Adding another municipality

Each municipality is one JSON file in `src/parking_report/configs/` with the channel
details (URL, hotline, whether submission is manual), attachment limits and an ordered
`fields` list. A field has a `key`, the form `label`, `required`, and a `source`:
`reporter` (from the reporter file), `config` (a fixed value such as `city`) or
`car`/`report` (derived from the input). Use a file outside the package with
`--municipality path/to/city.json`.

## Code layout

```
src/parking_report/report.py   Car dataclass and report formatting (no I/O)
src/parking_report/cli.py      argparse CLI, installed as `parking-report`
src/parking_report/municipality.py  config loading and form field values
src/parking_report/configs/    per-municipality JSON configs
tests/                         unit and CLI tests
```

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

The tests cover municipality configs and field values, plus report formatting, required fields, optional fields, date
edges, record validation, and the real CLI: successful output, options, help,
empty input, malformed JSON, invalid records, and missing files.

## Continuous integration

GitHub Actions runs the suite on Python 3.10 to 3.13 for every push and pull request.
A separate job builds the Docker image, runs the tests inside it, and smoke-tests the
container. Nothing is published. Workflows use read-only repository permissions and
need no secrets.
