# API Management Scripts

Scripts for managing the ThreatAssessor FastAPI server lifecycle.

## Available Scripts

### `api_start.sh` - Start the API server

Starts the FastAPI server in the background with proper configuration.

**Features:**
- Checks for port conflicts before starting
- Validates `.env` and virtual environment exist
- Starts server with reload enabled for development
- Logs output to `logs/api.log`
- Saves PID to `logs/api.pid` for management

**Usage:**
```bash
./scripts/api_start.sh
```

**Environment Variables (optional):**
```bash
API_HOST=0.0.0.0 API_PORT=8000 ./scripts/api_start.sh
```

**Output:**
```
🚀 Starting ThreatAssessor API...
   Host: 0.0.0.0
   Port: 8000
   Log:  logs/api.log
✅ API server started successfully (PID: 12345)
   Dashboard: http://localhost:8000/dashboard
   API Docs:  http://localhost:8000/docs
   Health:    http://localhost:8000/health
```

---

### `api_stop.sh` - Stop the API server

Gracefully stops the API server or forcefully kills if needed.

**Features:**
- Attempts graceful shutdown (SIGTERM) first
- Falls back to force kill (SIGKILL) if needed
- Cleans up stray processes on the API port
- Removes PID file
- Verifies port is freed after shutdown

**Usage:**
```bash
./scripts/api_stop.sh
```

**Stopping Process:**
1. Reads PID from `logs/api.pid`
2. Sends SIGTERM (graceful shutdown)
3. Waits 5 seconds for process to exit
4. Sends SIGKILL if still running
5. Cleans up any stray processes on port 8000

**Output:**
```
🛑 Stopping ThreatAssessor API...
   Found PID file: 12345
   Sending SIGTERM to API server (PID: 12345)...
   ✅ API server stopped gracefully
✅ All API processes stopped
✅ Port 8000 is now free
```

---

### `api_restart.sh` - Restart the API server

Stops and restarts the API server in one command.

**Usage:**
```bash
./scripts/api_restart.sh
```

**What it does:**
1. Runs `api_stop.sh` (graceful shutdown)
2. Waits 2 seconds
3. Runs `api_start.sh` (fresh start)

---

### `api_status.sh` - Check API server status

Shows comprehensive status of the API server.

**Usage:**
```bash
./scripts/api_status.sh
```

**Information Displayed:**
- PID file status and process state
- Port 8000 usage
- Health endpoint response (HTTP status + JSON)
- Log file size and last 5 lines
- Summary with dashboard/docs URLs

**Example Output:**
```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  ThreatAssessor API Status
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📄 PID File: logs/api.pid
   PID: 12345
   Status: ✅ Running
   Details:
     12345 12344  1.2  0.8 147328 70556 ...

🔌 Port 8000:
   Status: ✅ In use
   PID 12345: .venv/bin/python3 -m uvicorn ...

🏥 Health Check:
   Status: ✅ Healthy (HTTP 200)
   Response:
     {
       "status": "healthy",
       "version": "1.3.0",
       "services": {
         "deterministic_engine": "operational",
         "service_layer": "operational",
         "mitre_cache": "ready"
       }
     }

📝 Log File:
   Path: logs/api.log
   Size: 2.3M (15234 lines)
   Last 5 lines:
     INFO:     Application startup complete.
     INFO:     Uvicorn running on http://0.0.0.0:8000
     ...

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
✅ API is running and healthy
   Dashboard: http://localhost:8000/dashboard
   API Docs:  http://localhost:8000/docs
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

---

## Common Scenarios

### Starting API for first time
```bash
# Install dependencies
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Create .env with API keys
cp .env.example .env
# Edit .env with your keys

# Start API
./scripts/api_start.sh
```

### API crashed or hung
```bash
# Stop all processes (force kill if needed)
./scripts/api_stop.sh

# Check nothing is running
./scripts/api_status.sh

# Start fresh
./scripts/api_start.sh
```

### Port 8000 already in use
```bash
# Find what's using the port
lsof -i :8000

# Kill all processes on port 8000
./scripts/api_stop.sh

# Or use different port
API_PORT=8001 ./scripts/api_start.sh
```

### View real-time logs
```bash
# After starting API
tail -f logs/api.log
```

### Check if API is healthy
```bash
# Quick check
./scripts/api_status.sh

# Or use curl directly
curl http://localhost:8000/health
```

---

## Troubleshooting

### Script says "API already running" but it's not
**Problem:** Stale PID file exists but process is dead

**Solution:**
```bash
./scripts/api_stop.sh  # Cleans up stale PID file
./scripts/api_start.sh
```

### Port 8000 in use but can't find process
**Problem:** Process owned by different user or zombied

**Solution:**
```bash
# Check all processes (requires sudo)
sudo lsof -i :8000

# Kill by port (last resort)
sudo kill -9 $(sudo lsof -ti :8000)

# Then start API
./scripts/api_start.sh
```

### API starts but health check fails
**Problem:** API crashed during startup or configuration error

**Solution:**
```bash
# Check logs for errors
cat logs/api.log | tail -50

# Common issues:
# 1. Missing .env file
# 2. Invalid API_KEY in .env
# 3. MITRE cache download failed
# 4. Python module import error

# Fix issue then restart
./scripts/api_restart.sh
```

### Dashboard shows "Uncaught SyntaxError" after restart
**Problem:** Browser cached stale JavaScript files, shows `Unexpected token '<'` error

**Solution:**
```bash
# Restart API (changes version parameters)
./scripts/api_restart.sh

# Then in browser:
# - Press Ctrl+F5 (Windows/Linux) or Cmd+Shift+R (Mac)
# - Or clear browser cache and reload
```

**Why this happens:**
- Browser caches old JS files
- Server restart timing - browser requests file before ready, gets HTML 404 page
- Cache-busting solution automatically changes file URLs on restart

**See:** [Cache Busting Documentation](../docs/operations/CACHE_BUSTING.md)

### Multiple API instances running
**Problem:** Started API multiple times or didn't stop properly

**Solution:**
```bash
# Kill all instances
./scripts/api_stop.sh

# Verify all stopped
ps aux | grep uvicorn

# Start single instance
./scripts/api_start.sh
```

---

## Configuration

### Environment Variables

All scripts respect these environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `API_HOST` | `0.0.0.0` | Bind address (0.0.0.0 = all interfaces) |
| `API_PORT` | `8000` | Port number |
| `LOG_DIR` | `logs` | Directory for log files |

### Log Files

| File | Description |
|------|-------------|
| `logs/api.pid` | Process ID of running API server |
| `logs/api.log` | Combined stdout/stderr from uvicorn |

**Log Rotation:** Not implemented yet. Logs grow indefinitely. Consider using `logrotate` or clearing manually:

```bash
# Backup and clear logs
mv logs/api.log logs/api.log.$(date +%Y%m%d)
touch logs/api.log
./scripts/api_restart.sh
```

---

## Production Deployment

These scripts are designed for **development** use. For production:

### Option 1: systemd Service
```bash
# Create service file
sudo nano /etc/systemd/system/threatassessor.service

[Unit]
Description=ThreatAssessor API
After=network.target

[Service]
Type=simple
User=your-user
WorkingDirectory=/path/to/threatassessor
Environment="PATH=/path/to/threatassessor/.venv/bin"
ExecStart=/path/to/threatassessor/.venv/bin/uvicorn chatbot.api.app:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target

# Enable and start
sudo systemctl enable threatassessor
sudo systemctl start threatassessor
sudo systemctl status threatassessor
```

### Option 2: Docker Container
```bash
# Build image
docker build -t threatassessor:latest .

# Run container
docker run -d \
  --name threatassessor \
  -p 8000:8000 \
  -v $(pwd)/.env:/app/.env \
  -v $(pwd)/report:/app/report \
  threatassessor:latest
```

### Option 3: Process Manager (PM2)
```bash
# Install PM2
npm install -g pm2

# Start API
pm2 start "uvicorn chatbot.api.app:app --host 0.0.0.0 --port 8000" --name threatassessor

# Configure auto-restart
pm2 startup
pm2 save
```

---

## See Also

- [API Specification](../docs/API_SPECIFICATION.md) - API endpoints and usage
- [Operations Guide](../docs/operations/OPERATIONS.md) - Troubleshooting
- [CLAUDE.md](../CLAUDE.md) - Developer quick reference
