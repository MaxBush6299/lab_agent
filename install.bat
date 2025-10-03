@echo off
REM install.bat - Install dependencies for the lab-agent project on Windows

echo Installing dependencies for lab-agent with MCP support...

REM Upgrade pip first
python -m pip install --upgrade pip

REM Install the latest preview versions
pip install --pre "azure-ai-projects>=1.1.0b4"
pip install --pre "azure-ai-agents>=1.2.0b4"

REM Install other dependencies
pip install -r requirements.txt

echo Installation complete!
echo You can now run: python main.py

pause