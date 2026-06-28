#!/usr/bin/env bash
set -e

echo "[*] ORACLE Dashboard Execution Orchestrator"

# 1. Validate environment
if [ ! -f ".env" ]; then
    echo "[!] ERROR: .env file missing. Copy .env.example to .env and configure."
    exit 1
fi

export $(grep -v '^#' .env | xargs)

# 2. Extract passed arguments
COMMAND=${1:-generate}

# 3. Run dashboard CLI
echo "[*] Running command: python -m grc_dashboard.main $COMMAND"
python -m grc_dashboard.main "$COMMAND"

# Capture exit code
EXIT_CODE=$?

if [ $EXIT_CODE -eq 0 ]; then
    echo "[+] Pipeline execution completed successfully."
elif [ $EXIT_CODE -eq 1 ]; then
    echo "[-] Pipeline encountered a fatal error during stage execution."
elif [ $EXIT_CODE -eq 2 ]; then
    echo "[!] Pipeline ran, but post-flight audit lineage validations failed."
fi

exit $EXIT_CODE
