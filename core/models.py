"""Data models for Azure deployment agent."""

from typing import Literal, TypedDict, Optional, Dict, Any, List, Union, NotRequired
from pydantic import BaseModel, Field


class Property(BaseModel):
    """A single property key-value pair for Azure resource configuration."""
    key: str = Field(..., description="Property name in snake_case")
    value: Union[str, int, float, bool] = Field(..., description="Property value")


class ResourceParameters(BaseModel):
    """
    Generic parameters for ANY Azure resource deployment.
    
    This model is designed to be flexible and work with any Azure service
    without requiring service-specific field definitions.
    """
    
    # Core required fields (universal across all Azure resources)
    name: str = Field(..., description="Name for the resource")
    location: str = Field(..., description="Azure region (e.g., eastus, westeurope, southeastasia)")
    resource_group: str = Field(default="rg-deployment-test", description="Resource group name")
    
    # Optional common fields
    subscription: Optional[str] = Field(None, description="Azure subscription name or ID")
    tags: Optional[Dict[str, str]] = Field(None, description="Resource tags as key-value pairs")
    
    # Common configuration fields (applicable to many services)
    sku: Optional[str] = Field(None, description="SKU/pricing tier (e.g., Standard_LRS, Basic, S1, Premium)")
    tier: Optional[str] = Field(None, description="Pricing tier category (Basic, Standard, Premium)")
    kind: Optional[str] = Field(None, description="Resource kind/variant")
    capacity: Optional[int] = Field(None, description="Capacity or instance count")
    
    # Generic properties container for service-specific settings
    # This field captures ANY additional properties mentioned in the user request as a list
    # Examples: replication_type, runtime, performance, enable_https_traffic_only, 
    # purge_protection_enabled, min_tls_version, vm_size, etc.
    properties: Optional[List[Property]] = Field(
        None, 
        description="Additional service-specific properties as a list of key-value pairs. "
                    "Use this for any Azure resource properties not covered by the standard fields above."
    )


class parsed_input(BaseModel):
    """
    Structured model for Azure resource deployment request.
    
    This model uses a generic approach that works for ANY Azure service.
    No service-specific field definitions required.
    """
    
    resource_type: str = Field(
        ..., 
        description="Type of Azure resource using underscore notation (e.g., storage_account, "
                    "key_vault, virtual_machine, cosmos_db, aks_cluster, app_service, etc.)"
    )
    parameters: ResourceParameters = Field(
        ..., 
        description="Deployment parameters - accepts any Azure resource properties dynamically"
    )


class DeploymentAgentState(TypedDict):
    """State for the deployment agent workflow."""
    input_parsed_json: parsed_input
    user_input: str
    infra_code: str
    deployment_status: Literal["Success", "Failure"]
    infra_build_status: Literal["Pass", "Fail"]
    deploy_infra_validate_status: Literal["Pass", "Fail"]
    refinement_attempts: NotRequired[int]  # Track number of refinement attempts to prevent infinite loops
    build_error: NotRequired[str]  # Stores Bicep build errors for refinement
