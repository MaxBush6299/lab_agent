# Azure AI Agents with MCP Lab

This repository contains a Python application that demonstrates how to use Azure AI Agents with Model Context Protocol (MCP) tools to access Microsoft Learn documentation.

## Features

- Azure AI Agents integration with MCP (Model Context Protocol)
- Microsoft Learn MCP Server integration for accessing official documentation
- Support for both programmatic usage and Azure AI Foundry playground
- Automatic tool approval handling

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
pip install --pre azure-ai-agents azure-ai-projects azure-identity python-dotenv
```

4. Create a `.env` file with your Azure configuration:
```env
PROJECT_ENDPOINT=https://your-project.cognitiveservices.azure.com/
MODEL_DEPLOYMENT_NAME=your-model-deployment-name
MCP_SERVER_URL=https://learn.microsoft.com/api/mcp
MCP_SERVER_LABEL=microsoft.docs.mcp
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