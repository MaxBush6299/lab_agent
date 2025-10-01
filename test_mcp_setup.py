"""
Test script to verify MCP server authentication and connectivity.
Run this before running the full agent to ensure everything is configured correctly.
"""

import os
import sys
import time
from dotenv import load_dotenv
from azure.identity import DefaultAzureCredential

# Load environment variables
load_dotenv()

# Configuration
MCP_SERVER_URL = os.environ.get("MCP_SERVER_URL")
MCP_AUTH_SCOPE = os.environ.get("MCP_AUTH_SCOPE", "17a97781-0078-4478-8b4e-fe5dda9e2400/.default")

def test_azure_authentication():
    """Test if we can obtain an Azure AD token."""
    print("=" * 70)
    print("TEST 1: Azure AD Authentication")
    print("=" * 70)
    
    try:
        credential = DefaultAzureCredential()
        print("✅ DefaultAzureCredential initialized")
        
        print(f"🔑 Requesting token with scope: {MCP_AUTH_SCOPE}")
        token_result = credential.get_token(MCP_AUTH_SCOPE)
        
        expires_in = int((token_result.expires_on - time.time()) / 60)
        print(f"✅ Token obtained successfully!")
        print(f"   Token length: {len(token_result.token)} characters")
        print(f"   Expires in: {expires_in} minutes")
        print(f"   Token preview: {token_result.token[:50]}...")
        
        return token_result.token
        
    except Exception as e:
        print(f"❌ Authentication failed: {str(e)}")
        print("\n💡 Troubleshooting:")
        print("   1. Run 'az login' to authenticate")
        print("   2. Verify you have access to the MCP resource")
        print("   3. Check MCP_AUTH_SCOPE in .env file")
        return None

def test_mcp_server_connectivity(token):
    """Test if we can connect to the MCP server."""
    import requests
    
    print("\n" + "=" * 70)
    print("TEST 2: MCP Server Connectivity")
    print("=" * 70)
    
    if not token:
        print("⚠️ Skipping (no token available)")
        return False
    
    if not MCP_SERVER_URL:
        print("❌ MCP_SERVER_URL not set in .env file")
        return False
    
    try:
        endpoint = f"{MCP_SERVER_URL.rstrip('/')}/message"
        print(f"🌐 Connecting to: {endpoint}")
        
        # Try a simple list_tables request with sessionId as query parameter
        import uuid
        session_id = str(uuid.uuid4())
        endpoint_with_session = f"{endpoint}?sessionId={session_id}"
        
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "list_tables",
                "arguments": {}
            }
        }
        
        print(f"📤 Sending JSON-RPC request: list_tables (sessionId: {session_id})")
        
        response = requests.post(
            endpoint_with_session,
            json=payload,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {token}",
                "Accept": "application/json"
            },
            timeout=10
        )
        
        print(f"📥 Response Status: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print(f"✅ MCP server responded successfully!")
            
            if "result" in data:
                print(f"   Result preview: {str(data['result'])[:200]}...")
                return True
            elif "error" in data:
                print(f"   ⚠️ Server returned error: {data['error']}")
                return False
        
        elif response.status_code == 401:
            print(f"❌ Authentication failed (401 Unauthorized)")
            print(f"   Response: {response.text[:200]}")
            print("\n💡 Troubleshooting:")
            print("   1. Verify MCP_AUTH_CLIENT_ID in .env")
            print("   2. Check if token has correct scope")
            print("   3. Verify Azure AD app registration")
            return False
        
        elif response.status_code == 403:
            print(f"❌ Authorization failed (403 Forbidden)")
            print(f"   Response: {response.text[:200]}")
            print("\n💡 Troubleshooting:")
            print("   1. Check Azure AD role assignments")
            print("   2. Verify SQL Database permissions")
            print("   3. Check if user is in required Azure AD group")
            return False
        
        else:
            print(f"❌ Unexpected status code: {response.status_code}")
            print(f"   Response: {response.text[:200]}")
            return False
        
    except requests.exceptions.Timeout:
        print(f"❌ Connection timeout")
        print("\n💡 Troubleshooting:")
        print("   1. Check if MCP server is running")
        print("   2. Verify network connectivity")
        print("   3. Check firewall rules")
        return False
    
    except requests.exceptions.ConnectionError as e:
        print(f"❌ Connection error: {str(e)}")
        print("\n💡 Troubleshooting:")
        print("   1. Verify MCP_SERVER_URL in .env")
        print("   2. Check if server is running: az container show ...")
        print("   3. Test with: curl http://your-server/health")
        return False
    
    except Exception as e:
        print(f"❌ Unexpected error: {str(e)}")
        import traceback
        print(f"   Traceback: {traceback.format_exc()}")
        return False

def test_configuration():
    """Test if all required environment variables are set."""
    print("\n" + "=" * 70)
    print("TEST 3: Configuration Check")
    print("=" * 70)
    
    required_vars = {
        "PROJECT_ENDPOINT": os.environ.get("PROJECT_ENDPOINT"),
        "MODEL_DEPLOYMENT_NAME": os.environ.get("MODEL_DEPLOYMENT_NAME"),
        "MCP_SERVER_URL": MCP_SERVER_URL,
        "MCP_SERVER_LABEL": os.environ.get("MCP_SERVER_LABEL"),
        "MCP_AUTH_SCOPE": MCP_AUTH_SCOPE,
    }
    
    optional_vars = {
        "AGENT_ID": os.environ.get("AGENT_ID"),
        "BING_CONNECTION_ID": os.environ.get("BING_CONNECTION_ID"),
    }
    
    all_ok = True
    
    print("\n📋 Required Configuration:")
    for key, value in required_vars.items():
        if value:
            preview = value[:50] + "..." if len(value) > 50 else value
            print(f"   ✅ {key}: {preview}")
        else:
            print(f"   ❌ {key}: NOT SET")
            all_ok = False
    
    print("\n📋 Optional Configuration:")
    for key, value in optional_vars.items():
        if value:
            preview = value[:50] + "..." if len(value) > 50 else value
            print(f"   ✅ {key}: {preview}")
        else:
            print(f"   ⚠️ {key}: NOT SET (optional)")
    
    return all_ok

def main():
    print("\n" + "🔍 MCP Server Configuration Test".center(70))
    print("=" * 70 + "\n")
    
    # Test 1: Configuration
    config_ok = test_configuration()
    
    if not config_ok:
        print("\n❌ Configuration incomplete - fix .env file before continuing")
        return False
    
    # Test 2: Authentication
    token = test_azure_authentication()
    
    if not token:
        print("\n❌ Authentication failed - fix authentication before continuing")
        return False
    
    # Test 3: Connectivity
    connectivity_ok = test_mcp_server_connectivity(token)
    
    # Summary
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    
    if connectivity_ok:
        print("✅ All tests passed!")
        print("🚀 You can now run main.py to start the agent")
        return True
    else:
        print("❌ Some tests failed")
        print("🔧 Fix the issues above before running the agent")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
