# Deterministic policy v1 (AF-007)

`evaluate(ActionRequest, PolicyContext | None)` returns separate risk and decision.
`evaluate_json` additionally rejects malformed/oversized JSON and duplicate keys.
Invalid contracts raise PolicyInputError without fabricating IDs or an ALLOW.
The module is pure: no host reads, command execution, credentials or model calls.

Trusted context must supply run/scenario identity, environment, exact fixture-file,
service and check allowlists, additional protected paths, a minimum risk floor and
explicit isolation/test/baseline/rollback evidence (true/false/unknown). The runner,
not an adapter, supplies this context. Missing fields are validation failures;
missing/false evidence escalates. Agent precondition strings are never evidence.

Precedence: scope/capability/environment/target violations or prohibited/critical
actions BLOCK; missing required evidence ESCALATE; high risk or explicit approval
precondition REQUIRE_APPROVAL; exact ordinary sandbox matches ALLOW; all else BLOCK.
Deployment always needs observed tests, healthy baseline and rollback readiness.
Auth edits, deletion, global scope and irreversible mutations remain blocked.
An approval token alone never authorizes anything; AF-008 must validate synthetic
scope/expiry and cannot override BLOCK or ESCALATE. Only ALLOW has an allowed scope.

Risk takes the maximum of action class, impact, broad scope, reversibility,
protected path, simulated-production mutation and trusted minimum risk.
Conventional protected directories/manifests/lockfiles/CI/infrastructure names are
matched conservatively and case-insensitively. This is not semantic authentication
or secret detection: the trusted caller must populate additional protected_paths
and the minimum risk floor for fixture-specific hazards. Exact allowlists prevent
path-prefix grants. Filesystem containment remains the sandbox's responsibility.

Capabilities are exact tuples: read_file=(read), edit_file=(write), run_check=(check),
deploy_service=(deploy), delete_data=(delete), edit_authentication=(auth).
Targets must match the action's path/check/service/dataset argument. Context scopes
and values do not come from agent text. Unknown declared preconditions escalate.

Stable decision IDs identify run/scenario/action/risk/rule outcomes; they are not
cryptographic authorization tokens or complete action-content commitments. AF-008
must bind approvals/idempotency to the full action payload separately. Decision
identity deliberately does not hash arbitrary source content or token values.
The engine does not assert that any action ran or that any tests passed.
