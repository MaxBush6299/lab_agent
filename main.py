import os, time
from pathlib import Path
from azure.ai.projects import AIProjectClient
from azure.identity import DefaultAzureCredential
from azure.ai.agents.models import CodeInterpreterTool
from dotenv import load_dotenv
from azure.ai.agents.models import (
    ListSortOrder,
    McpTool,
    RequiredMcpToolCall,
    RunStepActivityDetails,
    SubmitToolApprovalAction,
    ToolApproval,
)

load_dotenv()

######################################################
#MCP Tool Setup
#######################################################


# Get MCP server configuration from environment variables
mcp_server_url = os.environ.get("MCP_SERVER_URL")
mcp_server_label = os.environ.get("MCP_SERVER_LABEL")

project_client = AIProjectClient(
    endpoint=os.environ["PROJECT_ENDPOINT"],
    credential=DefaultAzureCredential(),
)
# Initialize agent MCP tool
mcp_tool = McpTool(
    server_label=mcp_server_label,
    server_url=mcp_server_url,
    allowed_tools=[],  # Optional: specify allowed tools
)

# You can also add or remove allowed tools dynamically
microsoft_docs_search="microsoft_docs_search"
microsoft_docs_fetch="microsoft_docs_fetch"
microsoft_code_sample_search="microsoft_code_sample_search"
mcp_tool.allow_tool(microsoft_docs_fetch)
print(f"Allowed tools: {mcp_tool.allowed_tools}")
mcp_tool.allow_tool(microsoft_docs_search)
print(f"Allowed tools: {mcp_tool.allowed_tools}")
mcp_tool.allow_tool(microsoft_code_sample_search)
print(f"Allowed tools: {mcp_tool.allowed_tools}")


######################################################
#Project Client Setup
#######################################################

# Create an AIProjectClient from an endpoint, copied from your Azure AI Foundry project.
# You need to login to Azure subscription via Azure CLI and set the environment variables
project_endpoint = os.environ["PROJECT_ENDPOINT"]  # Ensure the PROJECT_ENDPOINT environment variable is set

# Create an AIProjectClient instance
project_client = AIProjectClient(
    endpoint=project_endpoint,
    credential=DefaultAzureCredential(),  # Use Azure Default Credential for authentication
)

code_interpreter = CodeInterpreterTool()
with project_client:
    # Create an agent with the Code Interpreter tool and MCP tool
    agent = project_client.agents.create_agent(
        model=os.environ["MODEL_DEPLOYMENT_NAME"],  # Model deployment name
        name="my-agent",  # Name of the agent
        instructions="""You are a helpful coding assistant that can also assist with general questions.

## Querying Microsoft Documentation

You have access to MCP tools called `microsoft_docs_search`, `microsoft_docs_fetch`, and `microsoft_code_sample_search` - these tools allow you to search through and fetch Microsoft's latest official documentation and code samples, and that information might be more detailed or newer than what's in your training data set.

When handling questions around how to work with Microsoft technologies, Azure services, C#, F#, ASP.NET Core, Microsoft.Extensions, NuGet, Entity Framework, the `dotnet` runtime, or any Microsoft-related topics - please use these tools for research purposes when dealing with specific questions.

Always try to use the MCP tools to provide the most current and accurate information from official Microsoft documentation. Use phrases like 'search Microsoft docs' or 'fetch full doc' to indicate when you're consulting official sources.""",  # Instructions for the agent
        tools=[code_interpreter.definitions[0]] + mcp_tool.definitions  # Attach the tools
    )
    print(f"Created agent, ID: {agent.id}")

    # Create a thread for communication
    thread = project_client.agents.threads.create()
    print(f"Created thread, ID: {thread.id}")

    # Add a message to the thread
    message = project_client.agents.messages.create(
        thread_id=thread.id,
        role="user",  # Role of the message sender
        content="I would like to get the AI-102 certification. What do you recommend I study?",  # Message content
    )
    print(f"Created message, ID: {message['id']}")

    # Create and process an agent run
    run = project_client.agents.runs.create(
        thread_id=thread.id,
        agent_id=agent.id,
        tool_resources=mcp_tool.resources,
        additional_instructions="Please address the user as Jane Doe. The user has a premium account",
    )
    print(f"Created run, ID: {run.id}")

    while run.status in ["queued", "in_progress", "requires_action"]:
        time.sleep(1)
        run = project_client.agents.runs.get(thread_id=thread.id, run_id=run.id)

        if run.status == "requires_action" and isinstance(run.required_action, SubmitToolApprovalAction):
            tool_calls = run.required_action.submit_tool_approval.tool_calls
            if not tool_calls:
                print("No tool calls provided - cancelling run")
                project_client.agents.runs.cancel(thread_id=thread.id, run_id=run.id)
                break

            tool_approvals = []
            for tool_call in tool_calls:
                if isinstance(tool_call, RequiredMcpToolCall):
                    try:
                        print(f"Approving tool call: {tool_call}")
                        tool_approvals.append(
                            ToolApproval(
                                tool_call_id=tool_call.id,
                                approve=True,
                                headers=mcp_tool.headers,
                            )
                        )
                    except Exception as e:
                        print(f"Error approving tool_call {tool_call.id}: {e}")

            print(f"tool_approvals: {tool_approvals}")
            if tool_approvals:
                project_client.agents.runs.submit_tool_outputs(
                    thread_id=thread.id, run_id=run.id, tool_approvals=tool_approvals
                )

        print(f"Current run status: {run.status}")

    print(f"Run completed with status: {run.status}")
    if run.status == "failed":
        print(f"Run failed: {run.last_error}")

    # Display run steps and tool calls
    run_steps = project_client.agents.run_steps.list(thread_id=thread.id, run_id=run.id)

    # Loop through each step
    for step in run_steps:
        print(f"Step {step['id']} status: {step['status']}")

        # Check if there are tool calls in the step details
        step_details = step.get("step_details", {})
        tool_calls = step_details.get("tool_calls", [])

        if tool_calls:
            print("  MCP Tool calls:")
            for call in tool_calls:
                print(f"    Tool Call ID: {call.get('id')}")
                print(f"    Type: {call.get('type')}")

        if isinstance(step_details, RunStepActivityDetails):
            for activity in step_details.activities:
                for function_name, function_definition in activity.tools.items():
                    print(
                        f'  The function {function_name} with description "{function_definition.description}" will be called.:'
                    )
                    if len(function_definition.parameters) > 0:
                        print("  Function parameters:")
                        for argument, func_argument in function_definition.parameters.properties.items():
                            print(f"      {argument}")
                            print(f"      Type: {func_argument.type}")
                            print(f"      Description: {func_argument.description}")
                    else:
                        print("This function has no parameters")

        print()  # add an extra newline between steps

    # Fetch and log all messages
    messages = project_client.agents.messages.list(thread_id=thread.id, order=ListSortOrder.ASCENDING)
    print("\nConversation:")
    print("-" * 50)
    for msg in messages:
        if msg.text_messages:
            last_text = msg.text_messages[-1]
            print(f"{msg.role.upper()}: {last_text.text.value}")
            print("-" * 50)

    # Example of dynamic tool management
    print(f"\nDemonstrating dynamic tool management:")
    print(f"Current allowed tools: {mcp_tool.allowed_tools}")

    # Remove a tool
    try:
        mcp_tool.disallow_tool(microsoft_docs_fetch)
        print(f"After removing {microsoft_docs_fetch}: {mcp_tool.allowed_tools}")
        mcp_tool.disallow_tool(microsoft_docs_search)
        print(f"After removing {microsoft_docs_search}: {mcp_tool.allowed_tools}")
        mcp_tool.disallow_tool(microsoft_code_sample_search)
        print(f"After removing {microsoft_code_sample_search}: {mcp_tool.allowed_tools}")
    except ValueError as e:
        print(f"Error removing tool: {e}")


    # Uncomment these lines to delete the agent when done
    # project_client.agents.delete_agent(agent.id)
    # print("Deleted agent")