"""Çok sayfalı isim okuma + oylama ölçümü (SPEC Adım 6, el yazısı külliyatı).

    .venv/bin/python araclar/olc_coklu_sayfa.py

Belgelerin %81'inde isim etiketi birden fazla sayfada bulunuyor (ortanca 3).
Mevcut kod ilk eşleşen sayfada duruyor; kalan sayfalar hiç kullanılmıyor.

Ölçülen üç strateji:
  ilk sayfa      mevcut davranış, taban
  çoğunluk       en çok tekrar eden okuma alınır
  uzlaşma        en az 2 sayfa aynı okumayı verirse kabul, yoksa BOŞ

Üçüncüsü kapsamayı düşürüp isabeti yükseltmeyi hedefler: projede sessiz yanlış
boş alandan çok daha pahalı.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import araclar._kok  # noqa: F401

import csv
import json
import sys
from collections import Counter
from pathlib import Path

import pymupdf  # noqa: E402

from belge.alan_cikarici import ETIKET_AD, etiket_kutusu, satir_kutusu  # noqa: E402
from belge.isim_okuyucu import normalize, oy_birlestir  # noqa: E402
from olc_elyazisi import HEDEF, KAYNAK, Onbellek  # noqa: E402


def sayfa_okumalari(yol: Path, onb, talimat: str, temizle) -> list[str]:
    okumalar = []
    with pymupdf.open(yol) as belge:
        for sayfa in belge:
            kutu = etiket_kutusu(sayfa, ETIKET_AD)
            if kutu is None:
                continue
            r = pymupdf.Rect(*satir_kutusu(sayfa, kutu)) & sayfa.rect
            png = sayfa.get_pixmap(dpi=300, clip=r).tobytes("png")
            okunan = normalize(temizle(onb.uret(talimat, png)))
            if okunan:
                okumalar.append(okunan)
    return okumalar


def main() -> None:
    from belge.isim_okuyucu import TALIMAT, IsimOkuyucu, _temizle, argv_model, secilen_model

    altin = [s for s in csv.DictReader((HEDEF / "altin_set.csv").open(encoding="utf-8"))
             if s["DOGRU_ISIM"].strip()]
    tah = json.loads((HEDEF / "_tahminler.json").read_text(encoding="utf-8"))

    model = secilen_model(argv_model())
    onb = Onbellek()
    print(f"{len(altin)} belge, model yükleniyor ({model})...")
    onb.gercek = IsimOkuyucu(model)

    sayim = {s: {"dogru": 0, "yanlis": 0, "bos": 0} for s in ("ilk", "cogunluk", "uzlasma")}
    tur_sayim: dict[str, dict[str, int]] = {}

    for satir in altin:
        dogru = normalize(satir["DOGRU_ISIM"])
        tur = satir["TUR"] or "?"
        yol = KAYNAK / tah[satir["sira"]]["kaynak_dosya"]
        okumalar = sayfa_okumalari(yol, onb, TALIMAT, _temizle)

        sonuc = {}
        sonuc["ilk"] = okumalar[0] if okumalar else ""
        temsilci, adet = oy_birlestir(okumalar)
        sonuc["cogunluk"] = temsilci
        sonuc["uzlasma"] = temsilci if adet >= 2 else ""

        for strateji, okunan in sonuc.items():
            k = "bos" if not okunan else ("dogru" if okunan == dogru else "yanlis")
            sayim[strateji][k] += 1
            tur_sayim.setdefault(tur, {}).setdefault(strateji, Counter())[k] += 1

    onb.kaydet()
    print(f"yeni model çağrısı: {onb.cagri}\n")
    print(f"{'strateji':<12}{'doğru':>8}{'yanlış':>8}{'boş':>7}{'isabet':>10}{'kapsama':>10}")
    for strateji, s in sayim.items():
        uretilen = s["dogru"] + s["yanlis"]
        isabet = f"%{100*s['dogru']/uretilen:.0f}" if uretilen else "-"
        kapsama = f"%{100*uretilen/len(altin):.0f}"
        print(f"{strateji:<12}{s['dogru']:>8}{s['yanlis']:>8}{s['bos']:>7}{isabet:>10}{kapsama:>10}")

    print("\nTÜRE GÖRE (doğru/toplam)")
    print(f"{'tür':<10}" + "".join(f"{x:>14}" for x in ("ilk", "cogunluk", "uzlasma")))
    for tur in ("el", "daktilo", "matbu"):
        if tur not in tur_sayim:
            continue
        satir = f"{tur:<10}"
        for strateji in ("ilk", "cogunluk", "uzlasma"):
            c = tur_sayim[tur][strateji]
            satir += f"{f'{c['dogru']}/{sum(c.values())}':>14}"
        print(satir)


if __name__ == "__main__":
    main()
