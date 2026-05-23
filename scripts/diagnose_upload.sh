#!/bin/bash
# Diagnostic script to test upload functionality

set -e

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${YELLOW}🔍 ThreatAssessor Upload Diagnostics${NC}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Step 1: Check API is running
echo -e "\n${GREEN}1. Checking API status...${NC}"
if curl -s http://localhost:8000/health > /dev/null 2>&1; then
    echo -e "${GREEN}   ✅ API is responding${NC}"
else
    echo -e "${RED}   ❌ API is not responding${NC}"
    exit 1
fi

# Step 2: Check API key configuration
echo -e "\n${GREEN}2. Checking API key configuration...${NC}"
API_KEY=$(grep "^API_KEY=" .env 2>/dev/null | cut -d'=' -f2)
if [ -z "$API_KEY" ]; then
    echo -e "${RED}   ❌ API_KEY not found in .env${NC}"
    exit 1
else
    echo -e "${GREEN}   ✅ API_KEY found in .env${NC}"
    echo -e "${GREEN}      Length: ${#API_KEY} characters${NC}"
    echo -e "${GREEN}      Hint: ${API_KEY:0:4}...${API_KEY: -4}${NC}"
fi

# Step 3: Check config endpoint
echo -e "\n${GREEN}3. Checking /api/v1/config endpoint...${NC}"
CONFIG=$(curl -s http://localhost:8000/api/v1/config)
echo "$CONFIG" | python3 -m json.tool | sed 's/^/   /'

# Step 4: Test with sample file
echo -e "\n${GREEN}4. Testing upload with sample file...${NC}"
TEST_FILE="tests/data/architectures/00_safeentry.mmd"

if [ ! -f "$TEST_FILE" ]; then
    echo -e "${RED}   ❌ Test file not found: $TEST_FILE${NC}"
    exit 1
fi

echo -e "${GREEN}   Using: $TEST_FILE${NC}"

# Test with correct API key
echo -e "\n${GREEN}5. Testing POST /api/v1/analyze-stream with correct key...${NC}"
HTTP_CODE=$(curl -s -o /tmp/upload_test.log -w "%{http_code}" \
    -X POST http://localhost:8000/api/v1/analyze-stream \
    -H "TM-API-KEY: $API_KEY" \
    -F "architecture_file=@$TEST_FILE" \
    -F "include_validation=true")

echo -e "${GREEN}   HTTP Status: $HTTP_CODE${NC}"

if [ "$HTTP_CODE" = "200" ]; then
    echo -e "${GREEN}   ✅ Upload successful!${NC}"
    echo -e "${GREEN}   First 20 lines of response:${NC}"
    head -20 /tmp/upload_test.log | sed 's/^/   /'
elif [ "$HTTP_CODE" = "401" ]; then
    echo -e "${RED}   ❌ 401 Unauthorized - API key invalid${NC}"
    cat /tmp/upload_test.log | sed 's/^/   /'
else
    echo -e "${RED}   ❌ HTTP $HTTP_CODE${NC}"
    cat /tmp/upload_test.log | sed 's/^/   /'
fi

# Test with wrong API key
echo -e "\n${GREEN}6. Testing with WRONG API key (should fail)...${NC}"
HTTP_CODE=$(curl -s -o /tmp/upload_test_wrong.log -w "%{http_code}" \
    -X POST http://localhost:8000/api/v1/analyze-stream \
    -H "TM-API-KEY: wrong-key-12345" \
    -F "architecture_file=@$TEST_FILE")

echo -e "${GREEN}   HTTP Status: $HTTP_CODE${NC}"

if [ "$HTTP_CODE" = "401" ]; then
    echo -e "${GREEN}   ✅ Correctly rejected invalid key${NC}"
else
    echo -e "${RED}   ⚠️  Expected 401, got $HTTP_CODE${NC}"
fi

# Test without API key
echo -e "\n${GREEN}7. Testing without API key (should fail)...${NC}"
HTTP_CODE=$(curl -s -o /tmp/upload_test_nokey.log -w "%{http_code}" \
    -X POST http://localhost:8000/api/v1/analyze-stream \
    -F "architecture_file=@$TEST_FILE")

echo -e "${GREEN}   HTTP Status: $HTTP_CODE${NC}"

if [ "$HTTP_CODE" = "422" ] || [ "$HTTP_CODE" = "401" ]; then
    echo -e "${GREEN}   ✅ Correctly rejected missing key${NC}"
else
    echo -e "${RED}   ⚠️  Expected 422 or 401, got $HTTP_CODE${NC}"
fi

# Check browser console instructions
echo -e "\n${GREEN}8. Browser Console Debug Instructions:${NC}"
echo -e "${YELLOW}   Open dashboard: http://localhost:8000/dashboard${NC}"
echo -e "${YELLOW}   Press F12 (DevTools)${NC}"
echo -e "${YELLOW}   Go to Console tab${NC}"
echo -e "${YELLOW}   Upload a file and check for:${NC}"
echo -e "${YELLOW}      • '[SSE] Connecting to...' message${NC}"
echo -e "${YELLOW}      • '✅ API key saved to localStorage' message${NC}"
echo -e "${YELLOW}      • Network tab shows TM-API-KEY header${NC}"
echo ""
echo -e "${YELLOW}   Check localStorage:${NC}"
echo -e "${YELLOW}      • Go to Application tab${NC}"
echo -e "${YELLOW}      • Expand Local Storage → http://localhost:8000${NC}"
echo -e "${YELLOW}      • Look for 'tm_api_key'${NC}"
echo -e "${YELLOW}      • Value should be: ${API_KEY:0:4}...${API_KEY: -4}${NC}"

echo -e "\n${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}✅ Diagnostics complete${NC}"
echo -e "${GREEN}   If upload still fails in browser:${NC}"
echo -e "${GREEN}   1. Check browser console for errors${NC}"
echo -e "${GREEN}   2. Check Network tab for failed requests${NC}"
echo -e "${GREEN}   3. Verify localStorage has API key${NC}"
echo -e "${GREEN}   4. Try clicking ⚙️ Settings and re-entering key${NC}"
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

# Cleanup
rm -f /tmp/upload_test*.log
