#!/usr/bin/env bash
set -euo pipefail

mkdir -p docs/architecture docs/reviews

rename_if_exists() {
  local src="$1"
  local dst="$2"
  if [ -e "$src" ]; then
    echo "Moving: $src -> $dst"
    mkdir -p "$(dirname "$dst")"
    mv "$src" "$dst"
  else
    echo "Skip (missing): $src"
  fi
}

rename_if_exists "docs/architecture/ARCHITECTUREEVALUATIONSUMMARY.md" "docs/architecture/architecture-evaluation-summary.md"
rename_if_exists "docs/architecture/DOWNLOADARCHITECTUREDETAILED.md" "docs/architecture/download-architecture-detailed.md"
rename_if_exists "docs/architecture/IMPLEMENTATIONSUMMARY.md" "docs/architecture/implementation-summary.md"
rename_if_exists "docs/MIGRATIONMATRIX.md" "docs/migration-matrix.md"
rename_if_exists "docs/PHASECOMPLETIONREPORT.md" "docs/phase-completion-report.md"

echo
echo "Resulting docs tree:"
find docs -maxdepth 3 -type f | sort
