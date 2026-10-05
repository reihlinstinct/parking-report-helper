# Design

## Purpose

Turn a JSON list of reported vehicles into text a person can send to a municipality:
either a Hebrew report draft, or the values of a municipality's web form. A person
always reviews and submits. The tool never submits anything.

## Non-goals and safety invariants

These are tested and must hold for every change:

1. Never submit a form, never click a submit button.
2. Never solve, bypass or interact with a captcha or other bot check. Stop and report.
3. Only open the configured municipality URL or a local test page (`check_url`).
4. One request per diagnostic run, no retries on HTTP errors or verification walls.
5. No personal data in the repository. Reporter details live in a file outside it.
6. The core (report text, form values) stays dependency-free. Playwright is an extra.

## Layers

```
cli.py            argument parsing, file I/O, exit codes, output printing
   |
municipality.py   config loading, address splitting, form field values   (pure, except load_config)
report.py         Car model, validation, Hebrew report text              (pure)

fill.py           browser form filling   (optional, Playwright)  -> uses municipality.MISSING
inspect.py        read-only field presence check (optional)       -> uses fill.check_url
configs/*.json    one data file per municipality
```

Dependencies point downward only. `report.py` imports nothing from the package.
`municipality.py` imports `report.py`. The browser modules import Playwright lazily, so
the core installs and runs without it. `cli.py` is the only module that reads files,
prints, or sets exit codes.

## Data flow

```
input.json --> Car.from_mapping (validate) --> build_report            --> text
                                           \-> build_submissions(config, reporter)
                                                  |-> format_submission / submission_dict --> stdout
                                                  \-> fill_page (browser, stops before submit)
```

A submission is an ordered list of `(key, label, value)` rows, one per config field.
Required values that are not available become `MISSING` (`<חסר>`) so gaps are visible
instead of invented. Browser code skips those fields.

## Error handling

Input and usage problems raise `ValueError` (or `FillError` in the browser modules).
`cli.main` turns them into `error: ...` on stderr and exit code 1, without tracebacks and
without partial stdout. Invalid records name their 1-based position (`car 2: ...`).
Option combinations that make no sense (for example `--fill` without `--municipality`)
are rejected by argparse with exit code 2 instead of being silently ignored.

## Extending

A new municipality is one JSON file in `configs/` (see the README). No code change is
needed unless the form has widgets that labels or selectors cannot reach.

## Test strategy

| Level | Where | What it proves |
| --- | --- | --- |
| Unit | `test_report*.py`, `test_municipality.py`, `test_fill.py` (checks), `test_inspect.py` | Pure functions, validation, URL and attachment guards |
| CLI | `test_cli.py` | Flags, exit codes, error messages |
| Functional | `test_functional_cli.py` | The real CLI on the shipped `sample.json`: exact report text, form values from the right sources, option validation |
| Functional (browser) | `test_functional_form.py` | Real headless Chromium against a local fake site: the form is filled but never submitted, photo upload works, HTTP 403 and captcha pages are reported and not retried, no non-GET request is ever made |

Why a fake site: the live Jerusalem 106 page answers HTTP 403 to automated requests from
cloud IPs and uses reCAPTCHA, so automated tests must never depend on it. `tests/support.py`
serves the mock form, a 403 page and a captcha page on localhost and records every request.
The browser tests skip when Playwright is not installed; the CI `fill` job installs it.

The live site is only ever touched by the manually triggered probe workflow
(`LIVE_PROBE.md`).
