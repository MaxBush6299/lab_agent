import os, time
import requests
import json
import logging
from pathlib import Path
from typing import Optional, Dict, Any, List
from azure.ai.projects import AIProjectClient
from azure.identity import DefaultAzureCredential
from azure.ai.agents.models import CodeInterpreterTool, BingGroundingTool
from dotenv import load_dotenv
from azure.ai.agents.models import (
    ListSortOrder,
    McpTool,
    RequiredMcpToolCall,
    RunStepActivityDetails,
    SubmitToolOutputsAction,
    SubmitToolApprovalAction,
    ToolApproval,
)

load_dotenv()

# Suppress verbose Azure Identity credential chain logging
logging.getLogger('azure.identity').setLevel(logging.WARNING)
logging.getLogger('azure.core').setLevel(logging.WARNING)

######################################################
#Configuration
#######################################################

MODEL = os.getenv("MODEL_DEPLOYMENT_NAME", "gpt-4o")

# Get MCP server configuration from environment variables
MCP_SERVER_URL = os.environ.get("MCP_SERVER_URL")
MCP_SERVER_LABEL = os.environ.get("MCP_SERVER_LABEL")
BING_CONNECTION_ID = os.environ.get("BING_CONNECTION_ID")

# MCP Server Azure AD authentication configuration
MCP_AUTH_TENANT_ID = os.environ.get("MCP_AUTH_TENANT_ID", "2e9b0657-eef8-47af-8747-5e89476faaab")
MCP_AUTH_CLIENT_ID = os.environ.get("MCP_AUTH_CLIENT_ID", "17a97781-0078-4478-8b4e-fe5dda9e2400")
MCP_AUTH_SCOPE = os.environ.get("MCP_AUTH_SCOPE", "17a97781-0078-4478-8b4e-fe5dda9e2400/.default")

# Agent reuse configuration (Microsoft best practice)
AGENT_ID = os.environ.get("AGENT_ID")  # Optional: reuse existing agent

CONN_STR = os.environ["PROJECT_ENDPOINT"]

# Global token cache
_mcp_token_cache = {"token": None, "expires_at": 0}

# --------------------------------------------------------------------------------------
# Azure AD Authentication for MCP Server
# --------------------------------------------------------------------------------------

def get_mcp_access_token() -> str:
    """
    Obtain an Azure AD access token for the MCP server using DefaultAzureCredential.
    
    This function:
    - Uses the same credential as the AI Foundry client for consistency
    - Caches the token to avoid unnecessary token requests
    - Automatically refreshes expired tokens
    
    Returns:
        Valid Azure AD access token for the MCP server
    """
    import time
    
    # Check if we have a valid cached token
    current_time = time.time()
    if _mcp_token_cache["token"] and _mcp_token_cache["expires_at"] > current_time + 300:
        # Token is valid for at least 5 more minutes
        return _mcp_token_cache["token"]
    
    try:
        pretty("[MCP Auth] Obtaining Azure AD access token...")
        
        # Use DefaultAzureCredential to get token (same as AI Foundry client)
        # Exclude broker credential to avoid verbose Windows WAM messages
        credential = DefaultAzureCredential(exclude_broker_credential=True)
        
        # Request token with the MCP server's scope
        # For DefaultAzureCredential, use the base resource URL with /.default
        # The MCP_AUTH_SCOPE is "api://GUID/user_impersonation", so extract the base
        base_resource = MCP_AUTH_SCOPE.rsplit('/', 1)[0]  # Gets "api://GUID"
        token_scope = f"{base_resource}/.default"  # Makes "api://GUID/.default"
        
        pretty(f"[MCP Auth] Requesting token for scope: {token_scope}")
        token_result = credential.get_token(token_scope)
        
        # Cache the token
        _mcp_token_cache["token"] = token_result.token
        _mcp_token_cache["expires_at"] = token_result.expires_on
        
        pretty(f"[MCP Auth] ✅ Token obtained successfully (expires in {int((token_result.expires_on - current_time) / 60)} minutes)")
        
        return token_result.token
        
    except Exception as e:
        pretty(f"[MCP Auth] ❌ Failed to obtain access token: {str(e)}")
        raise RuntimeError(f"Cannot authenticate with MCP server: {str(e)}")

# --------------------------------------------------------------------------------------
# MCP Server Discovery
# --------------------------------------------------------------------------------------

def discover_mcp_tools(server_url: str, timeout: int = 10) -> List[str]:
    """
    Discover available tools from an MCP server by calling its introspection endpoint.
    
    This function attempts multiple discovery methods:
    1. JSON-RPC tools/list method
    2. Various REST endpoints (/tools, /list_tools, etc.)
    3. Falls back to known MSSQL tools if discovery fails
    
    Args:
        server_url: The base URL of the MCP server
        timeout: Request timeout in seconds
        
    Returns:
        List of tool names available on the server
    """
    # Fallback tools (known MSSQL MCP tools)
    fallback_tools = [
        "query_sql",          # Execute SELECT queries (read-only)
        "execute_sql",        # Execute INSERT, UPDATE, DELETE statements
        "list_tables",        # List all tables in the database
        "describe_table",     # Get table schema details
        "create_table",       # Create a new table
        "drop_table",         # Delete a table
        "create_index",       # Create an index on a table
        "update_data",        # Update records in a table
    ]
    
    try:
        pretty(f"[MCP Discovery] Starting tool discovery for: {server_url}")
        
        # Get access token for authentication
        try:
            access_token = get_mcp_access_token()
        except Exception as e:
            pretty(f"[MCP Discovery] Could not get access token: {e}")
            pretty("[MCP Discovery] Using fallback tools without introspection")
            return fallback_tools
        
        # Method 1: Try JSON-RPC 2.0 tools/list
        try:
            pretty("[MCP Discovery] Trying JSON-RPC tools/list method...")
            
            import uuid
            session_id = str(uuid.uuid4())
            
            payload = {
                "jsonrpc": "2.0",
                "method": "tools/list",
                "id": 1
            }
            
            # Try with session ID query parameter
            endpoint = f"{server_url.rstrip('/')}/message?sessionId={session_id}"
            response = requests.post(
                endpoint,
                json=payload,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {access_token}",
                    "Accept": "application/json"
                },
                timeout=timeout
            )
            
            pretty(f"[MCP Discovery] JSON-RPC response status: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                if "result" in data:
                    tools = extract_tools_from_response(data["result"])
                    if tools:
                        pretty(f"[MCP Discovery] ✅ Found {len(tools)} tools via JSON-RPC: {tools}")
                        return tools
            else:
                pretty(f"[MCP Discovery] JSON-RPC response: {response.text[:200]}")
                        
        except Exception as e:
            pretty(f"[MCP Discovery] JSON-RPC method failed: {str(e)}")
        
        # Method 2: Try common REST endpoints
        endpoints_to_try = [
            f"{server_url.rstrip('/')}/tools",
            f"{server_url.rstrip('/')}/list_tools",
            f"{server_url.rstrip('/')}/capabilities",
            f"{server_url.rstrip('/')}/introspect",
        ]
        
        for endpoint in endpoints_to_try:
            try:
                pretty(f"[MCP Discovery] Trying REST endpoint: {endpoint}")
                
                response = requests.get(
                    endpoint,
                    headers={
                        "Authorization": f"Bearer {access_token}",
                        "Accept": "application/json"
                    },
                    timeout=timeout
                )
                
                if response.status_code == 200:
                    data = response.json()
                    tools = extract_tools_from_response(data)
                    if tools:
                        pretty(f"[MCP Discovery] ✅ Found {len(tools)} tools via REST: {tools}")
                        return tools
                        
            except Exception as e:
                pretty(f"[MCP Discovery] Endpoint {endpoint} failed: {str(e)}")
                continue
                
    except Exception as e:
        pretty(f"[MCP Discovery] Error during discovery: {str(e)}")
    
    # If all discovery methods fail, use fallback
    pretty("[MCP Discovery] ⚠️ All discovery methods failed, using fallback MSSQL tools")
    pretty(f"[MCP Discovery] Fallback tools: {fallback_tools}")
    return fallback_tools


def extract_tools_from_response(data: Dict[str, Any]) -> List[str]:
    """
    Extract tool names from various MCP response formats.
    
    Supports multiple formats:
    - {"tools": [{"name": "tool1"}, {"name": "tool2"}]}
    - {"tools": ["tool1", "tool2"]}
    - {"capabilities": {"tools": [...]}}
    - ["tool1", "tool2"]
    
    Args:
        data: Response data from MCP server
        
    Returns:
        List of tool names extracted from response
    """
    tools = []
    
    try:
        # Format 1: {"tools": [{"name": "tool1"}, {"name": "tool2"}]}
        if "tools" in data and isinstance(data["tools"], list):
            for tool in data["tools"]:
                if isinstance(tool, dict) and "name" in tool:
                    tools.append(tool["name"])
                elif isinstance(tool, str):
                    tools.append(tool)
        
        # Format 2: {"capabilities": {"tools": ["tool1", "tool2"]}}
        elif "capabilities" in data and isinstance(data["capabilities"], dict):
            if "tools" in data["capabilities"]:
                capabilities_tools = data["capabilities"]["tools"]
                if isinstance(capabilities_tools, list):
                    for tool in capabilities_tools:
                        if isinstance(tool, dict) and "name" in tool:
                            tools.append(tool["name"])
                        elif isinstance(tool, str):
                            tools.append(tool)
        
        # Format 3: Direct list ["tool1", "tool2"]
        elif isinstance(data, list):
            for tool in data:
                if isinstance(tool, dict) and "name" in tool:
                    tools.append(tool["name"])
                elif isinstance(tool, str):
                    tools.append(tool)
        
        # Format 4: {"result": {"tools": [...]}}
        elif "result" in data:
            return extract_tools_from_response(data["result"])
            
    except Exception as e:
        pretty(f"[MCP Discovery] Error extracting tools: {str(e)}")
    
    return tools

# --------------------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------------------

def pretty(msg: str):
    """Tiny logger to keep stdout readable."""
    print(msg, flush=True)


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
    
    Args:
        project_client: Azure AI Project client
        model: Model deployment name
        name: Agent name
        instructions: Agent instructions
        tools: List of tools to attach to agent
        force_create: Force creation of new agent even if AGENT_ID exists
        
    Returns:
        Agent object (either existing or newly created)
    """
    if AGENT_ID and not force_create:
        try:
            # Try to reuse existing agent (Microsoft best practice)
            pretty(f"[Agent] Attempting to reuse existing agent: {AGENT_ID}")
            agent = project_client.agents.get_agent(AGENT_ID)
            pretty(f"[Agent] ✅ Successfully reused agent: {agent.id}")
            pretty(f"[Agent] Name: {agent.name}, Model: {agent.model}")
            return agent
        except Exception as e:
            pretty(f"[Agent] ⚠️ Could not retrieve agent {AGENT_ID}: {str(e)}")
            pretty(f"[Agent] Creating new agent instead...")
    
    # Create new agent
    pretty(f"[Agent] Creating new agent with model: {model}")
    agent = project_client.agents.create_agent(
        model=model,
        name=name,
        instructions=instructions,
        tools=tools,
    )
    pretty(f"[Agent] ✅ Created new agent: {agent.id}")
    pretty(f"[Agent] Model: {agent.model}, Tools: {len(tools)}")
    pretty("")
    pretty("=" * 70)
    pretty("💡 TIP: To reuse this agent on future runs, add to your .env file:")
    pretty(f"   AGENT_ID={agent.id}")
    pretty("=" * 70)
    pretty("")
    
    return agent


def execute_mcp_tool(
    *,
    server_label: str,
    tool_name: str,
    args: Dict[str, Any],
    headers: Optional[Dict[str, str]] = None,
) -> Any:
    """
    Execute MCP tool using JSON-RPC 2.0 format with Azure AD authentication.
    
    This function:
    - Obtains an Azure AD access token
    - Formats the request using JSON-RPC 2.0 protocol
    - Calls the MCP server's /message endpoint with sessionId
    - Handles authentication and error responses
    
    Args:
        server_label: Label for the MCP server (for logging)
        tool_name: Name of the tool to execute (e.g., "query_sql")
        args: Dictionary of arguments for the tool
        headers: Optional additional headers (will be merged with auth headers)
        
    Returns:
        Tool execution result or error information
    """
    try:
        import uuid
        
        # Use the global MCP_SERVER_URL
        server_url = MCP_SERVER_URL
        pretty(f"[MCP Execute] Starting execution for tool '{tool_name}' on server '{server_label}'")
        pretty(f"[MCP Execute] Server URL: {server_url}")
        pretty(f"[MCP Execute] Arguments: {json.dumps(args, indent=2)}")
        
        # Get Azure AD access token
        access_token = get_mcp_access_token()
        
        # Generate a session ID for this request
        session_id = str(uuid.uuid4())
        
        # Build JSON-RPC 2.0 request
        # The MSSQL MCP server expects: method="tools/call" with params containing name and arguments
        payload = {
            "jsonrpc": "2.0",
            "id": int(time.time() * 1000),  # Unique ID for request tracking
            "method": "tools/call",
            "params": {
                "name": tool_name,
                "arguments": args
            }
        }
        
        pretty(f"[MCP Execute] JSON-RPC Request: {json.dumps(payload, indent=2)}")
        pretty(f"[MCP Execute] Session ID: {session_id}")
        
        # Prepare headers with authentication
        request_headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json"
        }
        
        # Merge any additional headers
        if headers:
            request_headers.update(headers)
        
        # Make the request to /message endpoint with sessionId query parameter
        endpoint = f"{server_url.rstrip('/')}/message?sessionId={session_id}"
        pretty(f"[MCP Execute] Calling endpoint: {endpoint}")
        
        response = requests.post(
            endpoint,
            json=payload,
            headers=request_headers,
            timeout=30
        )
        
        pretty(f"[MCP Execute] Response Status: {response.status_code}")
        pretty(f"[MCP Execute] Response Headers: {dict(response.headers)}")
        
        # Handle response
        if response.status_code == 401:
            pretty(f"[MCP Execute] ❌ Authentication failed - check token and permissions")
            return {"error": "Authentication failed - invalid or expired token"}
        
        if response.status_code == 403:
            pretty(f"[MCP Execute] ❌ Authorization failed - insufficient permissions")
            return {"error": "Authorization failed - user does not have required permissions"}
        
        if response.status_code != 200:
            error_text = response.text[:500]
            pretty(f"[MCP Execute] ❌ HTTP {response.status_code}: {error_text}")
            return {"error": f"HTTP {response.status_code}: {error_text}"}
        
        # Parse JSON-RPC response
        try:
            data = response.json()
            pretty(f"[MCP Execute] Response Data: {json.dumps(data, indent=2)}")
            
            # Check for JSON-RPC error
            if "error" in data:
                error_info = data["error"]
                error_msg = error_info.get("message", "Unknown error")
                error_code = error_info.get("code", -1)
                pretty(f"[MCP Execute] ❌ JSON-RPC Error [{error_code}]: {error_msg}")
                return {"error": f"MCP Error [{error_code}]: {error_msg}"}
            
            # Extract result
            if "result" in data:
                result = data["result"]
                
                # Handle MCP-style result with content array
                if isinstance(result, dict) and "content" in result:
                    content = result["content"]
                    if isinstance(content, list) and len(content) > 0:
                        # Extract text from first content item
                        first_content = content[0]
                        if isinstance(first_content, dict) and "text" in first_content:
                            result_text = first_content["text"]
                            pretty(f"[MCP Execute] ✅ Success! Result: {result_text[:200]}...")
                            return result_text
                
                # Return result as-is if not in expected format
                pretty(f"[MCP Execute] ✅ Success! Returning raw result")
                return result
            
            # No result or error found
            pretty(f"[MCP Execute] ⚠️ Unexpected response format - no result or error field")
            return {"error": "Unexpected response format", "response": data}
            
        except json.JSONDecodeError as e:
            pretty(f"[MCP Execute] ❌ Failed to parse JSON response: {str(e)}")
            pretty(f"[MCP Execute] Raw response: {response.text[:500]}")
            return {"error": f"Invalid JSON response: {str(e)}"}
        
    except Exception as e:
        pretty(f"[MCP Execute] ❌ Exception occurred: {str(e)}")
        import traceback
        pretty(f"[MCP Execute] Traceback: {traceback.format_exc()}")
        return {"error": f"Execution failed: {str(e)}"}


def drive_until_complete(project_client: AIProjectClient, thread, run, mcp_tool: McpTool, poll_interval: float = 1.0, timeout_seconds: int = 120):
    """
    Poll the run and satisfy required actions until it reaches a terminal state.
    Handles:
    - SubmitToolApprovalAction   -> submit_tool_approvals(...)
    - SubmitToolOutputsAction    -> execute tool + submit_tool_outputs(...)
    """
    def _log_required_action(ra):
        try:
            pretty(f"[DEBUG] Required action type: {type(ra).__name__}")
            if isinstance(ra, SubmitToolApprovalAction):
                pretty(f"[DEBUG] Tool approval action with {len(ra.submit_tool_approval.tool_calls or [])} tool calls")
                for c in ra.submit_tool_approval.tool_calls or []:
                    pretty(f"[RA-approve] id={c.id} server={getattr(c,'server_label',None)} tool={getattr(c,'name',None)}")
                    pretty(f"[DEBUG] Tool call type: {type(c).__name__}")
                    if hasattr(c, 'arguments'):
                        pretty(f"[DEBUG] Tool arguments: {getattr(c, 'arguments', 'None')}")
            elif isinstance(ra, SubmitToolOutputsAction):
                pretty(f"[DEBUG] Tool outputs action with {len(ra.submit_tool_outputs.tool_calls or [])} tool calls")
                for c in ra.submit_tool_outputs.tool_calls or []:
                    pretty(f"[RA-output ] id={c.id} server={getattr(c,'server_label',None)} tool={getattr(c,'name',None)} args={getattr(c,'arguments',None)}")
                    pretty(f"[DEBUG] Tool call type: {type(c).__name__}")
            else:
                pretty(f"[DEBUG] Unknown required action: {ra}")
        except Exception as e:
            pretty(f"[RA-log-error] {e!r}")
            import traceback
            pretty(f"[DEBUG] Traceback: {traceback.format_exc()}")

    start_time = time.time()
    iteration = 0
    while run.status in ("queued", "in_progress", "requires_action"):
        iteration += 1
        elapsed = time.time() - start_time
        pretty(f"[Run Status] Iteration {iteration}, Status: {run.status}, Elapsed: {elapsed:.1f}s")
        
        # Log additional run details
        if hasattr(run, 'last_error') and run.last_error:
            pretty(f"[Run Status] Last error: {run.last_error}")
        if hasattr(run, 'required_action') and run.required_action:
            pretty(f"[Run Status] Has required action: {type(run.required_action).__name__}")
        
        # Log every 10 iterations to reduce noise but still show progress
        if iteration % 10 == 0:
            pretty(f"[Run Status] Still waiting... Iteration {iteration}, Status: {run.status}")
        
        # Check for timeout
        if elapsed > timeout_seconds:
            pretty(f"[Timeout] Run exceeded {timeout_seconds} seconds, cancelling...")
            try:
                cancelled_run = project_client.agents.runs.cancel(thread_id=thread.id, run_id=run.id)
                pretty(f"[Timeout] Cancel result status: {cancelled_run.status}")
            except Exception as e:
                pretty(f"[Timeout] Could not cancel run: {e}")
            break
        
        if run.status != "requires_action":
            time.sleep(poll_interval)
            try:
                run = project_client.agents.runs.get(thread_id=thread.id, run_id=run.id)
            except Exception as e:
                pretty(f"[Run Status] Error getting run status: {e}")
                break
            continue

        ra = run.required_action
        _log_required_action(ra)

        # ---------- A) APPROVALS ----------
        if isinstance(ra, SubmitToolApprovalAction):
            approvals: list[ToolApproval] = []
            
            # Get Azure AD token to pass to MCP runtime
            try:
                access_token = get_mcp_access_token()
                auth_headers = {"Authorization": f"Bearer {access_token}"}
                pretty(f"[Approval] Including authentication headers with token")
            except Exception as e:
                pretty(f"[Approval] Warning: Could not get access token: {e}")
                auth_headers = None
            
            for call in ra.submit_tool_approval.tool_calls or []:
                if isinstance(call, RequiredMcpToolCall):
                    pretty(f"[Approval] Approving tool: {call.name} (id: {call.id})")
                    approvals.append(
                        ToolApproval(
                            tool_call_id=call.id,
                            approve=True,
                            headers=auth_headers,  # Pass authentication headers
                        )
                    )
            if approvals:
                pretty(f"[submit approvals] count={len(approvals)}")
                project_client.agents.runs.submit_tool_outputs(
                    thread_id=thread.id,
                    run_id=run.id,
                    tool_approvals=approvals,
                )
                pretty(f"[Approval] Submitted, waiting for next status...")

        # ---------- B) TOOL OUTPUTS ----------
        elif isinstance(ra, SubmitToolOutputsAction):
            pretty(f"[Tool Execution] Starting execution of {len(ra.submit_tool_outputs.tool_calls or [])} tool(s)")
            outputs = []
            for call in ra.submit_tool_outputs.tool_calls or []:
                if isinstance(call, RequiredMcpToolCall):
                    pretty(f"[execute] {call.id} tool={call.name} server={call.server_label}")
                    pretty(f"[execute] Arguments: {call.arguments}")
                    result = execute_mcp_tool(
                        server_label=call.server_label,
                        tool_name=call.name,
                        args=call.arguments,
                        headers=getattr(mcp_tool, "headers", None) or None,
                    )
                    pretty(f"[execute] Result: {str(result)[:200]}...")
                    outputs.append({"tool_call_id": call.id, "output": result})

            if outputs:
                pretty(f"[submit outputs] count={len(outputs)}")
                project_client.agents.runs.submit_tool_outputs(
                    thread_id=thread.id,
                    run_id=run.id,
                    tool_outputs=outputs,
                )
                pretty(f"[Tool Execution] Outputs submitted, waiting for next status...")

        # fetch next status after handling the action
        run = project_client.agents.runs.get(thread_id=thread.id, run_id=run.id)

    pretty(f"[run completed] status={run.status}")
    return run


# --------------------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------------------

def main():
    if not CONN_STR:
        raise RuntimeError(
            "Please set PROJECT_ENDPOINT to your Azure AI Foundry project."
        )

    # Create the project client
    project_client = AIProjectClient(
        endpoint=CONN_STR,
        credential=DefaultAzureCredential(),
    )

    # Enable/disable MCP for testing
    # Anonymous tool discovery IS working - testing if Azure AI Foundry can connect
    USE_MCP = True  # Set to True to enable MCP tools
    
    mcp_tool = None
    available_tools = []
    
    if USE_MCP and MCP_SERVER_URL and MCP_SERVER_LABEL:
        # Discover available tools from the MCP server
        pretty("[MCP Discovery] Starting tool discovery...")
        available_tools = discover_mcp_tools(MCP_SERVER_URL)
        
        # Build the MCP tool; label + URL must match the tool calls your agent will make.
        mcp_tool = McpTool(
            server_label=MCP_SERVER_LABEL,
            server_url=MCP_SERVER_URL,
        )

        # Dynamically allow all discovered tools
        for tool_name in available_tools:
            mcp_tool.allow_tool(tool_name)
            pretty(f"[MCP Setup] Allowed tool: {tool_name}")

        # Debug: Check MCP tool definitions
        pretty(f"[MCP Debug] MCP tool definitions count: {len(mcp_tool.definitions)}")
    else:
        pretty("[MCP] MCP tools disabled for testing")

    # Create Code Interpreter and Bing Grounding tools
    code_interpreter = CodeInterpreterTool()
    bing_grounding = BingGroundingTool(connection_id=BING_CONNECTION_ID)
    
    # Combine all tools
    all_tools = [code_interpreter.definitions[0]] + [bing_grounding.definitions[0]]
    if mcp_tool:
        all_tools.extend(mcp_tool.definitions)
    
    # Debug: Show tool counts
    pretty(f"[Debug] Code Interpreter tools: {len(code_interpreter.definitions)}")
    pretty(f"[Debug] Bing Grounding tools: {len(bing_grounding.definitions)}")
    pretty(f"[Debug] MCP tools: {len(mcp_tool.definitions) if mcp_tool else 0}")
    pretty(f"[Debug] Total tools combined: {len(all_tools)}")
    
    # Build dynamic tool descriptions based on discovered tools
    tool_descriptions = []
    if available_tools:
        for tool_name in available_tools:
            if tool_name == "read_data":
                tool_descriptions.append("- read_data: Execute SELECT queries to read data from tables")
            elif tool_name == "insert_data":
                tool_descriptions.append("- insert_data: Insert new records into tables")
            elif tool_name == "update_data":
                tool_descriptions.append("- update_data: Update existing records in tables")
            elif tool_name == "list_table":
                tool_descriptions.append("- list_table: List all available tables in the database")
            elif tool_name == "describe_table":
                tool_descriptions.append("- describe_table: Get schema information (columns, types, constraints) for a table")
            elif tool_name == "create_table":
                tool_descriptions.append("- create_table: Create new tables with specified schema")
            elif tool_name == "drop_table":
                tool_descriptions.append("- drop_table: Delete tables from the database")
            elif tool_name == "create_index":
                tool_descriptions.append("- create_index: Create indexes to improve query performance")
            else:
                tool_descriptions.append(f"- {tool_name}: Database operation tool")
    
    tool_list = "\n".join(tool_descriptions) if tool_descriptions else "- No MCP tools available"
    
    # Build agent instructions with detailed tool descriptions
    agent_instructions = (
        "You are a helpful database assistant with multiple capabilities:\n\n"
        
        f"**MSSQL Database Tools** (Primary capability):\n"
        f"{tool_list}\n\n"
        
        "**Row-Level Security (RLS):**\n"
        "- The database enforces RLS - you can only see data you own\n"
        "- The Security.Documents table filters by OwnerUPN (your user identity)\n"
        "- You cannot insert data with a different owner than yourself\n"
        "- All operations are executed with your authenticated identity\n\n"
        
        "**Other Tools:**\n"
        "- Code Interpreter: For Python calculations, data analysis, and visualizations\n"
        "- Bing Search: For real-time web information and current events\n\n"
        
        "**Guidelines:**\n"
        "- When users ask about database content, use list_tables and query_sql\n"
        "- Always check table schemas with describe_table before queries\n"
        "- Use proper SQL syntax for SQL Server (T-SQL)\n"
        "- Provide clear explanations of query results\n"
        "- Handle errors gracefully and explain any RLS restrictions\n"
        "- For data analysis, query the data first, then use Code Interpreter if needed\n"
    )
    
    # Get or create agent (Microsoft best practice for agent reuse)
    agent = get_or_create_agent(
        project_client=project_client,
        model=MODEL,
        name="MSSQL Database Agent",
        instructions=agent_instructions,
        tools=all_tools,
        force_create=False,  # Set to True to force new agent creation
    )
    pretty(f"[Agent] Total tools available: {len(all_tools)}")

    # Create a thread
    thread = project_client.agents.threads.create()
    pretty(f"[thread] id={thread.id}")

    # IMPORTANT: Add ONE user message. Do NOT inject tool/assistant messages yourself.
    user_prompt = "What is present in the dbo.Documents table? Summarize the results."
    project_client.agents.messages.create(
        thread_id=thread.id,
        role="user",
        content=user_prompt,
    )
    pretty("[message] role=user (added)")

    # Start the run
    run = project_client.agents.runs.create(thread_id=thread.id, agent_id=agent.id)
    pretty(f"[run] id={run.id} status={run.status}")

    # Drive the run until it completes, handling approvals/outputs
    try:
        final_run = drive_until_complete(project_client, thread, run, mcp_tool)
        pretty(f"[Final Run] Status: {final_run.status}")
        if hasattr(final_run, 'last_error') and final_run.last_error:
            pretty(f"[Final Run] Error: {final_run.last_error}")
    except Exception as e:
        pretty(f"[Error] Exception during run: {str(e)}")
        raise

    # Fetch and print the full conversation
    msgs = project_client.agents.messages.list(
        thread_id=thread.id,
        order=ListSortOrder.ASCENDING,
    )

    pretty("\n================ Conversation ================\n")
    for m in msgs:
        role = getattr(m, "role", "?")
        # Handle different content formats
        if hasattr(m, 'text_messages') and m.text_messages:
            content = m.text_messages[-1].text.value if m.text_messages[-1].text else ""
        else:
            content = getattr(m, "content", "")
        pretty(f"{role.upper()}: {content}\n")
    pretty("=============================================\n")

    # Agent cleanup (Microsoft best practice):
    # - Agents persist by design and should be reused across runs
    # - Only delete if you need to recreate with different configuration
    # - To reuse this agent, add AGENT_ID={agent.id} to your .env file
    # 
    # Uncomment to delete agent:
    # project_client.agents.delete_agent(agent.id)
    # pretty(f"Deleted agent: {agent.id}")


if __name__ == "__main__":
    main()