import sys
from pathlib import Path

# Dev-only helpers (e.g. chadwick_reference) live next to the tests.
sys.path.insert(0, str(Path(__file__).parent))
