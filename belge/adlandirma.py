"""İsimden dosya adı ve JSON anahtarı üretir (SPEC 4.1, 4.3).

Dosyaya hiç dokunmaz — saf dönüşümler. Arşivleme mantığı `belge/arsiv.py`'de.

Türkçe harflerin ASCII karşılığı
--------------------------------
`İ` ve `I` ayrı harflerdir ama dosya adında ikisi de `i` olur; bu kayıp
kabul edilmiştir çünkü dosya adı ASCII olmak zorunda (SPEC 4.1). Asıl isim
Türkçe hâliyle `person_data.json` içinde korunur — dosya adı bir etiket,
kayıt değil.
"""

from __future__ import annotations

import re
import unicodedata

# Türkçeye özgü harfler önce elle çevrilir: unicodedata çözümlemesi
# 'ı' ve 'İ' için beklenen sonucu vermiyor ('ı' -> '' oluyor).
TURKCE = str.maketrans(
    {
        "ç": "c", "Ç": "c",
        "ğ": "g", "Ğ": "g",
        "ı": "i", "I": "i",
        "i": "i", "İ": "i",
        "ö": "o", "Ö": "o",
        "ş": "s", "Ş": "s",
        "ü": "u", "Ü": "u",
    }
)

BOSLUK = re.compile(r"[\s_]+")
IZINSIZ = re.compile(r"[^a-z0-9_]")


def asciiye(metin: str) -> str:
    """Türkçe metni küçük harfli ASCII'ye indirger."""
    cevrilmis = metin.translate(TURKCE)
    # Kalan aksanlı harfler (yabancı isimler) için genel çözümleme.
    ayrik = unicodedata.normalize("NFKD", cevrilmis)
    return "".join(k for k in ayrik if not unicodedata.combining(k)).lower()


def dosya_adi(isim: str) -> str:
    """`Şener Çeliköz` -> `sener_celikoz`. Uzantı eklenmez.

    Boş ya da tamamen elenen isimlerde boş string döner; çağıran bunu
    `okunamadi/` kararı için kullanır.
    """
    temel = IZINSIZ.sub("", BOSLUK.sub("_", asciiye(isim).strip()))
    return temel.strip("_")


def json_anahtari(isim: str) -> str:
    """`Ayşe Nur Demir` -> `AYSE_NUR_DEMIR` (SPEC 4.3)."""
    return dosya_adi(isim).upper()


def cakismasiz(taban: str, kullanilan: set[str]) -> str:
    """Kullanılmış adlarla çakışmayan ad üretir: `ahmet_yilmaz_2` (SPEC 4.1).

    `kullanilan` DEĞİŞTİRİLMEZ; çağıran döneni kendisi ekler. Böyle olması,
    kuru çalıştırmada gerçek bir ad rezerve edilmesini engelliyor.
    """
    if taban not in kullanilan:
        return taban
    sira = 2
    while f"{taban}_{sira}" in kullanilan:
        sira += 1
    return f"{taban}_{sira}"
