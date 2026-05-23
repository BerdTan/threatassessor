# API Server Lifecycle Management

**Last Updated:** 2026-05-23  
**Purpose:** Operational guide for managing the ThreatAssessor FastAPI server

---

## Overview

The ThreatAssessor API server is a long-running background process that occasionally needs to be restarted due to:
- Crashes or hangs
- Configuration changes
- Port conflicts
- Memory leaks (rare)
- Code updates

This guide provides scripts and procedures for reliable API server management.

---

## Quick Reference

| Task | Command | Description |
|------|---------|-------------|
| **Start API** | `./scripts/api_start.sh` | Start server in background |
| **Stop API** | `./scripts/api_stop.sh` | Graceful shutdown or force kill |
| **Restart API** | `./scripts/api_restart.sh` | Stop + Start |
| **Check Status** | `./scripts/api_status.sh` | Show detailed status |
| **View Logs** | `tail -f logs/api.log` | Real-time log monitoring |

---

## Detailed Documentation

See [scripts/API_MANAGEMENT.md](../../scripts/API_MANAGEMENT.md) for:
- Full script documentation
- Troubleshooting scenarios
- Configuration options
- Production deployment patterns

---

## Common Issues and Solutions

### Issue 1: API Crashed or Not Responding

**Symptoms:**
- Dashboard shows "Failed to fetch" or connection errors
- Health check fails: `curl http://localhost:8000/health` returns error
- Process shows in `ps` but doesn't respond

**Solution:**
```bash
# Force stop all API processes
./scripts/api_stop.sh

# Verify nothing is running
./scripts/api_status.sh

# Start fresh
./scripts/api_start.sh

# Monitor logs for errors
tail -f logs/api.log
```

---

### Issue 2: Port 8000 Already in Use

**Symptoms:**
- `api_start.sh` says "Port 8000 is already in use"
- Old process didn't shut down properly

**Solution:**
```bash
# Kill all processes on port 8000
./scripts/api_stop.sh

# If still doesn't work, find process manually
lsof -i :8000

# Kill specific PID
kill -9 <PID>

# Then start API
./scripts/api_start.sh
```

---

### Issue 3: Multiple API Instances Running

**Symptoms:**
- Inconsistent behavior (requests go to different instances)
- High CPU/memory usage
- Port conflicts

**Solution:**
```bash
# Stop ALL instances (cleans up everything)
./scripts/api_stop.sh

# Verify all stopped
ps aux | grep uvicorn

# Start single instance
./scripts/api_start.sh
```

---

### Issue 4: API Starts But Health Check Fails

**Symptoms:**
- Process is running (`api_status.sh` shows PID)
- Health endpoint returns 500 or doesn't respond
- Dashboard doesn't load

**Common Causes:**
1. Missing `.env` file
2. Invalid `API_KEY` in `.env`
3. MITRE cache download failed (44MB)
4. Python module import error

**Solution:**
```bash
# Check logs for errors
cat logs/api.log | tail -100

# Look for:
# - "FileNotFoundError: .env"
# - "ModuleNotFoundError"
# - "Failed to load MITRE cache"
# - Traceback with error details

# Fix issue then restart
./scripts/api_restart.sh
```

---

### Issue 5: Logs Growing Too Large

**Symptoms:**
- `logs/api.log` exceeds 100MB
- Disk space issues
- Slow log viewing

**Solution:**
```bash
# Backup and rotate logs
mv logs/api.log logs/api.log.$(date +%Y%m%d)
touch logs/api.log

# Restart API (optional, picks up new log file)
./scripts/api_restart.sh

# Or compress old logs
gzip logs/api.log.*

# Or delete old logs (careful!)
rm logs/api.log.2026*
```

---

## Monitoring Best Practices

### Health Checks

**Manual Check:**
```bash
./scripts/api_status.sh
```

**Automated Monitoring (cron):**
```bash
# Add to crontab: check every 5 minutes
*/5 * * * * cd /path/to/threatassessor && ./scripts/api_status.sh | grep -q "✅ API is running and healthy" || ./scripts/api_restart.sh
```

**External Monitoring:**
```bash
# Use uptime monitoring service (e.g., UptimeRobot, Pingdom)
# Endpoint: http://your-server:8000/health
# Check interval: 1 minute
# Alert if: Status != 200 or response time > 5 seconds
```

---

### Log Monitoring

**Check for Errors:**
```bash
# Show recent errors
grep -i "error\|exception\|traceback" logs/api.log | tail -20

# Show requests with 500 errors
grep "500" logs/api.log | tail -20

# Show slow requests (>10 seconds)
# (Requires uvicorn access logs)
```

**Real-Time Monitoring:**
```bash
# Follow logs with filtering
tail -f logs/api.log | grep --line-buffered -E "ERROR|WARNING|CRITICAL"
```

---

### Performance Monitoring

**CPU/Memory Usage:**
```bash
# Check process stats
ps aux | grep uvicorn | grep -v grep

# Or use top
top -p $(cat logs/api.pid)

# Or use htop (if installed)
htop -p $(cat logs/api.pid)
```

**Response Times:**
```bash
# Test health endpoint
time curl -s http://localhost:8000/health > /dev/null

# Test analysis endpoint (requires .mmd file)
time curl -X POST http://localhost:8000/api/v1/analyze \
  -H "TM-API-KEY: $(grep API_KEY .env | cut -d'=' -f2)" \
  -F "architecture_file=@test.mmd"
```

---

## Production Deployment

### systemd Service (Recommended)

For production servers, use systemd instead of background scripts:

**1. Create service file:**
```bash
sudo nano /etc/systemd/system/threatassessor-api.service
```

**2. Add configuration:**
```ini
[Unit]
Description=ThreatAssessor API Server
After=network.target

[Service]
Type=simple
User=threatassessor
Group=threatassessor
WorkingDirectory=/opt/threatassessor
Environment="PATH=/opt/threatassessor/.venv/bin:/usr/local/bin:/usr/bin:/bin"
EnvironmentFile=/opt/threatassessor/.env
ExecStart=/opt/threatassessor/.venv/bin/python3 -m uvicorn chatbot.api.app:app --host 0.0.0.0 --port 8000 --workers 4
Restart=always
RestartSec=5
StandardOutput=append:/var/log/threatassessor/api.log
StandardError=append:/var/log/threatassessor/api.log

[Install]
WantedBy=multi-user.target
```

**3. Enable and start:**
```bash
sudo systemctl daemon-reload
sudo systemctl enable threatassessor-api
sudo systemctl start threatassessor-api
sudo systemctl status threatassessor-api
```

**4. Manage service:**
```bash
# Start
sudo systemctl start threatassessor-api

# Stop
sudo systemctl stop threatassessor-api

# Restart
sudo systemctl restart threatassessor-api

# View logs
sudo journalctl -u threatassessor-api -f
```

---

### Docker Deployment

For containerized deployment:

**1. Build image:**
```bash
docker build -t threatassessor:latest .
```

**2. Run container:**
```bash
docker run -d \
  --name threatassessor-api \
  --restart unless-stopped \
  -p 8000:8000 \
  -v $(pwd)/.env:/app/.env:ro \
  -v $(pwd)/report:/app/report \
  -v $(pwd)/logs:/app/logs \
  threatassessor:latest
```

**3. Manage container:**
```bash
# Start
docker start threatassessor-api

# Stop
docker stop threatassessor-api

# Restart
docker restart threatassessor-api

# View logs
docker logs -f threatassessor-api

# Check health
docker exec threatassessor-api curl -s http://localhost:8000/health
```

---

## Security Considerations

### API Key Management

**Generate Secure Key:**
```bash
# Generate 256-bit key (recommended)
openssl rand -hex 32

# Add to .env
echo "API_KEY=<generated-key>" >> .env
```

**Rotate Keys:**
```bash
# 1. Generate new key
NEW_KEY=$(openssl rand -hex 32)

# 2. Update .env
sed -i.bak "s/API_KEY=.*/API_KEY=$NEW_KEY/" .env

# 3. Restart API
./scripts/api_restart.sh

# 4. Update all clients with new key
```

### Network Security

**Bind to Localhost (Development):**
```bash
# Only accept local connections
API_HOST=127.0.0.1 ./scripts/api_start.sh
```

**Use Reverse Proxy (Production):**
```nginx
# nginx configuration
server {
    listen 80;
    server_name threatassessor.example.com;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

---

## Troubleshooting Checklist

When API has issues, run through this checklist:

- [ ] **Check process is running:** `ps aux | grep uvicorn`
- [ ] **Check port is listening:** `lsof -i :8000`
- [ ] **Check health endpoint:** `curl http://localhost:8000/health`
- [ ] **Check logs for errors:** `tail -100 logs/api.log | grep -i error`
- [ ] **Check disk space:** `df -h`
- [ ] **Check memory usage:** `free -h`
- [ ] **Check .env file exists:** `ls -la .env`
- [ ] **Check virtual environment:** `ls -la .venv/bin/python3`
- [ ] **Check MITRE cache loaded:** `ls -lh chatbot/data/enterprise-attack.json`
- [ ] **Try restart:** `./scripts/api_restart.sh`
- [ ] **If all else fails:** Reboot server

---

## Related Documentation

- [API Management Scripts](../../scripts/API_MANAGEMENT.md) - Detailed script documentation
- [API Specification](../API_SPECIFICATION.md) - API endpoints and usage
- [Operations Guide](OPERATIONS.md) - General troubleshooting
- [CLAUDE.md](../../CLAUDE.md) - Developer quick reference

---

**Need Help?**
- Check logs: `tail -f logs/api.log`
- Run status: `./scripts/api_status.sh`
- GitHub Issues: [Report a bug](https://github.com/yourusername/threatassessor/issues)
