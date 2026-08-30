"""Adım 1b: Örnek belgelerin toplu incelenmesi.

Tek seferlik keşif aracıdır, ana akışın parçası değildir. Cevapladığı sorular:

  - Belgeler kaç sayfa? (SPEC'te "2-5 sayfa" deniyordu)
  - Kaçında kullanılabilir metin katmanı var? (SPEC 5.2 iki yollu akış)
  - Aradığımız alanlar (DN-xxxx, 32/xxxx, TC) metin katmanında görünüyor mu?

Kişisel veri yazdırmaz; yalnızca sayım ve desen istatistiği üretir.
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

from belge.pdf_okuyucu import incele, sayfa_metinleri  # noqa: E402

# Alan desenleri. Gerçek belgelere göre düzeltildi:
#   - Sicil no 4 değil 5 hanelidir (221/288 belgede 5 hane)
#   - DN'den sonra tire yoktur: "DN47789"
#   - OCR "32/" ayıracını bazen "321" veya "32|" olarak okur
DESEN_DN = re.compile(r"DN[\s:.\-]*(\d+)")
DESEN_32 = re.compile(r"\b32\s*[/1|]\s*(\d+)")
DESEN_TC = re.compile(r"\b[1-9]\d{10}\b")


def main(klasor: str = "ornekler") -> None:
    dosyalar = sorted(Path(klasor).glob("*.pdf"))
    if not dosyalar:
        print(f"{klasor} klasoründe PDF bulunamadı.")
        return

    sayfa_sayilari: list[int] = []
    metin_katmanli = 0
    dn_bulunan = 0
    otuziki_bulunan = 0
    tc_bulunan = 0
    ikisi_de_bulunan = 0
    dn_sayfa_dagilimi: Counter[int] = Counter()

    for yol in dosyalar:
        bilgi = incele(yol)
        sayfa_sayilari.append(bilgi.sayfa_sayisi)

        if bilgi.metin_katmani_var:
            metin_katmanli += 1

        metinler = sayfa_metinleri(yol)
        tam_metin = "\n".join(metinler)

        dn = set(DESEN_DN.findall(tam_metin))
        otuziki = set(DESEN_32.findall(tam_metin))
        tc = set(DESEN_TC.findall(tam_metin))

        if dn:
            dn_bulunan += 1
            for i, sayfa_metni in enumerate(metinler, start=1):
                if DESEN_DN.search(sayfa_metni):
                    dn_sayfa_dagilimi[i] += 1
                    break
        if otuziki:
            otuziki_bulunan += 1
        if tc:
            tc_bulunan += 1
        if dn and otuziki:
            ikisi_de_bulunan += 1

    toplam = len(dosyalar)
    print(f"Belge sayısı        : {toplam}")
    print(f"Toplam sayfa        : {sum(sayfa_sayilari)}")
    print(
        "Sayfa/belge         : "
        f"en az {min(sayfa_sayilari)}, en çok {max(sayfa_sayilari)}, "
        f"ortalama {sum(sayfa_sayilari) / toplam:.1f}"
    )
    print()
    print(f"Metin katmanı olan  : {metin_katmanli}/{toplam}")
    print(f"DN-xxxx bulunan     : {dn_bulunan}/{toplam}")
    print(f"32/xxxx bulunan     : {otuziki_bulunan}/{toplam}")
    print(f"İkisi de bulunan    : {ikisi_de_bulunan}/{toplam}")
    print(f"11 haneli no bulunan: {tc_bulunan}/{toplam}")
    if dn_sayfa_dagilimi:
        print(f"DN'in ilk göründüğü sayfa: {dict(sorted(dn_sayfa_dagilimi.items()))}")


if __name__ == "__main__":
    main(*sys.argv[1:])
