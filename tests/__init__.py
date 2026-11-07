"""Riff tests.

The skill lives in skills/riff/, so that installers copy only what an agent
needs. Put it on the import path so tests can import `scripts.riff_core`.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILL_ROOT = ROOT / "skills" / "riff"
if str(SKILL_ROOT) not in sys.path:
    sys.path.insert(0, str(SKILL_ROOT))
