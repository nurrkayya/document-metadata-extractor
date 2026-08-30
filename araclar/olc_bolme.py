"""Bölme planını altın setin işaretli belgelerinde ölçer (SPEC Adım 11, R8).

    .venv/bin/python araclar/olc_bolme.py          # OCR + serbest arama
    .venv/bin/python araclar/olc_bolme.py vlm      # VLM adımı da açık

Hiçbir dosya yazılmaz — yalnızca plan çıkarılıp raporlanır. Bölmenin kendisi
`belge/bolucu.uygula` ile ve varsayılan olarak kuru kipte yapılır.
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

from belge.arsiv import kaynaktan_bul  # noqa: E402
from belge.alan_cikarici import cikar  # noqa: E402
from belge.bolucu import plan_cikar, uygula  # noqa: E402

ALTIN_SET = Path("altin_set/altin_set.csv")
TAHMINLER = Path("altin_set/_tahminler.json")
ORNEKLER = Path("ornekler")
ISARET = "YANLIS_BIRLESTIRME"


def main(kip: str = "") -> None:
    with ALTIN_SET.open(encoding="utf-8") as f:
        satirlar = {s["sira"]: s for s in csv.DictReader(f)}
    tahminler = json.loads(TAHMINLER.read_text(encoding="utf-8"))
    isaretli = [s for s in sorted(satirlar, key=int) if satirlar[s].get(ISARET, "").strip()]
    if not isaretli:
        print(f"Altın sette {ISARET} işaretli belge yok.")
        return

    okuyucu = None
    if kip == "vlm":
        from olc_tc_sicil import OnbellekliOkuyucu

        okuyucu = OnbellekliOkuyucu(None)
        try:
            from belge.isim_okuyucu import IsimOkuyucu, argv_model

            print("Model yükleniyor...")
            okuyucu.gercek = IsimOkuyucu(argv_model())
        except Exception as hata:  # model yoksa önbellekle devam
            print(f"  model yüklenemedi ({type(hata).__name__}), önbellek kullanılacak")

    print(f"{len(isaretli)} işaretli belge{' (VLM açık)' if okuyucu else ''}\n")
    bolunen = 0
    for sira in isaretli:
        yol = kaynaktan_bul(tahminler[sira]["kaynak_dosya"])
        if yol is None:
            continue
        # Birincil kimlik: DN sahibinin TC'si. Altın setten değil çıkarıcıdan
        # alınır — üretimde altın set yok, ölçüm gerçek koşulu yansıtmalı.
        # VLM açıksa Adım 10 tamamlaması da uygulanır: TC kapsaması OCR'da
        # %76.6, VLM ile %98.7. Bunu atlamak belgeleri boşuna elemek olur.
        sonuc = cikar(yol)
        if okuyucu is not None and not sonuc.tc_no:
            from belge.sayi_okuyucu import tamamla

            sonuc = tamamla(okuyucu, yol, sonuc)
        birincil = sonuc.tc_no
        if not birincil:
            print(f"  #{sira:>3}  ATLANDI — birincil TC çıkarılamadı")
            continue

        plan = plan_cikar(yol, birincil, okuyucu)
        durum = "BÖLÜNEBİLİR" if plan.bolunebilir else "elle"
        print(f"  #{sira:>3}  {plan.harita:<24} {durum:<12} {plan.gerekce}")
        if plan.bolunebilir:
            bolunen += 1
            for cikti in uygula(yol, plan, Path("ayrildi"), kuru_calistir=True):
                print(f"          -> {cikti.name}")

    if okuyucu is not None:
        okuyucu.kaydet()
    print(f"\notomatik bölünebilen: {bolunen}/{len(isaretli)}")
    print("Hiçbir dosya yazılmadı (kuru kip).")


if __name__ == "__main__":
    main(*sys.argv[1:])
