"""Proje kökü ve girdi/çıktı dizin adları (tek kaynak).

CLI (`isle.py`), web (`web_cikti/`) ve `Arsiv` aynı klasör adlarını kullanır.
Kişisel veri içeren çıktılar `.gitignore` ile versiyon kontrolüne girmez.
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJE_KOK = Path(__file__).resolve().parent.parent

# SPEC 4.2 — çıktı kovaları (çıktı kökünün altında)
ARSIV = "arsiv"
OKUNAMADI = "okunamadi"
DOGRULANMALI = "dogrulanmali"
AYRILDI = "ayrildi"
BOLUNMELI = "bolunmeli"
HATA = "hata"
ILGISIZ = "ilgisiz"

CIKTI_KLASORLERI: tuple[str, ...] = (
    ARSIV,
    OKUNAMADI,
    DOGRULANMALI,
    AYRILDI,
    BOLUNMELI,
    HATA,
    ILGISIZ,
)

# Web arayüzü varsayılan çıktı kökü — proje kökündeki arsiv/ ile karışmaz
WEB_CIKTI = "web_cikti"

# Girdi (örnek PDF'ler; kişisel veri)
ORNEKLER = "ornekler"


def proje_kokunu_yola_ekle() -> Path:
    """Betikleri proje kökünden çalıştırmadan `belge` / `isle` içe aktarımı için."""
    kok = str(PROJE_KOK)
    if kok not in sys.path:
        sys.path.insert(0, kok)
    return PROJE_KOK


def cikti_klasorlerini_hazirla(kok: Path | str) -> Path:
    """Çıktı kökü ve SPEC kovalarını oluşturur (içerik yazmaz)."""
    kok = Path(kok)
    kok.mkdir(parents=True, exist_ok=True)
    for ad in CIKTI_KLASORLERI:
        (kok / ad).mkdir(parents=True, exist_ok=True)
    (kok / AYRILDI / "asil").mkdir(parents=True, exist_ok=True)
    return kok
