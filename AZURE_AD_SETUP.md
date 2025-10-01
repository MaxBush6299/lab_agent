# Azure AD App Registration Setup for MCP Server

## Current Issue

```
AADSTS650057: Invalid resource. The client has requested access to a resource 
which is not listed in the requested permissions in the client's application registration.
```

This means your MCP server's Azure AD app needs to be configured to allow user authentication.

## Solution: Configure the MCP Server App Registration

### Step 1: Expose an API

1. **Go to Azure Portal** → Azure Active Directory → App Registrations
2. **Find your app**: `17a97781-0078-4478-8b4e-fe5dda9e2400`
3. **Click "Expose an API"** in the left menu

4. **Set Application ID URI**:
   - Click "Set" next to Application ID URI
   - Use: `api://17a97781-0078-4478-8b4e-fe5dda9e2400`
   - Click "Save"

5. **Add a scope**:
   - Click "+ Add a scope"
   - **Scope name**: `user_impersonation` or `access_as_user`
   - **Who can consent**: `Admins and users`
   - **Admin consent display name**: `Access MCP Server as user`
   - **Admin consent description**: `Allows the app to access the MCP Server on behalf of the signed-in user`
   - **User consent display name**: `Access MCP Server`
   - **User consent description**: `Allow the app to access the MCP Server on your behalf`
   - **State**: `Enabled`
   - Click "Add scope"

### Step 2: Add Authorized Client Applications (Optional but Recommended)

This allows the Azure CLI to get tokens without extra consent prompts:

1. Still in **"Expose an API"** section
2. Scroll to **"Authorized client applications"**
3. Click **"+ Add a client application"**
4. **Client ID**: `04b07795-8ddb-461a-bbee-02f9e1bf7b46` (Azure CLI)
5. **Check the scope** you just created
6. Click "Add application"

You can also add other Microsoft clients:
- **04b07795-8ddb-461a-bbee-02f9e1bf7b46**: Azure CLI
- **1950a258-227b-4e31-a9cf-717495945fc2**: Azure PowerShell

### Step 3: Update Your Code to Use the New Scope

After setting up the API, update your `.env` file:

**Option A: Use the full scope with the api:// prefix**
```bash
MCP_AUTH_SCOPE=api://17a97781-0078-4478-8b4e-fe5dda9e2400/user_impersonation
```

**Option B: Keep using .default (recommended for simplicity)**
```bash
MCP_AUTH_SCOPE=api://17a97781-0078-4478-8b4e-fe5dda9e2400/.default
```

### Step 4: Authenticate Again

```powershell
# Logout and login
az logout
az login --tenant "2e9b0657-eef8-47af-8747-5e89476faaab"

# Test getting a token
az account get-access-token --resource "api://17a97781-0078-4478-8b4e-fe5dda9e2400"
```

### Step 5: Grant Admin Consent (If Required)

If your organization requires admin consent:

1. In the app registration, go to **"API permissions"**
2. Click **"+ Add a permission"**
3. Click **"My APIs"** tab
4. Select your app: `17a97781-0078-4478-8b4e-fe5dda9e2400`
5. Select **"Delegated permissions"**
6. Check the scope you created (`user_impersonation`)
7. Click **"Add permissions"**
8. Click **"✓ Grant admin consent for [your tenant]"**

---

## Alternative: Use a Different Authentication Method

If you can't modify the app registration, try these alternatives:

### Option 1: Use Interactive Browser Authentication

Update `main.py` to use `InteractiveBrowserCredential`:

```python
from azure.identity import InteractiveBrowserCredential

def get_mcp_access_token() -> str:
    # Check cache first...
    
    try:
        # Use interactive browser login with specific tenant
        credential = InteractiveBrowserCredential(
            tenant_id=MCP_AUTH_TENANT_ID,
            client_id=MCP_AUTH_CLIENT_ID  # Your app's client ID
        )
        
        token_result = credential.get_token(MCP_AUTH_SCOPE)
        # Cache and return...
```

### Option 2: Use Client Credentials (Service Principal)

If this is a service-to-service scenario:

```python
from azure.identity import ClientSecretCredential

credential = ClientSecretCredential(
    tenant_id=MCP_AUTH_TENANT_ID,
    client_id=os.environ["AZURE_CLIENT_ID"],
    client_secret=os.environ["AZURE_CLIENT_SECRET"]
)
```

Add to `.env`:
```bash
AZURE_CLIENT_ID=<your-service-principal-client-id>
AZURE_CLIENT_SECRET=<your-service-principal-secret>
```

---

## Testing After Configuration

1. **Test token acquisition**:
```powershell
az account get-access-token --resource "api://17a97781-0078-4478-8b4e-fe5dda9e2400"
```

2. **Run the test script**:
```powershell
python test_mcp_setup.py
```

3. **Verify the token works**:
```powershell
# Get a token
$token = (az account get-access-token --resource "api://17a97781-0078-4478-8b4e-fe5dda9e2400" --query accessToken -o tsv)

# Test the MCP server
curl -X POST "http://mssql-mcp-server-hxqif63svfkuq.westus.azurecontainer.io:8080/mcp/message" `
  -H "Content-Type: application/json" `
  -H "Authorization: Bearer $token" `
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"list_tables","arguments":{}}}'
```

---

## Quick Commands Reference

### Check Current Azure Login
```powershell
az account show
```

### Login to Specific Tenant
```powershell
az login --tenant "2e9b0657-eef8-47af-8747-5e89476faaab"
```

### Get Token for MCP Resource
```powershell
# After app registration is configured
az account get-access-token --resource "api://17a97781-0078-4478-8b4e-fe5dda9e2400"
```

### Decode JWT Token (to verify claims)
```powershell
# Install jwt-cli: choco install jwt-cli
$token = (az account get-access-token --resource "api://..." --query accessToken -o tsv)
jwt decode $token
```

---

## Summary Checklist

- [ ] Go to Azure Portal → App Registrations → Your MCP App
- [ ] Expose an API with URI: `api://17a97781-0078-4478-8b4e-fe5dda9e2400`
- [ ] Add scope: `user_impersonation` or `access_as_user`
- [ ] Add authorized client: `04b07795-8ddb-461a-bbee-02f9e1bf7b46` (Azure CLI)
- [ ] Update `.env` scope to: `api://17a97781-0078-4478-8b4e-fe5dda9e2400/.default`
- [ ] Run: `az logout; az login --tenant "2e9b0657-eef8-47af-8747-5e89476faaab"`
- [ ] Test: `az account get-access-token --resource "api://17a97781-0078-4478-8b4e-fe5dda9e2400"`
- [ ] Run: `python test_mcp_setup.py`
- [ ] Run: `python main.py`

---

**Need Help?**

If you're still stuck:
1. Check if you have permission to modify app registrations in your tenant
2. Ask your Azure AD administrator to complete the "Expose an API" steps
3. Consider using `InteractiveBrowserCredential` as an alternative
4. Verify the MCP server's app registration exists and you have access to it
