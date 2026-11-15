"""Risk classification never authorizes an action."""

from pathlib import PurePosixPath

from agentforge.core.schemas import ActionRequest
from agentforge.guardrails.taxonomy import RiskTier


def protected_path(path: str, extra: tuple[str, ...] = ()) -> bool:
    parts = PurePosixPath(path.casefold()).parts
    name = parts[-1]
    directories = {
        "auth",
        "authentication",
        "authorization",
        "secrets",
        ".github",
        ".gitlab",
        "policies",
        "guardrails",
        "sandbox",
        "infra",
        "infrastructure",
        "deployment",
        "deploy",
        ".aws",
    }
    names = {
        "pyproject.toml",
        "package.json",
        "package-lock.json",
        "yarn.lock",
        "pnpm-lock.yaml",
        "poetry.lock",
        "uv.lock",
        "pipfile",
        "pipfile.lock",
        "dockerfile",
        "compose.yaml",
        "docker-compose.yml",
        ".gitlab-ci.yml",
        "jenkinsfile",
        "auth.py",
        "policy.py",
        "gateway.py",
        "secrets.py",
    }
    return (
        bool(set(parts) & directories)
        or name in names
        or name.startswith((".env", "requirements"))
        or name.endswith((".tf", ".tfvars", ".lock"))
        or any(
            path.casefold() == p.casefold() or path.casefold().startswith(p.casefold() + "/")
            for p in extra
        )
    )


def classify(
    action: ActionRequest, minimum: RiskTier = RiskTier.LOW, protected_paths: tuple[str, ...] = ()
) -> RiskTier:
    action = ActionRequest.model_validate_json(action.model_dump_json())
    mutation = action.type not in {"read_file", "run_check"}
    risk = RiskTier.LOW if action.type == "read_file" else RiskTier.MEDIUM
    if "medium" in action.impact.model_dump().values():
        risk = max(risk, RiskTier.MEDIUM)
    if (
        action.type == "deploy_service"
        or (mutation and action.environment == "simulated-production")
        or action.blast_radius == "multiple_services"
        or action.reversibility == "conditional"
        or "high" in action.impact.model_dump().values()
        or (
            mutation
            and action.arguments.path is not None
            and protected_path(action.arguments.path, protected_paths)
        )
    ):
        risk = RiskTier.HIGH
    if (
        action.type in {"edit_authentication", "delete_data"}
        or action.blast_radius == "global"
        or (mutation and action.reversibility == "irreversible")
    ):
        risk = RiskTier.CRITICAL
    return max(risk, minimum)
