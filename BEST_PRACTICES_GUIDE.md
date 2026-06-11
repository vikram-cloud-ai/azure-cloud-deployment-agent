# Azure Bicep Best Practices - Implementation Guide

## Overview
This guide explains how the Azure Deployment Agent generates production-ready Bicep templates following Azure best practices **without hardcoding service-specific instructions**.

## Strategy: Multi-Layered Best Practices Approach

### 1. **MCP Tools Integration** (Primary - Already Implemented)
The agent uses Azure MCP tools to dynamically fetch best practices and schemas:

#### Available Tools:
- `get_bestpractices` - Fetches Azure best practices for specific resource types
- `bicepschema` - Gets official Bicep schema with latest API versions
- `documentation` - Provides Azure documentation and guidance
- `cloudarchitect` - Offers architectural recommendations

#### How It Works:
The system message now instructs the LLM to:
1. **ANALYZE** the deployment request
2. **USE** `get_bestpractices` tool for the resource type
3. **USE** `bicepschema` tool for official schema
4. **USE** `documentation` tool for clarifications
5. **GENERATE** Bicep following retrieved best practices

#### Benefits:
✅ Always up-to-date (tools fetch latest information)
✅ No hardcoded service-specific rules
✅ Leverages official Azure guidance
✅ Works for any Azure service

---

### 2. **Azure Well-Architected Framework** (Universal Principles)
The system message includes framework principles that apply to ALL Azure resources:

#### Five Pillars:
1. **Security**
   - Use managed identities
   - Enable private endpoints
   - Encryption at rest
   - Disable public access by default

2. **Reliability**
   - Availability zones
   - Geo-redundancy
   - Backup/disaster recovery

3. **Performance**
   - Appropriate SKU/tier selection
   - Enable caching
   - Optimize configuration

4. **Cost Optimization**
   - Right-size resources
   - Use consumption plans
   - Apply cost tags

5. **Operational Excellence**
   - Comprehensive logging
   - Monitoring integration
   - Diagnostic settings

---

### 3. **Template Structure Best Practices** (Bicep-Specific)
Universal Bicep template quality standards:

- Latest stable API versions
- `@description` decorators for all parameters
- Parameter constraints (`@minLength`, `@maxLength`, `@allowed`)
- Meaningful variable names
- Comprehensive outputs
- `@secure()` decorator for sensitive data
- Proper tagging strategy

---

### 4. **Web Documentation Fetching** (Optional Enhancement)

#### Option A: Use `fetch_webpage` Tool
Fetch best practices from Microsoft Learn in real-time:

```python
from langchain_community.tools import fetch_webpage

async def enhance_with_web_docs(resource_type: str) -> str:
    """Fetch latest best practices from Microsoft Learn."""
    docs_urls = {
        "storage_account": "https://learn.microsoft.com/azure/storage/common/storage-security-guide",
        "key_vault": "https://learn.microsoft.com/azure/key-vault/general/best-practices",
        "function_app": "https://learn.microsoft.com/azure/azure-functions/functions-best-practices"
    }
    
    url = docs_urls.get(resource_type)
    if url:
        content = await fetch_webpage(urls=[url], query="best practices bicep")
        return content
    return ""

# Use in generate_infra_code:
best_practices_content = await enhance_with_web_docs(resource_type)
human_msg = HumanMessage(
    f"Generate bicep for: {state['input_parsed_json']}\n\n"
    f"Additional Best Practices:\n{best_practices_content}"
)
```

#### Option B: Bind Web Search to LLM
Give the LLM access to web search as a tool:

```python
from langchain_community.tools import DuckDuckGoSearchRun

# Add to filtered_tools
web_search = DuckDuckGoSearchRun()
filtered_tools.append(web_search)

# System message instructs LLM to search when needed
"If you need additional context, use web search to find 'Azure [resource] Bicep best practices'"
```

---

## Current Implementation Status

### ✅ Implemented
- [x] Azure Well-Architected Framework principles
- [x] Universal template structure best practices
- [x] MCP tools integration (get_bestpractices, bicepschema, documentation)
- [x] Security and compliance guidelines
- [x] Resource-specific critical rules (Key Vault purge protection, etc.)
- [x] Enhanced system messages in both `generate_infra_code` and `refine_infra_code`

### 🔄 Optional Enhancements
- [ ] Active web documentation fetching (helper function created, ready to use)
- [ ] Web search tool binding
- [ ] Example library caching
- [ ] Custom best practices repository

---

## How to Enable Web Documentation Fetching

### Step 1: Uncomment the Helper Function
In `workflow/nodes.py`, the `fetch_azure_best_practices()` function is ready to use.

Uncomment this section:
```python
# Requires: pip install langchain-community
from langchain_community.tools import fetch_webpage

# In fetch_azure_best_practices():
result = fetch_webpage(urls=[url], query="best practices bicep template")
return result
```

### Step 2: Integrate into generate_infra_code
```python
# After parsing resource type
resource_type = state['input_parsed_json'].get('resource_type')
web_docs = await fetch_azure_best_practices(resource_type)

# Add to human message
human_msg = HumanMessage(
    f"Generate bicep for: {state['input_parsed_json']}\n\n"
    f"Additional Best Practices from Microsoft Learn:\n{web_docs}"
)
```

---

## Testing the Enhanced System

### Test Case 1: Storage Account
```python
user_input = "Create a storage account for production workloads in East US"
```

**Expected Output:**
- ✅ Latest API version from bicepschema
- ✅ enableHttpsTrafficOnly: true
- ✅ minimumTlsVersion: 'TLS1_2'
- ✅ allowBlobPublicAccess: false
- ✅ Managed identity enabled
- ✅ Diagnostic settings configured
- ✅ Comprehensive @description decorators
- ✅ Production tags (Environment, Owner, CostCenter)

### Test Case 2: Key Vault
```python
user_input = "Create a key vault with soft delete for staging environment"
```

**Expected Output:**
- ✅ enableSoftDelete: true
- ✅ softDeleteRetentionInDays: 90
- ✅ enablePurgeProtection NOT set to false
- ✅ RBAC authorization enabled
- ✅ Private endpoint configuration
- ✅ Network ACLs configured
- ✅ Diagnostic logs enabled

### Test Case 3: Function App
```python
user_input = "Create a production function app with consumption plan"
```

**Expected Output:**
- ✅ Managed identity enabled
- ✅ Application Insights linked
- ✅ Storage connection string using listKeys()
- ✅ HTTPS only enabled
- ✅ Minimum TLS 1.2
- ✅ Diagnostic settings
- ✅ Proper tagging

---

## Advantages of This Approach

### 🎯 Universal Application
- Same principles apply to **any** Azure service
- No need to update code for new services
- Framework-based rather than prescriptive

### 🔄 Always Current
- MCP tools fetch latest schemas and best practices
- Optional web fetching gets real-time Microsoft Learn content
- No hardcoded API versions

### 🛡️ Security First
- Security best practices baked into every template
- Follows Azure Security Benchmark
- Principle of least privilege by default

### 📊 Production Ready
- Well-Architected Framework compliance
- Comprehensive logging and monitoring
- Cost-optimized configurations

### 🔧 Maintainable
- Central best practices definition
- No service-specific code sprawl
- Easy to update framework principles

---

## Monitoring Best Practices Compliance

### Option 1: Azure Policy Validation
After deployment, validate with Azure Policy:

```bash
az policy assignment list --resource-group rg-aidemo
az policy state list --resource-group rg-aidemo
```

### Option 2: Azure Advisor
Check Advisor recommendations:

```bash
az advisor recommendation list --resource-group rg-aidemo
```

### Option 3: Azure Security Center
Validate security posture:

```bash
az security assessment list --resource-group rg-aidemo
```

---

## Next Steps

1. **Test with Various Resources**
   - Try different Azure services
   - Verify MCP tools are being called
   - Check generated Bicep quality

2. **Enable Web Fetching (Optional)**
   - Uncomment helper function
   - Test with live Microsoft Learn docs
   - Compare with MCP tool results

3. **Add Custom Best Practices**
   - Create organization-specific guidelines
   - Add to system message
   - Document in this file

4. **Create Evaluation Suite**
   - Define quality metrics
   - Automated Bicep validation
   - Security compliance checks

---

## Troubleshooting

### MCP Tools Not Being Called
**Check:**
- Verify MCP server is running (`npx @azure/mcp@latest server start`)
- Ensure tools are properly bound to LLM
- Check system message instructs LLM to USE tools

**Debug:**
```python
print(f"Available tools: {[t.name for t in filtered_tools]}")
# Check if get_bestpractices, bicepschema are in the list
```

### Generated Bicep Still Has Issues
**Possible Causes:**
- LLM not following system instructions
- MCP tools returning incomplete data
- Need more specific resource guidance

**Solutions:**
- Add resource-specific rules to system message (as last resort)
- Enable web documentation fetching
- Use a more capable LLM model (GPT-4, Claude Opus)

### Web Fetching Not Working
**Check:**
- `fetch_webpage` tool is available
- URLs are accessible
- Network connectivity

**Alternative:**
Use browser tools to navigate Microsoft Learn and extract content.

---

## Contributing

To add support for a new Azure service:

1. **Do NOT** add service-specific code
2. **DO** ensure resource type is recognized in parsed_input
3. **DO** add Microsoft Learn URL to `best_practices_urls` dict (optional)
4. **DO** verify MCP tools support the service
5. **DO** test with existing framework-based instructions

---

## References

- [Azure Well-Architected Framework](https://learn.microsoft.com/azure/architecture/framework/)
- [Bicep Best Practices](https://learn.microsoft.com/azure/azure-resource-manager/bicep/best-practices)
- [Azure Security Benchmark](https://learn.microsoft.com/security/benchmark/azure/)
- [Azure Naming Conventions](https://learn.microsoft.com/azure/cloud-adoption-framework/ready/azure-best-practices/naming-and-tagging)
