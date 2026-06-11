"""Conditional edge functions for workflow routing."""

from typing import Literal
from langgraph.graph import END
from core.models import DeploymentAgentState


def conditional_edge_build(state: DeploymentAgentState) -> Literal["human_review", "refine_infra_code", END]:
    """Route based on Bicep build status."""
    infra_build_status = state["infra_build_status"]
    refinement_attempts = state.get("refinement_attempts", 0)

    if infra_build_status == "Pass":
        print("Build passed, proceeding to human review.")
        return "human_review"
    elif infra_build_status == "Fail":
        if refinement_attempts >= 5:
            print(f"❌ Maximum refinement attempts ({refinement_attempts}) reached. Stopping to prevent infinite loop.")
            print("Please review the errors and try again with a different approach.")
            return END
        else:
            print(f"Build failed, refining infrastructure code (attempt {refinement_attempts + 1} of 5).")
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
