# Parking Report Helper

A dependency-free Python CLI that turns a JSON list of vehicles into Hebrew
parking-violation report drafts for use in Israel. It generates text only; it
does not submit reports or attach photos.

## Requirements

Python 3.10 or later. No third-party dependencies are needed.

## Usage

```sh
python3 parking_report.py sample.json
python3 parking_report.py sample.json --city "Example City" --name "Example Reporter"
python3 parking_report.py sample.json --no-photo
```

Supply city and reporter values in Hebrew when preparing a Hebrew report.
Attach supporting photos separately when submitting to the municipality.

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
python3 -m unittest discover -v
```

The 19 tests cover report formatting, required fields, optional fields, date
edges, record validation, and the real CLI: successful output, options, help,
empty input, malformed JSON, invalid records, and missing files.

## Continuous integration

GitHub Actions runs the same suite on Python 3.10, 3.11, 3.12, and 3.13 for every
push and pull request. The workflow uses read-only repository permissions and a
five-minute job timeout. No secrets or external services are needed.
