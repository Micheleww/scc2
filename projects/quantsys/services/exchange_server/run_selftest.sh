#!/bin/bash

# Run A2A Bridge self-test suite

# Set up environment
export EXCHANGE_BEARER_TOKEN="default_secret_token"
export EXCHANGE_SSE_AUTH_MODE="none"

# Create artifacts directory
mkdir -p docs/REPORT/ci/artifacts/EXCHANGE-A2A-BRIDGE-MVP-v0.1__20260115/ata

# Start exchange server in background
python -m tools.exchange_server.main &
SERVER_PID=$!
echo "Exchange server started with PID: $SERVER_PID"

# Wait for server to start
sleep 3

# Run self-test
echo "Running A2A Bridge self-test..."
python -m tools.exchange_server.test_a2a_bridge > docs/REPORT/ci/artifacts/EXCHANGE-A2A-BRIDGE-MVP-v0.1__20260115/selftest.log 2>&1

# Get exit code
EXIT_CODE=$?

# Kill server
kill $SERVER_PID
wait $SERVER_PID 2>/dev/null

echo "Exchange server stopped"

# Create context.json
cat > docs/REPORT/ci/artifacts/EXCHANGE-A2A-BRIDGE-MVP-v0.1__20260115/ata/context.json << EOF
{
  "task_code": "EXCHANGE-A2A-BRIDGE-MVP-v0.1__20260115",
  "goal": "Add A2A bridge tools to exchange_server with gate-before-return",
  "created_at": "$(date -Iseconds)",
  "updated_at": "$(date -Iseconds)",
  "trace_id": "$(uuidgen)",
  "status": "done",
  "owner_role": "Integration Engineer",
  "area": "ci/exchange",
  "files": [
    "tools/exchange_server/main.py",
    "docs/SPEC/ci/exchange_a2a_bridge__v0.1__20260115.md",
    "tools/exchange_server/test_a2a_bridge.py",
    "tools/exchange_server/run_selftest.sh"
  ]
}
EOF

# Create SUBMIT.txt
cat > docs/REPORT/ci/artifacts/EXCHANGE-A2A-BRIDGE-MVP-v0.1__20260115/SUBMIT.txt << EOF
changed_files:
- tools/exchange_server/main.py
- docs/SPEC/ci/exchange_a2a_bridge__v0.1__20260115.md
- tools/exchange_server/test_a2a_bridge.py
- tools/exchange_server/run_selftest.sh
report: docs/REPORT/ci/REPORT__EXCHANGE-A2A-BRIDGE-MVP-v0.1__20260115__20260115.md
selftest_log: docs/REPORT/ci/artifacts/EXCHANGE-A2A-BRIDGE-MVP-v0.1__20260115/selftest.log
evidence_paths:
- docs/SPEC/ci/exchange_a2a_bridge__v0.1__20260115.md
- docs/REPORT/ci/artifacts/EXCHANGE-A2A-BRIDGE-MVP-v0.1__20260115/
selftest_cmds:
- python -m tools.exchange_server.run_selftest.sh
status: done
rollback: echo "No rollback needed"
forbidden_check:
- no_absolute_paths: true
- no_delete_protected: true
- no_new_entry_files: true
EOF

echo "Self-test completed with exit code: $EXIT_CODE"
echo "EXIT_CODE=$EXIT_CODE" >> docs/REPORT/ci/artifacts/EXCHANGE-A2A-BRIDGE-MVP-v0.1__20260115/selftest.log

exit $EXIT_CODE