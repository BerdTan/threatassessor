# API Key Setup for Dashboard

**Last Updated:** 2026-05-23  
**Issue:** "API key not found" error when uploading architecture to dashboard  
**Solution:** Configure API key in browser localStorage

---

## Quick Setup

### Step 1: Find Your API Key

**Location:** `.env` file in project root

```bash
# View your API key
grep API_KEY .env

# Output:
# API_KEY=05e5abc123...xyz22d2
```

### Step 2: Configure in Dashboard

**Option A: Use Settings Button (Recommended)**

1. Open dashboard: http://localhost:8000/dashboard
2. Click ⚙️ Settings button (top-right, next to theme toggle)
3. Enter your API key from `.env` file
4. Click OK

**Option B: Enter on First Upload**

1. Open dashboard: http://localhost:8000/dashboard
2. Upload a `.mmd` file
3. Enter API key when prompted
4. Key is saved for future uploads

### Step 3: Verify

Click ⚙️ Settings button to see:
```
Current API Key: ✅ Saved
Server API Key: 05e5...22d2 (64 chars)
```

---

## How It Works

### Storage

**Browser:** API key stored in `localStorage` (client-side, per-browser)
```javascript
localStorage.setItem('tm_api_key', 'your-key-here')
```

**Server:** API key stored in `.env` file (server-side)
```
API_KEY=your-key-here
```

### Authentication Flow

```
1. User uploads architecture
2. Dashboard checks localStorage for 'tm_api_key'
3. If found, includes in request header: TM-API-KEY: <key>
4. If not found, prompts user to enter key
5. Server validates key against .env file
6. If valid → analysis proceeds
7. If invalid → 401 error, prompt to re-enter
```

---

## Troubleshooting

### Error: "API key is required"

**Symptom:** Prompt appears but no key is saved

**Solution:**
```bash
# Check server has API key
grep API_KEY .env

# If missing, add it
echo "API_KEY=$(openssl rand -hex 32)" >> .env

# Restart API
./scripts/api_restart.sh

# In dashboard, click ⚙️ Settings and enter the key
```

---

### Error: "Invalid API key"

**Symptom:** Key is entered but server rejects it with 401

**Causes:**
1. Typo in key (copy-paste issue)
2. Wrong key (not matching server .env)
3. Key has spaces/newlines

**Solution:**
```bash
# View server key (first 4 and last 4 chars)
curl -s http://localhost:8000/api/v1/config | python3 -m json.tool

# Output:
# {
#   "api_key_configured": true,
#   "hint": "05e5...22d2",
#   "key_length": 64
# }

# Compare with your entered key
# In dashboard, click ⚙️ Settings
# Verify key starts with "05e5" and ends with "22d2"
# Verify length is 64 characters

# If wrong, get correct key:
grep API_KEY .env | cut -d'=' -f2

# Copy entire key (no spaces, no newlines)
# Enter in dashboard ⚙️ Settings
```

---

### Error: "API_KEY not configured in .env file"

**Symptom:** Server returns 500 error

**Cause:** Server `.env` file missing or doesn't have `API_KEY` variable

**Solution:**
```bash
# Generate new API key
openssl rand -hex 32

# Add to .env
echo "API_KEY=<generated-key>" >> .env

# Restart API (required!)
./scripts/api_restart.sh

# In dashboard, enter the same key in ⚙️ Settings
```

---

### Key Is Saved But Still Prompts

**Symptom:** Dashboard prompts for key even though it's saved

**Causes:**
1. Browser cleared localStorage (incognito mode, cache clear)
2. Different browser/device
3. Different port (localhost:8000 vs localhost:8001)

**Solution:**
```bash
# Check localStorage in browser DevTools:
# 1. Press F12
# 2. Go to Application tab
# 3. Expand Local Storage → http://localhost:8000
# 4. Look for 'tm_api_key'

# If missing, re-enter via ⚙️ Settings
```

---

### Can't Find API Key in .env

**Symptom:** `.env` file exists but no `API_KEY` line

**Solution:**
```bash
# Check if .env exists
ls -la .env

# View contents
cat .env

# If API_KEY is missing, add it
echo "API_KEY=$(openssl rand -hex 32)" >> .env

# Restart API
./scripts/api_restart.sh
```

---

## Security Considerations

### Browser Storage Security

**What's Stored:**
- API key stored in browser's localStorage
- Stored per-origin (http://localhost:8000)
- Persists across browser restarts
- Cleared when user clears browser data

**Security Notes:**
- ⚠️ **Not encrypted** - API key visible in browser DevTools
- ⚠️ **Accessible by JavaScript** - Any script on same origin can read
- ⚠️ **XSS risk** - If site has XSS vulnerability, key can be stolen

**Why This Is Acceptable for Development:**
- Dashboard runs locally (localhost)
- No external users
- Convenient for development workflow

**NOT Acceptable for Production:**
- Don't expose dashboard to internet with this setup
- Use proper authentication (OAuth2, JWT, session cookies)
- Consider reverse proxy with auth (nginx + basic auth)

---

### API Key Best Practices

**Development (Current Setup):**
```bash
# Generate random 256-bit key
openssl rand -hex 32

# Store in .env (never commit)
echo "API_KEY=<key>" >> .env

# Add .env to .gitignore
echo ".env" >> .gitignore
```

**Production (Recommended):**
```bash
# Use secrets management
# - AWS Secrets Manager
# - HashiCorp Vault
# - Kubernetes Secrets
# - Environment variables in hosting platform

# Rotate keys regularly (quarterly)
# Use different keys per environment (dev/staging/prod)
# Monitor for unauthorized API usage
```

---

### Key Rotation

**When to Rotate:**
- Quarterly (every 3 months)
- When employee leaves team
- After security incident
- If key is accidentally exposed

**How to Rotate:**

**Step 1: Generate new key**
```bash
NEW_KEY=$(openssl rand -hex 32)
echo $NEW_KEY
```

**Step 2: Update server**
```bash
# Backup old .env
cp .env .env.backup

# Update API_KEY
sed -i "s/API_KEY=.*/API_KEY=$NEW_KEY/" .env

# Restart API
./scripts/api_restart.sh
```

**Step 3: Update dashboard**
1. Open dashboard
2. Click ⚙️ Settings
3. Enter new API key
4. Click OK

**Step 4: Verify**
```bash
# Test health endpoint
curl -s -H "TM-API-KEY: $NEW_KEY" http://localhost:8000/health

# Should return: {"status": "healthy", ...}
```

---

## Advanced: Multiple Users

**Problem:** Each user needs their own API key

**Solution: Key Management System**

**Option 1: Simple - Shared Key**
```bash
# One key for whole team
# Share via secure channel (1Password, LastPass, etc.)
# All team members use same key in dashboard
```
**Pros:** Simple  
**Cons:** Can't revoke individual access, no audit trail

**Option 2: Per-User Keys (Requires Implementation)**
```bash
# Store keys in database
# Each user has unique key
# API checks key against database

# Database schema:
# users (id, email, api_key_hash, created_at, revoked_at)

# Backend validates:
# SELECT * FROM users WHERE api_key_hash = hash(provided_key) AND revoked_at IS NULL
```
**Pros:** Individual revocation, audit trail  
**Cons:** Requires database, more complex

**Option 3: OAuth2 / JWT (Best for Production)**
```bash
# Use external identity provider (Google, Microsoft, Okta)
# Users log in with SSO
# Backend issues short-lived JWT tokens
# Dashboard includes JWT in requests

# No API keys stored in localStorage
# Tokens expire (1 hour typical)
# Automatic refresh if session valid
```
**Pros:** Secure, standard, no key management  
**Cons:** Complex to implement

---

## Testing

### Test API Key Configuration

**Step 1: Check server has key**
```bash
grep "^API_KEY=" .env
```
**Expected output:**
```
API_KEY=your-64-character-key-here
```

**Step 2: Check localStorage has key**
1. Open dashboard: http://localhost:8000/dashboard
2. Press F12 (DevTools)
3. Go to Application tab
4. Expand Local Storage → http://localhost:8000
5. Look for key: `tm_api_key`
6. Value should match your API key from .env

**Step 3: Test upload with valid key**
```bash
# In dashboard:
# 1. Click ⚙️ Settings
# 2. Verify key is saved
# 3. Upload architecture.mmd
# 4. Should proceed without error
```

**Step 4: Test upload with invalid key**
```bash
# In dashboard:
# 1. Click ⚙️ Settings
# 2. Enter wrong key: "wrong-key-12345"
# 3. Upload architecture.mmd
# 4. Should show: "❌ API Key Error - Invalid API key"
# 5. Should prompt: "Would you like to update your API key now?"
```

---

## Related Documentation

- [API Specification](../API_SPECIFICATION.md) - API authentication details
- [API Lifecycle Management](API_LIFECYCLE.md) - Starting/stopping API server
- [Cache Busting](CACHE_BUSTING.md) - Static file caching issues

---

## Summary

**Problem:** Dashboard can't upload without API key  
**Solution:** Store key in browser localStorage, include in request headers  
**Setup:** Click ⚙️ Settings button, enter key from `.env` file  
**Verification:** Settings dialog shows "✅ Saved" with server key hint  

**Key Files:**
- `.env` - Server API key configuration
- `chatbot/api/dependencies.py` - Server-side key validation
- `chatbot/api/static/js/sse-client.js` - Client-side key handling

**Commands:**
```bash
# View server key
grep API_KEY .env

# Check config endpoint
curl -s http://localhost:8000/api/v1/config | python3 -m json.tool

# Restart API (required after changing .env)
./scripts/api_restart.sh
```
