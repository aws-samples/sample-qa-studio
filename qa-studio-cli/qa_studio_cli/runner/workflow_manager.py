"""Nova Act workflow definition management for GA Service mode."""

import logging

logger = logging.getLogger(__name__)

# Nova Act GA is only available in us-east-1.  All Nova Act API calls
# (workflow definitions, CreateWorkflowRun) must target this region.
# The --region CLI flag controls the *browser execution* region, not
# the Nova Act API region.
NOVA_ACT_REGION = "us-east-1"


class WorkflowManager:
    """Manages Nova Act workflow definitions for GA Service mode."""

    def __init__(self):
        import boto3  # lazy import — runner extra

        self._client = boto3.client("nova-act", region_name=NOVA_ACT_REGION)

    def ensure_workflow(self, usecase_id: str) -> str:
        """Ensure workflow definition exists, return workflow name.

        Workflow names: 1-40 chars, a-z A-Z 0-9 - _ only.
        """
        workflow_name = "".join(
            c if c.isalnum() or c in "-_" else "-" for c in usecase_id
        )[:40]

        try:
            try:
                resp = self._client.get_workflow_definition(
                    workflowDefinitionName=workflow_name
                )
                logger.info(
                    "Workflow '%s' exists (ID: %s)",
                    workflow_name,
                    resp.get("id", "unknown"),
                )
            except self._client.exceptions.ResourceNotFoundException:
                logger.info("Creating workflow definition '%s'", workflow_name)
                self._client.create_workflow_definition(
                    name=workflow_name,
                    description=f"Nova Act workflow for usecase {usecase_id}",
                )
            except Exception as e:
                logger.warning(
                    "Could not check workflow definition: %s. Will attempt to use it anyway.",
                    e,
                )
        except Exception as e:
            logger.error("Error ensuring workflow definition: %s", e)
            raise

        return workflow_name
