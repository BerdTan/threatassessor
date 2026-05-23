#!/bin/bash
# ThreatAssessor API Shutdown Script
# Gracefully stops the FastAPI server or forcefully kills if needed

set -e  # Exit on error

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Configuration
API_PORT="${API_PORT:-8000}"
LOG_DIR="logs"
PID_FILE="$LOG_DIR/api.pid"

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$(dirname "$SCRIPT_DIR")")"

cd "$PROJECT_ROOT"

echo -e "${YELLOW}🛑 Stopping ThreatAssessor API...${NC}"

# Function to kill process gracefully
kill_graceful() {
    local pid=$1
    local name=$2

    if ps -p "$pid" > /dev/null 2>&1; then
        echo -e "${YELLOW}   Sending SIGTERM to $name (PID: $pid)...${NC}"
        kill -TERM "$pid" 2>/dev/null || true

        # Wait up to 5 seconds for graceful shutdown
        for i in {1..5}; do
            if ! ps -p "$pid" > /dev/null 2>&1; then
                echo -e "${GREEN}   ✅ $name stopped gracefully${NC}"
                return 0
            fi
            sleep 1
        done

        # Force kill if still running
        if ps -p "$pid" > /dev/null 2>&1; then
            echo -e "${RED}   ⚠️  Graceful shutdown failed, sending SIGKILL...${NC}"
            kill -KILL "$pid" 2>/dev/null || true
            sleep 1

            if ! ps -p "$pid" > /dev/null 2>&1; then
                echo -e "${GREEN}   ✅ $name force-killed${NC}"
                return 0
            else
                echo -e "${RED}   ❌ Failed to kill $name (PID: $pid)${NC}"
                return 1
            fi
        fi
    else
        echo -e "${YELLOW}   Process $pid already stopped${NC}"
        return 0
    fi
}

# Stop process from PID file
if [ -f "$PID_FILE" ]; then
    PID=$(cat "$PID_FILE")
    echo -e "${YELLOW}   Found PID file: $PID${NC}"
    kill_graceful "$PID" "API server"
    rm -f "$PID_FILE"
else
    echo -e "${YELLOW}   No PID file found at $PID_FILE${NC}"
fi

# Kill any remaining uvicorn processes on this port
echo -e "${YELLOW}   Checking for stray processes on port $API_PORT...${NC}"
PIDS=$(lsof -ti :$API_PORT 2>/dev/null || true)

if [ -n "$PIDS" ]; then
    echo -e "${YELLOW}   Found processes using port $API_PORT:${NC}"
    for pid in $PIDS; do
        PROCESS_NAME=$(ps -p "$pid" -o comm= 2>/dev/null || echo "unknown")
        kill_graceful "$pid" "$PROCESS_NAME"
    done
else
    echo -e "${GREEN}   No processes found on port $API_PORT${NC}"
fi

# Kill any remaining uvicorn/chatbot processes (last resort)
echo -e "${YELLOW}   Checking for any remaining API processes...${NC}"
PIDS=$(pgrep -f "uvicorn.*chatbot.api.app" || true)

if [ -n "$PIDS" ]; then
    echo -e "${YELLOW}   Found stray API processes:${NC}"
    for pid in $PIDS; do
        kill_graceful "$pid" "uvicorn"
    done
else
    echo -e "${GREEN}   No stray API processes found${NC}"
fi

echo -e "${GREEN}✅ All API processes stopped${NC}"

# Check final state
if lsof -Pi :$API_PORT -sTCP:LISTEN -t >/dev/null 2>&1; then
    echo -e "${RED}⚠️  Warning: Port $API_PORT still in use${NC}"
    echo -e "${RED}   Run: lsof -i :$API_PORT${NC}"
    exit 1
else
    echo -e "${GREEN}✅ Port $API_PORT is now free${NC}"
fi
