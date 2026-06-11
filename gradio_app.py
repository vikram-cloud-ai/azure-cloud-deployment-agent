"""Gradio UI for Azure deployment agent."""

import sys
import os

# Add parent directory to path for imports to work when run as script
if __name__ == "__main__":
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import asyncio
import uuid
import io
import contextlib

import gradio as gr
from langgraph.types import Command

from core.models import DeploymentAgentState
from workflow.graph import create_deployment_graph


# Track active thread and pending interrupt state
active_thread_id = None
pending_interrupt = False
validation_passed = False

# Create the graph once at startup
app = create_deployment_graph()


async def run_workflow(user_prompt):
    """Run the LangGraph workflow from user prompt up to the human_review interrupt."""
    global active_thread_id, pending_interrupt, validation_passed
    
    validation_passed = False
    
    if not user_prompt.strip():
        return "Please enter a deployment request.", "", "", gr.update(interactive=False)
    
    active_thread_id = str(uuid.uuid4())
    thread_config = {"configurable": {"thread_id": active_thread_id}}
    
    initial_state: DeploymentAgentState = {"user_input": user_prompt}
    
    log_lines = []
    
    # Capture print output
    f = io.StringIO()
    with contextlib.redirect_stdout(f):
        result = await app.ainvoke(initial_state, thread_config)
    
    log_lines.append(f.getvalue())
    
    # Check if we hit the human_review interrupt (only reached when validation passed)
    interrupt_info = result.get("__interrupt__")
    infra_code = result.get("infra_code", "No infrastructure code generated.")
    validation_passed = result.get("deploy_infra_validate_status") == "Pass"
    
    if interrupt_info:
        pending_interrupt = True
        log_lines.append("\n⏸️ Workflow paused at human review. Review the Bicep code and Approve or Reject.")
    else:
        pending_interrupt = False
        log_lines.append("\n⚠️ Workflow completed without reaching human review (may have failed at an earlier step).")
    
    return "\n".join(log_lines), infra_code, "", gr.update(interactive=validation_passed)


async def approve_deployment():
    """Resume workflow with approval."""
    global active_thread_id, pending_interrupt
    
    if not pending_interrupt or not active_thread_id:
        return "No pending deployment to approve.", ""
    
    thread_config = {"configurable": {"thread_id": active_thread_id}}
    human_response = Command(resume={"approved": True})
    
    f = io.StringIO()
    with contextlib.redirect_stdout(f):
        final_result = await app.ainvoke(human_response, thread_config)
    
    pending_interrupt = False
    log_output = f.getvalue()
    
    status = final_result.get("deployment_status", "Unknown")
    log_output += f"\n\n{'='*50}\nFinal Deployment Status: {status}\n{'='*50}"
    
    return log_output, status


async def reject_deployment():
    """Resume workflow with rejection."""
    global active_thread_id, pending_interrupt
    
    if not pending_interrupt or not active_thread_id:
        return "No pending deployment to reject.", ""
    
    thread_config = {"configurable": {"thread_id": active_thread_id}}
    human_response = Command(resume={"approved": False})
    
    f = io.StringIO()
    with contextlib.redirect_stdout(f):
        final_result = await app.ainvoke(human_response, thread_config)
    
    pending_interrupt = False
    return f.getvalue() + "\n\n❌ Deployment rejected by user.", "Rejected"


def create_ui():
    """Create and return the Gradio UI."""
    with gr.Blocks(title="Azure Deployment Agent", theme=gr.themes.Soft()) as demo:
        gr.Markdown("# 🚀 Azure Infrastructure Deployment Agent")
        gr.Markdown("Enter a natural language request to deploy Azure resources. The agent will parse your request, generate Bicep code, validate it, and deploy after your approval.")
        
        with gr.Row():
            with gr.Column(scale=2):
                user_input = gr.Textbox(
                    label="Deployment Request",
                    placeholder="e.g., Create a storage account named mystorageacct01 in resource group rg-aidemo in East US with standard performance and LRS replication",
                    lines=3
                )
                submit_btn = gr.Button("🔄 Run Workflow", variant="primary")
            
            with gr.Column(scale=1):
                gr.Markdown("### Example Prompts")
                gr.Markdown("""
- Create a storage account named mysa123 in rg-aidemo in East US with standard LRS
- Create a key vault named kv-demo-01 in rg-aidemo in West Europe with soft delete enabled
- Create an App Service Plan named asp-demo in rg-aidemo in East US with B1 tier
- Create a function app named func-demo in rg-aidemo in East US with consumption plan and managed identity
                """)
        
        with gr.Row():
            workflow_log = gr.Textbox(label="Workflow Log", lines=15, interactive=False)
        
        with gr.Row():
            bicep_code = gr.Code(label="Generated Bicep Code", language=None, lines=20)
        
        with gr.Row():
            approve_btn = gr.Button("✅ Approve & Deploy", variant="primary", interactive=False)
            reject_btn = gr.Button("❌ Reject", variant="stop")
        
        with gr.Row():
            deploy_log = gr.Textbox(label="Deployment Log", lines=10, interactive=False)
            deploy_status = gr.Textbox(label="Deployment Status", interactive=False)
        
        # Wire up events
        submit_btn.click(
            fn=run_workflow,
            inputs=[user_input],
            outputs=[workflow_log, bicep_code, deploy_log, approve_btn]
        )
        
        approve_btn.click(
            fn=approve_deployment,
            inputs=[],
            outputs=[deploy_log, deploy_status]
        )
        
        reject_btn.click(
            fn=reject_deployment,
            inputs=[],
            outputs=[deploy_log, deploy_status]
        )
    
    return demo


def launch_app(share=False):
    """Launch the Gradio application."""
    demo = create_ui()
    demo.launch(share=share)


if __name__ == "__main__":
    launch_app(share=False)
