"""Yeni isim yolunu (çok sayfalı uzlaşma) 1. külliyatta ölçer.

    .venv/bin/python -u araclar/olc_yeni_yol.py

`isle.py` isim okumayı tek sayfadan çok sayfalı uzlaşmaya çevirdi. Bu yol
2. külliyatta ölçüldü (el yazısında %88) ama 1. külliyatta ölçülmedi; orada
eski yol %95 veriyor ve gerileme olup olmadığı bilinmiyor.

Kesintiye dayanıklı: her belgeden sonra önbellek diske yazılır, ilerleme
anında basılır. (Daha önce 33 dakikalık bir koşu kesilip her şey kaybolmuştu.)
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

from belge.alan_cikarici import cikar  # noqa: E402
from belge.arsiv import kaynaktan_bul  # noqa: E402
from belge.isim_okuyucu import birlestir, coklu_sayfa_oku, normalize  # noqa: E402
from olc_tc_sicil import OnbellekliOkuyucu  # noqa: E402

ALTIN = Path("altin_set/altin_set.csv")
TAHMIN = Path("altin_set/_tahminler.json")


class Sarmal:
    """coklu_sayfa_oku bir `oku()` bekliyor; önbelleği araya sokuyoruz."""

    def __init__(self, onb):
        self.onb = onb

    def oku(self, png, ocr_ipucu="", azami_belirtec=40):
        from belge.isim_okuyucu import TALIMAT, OkunanIsim, _temizle

        ham = self.onb.uret(TALIMAT, png, azami_belirtec)
        return OkunanIsim(isim=_temizle(ham), ham_cikti=ham)


def main() -> None:
    from belge.isim_okuyucu import IsimOkuyucu, argv_model, secilen_model

    dogrular = {s["sira"]: s["DOGRU_ISIM"] for s in csv.DictReader(ALTIN.open(encoding="utf-8"))}
    tahminler = json.loads(TAHMIN.read_text(encoding="utf-8"))
    model = secilen_model(argv_model())
    onb = OnbellekliOkuyucu(None)
    print(f"model yükleniyor ({model})...", flush=True)
    onb.gercek = IsimOkuyucu(model)
    sarmal = Sarmal(onb)
    print(f"{len(dogrular)} belge\n", flush=True)

    sayim = {"uzlasan_dogru": 0, "uzlasan_yanlis": 0, "uzlasma_yok": 0, "atlandi": 0}
    yeni_dogru = 0
    olculen = 0
    for i, sira in enumerate(sorted(dogrular, key=int), 1):
        dogru = normalize(dogrular[sira])
        if not dogru:
            continue
        yol = kaynaktan_bul(tahminler[sira]["kaynak_dosya"])
        if yol is None:
            sayim["atlandi"] += 1
            continue
        olculen += 1
        alanlar = cikar(yol)
        coklu = coklu_sayfa_oku(sarmal, yol)
        if coklu.uzlasan:
            sonuc = normalize(birlestir(coklu.uzlasan, alanlar.isim_bosluksuz))
            sayim["uzlasan_dogru" if sonuc == dogru else "uzlasan_yanlis"] += 1
        else:
            sayim["uzlasma_yok"] += 1
            sonuc = ""
        if sonuc == dogru:
            yeni_dogru += 1
        onb.kaydet()
        if i % 10 == 0:
            print(f"  {i}/{len(dogrular)} ... (yeni çağrı {onb.cagri})", flush=True)

    print(f"\nÖLÇÜLEN {olculen} belge, yeni model çağrısı {onb.cagri}")
    u = sayim["uzlasan_dogru"] + sayim["uzlasan_yanlis"]
    print(f"  uzlaşma sağlandı : {u}  -> doğru {sayim['uzlasan_dogru']}, "
          f"yanlış {sayim['uzlasan_yanlis']}"
          + (f"  (isabet %{100*sayim['uzlasan_dogru']/u:.0f})" if u else ""))
    print(f"  uzlaşma YOK      : {sayim['uzlasma_yok']}  -> eski yola düşer")
    print(f"  kapsama (uzlaşma): %{100*u/olculen:.0f}" if olculen else "")
    print(f"\n  Karşılaştırma: eski yol (tek sayfa + birleştirme) %95.0")


if __name__ == "__main__":
    main()
