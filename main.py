"""Main entry point for Azure deployment agent (CLI mode)."""

import sys
import os

# Add parent directory to path for imports to work when run as script
if __name__ == "__main__":
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import asyncio
from langgraph.types import Command

from core.models import DeploymentAgentState
from workflow.graph import create_deployment_graph, get_graph_visualization


async def main():
    """Run the deployment workflow from command line."""
    # Example deployment requests
    deployment_requests = [
        "Create a ADLS storage account named teststorageaccount16120 in resource group rg-aidemo in the East US region with standard performance and locally-redundant storage",
        # "create a key vault named kv-aidemo-140126 in resource group rg-aidemo in the East US region with standard tier and soft delete enabled",
        # "create an AppService Plan named appserviceplan-aidemo-290326 in resource group rg-aidemo in the East US region with B1 pricing tier. Disable Zone redundancy.",
        # "create an application insights resource named ai-aidemo-290326 in resource group rg-aidemo in the East US region",
        # "create a function app named funcapp-aidemo-10022026 in resource group rg-aidemo in the East US region with consumption plan and enable system assigned managed identity."
    ]
    
    # Get user input
    print("Azure Deployment Agent")
    print("=" * 50)
    print("\nExample requests:")
    for i, req in enumerate(deployment_requests, 1):
        print(f"{i}. {req[:100]}...")
    
    user_input = input("\nEnter your deployment request (or press Enter for default): ").strip()
    if not user_input:
        user_input = deployment_requests[0]
    
    # Create initial state
    initial_state: DeploymentAgentState = {
        "user_input": user_input
    }
    
    # Create and run the graph
    print("\nInitializing deployment workflow...")
    app = create_deployment_graph()
    
    # Print the graph visualization
    print("\n" + "=" * 50)
    print("Graph Visualization (Mermaid Format)")
    print("=" * 50)
    print("Copy the text below and paste it into https://mermaid.live to visualize:")
    print("=" * 50)
    print(app.get_graph().draw_mermaid())
    print("=" * 50)
    
    # Run with a thread_id for persistence
    config = {"configurable": {"thread_id": "cli-session-1"}}
    result = await app.ainvoke(initial_state, config)
    
    # Check if we hit the human review interrupt
    if "__interrupt__" in result:
        print("\n" + "=" * 50)
        print("HUMAN REVIEW REQUIRED")
        print("=" * 50)
        print(f"\nGenerated Bicep Code:\n{result['infra_code']}\n")
        
        approval = input("Approve deployment? (yes/no): ").strip().lower()
        
        # Resume with human decision
        human_response = Command(
            resume={
                "approved": approval in ["yes", "y", "true", "1"]
            }
        )
        
        final_result = await app.ainvoke(human_response, config)
        print("\n" + "=" * 50)
        print("FINAL RESULT")
        print("=" * 50)
        print(f"Deployment Status: {final_result.get('deployment_status', 'Unknown')}")
    else:
        print("\n⚠️ Workflow completed without reaching human review.")
        print("This may indicate a validation failure at an earlier step.")


# def print_graph():
#     """Print the graph visualization in Mermaid format."""
#     print("\n" + "=" * 50)
#     print("Graph Visualization (Mermaid Format)")
#     print("=" * 50)
#     print("Copy the text below and paste it into https://mermaid.live to visualize:")
#     print("=" * 50)
#     print(get_graph_visualization())
#     print("=" * 50)


if __name__ == "__main__":
    asyncio.run(main())
