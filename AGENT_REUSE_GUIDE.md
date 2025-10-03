# Agent Reuse Implementation Guide

## Overview
This document explains the Microsoft best practices implementation for Azure AI Agent reuse in this project.

## What Was Implemented

### 1. Environment Variable Configuration
Added `AGENT_ID` to the configuration section:
```python
# Agent reuse configuration (Microsoft best practice)
AGENT_ID = os.environ.get("AGENT_ID")  # Optional: reuse existing agent
```

### 2. Helper Function: `get_or_create_agent()`
Created a reusable function that implements Microsoft's recommended pattern:

```python
def get_or_create_agent(
    project_client: AIProjectClient,
    model: str,
    name: str,
    instructions: str,
    tools: List,
    force_create: bool = False,
):
    """
    Get existing agent or create a new one (Microsoft best practice).
    
    This follows Microsoft's recommended pattern for agent reuse:
    - Reuse existing agent if AGENT_ID is set in environment
    - Create new agent only when needed
    - Agents persist by design and should be reused across runs
    """
```

**Key Features:**
- ✅ Attempts to retrieve existing agent if `AGENT_ID` is set
- ✅ Falls back to creating new agent if retrieval fails
- ✅ Provides helpful messages with agent ID for future reuse
- ✅ Supports `force_create` flag to override reuse behavior
- ✅ Comprehensive logging for troubleshooting

### 3. Updated main() Function
Modified the main function to use the helper:

**Before:**
```python
agent = project_client.agents.create_agent(
    model=MODEL,
    name="Enhanced MCP Agent",
    instructions=instructions,
    tools=all_tools,
)
```

**After:**
```python
agent = get_or_create_agent(
    project_client=project_client,
    model=MODEL,
    name="Enhanced MCP Agent",
    instructions=agent_instructions,
    tools=all_tools,
    force_create=False,  # Set to True to force new agent creation
)
```

### 4. Enhanced Cleanup Comments
Updated the cleanup section with Microsoft best practices:

```python
# Agent cleanup (Microsoft best practice):
# - Agents persist by design and should be reused across runs
# - Only delete if you need to recreate with different configuration
# - To reuse this agent, add AGENT_ID={agent.id} to your .env file
# 
# Uncomment to delete agent:
# project_client.agents.delete_agent(agent.id)
# pretty(f"Deleted agent: {agent.id}")
```

## How to Use

### First Run (No AGENT_ID set)

1. Run the application:
   ```bash
   python main.py
   ```

2. The output will show:
   ```
   [Agent] Creating new agent with model: gpt-4.1
   [Agent] ✅ Created new agent: asst_abc123xyz456
   [Agent] Model: gpt-4.1, Tools: 3
   
   ======================================================================
   💡 TIP: To reuse this agent on future runs, add to your .env file:
      AGENT_ID=asst_abc123xyz456
   ======================================================================
   ```

3. Copy the agent ID and add it to your `.env` file:
   ```env
   AGENT_ID=asst_abc123xyz456
   ```

### Subsequent Runs (AGENT_ID set)

1. Run the application:
   ```bash
   python main.py
   ```

2. The output will show:
   ```
   [Agent] Attempting to reuse existing agent: asst_abc123xyz456
   [Agent] ✅ Successfully reused agent: asst_abc123xyz456
   [Agent] Name: Enhanced MCP Agent, Model: gpt-4.1
   ```

### Force New Agent Creation

If you need to create a new agent even when `AGENT_ID` is set, modify the code:

```python
agent = get_or_create_agent(
    project_client=project_client,
    model=MODEL,
    name="Enhanced MCP Agent",
    instructions=agent_instructions,
    tools=all_tools,
    force_create=True,  # ← Change to True
)
```

Or temporarily remove/comment out the `AGENT_ID` in your `.env` file.

## Benefits of This Approach

### 🎯 Aligned with Microsoft Best Practices
- Follows official SDK patterns and examples
- Implements recommended `get_agent()` + `create_agent()` pattern
- Documented in official Azure AI Foundry documentation

### 💰 Cost Optimization
- Reduces unnecessary agent creation
- Lowers inference costs by reusing configurations
- Avoids orphaned agent accumulation

### ⚡ Performance Improvements
- Faster startup (skips agent creation overhead)
- Immediate availability of agent
- Reduced API calls to Azure

### 🛡️ Reliability
- Graceful fallback if agent not found
- Clear error messages for troubleshooting
- Supports force recreation when needed

### 🔧 Simplicity
- Environment variable-based configuration
- No complex cache files or hashing
- Easy to understand and maintain

## When to Create a New Agent

Create a new agent when:
- ✅ Changing the model (e.g., gpt-4o → gpt-4o-mini)
- ✅ Modifying agent instructions significantly
- ✅ Adding or removing tools
- ✅ Changing MCP server configuration
- ✅ Testing different agent configurations

## When to Reuse an Agent

Reuse an agent when:
- ✅ Only the user prompt changes
- ✅ Running multiple questions in sequence
- ✅ Testing with different threads
- ✅ No changes to agent configuration
- ✅ Normal day-to-day operations

## Troubleshooting

### Agent Not Found Error
```
[Agent] ⚠️ Could not retrieve agent asst_abc123: Agent not found
[Agent] Creating new agent instead...
```

**Possible causes:**
- Agent was deleted manually in Azure AI Foundry portal
- Agent ID is incorrect in `.env` file
- Agent belongs to different project

**Solution:**
- Application will automatically create a new agent
- Update `.env` with the new agent ID

### Want to Reset and Start Fresh
```bash
# Option 1: Remove AGENT_ID from .env file
# Option 2: Set force_create=True in code
# Option 3: Delete agent in Azure portal and let it recreate
```

## Files Modified

1. **main.py**
   - Added `AGENT_ID` configuration
   - Added `get_or_create_agent()` function
   - Updated `main()` to use helper function
   - Enhanced cleanup comments

2. **README.md**
   - Added "Agent Reuse" section
   - Updated `.env` example
   - Added usage instructions

3. **AGENT_REUSE_GUIDE.md** (this file)
   - Complete implementation documentation

## References

- [Azure AI Foundry Agent Quickstart](https://learn.microsoft.com/en-us/azure/ai-foundry/agents/quickstart)
- [Azure AI Agents FAQ](https://learn.microsoft.com/en-us/azure/ai-foundry/agents/faq)
- [Azure AI Projects Python SDK](https://learn.microsoft.com/en-us/python/api/overview/azure/ai-projects-readme)

## Summary

This implementation follows Microsoft's recommended best practices for agent lifecycle management:

1. **Simple** - Environment variable-based configuration
2. **Efficient** - Reuses agents across runs
3. **Robust** - Handles errors gracefully
4. **Cost-effective** - Reduces unnecessary resource creation
5. **Maintainable** - Clear code with helpful messages

The pattern is simple: **Create once, reuse many times** ✅
