# Cache Busting for Static Files

**Last Updated:** 2026-05-23  
**Issue:** `Uncaught SyntaxError: Unexpected token '<'` in dashboard.js  
**Root Cause:** Browser caching stale/corrupted static files or receiving HTML error pages instead of JS

---

## Problem Description

### Symptoms

When pressing Ctrl+F5 or restarting the API server, users may see:

```
Uncaught SyntaxError: Unexpected token '<' (at dashboard.js:1598:25)
```

This happens because:

1. **Browser cache is stale** - Old version of JS file is cached
2. **Server restart timing** - Browser requests file before server is ready, gets 404 HTML page, caches it
3. **HTML served as JS** - Error page HTML is returned with `text/html` content-type but browser expects `text/javascript`

### Why This Happens

**Scenario 1: Stale Cache**
```
Browser -> Cached dashboard.js (old version with syntax error)
Server  -> New dashboard.js (fixed version) [not used]
Result  -> SyntaxError in old cached file
```

**Scenario 2: Race Condition on Restart**
```
1. User restarts server: ./scripts/api_restart.sh
2. Browser requests: GET /static/js/dashboard.js
3. Server not ready yet -> 404 error
4. FastAPI returns: HTML error page (text/html)
5. Browser caches HTML as "dashboard.js"
6. Browser executes: HTML content as JavaScript
7. Result: SyntaxError: Unexpected token '<' (HTML tag in JS context)
```

---

## Solution Implemented

### Cache-Busting with Version Parameters

**Mechanism:** Add unique query parameter to static file URLs that changes on every server restart.

**Implementation in `chatbot/api/app.py`:**

```python
# Store startup timestamp (changes on every restart)
_startup_time = str(int(datetime.utcnow().timestamp()))

@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard():
    """Serve dashboard with cache-busting version parameters."""
    html_content = index_path.read_text()
    
    # Add ?v=TIMESTAMP to all static file URLs
    import re
    html_content = re.sub(
        r'(src|href)="(/static/[^"]+)"',
        rf'\1="\2?v={_startup_time}"',
        html_content
    )
    
    return HTMLResponse(
        content=html_content,
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0"
        }
    )
```

**Result:** HTML is transformed from:
```html
<script src="/static/js/dashboard.js"></script>
```

To:
```html
<script src="/static/js/dashboard.js?v=1779503540"></script>
```

**Effect:**
- On server restart, timestamp changes (e.g., 1779503540 → 1779503600)
- Browser sees different URL → treats as new file → fetches fresh copy
- Ctrl+F5 always works because `Cache-Control: no-cache` on dashboard HTML

---

## How It Works

### Request Flow (Normal)

```
User opens dashboard:
1. Browser: GET /dashboard
2. Server:  Returns HTML with versioned URLs:
            <script src="/static/js/dashboard.js?v=1779503540"></script>
3. Browser: GET /static/js/dashboard.js?v=1779503540
4. Server:  Returns JavaScript with headers:
            Content-Type: text/javascript
            Cache-Control: public, max-age=0, must-revalidate
5. Browser: Executes JavaScript successfully
```

### Request Flow (After Restart)

```
User presses Ctrl+F5:
1. Browser: GET /dashboard (cache bypassed due to Ctrl+F5)
2. Server:  Returns HTML with NEW version:
            <script src="/static/js/dashboard.js?v=1779503600"></script>
3. Browser: Sees NEW URL, cache miss
4. Browser: GET /static/js/dashboard.js?v=1779503600
5. Server:  Returns fresh JavaScript
6. Browser: Executes new JavaScript successfully
```

### Request Flow (404 Error - Fixed)

```
If static file doesn't exist:
1. Browser: GET /static/js/missing.js?v=1779503600
2. Server:  File not found
3. Custom 404 handler:
    - Detects /static/ prefix
    - Returns PlainTextResponse (NOT HTML)
    - Content-Type: text/plain
4. Browser: Doesn't execute as JavaScript (wrong content-type)
5. Console: Shows network error (not SyntaxError)
```

---

## Cache Control Headers

### Dashboard HTML (`/dashboard`)

```http
Cache-Control: no-cache, no-store, must-revalidate
Pragma: no-cache
Expires: 0
```

**Effect:**
- Browser NEVER caches dashboard HTML
- Ctrl+F5 always fetches fresh HTML with new version parameters

### Static Files (`/static/*`)

```http
Cache-Control: public, max-age=0, must-revalidate
ETag: "<hash>"
```

**Effect:**
- Browser CAN cache but MUST revalidate (conditional GET with If-None-Match)
- If file unchanged, server returns 304 Not Modified (fast)
- If file changed or version parameter changed, server returns 200 with new content

---

## Testing

### Verify Cache-Busting Works

**Step 1: Check HTML has version parameters**
```bash
curl -s http://localhost:8000/dashboard | grep dashboard.js
# Expected output:
# <script src="/static/js/dashboard.js?v=1779503540"></script>
```

**Step 2: Verify JS file is served correctly**
```bash
curl -s -I http://localhost:8000/static/js/dashboard.js?v=1779503540
# Expected headers:
# HTTP/1.1 200 OK
# Content-Type: text/javascript; charset=utf-8
# Cache-Control: public, max-age=0, must-revalidate
```

**Step 3: Verify content is JavaScript (not HTML)**
```bash
curl -s http://localhost:8000/static/js/dashboard.js?v=1779503540 | head -5
# Expected output:
# // ThreatAssessor Dashboard - Main Controller
# class Dashboard {
```

**Step 4: Test restart changes version**
```bash
# Before restart
curl -s http://localhost:8000/dashboard | grep -o "v=[0-9]*" | head -1
# Output: v=1779503540

# Restart
./scripts/api_restart.sh

# After restart
curl -s http://localhost:8000/dashboard | grep -o "v=[0-9]*" | head -1
# Output: v=1779503600 (different!)
```

---

## User Instructions

### How to Force Fresh Load

**Method 1: Ctrl+F5 (Recommended)**
```
Windows/Linux: Ctrl + F5
Mac: Cmd + Shift + R
```

**What happens:**
1. Browser bypasses cache for dashboard HTML
2. Server returns HTML with NEW version parameters
3. Browser requests static files with NEW URLs
4. Server returns fresh files

**Method 2: Clear Browser Cache**
```
1. Open browser DevTools (F12)
2. Right-click refresh button
3. Select "Empty Cache and Hard Reload"
```

**Method 3: Open Incognito/Private Window**
```
Windows/Linux: Ctrl + Shift + N (Chrome) or Ctrl + Shift + P (Firefox)
Mac: Cmd + Shift + N (Chrome) or Cmd + Shift + P (Firefox)
```

---

## Troubleshooting

### Still Getting SyntaxError After Ctrl+F5

**Diagnosis:**
```bash
# Check what version browser is requesting
# (Open browser DevTools -> Network tab -> dashboard.js -> Headers -> Request URL)

# Compare with server's current version
curl -s http://localhost:8000/dashboard | grep -o "v=[0-9]*" | head -1

# If different, browser is using stale HTML
```

**Solution:**
1. Clear browser cache completely
2. Close all browser tabs/windows
3. Restart browser
4. Open dashboard in new window

### Static File Returns 404

**Diagnosis:**
```bash
# Check file exists
ls -lh /mnt/c/BACKUP/DEV-TEST/chatbot/api/static/js/dashboard.js

# Check server can read it
cat /mnt/c/BACKUP/DEV-TEST/chatbot/api/static/js/dashboard.js | head -5
```

**Solution:**
1. Verify file exists in static directory
2. Check file permissions (should be readable)
3. Restart API server: `./scripts/api_restart.sh`

### Version Parameter Not Changing

**Diagnosis:**
```bash
# Restart server twice and check version
./scripts/api_restart.sh
VERSION1=$(curl -s http://localhost:8000/dashboard | grep -o "v=[0-9]*" | head -1)
echo "Version 1: $VERSION1"

sleep 2

./scripts/api_restart.sh
VERSION2=$(curl -s http://localhost:8000/dashboard | grep -o "v=[0-9]*" | head -1)
echo "Version 2: $VERSION2"

# Should be different (timestamp changed)
```

**Solution:**
If versions are identical, check:
1. Server is actually restarting (not just reload)
2. `_startup_time` variable is set in `create_app()`
3. No caching proxy between browser and server

---

## Advanced: Production Considerations

### CDN with Cache Busting

If using CDN (CloudFlare, CloudFront, etc.):

**Option 1: Query Parameters (Current Approach)**
```html
<script src="/static/js/dashboard.js?v=1779503540"></script>
```
- ✅ Works with FastAPI StaticFiles
- ✅ Simple to implement
- ⚠️ Some CDNs ignore query parameters

**Option 2: Filename Hashing (Better for Production)**
```html
<script src="/static/js/dashboard.1779503540.js"></script>
```
- ✅ Works with all CDNs
- ✅ Aggressive caching possible (cache-control: max-age=31536000)
- ❌ Requires build step to rename files

**Option 3: ETag + Conditional Requests**
```http
GET /static/js/dashboard.js
If-None-Match: "abc123"

Response: 304 Not Modified (if unchanged)
Response: 200 OK + new content (if changed)
```
- ✅ Bandwidth efficient
- ✅ Already implemented in FastAPI StaticFiles
- ⚠️ Requires round-trip to server

### Cache Strategy for Production

**Development (Current):**
```
Dashboard HTML: no-cache (always fresh)
Static Files:   max-age=0, must-revalidate (validate with server)
Version param:  timestamp (changes on restart)
```

**Production (Recommended):**
```
Dashboard HTML: no-cache (always fresh)
Static Files:   max-age=3600 (1 hour) + version parameter
Version param:  git commit hash (changes on deployment)
```

**Implementation:**
```python
# Get git commit hash instead of timestamp
import subprocess
try:
    _version = subprocess.check_output(
        ['git', 'rev-parse', '--short', 'HEAD'],
        stderr=subprocess.DEVNULL
    ).decode().strip()
except:
    _version = str(int(datetime.utcnow().timestamp()))
```

---

## Summary

**Problem:** Browser caches stale static files, causing SyntaxError  
**Solution:** Cache-busting via version parameters that change on server restart  
**User Action:** Ctrl+F5 always gets fresh files  
**Verification:** `curl` shows different version after restart

**Key Files:**
- `chatbot/api/app.py` - Cache-busting implementation
- `chatbot/api/static/js/dashboard.js` - Main JavaScript file
- `chatbot/api/static/index.html` - Dashboard HTML template

**Related Docs:**
- [API Lifecycle Management](API_LIFECYCLE.md)
- [Operations Guide](OPERATIONS.md)
