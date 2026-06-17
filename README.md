# Azure Deployment Agent

An AI-powered Azure infrastructure deployment tool that uses LangGraph workflows and Azure MCP (Model Context Protocol) to automate resource deployments.

## LangChain and LangGraph in Brief

This project sits on top of the LangChain ecosystem. **LangChain** provides the building blocks for LLM applications, such as prompts, models, tools, and structured output. It is useful when you want to connect an LLM to external systems and give it reusable components for reasoning and action.

**LangGraph** builds on that foundation and adds workflow orchestration. Instead of treating an agent as a single black-box call, LangGraph models the application as a graph with explicit control flow and durable state. That makes it a strong fit for multi-step processes like infrastructure generation, validation, approval, and deployment.

Key LangGraph concepts used in this project:

- **State**: A shared data object that carries information between steps, such as the user request, generated Bicep, validation results, and deployment status.
- **Nodes**: Individual workflow steps that perform work, such as parsing user input, generating code, building templates, or deploying resources.
- **Edges**: Connections between nodes that define what runs next. Edges can be linear or conditional.
- **Conditional Routing**: Logic that chooses the next step based on the current state, for example retrying code refinement when a Bicep build fails or pausing for human approval before deployment.
- **Interrupts / Human-in-the-Loop**: A workflow can pause and wait for a human decision, then resume from the same point with the updated input.

In this Azure Deployment Agent, LangChain handles the LLM-driven tasks and tool integration, while LangGraph manages the end-to-end deployment workflow as a reliable, inspectable graph.

## Features

- 🤖 **Natural Language Processing**: Describe your infrastructure needs in plain English
- 📝 **Bicep Code Generation**: Automatically generates Azure Bicep templates
- ✅ **Validation Pipeline**: Multi-stage validation including build and pre-deployment checks
- 👤 **Human-in-the-Loop**: Review and approve generated code before deployment
- 🚀 **Automated Deployment**: Deploys resources to Azure using Azure CLI
- 📊 **Deployment Verification**: Verifies deployment status and outputs results
- 🖥️ **Multiple Interfaces**: CLI and Gradio web UI

## Architecture

The agent uses a LangGraph workflow with the following stages:

1. **Parse User Input**: Extracts deployment parameters from natural language
2. **Generate Infrastructure Code**: Creates Bicep templates using Azure MCP tools
3. **Build Bicep**: Validates Bicep syntax
4. **Refine Code** (if needed): Fixes syntax errors using LLM
5. **Pre-validate**: Validates deployment against Azure
6. **Human Review**: Pause for approval
7. **Deploy**: Executes deployment using Azure CLI
8. **Verify**: Confirms deployment status

## Project Structure

```
azure_deployment_agent/
├── core/                # Core components
│   ├── __init__.py      # Core package exports
│   ├── models.py        # Pydantic models and TypedDicts
│   ├── config.py        # LLM and MCP configuration
│   └── utils.py         # Helper functions (Azure CLI wrapper)
├── workflow/            # Workflow components
│   ├── __init__.py      # Workflow package exports
│   ├── nodes.py         # Workflow node functions
│   ├── edges.py         # Conditional edge routing
│   └── graph.py         # Graph construction and compilation
├── __init__.py          # Package initialization
├── main.py              # CLI entry point
├── gradio_app.py        # Web UI application
├── requirements.txt     # Python dependencies
├── .env.example         # Environment variables template
└── README.md            # This file
```

## Installation

1. Clone or copy the `azure_deployment_agent` folder to your system

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Set up environment variables:
```bash
# Copy the example file
cp .env.example .env

# Edit .env with your Azure OpenAI credentials
```

4. Ensure Azure CLI is installed and you're logged in:
```bash
az login
```

5. Install Node.js (required for Azure MCP server):
```bash
# Azure MCP server runs via npx
```

## Usage

### CLI Mode

Run the agent from the command line:

```bash
python main.py
```

You'll be prompted to enter a deployment request. Examples:
- "Create a storage account named mysa123 in rg-aidemo in East US with standard LRS"
- "Create a key vault named kv-demo-01 in rg-aidemo in West Europe with soft delete enabled"
- "Create an App Service Plan named asp-demo in rg-aidemo in East US with B1 tier"

View the workflow graph:
```bash
python main.py --graph
```

### Web UI Mode

Launch the Gradio interface:

```bash
python gradio_app.py
```

Then open your browser to the URL shown (typically http://127.0.0.1:7860)

### Programmatic Usage

```python
import asyncio
from azure_deployment_agent import create_deployment_graph, DeploymentAgentState

async def deploy():
    app = create_deployment_graph()
    
    initial_state = {
        "user_input": "Create a storage account named mysa in rg-demo in East US"
    }
    
    config = {"configurable": {"thread_id": "my-session"}}
    result = await app.ainvoke(initial_state, config)
    
    # Handle human review if needed
    if "__interrupt__" in result:
        # ... approve/reject logic
        pass

asyncio.run(deploy())
```

## Configuration

### Environment Variables

Required:
- `AZURE_OPENAI_ENDPOINT`: Your Azure OpenAI endpoint URL
- `AZURE_OPENAI_KEY`: Your Azure OpenAI API key

Optional (for Azure MCP authentication):
- `AZURE_CLIENT_ID`: Service principal client ID
- `AZURE_CLIENT_SECRET`: Service principal client secret
- `AZURE_TENANT_ID`: Azure tenant ID
- `AZURE_USE_MSI`: Set to "true" for managed identity authentication

### Supported Azure Resources

- Storage Accounts
- Key Vaults
- App Service Plans
- Application Insights
- Function Apps

## Development

### Adding New Resource Types

1. Update the `parsed_input` model in [core/models.py](core/models.py) with new fields
2. Update the parsing prompt in `parse_user_input` node in [workflow/nodes.py](workflow/nodes.py)
3. Test with example requests

### Customizing the Workflow

Modify [workflow/graph.py](workflow/graph.py) to:
- Add new nodes
- Change routing logic
- Add additional validation steps

## Requirements

- Python 3.9+
- Azure CLI
- Node.js (for Azure MCP server)
- Azure subscription with appropriate permissions
- Azure OpenAI service

## License

MIT License

## Contributing

Contributions are welcome! Please submit pull requests or open issues for bugs and feature requests.

## Troubleshooting

### Azure CLI Issues
- Ensure you're logged in: `az login`
- Check your subscription: `az account show`
- Verify permissions for resource group creation and deployments

### MCP Connection Issues
- Ensure Node.js is installed
- Check that `npx` is available in your PATH
- Verify Azure credentials if using service principal authentication

### Bicep Build Failures
- Check the generated Bicep code in the logs
- The agent will attempt to auto-fix common syntax errors
- Review Azure naming conventions and resource limits

## Support

For issues and questions, please open an issue in the repository or contact the maintainers.

# test commit