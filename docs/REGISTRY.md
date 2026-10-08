# Private vehicle registry enrichment

Official active vehicle resource: 053cea08-09bc-40ec-8f7a-156f0677aff3.
Official disability resource: c8b9f9c8-4612-4068-934f-d4acd2e3c06e.
API: https://data.gov.il/api/3/action/datastore_search
Scope: https://www.gov.il/he/departments/dynamiccollectors/private-and-commercial-vehicles
Live schema validation confirmed both resources on 2026-10-08. Active coverage is
private cars from 1996 and commercial vehicles up to 3500 kg from 1998. Missing
records do not prove invalid licensing or absence of disability eligibility.

The Action queries each plate exactly, once per resource. It saves plate,
manufacturer/model/commercial name/color/year (photo matching), last test date,
licence expiry, tag presence/type/issue date, check time and source IDs. No owner
identity/history or chassis is requested in the stored result. The official query
returns other fields, which are discarded. Tag type is preserved as a raw code;
no unsupported interpretation is made. Licence status is compared with the check
date, not claimed as proof of the vehicle's state at the photograph time.

```
python -m parking_report.registry /private/report.json --output /private/registry.json
```

Run in the PRIVATE caller repository only. Never publish the JSON or copy it into
public posts beyond what the owner has approved. Municipal reports: when a report
record has a `registry` key (the lookup result), `intake.record_to_car` turns it into
Hebrew sentences with `describe_he` (make/model/colour, licence validity, last test
date, disability tag and its raw type code). The owner approved this on 2026-10-08;
owner/chassis data are still never requested. A vehicle with no match in the active dataset (for example pre-1996) or a failed lookup
is omitted from the text entirely; unknown is never worded as "no valid licence". The final text is still shown to the owner before filing and then
frozen as `approved_description`. Coordinates are never added to report text.
Data can be stale or incomplete; check unknown results before approving.
