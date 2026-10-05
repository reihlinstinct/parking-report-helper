# Intake from Google Drive

Photos of parking violations are saved by the assistant into a Drive folder, one subfolder
per report. The tool reads those folders and prepares the report text or form values. It
never writes to Drive and never submits anything.

## Layout

```
Parking reports/
  2026-10-05_1005_ab12/
    photo.jpg      original photo, unmodified
    report.json    the record below
```

## report.json (schema_version 1)

```json
{
  "schema_version": 1,
  "status": "ready",
  "captured_at": "2026-10-05 10:05",
  "gps": {"lat": 31.75081, "lon": 35.21398, "heading_deg": 338},
  "address": {"street": "התנופה", "house_number": "17", "neighborhood": "תלפיות",
              "city": "ירושלים", "approximate": true, "source": "OpenStreetMap Nominatim"},
  "plate": "00-000-00",
  "car_type": "קופרה",
  "violation": {"description": "על המדרכה וחוסם אותה למעבר הולכי רגל",
                "category": "sidewalk", "confidence": "high",
                "needs_clarification": false, "question": ""},
  "photo": "photo.jpg",
  "notes": "",
  "user_corrections": []
}
```

- `status`: `ready`, `needs_clarification` or `reported`. Only `ready` records are used.
- `captured_at`: Israel local time from the photo EXIF, `YYYY-MM-DD HH:MM`.
- `violation.description`: Hebrew, used as the report text. `category` is one of `sidewalk`,
  `crosswalk`, `bus_stop`, `disabled_spot`, `corner`, `fire_hydrant`, `double_parking`, `other`.
- `violation.question`: what to ask the reporter when the violation is unclear.
- `user_corrections`: the reporter's corrections, kept so the next guesses improve.
- Required for use: `plate`, `captured_at`, `address.street`. Anything else is optional.
- Records that are not ready, or lack a required value, are skipped with a reason on stderr.
  They are never guessed.

## Usage

```sh
# a local folder (Drive for desktop sync, rclone, or a download)
parking-report --intake ~/Drive/"Parking reports" --municipality jerusalem --reporter ~/reporter.json

# copy the Drive folder first (read-only token), then read it
export PARKING_DRIVE_TOKEN=...   # OAuth access token with the drive.readonly scope
parking-report --intake ./reports --drive-folder <folder id> --municipality jerusalem
```

The skipped list and the photo path of each car are printed on stderr. With `--fill N` the
car's photo is attached automatically unless `--photo` is given.

Credentials are never stored in the repository. The Drive client talks only to
`www.googleapis.com` (or a localhost test server), sends GET requests only, does not retry.
