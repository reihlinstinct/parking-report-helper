# Beit Shemesh backend, included but disabled (#363)

The owner approved including Beit Shemesh code in the reporting service on
2026-11-26, with three limits: not enabled, not Active, and no UI changes.
`parking_report.beit_shemesh` is an installed Python backend module, not an active
municipality or an operator command. Existing Jerusalem behavior is unchanged.

## What is included

`prepare_call(reporter, event, secret=...)` validates and prepares the Bina CRM
`insert_call.php` query contract offline. It supports either a street ID or
finite numeric coordinates, never both. Required names, mobile, description,
street and house number must be supplied explicitly. A national ID is not
needed and nonempty values are rejected. Up to four image URLs may be supplied
from the documented HTTPS upload origin. Excess images are rejected, not lost.
No image is uploaded, fetched or checked for existence.

The source is the existing resident-app research and prototype at
https://github.com/reihlinstinct/beit-shemesh-moked , revision
`3e03495e68f4c20d78c16458e64b2eedbc71b41b`.
The prototype documents the app protocol. It does not prove current endpoint
availability or the correctness of a particular report. This integration does
not copy its embedded credential, use real reporter data or repeat a test filing.
The older source design's statement that no report had been filed describes its
research date, not the service's later operational history.

## Execution is blocked

`ACTIVE` is false. `submit_call()` always raises `BeitShemeshDisabled`, before
validating inputs or constructing a network client. No environment variable,
`live=True`, credential, UI action or caller override enables it. There is no
Beit Shemesh CLI, HTTP route, deployment variable, scheduled job or municipality
registration. The module imports no network transport. It cannot perform
street-list reads, uploads, case creation, SMS/OTP requests or status lookups.

Tests block `urllib.request.urlopen` and use synthetic data. They check the
request shape, Hebrew encoding, location ambiguity, bad coordinates, missing
required fields, image validation, no truncation and unconditional refusal
under the prototype's old live environment flags.

## Privacy and future work

A prepared query contains reporter details, the description, image URLs and a
credential. Treat it as private. `PreparedCall` hides its parameters from its
representation, but callers must not print `encoded_query()`, persist it in a
public artifact, or turn it into a network request. This is an internal backend
contract, not authority to disclose or file anything.

Activation is a separate code change and owner decision. It would need an
approved reporter identity and exact report, a durable single-use claim before
every external effect, unchanged-evidence deduplication, no automatic retry
(including redirects), private receipt reconciliation, upload-result checks,
current protocol qualification and independent review. A historical accepted
test is not approval for another case. No activation is included here.
