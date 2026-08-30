"""Ölçüm / keşif betikleri için proje kökünü sys.path'e ekler.

Her araç betiğinin başında::

    import araclar._kok  # noqa: F401
"""

from __future__ import annotations

import sys
from pathlib import Path

_kok = Path(__file__).resolve().parent.parent
if str(_kok) not in sys.path:
    sys.path.insert(0, str(_kok))

from belge.yollar import PROJE_KOK, proje_kokunu_yola_ekle  # noqa: E402

proje_kokunu_yola_ekle()

__all__ = ["PROJE_KOK"]
