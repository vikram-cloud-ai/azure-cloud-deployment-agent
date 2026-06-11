"""Workflow node functions for Azure deployment agent."""

import os
import json
import tempfile
import subprocess
import time
import platform
from typing import Literal

from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain.messages import HumanMessage, SystemMessage
from langgraph.types import Command, interrupt
from langgraph.graph import END

from core.models import DeploymentAgentState, parsed_input
from core.config import get_llm, get_mcp_server_config
from core.utils import run_az_command


# Get LLM instance
llm = get_llm()


async def fetch_azure_best_practices(resource_type: str) -> str:
    """
    Optional: Fetch Azure best practices from official Microsoft Learn documentation.
    Uncomment and use this if you want to augment MCP tools with web documentation.
    
    Args:
        resource_type: Azure resource type (e.g., 'storage_account', 'key_vault')
    
    Returns:
        Best practices content from Microsoft Learn
    """
    # Mapping of resource types to Microsoft Learn URLs
    best_practices_urls = {
        "storage_account": "https://learn.microsoft.com/en-us/azure/storage/common/storage-security-guide",
        "key_vault": "https://learn.microsoft.com/en-us/azure/key-vault/general/best-practices",
        "app_service_plan": "https://learn.microsoft.com/en-us/azure/app-service/overview-hosting-plans",
        "function_app": "https://learn.microsoft.com/en-us/azure/azure-functions/functions-best-practices",
        "application_insights": "https://learn.microsoft.com/en-us/azure/azure-monitor/app/app-insights-overview"
    }
    
    # Get the URL for this resource type
    url = best_practices_urls.get(resource_type)
    if not url:
        return f"No best practices URL configured for resource type: {resource_type}"
    
    try:
        # This requires importing fetch_webpage
        # from tools import fetch_webpage
        # result = fetch_webpage(urls=[url], query="best practices bicep template")
        # return result
        
        # For now, return a placeholder - uncomment above when ready to use
        return f"Best practices documentation available at: {url}"
    except Exception as e:
        return f"Could not fetch best practices: {e}"


def validate_and_fix_api_versions(bicep_code: str, resource_type: str) -> str:
    """
    Validate and fix API versions in Bicep code to use known valid versions.
    This is a safety net for common resources. For new/unknown resources,
    the bicepschema MCP tool should provide the correct API version.
    
    Args:
        bicep_code: The generated Bicep template code
        resource_type: The Azure resource type being deployed
    
    Returns:
        Bicep code with corrected API versions
    """
    import re
    
    # Known valid API versions for common resources (updated May 2026)
    # This is a fallback - the bicepschema tool should be the primary source
    known_valid_versions = {
        # Compute
        "Microsoft.Compute/virtualMachines": "2024-03-01",
        "Microsoft.Compute/disks": "2024-03-01",
        
        # Storage
        "Microsoft.Storage/storageAccounts": "2024-01-01",
        
        # Security & Identity
        "Microsoft.KeyVault/vaults": "2023-07-01",
        "Microsoft.ManagedIdentity/userAssignedIdentities": "2023-01-31",
        
        # Web & App Services
        "Microsoft.Web/serverfarms": "2023-01-01",
        "Microsoft.Web/sites": "2023-12-01",
        
        # Networking
        "Microsoft.Network/virtualNetworks": "2024-01-01",
        "Microsoft.Network/networkSecurityGroups": "2024-01-01",
        "Microsoft.Network/publicIPAddresses": "2024-01-01",
        "Microsoft.Network/loadBalancers": "2024-01-01",
        
        # Databases
        "Microsoft.Sql/servers": "2023-08-01-preview",
        "Microsoft.DBforPostgreSQL/flexibleServers": "2023-06-01-preview",
        "Microsoft.DBforMySQL/flexibleServers": "2023-06-01-preview",
        "Microsoft.DocumentDB/databaseAccounts": "2024-05-15",
        
        # Monitoring
        "Microsoft.Insights/components": "2020-02-02",
        "Microsoft.OperationalInsights/workspaces": "2023-09-01",
        
        # Containers
        "Microsoft.ContainerRegistry/registries": "2023-07-01",
        "Microsoft.ContainerService/managedClusters": "2024-02-01",
        
        # AI & ML
        "Microsoft.CognitiveServices/accounts": "2024-04-01-preview",
        "Microsoft.MachineLearningServices/workspaces": "2024-04-01",
    }
    
    # Pattern to find resource type definitions with API versions
    pattern = r"(['\"]Microsoft\.\w+/[\w/]+)@(\d{4}-\d{2}-\d{2}(?:-preview)?)['\"]"
    
    def replace_version(match):
        resource_provider_with_quote = match.group(1)
        # Remove quotes to get clean provider name
        resource_provider = resource_provider_with_quote.strip("'\"")
        old_version = match.group(2)
        
        # Check if we have a known valid version for this provider
        if resource_provider in known_valid_versions:
            valid_version = known_valid_versions[resource_provider]
            if old_version != valid_version:
                print(f"⚠️  Fixing API version: {resource_provider}@{old_version} → @{valid_version}")
                # Preserve the quote style from original
                quote_char = resource_provider_with_quote[0]
                return f"{quote_char}{resource_provider}@{valid_version}{quote_char}"
        
        # If not in our known list, leave it as-is (trust bicepschema tool)
        return match.group(0)
    
    bicep_code = re.sub(pattern, replace_version, bicep_code)
    
    return bicep_code


def parse_user_input(state: DeploymentAgentState) -> DeploymentAgentState:
    """Parse user input into structured Pydantic model using LLM - supports ANY Azure service."""
    parse_prompt = f"""
    You are an expert in parsing user requests for Azure resource deployments.
    Analyze the user request and extract all relevant information to populate the appropriate fields.
    
    User Request: {state['user_input']}
    
    REQUIRED FIELDS - Always extract these:
    - resource_type: Identify the Azure resource type using underscore notation
      Examples: storage_account, key_vault, app_service_plan, application_insights, function_app,
                virtual_machine, virtual_network, sql_server, cosmos_db, container_registry,
                aks_cluster, redis_cache, postgresql_server, mysql_server, event_hub, etc.
      (This works for ANY Azure resource type, not just the examples listed)
    
    - parameters.location: Azure region in lowercase without spaces
      Examples: "eastus", "westeurope", "southeastasia", "westus2"
      Convert friendly names: "East US" → "eastus", "West Europe" → "westeurope"
    
    - parameters.name: The specific resource name provided in the request
    
    - parameters.resource_group: Resource group name (default: "rg-deployment-test" if not mentioned)
    
    OPTIONAL COMMON FIELDS (directly under parameters):
    - subscription: Azure subscription name or ID
    - sku: SKU/pricing tier (e.g., "Standard_LRS", "Basic", "S1", "Premium", "B2s")
    - tier: Pricing tier category (e.g., "Basic", "Standard", "Premium")
    - kind: Resource kind/variant (e.g., "StorageV2", "Linux", "Windows", "web")
    - capacity: Instance count or capacity units
    - tags: Resource tags as key-value pairs object
    
    SERVICE-SPECIFIC PROPERTIES (under parameters.properties as a LIST of key-value objects):
    Extract ANY resource-specific properties mentioned in the request.
    
    Common property examples (extract if mentioned):
    - Storage: replication_type, access_tier, performance, enable_https_traffic_only, min_tls_version, allow_blob_public_access
    - Key Vault: soft_delete_enabled, soft_delete_retention_days, purge_protection_enabled, enable_rbac_authorization
    - VMs: vm_size, os_disk_size, admin_username, ssh_key, image_reference, enable_accelerated_networking
    - Databases: backup_retention_days, geo_redundancy, firewall_rules, admin_login, version, collation
    - Networking: address_space, subnets, dns_servers, peering_enabled, address_prefix
    - Containers: node_count, kubernetes_version, network_plugin
    - App Services: runtime, runtime_version, always_on, app_service_plan_id, operating_system
    - Function Apps: runtime, enable_managed_identity, storage_account_name
    
    Each property in the properties array must be formatted as:
    {{"key": "property_name", "value": property_value}}
    
    CRITICAL AZURE-SPECIFIC RULES:
    
    1. Key Vault purgeProtection (CRITICAL - prevents deployment failures):
       - NEVER include {{"key": "purge_protection_enabled", "value": false}}
       - ONLY include {{"key": "purge_protection_enabled", "value": true}} if user EXPLICITLY requests it
       - If purge protection is not mentioned, OMIT this property completely
       - Reason: Once enabled, purgeProtection CANNOT be disabled (Azure hard limitation)
    
    2. Property naming:
       - Use snake_case for all property keys (enable_rbac_authorization, not enableRbacAuthorization)
       - Be consistent with Azure property naming conventions
    
    EXTRACTION RULES:
    - Only include fields explicitly mentioned or clearly implied in the request
    - Use snake_case for property names (e.g., soft_delete_enabled, not softDeleteEnabled)
    - Location should be lowercase without spaces (eastus, not "East US")
    - If a property isn't mentioned, don't include it (the Bicep generator will apply best practices)
    - Be flexible - this model should work for ANY Azure resource type
    - Don't limit yourself to predefined fields - extract whatever properties are mentioned
    
    IMPORTANT: This parser is generic and works for ALL Azure services.
    Extract the resource_type and any mentioned properties flexibly.
    """
    
    # Use structured output with Pydantic model
    structured_llm = llm.with_structured_output(parsed_input)
    parsed_data = structured_llm.invoke(parse_prompt)
    
    # Convert Pydantic model to dict and store in state
    state['input_parsed_json'] = parsed_data.model_dump(exclude_none=True)
    print("Parsed Input (Pydantic Model):\n", json.dumps(state['input_parsed_json'], indent=2))
    return state


async def generate_infra_code_mcp(state: DeploymentAgentState) -> DeploymentAgentState:
    """Generate Azure Bicep code using Azure CLI MCP tools and LLM."""
    print("Generating Azure Bicep code...")
    
    server_config = get_mcp_server_config()
    
    mcp_client = MultiServerMCPClient(server_config)
    all_tools = await mcp_client.get_tools()
    print(f"Loaded {len(all_tools)} MCP tools: {[t.name for t in all_tools]}")
    
    # Define your filtering logic and apply it
    # tools_to_keep = ["get_bestpractices", "group_list", "subscription_list", 
    #                  "bicepschema", "documentation", "azd", "cloudarchitect", 
    #                  "extension_cli_generate"]
    tools_to_keep = ["get_bestpractices", "group_list", "subscription_list", 
                     "bicepschema", "documentation", "azd", "cloudarchitect", 
                     "extension_cli_generate"]
    filtered_tools = [tool for tool in all_tools if tool.name in tools_to_keep]
    
    llm_azcli = llm
    llm_azcli.bind_tools(filtered_tools)
    
    system_msg_mcp = SystemMessage(
        "You are an Azure Bicep architect generating production-ready infrastructure templates for ANY Azure service.\n\n"
        
        "CRITICAL WORKFLOW - ALWAYS USE TOOLS (NON-NEGOTIABLE):\n"
        "1. ANALYZE the deployment request - identify the Azure resource type\n"
        "\n"
        "2. ⚠️  MANDATORY STEP 1 - USE 'bicepschema' tool:\n"
        "   - Call bicepschema with the resource type (e.g., 'Microsoft.KeyVault/vaults')\n"
        "   - This returns THE ONLY VALID API version you should use\n"
        "   - Extract valid API versions from the tool response\n"
        "   - Extract required and optional properties\n"
        "   - Extract property types and constraints\n"
        "   - DO NOT PROCEED without calling this tool first\n"
        "\n"
        "3. ⚠️  MANDATORY STEP 2 - USE 'get_bestpractices' tool:\n"
        "   - Call get_bestpractices for the resource type\n"
        "   - Get Azure best practices for this specific resource\n"
        "   - Get security recommendations\n"
        "   - Get configuration guidance\n"
        "\n"
        "4. OPTIONAL: USE 'documentation' tool if you need:\n"
        "   - Clarification on specific properties\n"
        "   - Examples or additional context\n"
        "\n"
        "5. GENERATE the Bicep template using ONLY the information from tools:\n"
        "   - Use the exact API version from bicepschema (not from memory)\n"
        "   - Follow the schema structure from bicepschema\n"
        "   - Apply best practices from get_bestpractices\n\n"
        
        "API VERSION RULES (CRITICAL - MUST FOLLOW):\n"
        "- MANDATORY: You MUST use the 'bicepschema' tool to get the correct API version\n"
        "- NEVER guess, assume, or hardcode API versions from memory\n"
        "- The bicepschema tool returns the exact, currently valid API versions for each resource type\n"
        "- Use the LATEST STABLE API version returned by bicepschema (avoid -preview unless requested)\n"
        "- Do NOT use outdated API versions - they will cause deployment failures\n"
        "- Example: For Microsoft.KeyVault/vaults, call bicepschema first to get the current API version\n\n"
        
        "AZURE WELL-ARCHITECTED FRAMEWORK (applies to ALL resources):\n"
        "Security:\n"
        "  - Enable managed identities where supported\n"
        "  - Use private endpoints for network isolation\n"
        "  - Enable encryption at rest and in transit\n"
        "  - Use latest TLS versions (TLS 1.2+)\n"
        "  - Disable public network access by default\n"
        "  - Apply principle of least privilege\n"
        "  - Never hardcode secrets (use listKeys(), Key Vault references)\n\n"
        
        "Reliability:\n"
        "  - Enable availability zones where applicable\n"
        "  - Use geo-redundancy for critical resources\n"
        "  - Configure backup and disaster recovery\n"
        "  - Enable diagnostic settings and logging\n\n"
        
        "Performance:\n"
        "  - Select appropriate SKU/tier for workload\n"
        "  - Enable caching mechanisms where available\n"
        "  - Optimize configuration for expected load\n\n"
        
        "Cost Optimization:\n"
        "  - Right-size resources based on requirements\n"
        "  - Use consumption/serverless tiers when appropriate\n"
        "  - Apply comprehensive tagging for cost allocation\n"
        "  - Enable auto-scaling where supported\n\n"
        
        "Operational Excellence:\n"
        "  - Enable comprehensive logging to Log Analytics\n"
        "  - Configure monitoring and alerting\n"
        "  - Use diagnostic settings\n"
        "  - Follow Azure naming conventions\n\n"
        
        "BICEP TEMPLATE STRUCTURE (universal best practices):\n"
        "Parameters:\n"
        "  - Add @description decorator for ALL parameters\n"
        "  - Use @secure() for sensitive values (passwords, keys, secrets)\n"
        "  - Add validation: @minLength, @maxLength, @allowed, @minValue, @maxValue\n"
        "  - Provide sensible defaults where appropriate\n"
        "  - Use param naming: camelCase\n\n"
        
        "Variables:\n"
        "  - Extract complex expressions into variables\n"
        "  - Use variables for reusable values\n"
        "  - Name variables descriptively in camelCase\n\n"
        
        "Resources:\n"
        "  - Use descriptive symbolic names (e.g., 'storageAccount', 'keyVault')\n"
        "  - Always use format: resourceName 'Microsoft.Provider/type@apiVersion'\n"
        "  - Apply all properties from user request\n"
        "  - Add security best practices by default\n"
        "  - Use string interpolation: '${{variable}}-suffix'\n\n"
        
        "Outputs:\n"
        "  - Export resource ID (always)\n"
        "  - Export connection endpoints/URLs\n"
        "  - Export important properties (keys via listKeys(), etc.)\n"
        "  - Add @description to all outputs\n\n"
        
        "Tagging:\n"
        "  - Include tags for: Environment, Owner, CostCenter, Project, CreatedBy\n"
        "  - Use consistent tag naming\n\n"
        
        "CRITICAL BICEP SYNTAX RULES (MUST FOLLOW):\n"
        "1. NEVER use 'scope' as a resource property:\n"
        "   - 'scope' is ONLY for module/extension deployments, NOT regular resources\n"
        "   - Regular Azure resources (storage, VMs, App Service Plans, etc.) CANNOT have a 'scope' property\n"
        "   - Resources are scoped by the deployment context, not by property\n"
        "   - WRONG: resource appPlan 'Microsoft.Web/serverfarms@2023-01-01' = { scope: resourceGroup(), ... }\n"
        "   - CORRECT: resource appPlan 'Microsoft.Web/serverfarms@2023-01-01' = { name: 'myplan', location: 'eastus', ... }\n"
        "   - Only use properties returned by bicepschema tool\n\n"
        
        "2. Resource property validation:\n"
        "   - ONLY use properties listed in bicepschema tool response for that specific resource type\n"
        "   - Common INVALID properties: 'scope', 'apiVersion', 'type' (these are part of declaration, not properties)\n"
        "   - Valid resource properties go inside the = { } block: name, location, sku, tags, properties, etc.\n"
        "   - Allowed top-level resource keywords (outside { }): 'existing', 'dependsOn', 'asserts', 'extendedLocation'\n"
        "   - If bicepschema doesn't list a property, DON'T use it\n\n"
        
        "3. Resource declaration format:\n"
        "   - CORRECT: resource <symbolic-name> '<resource-type>@<api-version>' = { name: '...', location: '...', properties: {...} }\n"
        "   - The resource type and API version go in the string after the symbolic name\n"
        "   - Resource properties (name, location, sku, tags, properties) go INSIDE the curly braces\n"
        "   - Example: resource kv 'Microsoft.KeyVault/vaults@2023-07-01' = { name: 'mykv', location: 'eastus', properties: {...} }\n\n"
        
        "CRITICAL RULES (known Azure limitations):\n"
        "1. Key Vault purge protection:\n"
        "   - NEVER set 'enablePurgeProtection: false' (causes deployment failure)\n"
        "   - Only include 'enablePurgeProtection: true' if explicitly requested\n"
        "   - If not requested, OMIT the property (defaults to false)\n"
        "   - This is IRREVERSIBLE once enabled\n\n"
        
        "2. Secrets and keys:\n"
        "   - Never use placeholder values like 'REPLACE_WITH_KEY'\n"
        "   - Use listKeys() for storage keys: storageAccount.listKeys().keys[0].value\n"
        "   - Use listSecrets() for other secrets\n"
        "   - Reference Key Vault for application secrets\n\n"
        
        "3. Naming constraints:\n"
        "   - Follow Azure naming rules for each resource type\n"
        "   - Storage accounts: lowercase, 3-24 chars, alphanumeric only\n"
        "   - Key Vaults: 3-24 chars, alphanumeric and hyphens\n"
        "   - Check bicepschema tool for specific constraints\n\n"
        
        "OUTPUT REQUIREMENTS:\n"
        "- Return ONLY valid Bicep code\n"
        "- No markdown code blocks (no ```bicep)\n"
        "- No explanatory text before or after the code\n"
        "- No comments about what tools you used\n"
        "- No JSON objects or tool call syntax\n"
        "- Use single quotes (') for all strings\n"
        "- Follow exact Bicep syntax from bicepschema tool\n"
        "- Apply best practices from get_bestpractices tool\n"
        "- Your final message must be PURE BICEP CODE ONLY\n"
        "- Start with parameters or resources, not explanatory text\n"
    )
    

    system_msg = SystemMessage(
          f"""
    You are an Azure Bicep architect generating production-ready infrastructure templates for ANY Azure service.
    Generate a syntactically correct Bicep template based on these requirements:
    {json.dumps(state['input_parsed_json'], indent=2)}
    
    CRITICAL BICEP SYNTAX RULES:
    1. Use ONLY single quotes (') for strings, NEVER double quotes (")
    2. Do NOT use dollar signs ($) except in string interpolation: '${{variable}}'
    3. Use camelCase for parameter and variable names
    4. Resource syntax: resourceName 'Microsoft.Provider/type@YYYY-MM-DD' = {{}}
    5. Parameter syntax: @description('...') param name type = defaultValue
    6. Variable syntax: var name = value
    7. Scope resources to resource group level only (no subscriptions or management groups)
    8. ALWAYS use 'az.environment()' NOT 'environment()' - this is CRITICAL
    9. For storage endpoints, use: az.environment().suffixes.storage
    10. Do NOT set the 'tier' property on storage SKU - it is read-only
    
    API VERSION RULES:
    - Use stable, well-tested API versions (avoid preview unless requested)
    - Common valid versions (use latest available for each resource type):
      * Storage Accounts: 2024-01-01
      * Key Vaults: 2023-07-01
      * Virtual Machines: 2024-03-01
      * App Service Plans: 2023-01-01
      * Function Apps (Web/sites): 2023-12-01
      * AKS: 2024-02-01
      * Cosmos DB: 2024-05-15
      * Virtual Networks: 2024-01-01
      * Application Insights: 2020-02-02
    - For other resources, use the latest stable API version
    
    REQUIRED TEMPLATE STRUCTURE:
    1. Parameters section:
       - Add @description decorator for ALL parameters
       - Use @secure() for sensitive values (passwords, keys, connection strings)
       - Add validation: @minLength, @maxLength, @allowed, @minValue, @maxValue
       - Provide sensible defaults
    
    2. Variables section (if needed):
       - Extract complex expressions into variables
       - Use for reusable values
       - Descriptive camelCase naming
    
    3. Resources section:
       - Use descriptive symbolic names (e.g., 'storageAccount', 'keyVault', 'virtualMachine')
       - Include ALL properties from user request
       - Apply security best practices by default
    
    4. Outputs section:
       - Export resource ID (always)
       - Export connection endpoints/URLs
       - Export important properties (use listKeys() for keys)
       - Add @description to all outputs
    
    AZURE WELL-ARCHITECTED FRAMEWORK (apply to ALL resources):
    
    Security:
    - Enable system-assigned managed identity ONLY for compute/PaaS services that support it:
      * App Services, Function Apps, Logic Apps, Container Apps
      * Azure VMs, Virtual Machine Scale Sets
      * Azure Kubernetes Service (AKS)
      * API Management, Azure Spring Apps
      * DO NOT enable for: Key Vault, Storage Accounts, Cosmos DB, or other infrastructure resources
    - Use private endpoints for network isolation
    - Enable encryption at rest and in transit
    - Use latest TLS version (minimumTlsVersion: 'TLS1_2' or higher)
    - Disable public network access by default
    - Apply principle of least privilege
    - NEVER hardcode secrets - use listKeys(), listSecrets(), or Key Vault references
    
    Reliability:
    - Enable availability zones where applicable
    - Use appropriate redundancy (LRS, ZRS, GRS for storage; geo-replication for databases)
    - Configure diagnostic settings to Log Analytics workspace
    - Enable backup and disaster recovery where applicable
    
    Performance:
    - Select appropriate SKU/tier for the workload
    - Enable caching mechanisms where available
    - Configure auto-scaling where supported
    
    Cost Optimization:
    - Right-size resources based on requirements
    - Use consumption/serverless tiers when appropriate
    - Apply comprehensive tagging for cost allocation
    
    Operational Excellence:
    - Enable comprehensive logging to Log Analytics
    - Configure monitoring and alerting
    - Follow Azure naming conventions
    - Add meaningful tags: Environment, Owner, CostCenter, Project
    
    CRITICAL RULES (known Azure limitations):
    
    1. Key Vault Purge Protection:
       - NEVER set 'enablePurgeProtection: false' (causes deployment failure)
       - Only include 'enablePurgeProtection: true' if explicitly requested
       - If not requested, OMIT this property entirely (defaults to false)
       - This is IRREVERSIBLE once enabled
    
    2. Secrets and Keys:
       - NEVER use placeholder values like 'REPLACE_WITH_KEY'
       - For storage keys: storageAccount.listKeys().keys[0].value
       - For other secrets: use appropriate list* functions
       - CRITICAL: Use 'az.environment()' NOT 'environment()' for endpoint suffixes
       - Example for Function App storage connection string:
         var storageConnectionString = 'DefaultEndpointsProtocol=https;AccountName=${{storageAccount.name}};AccountKey=${{storageAccount.listKeys().keys[0].value}};EndpointSuffix=${{az.environment().suffixes.storage}}'
       - For connection strings in outputs:
         'DefaultEndpointsProtocol=https;AccountName=${{storageAccount.name}};AccountKey=${{listKeys(storageAccount.id, storageAccount.apiVersion).keys[0].value}};EndpointSuffix=${{az.environment().suffixes.storage}}'
    
    3. Naming Constraints (follow Azure rules for each resource):
       - Storage accounts: lowercase, 3-24 chars, alphanumeric only, globally unique
       - Key Vaults: 3-24 chars, alphanumeric and hyphens, globally unique
       - VMs: 1-64 chars for Windows, 1-15 chars for Linux
       - Check Azure documentation for specific resource naming rules
    
    4. Common Best Practice Patterns:
       - Storage: enableHttpsTrafficOnly: true, minimumTlsVersion: 'TLS1_2', allowBlobPublicAccess: false
       - Key Vault: enableSoftDelete: true, softDeleteRetentionInDays: 90
       - VMs: Use managed disks, enable boot diagnostics, configure backups
       - Function Apps: Enable Application Insights, use consumption plan for cost savings
       - Databases: Enable backups, configure firewall rules, use geo-redundancy for production
    
    OUTPUT REQUIREMENTS:
    - Return ONLY valid Bicep code
    - No markdown code blocks (no ```bicep)
    - No explanatory text before or after the code
    - Must be syntactically valid and deployable
    - Apply best practices even if not explicitly requested
    """
    )

    human_msg = HumanMessage(
        f"Generate bicep schema for this deployment request: {state['input_parsed_json']}\n\n"
        "IMPORTANT: After using tools (bicepschema, get_bestpractices, documentation), "
        "your FINAL response must contain ONLY the complete Bicep code - no explanations, "
        "no markdown formatting, no tool calls in the final message. Just pure Bicep code."
    )
    
    messages = [system_msg, human_msg]
    result = await llm_azcli.ainvoke(messages)
    
    # Extract text content - handle different response formats
    text_content = None
    
    # Try different extraction methods
    if hasattr(result, 'content_blocks') and result.content_blocks:
        print(f"DEBUG: Found {len(result.content_blocks)} content blocks")
        # Get the LAST text block (after tool calls are done)
        text_blocks = [block.get('text', '') for block in result.content_blocks if block.get('type') == 'text']
        if text_blocks:
            # Take the longest text block (likely the Bicep code)
            text_content = max(text_blocks, key=len)
            print(f"DEBUG: Extracted text block with {len(text_content)} characters")
    
    # Fallback to .content attribute
    if not text_content and hasattr(result, 'content'):
        text_content = result.content
        print("DEBUG: Using result.content")
    
    # Validate we got something
    if not text_content or len(text_content.strip()) < 50:
        print("❌ ERROR: Failed to extract valid Bicep code from LLM response")
        print(f"Response type: {type(result)}")
        print(f"Response attributes: {dir(result)}")
        if hasattr(result, 'content_blocks'):
            print(f"Content blocks: {result.content_blocks}")
        state['infra_code'] = "// ERROR: Failed to generate Bicep code\n// Please try again"
        return state
    
    # Clean up the content - remove markdown code blocks if present
    text_content = text_content.strip()
    if text_content.startswith('```'):
        # Remove markdown code fence
        lines = text_content.split('\n')
        if lines[0].startswith('```'):
            lines = lines[1:]  # Remove first line (```bicep or ```)
        if lines and lines[-1].strip() == '```':
            lines = lines[:-1]  # Remove last line if it's ```
        text_content = '\n'.join(lines).strip()
    
    # Basic validation - check if it looks like Bicep code
    if not any(keyword in text_content for keyword in ['param ', 'resource ', 'output ', 'var ']):
        print("⚠️ WARNING: Generated content doesn't look like Bicep code")
        print(f"Content preview: {text_content[:200]}")
    
    print("\nGenerated Bicep Code:")
    print(text_content[:300] + "..." if len(text_content) > 300 else text_content)
    
    print("\n✅ Bicep code generation complete")
    
    state['infra_code'] = text_content
    return state


async def generate_infra_code(state: DeploymentAgentState) -> DeploymentAgentState:
    """Generate infrastructure code in Bicep for ANY Azure service using LLM."""
    print("Generating Infrastructure Code...", state['input_parsed_json'])
    
    # Initialize refinement counter
    state['refinement_attempts'] = 0
    
    infra_prompt = f"""
    You are an Azure Bicep architect generating production-ready infrastructure templates for ANY Azure service.
    Generate a syntactically correct Bicep template based on these requirements:
    {json.dumps(state['input_parsed_json'], indent=2)}
    
    CRITICAL BICEP SYNTAX RULES:
    1. Use ONLY single quotes (') for strings, NEVER double quotes (")
    2. Do NOT use dollar signs ($) except in string interpolation: '${{variable}}'
    3. Use camelCase for parameter and variable names
    4. Resource syntax: resourceName 'Microsoft.Provider/type@YYYY-MM-DD' = {{}}
    5. Parameter syntax: @description('...') param name type = defaultValue
    6. Variable syntax: var name = value
    7. Scope resources to resource group level only (no subscriptions or management groups)
    8. ALWAYS use 'az.environment()' NOT 'environment()' - this is CRITICAL
    9. For storage endpoints, use: az.environment().suffixes.storage
    10. Do NOT set the 'tier' property on storage SKU - it is read-only
    
    API VERSION RULES:
    - Use stable, well-tested API versions (avoid preview unless requested)
    - Common valid versions (use latest available for each resource type):
      * Storage Accounts: 2024-01-01
      * Key Vaults: 2023-07-01
      * Virtual Machines: 2024-03-01
      * App Service Plans: 2023-01-01
      * Function Apps (Web/sites): 2023-12-01
      * AKS: 2024-02-01
      * Cosmos DB: 2024-05-15
      * Virtual Networks: 2024-01-01
      * Application Insights: 2020-02-02
    - For other resources, use the latest stable API version
    
    REQUIRED TEMPLATE STRUCTURE:
    1. Parameters section:
       - Add @description decorator for ALL parameters
       - Use @secure() for sensitive values (passwords, keys, connection strings)
       - Add validation: @minLength, @maxLength, @allowed, @minValue, @maxValue
       - Provide sensible defaults
    
    2. Variables section (if needed):
       - Extract complex expressions into variables
       - Use for reusable values
       - Descriptive camelCase naming
    
    3. Resources section:
       - Use descriptive symbolic names (e.g., 'storageAccount', 'keyVault', 'virtualMachine')
       - Include ALL properties from user request
       - Apply security best practices by default
    
    4. Outputs section:
       - Export resource ID (always)
       - Export connection endpoints/URLs
       - Export important properties (use listKeys() for keys)
       - Add @description to all outputs
    
    AZURE WELL-ARCHITECTED FRAMEWORK (apply to ALL resources):
    
    Security:
    - Enable system-assigned managed identity ONLY for compute/PaaS services that support it:
      * App Services, Function Apps, Logic Apps, Container Apps
      * Azure VMs, Virtual Machine Scale Sets
      * Azure Kubernetes Service (AKS)
      * API Management, Azure Spring Apps
      * DO NOT enable for: Key Vault, Storage Accounts, Cosmos DB, or other infrastructure resources
    - Use private endpoints for network isolation
    - Enable encryption at rest and in transit
    - Use latest TLS version (minimumTlsVersion: 'TLS1_2' or higher)
    - Disable public network access by default
    - Apply principle of least privilege
    - NEVER hardcode secrets - use listKeys(), listSecrets(), or Key Vault references
    
    Reliability:
    - Enable availability zones where applicable
    - Use appropriate redundancy (LRS, ZRS, GRS for storage; geo-replication for databases)
    - Configure diagnostic settings to Log Analytics workspace
    - Enable backup and disaster recovery where applicable
    
    Performance:
    - Select appropriate SKU/tier for the workload
    - Enable caching mechanisms where available
    - Configure auto-scaling where supported
    
    Cost Optimization:
    - Right-size resources based on requirements
    - Use consumption/serverless tiers when appropriate
    - Apply comprehensive tagging for cost allocation
    
    Operational Excellence:
    - Enable comprehensive logging to Log Analytics
    - Configure monitoring and alerting
    - Follow Azure naming conventions
    - Add meaningful tags: Environment, Owner, CostCenter, Project
    
    CRITICAL RULES (known Azure limitations):
    
    1. Key Vault Purge Protection:
       - NEVER set 'enablePurgeProtection: false' (causes deployment failure)
       - Only include 'enablePurgeProtection: true' if explicitly requested
       - If not requested, OMIT this property entirely (defaults to false)
       - This is IRREVERSIBLE once enabled
    
    2. Secrets and Keys:
       - NEVER use placeholder values like 'REPLACE_WITH_KEY'
       - For storage keys: storageAccount.listKeys().keys[0].value
       - For other secrets: use appropriate list* functions
       - CRITICAL: Use 'az.environment()' NOT 'environment()' for endpoint suffixes
       - Example for Function App storage connection string:
         var storageConnectionString = 'DefaultEndpointsProtocol=https;AccountName=${{storageAccount.name}};AccountKey=${{storageAccount.listKeys().keys[0].value}};EndpointSuffix=${{az.environment().suffixes.storage}}'
       - For connection strings in outputs:
         'DefaultEndpointsProtocol=https;AccountName=${{storageAccount.name}};AccountKey=${{listKeys(storageAccount.id, storageAccount.apiVersion).keys[0].value}};EndpointSuffix=${{az.environment().suffixes.storage}}'
    
    3. Naming Constraints (follow Azure rules for each resource):
       - Always follow the Azure naming rules for the specific resource type being deployed
       - Storage accounts: lowercase, 3-24 chars, alphanumeric only, globally unique
       - Key Vaults: 3-24 chars, alphanumeric and hyphens, globally unique
       - VMs: 1-64 chars for Windows, 1-15 chars for Linux
       - App Service / Function App: 2-60 chars, alphanumeric and hyphens
       - For any other resource type, apply its documented Azure naming constraints
    
    4. Common Best Practice Patterns (apply relevant ones for the resource being deployed):
       - Storage: enableHttpsTrafficOnly: true, minimumTlsVersion: 'TLS1_2', allowBlobPublicAccess: false
       - Key Vault: enableSoftDelete: true, softDeleteRetentionInDays: 90
       - VMs: Use managed disks, enable boot diagnostics, configure backups
       - Function Apps: Enable Application Insights, use consumption plan for cost savings
       - Databases: Enable backups, configure firewall rules, use geo-redundancy for production
       - Networking: Apply NSG rules, enable DDoS protection where appropriate
       - Containers/AKS: Enable RBAC, use managed identity, configure network policy
       - For ANY other Azure service: enable encryption at rest and in transit, configure
         diagnostic settings to Log Analytics, disable public network access by default,
         apply minimum TLS where applicable, and follow the resource-specific WAF guidance
    
    OUTPUT REQUIREMENTS:
    - Return ONLY valid Bicep code
    - No markdown code blocks (no ```bicep)
    - No explanatory text before or after the code
    - Must be syntactically valid and deployable
    - Apply best practices even if not explicitly requested
    """

    response = llm.invoke(infra_prompt)
    state['infra_code'] = response.content
    print("Generated Infrastructure Code:\n", response.content)
    return state



def build_bicep(state: DeploymentAgentState) -> DeploymentAgentState:
    """Build Bicep file before deployment."""
    print("Building Bicep file...")
    
    try:
        with tempfile.NamedTemporaryFile(mode='w', suffix='.bicep', delete=False, encoding='utf-8') as f:
            f.write(state['infra_code'])
            bicep_file = f.name
        
        # Build using Azure CLI with the helper function
        result = run_az_command(["bicep", "build", "--file", bicep_file, "--stdout"])
        
        os.unlink(bicep_file)
        
        if result.returncode == 0:
            print("✅ Bicep build succeeded")
            state['infra_build_status'] = "Pass"
            state['build_error'] = ""  # Clear any previous errors
        else:
            print("❌ Bicep build failed:")
            error_msg = result.stderr if result.stderr else "Unknown build error"
            print(error_msg)
            state['infra_build_status'] = "Fail"
            state['build_error'] = error_msg  # Store error for refinement
            
    except Exception as e:
        print(f"Error during build: {e}")
        state['infra_build_status'] = "Fail"
        state['build_error'] = str(e)
    
    return state


def refine_infra_code_mcp(state: DeploymentAgentState) -> DeploymentAgentState:
    """Refine infrastructure code based on validation results using LLM."""
    print("Refining Infrastructure Code based on validation results...")
    
    # Get the build error if available
    build_error = state.get('build_error', '')
    
    refine_prompt = f"""
    You are an Azure Bicep architect. The following Bicep code has errors and must be fixed.
    
    Current Bicep Code:
    {state['infra_code']}
    
    Build Error (if any):
    {build_error}
    
    CRITICAL: ANALYZE THE ERROR MESSAGE FIRST
    - If error mentions "property ... is not allowed", REMOVE that property completely
    - If error is BCP037 (property not allowed), check bicepschema for valid properties
    - Common errors: using 'scope', 'apiVersion', 'type' as resource properties (INVALID)
    - Only use properties from the resource schema, not deployment metadata
    
    REFINING APPROACH:
    1. READ the error message carefully and understand what's wrong
    2. Fix the specific syntax errors mentioned in the error
    3. Remove any invalid properties (scope, apiVersion, type used as properties)
    4. Verify API versions are in correct format (YYYY-MM-DD or YYYY-MM-DD-preview)
    5. Ensure all properties are valid for the resource type
    6. Apply security best practices
    7. Follow Bicep coding standards
    
    BICEP SYNTAX REQUIREMENTS:
    - Use ONLY single quotes (') for strings, NEVER double quotes (")
    - No dollar signs ($) except in string interpolation: '${{variable}}'
    - camelCase for parameters, variables, and resource symbolic names
    - Resource syntax: resourceName 'Microsoft.Provider/type@YYYY-MM-DD' = {{}}
    - Parameter syntax: @description('...') param name type = defaultValue
    - Variable syntax: var name = value
    - API versions must be valid (YYYY-MM-DD format, actually supported by Azure)
    
    CRITICAL BICEP SYNTAX ERRORS TO FIX:
    
    1. REMOVE invalid properties (MOST COMMON ERROR):
       - NEVER use 'scope' as a resource property - it's NOT ALLOWED on regular resources
       - 'scope' is only for module/extension resources, NOT for Azure resources like storage, VMs, App Service Plans
       - If you see "scope: resourceGroup()" or "scope: subscription()" INSIDE a resource block, DELETE IT
       - Also remove if present as property: apiVersion, type, resourceType
       - Example: If error says "property 'scope' is not allowed", REMOVE the entire "scope: ..." line
    
    2. Resource structure (CORRECT FORMAT):
       - Declaration: resource <name> '<type>@<version>' = {{ name: '...', location: '...', ... }}
       - Properties go INSIDE the {{ }} block
       - Valid properties: name, location, tags, sku, kind, properties, identity, dependsOn
       - INVALID as properties (part of declaration): scope, type, apiVersion
    
    3. Property validation:
       - Only use properties that are documented for that specific Azure resource type
       - If error says "property X is not allowed on objects of type Y", DELETE property X
       - Don't guess - if you're unsure, check the bicepschema or omit the property
    
    AZURE WELL-ARCHITECTED FRAMEWORK (apply universally):
    
    Security:
    - Enable system-assigned managed identity where supported
    - Use private endpoints for network isolation
    - Enable encryption at rest and in transit
    - Set latest TLS version (minimumTlsVersion: 'TLS1_2' or higher)
    - Disable public network access unless explicitly required
    - Never use placeholder secrets - use listKeys(), listSecrets(), or Key Vault references
    - Apply principle of least privilege for access policies
    
    Reliability:
    - Enable diagnostic settings pointing to Log Analytics workspace
    - Use appropriate redundancy options (zone redundancy, geo-redundancy)
    - Configure backup where applicable
    - Enable monitoring and alerting capabilities
    
    Template Quality:
    - Add @description decorator to ALL parameters and outputs
    - Use @secure() for sensitive parameters (passwords, connection strings, keys)
    - Add parameter validation (@minLength, @maxLength, @allowed, @minValue, @maxValue)
    - Extract complex expressions into variables for readability
    - Add meaningful tags (Environment, Owner, CostCenter, Project)
    - Include comprehensive outputs (resource ID, endpoints, important properties)
    
    Performance & Cost:
    - Use appropriate SKU/tier for the workload
    - Enable auto-scaling where supported
    - Consider consumption-based pricing tiers
    
    OUTPUT REQUIREMENTS:
    - Return ONLY the corrected, production-ready Bicep code
    - No markdown code blocks or formatting (no ```bicep```)
    - No explanatory text before or after the code
    - Must be syntactically valid and deployable
    """
    response = llm.invoke(refine_prompt)
    
    # Extract text content robustly - handle different response formats
    text_content = None
    
    if hasattr(response, 'content_blocks') and response.content_blocks:
        # Get text blocks
        text_blocks = [block.get('text', '') for block in response.content_blocks if block.get('type') == 'text']
        if text_blocks:
            # Take the longest text block (likely the Bicep code)
            text_content = max(text_blocks, key=len)
    
    # Fallback to .content attribute
    if not text_content and hasattr(response, 'content'):
        text_content = response.content if isinstance(response.content, str) else str(response.content)
    
    # Validate we got something
    if not text_content or len(text_content.strip()) < 50:
        print("❌ ERROR: Failed to extract refined Bicep code from LLM response")
        # Keep the old code if refinement fails
        return state
    
    # Clean up the content - remove markdown code blocks if present
    text_content = text_content.strip()
    if text_content.startswith('```'):
        lines = text_content.split('\n')
        if lines[0].startswith('```'):
            lines = lines[1:]
        if lines and lines[-1].strip() == '```':
            lines = lines[:-1]
        text_content = '\n'.join(lines).strip()
    
    state['infra_code'] = text_content
    print("Refined Infrastructure Code:\n", text_content[:200] + "..." if text_content else "No content")
    return state


def refine_infra_code(state: DeploymentAgentState) -> DeploymentAgentState:
    """Refine infrastructure code based on validation results using LLM."""
    print("Refining Infrastructure Code based on validation results...")

    # Increment refinement counter
    current_attempts = state.get('refinement_attempts', 0)
    state['refinement_attempts'] = current_attempts + 1
    print(f"Refinement attempt {state['refinement_attempts']} of 5")
    
    # Get the build error if available
    build_error = state.get('build_error', '')
    
    refine_prompt = f"""
    You are an Azure Bicep architect. The following Bicep code has errors and must be fixed.
    This function handles ANY Azure service - apply the relevant guidance for the resource type present.
    
    Current Bicep Code:
    {state['infra_code']}
    
    Build Error (if any):
    {build_error}
    
    CRITICAL: ANALYZE THE ERROR MESSAGE FIRST
    - If error mentions "property ... is not allowed", REMOVE that property completely
    - If error is BCP037 (property not allowed), the property is invalid for this resource type - remove it
    - Common errors: using 'scope', 'apiVersion', 'type' as resource properties (INVALID)
    - Only use properties that are valid for the specific Azure resource type in the schema
    
    REFINING APPROACH:
    1. READ the error message carefully and understand what's wrong
    2. Fix the specific syntax errors mentioned in the error
    3. Remove any invalid properties (scope, apiVersion, type used as properties)
    4. Verify API versions are in correct format (YYYY-MM-DD or YYYY-MM-DD-preview)
    5. Ensure all properties are valid for the resource type
    6. Apply security best practices
    7. Follow Bicep coding standards
    
    BICEP SYNTAX REQUIREMENTS:
    - Use ONLY single quotes (') for strings, NEVER double quotes (")
    - No dollar signs ($) except in string interpolation: '${{variable}}'
    - camelCase for parameters, variables, and resource symbolic names
    - Resource syntax: resourceName 'Microsoft.Provider/type@YYYY-MM-DD' = {{}}
    - Parameter syntax: @description('...') param name type = defaultValue
    - Variable syntax: var name = value
    - Scope resources to resource group level only (no subscriptions or management groups)
    - ALWAYS use 'az.environment()' NOT 'environment()' - this is CRITICAL
    - For storage endpoints, use: az.environment().suffixes.storage
    - Do NOT set the 'tier' property on storage SKU - it is read-only
    
    API VERSION RULES:
    - Use stable, well-tested API versions (avoid preview unless the existing code already uses preview)
    - Common valid versions (reference only - verify for the specific resource type):
      * Storage Accounts: 2024-01-01
      * Key Vaults: 2023-07-01
      * Virtual Machines: 2024-03-01
      * App Service Plans: 2023-01-01
      * Function Apps (Web/sites): 2023-12-01
      * AKS: 2024-02-01
      * Cosmos DB: 2024-05-15
      * Virtual Networks: 2024-01-01
      * Application Insights: 2020-02-02
    - For any other resource type, use the latest known stable API version
    
    CRITICAL BICEP SYNTAX ERRORS TO FIX:
    
    1. REMOVE invalid properties (MOST COMMON ERROR):
       - NEVER use 'scope' as a resource property - it's NOT ALLOWED on regular resources
       - 'scope' is only for module/extension resources, NOT for regular Azure resources
       - If you see "scope: resourceGroup()" or "scope: subscription()" INSIDE a resource block, DELETE IT
       - Also remove if present as a property: apiVersion, type, resourceType
       - Example: If error says "property 'scope' is not allowed", REMOVE the entire "scope: ..." line
    
    2. Resource structure (CORRECT FORMAT):
       - Declaration: resource <name> '<type>@<version>' = {{ name: '...', location: '...', ... }}
       - Properties go INSIDE the {{ }} block
       - Valid top-level resource properties: name, location, tags, sku, kind, properties, identity, dependsOn
       - INVALID as properties (these are part of the declaration, not the body): scope, type, apiVersion
    
    3. Property validation:
       - Only use properties that are documented for that specific Azure resource type
       - If error says "property X is not allowed on objects of type Y", DELETE property X
       - If unsure whether a property is valid for the resource type, omit it
    
    AZURE WELL-ARCHITECTED FRAMEWORK (apply to ALL resources):
    
    Security:
    - Enable system-assigned managed identity ONLY for compute/PaaS services that support it:
      * App Services, Function Apps, Logic Apps, Container Apps
      * Azure VMs, Virtual Machine Scale Sets
      * Azure Kubernetes Service (AKS)
      * API Management, Azure Spring Apps
      * DO NOT enable for: Key Vault, Storage Accounts, Cosmos DB, or other infrastructure resources
    - Use private endpoints for network isolation
    - Enable encryption at rest and in transit
    - Set latest TLS version (minimumTlsVersion: 'TLS1_2' or higher) where applicable
    - Disable public network access unless explicitly required
    - Never use placeholder secrets - use listKeys(), listSecrets(), or Key Vault references
    - Apply principle of least privilege for access policies
    
    Reliability:
    - Enable diagnostic settings pointing to Log Analytics workspace
    - Use appropriate redundancy options (zone redundancy, geo-redundancy) for the resource type
    - Configure backup where applicable
    - Enable monitoring and alerting capabilities
    
    Template Quality:
    - Add @description decorator to ALL parameters and outputs
    - Use @secure() for sensitive parameters (passwords, connection strings, keys)
    - Add parameter validation (@minLength, @maxLength, @allowed, @minValue, @maxValue)
    - Extract complex expressions into variables for readability
    - Add meaningful tags (Environment, Owner, CostCenter, Project)
    - Include comprehensive outputs (resource ID, endpoints, important properties)
    
    Performance & Cost:
    - Use appropriate SKU/tier for the workload
    - Enable auto-scaling where supported
    - Consider consumption-based pricing tiers
    
    CRITICAL RULES (known Azure limitations):
    
    1. Key Vault Purge Protection:
       - NEVER set 'enablePurgeProtection: false' (causes deployment failure)
       - Only include 'enablePurgeProtection: true' if explicitly present in the original code
       - If not present, OMIT this property entirely (defaults to false)
       - This is IRREVERSIBLE once enabled
    
    2. Secrets and Keys:
       - NEVER use placeholder values like 'REPLACE_WITH_KEY'
       - For storage keys: storageAccount.listKeys().keys[0].value
       - For other secrets: use appropriate list* functions
       - CRITICAL: Use 'az.environment()' NOT 'environment()' for endpoint suffixes
       - Example for Function App storage connection string:
         var storageConnectionString = 'DefaultEndpointsProtocol=https;AccountName=${{storageAccount.name}};AccountKey=${{storageAccount.listKeys().keys[0].value}};EndpointSuffix=${{az.environment().suffixes.storage}}'
       - For connection strings in outputs:
         'DefaultEndpointsProtocol=https;AccountName=${{storageAccount.name}};AccountKey=${{listKeys(storageAccount.id, storageAccount.apiVersion).keys[0].value}};EndpointSuffix=${{az.environment().suffixes.storage}}'
    
    3. Naming Constraints (apply the relevant rules for the resource type being fixed):
       - Always follow the Azure naming rules for the specific resource type
       - Storage accounts: lowercase, 3-24 chars, alphanumeric only, globally unique
       - Key Vaults: 3-24 chars, alphanumeric and hyphens, globally unique
       - VMs: 1-64 chars for Windows, 1-15 chars for Linux
       - App Service / Function App: 2-60 chars, alphanumeric and hyphens
       - For any other resource type, apply its documented Azure naming constraints
    
    4. Common Best Practice Patterns (apply relevant ones for the resource being fixed):
       - Storage: enableHttpsTrafficOnly: true, minimumTlsVersion: 'TLS1_2', allowBlobPublicAccess: false
       - Key Vault: enableSoftDelete: true, softDeleteRetentionInDays: 90
       - VMs: Use managed disks, enable boot diagnostics, configure backups
       - Function Apps: Enable Application Insights, use consumption plan for cost savings
       - Databases: Enable backups, configure firewall rules, use geo-redundancy for production
       - Networking: Apply NSG rules, enable DDoS protection where appropriate
       - Containers/AKS: Enable RBAC, use managed identity, configure network policy
       - For ANY other Azure service: enable encryption, configure diagnostic settings,
         disable public network access by default, apply minimum TLS where applicable
    
    OUTPUT REQUIREMENTS:
    - Return ONLY the corrected, production-ready Bicep code
    - No markdown code blocks or formatting (no ```bicep```)
    - No explanatory text before or after the code
    - Must be syntactically valid and deployable
    """
    response = llm.invoke(refine_prompt)
    
    # Extract text content robustly - handle different response formats
    text_content = None
    
    if hasattr(response, 'content_blocks') and response.content_blocks:
        # Get text blocks
        text_blocks = [block.get('text', '') for block in response.content_blocks if block.get('type') == 'text']
        if text_blocks:
            # Take the longest text block (likely the Bicep code)
            text_content = max(text_blocks, key=len)
    
    # Fallback to .content attribute
    if not text_content and hasattr(response, 'content'):
        text_content = response.content if isinstance(response.content, str) else str(response.content)
    
    # Validate we got something
    if not text_content or len(text_content.strip()) < 50:
        print("❌ ERROR: Failed to extract refined Bicep code from LLM response")
        # Keep the old code if refinement fails
        return state
    
    # Clean up the content - remove markdown code blocks if present
    text_content = text_content.strip()
    if text_content.startswith('```'):
        lines = text_content.split('\n')
        if lines[0].startswith('```'):
            lines = lines[1:]
        if lines and lines[-1].strip() == '```':
            lines = lines[:-1]
        text_content = '\n'.join(lines).strip()
    
    state['infra_code'] = text_content
    print("Refined Infrastructure Code:\n", text_content[:200] + "..." if text_content else "No content")
    return state



def human_review(state: DeploymentAgentState) -> Command[Literal["deploy_infra_with_cli", "__end__"]]:
    """Pause for human review using interrupt and route based on decision."""
    
    # Print deployment summary
    print("\n" + "="*80)
    print("DEPLOYMENT SUMMARY")
    print("="*80)
    print(f"Resource Type: {state['input_parsed_json'].get('resource_type', 'Unknown')}")
    print(f"Resource Name: {state['input_parsed_json'].get('parameters', {}).get('name', 'Unknown')}")
    print(f"Location: {state['input_parsed_json'].get('parameters', {}).get('location', 'Unknown')}")
    print(f"Resource Group: {state['input_parsed_json'].get('parameters', {}).get('resource_group', 'Unknown')}")
    print(f"Build Status: {state.get('infra_build_status', 'N/A')}")
    print(f"Validation Status: {state.get('deploy_infra_validate_status', 'N/A')}")
    print("="*80)
    
    # Print the generated Bicep code to console for review
    print("\nGENERATED BICEP CODE FOR REVIEW:")
    print("-"*80)
    print(state['infra_code'])
    print("-"*80)
    print("\n⏸️  Waiting for human approval...\n")
    
    # Interrupt() must come first (after prints) - any code before it will re-run on resume
    human_decision = interrupt({
        "generated_infra_code": state['infra_code'],
        "action": "Please review and approve/edit this response"
    })

    # Now process the human's decision
    if human_decision.get("approved"):
        print("✅ Deployment approved by user")
        return Command(
            update=None,
            goto="deploy_infra_with_cli"
        )
    else:
        print("❌ Deployment rejected by user. Ending process.")
        return Command(
            update=None,
            goto=END
        )


def deploy_infra_with_cli(state: DeploymentAgentState) -> DeploymentAgentState:
    """Deploy infrastructure using Azure CLI."""
    print("\n" + "="*80)
    print("DEPLOYING INFRASTRUCTURE TO AZURE")
    print("="*80)
    
    try:
        # Validate the Bicep code has actual resources
        if not state.get('infra_code') or 'resource ' not in state['infra_code']:
            print("❌ ERROR: Bicep template has no resource definitions!")
            print("The generated code doesn't contain any Azure resources to deploy.")
            state['deployment_status'] = "Fail"
            return state
        
        # Save Bicep code to temporary file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.bicep', delete=False, encoding='utf-8') as f:
            f.write(state['infra_code'])
            bicep_file = f.name
        
        print(f"📄 Bicep template saved to: {bicep_file}")
        
        # Use configurable resource group name from parsed input
        resource_group = state['input_parsed_json']['parameters']['resource_group']
        deployment_name = f"deployment-{state['input_parsed_json']['parameters']['name']}"
        
        # Get location from parsed input, or default to resource group location
        location = state['input_parsed_json']['parameters'].get('location')
        
        if not location:
            print("📍 No location specified, checking resource group...")
            # Check if resource group exists and get its location
            rg_show = run_az_command([
                "group", "show",
                "--name", resource_group,
                "--query", "location",
                "--output", "tsv"
            ])
            
            if rg_show.returncode == 0 and rg_show.stdout.strip():
                location = rg_show.stdout.strip()
                print(f"✅ Using existing resource group location: {location}")
            else:
                # Resource group doesn't exist, use default location
                location = "eastus"
                print(f"⚠️  Resource group doesn't exist. Using default location: {location}")
        
        print(f"📦 Resource Group: {resource_group}")
        print(f"📍 Location: {location}")
        print(f"🏷️  Deployment Name: {deployment_name}")
        
        # Check if logged in to Azure using the helper function
        print("\n🔐 Checking Azure login status...")
        login_check = run_az_command(["account", "show"], timeout=10)
        
        if login_check.returncode != 0:
            print("❌ Not logged in to Azure. Please run 'az login' first.")
            print(f"Error: {login_check.stderr}")
            state['deployment_status'] = "Fail"
            os.unlink(bicep_file)
            return state
        
        # Get current subscription for logging
        subscription_info = json.loads(login_check.stdout)
        print(f"✅ Azure login verified")
        print(f"📋 Subscription: {subscription_info.get('name', 'Unknown')} ({subscription_info.get('id', 'Unknown')})")
        
        # Create resource group if it doesn't exist
        print(f"\n📁 Creating/verifying resource group '{resource_group}'...")
        rg_create = run_az_command([
            "group", "create",
            "--name", resource_group,
            "--location", location
        ], timeout=30)
        
        if rg_create.returncode == 0:
            print(f"✅ Resource group ready")
        else:
            print(f"❌ Resource group creation failed with code {rg_create.returncode}")
            if rg_create.stderr:
                print(f"Error: {rg_create.stderr}")
            state['deployment_status'] = "Fail"
            os.unlink(bicep_file)
            return state
        
        # Build parameters object from parsed input
        # Extract parameter names from Bicep code
        import re
        param_pattern = r"param\s+(\w+)\s+"
        bicep_params = re.findall(param_pattern, state['infra_code'])
        print(f"\n📝 Bicep template has {len(bicep_params)} parameters: {bicep_params}")
        
        # Build parameter values from our parsed input
        parameters = {}
        parsed_params = state['input_parsed_json'].get('parameters', {})
        
        # Map common parameter names
        param_mapping = {
            'name': parsed_params.get('name'),
            'location': location,
            'resourceName': parsed_params.get('name'),
            'resourceLocation': location,
            'storageAccountName': parsed_params.get('name'),
            'keyVaultName': parsed_params.get('name'),
            'appServicePlanName': parsed_params.get('name'),
            'functionAppName': parsed_params.get('name'),
            'sku': parsed_params.get('sku'),
            'skuName': parsed_params.get('sku'),
            'tier': parsed_params.get('tier'),
            'kind': parsed_params.get('kind'),
        }
        
        # Add parameters that exist in both the template and our data
        for param_name in bicep_params:
            if param_name in param_mapping and param_mapping[param_name]:
                parameters[param_name] = param_mapping[param_name]
        
        # Create parameters file if we have parameters
        params_file = None
        if parameters:
            print(f"📋 Providing parameters: {list(parameters.keys())}")
            params_content = {
                "$schema": "https://schema.management.azure.com/schemas/2019-04-01/deploymentParameters.json#",
                "contentVersion": "1.0.0.0",
                "parameters": {k: {"value": v} for k, v in parameters.items()}
            }
            
            with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False, encoding='utf-8') as pf:
                json.dump(params_content, pf, indent=2)
                params_file = pf.name
            print(f"📄 Parameters file saved to: {params_file}")
        else:
            print("⚠️  No parameters to provide (template might use defaults)")
        
        # # Validate the deployment first (quick check)
        # print(f"\n🔍 Validating deployment template...")
        # validate_cmd = [
        #     "deployment", "group", "validate",
        #     "--resource-group", resource_group,
        #     "--template-file", bicep_file,
        #     "--name", deployment_name
        # ]
        # if params_file:
        #     validate_cmd.extend(["--parameters", params_file])
        
        # validate_result = run_az_command(validate_cmd, timeout=120)
        
        # if validate_result.returncode != 0:
        #     print("❌ Template validation failed!")
        #     print("-"*80)
        #     if validate_result.stderr:
        #         print(validate_result.stderr)
        #     print("-"*80)
        #     print("\n💡 This usually means:")
        #     print("   - Invalid Bicep syntax")
        #     print("   - Missing required parameters")
        #     print("   - Invalid resource properties")
        #     print("   - API version issues")
        #     state['deployment_status'] = "Fail"
        #     os.unlink(bicep_file)
        #     if params_file:
        #         os.unlink(params_file)
        #     return state
        # else:
        #     print("✅ Template validation passed")
        
        # Deploy the Bicep template with extended timeout for deployment operations
        print(f"\n🚀 Starting deployment '{deployment_name}'...")
        print("⏳ This may take several minutes. Please wait...\n")
        
        deploy_cmd = [
            "deployment", "group", "create",
            "--resource-group", resource_group,
            "--template-file", bicep_file,
            "--name", deployment_name,
            "--mode", "Incremental",
            "--verbose"
        ]
        if params_file:
            deploy_cmd.extend(["--parameters", params_file])
        
        deploy_result = run_az_command(deploy_cmd, timeout=600)  # 10 minutes timeout
        
        # Clean up temp files
        os.unlink(bicep_file)
        if params_file:
            os.unlink(params_file)
        print(f"\n🗑️  Cleaned up temporary files")
        
        # Process deployment result
        print("\n" + "="*80)
        print("DEPLOYMENT RESULT")
        print("="*80)
        
        if deploy_result.returncode == 0:
            print("✅ Deployment completed successfully!")
            state['deployment_status'] = "Pass"
            
            # Parse deployment output to see what was deployed
            try:
                if deploy_result.stdout:
                    deploy_info = json.loads(deploy_result.stdout)
                    if 'properties' in deploy_info:
                        provisioning_state = deploy_info['properties'].get('provisioningState', 'Unknown')
                        print(f"📊 Provisioning State: {provisioning_state}")
                        
                        # Check outputs
                        if deploy_info['properties'].get('outputs'):
                            print("\n📤 Deployment Outputs:")
                            for key, value in deploy_info['properties']['outputs'].items():
                                print(f"   {key}: {value.get('value', 'N/A')}")
            except:
                pass  # If parsing fails, continue
            
            # List deployed resources
            print("\n📦 Listing deployed resources...")
            resource_list = run_az_command([
                "resource", "list",
                "--resource-group", resource_group,
                "--query", "[].{Name:name, Type:type, Location:location, ProvisioningState:provisioningState}",
                "--output", "table"
            ], timeout=30)
            
            if resource_list.returncode == 0 and resource_list.stdout:
                print(resource_list.stdout)
                
                # Check if any resources were actually created
                if "No resources found" in resource_list.stdout or len(resource_list.stdout.strip().split('\n')) <= 2:
                    print("\n⚠️  WARNING: Deployment succeeded but NO resources were created!")
                    print("This might indicate:")
                    print("   - The Bicep template has no resource definitions")
                    print("   - Resources already exist and deployment was a no-op")
                    print("   - The template only has outputs/variables")
            else:
                print("⚠️  Could not list resources")
                
        else:
            print("❌ Deployment failed!")
            state['deployment_status'] = "Fail"
            
            # Print stderr for immediate error info
            if deploy_result.stderr:
                print("\n❌ Error Output:")
                print("-"*80)
                print(deploy_result.stderr[:1000])  # First 1000 chars
                print("-"*80)
            
            # Get detailed error information from Azure
            print("\n🔍 Fetching detailed error information from Azure...")
            error_details = run_az_command([
                "deployment", "operation", "group", "list",
                "--resource-group", resource_group,
                "--name", deployment_name,
                "--query", "[?properties.provisioningState=='Failed'].{Resource:properties.targetResource.resourceName, Type:properties.targetResource.resourceType, Error:properties.statusMessage.error.message, Code:properties.statusMessage.error.code}",
                "--output", "table"
            ], timeout=30)
            
            if error_details.returncode == 0 and error_details.stdout:
                print("\n❌ Deployment Error Details:")
                print("-"*80)
                print(error_details.stdout)
                print("-"*80)
            
            # Also try to get the deployment details
            deployment_show = run_az_command([
                "deployment", "group", "show",
                "--resource-group", resource_group,
                "--name", deployment_name,
                "--query", "{state:properties.provisioningState, error:properties.error}",
                "--output", "json"
            ], timeout=30)
            
            if deployment_show.returncode == 0 and deployment_show.stdout:
                try:
                    deploy_status = json.loads(deployment_show.stdout)
                    if deploy_status.get('error'):
                        print("\n❌ Deployment Error:")
                        print(json.dumps(deploy_status['error'], indent=2))
                except:
                    pass
        
        print("="*80 + "\n")
            
    except subprocess.TimeoutExpired:
        print("\n❌ Deployment timed out after 10 minutes.")
        print("💡 The deployment might still be running in Azure.")
        print(f"Check status with: az deployment group show -g {resource_group} -n {deployment_name}")
        state['deployment_status'] = "Fail"
        # Clean up files
        try:
            os.unlink(bicep_file)
            if params_file:
                os.unlink(params_file)
        except:
            pass
    except Exception as e:
        print(f"\n❌ Unexpected error during deployment: {e}")
        import traceback
        traceback.print_exc()
        state['deployment_status'] = "Fail"
        # Clean up files
        try:
            os.unlink(bicep_file)
            if 'params_file' in locals() and params_file:
                os.unlink(params_file)
        except:
            pass
    
    return state


def verify_deployment(state: DeploymentAgentState) -> DeploymentAgentState:
    """Verify the deployment status using Azure CLI."""
    print("Verifying deployment status...")
    
    try:
        resource_group = state['input_parsed_json']['parameters']['resource_group']
        deployment_name = f"deployment-{state['input_parsed_json']['parameters']['name']}"
        
        # Get deployment details using az deployment show
        result = run_az_command([
            "deployment", "group", "show",
            "--resource-group", resource_group,
            "--name", deployment_name,
            "--query", "{provisioningState:properties.provisioningState, timestamp:properties.timestamp, duration:properties.duration, outputs:properties.outputs}",
            "--output", "json"
        ])
        
        if result.returncode == 0:
            deployment_info = json.loads(result.stdout)
            provisioning_state = deployment_info.get('provisioningState', 'Unknown')
            
            print(f"\n{'='*50}")
            print(f"Deployment Verification Results:")
            print(f"{'='*50}")
            print(f"Deployment Name: {deployment_name}")
            print(f"Resource Group: {resource_group}")
            print(f"Provisioning State: {provisioning_state}")
            print(f"Timestamp: {deployment_info.get('timestamp', 'N/A')}")
            print(f"Duration: {deployment_info.get('duration', 'N/A')}")
            
            if deployment_info.get('outputs'):
                print(f"\nOutputs:")
                for key, value in deployment_info['outputs'].items():
                    print(f"  {key}: {value.get('value', 'N/A')}")
            
            print(f"{'='*50}\n")
            
            if provisioning_state == "Succeeded":
                print("✅ Deployment verification: SUCCESS")
            else:
                print(f"⚠️ Deployment verification: {provisioning_state}")
        else:
            print("❌ Failed to verify deployment")
            print(f"Error: {result.stderr}")
            
    except Exception as e:
        print(f"Error during deployment verification: {e}")
    
    return {}
