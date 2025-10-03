# Azure AI Foundry Agent with MCP Server Setup Guide

This guide explains how to configure an Azure AI Foundry Agent to use an MCP (Model Context Protocol) server with Azure AD authentication and Row-Level Security.

## 🎯 Overview

Your agent is now configured to:
- ✅ Authenticate with Azure AD OAuth 2.0
- ✅ Call 8 MSSQL database tools via JSON-RPC 2.0
- ✅ Respect Row-Level Security (users only see their data)
- ✅ Execute database operations with user identity
- ✅ Handle errors gracefully with detailed logging

## 🔐 Authentication Flow

```
1. Agent needs to call MCP tool
2. Python code obtains Azure AD token using DefaultAzureCredential
3. Token is cached for 5 minutes to minimize requests
4. Token is sent with each MCP request: Authorization: Bearer <TOKEN>
5. MCP server validates JWT token
6. MCP server exchanges token for SQL Database token (On-Behalf-Of flow)
7. SQL queries execute with user's identity (RLS enforced)
```

## 🛠️ Available MCP Tools

The agent has access to 8 database tools:

| Tool | Description | Example |
|------|-------------|---------|
| `query_sql` | Execute SELECT queries | "Show me all documents" |
| `execute_sql` | Execute INSERT/UPDATE/DELETE | "Insert a new document" |
| `list_tables` | List all database tables | "What tables are available?" |
| `describe_table` | Get table schema | "Describe the Documents table" |
| `create_table` | Create new tables | "Create a Products table" |
| `drop_table` | Delete tables | "Drop the old_data table" |
| `create_index` | Create performance indexes | "Create index on CustomerID" |
| `update_data` | Update existing records | "Update the price of product 123" |

## 📋 Configuration Files

### `.env` File

```bash
# Azure AI Foundry Project
PROJECT_ENDPOINT=https://learnagent6299.services.ai.azure.com/api/projects/learnagent
MODEL_DEPLOYMENT_NAME=gpt-4.1
BING_CONNECTION_ID=/subscriptions/.../connections/mcppracground

# MCP Server Configuration
MCP_SERVER_URL=http://mssql-mcp-server-hxqif63svfkuq.westus.azurecontainer.io:8080/mcp
MCP_SERVER_LABEL=MSSQL_MCP

# MCP Server Authentication (Azure AD OAuth 2.0)
MCP_AUTH_TENANT_ID=2e9b0657-eef8-47af-8747-5e89476faaab
MCP_AUTH_CLIENT_ID=17a97781-0078-4478-8b4e-fe5dda9e2400
MCP_AUTH_SCOPE=17a97781-0078-4478-8b4e-fe5dda9e2400/.default

# Agent Reuse (Microsoft Best Practice)
AGENT_ID=asst_kHabTWJ0v5XkaQxVtxwNRhdA
```

### Key Components in `main.py`

1. **Token Acquisition** (`get_mcp_access_token`)
   - Uses `DefaultAzureCredential` for authentication
   - Caches tokens for 5 minutes
   - Automatically refreshes expired tokens

2. **Tool Discovery** (`discover_mcp_tools`)
   - Returns known MSSQL tools
   - Supports introspection for other MCP servers

3. **Tool Execution** (`execute_mcp_tool`)
   - Formats requests as JSON-RPC 2.0
   - Includes Bearer token in Authorization header
   - Handles authentication errors (401, 403)
   - Parses MCP-style responses

## 🚀 Running the Agent

```powershell
# 1. Ensure you're authenticated with Azure
az login

# 2. Run the agent
python main.py
```

The agent will:
1. Load configuration from `.env`
2. Obtain an Azure AD access token
3. Discover available MCP tools
4. Create/reuse agent with tool definitions
5. Process user queries with database access

## 📝 Example Interactions

### List Tables
**User:** "What tables are in the database?"

**Agent Process:**
1. Calls `list_tables` MCP tool
2. Server returns table list
3. Agent formats response

### Query with RLS
**User:** "Show me all documents in Security.Documents"

**Agent Process:**
1. Calls `query_sql` with SELECT query
2. Server executes query with user's identity
3. RLS filters results (only user's documents)
4. Agent presents filtered results

### Insert Data
**User:** "Add a document titled 'Q1 Report' to Security.Documents"

**Agent Process:**
1. Calls `execute_sql` with INSERT statement
2. Server automatically sets OwnerUPN to user's identity
3. RLS allows insert (matches user's identity)
4. Agent confirms success

### Blocked Insert (RLS)
**User:** "Add a document with owner 'someone@else.com'"

**Agent Process:**
1. Calls `execute_sql` with INSERT statement
2. Server detects OwnerUPN mismatch
3. RLS BLOCK predicate prevents insert
4. Agent returns error message

## 🔍 JSON-RPC 2.0 Request Format

All MCP requests follow this structure:

```json
POST http://mssql-mcp-server-hxqif63svfkuq.westus.azurecontainer.io:8080/mcp/message
Authorization: Bearer <AZURE_AD_TOKEN>
Content-Type: application/json

{
  "jsonrpc": "2.0",
  "id": 1234567890,
  "method": "tools/call",
  "params": {
    "name": "query_sql",
    "arguments": {
      "query": "SELECT * FROM Security.Documents"
    }
  }
}
```

### Success Response

```json
{
  "jsonrpc": "2.0",
  "id": 1234567890,
  "result": {
    "content": [
      {
        "type": "text",
        "text": "[{\"DocumentID\": 1, \"Title\": \"Doc1\", \"OwnerUPN\": \"user@domain.com\"}]"
      }
    ]
  }
}
```

### Error Response

```json
{
  "jsonrpc": "2.0",
  "id": 1234567890,
  "error": {
    "code": -32603,
    "message": "Authentication failed"
  }
}
```

## 🛡️ Row-Level Security (RLS)

The `Security.Documents` table enforces RLS:

```sql
-- Filter Predicate: Users only see their documents
CREATE SECURITY POLICY DocumentAccessPolicy
ADD FILTER PREDICATE dbo.fn_DocumentSecurityPredicate(OwnerUPN)
ON Security.Documents
WITH (STATE = ON);

-- Block Predicate: Users can't insert documents for others
ADD BLOCK PREDICATE dbo.fn_DocumentSecurityPredicate(OwnerUPN)
ON Security.Documents AFTER INSERT;
```

### Test Data
User: `mb6299@MngEnvMCAP095199.onmicrosoft.com`
- Has 2 documents in the database
- Can only see/modify their own documents
- Cannot insert documents with different OwnerUPN

## 🧪 Testing Scenarios

1. **List Tables**
   ```
   User: "What tables are available?"
   Expected: List of all tables including Security.Documents
   ```

2. **Query with RLS**
   ```
   User: "Show all documents"
   Expected: Only 2 documents (user's documents)
   ```

3. **Table Schema**
   ```
   User: "Describe the Security.Documents table"
   Expected: Columns: DocumentID, Title, OwnerUPN
   ```

4. **Insert Allowed**
   ```
   User: "Add a document titled 'New Report'"
   Expected: Success (uses user's identity)
   ```

5. **Insert Blocked**
   ```
   User: "Add a document with owner 'other@domain.com'"
   Expected: Error (RLS blocks different owner)
   ```

## 🔧 Troubleshooting

### Authentication Errors (401)

**Problem:** "Authentication failed - invalid or expired token"

**Solutions:**
- Run `az login` to authenticate
- Check `MCP_AUTH_CLIENT_ID` and `MCP_AUTH_SCOPE` in `.env`
- Verify your Azure account has access to the resource

### Authorization Errors (403)

**Problem:** "Authorization failed - insufficient permissions"

**Solutions:**
- Verify your user has SQL permissions
- Check Azure AD group membership
- Review SQL Database firewall rules

### Empty Results (RLS Filtering)

**Problem:** Queries return no data

**Explanation:** RLS is working correctly - you only see your own data

**Test:**
```sql
-- Check your identity
SELECT SUSER_SNAME(), USER_NAME()

-- Check your documents
SELECT * FROM Security.Documents WHERE OwnerUPN = SUSER_SNAME()
```

### Token Caching Issues

**Problem:** "Token expired" errors

**Solution:** Token cache automatically refreshes. If issues persist:
```python
# Force token refresh by clearing cache
_mcp_token_cache["token"] = None
_mcp_token_cache["expires_at"] = 0
```

## 📊 Logging and Debugging

The agent provides detailed logging:

```
[MCP Auth] Obtaining Azure AD access token...
[MCP Auth] ✅ Token obtained successfully (expires in 59 minutes)
[MCP Discovery] Using known MSSQL MCP tools
[MCP Setup] Allowed tool: query_sql
[MCP Execute] Starting execution for tool 'query_sql'
[MCP Execute] JSON-RPC Request: {...}
[MCP Execute] Response Status: 200
[MCP Execute] ✅ Success! Result: ...
```

### Verbose Logging

For debugging, the agent logs:
- Token acquisition and expiration
- Tool discovery results
- JSON-RPC request/response payloads
- HTTP status codes and headers
- Parsed results

## 🎓 Microsoft Best Practices

This implementation follows:

1. **Agent Reuse:** Agents persist by design, reuse via `AGENT_ID`
2. **DefaultAzureCredential:** Works in dev, test, and production
3. **Token Caching:** Minimize Azure AD requests
4. **Error Handling:** Graceful degradation with informative messages
5. **RLS Enforcement:** User identity flows through entire stack
6. **Logging:** Detailed tracing for debugging

## 🔗 Related Resources

- [Azure AI Foundry Documentation](https://learn.microsoft.com/azure/ai-studio/)
- [Model Context Protocol Spec](https://modelcontextprotocol.io/)
- [Azure SQL Row-Level Security](https://learn.microsoft.com/sql/relational-databases/security/row-level-security)
- [DefaultAzureCredential](https://learn.microsoft.com/dotnet/api/azure.identity.defaultazurecredential)

## 📞 Support

For issues:
1. Check logs for detailed error messages
2. Verify `.env` configuration
3. Test authentication with `az login`
4. Review MCP server health
5. Check SQL Database connectivity

---

**Status:** ✅ Fully Configured and Operational

**Last Updated:** October 1, 2025
