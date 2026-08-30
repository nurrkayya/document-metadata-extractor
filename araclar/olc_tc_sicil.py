"""`tc_no` ve `sicil_no` doğruluğunu altın sete karşı ölçer (SPEC 3, R6).

    .venv/bin/python araclar/olc_tc_sicil.py

Model gerekmez: bu iki alan tamamen OCR metninden desenle çıkarılıyor
(`belge/alan_cikarici.py`), VLM devrede değil. Ölçüm saniyeler sürer.

Kapsama ile doğruluk neden ayrı sayılıyor
-----------------------------------------
Bugüne kadar bu iki alan için elimizde yalnızca **kapsama** vardı: "çıkarıcı
bir değer üretebildi mi". Üretilen değerin doğru olup olmadığı hiç
bakılmamıştı. İkisi çok farklı şeyler:

  kaçırdı   — çıkarıcı boş bıraktı. Zararsız: alan `person_data.json`'da boş
              kalır, kimse yanlış bilgilendirilmez.
  YANLIŞ    — çıkarıcı dolu ama hatalı değer üretti. Tehlikeli: sessizdir,
              arşivde yanlış kişiye ait TC durur ve fark edilmez.

Bu yüzden asıl rakam **isabet** (üretilen değerlerin kaçı doğru), kapsama
değil. Rapor ikisini ayrı verir.

R6 alt kümesi
-------------
Belgede birden fazla geçerli TC geçen belgeler ayrıca raporlanır. SPEC R6'nın
sorduğu soru orada: çıkarıcı DN sahibinin TC'sini mi alıyor, yoksa eşin/
kefilin TC'sini mi? Genel ortalama bu küçük ama kritik grubu gizler.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import araclar._kok  # noqa: F401

import csv
import hashlib
import json
import re
import sys
from pathlib import Path

import pymupdf  # noqa: E402

from belge.arsiv import kaynaktan_bul  # noqa: E402
from belge.alan_cikarici import cikar, gecerli_tcler  # noqa: E402

ALTIN_SET = Path("altin_set/altin_set.csv")
TAHMINLER = Path("altin_set/_tahminler.json")
VLM_ONBELLEK = Path("altin_set/_vlm_sayi_okumalari.json")
ORNEKLER = Path("ornekler")


class OnbellekliOkuyucu:
    """Model çağrılarını önbelleğe alan sarmalayıcı.

    Birleştirme kurallarını denemek aynı okumaları defalarca gerektiriyor ama
    her çağrı saniyeler sürüyor. Önbellek ölçümün içinde duruyor, üretim
    modülünde değil: `belge/sayi_okuyucu.py` ölçümün varlığından habersiz
    kalmalı.

    Anahtar talimat+görüntüden türetilir, sıra numarasından değil — talimat
    değişirse önbellek kendiliğinden geçersiz olur ve bayat okuma dönmez.
    """

    def __init__(self, gercek: object | None, yol: Path | None = None) -> None:
        from belge.isim_okuyucu import onbellek_yolu

        self.yol = yol if yol is not None else onbellek_yolu(VLM_ONBELLEK)
        self.gercek = gercek
        self.kayit: dict[str, str] = (
            json.loads(self.yol.read_text(encoding="utf-8")) if self.yol.exists() else {}
        )
        self.cagri = 0

    def uret(self, talimat: str, png_baytlari: bytes, azami_belirtec: int = 40) -> str:
        anahtar = hashlib.sha256(talimat.encode() + png_baytlari).hexdigest()[:32]
        if anahtar not in self.kayit:
            if self.gercek is None:
                raise SystemExit(
                    "Önbellekte olmayan okuma var ama model yüklenmedi.\n"
                    "Modeli yükleyerek çalıştırın: olc_tc_sicil.py vlm"
                )
            self.kayit[anahtar] = self.gercek.uret(talimat, png_baytlari, azami_belirtec)
            self.cagri += 1
        return self.kayit[anahtar]

    def kaydet(self) -> None:
        self.yol.write_text(
            json.dumps(self.kayit, ensure_ascii=False, indent=2), encoding="utf-8"
        )


SADECE_RAKAM = re.compile(r"\D")


def _sadelestir(deger: str) -> str:
    return SADECE_RAKAM.sub("", deger or "")


def _rapor(ad: str, kayitlar: list[tuple[str, str, str]]) -> dict[str, int]:
    """kayitlar: (sira, altin, cikan) — hepsi sadeleştirilmiş."""
    sayim = {"dogru": 0, "yanlis": 0, "kacirdi": 0, "olculemez": 0}
    hatalar = []
    for sira, altin, cikan in kayitlar:
        if not altin:
            sayim["olculemez"] += 1
        elif not cikan:
            sayim["kacirdi"] += 1
            hatalar.append((sira, altin, "(boş)", "kaçırdı"))
        elif cikan == altin:
            sayim["dogru"] += 1
        else:
            sayim["yanlis"] += 1
            hatalar.append((sira, altin, cikan, "YANLIŞ"))

    olculen = len(kayitlar) - sayim["olculemez"]
    uretilen = sayim["dogru"] + sayim["yanlis"]

    def yuzde(n: int, payda: int) -> str:
        return f"{n:3}/{payda}  (%{100 * n / payda:.1f})" if payda else f"{n:3}/0"

    print(f"\n{ad}  —  ölçülebilen {olculen} belge")
    print(f"  İSABET (üretilenin doğruluğu) : {yuzde(sayim['dogru'], uretilen)}")
    print(f"  Kapsama (değer üretebildi)    : {yuzde(uretilen, olculen)}")
    print(f"  Uçtan uca (doğru / ölçülen)   : {yuzde(sayim['dogru'], olculen)}")
    print(f"    sessiz YANLIŞ               : {sayim['yanlis']:3}")
    print(f"    kaçırdı (boş bıraktı)       : {sayim['kacirdi']:3}")
    if sayim["olculemez"]:
        print(f"    altın sette boş, ölçülemedi : {sayim['olculemez']:3}")

    if hatalar:
        # Kişisel veri terminale basılmaz (SPEC 7). Yalnızca sıra ve hata türü
        # gösterilir; belgeye bakmak gerekirse sıra numarası yeterli.
        print(f"\n  Hatalı belgeler ({ad}):")
        for sira, altin, cikan, tur in hatalar:
            ek = "" if tur == "kaçırdı" else f"  ({len(altin)} hane bekleniyordu, {len(cikan)} geldi)"
            print(f"    #{sira:>3}  {tur}{ek}")
    return sayim


def main(kip: str = "") -> None:
    vlm_acik = kip == "vlm"
    if not ALTIN_SET.exists():
        print(f"{ALTIN_SET} yok. Önce araclar/altin_set_hazirla.py çalıştırın.")
        return

    with ALTIN_SET.open(encoding="utf-8") as f:
        satirlar = list(csv.DictReader(f))
    if "DOGRU_TC" not in (satirlar[0] if satirlar else {}):
        print("Altın sette DOGRU_TC/DOGRU_SICIL sütunu yok.")
        print("Önce: .venv/bin/python araclar/altin_set_tc_sicil.py")
        return

    dolu = sum(1 for s in satirlar if s.get("DOGRU_TC", "").strip() or s.get("DOGRU_SICIL", "").strip())
    if not dolu:
        print("Altın sette hiç TC/sicil cevabı yok — doldurma sayfası henüz işlenmemiş.")
        print("  1) altin_set/doldur_tc_sicil.html sayfasını doldur, CSV indir")
        print("  2) .venv/bin/python araclar/altin_set_tc_sicil.py birlestir <indirilen.csv>")
        return

    tahminler = json.loads(TAHMINLER.read_text(encoding="utf-8"))

    okuyucu = None
    if vlm_acik:
        from belge.sayi_okuyucu import tamamla

        onbellek = OnbellekliOkuyucu(None)
        eksik_olabilir = not onbellek.yol.exists()
        if eksik_olabilir:
            from belge.isim_okuyucu import IsimOkuyucu, argv_model

            print("Model yükleniyor...")
            onbellek.gercek = IsimOkuyucu(argv_model())
        okuyucu = (onbellek, tamamla)
    print(f"{len(satirlar)} belge ölçülüyor{' (VLM açık)' if vlm_acik else ''}...")

    tc_kayitlari, sicil_kayitlari, r6_kayitlari, birlesik_kayitlari = [], [], [], []
    for satir in satirlar:
        sira = satir["sira"]
        yol = kaynaktan_bul(tahminler[sira]["kaynak_dosya"])
        if yol is None:
            continue
        sonuc = cikar(yol)
        if okuyucu is not None:
            onbellek, tamamla = okuyucu
            try:
                sonuc = tamamla(onbellek, yol, sonuc)
            except SystemExit:
                from belge.isim_okuyucu import IsimOkuyucu, argv_model

                print("  önbellek eksik, model yükleniyor...")
                onbellek.gercek = IsimOkuyucu(argv_model())
                sonuc = tamamla(onbellek, yol, sonuc)

        tc = (sira, _sadelestir(satir.get("DOGRU_TC", "")), _sadelestir(sonuc.tc_no))
        tc_kayitlari.append(tc)
        sicil_kayitlari.append(
            (sira, _sadelestir(satir.get("DOGRU_SICIL", "")), _sadelestir(sonuc.sicil_no))
        )

        with pymupdf.open(yol) as belge:
            adet = len({t for s in belge for t in gecerli_tcler(s.get_text())})
        if adet != 1:
            r6_kayitlari.append(tc)
        if satir.get("YANLIS_BIRLESTIRME", "").strip():
            birlesik_kayitlari.append(tc)

    if okuyucu is not None:
        okuyucu[0].kaydet()
        print(f"  yeni model çağrısı: {okuyucu[0].cagri}")

    _rapor("TC KİMLİK NO", tc_kayitlari)
    _rapor("SİCİL NO", sicil_kayitlari)
    if r6_kayitlari:
        print("\n" + "=" * 60)
        print("R6 alt kümesi: belgede TC sayısı 1 değil (sahiplik kararı gerekiyor)")
        _rapor("TC — belirsiz belgeler", r6_kayitlari)
    if birlesik_kayitlari:
        print("\n" + "=" * 60)
        print("R8 alt kümesi: yanlış birleştirilmiş belgeler (iki kişinin dosyası bir arada)")
        print("Doğru değer DN sahibine ait. Buradaki isabet 'DN sahibini doğru")
        print("seçebiliyor muyuz' sorusunu yanıtlar — ikinci kişi yine de kaybolur.")
        _rapor("TC — yanlış birleştirme", birlesik_kayitlari)


if __name__ == "__main__":
    main(*sys.argv[1:])
