# Azure AD App Registration - Expose API Configuration

## Complete Scope Configuration for MCP Server

When you're in the Azure Portal creating the scope in "Expose an API", use these exact values:

---

### Application ID URI
```
api://17a97781-0078-4478-8b4e-fe5dda9e2400
```

---

### Add a Scope - Form Fields

**Scope name:**
```
user_impersonation
```
*(Standard convention - means "act as the user")*

---

**Who can consent?**
```
☑ Admins and users
```

**Why?** Your users need to access their own data via RLS. No need to force admin consent for every user.

---

**Admin consent display name:**
```
Access MSSQL MCP Server as user
```

**Admin consent description:**
```
Allows the application to access the MSSQL MCP Server on behalf of the signed-in user. Row-Level Security (RLS) ensures users can only access data they own. This enables authenticated database queries through the Model Context Protocol while preserving user identity for audit and security purposes.
```

---

**User consent display name:**
```
Access database on your behalf
```

**User consent description:**
```
Allow this application to query the SQL database on your behalf. You will only be able to access data you own due to Row-Level Security.
```

---

**State:**
```
☑ Enabled
```

---

## After Creating the Scope

### Step 1: Add Authorized Client Applications

**Why?** So Azure CLI doesn't need manual consent every time.

**Authorized client applications to add:**

1. **Azure CLI:**
   - Client ID: `04b07795-8ddb-461a-bbee-02f9e1bf7b46`
   - ☑ Check: `api://17a97781-0078-4478-8b4e-fe5dda9e2400/user_impersonation`

2. **Azure PowerShell (optional):**
   - Client ID: `1950a258-227b-4e31-a9cf-717495945fc2`
   - ☑ Check: `api://17a97781-0078-4478-8b4e-fe5dda9e2400/user_impersonation`

3. **VS Code (optional, for development):**
   - Client ID: `aebc6443-996d-45c2-90f0-388ff96faa56`
   - ☑ Check: `api://17a97781-0078-4478-8b4e-fe5dda9e2400/user_impersonation`

---

## Visual Guide - What You'll See

### In Azure Portal - Expose an API

```
┌─────────────────────────────────────────────────────────────┐
│ Expose an API                                                │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│ Application ID URI                                           │
│ api://17a97781-0078-4478-8b4e-fe5dda9e2400          [Edit]  │
│                                                              │
│ Scopes defined by this API                                   │
│ ┌──────────────────────────────────────────────────────┐   │
│ │ Scope name          user_impersonation                │   │
│ │ Admins and users    Can consent                       │   │
│ │ Status              Enabled                           │   │
│ │ Admin consent       Access MSSQL MCP Server as user   │   │
│ └──────────────────────────────────────────────────────┘   │
│                                                              │
│ Authorized client applications                               │
│ ┌──────────────────────────────────────────────────────┐   │
│ │ 04b07795-8ddb-461a-bbee-02f9e1bf7b46                 │   │
│ │ Microsoft Azure CLI                                   │   │
│ │ ☑ api://.../user_impersonation                       │   │
│ └──────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

---

## What Users Will See (Consent Prompt)

When a user first authenticates, they'll see:

```
┌───────────────────────────────────────────────────┐
│  Microsoft                                         │
│  ──────────────────────────────────────────────   │
│                                                    │
│  Permissions requested                             │
│                                                    │
│  [Your App Name] wants to:                        │
│                                                    │
│  ✓ Access database on your behalf                 │
│    Allow this application to query the SQL        │
│    database on your behalf. You will only be      │
│    able to access data you own due to Row-Level   │
│    Security.                                       │
│                                                    │
│  ☐ Consent on behalf of your organization         │
│                                                    │
│  [ Cancel ]                    [ Accept ]          │
└───────────────────────────────────────────────────┘
```

**Note:** If you add Azure CLI as an authorized client, users won't see this prompt when using `az login` - it will be pre-authorized!

---

## Testing After Setup

### 1. Update your .env file:

```bash
MCP_AUTH_SCOPE=api://17a97781-0078-4478-8b4e-fe5dda9e2400/.default
```

### 2. Login with Azure CLI:

```powershell
az logout
az login --tenant "2e9b0657-eef8-47af-8747-5e89476faaab"
```

### 3. Get a token:

```powershell
az account get-access-token --resource "api://17a97781-0078-4478-8b4e-fe5dda9e2400"
```

Expected output:
```json
{
  "accessToken": "eyJ0eXAiOiJKV1QiLCJhbGc...",
  "expiresOn": "2025-10-01 20:30:00.000000",
  "subscription": "f2d349c3-ab28-456e-95c2-13ce65ae676a",
  "tenant": "2e9b0657-eef8-47af-8747-5e89476faaab",
  "tokenType": "Bearer"
}
```

### 4. Run your test:

```powershell
python test_mcp_setup.py
```

---

## Troubleshooting

### If users still see "admin consent required"

**Solution 1: Pre-authorize Azure CLI (recommended)**
- Add `04b07795-8ddb-461a-bbee-02f9e1bf7b46` as authorized client application
- Users won't see consent prompt

**Solution 2: Grant admin consent for all users**
1. Go to **API permissions** in your app registration
2. Click **Grant admin consent for [Your Tenant]**
3. This pre-approves the app for all users in your organization

### If you can't modify the app registration

**You need one of these roles:**
- Application Administrator
- Cloud Application Administrator
- Global Administrator
- Owner of the app registration

Ask your Azure AD admin to:
1. Make you an owner of the app registration, OR
2. Complete the "Expose an API" configuration for you

---

## Security Considerations

### Why "Admins and users" is safe for your scenario:

✅ **Row-Level Security (RLS) is enforced** - Users can't see others' data  
✅ **User identity is preserved** - Audit logs show who accessed what  
✅ **No elevated privileges** - Users only have their normal SQL permissions  
✅ **Controlled access** - Only members of your tenant can authenticate  

### When you would use "Admins only":

❌ **App can modify security settings**  
❌ **App can access all users' data**  
❌ **App performs privileged operations**  
❌ **Sensitive compliance requirements**  

**Your scenario doesn't match these** - users only access their own data!

---

## Quick Reference Card

| Setting | Value | Why |
|---------|-------|-----|
| **Application ID URI** | `api://17a97781-0078-4478-8b4e-fe5dda9e2400` | Standard format |
| **Scope name** | `user_impersonation` | Convention for delegated access |
| **Who can consent** | Admins and users | Users access own data (RLS) |
| **State** | Enabled | Make it active |
| **Authorized clients** | Azure CLI (`04b07795...`) | Skip consent prompt |

---

## Next Steps

1. ✅ Configure the scope in Azure Portal
2. ✅ Add Azure CLI as authorized client
3. ✅ Update `.env` with `api://` prefix
4. ✅ Test: `az login` and `az account get-access-token`
5. ✅ Run: `python test_mcp_setup.py`
6. ✅ Run: `python main.py`

---

**Questions?**

- **Q: What if I use "Admins only"?**  
  A: You'll need to manually approve every user - creates admin burden

- **Q: What if I don't add Azure CLI as authorized client?**  
  A: Users will see a consent prompt the first time - but it will work

- **Q: Can I change these settings later?**  
  A: Yes! You can update the scope settings anytime in Azure Portal

- **Q: What about the MCP server code - does it need changes?**  
  A: No! Your MCP server just validates the JWT token - it doesn't care about consent settings
