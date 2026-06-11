"""Graph construction for Azure deployment workflow."""

from langgraph.graph import END, START, StateGraph
from langgraph.checkpoint.memory import InMemorySaver

from core.models import DeploymentAgentState
from workflow.nodes import (
    parse_user_input,
    generate_infra_code,
    build_bicep,
    refine_infra_code,
    #prevalidate_infra_code,
    human_review,
    deploy_infra_with_cli,
    verify_deployment
)
from workflow.edges import conditional_edge_build, conditional_edge_prevalidate


def create_deployment_graph():
    """Create and compile the deployment workflow graph."""
    # Create memory checkpointer
    memory = InMemorySaver()
    
    # Define the state graph
    graph = StateGraph(DeploymentAgentState)
    
    # Add all nodes
    graph.add_node("parse_user_input", parse_user_input)
    graph.add_node("generate_infra_code", generate_infra_code)
    graph.add_node("build_bicep", build_bicep)
    graph.add_node("refine_infra_code", refine_infra_code)
    #graph.add_node("prevalidate_infra_code", prevalidate_infra_code)
    graph.add_node("human_review", human_review)
    graph.add_node("deploy_infra_with_cli", deploy_infra_with_cli)
    graph.add_node("verify_deployment", verify_deployment)
    
    # Define the flow
    graph.add_edge(START, "parse_user_input")
    graph.add_edge("parse_user_input", "generate_infra_code")
    graph.add_edge("generate_infra_code", "build_bicep")
    graph.add_conditional_edges("build_bicep", conditional_edge_build)
    graph.add_edge("refine_infra_code", "build_bicep")
    #graph.add_conditional_edges("prevalidate_infra_code", conditional_edge_prevalidate)
    graph.add_edge("deploy_infra_with_cli", "verify_deployment")
    graph.add_edge("verify_deployment", END)
    
    # Compile the graph
    app = graph.compile(checkpointer=memory)
    
    return app


def get_graph_visualization():
    """Get Mermaid visualization of the graph."""
    app = create_deployment_graph()
    return app.get_graph().draw_mermaid()
