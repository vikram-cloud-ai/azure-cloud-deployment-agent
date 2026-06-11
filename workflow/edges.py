"""Conditional edge functions for workflow routing."""

from typing import Literal
from langgraph.graph import END

from core.models import DeploymentAgentState


def conditional_edge_build(state: DeploymentAgentState) -> Literal["human_review", "refine_infra_code", END]:
    """Route based on Bicep build status."""
    infra_build_status = state["infra_build_status"]
    if infra_build_status == "Pass":
        print("Build passed, proceeding to human review.")
        return "human_review"
    elif infra_build_status == "Fail":
        print("Build failed, refining infrastructure code.")
        return "refine_infra_code"
    else:
        return END


def conditional_edge_prevalidate(state: DeploymentAgentState) -> Literal["human_review", END]:
    """Route based on pre-validation status."""
    deploy_infra_validate_status = state["deploy_infra_validate_status"]
    if deploy_infra_validate_status == "Pass":
        print("Validation passed, proceeding to human review.")
        print("Needs approval")
        return "human_review"
    elif deploy_infra_validate_status == "Fail":
        print("Validation failed, Ending.")
        return END
