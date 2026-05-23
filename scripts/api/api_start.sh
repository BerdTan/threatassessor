#!/bin/bash
# ThreatAssessor API Startup Script
# Starts the FastAPI server with proper configuration

set -e  # Exit on error

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Configuration
API_HOST="${API_HOST:-0.0.0.0}"
API_PORT="${API_PORT:-8000}"
LOG_DIR="logs"
PID_FILE="$LOG_DIR/api.pid"
LOG_FILE="$LOG_DIR/api.log"

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$(dirname "$SCRIPT_DIR")")"

cd "$PROJECT_ROOT"

# Create logs directory
mkdir -p "$LOG_DIR"

# Check if already running
if [ -f "$PID_FILE" ]; then
    PID=$(cat "$PID_FILE")
    if ps -p "$PID" > /dev/null 2>&1; then
        echo -e "${YELLOW}⚠️  API server already running (PID: $PID)${NC}"
        echo -e "${YELLOW}   Use ./scripts/api_stop.sh to stop it first${NC}"
        exit 1
    else
        echo -e "${YELLOW}⚠️  Stale PID file found, removing...${NC}"
        rm -f "$PID_FILE"
    fi
fi

# Check if port is already in use
if lsof -Pi :$API_PORT -sTCP:LISTEN -t >/dev/null 2>&1; then
    echo -e "${RED}❌ Port $API_PORT is already in use${NC}"
    echo -e "${RED}   Run: lsof -i :$API_PORT to see what's using it${NC}"
    echo -e "${RED}   Or use: ./scripts/api_stop.sh to kill any stray processes${NC}"
    exit 1
fi

# Check for .env file
if [ ! -f ".env" ]; then
    echo -e "${RED}❌ .env file not found${NC}"
    echo -e "${RED}   Create .env with API_KEY and LLM provider keys${NC}"
    exit 1
fi

# Check for virtual environment
if [ ! -d ".venv" ]; then
    echo -e "${RED}❌ Virtual environment not found${NC}"
    echo -e "${RED}   Run: python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt${NC}"
    exit 1
fi

# Activate virtual environment
source .venv/bin/activate

echo -e "${GREEN}🚀 Starting ThreatAssessor API...${NC}"
echo -e "${GREEN}   Host: $API_HOST${NC}"
echo -e "${GREEN}   Port: $API_PORT${NC}"
echo -e "${GREEN}   Log:  $LOG_FILE${NC}"

# Start API server in background
nohup .venv/bin/python -m uvicorn chatbot.api.app:app \
    --host "$API_HOST" \
    --port "$API_PORT" \
    --reload \
    --log-level info \
    > "$LOG_FILE" 2>&1 &

# Save PID
echo $! > "$PID_FILE"

# Wait a moment for startup
sleep 2

# Check if process started successfully
if ps -p $(cat "$PID_FILE") > /dev/null 2>&1; then
    PID=$(cat "$PID_FILE")
    echo -e "${GREEN}✅ API server started successfully (PID: $PID)${NC}"
    echo -e "${GREEN}   Dashboard: http://localhost:$API_PORT/dashboard${NC}"
    echo -e "${GREEN}   API Docs:  http://localhost:$API_PORT/docs${NC}"
    echo -e "${GREEN}   Health:    http://localhost:$API_PORT/health${NC}"
    echo ""
    echo -e "${GREEN}   View logs: tail -f $LOG_FILE${NC}"
    echo -e "${GREEN}   Stop API:  ./scripts/api_stop.sh${NC}"
else
    echo -e "${RED}❌ Failed to start API server${NC}"
    echo -e "${RED}   Check logs: cat $LOG_FILE${NC}"
    rm -f "$PID_FILE"
    exit 1
fi
