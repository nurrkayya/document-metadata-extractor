"""Kırpmanın NEYİ içerdiğini ölçer (SPEC 5.4).

    .venv/bin/python -u araclar/olc_kirpma.py

Büyütme ve ön işleme ölçüldü, ikisi de işe yaramadı. Ama o denemeler
kırpmanın SINIRLARINI hiç değiştirmedi. Mevcut kırpma etiketin solundan
sayfanın sağ kenarına kadar uzanıyor ve modele şunları birlikte veriyor:

    [Adı ve Soyadı] [:] [el yazısı] [noktalı çizgi] [fotoğraf] [mühür]

Hipotez: model gördüğünde iyi okuyor; sorun görmesi gerekeni kalabalığın
içinde bulmak zorunda olması.

Ölçülen dört varyant:
  ham            mevcut: etiket + değer + sağdaki her şey
  etiketsiz      basılı etiket atılır, değerden başlar
  murekkep       etiketsiz + sondaki boşluk/noktalı çizgi kırpılır (mürekkep sınırı)
  dar_bant       ham, ama dikey bant daraltılır (komşu satırlar dışarıda)
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

from belge.alan_cikarici import ETIKET_AD, etiket_kutusu  # noqa: E402
from belge.isim_okuyucu import TALIMAT, _temizle, normalize  # noqa: E402
from olc_elyazisi import HEDEF, KAYNAK, Onbellek  # noqa: E402

DPI = 300


def _png(dizi: np.ndarray) -> bytes:
    return cv2.imencode(".png", dizi)[1].tobytes()


def _mureккep_sinirlari(gri: np.ndarray, esik: int = 200) -> tuple[int, int] | None:
    """Görüntüde mürekkebin başladığı ve bittiği sütunu bulur.

    Noktalı çizgi ve boş kağıt sağda uzayıp gidiyor; model için gürültü.
    Sütun bazında koyu piksel sayılıp eşik üstü olanların sınırı alınır.
    """
    koyu = (gri < esik).sum(axis=0)
    if koyu.max() == 0:
        return None
    # Noktalı çizgi az sayıda koyu piksel üretir; yazı çok daha fazla.
    dolu = np.where(koyu > max(2, koyu.max() * 0.15))[0]
    if len(dolu) == 0:
        return None
    return int(dolu[0]), int(dolu[-1])


def kirpmalar(pdf_yolu: Path) -> dict[str, bytes]:
    """Bir belgeden dört varyantı üretir."""
    with pymupdf.open(pdf_yolu) as belge:
        for sayfa in belge:
            kutu = etiket_kutusu(sayfa, ETIKET_AD)
            if kutu is None:
                continue
            x0, y0, x1, y1 = kutu
            yukseklik = y1 - y0
            sonuc: dict[str, bytes] = {}

            def kes(sol, pay_orani):
                r = pymupdf.Rect(sol, y0 - yukseklik * pay_orani,
                                 sayfa.rect.x1, y1 + yukseklik * pay_orani) & sayfa.rect
                return sayfa.get_pixmap(dpi=DPI, clip=r).tobytes("png")

            sonuc["ham"] = kes(max(sayfa.rect.x0, x0 - 2), 0.6)
            sonuc["dar_bant"] = kes(max(sayfa.rect.x0, x0 - 2), 0.25)
            # Etiketi at: değer etiketin sağında başlıyor
            sonuc["etiketsiz"] = kes(x1 + 2, 0.6)

            # Mürekkep sınırıyla sağdan kırp
            dizi = cv2.imdecode(
                np.frombuffer(sonuc["etiketsiz"], np.uint8), cv2.IMREAD_GRAYSCALE
            )
            sinir = _mureккep_sinirlari(dizi)
            if sinir and sinir[1] > sinir[0] + 20:
                pay = 15
                sonuc["murekkep"] = _png(
                    dizi[:, max(0, sinir[0] - pay) : min(dizi.shape[1], sinir[1] + pay)]
                )
            else:
                sonuc["murekkep"] = sonuc["etiketsiz"]
            return sonuc
    return {}


def main() -> None:
    from belge.isim_okuyucu import IsimOkuyucu, argv_model, secilen_model

    altin = [s for s in csv.DictReader((HEDEF / "altin_set.csv").open(encoding="utf-8"))
             if s["DOGRU_ISIM"].strip()]
    tah = json.loads((HEDEF / "_tahminler.json").read_text(encoding="utf-8"))
    model = secilen_model(argv_model())
    onb = Onbellek()
    print(f"{len(altin)} belge, model yükleniyor ({model})...", flush=True)
    onb.gercek = IsimOkuyucu(model)

    adlar = ["ham", "etiketsiz", "murekkep", "dar_bant"]
    sayim = {a: {"el": [0, 0], "hepsi": [0, 0]} for a in adlar}
    for i, satir in enumerate(altin, 1):
        dogru = normalize(satir["DOGRU_ISIM"])
        tur = satir["TUR"] or "?"
        pngler = kirpmalar(KAYNAK / tah[satir["sira"]]["kaynak_dosya"])
        if not pngler:
            continue
        for ad in adlar:
            okunan = normalize(_temizle(onb.uret(TALIMAT, pngler[ad])))
            sayim[ad]["hepsi"][1] += 1
            sayim[ad]["hepsi"][0] += okunan == dogru
            if tur == "el":
                sayim[ad]["el"][1] += 1
                sayim[ad]["el"][0] += okunan == dogru
        onb.kaydet()
        if i % 8 == 0:
            print(f"  {i}/{len(altin)} (yeni çağrı {onb.cagri})", flush=True)

    print(f"\nyeni model çağrısı: {onb.cagri}\n")
    print(f"{'varyant':<14}{'el yazısı':>13}{'tümü':>13}")
    for ad in adlar:
        e, h = sayim[ad]["el"], sayim[ad]["hepsi"]
        print(f"{ad:<14}{f'{e[0]}/{e[1]}':>13}{f'{h[0]}/{h[1]}':>13}")


if __name__ == "__main__":
    main()
