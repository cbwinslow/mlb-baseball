"""``python -m retrosheetpy.cw TOOL [options] eventfile...`` runs one of the ported tools."""

import sys

from retrosheetpy.cw.cli import main_umbrella

if __name__ == "__main__":
    sys.exit(main_umbrella())
