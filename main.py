import os, time
import requests
import json
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

######################################################
#Configuration
#######################################################

MODEL = os.getenv("MODEL_DEPLOYMENT_NAME", "gpt-4o")

# Get MCP server configuration from environment variables
MCP_SERVER_URL = os.environ.get("MCP_SERVER_URL")
MCP_SERVER_LABEL = os.environ.get("MCP_SERVER_LABEL")
BING_CONNECTION_ID = os.environ.get("BING_CONNECTION_ID")

CONN_STR = os.environ["PROJECT_ENDPOINT"]  

# --------------------------------------------------------------------------------------
# MCP Server Discovery
# --------------------------------------------------------------------------------------

def discover_mcp_tools(server_url: str, timeout: int = 10) -> List[str]:
    """
    Discover available tools from an MCP server by calling its introspection endpoint.
    
    Args:
        server_url: The base URL of the MCP server
        timeout: Request timeout in seconds
        
    Returns:
        List of tool names available on the server
    """
    try:
        # Try common MCP introspection endpoints
        endpoints_to_try = [
            f"{server_url}/tools",
            f"{server_url}/list_tools", 
            f"{server_url}/capabilities",
            f"{server_url}/introspect"
        ]
        
        for endpoint in endpoints_to_try:
            try:
                pretty(f"[MCP Discovery] Trying endpoint: {endpoint}")
                
                # Make request to the MCP server
                response = requests.get(
                    endpoint,
                    headers={
                        "Content-Type": "application/json",
                        "Accept": "application/json"
                    },
                    timeout=timeout
                )
                
                pretty(f"[MCP Discovery] Response status: {response.status_code}")
                pretty(f"[MCP Discovery] Response headers: {dict(response.headers)}")
                
                if response.status_code == 200:
                    data = response.json()
                    pretty(f"[MCP Discovery] Response data keys: {list(data.keys()) if isinstance(data, dict) else type(data)}")
                    
                    # Try to extract tool names from different response formats
                    tools = extract_tools_from_response(data)
                    if tools:
                        pretty(f"[MCP Discovery] Found {len(tools)} tools: {tools}")
                        return tools
                else:
                    pretty(f"[MCP Discovery] Non-200 response body: {response.text[:200]}...")
                        
            except requests.exceptions.RequestException as e:
                pretty(f"[MCP Discovery] Endpoint {endpoint} failed: {str(e)}")
                continue
                
        # If introspection fails, try MCP protocol method
        tools = try_mcp_protocol_discovery(server_url, timeout)
        if tools:
            return tools
            
    except Exception as e:
        pretty(f"[MCP Discovery] Error during discovery: {str(e)}")
    
    # Fallback to your known Microsoft Learn tools
    pretty("[MCP Discovery] Using fallback tools for Microsoft Learn")
    return [
        "microsoft_docs_search",
        "microsoft_docs_fetch", 
        "microsoft_code_sample_search"
    ]

def extract_tools_from_response(data: Dict[str, Any]) -> List[str]:
    """Extract tool names from various response formats."""
    tools = []
    
    # Format 1: {"tools": [{"name": "tool1"}, {"name": "tool2"}]}
    if "tools" in data and isinstance(data["tools"], list):
        for tool in data["tools"]:
            if isinstance(tool, dict) and "name" in tool:
                tools.append(tool["name"])
            elif isinstance(tool, str):
                tools.append(tool)
    
    # Format 2: {"capabilities": {"tools": ["tool1", "tool2"]}}
    elif "capabilities" in data and "tools" in data["capabilities"]:
        capabilities_tools = data["capabilities"]["tools"]
        if isinstance(capabilities_tools, list):
            tools.extend([str(tool) for tool in capabilities_tools])
    
    # Format 3: Direct list ["tool1", "tool2"]
    elif isinstance(data, list):
        tools.extend([str(tool) for tool in data])
    
    # Format 4: {"result": {"tools": [...]}}
    elif "result" in data:
        return extract_tools_from_response(data["result"])
    
    return tools

def try_mcp_protocol_discovery(server_url: str, timeout: int) -> List[str]:
    """Try MCP protocol-specific discovery methods."""
    try:
        # MCP JSON-RPC method for listing tools
        payload = {
            "jsonrpc": "2.0",
            "method": "tools/list",
            "id": 1
        }
        
        response = requests.post(
            server_url,
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=timeout
        )
        
        if response.status_code == 200:
            data = response.json()
            if "result" in data and "tools" in data["result"]:
                tools = []
                for tool in data["result"]["tools"]:
                    if isinstance(tool, dict) and "name" in tool:
                        tools.append(tool["name"])
                return tools
                
    except Exception as e:
        pretty(f"[MCP Protocol] Discovery failed: {str(e)}")
    
    return []

# --------------------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------------------

def pretty(msg: str):
    """Tiny logger to keep stdout readable."""
    print(msg, flush=True)


def execute_mcp_tool(
    *,
    server_label: str,
    tool_name: str,
    args: Dict[str, Any],
    headers: Optional[Dict[str, str]] = None,
) -> Any:
    """
    Execute MCP tool by making direct HTTP calls to the MCP server.
    This bypasses Azure's MCP runtime and calls the server directly.
    """
    try:
        # Use the global MCP_SERVER_URL
        server_url = MCP_SERVER_URL
        pretty(f"[MCP Execute] Starting execution for tool '{tool_name}' on server '{server_label}'")
        pretty(f"[MCP Execute] Server URL: {server_url}")
        pretty(f"[MCP Execute] Arguments: {args}")
        pretty(f"[MCP Execute] Headers: {headers}")
        
        # Try JSON-RPC 2.0 first
        payload = {
            "jsonrpc": "2.0",
            "method": f"tools/{tool_name}",
            "params": args,
            "id": 1
        }
        
        pretty(f"[MCP Execute] Sending JSON-RPC payload: {payload}")
        
        response = requests.post(
            server_url,
            json=payload,
            headers={"Content-Type": "application/json", **(headers or {})},
            timeout=30
        )
        
        pretty(f"[MCP Execute] JSON-RPC Response Status: {response.status_code}")
        pretty(f"[MCP Execute] JSON-RPC Response Headers: {dict(response.headers)}")
        
        if response.status_code == 200:
            data = response.json()
            pretty(f"[MCP Execute] JSON-RPC Response Data: {data}")
            if "result" in data:
                pretty(f"[MCP Execute] Success! Returning result: {data['result']}")
                return data["result"]
            elif "error" in data:
                pretty(f"[MCP Execute] JSON-RPC Error: {data['error']}")
                return {"error": f"MCP Error: {data['error']}"}
        
        pretty(f"[MCP Execute] JSON-RPC failed with status {response.status_code}, trying REST endpoint")
        pretty(f"[MCP Execute] JSON-RPC Response body: {response.text}")
        
        # If JSON-RPC fails, try REST endpoint
        rest_url = f"{server_url.rstrip('/')}/{tool_name}"
        pretty(f"[MCP Execute] Trying REST URL: {rest_url}")
        
        response = requests.post(
            rest_url,
            json=args,
            headers={"Content-Type": "application/json", **(headers or {})},
            timeout=30
        )
        
        pretty(f"[MCP Execute] REST Response Status: {response.status_code}")
        pretty(f"[MCP Execute] REST Response Body: {response.text}")
        
        if response.status_code == 200:
            result = response.json()
            pretty(f"[MCP Execute] REST Success! Returning: {result}")
            return result
        
        error_msg = f"HTTP {response.status_code}: {response.text}"
        pretty(f"[MCP Execute] Both methods failed. Final error: {error_msg}")
        return {"error": error_msg}
        
    except Exception as e:
        pretty(f"[MCP Execute Error] Exception occurred: {str(e)}")
        import traceback
        pretty(f"[MCP Execute Error] Traceback: {traceback.format_exc()}")
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
            for call in ra.submit_tool_approval.tool_calls or []:
                if isinstance(call, RequiredMcpToolCall):
                    approvals.append(
                        ToolApproval(
                            tool_call_id=call.id,
                            approve=True,
                            headers=getattr(mcp_tool, "headers", None) or None,
                        )
                    )
            if approvals:
                pretty(f"[submit approvals] count={len(approvals)}")
                project_client.agents.runs.submit_tool_outputs(
                    thread_id=thread.id,
                    run_id=run.id,
                    tool_approvals=approvals,
                )

        # ---------- B) TOOL OUTPUTS ----------
        elif isinstance(ra, SubmitToolOutputsAction):
            outputs = []
            for call in ra.submit_tool_outputs.tool_calls or []:
                if isinstance(call, RequiredMcpToolCall):
                    pretty(f"[execute] {call.id} tool={call.name} server={call.server_label}")
                    result = execute_mcp_tool(
                        server_label=call.server_label,
                        tool_name=call.name,
                        args=call.arguments,
                        headers=getattr(mcp_tool, "headers", None) or None,
                    )
                    outputs.append({"tool_call_id": call.id, "output": result})

            if outputs:
                pretty(f"[submit outputs] count={len(outputs)}")
                project_client.agents.runs.submit_tool_outputs(
                    thread_id=thread.id,
                    run_id=run.id,
                    tool_outputs=outputs,
                )

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
    
    # Create dynamic instructions based on discovered tools
    mcp_description = "- Use MSSQL MCP tools for database operations (create, read, update tables, insert data, etc.)"
    if any("microsoft" in tool.lower() or "docs" in tool.lower() for tool in available_tools):
        mcp_description = "- Use Microsoft Learn MCP tools for official Microsoft documentation"
    
    # Create the agent with enhanced instructions
    agent = project_client.agents.create_agent(
        model=MODEL,
        name="Enhanced MCP Agent",
        instructions=(
            "You are a helpful assistant with multiple capabilities:\n"
            "- Use Code Interpreter for Python code execution, data analysis, and calculations\n"
            "- Use Bing Search for real-time web information and current events\n"
            f"{mcp_description}\n\n"
            "When users ask about database operations, SQL queries, or table management, use the MSSQL MCP tools. "
            "For coding tasks, use the Code Interpreter. For current events or general web info, use Bing Search. "
            "Available MSSQL operations: list tables, describe tables, read data, insert data, update data, create tables, create indexes, and drop tables."
        ),
        tools=all_tools,
    )
    pretty(f"[agent] id={agent.id} model={agent.model}")
    pretty(f"[agent] Total tools available: {len(all_tools)}")

    # Create a thread
    thread = project_client.agents.threads.create()
    pretty(f"[thread] id={thread.id}")

    # IMPORTANT: Add ONE user message. Do NOT inject tool/assistant messages yourself.
    user_prompt = "What are my top 3 customers?"
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

    # Cleanup hint:
    # If you're iterating frequently, you may want to delete the agent and/or thread here.


if __name__ == "__main__":
    main()