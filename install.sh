#!/bin/bash
# install.sh - Install dependencies for the lab-agent project

echo "Installing dependencies for lab-agent with MCP support..."

# Upgrade pip first
python -m pip install --upgrade pip

# Install the latest preview versions
pip install --pre azure-ai-projects>=1.1.0b4
pip install --pre azure-ai-agents>=1.2.0b4

# Install other dependencies
pip install -r requirements.txt

echo "Installation complete!"
echo "You can now run: python main.py"