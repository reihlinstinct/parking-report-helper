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

Run in the PRIVATE caller repository only. Never publish the JSON, copy it into
public posts, or append it automatically to municipal complaints. These data can
be stale/incomplete; unknown and failed matches need review. A disability tag alone
does not decide whether the photographed parking is legal. An expired licence is
not itself proof of the reported parking violation. The user's desired enforcement
purpose needs municipal category/requirements confirmation.

The private workflow should save registry.json in its private ledger branch,
never use it to mutate the original evidence, and exclude ledger commits from push
triggers. Mock unit tests require no network. This module does not file reports.
