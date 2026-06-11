"""Configuration for LLM and environment settings."""

import os
from langchain_openai import ChatOpenAI
from dotenv import load_dotenv

# Load environment variables
load_dotenv(override=True)


def get_llm():
    """Get configured LLM instance."""
    return ChatOpenAI(
        model=os.getenv("AZURE_DEPLOYMENT_NAME"),
        base_url=os.getenv("AZURE_OPENAI_ENDPOINT"),
        api_key=os.getenv("AZURE_OPENAI_KEY"),
        use_responses_api=True,
        reasoning_effort="low"
    )


def get_mcp_server_config():
    """Get MCP server configuration."""
    return {
        "azure": {
            "transport": "stdio",
            "command": "npx",
            "args": [
                "-y",
                "@azure/mcp@latest",
                "server",
                "start"
            ],
            "env": {
                "AZURE_CLIENT_ID": os.getenv("AZURE_CLIENT_ID", ""),
                "AZURE_CLIENT_SECRET": os.getenv("AZURE_CLIENT_SECRET", ""),
                "AZURE_TENANT_ID": os.getenv("AZURE_TENANT_ID", ""),
                "AZURE_USE_MSI": "true" if os.getenv("AZURE_USE_MSI") == "true" else "false"
            }
        }
    }
