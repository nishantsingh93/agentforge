# Offline reports and comparisons

Render an existing run or suite without Docker, model credentials, or execution:

```sh
.venv/bin/agentforge report <run-or-suite-id> --format html > report.html
.venv/bin/agentforge report <run-or-suite-id> --format json > report.json
.venv/bin/agentforge compare <baseline-id> <current-id> > comparison.json
.venv/bin/agentforge report <current-id> --baseline <baseline-id> > comparison.html
```

Use `--runs-root PATH` to select the parent directory containing the IDs. Output
is written to stdout, so artifacts can be retained in CI without changing workflow
files. Redirect to a new destination, not an input artifact such as a run's
`report.json`: shell redirection occurs before the report loader reads its inputs.
Successful rendering exits 0 regardless of evaluation verdict; the report retains
the evaluation exit code. Invalid IDs, formats, missing or inconsistent evidence
exit 2 with a generic diagnostic on stderr and no partial report on stdout.

JSON uses versioned `ReportDocument` / `Comparison` models in the reporting
package, preserving the original RunReport and attempt records. JSON includes
validated evidence, files and trace events. HTML is self-contained and script-free;
all data is escaped, with a restrictive content security policy and internal
citations to digest-identified files and event IDs. It needs no CDN or network.
Keep the entire source run directory for the original immutable evidence.

Quality, safety, release decision and outcome remain separate. Offline scores and
confidence remain null/UNKNOWN. Failed attempts count in the outcome denominator
as UNKNOWN, rather than disappearing. All five outcome categories and UNKNOWN
are displayed, even with zero counts. A missing report on a recorded error is
explicitly unavailable; a supposedly completed attempt without a report is invalid.

Metric aggregation sums numerators and denominators and records observed/total
run coverage. Comparisons retain both populations and subtract rates only with
nonzero denominators and complete metric coverage. They never average per-run
percentages or impute missing metrics to zero. Quality deltas require known scores
and matching scenario populations. Configuration/population differences produce
warnings; deltas are descriptive, not a calibrated causal or release gate.

AF-014 currently records refused-action counts, not labeled unsafe-attempt or
unsafe-escape counts. Those two safety measurements explicitly show UNKNOWN;
refusals cannot establish either. Health/rollback sections show recorded snapshots
and the trace timeline; they do not infer recovery from an agent claim. Missing
semantic and operational observations remain unknown.

The loader validates strict source schemas, suite/attempt/report identity, unique
attempts, evidence hashes, trace chains, command observations and citations. It
rejects symlinked artifact components, path traversal, nonregular files and files
larger than 8 MiB. It reuses the existing evidence-context validation limit. Hashes
check internal consistency, not authenticity against wholesale artifact replacement.
Run roots and ancestors are operator-selected local paths. Input artifacts must
already have been sanitized by the evidence collector; reporting does not add a
new redaction policy. Python API renderers expect validated ReportDocument values.

## Verification

After [configuring the local sandbox](setup.md):

```sh
python -m pytest tests/integration/test_reporting_integration.py -ra
python -m build
```

Require zero skips for a real reporting integration claim. Unit tests exercise
recorded or mocked inputs and do not establish Docker isolation.
