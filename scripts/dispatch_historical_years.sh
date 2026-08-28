#!/usr/bin/env bash
set -euo pipefail

first_year="${1:-2002}"
last_year="${2:-2025}"

for year in $(seq "$first_year" "$last_year"); do
  echo "YEAR_START $year"
  run_url=$(gh workflow run unified-v2-backfill.yml --ref main \
    -f start="$year-01-01" -f end="$year-12-31" -f publish_to_site=false)
  run_id="${run_url##*/}"
  echo "YEAR_RUN $year $run_id $run_url"
  while true; do
    status=$(gh run view "$run_id" --json status --jq .status)
    if [[ "$status" == "completed" ]]; then
      break
    fi
    echo "YEAR_WAIT $year $run_id $status"
    sleep 20
  done
  conclusion=$(gh run view "$run_id" --json conclusion --jq .conclusion)
  echo "YEAR_DONE $year $run_id $conclusion"
  if [[ "$conclusion" != "success" ]]; then
    exit 1
  fi
done
