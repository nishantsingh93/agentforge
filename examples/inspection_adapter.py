"""An inspection proposal; no tools, file reads or execution claims."""

import hashlib

from agentforge.adapters.base import AdapterPlan, AdapterTask
from agentforge.core.schemas import ActionRequest, Arguments, Impact


class InspectionAdapter:
    def propose(self, task: AdapterTask) -> AdapterPlan:
        task = AdapterTask.model_validate_json(task.model_dump_json())
        path = {"F01": "orders.py", "F04": "service.py"}.get(task.scenario_id)
        if path is None:
            return AdapterPlan(
                schema_version="1", requests=(), claim="Unknown fixture; owner review needed."
            )
        identity = hashlib.sha256(task.model_dump_json().encode()).hexdigest()
        request = ActionRequest(
            schema_version="1",
            action_id="inspect-" + identity,
            type="read_file",
            arguments=Arguments(path=path),
            target=path,
            environment="sandbox",
            requested_capabilities=("read",),
            blast_radius="single_file",
            reversibility="reversible",
            impact=Impact(availability="none", data="none", revenue="none", security="none"),
            preconditions=(),
            approval_token=None,
            idempotency_key="inspect-" + identity,
            dry_run=True,
        )
        return AdapterPlan(
            schema_version="1",
            requests=(request,),
            claim="Inspection proposed only; no file was read, changed or verified.",
        )


if __name__ == "__main__":
    task = AdapterTask(
        schema_version="1",
        task_id="tutorial",
        scenario_id="F01",
        instruction="Inspect the null-handling task",
        source="Synthetic tutorial input",
    )
    print(InspectionAdapter().propose(task).model_dump_json(indent=2))
