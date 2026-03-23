"""Root conftest — ensures src/ and silicondb are on sys.path before any test imports."""
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(_ROOT / "lib" / "silicondb" / "python"))
sys.path.insert(0, str(_ROOT / "src"))
