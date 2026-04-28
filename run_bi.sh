#!/bin/bash
set -o pipefail
# run_bi.sh – kör BI-pipeline (src.bi_prep)

cd "$(dirname "$0")"
source /Users/mikael/Projects/claude-env/bin/activate

python -m src.bi_prep 2>&1 | tee logs/bi_$(date +%Y%m%d_%H%M%S).log
