# Azure AI Foundry Agent - MCP Configuration Summary

## ✅ What Was Configured

Your Azure AI Foundry agent has been successfully configured to use the MSSQL MCP server with Azure AD authentication and Row-Level Security.

## 🔑 Key Changes Made

### 1. **Azure AD Authentication** (`main.py` lines 45-89)

Added `get_mcp_access_token()` function that:
- Uses `DefaultAzureCredential` (same as AI Foundry client)
- Requests tokens with scope: `17a97781-0078-4478-8b4e-fe5dda9e2400/.default`
- Caches tokens for 5 minutes to reduce Azure AD requests
- Automatically refreshes expired tokens

### 2. **MCP Tool Discovery** (`main.py` lines 94-171)

Updated `discover_mcp_tools()` function to:
- Return 8 known MSSQL tools: `query_sql`, `execute_sql`, `list_tables`, `describe_table`, `create_table`, `drop_table`, `create_index`, `update_data`
- Support introspection for other MCP servers
- Include authentication in discovery requests

### 3. **JSON-RPC 2.0 Tool Execution** (`main.py` lines 243-368)

Completely rewrote `execute_mcp_tool()` function to:
- Format requests using JSON-RPC 2.0 protocol
- Use `method: "tools/call"` with `params: {name, arguments}`
- Include `Authorization: Bearer <TOKEN>` header
- Call `/message` endpoint (not `/tools/toolname`)
- Handle MCP-style responses with `content` arrays
- Provide detailed error handling (401, 403, etc.)

### 4. **Enhanced Agent Instructions** (`main.py` lines 549-578)

Created comprehensive instructions that:
- Document all 8 MSSQL tools with descriptions
- Explain Row-Level Security (RLS) behavior
- Provide guidelines for using tools effectively
- Include Code Interpreter and Bing Search capabilities

### 5. **Environment Configuration** (`.env`)

Added authentication parameters:
```bash
MCP_AUTH_TENANT_ID=2e9b0657-eef8-47af-8747-5e89476faaab
MCP_AUTH_CLIENT_ID=17a97781-0078-4478-8b4e-fe5dda9e2400
MCP_AUTH_SCOPE=17a97781-0078-4478-8b4e-fe5dda9e2400/.default
```

Updated MCP server URL to correct endpoint:
```bash
MCP_SERVER_URL=http://mssql-mcp-server-hxqif63svfkuq.westus.azurecontainer.io:8080/mcp
```

## 📁 New Files Created

### 1. **MCP_SETUP_GUIDE.md**
Comprehensive documentation including:
- Authentication flow diagram
- Tool descriptions and examples
- JSON-RPC request/response formats
- Row-Level Security explanation
- Testing scenarios
- Troubleshooting guide

### 2. **test_mcp_setup.py**
Automated test script that verifies:
- ✅ Configuration completeness
- ✅ Azure AD token acquisition
- ✅ MCP server connectivity
- ✅ JSON-RPC communication

## 🚀 How to Use

### Step 1: Test Configuration

```powershell
# Ensure Azure authentication
az login

# Run configuration test
python test_mcp_setup.py
```

Expected output:
```
✅ All tests passed!
🚀 You can now run main.py to start the agent
```

### Step 2: Run the Agent

```powershell
python main.py
```

The agent will:
1. ✅ Obtain Azure AD access token
2. ✅ Discover 8 MSSQL tools
3. ✅ Create/reuse agent (see `AGENT_ID` tip)
4. ✅ Process user query with database access

### Step 3: Test Natural Language Queries

Try these examples:

**List tables:**
```
User: "What tables are in the database?"
```

**Query with RLS:**
```
User: "Show me all my documents"
```

**Table schema:**
```
User: "What columns does Security.Documents have?"
```

**Insert data:**
```
User: "Add a document titled 'Q1 Report' to my documents"
```

## 🔍 What Happens Behind the Scenes

### Example: User asks "Show me my documents"

1. **Agent decides to use `query_sql` tool**
   ```
   Tool: query_sql
   Args: {"query": "SELECT * FROM Security.Documents"}
   ```

2. **Python code obtains Azure AD token**
   ```python
   token = get_mcp_access_token()
   # Returns: eyJ0eXAiOiJKV1QiLCJhbG...
   ```

3. **Formats JSON-RPC 2.0 request**
   ```json
   {
     "jsonrpc": "2.0",
     "id": 1696186000000,
     "method": "tools/call",
     "params": {
       "name": "query_sql",
       "arguments": {"query": "SELECT * FROM Security.Documents"}
     }
   }
   ```

4. **Sends authenticated HTTP request**
   ```
   POST http://...westus.azurecontainer.io:8080/mcp/message
   Authorization: Bearer eyJ0eXAiOiJKV1QiLCJhbG...
   Content-Type: application/json
   ```

5. **MCP server processes request**
   - Validates JWT token
   - Exchanges for SQL Database token (OBO flow)
   - Executes query as user: `mb6299@MngEnvMCAP095199.onmicrosoft.com`
   - RLS filters results (only shows user's 2 documents)

6. **Returns JSON-RPC response**
   ```json
   {
     "jsonrpc": "2.0",
     "id": 1696186000000,
     "result": {
       "content": [
         {
           "type": "text",
           "text": "[{\"DocumentID\": 1, \"Title\": \"Doc1\", ...}]"
         }
       ]
     }
   }
   ```

7. **Python code extracts result**
   ```python
   result_text = data["result"]["content"][0]["text"]
   # Returns: "[{\"DocumentID\": 1, ...}]"
   ```

8. **Agent presents to user**
   ```
   "You have 2 documents:
   1. Doc1 (ID: 1)
   2. Doc2 (ID: 2)"
   ```

## 🛡️ Security Features

### 1. **Azure AD Authentication**
- No hardcoded credentials
- Uses managed identity in production
- Token caching reduces requests
- Automatic token refresh

### 2. **Row-Level Security (RLS)**
- Users only see their data
- Identity flows through entire stack
- Cannot bypass with SQL injection
- Enforced at database level

### 3. **On-Behalf-Of (OBO) Flow**
- MCP server exchanges user token for SQL token
- Maintains user identity chain
- Audit logs show actual user
- Per-user connection pooling

## 📊 Logging and Debugging

The agent provides detailed logging at each step:

```
[MCP Auth] Obtaining Azure AD access token...
[MCP Auth] ✅ Token obtained successfully (expires in 59 minutes)
[MCP Discovery] Using known MSSQL MCP tools
[MCP Setup] Allowed tool: query_sql
[MCP Setup] Allowed tool: execute_sql
...
[Agent] ✅ Successfully reused agent: asst_kHabTWJ0v5XkaQxVtxwNRhdA
[MCP Execute] Starting execution for tool 'query_sql'
[MCP Execute] JSON-RPC Request: {...}
[MCP Execute] Calling endpoint: http://.../mcp/message
[MCP Execute] Response Status: 200
[MCP Execute] ✅ Success! Result: ...
```

## 🔧 Troubleshooting

### Issue: "Authentication failed"

**Check:**
1. Run `az login`
2. Verify `MCP_AUTH_SCOPE` in `.env`
3. Test with `python test_mcp_setup.py`

### Issue: "Empty results from query"

**This is normal!** RLS is working - you only see your data.

**Verify:**
```python
# In SQL:
SELECT SUSER_SNAME()  -- Should show your identity
```

### Issue: "Cannot insert with different owner"

**This is expected!** RLS blocks inserts with wrong owner.

**Solution:** Let the agent insert without specifying owner:
```sql
-- ❌ This will fail:
INSERT INTO Security.Documents (Title, OwnerUPN) 
VALUES ('Doc', 'other@domain.com')

-- ✅ This will work:
INSERT INTO Security.Documents (Title, OwnerUPN) 
VALUES ('Doc', SUSER_SNAME())
```

## 📚 Next Steps

1. **Run the test script**: `python test_mcp_setup.py`
2. **Start the agent**: `python main.py`
3. **Try example queries** (see MCP_SETUP_GUIDE.md)
4. **Check logs** for detailed execution trace
5. **Review MCP_SETUP_GUIDE.md** for comprehensive documentation

## ✨ Microsoft Best Practices Implemented

- ✅ **Agent Reuse**: Set `AGENT_ID` in `.env` to reuse agents
- ✅ **DefaultAzureCredential**: Works in dev, test, and production
- ✅ **Token Caching**: Minimizes Azure AD requests
- ✅ **Error Handling**: Graceful degradation with informative messages
- ✅ **RLS Enforcement**: User identity flows through entire stack
- ✅ **Detailed Logging**: Comprehensive tracing for debugging

## 📞 Support

If you encounter issues:
1. Check logs for detailed error messages
2. Run `python test_mcp_setup.py` to diagnose
3. Review MCP_SETUP_GUIDE.md troubleshooting section
4. Verify MCP server health: `az container show --name mssql-mcp-server --resource-group <rg>`

---

**Configuration Status:** ✅ Complete and Ready to Use

**Last Updated:** October 1, 2025
