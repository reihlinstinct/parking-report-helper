# Shared photo extension after a completed intake

- Issue: #293
- Status: proposal, pending owner sign-off
- Date: 2026-11-05
- Base measured: main `efda4ca3ca87e3002fea0eddba46b844114a157b` (reviewed baseline #294)

Not implemented. This document grants no live authority.

## Existing behavior

The shared-photo manifest in [SHARED-PHOTO.md](SHARED-PHOTO.md) already permits
exactly two distinct cars if both records are prepared before either reservation.
A record reserved without that manifest cannot acquire it retroactively because
its digest and relation are immutable. The existing behavior is correct and
must remain unchanged. The local operational runner may lag main; upgrading it
alone does not make an already-completed ordinary intake eligible for reuse.

## Goal and boundaries

Permit one explicitly approved, separately verified car in the unchanged
original of one completed ordinary vehicle intake. Do not change the original
photo bytes, parent payload digest, parent state, or original photo index.
Add a domain-separated photo-plus-plate guard key only to the private ledger;
never store raw plates or derived keys in public repositories or logs.
No general migration, arbitrary group growth, non-vehicle reuse or live test
submissions are in scope. An approval reference records evidence; the caller
must recover and verify that evidence independently before any live use.

## Duplicate guard identity and privacy

The owner-selected guard identity is a domain-separated SHA256 of the original
photo SHA256 and strictly normalized vehicle plate. Encode the tuple as canonical
UTF-8 JSON with fixed field names, sorted keys and fixed compact separators:
`{domain: parking-report/photo-vehicle/v1, photo_sha256: ..., plate: ...}`.
Hash that canonical encoding; do not concatenate ambiguous variable-length text.
The concrete JSON keys and domain string are a versioned contract covered by
synthetic test vectors. Preserve leading zeros and canonicalize standard plate
formatting before computing the key.

Store this derived key only in the PRIVATE operational ledger, in an optional
additive index from key to hashed intake ID. The public helper repository contains
code, design and synthetic tests only. No real plate, original photo hash,
derived guard key or reporter information belongs in public fixtures or logs.
The parent/child relationship remains plate-free. This intentionally changes the
previous no-derived-plate-values rule for this private index only; it does not
relax public output or diagnostics privacy.

Same original plus same plate is blocked under any different intake ID; unchanged
same-ID retries resume. Same original plus a different verified plate can be
reserved only within the one-extension bound and all parent-binding checks below.
A key alone is not proof that the plate is visible or that the target is distinct.
Neither changing a plate string nor cropping/re-encoding the source may be used
to evade the source-photo identity and evidence checks.

Residual risk: a person with the private ledger and original photo hash can guess
candidate plates from the small plate space. SHA256 is not encryption; domain
separation and a public salt do not prevent guessing. A private secret salt/HMAC
would improve resistance, but adds secret custody, rotation, cross-run consistency
and migration failure cases. Recommendation for this bounded feature: do not add
that machinery now. Keep the ledger private and diagnostics plate-free; revisit
HMAC as a separately reviewed privacy change if the exposure model changes.

## Proposed private manifest

A new `shared_photo_extension` field on the new record carries exactly:

- `parent_id`: opaque existing intake folder name.
- `parent_digest`: existing payload digest.
- No municipal case number in the manifest: municipal numbering is metadata,
  not duplicate identity.
- `photo_sha256`: unchanged original hash.
- `parent_plate` and `plate`: distinct strictly normalized standard plates.
- `authority_reference`: caller-verified approval evidence reference.

All fields and the new intake ID enter the new preview digest. The own plate
must match the new record; the parent plate must match the parent's structured
private record. Never parse plates from prose. Preserve leading zeros and reject
invalid or ambiguous normalization. Synthetic tests use shared synthetic-data
variables, not personal examples.

## Validation and reservation

1. Preview validates the new manifest and own record without reservation.
2. Live use requires the ordinary exact-digest gates plus an explicit
   extension-digest gate. Reject combination with `followup` or `shared_photo`.
3. Read the parent record from the same fixed sibling layout as #271, using the
   nonblocking regular-file reader from #284. Reject missing, unreadable,
   non-object or non-regular inputs without hanging. The new intake folder must
   sit beside the completed parent folder. A parent outside that layout is
   ineligible; support would require a future explicit path flag.
4. Require the new record's photo bytes to be identical to the parent's original
   photo. Check both originals have the declared hash and each record's plate
   matches the manifest. The 106-ledger parent entry is the source of truth for the submission digest;
   require the preserved private submission artifacts to corroborate that digest.
   Accept a recorded `report.json` submission digest or the original unchanged
   `municipal-payload.json` digest plus its saved submitted payload, matching the
   report description and subject/address fields. Both the ledger and preserved
   artifacts must match `parent_digest`. Recompute the payload digest through
   the existing preparation contract with the original photo and original
   reporter inputs; never print or persist those reporter secrets. A saved
   digest string alone is not sufficient corroboration. The corroborated and
   recomputed payload's plate must equal the parent record's structured plate
   and the manifest's `parent_plate`; fail closed on divergence. Missing original
   inputs, changed payload or conflicting records make the parent ineligible.
   A municipal reference is optional metadata and does not select the parent.
   Preserve its provenance verbatim, including an unverified FIFO association.
   This feature must never upgrade it to owner-attested or city-verified.
5. Under the existing ledger lock, verify remote head and parent identity. Parent
   must be complete, ordinary, own the original photo index, and match the exact
   stored digest/photo. An uncertain parent is not complete. Existing children,
   follow-ups or shared groups make the parent ineligible. Reconciliation is
   outside the scope of this feature.
6. Reserve one new intake, its private photo-plus-plate guard key, and a plate-free
   relation containing the parent key,
   parent digest, photo hash and authority reference. A separate bounded index
   prevents a second extension of the same original. This index is additive and
   optional, keeping ledger version 1 as `shared_photos` did. The parent key is the hashed
   intake ID, consistent with #271: it binds the relationship to the immutable
   ledger identity without copying intake names or plates into the relation.
   Parent entries and original
   photo index remain byte-for-byte unchanged.
7. Persist and verify remote acceptance before any municipal effect. Retry with
   the same intake and manifest resumes its checkpoint. A changed relation,
   renamed intake, different photo or second target fails closed.

The relation must not store either plate or the derived guard key; only the
private duplicate index stores that key. As in
#271, each retry rechecks both private records. An uncertain new create blocks
that intake without automatic retry; it never causes a parent resubmission.

```mermaid
flowchart TD
  A[New private record and extension manifest] --> B[Validate own and parent records]
  B --> C[Hash unchanged originals and compare distinct plates privately]
  C --> D[Lock and verify remote ledger]
  D --> E{Completed ordinary parent and no prior extension?}
  E -->|No| F[Fail closed]
  E -->|Yes| G[Persist one plate-free child relation]
  G --> H[Verify remote acceptance]
  H --> I[Create only the new case or resume its checkpoint]
```

## Tests first

Before implementation, add failing regression tests for:

- One completed ordinary parent plus one different plate succeeds; same plate,
  normalized spelling of the same plate, wrong hash/digest and missing
  authority reference fail before any fake create.
- Parent record plate diverging from the corroborated payload fails closed.
- Parent and original photo index stay unchanged; new member digest includes
  the full manifest and its ID.
- Same child retries resume; changed relation, renamed child, second extension,
  existing shared group or follow-up cannot add another case.
- Missing/FIFO/device parent records fail promptly; mismatched private records
  and changing parent files on retry fail closed.
- Stale/concurrent writers and uncertain remote writes block effects. Simulated
  interruption never repeats a completed create or original parent filing.
- Unknown legacy plate cannot be inferred. Non-vehicle behavior and all #271
  and follow-up tests remain unchanged. No raw plates enter the ledger; derived
  keys appear only in its private duplicate index, never public output or
  diagnostics.

Run unit and mocked functional suites, lint and type checks at the exact head.
Run the full suite in the Docker test target and inspect its real result. A
missing local container runtime is a verification gap, not a passing result.
CI and independent exact-head review remain merge gates. No live municipal
writes are allowed during tests.

## Revised review decisions (pending fresh independent review)

- Exactly one extension per ordinary photo is the initial bound.
- The guard key is the domain-separated hash of original photo hash plus
  normalized plate, stored only in the private ledger as specified above.
- Duplicate identity binds the internal parent intake ID, ledger digest and
  original photo, not the municipal case number. A FIFO reference may remain
  explicitly unverified metadata. It is never upgraded by reuse approval.
- Require explicit owner approval to use that exact unchanged original for the
  separately identified new car while leaving the parent untouched. The owner
  is approving the new action, not certifying an unknown municipal mapping.
- Parent digest comes from the 106-ledger entry, corroborated against preserved
  original private submission artifacts and recomputed original inputs. No
  retrospective field added to a parent can stand in for that evidence.
- Missing/conflicting original evidence still fails closed. This is not a
  migration and creates no general exception for every old intake.

Until this design is reviewed and implemented, use a separate original photo
or leave the new report pending. Even after implementation, these eligibility
rules still apply; the feature does not promise coverage for every old intake.
