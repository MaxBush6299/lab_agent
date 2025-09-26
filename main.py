import os, time
from pathlib import Path
from typing import Optional, Dict, Any
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
    Replace this stub with a real call to your MCP server IF your flow requires you
    to *manually* execute the tool and return its output.

    Some setups only need approvals, and the runtime will do the execution.
    In others, you'll receive SubmitToolOutputsAction and must return outputs yourself.

    IMPORTANT:
    - Return a JSON-serializable value (str or dict).
    - Keep it small; summarize large blobs.

    For smoke testing, we echo back the inputs.
    """
    # TODO: implement a real call to your MCP server if required by your setup
    # Example shape (pseudo):
    # result = mcp_client.invoke(server_label=server_label, tool=tool_name, arguments=args, headers=headers)
    # return result
    return {
        "status": "ok",
        "server_label": server_label,
        "tool": tool_name,
        "echo_args": args,
    }


def drive_until_complete(project_client: AIProjectClient, thread, run, mcp_tool: McpTool, poll_interval: float = 0.7):
    """
    Poll the run and satisfy required actions until it reaches a terminal state.
    Handles:
    - SubmitToolApprovalAction   -> submit_tool_approvals(...)
    - SubmitToolOutputsAction    -> execute tool + submit_tool_outputs(...)
    """
    def _log_required_action(ra):
        try:
            if isinstance(ra, SubmitToolApprovalAction):
                for c in ra.submit_tool_approval.tool_calls or []:
                    pretty(f"[RA-approve] id={c.id} server={getattr(c,'server_label',None)} tool={getattr(c,'name',None)}")
            elif isinstance(ra, SubmitToolOutputsAction):
                for c in ra.submit_tool_outputs.tool_calls or []:
                    pretty(f"[RA-output ] id={c.id} server={getattr(c,'server_label',None)} tool={getattr(c,'name',None)} args={getattr(c,'arguments',None)}")
        except Exception as e:
            pretty(f"[RA-log-error] {e!r}")

    while run.status in ("queued", "in_progress", "requires_action"):
        if run.status != "requires_action":
            time.sleep(poll_interval)
            run = project_client.agents.runs.get(thread_id=thread.id, run_id=run.id)
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

    # Build the MCP tool; label + URL must match the tool calls your agent will make.
    mcp_tool = McpTool(
        server_label=MCP_SERVER_LABEL,
        server_url=MCP_SERVER_URL ,
    )

    # Allow exactly the tools you expect from that MCP server
    mcp_tool.allow_tool("microsoft_docs_search")
    mcp_tool.allow_tool("microsoft_docs_fetch")
    mcp_tool.allow_tool("microsoft_code_sample_search")

    # Create Code Interpreter and Bing Grounding tools
    code_interpreter = CodeInterpreterTool()
    bing_grounding = BingGroundingTool(connection_id=BING_CONNECTION_ID)
    
    # Combine all tools
    all_tools = [code_interpreter.definitions[0]] + [bing_grounding.definitions[0]] + mcp_tool.definitions
    
    # Create the agent with enhanced instructions
    agent = project_client.agents.create_agent(
        model=MODEL,
        name="Enhanced MCP Agent",
        instructions=(
            "You are a helpful assistant with multiple capabilities:\n"
            "- Use Code Interpreter for Python code execution, data analysis, and calculations\n"
            "- Use Bing Search for real-time web information and current events\n"
            "- Use Microsoft Learn MCP tools for official Microsoft documentation\n\n"
            "When users ask about Microsoft technologies, prioritize using the MCP tools. "
            "For coding tasks, use the Code Interpreter. For current events or general web info, use Bing Search."
        ),
        tools=all_tools,
    )
    pretty(f"[agent] id={agent.id} model={agent.model}")

    # Create a thread
    thread = project_client.agents.threads.create()
    pretty(f"[thread] id={thread.id}")

    # IMPORTANT: Add ONE user message. Do NOT inject tool/assistant messages yourself.
    user_prompt = "What is Azure AI Foundry? Please search Microsoft Learn for official documentation. Also, can you calculate the square root of 144 using code?"
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
    final_run = drive_until_complete(project_client, thread, run, mcp_tool)

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