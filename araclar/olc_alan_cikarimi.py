"""Adım 2 ölçümü: OCR katmanı tek başına ne kadarını çözüyor?

Modele hiç gitmeden ulaşılan kapsamayı raporlar. VLM'e ne kadar iş kaldığını
somut sayıyla verir; her iyileştirmeden sonra tekrar çalıştırılabilir.

    .venv/bin/python araclar/olc_alan_cikarimi.py

Kişisel veri yazdırmaz; yalnızca sayım üretir.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import araclar._kok  # noqa: F401

import re
import sys
from collections import Counter
from pathlib import Path

from belge.alan_cikarici import cikar  # noqa: E402

# Bu belgelerde isimler BÜYÜK harfle basılıdır. Sonuçta küçük harf varsa
# OCR o karakteri yanlış okumuş demektir.
SADECE_BUYUK = re.compile(r"[A-ZÇĞİÖŞÜ ]+")
# "i" ve "l" karışıklığı OCR'ın sistematik ve tek tip hatasıdır
# (İ→i, I→l). Diğer bozulmalardan ayrı sayılır.
HAFIF_BOZULMA = re.compile(r"[A-ZÇĞİÖŞÜil ]+")


def main(klasor: str = "ornekler") -> None:
    dosyalar = sorted(Path(klasor).rglob("*.pdf"))
    if not dosyalar:
        print(f"{klasor} klasöründe PDF bulunamadı.")
        return

    bulunan = Counter()
    isim_kalitesi = Counter()
    uyarilar = Counter()

    for yol in dosyalar:
        sonuc = cikar(yol)

        if sonuc.sicil_no:
            bulunan["sicil_no"] += 1
        if sonuc.tc_no:
            bulunan["tc_no"] += 1
        if sonuc.isim_bosluksuz:
            bulunan["isim"] += 1
        if sonuc.sicil_no and sonuc.tc_no and sonuc.isim_bosluksuz:
            bulunan["ücü de"] += 1

        for uyari in sonuc.uyarilar:
            uyarilar[uyari] += 1

        ad = sonuc.isim_bosluksuz.strip()
        if not ad:
            isim_kalitesi["bulunamadı"] += 1
        elif SADECE_BUYUK.fullmatch(ad):
            isim_kalitesi["temiz"] += 1
        elif HAFIF_BOZULMA.fullmatch(ad):
            isim_kalitesi["hafif (i/l karışıklığı)"] += 1
        else:
            isim_kalitesi["ağır bozulma"] += 1

    toplam = len(dosyalar)
    print(f"TOPLAM BELGE: {toplam}\n")

    print("OCR katmanından bulunan alanlar")
    for anahtar in ("sicil_no", "tc_no", "isim", "ücü de"):
        n = bulunan[anahtar]
        print(f"  {anahtar:12} {n:4}/{toplam}  (%{100 * n / toplam:.1f})")

    print("\nİsim kalitesi")
    for anahtar in ("temiz", "hafif (i/l karışıklığı)", "ağır bozulma", "bulunamadı"):
        n = isim_kalitesi[anahtar]
        print(f"  {anahtar:24} {n:4}  (%{100 * n / toplam:.1f})")

    ocr_yeterli = isim_kalitesi["temiz"] + isim_kalitesi["hafif (i/l karışıklığı)"]
    print(
        f"\n  → OCR tek başına yeterli : {ocr_yeterli}/{toplam} (%{100 * ocr_yeterli / toplam:.1f})"
        f"\n  → VLM gerekli            : {toplam - ocr_yeterli}/{toplam}"
        f" (%{100 * (toplam - ocr_yeterli) / toplam:.1f})"
    )

    print("\nUyarılar")
    for uyari, n in uyarilar.most_common():
        print(f"  {uyari:46} {n}")


if __name__ == "__main__":
    main(*sys.argv[1:])
