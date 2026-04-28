#!/bin/bash
set -o pipefail
# run_all.sh – kör upstream + BI sekventiellt (ersätter Portföljindex.bat)

cd "$(dirname "$0")"
source /Users/mikael/Projects/claude-env/bin/activate

echo "=== Kör upstream (src.main) ==="
python -m src.main 2>&1 | tee logs/main_$(date +%Y%m%d_%H%M%S).log
if [ ${PIPESTATUS[0]} -ne 0 ]; then
    echo "Upstream misslyckades – avbryter BI-körning."
    exit 1
fi

echo "=== Kör BI (src.bi_prep) ==="
python -m src.bi_prep 2>&1 | tee logs/bi_$(date +%Y%m%d_%H%M%S).log
