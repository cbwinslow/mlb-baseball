import subprocess
import sys


def test_imports_without_warehouse_or_dataframe_libs():
    code = (
        "import sys, retrosheetpy;"
        "assert retrosheetpy.__version__;"
        "banned = {'mlb_baseball', 'pandas', 'psycopg', 'psycopg2'};"
        "assert not banned & set(sys.modules), banned & set(sys.modules)"
    )
    subprocess.run([sys.executable, "-c", code], check=True)
