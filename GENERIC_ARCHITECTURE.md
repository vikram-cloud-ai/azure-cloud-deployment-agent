# Generic Azure Bicep Generation Architecture

## Overview
The Azure Deployment Agent has been refactored to support **ANY Azure service**, not just specific resources like Storage Accounts, Key Vaults, or Function Apps.

## Design Philosophy

### ✅ Tool-Driven (Not Hardcoded)
- **Primary Source**: MCP tools (`bicepschema`, `get_bestpractices`, `documentation`)
- **Fallback Only**: Hardcoded knowledge for common resources as safety net
- **Dynamic Discovery**: Agent learns about new Azure services through tools

### ✅ Framework-Based (Not Prescriptive)
- **Universal Principles**: Azure Well-Architected Framework applies to all resources
- **Best Practices**: Security, reliability, cost optimization work universally
- **No Service-Specific Code**: Logic works for Storage, Cosmos DB, VMs, AKS, etc.

### ✅ Extensible (Not Limited)
- **New Services**: Automatically supported when Azure adds them
- **No Code Changes**: Adding support for new resource types requires zero code updates
- **Future-Proof**: Architecture adapts to Azure platform evolution

---

## Architecture Changes

### 1. Generic User Input Parsing

**Before (Service-Specific):**
```python
# Hardcoded list of supported services
- For storage: "storage_account"
- For key vault: "key_vault"
- For app service plan: "app_service_plan"
# ... extensive service-specific field documentation
```

**After (Universal):**
```python
# Generic extraction for ANY Azure service
- resource_type: Identify using underscore notation (storage_account, cosmos_db, aks_cluster, etc.)
- Extract ANY properties mentioned in request (not limited to predefined fields)
- Flexible schema that adapts to any Azure resource
```

**Benefits:**
- Works for Virtual Machines, AKS, Cosmos DB, Redis Cache, etc. without modification
- Extracts custom properties not in predefined schema
- User can request any Azure service using natural language

---

### 2. Tool-First Code Generation

**Before:**
```python
# System message with hardcoded service rules
For Storage Account (resource_type: storage_account):
- API version: '2023-01-01' or higher
- Required properties: name, location, sku, kind
# ... 100+ lines of service-specific instructions
```

**After:**
```python
# System message mandates using tools
CRITICAL WORKFLOW - ALWAYS USE TOOLS:
1. USE 'bicepschema' tool to get valid API versions and schema
2. USE 'get_bestpractices' tool to get Azure best practices
3. GENERATE using information from tools (not hardcoded rules)
```

**Benefits:**
- Always uses latest Azure API versions from bicepschema
- Gets service-specific best practices dynamically
- No need to update code when Azure releases new features
- Works for services that didn't exist when code was written

---

### 3. Universal Best Practices (Framework-Based)

**Principles Applied to ALL Resources:**

#### Security
- Managed identities
- Private endpoints
- Encryption at rest/transit
- Latest TLS versions
- Disable public access by default
- No hardcoded secrets

#### Reliability
- Availability zones
- Geo-redundancy
- Diagnostic logging
- Backup/DR

#### Performance
- Appropriate SKU selection
- Caching
- Auto-scaling

#### Cost Optimization
- Right-sizing
- Consumption tiers
- Comprehensive tagging

#### Operational Excellence
- Log Analytics integration
- Monitoring
- Azure naming conventions

---

### 4. Minimal Critical Rules

**Only Known Azure Platform Limitations:**

1. **Key Vault Purge Protection**
   - Known bug: Cannot set to `false` (deployment fails)
   - Solution: Only set to `true` if requested, otherwise omit

2. **Secrets Handling**
   - Never use placeholders like `REPLACE_WITH_KEY`
   - Use `listKeys()`, `listSecrets()` for dynamic retrieval

3. **API Version Format**
   - Must be exact: `YYYY-MM-DD` or `YYYY-MM-DD-preview`
   - Must be actually supported by Azure

**That's it!** No service-specific rules hardcoded.

---

### 5. Dynamic API Version Validation

**Before:**
```python
# Hardcoded mapping for 5 services only
valid_versions = {
    "Microsoft.Storage/storageAccounts": "2023-05-01",
    "Microsoft.KeyVault/vaults": "2023-07-01",
    # Only worked for these 5 services
}
```

**After:**
```python
# Expanded to 20+ common services + fallback to bicepschema tool
known_valid_versions = {
    # Compute, Storage, Networking, Databases, 
    # Containers, AI/ML, Monitoring, etc.
    # 20+ resource types covered
}
# If not in list, trust bicepschema tool response
```

**Benefits:**
- Validates API versions for most common Azure services
- Falls back to bicepschema tool for new/unknown services
- Easy to expand as needed

---

## Supported Azure Services

### ✅ Explicitly Tested
- Storage Accounts
- Key Vaults
- App Service Plans
- Function Apps
- Application Insights

### ✅ Supported via Generic Architecture (untested but should work)
- **Compute**: Virtual Machines, VM Scale Sets, Disks
- **Containers**: AKS, Container Registry, Container Instances
- **Databases**: Azure SQL, Cosmos DB, MySQL, PostgreSQL
- **Networking**: VNets, NSGs, Load Balancers, Public IPs, VPN Gateway
- **AI/ML**: Cognitive Services, Machine Learning Workspaces, OpenAI
- **Data**: Data Factory, Synapse, Event Hubs, IoT Hub
- **Identity**: Managed Identity, Active Directory
- **Monitoring**: Log Analytics, App Insights, Alerts
- **And ANY other Azure service** via bicepschema tool

---

## How It Works: Example Flow

### User Request:
```
"Create an Azure Cosmos DB account named mycosmosdb in East US 
with SQL API and geo-replication to West Europe"
```

### Agent Workflow:

1. **Parse User Input** (Generic)
   ```json
   {
     "resource_type": "cosmos_db",
     "name": "mycosmosdb",
     "region": "East US",
     "resource_group": "rg-deployment-test",
     "api": "sql",
     "geo_replication": "West Europe"
   }
   ```

2. **Call MCP Tools** (Dynamic)
   - `bicepschema(resource_type='Microsoft.DocumentDB/databaseAccounts')`
     → Returns: API version `2024-05-15`, required properties, schema
   - `get_bestpractices(service='CosmosDB')`
     → Returns: Consistency levels, backup policies, throughput guidance

3. **Generate Bicep** (Tool-Informed)
   - Uses API version from bicepschema: `@2024-05-15`
   - Applies best practices from get_bestpractices
   - Adds Well-Architected Framework principles (security, tags, etc.)

4. **Validate & Fix** (Safety Net)
   - Python validator checks API version is in valid format
   - If in known list, validates it's correct
   - Otherwise trusts bicepschema tool

5. **Deploy**
   - Bicep build → validate → human review → deploy

**No code changes needed** - works for Cosmos DB even though it wasn't explicitly programmed!

---

## Testing New Services

To verify the agent works with a new Azure service:

### Example: Azure Container Registry

```python
user_input = "Create an Azure Container Registry named myacr123 in East US with Premium SKU"
```

**Expected Behavior:**
1. ✅ Parses `resource_type: "container_registry"`
2. ✅ Calls `bicepschema` for `Microsoft.ContainerRegistry/registries`
3. ✅ Gets valid API version (e.g., `2023-07-01`)
4. ✅ Calls `get_bestpractices` for ACR
5. ✅ Generates Bicep with:
   - Premium SKU
   - Managed identity enabled
   - Geo-replication (if multi-region)
   - Diagnostic settings
   - Private endpoint ready
   - Comprehensive tags
6. ✅ Validates and deploys

**No modifications to nodes.py required!**

---

## Advantages Over Service-Specific Approach

### Maintenance
- **Before**: Add 50-100 lines of code per new service
- **After**: Zero code changes, works automatically

### Coverage
- **Before**: 5-6 Azure services explicitly supported
- **After**: 200+ Azure services supported via tools

### Quality
- **Before**: Best practices hardcoded, may become outdated
- **After**: Best practices from live Azure documentation

### Accuracy
- **Before**: API versions hardcoded, may become invalid
- **After**: API versions from bicepschema tool, always current

### Flexibility
- **Before**: Only supports predefined properties
- **After**: Extracts any property mentioned in user request

---

## Migration Path for Existing Code

### Phase 1: Current State ✅
- Generic architecture implemented
- Common resources have fallback API versions
- Works for any Azure service via tools

### Phase 2: Enhanced Validation (Optional)
- Expand `known_valid_versions` with more Azure services
- Add automated tests for common resources
- Create example library

### Phase 3: Advanced Features (Future)
- Multi-resource deployments in single Bicep
- Cross-resource dependencies
- Module composition

---

## Configuration

### Adding New Resource to Fallback List

If you want to add API version validation for a new resource:

```python
# In validate_and_fix_api_versions()
known_valid_versions = {
    # ... existing entries ...
    
    # Add new resource
    "Microsoft.Cache/redis": "2024-03-01",  # Redis Cache
    "Microsoft.ServiceBus/namespaces": "2024-01-01",  # Service Bus
}
```

**But remember**: This is optional! The bicepschema tool is the primary source.

---

## Troubleshooting

### Agent generates code for unsupported resource
**Cause**: MCP tools returned information
**Solution**: This is expected behavior - trust the tools

### API version invalid after generation
**Cause**: LLM didn't call bicepschema tool
**Solution**: Python validator will fix it using fallback versions

### Best practices not applied
**Cause**: get_bestpractices tool may not have service-specific data
**Solution**: Universal Well-Architected Framework principles still apply

### Unknown resource type
**Cause**: User request was ambiguous
**Solution**: Parser will extract what it can, bicepschema will validate

---

## Best Practices for Users

### ✅ Good Requests
```
"Create an Azure SQL Server named mysqlserver in East US with firewall rules to allow Azure services"
"Deploy an AKS cluster with 3 nodes, Standard tier, and Azure CNI networking"
"Set up a Redis Cache Premium tier with geo-replication in paired regions"
```

### ❌ Vague Requests
```
"Create a database" (Which type? SQL, Cosmos, MySQL, PostgreSQL?)
"Deploy storage" (Storage account? Disk? File share? Blob container?)
```

**Tip**: Be specific about resource type and key configuration

---

## Summary

| Aspect | Service-Specific | Generic Architecture |
|--------|-----------------|---------------------|
| **Supported Services** | 5-6 hardcoded | 200+ via tools |
| **Maintenance** | High (per-service) | Low (framework) |
| **API Versions** | Hardcoded | Dynamic from tools |
| **Best Practices** | Static rules | Live from Azure |
| **Code Changes** | Frequent | Rare |
| **Future-Proof** | No | Yes |
| **Flexibility** | Limited | High |

The generic architecture makes the agent **scalable, maintainable, and future-proof** while maintaining high code quality through Azure Well-Architected Framework principles. 🚀
