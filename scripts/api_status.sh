#!/bin/bash
# ThreatAssessor API Status Script
# Shows current status of the API server

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
API_PORT="${API_PORT:-8000}"
LOG_DIR="logs"
PID_FILE="$LOG_DIR/api.pid"
LOG_FILE="$LOG_DIR/api.log"

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_ROOT"

echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BLUE}  ThreatAssessor API Status${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

# Check PID file
if [ -f "$PID_FILE" ]; then
    PID=$(cat "$PID_FILE")
    echo -e "${GREEN}📄 PID File:${NC} $PID_FILE"
    echo -e "${GREEN}   PID:${NC} $PID"

    if ps -p "$PID" > /dev/null 2>&1; then
        echo -e "${GREEN}   Status:${NC} ✅ Running"

        # Show process details
        PROCESS_INFO=$(ps -p "$PID" -o pid,ppid,%cpu,%mem,etime,cmd --no-headers)
        echo -e "${GREEN}   Details:${NC}"
        echo "     $PROCESS_INFO"
    else
        echo -e "${RED}   Status:${NC} ❌ Not running (stale PID file)"
    fi
else
    echo -e "${YELLOW}📄 PID File:${NC} Not found"
fi

echo ""

# Check port
echo -e "${GREEN}🔌 Port ${API_PORT}:${NC}"
PIDS=$(lsof -ti :$API_PORT 2>/dev/null || true)

if [ -n "$PIDS" ]; then
    echo -e "${GREEN}   Status:${NC} ✅ In use"
    for pid in $PIDS; do
        PROCESS_NAME=$(ps -p "$pid" -o cmd= 2>/dev/null || echo "unknown")
        echo -e "${GREEN}   PID $pid:${NC} $PROCESS_NAME"
    done
else
    echo -e "${RED}   Status:${NC} ❌ Not in use"
fi

echo ""

# Check health endpoint
echo -e "${GREEN}🏥 Health Check:${NC}"
if command -v curl >/dev/null 2>&1; then
    HEALTH_RESPONSE=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:$API_PORT/health 2>/dev/null || echo "000")

    if [ "$HEALTH_RESPONSE" = "200" ]; then
        echo -e "${GREEN}   Status:${NC} ✅ Healthy (HTTP 200)"

        # Get full health response
        HEALTH_JSON=$(curl -s http://localhost:$API_PORT/health 2>/dev/null || echo "{}")
        if [ -n "$HEALTH_JSON" ] && [ "$HEALTH_JSON" != "{}" ]; then
            echo -e "${GREEN}   Response:${NC}"
            echo "$HEALTH_JSON" | python3 -m json.tool 2>/dev/null | sed 's/^/     /'
        fi
    elif [ "$HEALTH_RESPONSE" = "000" ]; then
        echo -e "${RED}   Status:${NC} ❌ Not reachable"
    else
        echo -e "${YELLOW}   Status:${NC} ⚠️  HTTP $HEALTH_RESPONSE"
    fi
else
    echo -e "${YELLOW}   Status:${NC} ⚠️  curl not installed, cannot check"
fi

echo ""

# Check log file
echo -e "${GREEN}📝 Log File:${NC}"
if [ -f "$LOG_FILE" ]; then
    LOG_SIZE=$(du -h "$LOG_FILE" | cut -f1)
    LOG_LINES=$(wc -l < "$LOG_FILE")
    echo -e "${GREEN}   Path:${NC} $LOG_FILE"
    echo -e "${GREEN}   Size:${NC} $LOG_SIZE ($LOG_LINES lines)"

    echo -e "${GREEN}   Last 5 lines:${NC}"
    tail -5 "$LOG_FILE" 2>/dev/null | sed 's/^/     /' || echo "     (unable to read log)"
else
    echo -e "${YELLOW}   Path:${NC} $LOG_FILE (not found)"
fi

echo ""
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

# Summary
if [ -f "$PID_FILE" ] && ps -p "$(cat "$PID_FILE")" > /dev/null 2>&1 && [ "$HEALTH_RESPONSE" = "200" ]; then
    echo -e "${GREEN}✅ API is running and healthy${NC}"
    echo -e "${GREEN}   Dashboard: http://localhost:$API_PORT/dashboard${NC}"
    echo -e "${GREEN}   API Docs:  http://localhost:$API_PORT/docs${NC}"
else
    echo -e "${RED}❌ API is not running or unhealthy${NC}"
    echo -e "${YELLOW}   Start with: ./scripts/api_start.sh${NC}"
fi

echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
