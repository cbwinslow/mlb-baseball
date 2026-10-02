"""``python -m retrosheetpy.cw TOOL [options] eventfile...`` runs one of the ported tools."""

import sys

from retrosheetpy.cw.cli import TOOLS, run

if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] not in TOOLS:
        sys.exit(f"usage: python -m retrosheetpy.cw {{{','.join(TOOLS)}}} [options] eventfile...")
    tool = sys.argv.pop(1)
    sys.exit(run(tool))
