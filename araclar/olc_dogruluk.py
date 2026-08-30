"""Altın sete karşı gerçek doğruluk ölçümü (SPEC bölüm 6).

OCR'ın ve VLM'in okumalarını insan tarafından doğrulanmış değerlerle
karşılaştırır. Bundan sonraki her iyileştirmenin etkisi bu araçla ölçülür.

    .venv/bin/python araclar/olc_dogruluk.py

Hata türleri ayrı sayılır. Özellikle "sadece İ/I farkı" kendi başına
raporlanır: bu, modelin şu ana kadar gözlenen tek sistematik hatası ve
sıklığını bilmeden ona yönelik iyileştirme yapmak körlemesine olur.
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
from belge.isim_okuyucu import (  # noqa: E402
    IsimOkuyucu,
    argv_model,
    birlestir,
    noktasizlastir,
    normalize,
    onbellek_yolu,
)
from belge.pdf_okuyucu import bolge_goruntusu  # noqa: E402

ALTIN_SET = Path("altin_set/altin_set.csv")
TAHMINLER = Path("altin_set/_tahminler.json")
VLM_ONBELLEK = Path("altin_set/_vlm_okumalari.json")
ORNEKLER = Path("ornekler")


def main() -> None:
    if not ALTIN_SET.exists():
        print(f"{ALTIN_SET} yok. Önce araclar/altin_set_hazirla.py çalıştırın.")
        return

    dogrular = {s["sira"]: s["DOGRU_ISIM"] for s in csv.DictReader(ALTIN_SET.open(encoding="utf-8"))}
    tahminler = json.loads(TAHMINLER.read_text(encoding="utf-8"))

    # VLM okumaları önbelleğe alınır: model çağrısı pahalı, ama birleştirme
    # kurallarını denemek için aynı okumalar defalarca gerekiyor.
    onbellek_dosya = onbellek_yolu(VLM_ONBELLEK)
    onbellek = json.loads(onbellek_dosya.read_text(encoding="utf-8")) if onbellek_dosya.exists() else {}
    eksik = [s for s in dogrular if s not in onbellek]

    okuyucu = None
    if eksik:
        print(f"Model yükleniyor ({len(eksik)} belge okunacak)...")
        okuyucu = IsimOkuyucu(argv_model())
    else:
        print(f"Tüm okumalar önbellekte ({onbellek_dosya}), model yüklenmiyor.")
    print(f"{len(dogrular)} belge ölçülüyor...\n")

    sayim = {
        "ocr_tam": 0,
        "vlm_tam": 0,
        "birlesik_tam": 0,
        "sadece_nokta": 0,
        "diger_hata": 0,
        "okuyamadi": 0,
    }
    hatalar = []

    for sira in sorted(dogrular, key=int):
        dogru = normalize(dogrular[sira])
        if not dogru:
            continue
        pdf = kaynaktan_bul(tahminler[sira]["kaynak_dosya"])
        if pdf is None:
            continue

        # OCR okuması her seferinde yeniden hesaplanır. _tahminler.json'daki
        # değer altın set hazırlanırkenki çıkarıcıya aitti; çıkarıcı
        # değiştiğinde bayat kalıyor ve birleştirmeyi yanlış besliyor.
        sonuc = cikar(pdf)
        ocr_ham = sonuc.isim_bosluksuz
        if normalize(ocr_ham) == dogru:
            sayim["ocr_tam"] += 1

        if sira in onbellek:
            vlm = normalize(onbellek[sira])
        else:
            if sonuc.isim_kutusu and sonuc.isim_sayfa:
                png = bolge_goruntusu(pdf, sonuc.isim_sayfa, sonuc.isim_kutusu, dpi=300)
                ham = okuyucu.oku(png).isim
            else:
                ham = ""  # isim satırı bulunamadı: sistem bu belgeyi okuyamıyor
            onbellek[sira] = ham
            vlm = normalize(ham)

        if vlm == dogru:
            sayim["vlm_tam"] += 1

        # Nihai sonuç: iki okumanın birleşimi (belge/isim_okuyucu.birlestir)
        birlesik = normalize(birlestir(vlm, ocr_ham))
        if birlesik == dogru:
            sayim["birlesik_tam"] += 1
        elif not birlesik:
            sayim["okuyamadi"] += 1
            hatalar.append((sira, dogru, "(okunamadı)", "okuyamadi"))
        elif noktasizlastir(birlesik) == noktasizlastir(dogru):
            sayim["sadece_nokta"] += 1
            hatalar.append((sira, dogru, birlesik, "sadece İ/I"))
        else:
            sayim["diger_hata"] += 1
            hatalar.append((sira, dogru, birlesik, "farklı"))

    onbellek_dosya.write_text(json.dumps(onbellek, ensure_ascii=False, indent=2), encoding="utf-8")

    toplam = sum(1 for s in dogrular.values() if normalize(s))

    def yuzde(n: int) -> str:
        return f"{n:3}/{toplam}  (%{100 * n / toplam:.1f})"

    print(f"ÖLÇÜM SONUCU ({toplam} belge)\n")
    print(f"  Sadece OCR                : {yuzde(sayim['ocr_tam'])}")
    print(f"  Sadece VLM                : {yuzde(sayim['vlm_tam'])}")
    print(f"  BİRLEŞİK (kullanılan)     : {yuzde(sayim['birlesik_tam'])}")
    print()
    print("  Kalan hatalar:")
    print(f"    sadece İ/I nokta farkı  : {sayim['sadece_nokta']:3}")
    print(f"    gerçekten farklı okuma  : {sayim['diger_hata']:3}")
    print(f"    hiç okuyamadı           : {sayim['okuyamadi']:3}")

    nokta_affedilse = sayim["birlesik_tam"] + sayim["sadece_nokta"]
    print(f"\n  İ/I farkı yok sayılsaydı  : {yuzde(nokta_affedilse)}")

    if hatalar:
        print("\nHatalı okumalar")
        print(f"  {'#':>3}  {'doğru':28} {'VLM':28} tür")
        for sira, dogru, vlm, tur in hatalar:
            print(f"  {sira:>3}  {dogru:28} {vlm:28} {tur}")


if __name__ == "__main__":
    main()
