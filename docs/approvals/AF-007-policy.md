# AF-007 — Proposed deterministic classifier and policy engine

Scoped human approval granted by the user’s “approve” response to this proposal.
Approved implementation is now applied and verified; see docs/tickets/AF-007.md.
AF-005 verification passed in the saved operator run. No repeat approval is required within
the exact scope below.
AGENTS.md protects policy enforcement and project plan section 13 requires an exact
proposal and risk assessment before application. Building subsequent tickets is not
blanket authorization for protected policy changes.

## Files and ownership

New guardrails/__init__.py, taxonomy.py, classifier.py, policy.py;
tests/unit/test_policy.py; docs/policy.md and ticket handoff. Existing schemas remain
unchanged. No dependency, CI, sandbox, credential, deployment or executor changes.
The policy is a pure function: it returns an existing PolicyDecision contract and a
separate typed risk classification. It never executes, reads host state or calls models.

## Proposed v1 rules, in precedence order

1. Revalidate action input against ActionRequest. Unknown action, missing fields,
   invalid enum, mismatched arguments or incomplete trusted context cannot ALLOW.
   Malformed requests return a distinct validation rejection, not a forged valid
   ActionRequest/PolicyDecision with invented IDs.
2. Trusted context identifies scenario/run, environment, exact permitted fixture
   file paths and services, enabled checks and protected paths. Request declarations
   cannot expand that context. Environment mismatch, target/argument inconsistency,
   traversal, out-of-scope paths/services/checks => BLOCK.
3. edit_authentication and delete_data => BLOCK in v0.1 regardless of supplied
   approval_token or favorable preconditions. Global blast radius and irreversible
   writes also BLOCK. There is no privileged production escape hatch.
4. Changes to protected scopes (auth, secrets, dependency manifests/lockfiles,
   CI/workflows, policy, sandbox, infrastructure) => REQUIRE_APPROVAL, provided the
   action is otherwise a supported disposable simulation and not already blocked.
   Plain token presence never satisfies approval. Approval validation belongs to
   AF-008; AF-007 alone cannot release these actions for execution.
5. deploy_service, any simulated-production mutation, multi-service mutation,
   conditional reversibility, high availability/data/revenue/security impact =>
   REQUIRE_APPROVAL; missing mandatory trusted execution evidence => ESCALATE.
   BLOCK always wins; absent required evidence cannot become an approval bypass.
6. A low-risk read of a trusted allowlisted fixture file or a named supported check
   in sandbox can ALLOW. A reversible single-file edit within the trusted fixture
   allowlist with no protected scope and no high impact can ALLOW. Requested
   capabilities must exactly match the action's supported capabilities.
7. Everything not explicitly allowed => BLOCK. Unknown evidence is not true.

Risk is the maximum dimension: read=low; ordinary edit/check=medium; deploy or
simulated-production mutation/conditional reversibility/multiple services/high
impact=high; auth/delete/global/irreversible mutation=critical. Higher risk never
weakens a decision. Return stable rule IDs, policy version, reason and only the
exact allowed scope for ALLOW; all other decisions have empty allowed_scope.
No numeric quality scores, model judgments or asserted test success authorize an action.

## Tests and risks

Table-driven tests for every action/risk tier; each missing context field; forged
precondition strings and approval tokens; unknown/malformed actions; environment
and target mismatch; every protected path family; scope/capability escalation;
precedence when multiple rules match; stable deterministic decisions; no mutation
of input. Property-style matrices verify increasing impact never reduces risk.
Run full pytest, strict typing, lint/format and build. Record actual outputs.

Risk: permissive path matching or trusting agent-supplied risk attributes could
allow a dangerous request. Mitigations: exact trusted allowlists, conservative
maximum classification and deny-by-default. Context still depends on trusted
runner wiring, tested later with AF-008. False positives are acceptable for v0.1
and must carry explicit reasons. No production safety claim.

Approval scope: implement precisely this AF-007 pure classifier/policy and tests.
AF-008 execution/approvals, sandbox changes, dependencies and CI require separate
proposals. Rollback: remove new unused modules; no data migration or cleanup.
