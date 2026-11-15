# AF-005 redaction and collector boundary — approved 2026-11-09

Scoped approval granted by the user on 2026-11-09: “lts implement”, directly
in response to this proposal. Implementation remains within the scope below.
No credentials will be read from the host, environment, browser or connected apps.
All redaction tests use synthetic strings. No dependencies or policy changes.

## Exact proposed scope and behavior

1. Add `src/agentforge/core/redaction.py` with a deterministic `Redactor` and a
   result containing sanitized JSON/text plus rule IDs/counts, never matched values.
   Optional literal strings come from the trusted caller; the module must not
   discover/read real secrets. Reject empty literals; match longest first.
2. Recursively sanitize JSON objects/lists and free-text fields before any
   persistence or hashing. Replace values under case-insensitive keys `password`,
   `passwd`, `secret`, `api_key`, `apikey`, `access_token`, `refresh_token`,
   `authorization`, `cookie`, `set-cookie`, and `approval_token`. Synthetic approval
   references become redacted references in evidence; execution inputs are unchanged.
3. For text, redact configured literal values, complete PEM private-key blocks,
   authorization Bearer/Basic values, and credential assignments for the keys above.
   Replace complete matched lines when a generic credential assignment is detected,
   preserving line breaks so file citations keep line numbers. Replacement marker
   `REDACTED` must itself pass Identifier fields when needed. Never log regex
   matches, raw exceptions containing input, or unsanitized fallback data.
4. Add the write side of `core/trace.py`: append hash-chained, versioned JSONL
   events only after sanitization and schema revalidation. Collector assigns event
   ID, run ID, UTC timestamp and monotonic sequence; agent claims and observed tool
   results use separate APIs, and agents cannot set the executor actor. Provenance
   still depends on trusted caller wiring; no Python method is a security boundary.
5. Add `core/evidence.py`: sanitize inspected text, patch diffs, command output and
   JSON snapshots before storing content-addressed artifacts and composing the
   strict EvidenceBundle. Snapshot/file revisions refer to **sanitized persisted
   bytes**, never falsely claim unchanged raw-source hashes. Include explicit
   redaction flags and rule notes. Treat hash changes as distinct evidence.
6. Final bundle writing uses atomic publication and rejects overwrite. Replay is
   read-only and checks sequence, run/parent IDs and hashes. A malformed sanitized
   contract fails closed before writes; do not silently omit a mandatory field.

Target tests: `tests/unit/test_redaction.py`, `test_trace.py`, `test_evidence.py`,
and an owned sandbox-to-collector integration test. Verify synthetic passwords,
headers, PEM blocks and literal strings are absent from every persisted artifact;
test newline preservation, nested payloads, partial text, Unicode, immutable refs,
failed-command output, false agent success claims, tampering, and interrupted writes.

## Risk and limits

Redaction is a deterministic best-effort filter, not comprehensive secret detection.
Unknown credential formats can be missed and benign text can be over-redacted.
This v0.1 collector is for owned synthetic data only. Do not enable production
collection based on these tests. Caller-supplied literal handling is sensitive,
so literals stay in memory and are never included in reports or exception text.
Hash chains detect accidental edits when anchored by a known revision; an attacker
who can rewrite the whole store and trusted anchor can forge a new chain.

Rollback: remove the new redaction/collector modules and tests; existing artifacts
remain untouched. No migration or destructive cleanup. The low-level artifact
store and read-only replay can be prepared independently, but no public evidence
collection or raw-data write integration is enabled before this approval.
