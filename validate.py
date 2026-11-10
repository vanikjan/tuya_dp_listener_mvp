"""Local syntax check for the Tuya DP Listener source."""
from pathlib import Path
import py_compile

source = Path(__file__).parent / "app" / "main.py"
py_compile.compile(str(source), doraise=True)
print(f"Syntax OK: {source}")
