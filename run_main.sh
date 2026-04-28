#!/bin/bash
set -o pipefail
# run_main.sh – kör upstream pipeline (src.main)

cd "$(dirname "$0")"
source /Users/mikael/Projects/claude-env/bin/activate

python -m src.main 2>&1 | tee logs/main_$(date +%Y%m%d_%H%M%S).log
