#!/bin/bash
# ThreatAssessor API Restart Script
# Stops and restarts the FastAPI server

set -e  # Exit on error

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo -e "${YELLOW}🔄 Restarting ThreatAssessor API...${NC}"

# Stop API
"$SCRIPT_DIR/api_stop.sh"

echo ""
echo -e "${YELLOW}⏳ Waiting 2 seconds before restart...${NC}"
sleep 2

# Start API
"$SCRIPT_DIR/api_start.sh"

echo ""
echo -e "${GREEN}✅ API restart complete${NC}"
