# Azure AI Agents with MCP Lab

This repository contains a Python application that demonstrates how to use Azure AI Agents with Model Context Protocol (MCP) tools to access databases and external services.

## Features

- **Azure AI Agents integration** with MCP (Model Context Protocol)
- **Database MCP Server** integration for SQL operations
- **Agent reuse** following Microsoft best practices
- **Dynamic tool discovery** from MCP servers
- **Automatic tool approval handling**
- Support for Code Interpreter and Bing Search tools

## Prerequisites

- Python 3.9 or higher
- Azure subscription with AI Foundry project
- Azure CLI (logged in) or appropriate Azure credentials

## Installation

1. Clone the repository:
```bash
git clone https://github.com/MaxBush6299/lab_agent.git
cd lab_agent
```

2. Create and activate a virtual environment:
```bash
python -m venv .venv
.venv\Scripts\activate  # On Windows
# or
source .venv/bin/activate  # On Linux/Mac
```

3. Install the required packages (preview versions needed for MCP support):
```bash
pip install -r requirements.txt
```

4. Create a `.env` file with your Azure configuration:
```env
PROJECT_ENDPOINT=https://your-project.ai.azure.com/api/projects/your-project-name
MODEL_DEPLOYMENT_NAME=gpt-4o
MCP_SERVER_URL=http://your-mcp-server:8080/mcp
MCP_SERVER_LABEL=MSSQL_MCP
BING_CONNECTION_ID=your-bing-connection-id

# Optional: Reuse existing agent (Microsoft best practice)
# AGENT_ID=asst_your_agent_id_here
```

## Agent Reuse (Microsoft Best Practice)

This application implements Microsoft's recommended pattern for agent reuse:

### First Run
When you run the application for the first time, it will create a new agent and display:
```
💡 TIP: To reuse this agent on future runs, add to your .env file:
   AGENT_ID=asst_abc123xyz456
```

### Subsequent Runs
1. Copy the agent ID and add it to your `.env` file:
   ```env
   AGENT_ID=asst_abc123xyz456
   ```

2. On subsequent runs, the application will reuse the existing agent instead of creating a new one:
   ```
   [Agent] ✅ Successfully reused agent: asst_abc123xyz456
   ```

### Benefits
- **Cost savings** - Avoid creating unnecessary agents
- **Faster startup** - Skip agent creation overhead
- **Consistency** - Same agent configuration across runs
- **Resource management** - Fewer orphaned agents in Azure

### Force New Agent Creation
To create a new agent even when `AGENT_ID` is set, modify `main.py`:
```python
agent = get_or_create_agent(
    project_client=project_client,
    model=MODEL,
    name="Enhanced MCP Agent",
    instructions=agent_instructions,
    tools=all_tools,
    force_create=True,  # ← Set to True
)
```

## Usage

### Running the Main Application

```bash
python main.py
```

## MCP Tools Available

The application provides access to these Microsoft Learn MCP tools:

- `microsoft_docs_search`: Search Microsoft's official documentation
- `microsoft_docs_fetch`: Fetch complete documentation pages
- `microsoft_code_sample_search`: Find official Microsoft code examples

## Key Insights

- **Preview Packages Required**: MCP functionality is only available in preview versions of Azure AI packages
- **System Prompt Matters**: Explicit instructions help the AI use MCP tools effectively


## Troubleshooting

If you encounter import errors with MCP-related classes, ensure you're using the preview packages:

```bash
pip install --pre --upgrade azure-ai-agents azure-ai-projects
```

## Files

- `main.py`: Main application with full MCP workflow including approval handling

## Contributing

Feel free to submit issues and enhancement requests!

## License

This project is for educational and demonstration purposes.