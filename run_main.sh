#!/bin/bash
set -o pipefail
# run_main.sh – kör upstream pipeline (src.main)

cd "$(dirname "$0")"
source /Users/mikael/Projects/claude-env/bin/activate

# Log-retention: radera loggar äldre än 30 dagar
find logs -name "*.log" -mtime +30 -delete

python -m src.main 2>&1 | tee logs/main_$(date +%Y%m%d_%H%M%S).log
