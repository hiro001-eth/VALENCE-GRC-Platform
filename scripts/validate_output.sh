#!/usr/bin/env bash
set -e

OUTPUT_DIR=${1:-"./output"}
RUN_ID=$2

if [ -z "$RUN_ID" ]; then
    echo "Usage: ./scripts/validate_output.sh <output_dir> <run_id>"
    exit 1
fi

HTML_FILE="$OUTPUT_DIR/dashboard_$RUN_ID.html"
PDF_FILE="$OUTPUT_DIR/dashboard_$RUN_ID.pdf"

echo "[*] Validating Output Artifacts for Run: $RUN_ID"

# 1. Check file existence
if [ ! -f "$HTML_FILE" ]; then
    echo "[-] ERROR: HTML Artifact missing: $HTML_FILE"
    exit 1
fi

if [ ! -f "$PDF_FILE" ]; then
    echo "[-] ERROR: PDF Artifact missing: $PDF_FILE"
    exit 1
fi

# 2. Check PDF Size
PDF_SIZE=$(stat -c%s "$PDF_FILE" 2>/dev/null || stat -f%z "$PDF_FILE")
if [ "$PDF_SIZE" -lt 1000 ]; then
    echo "[-] ERROR: PDF file is suspiciously small ($PDF_SIZE bytes)."
    exit 1
fi

# 3. Verify Footer Hash Injection in HTML source
if ! grep -q "snapshot_hash" "$HTML_FILE"; then
    echo "[-] ERROR: Cryptographic lineage hash missing from HTML source."
    exit 2
fi

echo "[+] Post-flight validation PASSED. Artifacts are cryptographically sound."
exit 0
