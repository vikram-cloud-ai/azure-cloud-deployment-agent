# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [Unreleased]

## [0.2.0] - 2026-06-17

### Added
- Human-in-the-loop skill for LangGraph: manages human approval workflows, error handling, and state interruptions
- Comprehensive examples for basic interrupts, approval workflows, validation loops, and handling multiple interrupts
- LangGraph persistence skill: enables state persistence, conversation history, and subgraph checkpointer configuration
- Examples for setting up checkpointers, managing threads, and utilizing long-term memory with a store
- Guidelines for idempotency and side effects in graph execution
- Best practices for thread IDs, state updates, and accessing the store within graph nodes

### Fixed
- PR review comments addressed across workflow and core components

## [0.1.0] - 2026-06-11

### Added
- Initial release of Azure Deployment Agent
- LangGraph workflow with eight-stage pipeline: parse input, generate Bicep, build, refine, pre-validate, human review, deploy, verify
- Natural language processing to extract Azure deployment parameters from plain English requests
- Bicep template generation via Azure MCP (Model Context Protocol) tools
- Multi-stage validation: Bicep build validation and Azure pre-deployment checks
- Automated deployment using Azure CLI
- Deployment verification and status reporting
- CLI entry point (`main.py`) with optional workflow graph visualisation (`--graph` flag)
- Gradio web UI (`gradio_app.py`) for browser-based interaction
- Support for Storage Accounts, Key Vaults, App Service Plans, Application Insights, and Function Apps
- LangChain + Azure OpenAI integration for LLM-driven reasoning
- Pydantic models and TypedDicts for structured state management
- Environment variable configuration via `.env` with `.env.example` template
