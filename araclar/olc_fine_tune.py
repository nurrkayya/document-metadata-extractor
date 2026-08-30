"""Faz 4 fine-tune sonucunu altın setle ölçer: taban model vs adaptörlü.

    .venv/bin/python araclar/olc_fine_tune.py <model_adi> [adapter_yolu]

Aynı 40 belgelik altın setle (`olc_elyazisi.py` ile aynı veri), tek sayfa
okuma isabetini raporlar. Adapter_yolu verilmezse yalnız taban model ölçülür
— bu, fine-tune'un fark yaratıp yaratmadığını ayırt etmek için karşılaştırma
noktasıdır (aynı taban modelin adaptörlü/adaptörsüz hali).
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import araclar._kok  # noqa: F401

import csv
import json
from collections import Counter

sys.path.insert(0, str(Path(__file__).resolve().parent))
from olc_elyazisi import HEDEF, KAYNAK  # noqa: E402


def main(model_adi: str, adapter_yolu: str | None = None) -> None:
    from belge.alan_cikarici import ETIKET_AD, cikar, etiket_kutusu, satir_kutusu
    from belge.isim_okuyucu import IsimOkuyucu, normalize
    import pymupdf

    altin = [s for s in csv.DictReader((HEDEF / "altin_set.csv").open(encoding="utf-8"))
             if s["DOGRU_ISIM"].strip()]
    tah = json.loads((HEDEF / "_tahminler.json").read_text(encoding="utf-8"))

    etiket = f"{model_adi}" + (f" + adaptör({adapter_yolu})" if adapter_yolu else " (taban, adaptörsüz)")
    print(f"{len(altin)} belge, model yükleniyor: {etiket}...")
    okuyucu = IsimOkuyucu(model_adi, adapter_yolu)

    sayim = {"el": Counter(), "daktilo": Counter(), "matbu": Counter(), "toplam": Counter()}
    for satir in altin:
        dogru = normalize(satir["DOGRU_ISIM"])
        tur = satir["TUR"] or "?"
        yol = KAYNAK / tah[satir["sira"]]["kaynak_dosya"]

        okunan = ""
        with pymupdf.open(yol) as belge:
            for sayfa in belge:
                kutu = etiket_kutusu(sayfa, ETIKET_AD)
                if kutu is None:
                    continue
                kirpma = pymupdf.Rect(*satir_kutusu(sayfa, kutu)) & sayfa.rect
                png = sayfa.get_pixmap(dpi=300, clip=kirpma).tobytes("png")
                okunan = normalize(okuyucu.oku(png).isim)
                break

        k = "bos" if not okunan else ("dogru" if okunan == dogru else "yanlis")
        sayim[tur if tur in sayim else "toplam"][k] += 1
        sayim["toplam"][k] += 1

    print(f"\nSonuç — {etiket}")
    print(f"{'tür':<10}{'doğru':>8}{'yanlış':>8}{'boş':>6}{'isabet':>10}")
    for tur in ("el", "daktilo", "matbu", "toplam"):
        c = sayim[tur]
        uretilen = c["dogru"] + c["yanlis"]
        isabet = f"%{100*c['dogru']/uretilen:.0f}" if uretilen else "-"
        print(f"{tur:<10}{c['dogru']:>8}{c['yanlis']:>8}{c['bos']:>6}{isabet:>10}")


if __name__ == "__main__":
    main(*sys.argv[1:])
