"""Bir klasördeki belgeleri baştan sona işler (SPEC Adım 7).

CLI girişi — çekirdek mantık `belge.islem` / `belge.arsiv` içindedir.

    .venv/bin/python isle.py ornekler                  # KURU — hiçbir şey yazılmaz
    .venv/bin/python isle.py ornekler --uygula         # gerçekten taşır
    .venv/bin/python isle.py ornekler --vlm            # VLM'i de kullan
    .venv/bin/python isle.py ornekler --sinir 20       # ilk 20 belge
    .venv/bin/python isle.py ornekler --vlm --kati     # yalnız doğrulanmışı arşivle
    .venv/bin/python isle.py ornekler --sinir 250 --karisik   # rastgele 250 belge
    .venv/bin/python isle.py ornekler --cikti /tmp/cikti      # çıktı kökü (yoksa .)
    .venv/bin/python isle.py ornekler --vlm --model mlx-community/InternVL3-14B-4bit
        # varsayılan modeli değiştirmeden geçici VLM (VLM_MODEL da olur)

Varsayılan **kuru**dur. Arşivleme dosyaları taşıyor ve geri alması zor; ne
yapacağı önce raporlanır, çıktı doğrulandıktan sonra `--uygula` verilir.

Akış (SPEC 5.2)
---------------
    PDF -> [resmi belge mi?] -> OCR alanları -> [VLM tamamlama]
        -> yanlış birleştirme kontrolü
        -> arsiv/ | okunamadi/ | ayrildi/ | bolunmeli/ | ilgisiz/ | atlandı

`--vlm` olmadan isim OCR'dan geldiği gibi (boşluksuz) kalır; bu yalnızca
akışı denemek içindir, gerçek koşuda `--vlm` gerekir (SPEC 2.2).
"""

from __future__ import annotations

import sys
from pathlib import Path

from belge.alan_cikarici import belge_resmi_mi
from belge.arsiv import (
    ARSIVLE,
    ATLA,
    BOLUNMELI,
    DOGRULANMALI,
    HATA,
    ILGISIZ,
    OKUNAMADI,
    Arsiv,
)
from belge.islem import (
    Sonuc,
    _UZLASMA,
    _alanlari_topla,
    _birlestir_guvenli,
    _birlestirme_isle,
    _bolmeleri_uygula,
    _cok_kimlikli,
    _kati_uyarisi,
    _yedek_kirpma_kutusu,
    belge_analiz,
    cok_kimlik_gerekce,
    kova_oner,
)
from belge.yollar import AYRILDI

# Geriye dönük: web / sinama `from isle import ...` kullanabilir
__all__ = [
    "AYRILDI",
    "Sonuc",
    "belge_analiz",
    "cok_kimlik_gerekce",
    "kova_oner",
    "main",
    "_UZLASMA",
    "_alanlari_topla",
    "_birlestir_guvenli",
    "_birlestirme_isle",
    "_bolmeleri_uygula",
    "_cok_kimlikli",
    "_kati_uyarisi",
    "_yedek_kirpma_kutusu",
]


def _yazdir(eylem) -> None:
    isaret = {
        ARSIVLE: "→ arsiv",
        OKUNAMADI: "→ okunamadi",
        ATLA: "· atlandı",
        BOLUNMELI: "! bolunmeli",
        DOGRULANMALI: "? dogrulanmali",
        AYRILDI: "✂ ayrildi",
        HATA: "✗ hata",
        ILGISIZ: "⚠ ilgisiz",
    }.get(eylem.tur, eylem.tur)
    hedef = eylem.hedef.name if eylem.hedef and eylem.tur in (ARSIVLE, DOGRULANMALI) else ""
    ek = f"  ({eylem.not_})" if eylem.not_ else ""
    u = _UZLASMA.get(eylem.kaynak.name, 0)
    guven = f"  [{u} sayfa uzlaştı]" if u >= 2 else ("  [UZLAŞMA YOK]" if eylem.tur == ARSIVLE else "")
    print(f"  {eylem.kaynak.name:<34} {isaret:<12} {hedef:<24}{guven}{ek}")
    if getattr(eylem, "uyarilar", None):
        print(f"    uyarı: {'; '.join(eylem.uyarilar)}")


def _ozet(eylemler, kuru: bool) -> None:
    from collections import Counter

    sayim = Counter(e.tur for e in eylemler)
    print("\nÖZET")
    for tur, etiket in (
        (ARSIVLE, "arşivlenecek"),
        (AYRILDI, "bölünecek"),
        (DOGRULANMALI, "doğrulanmalı"),
        (BOLUNMELI, "elle bölünmeli"),
        (OKUNAMADI, "isim okunamadı"),
        (ATLA, "mükerrer, atlandı"),
        (HATA, "hata"),
        (ILGISIZ, "ilgisiz/el yazısı"),
    ):
        if sayim.get(tur):
            print(f"  {etiket:<20} {sayim[tur]:>4}")
    uzlasan = sum(1 for v in _UZLASMA.values() if v >= 2)
    if _UZLASMA:
        print(f"  {'uzlaşmayla okunan':<20} {uzlasan:>4}  (güvenilir)")
        print(f"  {'uzlaşma yok':<20} {len(_UZLASMA) - uzlasan:>4}  (eski yoldan, doğrulanmamış)")
    if kuru:
        print("\nHiçbir dosya yazılmadı. Uygulamak için: --uygula")


def main(argv: list[str]) -> int:
    if not argv or argv[0].startswith("-"):
        print(__doc__)
        return 1

    kaynak = Path(argv[0])
    kuru = "--uygula" not in argv
    vlm = "--vlm" in argv
    kati = "--kati" in argv
    sinir = None
    if "--sinir" in argv:
        sinir = int(argv[argv.index("--sinir") + 1])
    karisik = "--karisik" in argv
    cikti = Path(".")
    if "--cikti" in argv:
        cikti = Path(argv[argv.index("--cikti") + 1])

    if not kaynak.is_dir():
        print(f"Klasör yok: {kaynak}")
        return 1

    uyari = _kati_uyarisi(vlm, kati, kuru)
    if uyari:
        print(uyari, file=sys.stderr)

    okuyucu = None
    if vlm:
        from belge.isim_okuyucu import IsimOkuyucu, argv_model, secilen_model

        model = secilen_model(argv_model(argv))
        print(f"Model yükleniyor ({model})...")
        okuyucu = IsimOkuyucu(model)

    dosyalar = sorted(kaynak.rglob("*.pdf"))
    if karisik:
        import random

        random.Random(42).shuffle(dosyalar)
    dosyalar = dosyalar[:sinir]
    arsiv = Arsiv.yukle(cikti)
    print(
        f"{len(dosyalar)} belge{' (VLM açık)' if vlm else ''}{' [KATI]' if kati else ''} — "
        f"{'KURU ÇALIŞTIRMA, hiçbir dosya yazılmayacak' if kuru else 'UYGULANACAK'}\n"
    )

    _UZLASMA.clear()
    eylemler = []
    for yol in dosyalar:
        try:
            if not belge_resmi_mi(yol):
                eylem = arsiv.ilgisiz_planla(
                    yol,
                    "hiçbir sayfada resmi belge göstergesi yok (muhtemelen ilgisiz/el yazısı)",
                )
                eylemler.append(eylem)
                _yazdir(eylem)
                if not kuru:
                    arsiv.uygula([eylem], kuru_calistir=False)
                continue

            if _cok_kimlikli(yol):
                eylem, plan = _birlestirme_isle(yol, arsiv, okuyucu)
            else:
                alanlar = _alanlari_topla(yol, okuyucu)
                _UZLASMA[yol.name] = alanlar.uzlasma
                eylem, plan = arsiv.planla(yol, alanlar, kati=kati), None
            eylemler.append(eylem)
            _yazdir(eylem)

            if kuru:
                continue

            arsiv.uygula([eylem], kuru_calistir=False)
            if plan is not None and eylem.hedef is not None:
                parcalar = _bolmeleri_uygula([(eylem.hedef, plan)])
                if parcalar:
                    print(f"\n{len(parcalar)} parça işleniyor:")
                for p in parcalar:
                    parca_alan = _alanlari_topla(p, okuyucu)
                    _UZLASMA[p.name] = parca_alan.uzlasma
                    parca_eylem = arsiv.planla(p, parca_alan, kati=kati)
                    eylemler.append(parca_eylem)
                    _yazdir(parca_eylem)
                    arsiv.uygula([parca_eylem], kuru_calistir=False)
        except (KeyboardInterrupt, MemoryError):
            raise
        except Exception as e:
            print(f"  HATA {yol.name}: {e}")
            eylem = arsiv.hata_planla(yol, str(e))
            eylemler.append(eylem)
            _yazdir(eylem)
            if not kuru:
                try:
                    arsiv.uygula([eylem], kuru_calistir=False)
                except Exception as tasi:
                    print(f"  HATA {yol.name} taşınamadı: {tasi}")

    _ozet(eylemler, kuru)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
