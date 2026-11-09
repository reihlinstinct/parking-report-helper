# Explicitly approved shared-photo issue pair

One unchanged original photo can ground two distinct non-vehicle municipal
issues, for example a missing sign and a missing bollard at one spot. Each
issue is its own intake with its own digest, receipt and state. The photo is
never re-encoded. A manifest is an audit record, never permission by itself.
Vehicle pairs keep using [shared photo](SHARED-PHOTO.md); a record with a
plate is refused here.

Both records carry the same `shared_photo_issue` with exactly `intake_ids`
(two distinct sorted folder names), `issues` (the two distinct `event_type`
values, same order), `photo_sha256` and `authority_reference`. Each record
needs an owner-chosen `municipal_subject` whose `event_type` matches its slot.

The manifest and the member's intake ID are bound into the preview digest. A
live member also needs `--approved-shared-issue-sha256` equal to that digest,
plus every normal gate. Previews never reserve a ledger slot.

Ledger: the group is recorded in `shared_photos[photo_hash]` with
`kind: "issue"`; the member entry gains `shared_issue`. A sibling check reads
the other member's record and refuses unless both manifests are identical.

Late join: the first issue may already be filed as an ordinary intake. The
second member may join only if the photo's origin intake is named by the
manifest, is `complete`, and has no other relation. The origin entry, digest,
state and the photo index are never rewritten. Any other already-claimed
photo stays refused.
