"""Görüntü ön işlemenin el yazısı okumaya etkisini ölçer (SPEC 5.4).

    .venv/bin/python -u araclar/olc_onisleme.py

SPEC 5.4 "ön işleme yok, ham görüntü" diyor — ama o karar MATBU külliyat için
alınmıştı. İkinci külliyat soluk kurşun kalemle, sararmış kağıda yazılmış;
kontrast ve eşikleme orada fark yaratabilir.

Karşılaştırılan dört hâl, aynı 32 belgede, aynı etiket çıpalı kırpmada:
  ham          mevcut davranış (taban)
  clahe        uyarlamalı histogram eşitleme — soluk yazıyı belirginleştirir
  esikleme     uyarlamalı eşikleme — ikili görüntü, kağıt dokusunu siler
  keskinlestir unsharp mask — harf kenarlarını netleştirir

Kesintiye dayanıklı: her belgeden sonra önbellek yazılır, ilerleme basılır.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import araclar._kok  # noqa: F401

import csv
import json
import sys
from pathlib import Path

import cv2  # noqa: E402
import numpy as np  # noqa: E402
import pymupdf  # noqa: E402

from belge.alan_cikarici import ETIKET_AD, etiket_kutusu, satir_kutusu  # noqa: E402
from belge.isim_okuyucu import TALIMAT, _temizle, normalize  # noqa: E402
from olc_elyazisi import HEDEF, KAYNAK, Onbellek  # noqa: E402


def _png(gri: np.ndarray) -> bytes:
    return cv2.imencode(".png", gri)[1].tobytes()


def ham(g):
    return g


def buyut2(g):
    """300 DPI kırpmayı 2 kat büyütür — piksel eklenmiyor, YORUMLANIYOR.

    Model dinamik çözünürlük kullanıyorsa görsel belirteç sayısı artar.
    Detay artmadığı için, kazanç varsa sebebi belirteç sayısıdır.
    """
    return cv2.resize(g, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)


def dpi600(g):
    """Yer tutucu — gerçek 600 DPI kırpma ana döngüde üretilir."""
    return g


def clahe(g):
    return cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8)).apply(g)


def esikleme(g):
    # Blok boyutu satır yüksekliğine göre kaba ayarlı; sabit eşik sararmış
    # kağıtta çalışmıyor çünkü arka plan parlaklığı sayfa içinde değişiyor.
    return cv2.adaptiveThreshold(g, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                 cv2.THRESH_BINARY, 31, 15)


def keskinlestir(g):
    bulanik = cv2.GaussianBlur(g, (0, 0), 3)
    return cv2.addWeighted(g, 1.6, bulanik, -0.6, 0)


# Ölçülen: clahe ve eşikleme zarar veriyor, keskinleştirme fark etmiyor.
# Bu turda sorulan soru farklı: kazanç DETAYDAN mı BELİRTEÇ SAYISINDAN mı?
#   buyut2  -> detay sabit, belirteç artar (interpolasyon)
#   dpi600  -> detay da artar (gerçek yeniden tarama)
YONTEMLER = {"ham": ham, "buyut2": buyut2}


def main() -> None:
    from belge.isim_okuyucu import IsimOkuyucu, argv_model, secilen_model

    altin = [s for s in csv.DictReader((HEDEF / "altin_set.csv").open(encoding="utf-8"))
             if s["DOGRU_ISIM"].strip()]
    tah = json.loads((HEDEF / "_tahminler.json").read_text(encoding="utf-8"))
    model = secilen_model(argv_model())
    onb = Onbellek()
    print(f"{len(altin)} belge, model yükleniyor ({model})...", flush=True)
    onb.gercek = IsimOkuyucu(model)

    sayim = {ad: {"el": [0, 0], "hepsi": [0, 0]} for ad in YONTEMLER}
    for i, satir in enumerate(altin, 1):
        dogru = normalize(satir["DOGRU_ISIM"])
        tur = satir["TUR"] or "?"
        yol = KAYNAK / tah[satir["sira"]]["kaynak_dosya"]
        with pymupdf.open(yol) as belge:
            kirpma_png = None
            for sayfa in belge:
                kutu = etiket_kutusu(sayfa, ETIKET_AD)
                if kutu is None:
                    continue
                r = pymupdf.Rect(*satir_kutusu(sayfa, kutu)) & sayfa.rect
                kirpma_png = sayfa.get_pixmap(dpi=300, clip=r).tobytes("png")
                break
        if kirpma_png is None:
            continue
        dizi = cv2.imdecode(np.frombuffer(kirpma_png, np.uint8), cv2.IMREAD_GRAYSCALE)

        # 600 DPI: gerçek detay artışı, interpolasyon değil
        with pymupdf.open(yol) as belge:
            for sayfa in belge:
                kutu = etiket_kutusu(sayfa, ETIKET_AD)
                if kutu is None:
                    continue
                r = pymupdf.Rect(*satir_kutusu(sayfa, kutu)) & sayfa.rect
                yuksek = sayfa.get_pixmap(dpi=600, clip=r).tobytes("png")
                break
        okunan = normalize(_temizle(onb.uret(TALIMAT, yuksek)))
        sayim.setdefault("dpi600", {"el": [0, 0], "hepsi": [0, 0]})
        sayim["dpi600"]["hepsi"][1] += 1
        sayim["dpi600"]["hepsi"][0] += okunan == dogru
        if tur == "el":
            sayim["dpi600"]["el"][1] += 1
            sayim["dpi600"]["el"][0] += okunan == dogru

        for ad, islev in YONTEMLER.items():
            png = _png(islev(dizi))
            okunan = normalize(_temizle(onb.uret(TALIMAT, png)))
            sayim[ad]["hepsi"][1] += 1
            sayim[ad]["hepsi"][0] += okunan == dogru
            if tur == "el":
                sayim[ad]["el"][1] += 1
                sayim[ad]["el"][0] += okunan == dogru
        onb.kaydet()
        if i % 8 == 0:
            print(f"  {i}/{len(altin)} (yeni çağrı {onb.cagri})", flush=True)

    print(f"\nyeni model çağrısı: {onb.cagri}\n")
    print(f"{'yöntem':<16}{'el yazısı':>14}{'tümü':>14}")
    for ad in sayim:
        e, h = sayim[ad]["el"], sayim[ad]["hepsi"]
        print(f"{ad:<16}{f'{e[0]}/{e[1]}':>14}{f'{h[0]}/{h[1]}':>14}")


if __name__ == "__main__":
    main()
