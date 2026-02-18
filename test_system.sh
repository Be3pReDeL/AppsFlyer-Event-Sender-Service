#!/bin/bash
# Скрипт для полного тестирования системы

set -e

echo "=== AppsFlyer Event Sender Service - System Test ==="
echo ""

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Base URL
API_URL="http://localhost:8000"
TOKEN="test-token-local"

# Test functions
test_health() {
    echo -e "${YELLOW}[TEST] Health endpoints${NC}"
    
    # Liveness
    echo "  Testing /health/live..."
    RESPONSE=$(curl -s "$API_URL/health/live")
    if echo "$RESPONSE" | grep -q '"status":"ok"'; then
        echo -e "  ${GREEN}✓ Liveness check passed${NC}"
    else
        echo -e "  ${RED}✗ Liveness check failed${NC}"
        echo "    Response: $RESPONSE"
        exit 1
    fi
    
    # Readiness
    echo "  Testing /health/ready..."
    RESPONSE=$(curl -s "$API_URL/health/ready")
    if echo "$RESPONSE" | grep -q '"status":"ok"'; then
        echo -e "  ${GREEN}✓ Readiness check passed${NC}"
    else
        echo -e "  ${RED}✗ Readiness check failed${NC}"
        echo "    Response: $RESPONSE"
        exit 1
    fi
    
    echo ""
}

test_metrics() {
    echo -e "${YELLOW}[TEST] Prometheus metrics${NC}"
    
    echo "  Testing /metrics..."
    RESPONSE=$(curl -s "$API_URL/metrics")
    if echo "$RESPONSE" | grep -q "queue_enqueued_total"; then
        echo -e "  ${GREEN}✓ Metrics endpoint accessible${NC}"
    else
        echo -e "  ${RED}✗ Metrics endpoint failed${NC}"
        exit 1
    fi
    
    echo ""
}

test_auth() {
    echo -e "${YELLOW}[TEST] Authentication${NC}"
    
    # Missing token
    echo "  Testing missing token..."
    STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$API_URL/v1/track/registration?appsflyer_id=test-device")
    if [ "$STATUS" = "401" ]; then
        echo -e "  ${GREEN}✓ Missing token rejected (401)${NC}"
    else
        echo -e "  ${RED}✗ Expected 401, got $STATUS${NC}"
        exit 1
    fi
    
    # Invalid token
    echo "  Testing invalid token..."
    STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$API_URL/v1/track/registration?token=invalid&appsflyer_id=test-device")
    if [ "$STATUS" = "401" ]; then
        echo -e "  ${GREEN}✓ Invalid token rejected (401)${NC}"
    else
        echo -e "  ${RED}✗ Expected 401, got $STATUS${NC}"
        exit 1
    fi
    
    echo ""
}

test_registration() {
    echo -e "${YELLOW}[TEST] Registration event${NC}"
    
    # Valid registration
    echo "  Testing valid registration (GET)..."
    RESPONSE=$(curl -s -X GET "$API_URL/v1/track/registration?token=$TOKEN&appsflyer_id=device-reg-001&customer_user_id=user-001&platform=ios")
    if echo "$RESPONSE" | grep -q '"status":"accepted"'; then
        EVENT_ID=$(echo "$RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin)['event_id'])")
        echo -e "  ${GREEN}✓ Registration accepted (event_id: $EVENT_ID)${NC}"
    else
        echo -e "  ${RED}✗ Registration failed${NC}"
        echo "    Response: $RESPONSE"
        exit 1
    fi
    
    # POST with query params
    echo "  Testing registration (POST with query params)..."
    RESPONSE=$(curl -s -X POST "$API_URL/v1/track/registration?token=$TOKEN&appsflyer_id=device-reg-002&platform=android")
    if echo "$RESPONSE" | grep -q '"status":"accepted"'; then
        echo -e "  ${GREEN}✓ POST registration accepted${NC}"
    else
        echo -e "  ${RED}✗ POST registration failed${NC}"
        exit 1
    fi
    
    echo ""
}

test_purchase() {
    echo -e "${YELLOW}[TEST] Purchase event${NC}"
    
    # Valid purchase
    echo "  Testing valid purchase..."
    RESPONSE=$(curl -s -X POST "$API_URL/v1/track/purchase?token=$TOKEN&appsflyer_id=device-purchase-001&revenue=19.99&currency=USD&product_id=premium_monthly&platform=ios")
    if echo "$RESPONSE" | grep -q '"status":"accepted"'; then
        EVENT_ID=$(echo "$RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin)['event_id'])")
        echo -e "  ${GREEN}✓ Purchase accepted (event_id: $EVENT_ID)${NC}"
    else
        echo -e "  ${RED}✗ Purchase failed${NC}"
        echo "    Response: $RESPONSE"
        exit 1
    fi
    
    # Missing required fields
    echo "  Testing purchase without revenue..."
    STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$API_URL/v1/track/purchase?token=$TOKEN&appsflyer_id=device-test&currency=USD")
    if [ "$STATUS" = "400" ]; then
        echo -e "  ${GREEN}✓ Missing revenue rejected (400)${NC}"
    else
        echo -e "  ${RED}✗ Expected 400, got $STATUS${NC}"
        exit 1
    fi
    
    echo ""
}

test_deduplication() {
    echo -e "${YELLOW}[TEST] Deduplication${NC}"
    
    CUSTOM_EVENT_ID="dedup_test_$(date +%s)"
    
    # First request
    echo "  Sending first event (event_id: $CUSTOM_EVENT_ID)..."
    RESPONSE1=$(curl -s -X POST "$API_URL/v1/track/registration?token=$TOKEN&appsflyer_id=device-dedup-001&event_id=$CUSTOM_EVENT_ID")
    if echo "$RESPONSE1" | grep -q '"status":"accepted"'; then
        if echo "$RESPONSE1" | grep -q "Duplicate"; then
            echo -e "  ${RED}✗ First request marked as duplicate${NC}"
            exit 1
        fi
        echo -e "  ${GREEN}✓ First event accepted${NC}"
    else
        echo -e "  ${RED}✗ First event failed${NC}"
        exit 1
    fi
    
    # Duplicate request
    echo "  Sending duplicate event..."
    sleep 1
    RESPONSE2=$(curl -s -X POST "$API_URL/v1/track/registration?token=$TOKEN&appsflyer_id=device-dedup-001&event_id=$CUSTOM_EVENT_ID")
    if echo "$RESPONSE2" | grep -q "Duplicate"; then
        echo -e "  ${GREEN}✓ Duplicate detected${NC}"
    else
        echo -e "  ${RED}✗ Duplicate not detected${NC}"
        echo "    Response: $RESPONSE2"
        exit 1
    fi
    
    echo ""
}

test_rate_limit() {
    echo -e "${YELLOW}[TEST] Rate limiting${NC}"
    
    echo "  Sending burst of requests..."
    BLOCKED=0
    for i in {1..50}; do
        STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$API_URL/v1/track/registration?token=$TOKEN&appsflyer_id=device-rate-$i")
        if [ "$STATUS" = "429" ]; then
            BLOCKED=$((BLOCKED + 1))
        fi
    done
    
    if [ $BLOCKED -gt 0 ]; then
        echo -e "  ${GREEN}✓ Rate limiting working ($BLOCKED requests blocked)${NC}"
    else
        echo -e "  ${YELLOW}⚠ No rate limiting detected (might be disabled or limit too high)${NC}"
    fi
    
    echo ""
}

check_metrics_after_tests() {
    echo -e "${YELLOW}[TEST] Metrics after tests${NC}"
    
    echo "  Checking queue metrics..."
    METRICS=$(curl -s "$API_URL/metrics")
    
    if echo "$METRICS" | grep -q 'queue_enqueued_total{event_type="registration"}'; then
        COUNT=$(echo "$METRICS" | grep 'queue_enqueued_total{event_type="registration"}' | awk '{print $2}')
        echo -e "  ${GREEN}✓ Registration events enqueued: $COUNT${NC}"
    fi
    
    if echo "$METRICS" | grep -q 'queue_enqueued_total{event_type="purchase"}'; then
        COUNT=$(echo "$METRICS" | grep 'queue_enqueued_total{event_type="purchase"}' | awk '{print $2}')
        echo -e "  ${GREEN}✓ Purchase events enqueued: $COUNT${NC}"
    fi
    
    if echo "$METRICS" | grep -q 'dedup_check_total{result="duplicate"}'; then
        COUNT=$(echo "$METRICS" | grep 'dedup_check_total{result="duplicate"}' | awk '{print $2}')
        echo -e "  ${GREEN}✓ Duplicate events detected: $COUNT${NC}"
    fi
    
    echo ""
}

check_worker_logs() {
    echo -e "${YELLOW}[TEST] Worker processing${NC}"
    
    echo "  Waiting for worker to process events (5 seconds)..."
    sleep 5
    
    echo "  Checking worker logs..."
    docker logs appsflyer-event-sender-service-worker-1 2>&1 | tail -20
    
    echo ""
}

# Main test flow
main() {
    echo "Starting system tests..."
    echo ""
    
    # Wait for services to be ready
    echo "Waiting for API to be ready..."
    for i in {1..30}; do
        if curl -s "$API_URL/health/live" > /dev/null 2>&1; then
            echo -e "${GREEN}API is ready${NC}"
            break
        fi
        if [ $i -eq 30 ]; then
            echo -e "${RED}API failed to start${NC}"
            exit 1
        fi
        sleep 1
    done
    echo ""
    
    # Run tests
    test_health
    test_metrics
    test_auth
    test_registration
    test_purchase
    test_deduplication
    test_rate_limit
    check_metrics_after_tests
    check_worker_logs
    
    echo -e "${GREEN}=== All system tests passed ===${NC}"
}

main
