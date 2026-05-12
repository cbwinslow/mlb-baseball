#!/usr/bin/env bash
set -euo pipefail

README_FILE="README.md"

if [ ! -f "$README_FILE" ]; then
  echo "Missing $README_FILE"
  exit 1
fi

python <<'PY'
from pathlib import Path

path = Path("README.md")
text = path.read_text()

replacements = {
    "docs/architecture/ARCHITECTURE.md": "docs/architecture/architecture-overview.md",
    "docs/architecture/ARCHITECTURE_EVALUATION_SUMMARY.md": "docs/architecture/architecture-evaluation-summary.md",
    "docs/architecture/DOWNLOAD_ARCHITECTURE_DETAILED.md": "docs/architecture/download-architecture-detailed.md",
    "docs/architecture/IMPLEMENTATION_SUMMARY.md": "docs/architecture/implementation-summary.md",
    "docs/architecture/SOURCE_ADAPTERS.md": "docs/architecture/source-adapters.md",
    "docs/MIGRATION_MATRIX.md": "docs/migration-matrix.md",
    "docs/PHASE_COMPLETION_REPORT.md": "docs/phase-completion-report.md",
}

original = text
for old, new in replacements.items():
    text = text.replace(old, new)

docs_index_block = """
## Documentation

See the documentation index for organized project docs:

- [Documentation index](docs/README.md)
- [Architecture overview](docs/architecture/architecture-overview.md)
- [Source adapters](docs/architecture/source-adapters.md)
- [Migration matrix](docs/migration-matrix.md)
"""

if "## Documentation" not in text:
    marker = "## Architecture"
    if marker in text:
        text = text.replace(marker, docs_index_block + "\n" + marker, 1)
    else:
        text += "\n\n" + docs_index_block + "\n"

if text != original:
    path.write_text(text)
    print("README.md updated")
else:
    print("No README.md changes were needed")
PY
