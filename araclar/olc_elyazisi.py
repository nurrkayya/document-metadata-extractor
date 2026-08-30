"""El yazısı külliyatında isim doğruluğunu ölçer (SPEC Adım 12).

    .venv/bin/python araclar/olc_elyazisi.py

Doğruluk **belge türüne göre ayrı** raporlanır (el yazısı / daktilo / matbu).
Karışık bir ortalama hangi kısmın çözülüp hangisinin çözülmediğini gizler;
projenin hedefi (%90-95) özellikle el yazısı için konulmuş.

İki istem karşılaştırılır
-------------------------
Mevcut istem (`isim_okuyucu.TALIMAT`) ilk külliyat için yazıldı ve modele
"büyük harfle BASILI isim" diyor. El yazısı için bu tarif yanlış. Bir de el
yazısına uyarlanmış istem ölçülür, böylece istem uyarlamasının tek başına ne
kazandırdığı görülür.

Kırpma
------
Kırpma etikete çıpalanır (`alan_cikarici.etiket_kutusu`), değer kutusuna
değil. Değer kutusu OCR'ın gördüğü kelimelerden türer ve el yazısını OCR
görmediği için yanlış yere oturur — ölçülüp düzeltildi.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import araclar._kok  # noqa: F401

import csv
import hashlib
import json
import sys
from collections import defaultdict
from pathlib import Path

import pymupdf  # noqa: E402

from belge.alan_cikarici import ETIKET_AD, cikar, etiket_kutusu, satir_kutusu  # noqa: E402
from belge.isim_okuyucu import birlestir, normalize  # noqa: E402

HEDEF = Path("altin_set_elyazisi")
ALTIN = HEDEF / "altin_set.csv"
TAHMIN = HEDEF / "_tahminler.json"
ONBELLEK = HEDEF / "_vlm_okumalari.json"
KAYNAK = Path("ornekler")

TALIMAT_ELYAZISI = (
    "This image is a cropped line from a scanned Turkish official form from "
    "the 1980s. To the left is a printed field label; to the right is the "
    "value, which is filled in by HAND in cursive handwriting or by an old "
    "TYPEWRITER.\n"
    "Transcribe ONLY the person's full name written after the colon.\n"
    "Rules:\n"
    "- Output ONLY the name, nothing else.\n"
    "- Ignore the printed field label on the left and the dotted line.\n"
    "- The writing may be faint, slanted or joined up. Read what is actually "
    "written, letter by letter.\n"
    "- Keep Turkish letters exactly: Ç Ğ İ I Ö Ş Ü. 'İ' has a dot, 'I' does not.\n"
    "- Do NOT correct the name to a more common Turkish name. Rare and unusual "
    "names are expected; reproduce exactly what is on the paper.\n"
    "- Do not add letters that you cannot see.\n"
    "- If the name is not legible, output exactly: YOK"
)


class Onbellek:
    """Model çağrılarını görüntü+talimat hash'iyle önbelleğe alır."""

    def __init__(self, gercek=None, yol: Path | None = None):
        from belge.isim_okuyucu import onbellek_yolu

        self.yol = yol if yol is not None else onbellek_yolu(ONBELLEK)
        self.gercek = gercek
        self.kayit = json.loads(self.yol.read_text(encoding="utf-8")) if self.yol.exists() else {}
        self.cagri = 0

    def uret(self, talimat: str, png: bytes, azami_belirtec: int = 40) -> str:
        anahtar = hashlib.sha256(talimat.encode() + png).hexdigest()[:32]
        if anahtar not in self.kayit:
            if self.gercek is None:
                raise SystemExit("önbellekte yok ve model yüklenmedi")
            self.kayit[anahtar] = self.gercek.uret(talimat, png, azami_belirtec)
            self.cagri += 1
        return self.kayit[anahtar]

    def kaydet(self):
        self.yol.write_text(json.dumps(self.kayit, ensure_ascii=False, indent=2), encoding="utf-8")


def _kirpma(yol: Path) -> bytes | None:
    with pymupdf.open(yol) as belge:
        for sayfa in belge:
            kutu = etiket_kutusu(sayfa, ETIKET_AD)
            if kutu is None:
                continue
            r = pymupdf.Rect(*satir_kutusu(sayfa, kutu)) & sayfa.rect
            return sayfa.get_pixmap(dpi=300, clip=r).tobytes("png")
    return None


def main() -> None:
    with ALTIN.open(encoding="utf-8") as f:
        satirlar = [s for s in csv.DictReader(f) if s["DOGRU_ISIM"].strip()]
    tahminler = json.loads(TAHMIN.read_text(encoding="utf-8"))
    if not satirlar:
        print("Altın sette dolu cevap yok.")
        return

    from belge.isim_okuyucu import TALIMAT, IsimOkuyucu, _temizle, argv_model, secilen_model

    model = secilen_model(argv_model())
    onb = Onbellek()
    try:
        onb.uret(TALIMAT, b"deneme")  # önbellek yeterli mi
    except SystemExit:
        pass
    print(f"{len(satirlar)} belge ölçülüyor, model yükleniyor ({model})...")
    onb.gercek = IsimOkuyucu(model)

    # tur -> yontem -> [dogru, toplam]
    sayim: dict[str, dict[str, list[int]]] = defaultdict(lambda: defaultdict(lambda: [0, 0]))
    hatalar = []

    for satir in satirlar:
        sira, tur = satir["sira"], satir["TUR"] or "?"
        dogru = normalize(satir["DOGRU_ISIM"])
        yol = KAYNAK / tahminler[sira]["kaynak_dosya"]

        ocr = cikar(yol).isim_bosluksuz
        png = _kirpma(yol)
        okumalar = {"OCR": normalize(ocr)}
        if png:
            eski = _temizle(onb.uret(TALIMAT, png))
            yeni = _temizle(onb.uret(TALIMAT_ELYAZISI, png))
            okumalar["VLM (eski istem)"] = normalize(eski)
            okumalar["VLM (el yazısı istemi)"] = normalize(yeni)
            okumalar["birleşik (yeni istem+OCR)"] = normalize(birlestir(yeni, ocr))

        for yontem, okunan in okumalar.items():
            sayim[tur][yontem][1] += 1
            if okunan == dogru:
                sayim[tur][yontem][0] += 1
        if okumalar.get("VLM (el yazısı istemi)") != dogru:
            hatalar.append((sira, tur))

    onb.kaydet()

    yontemler = ["OCR", "VLM (eski istem)", "VLM (el yazısı istemi)", "birleşik (yeni istem+OCR)"]
    print(f"\nyeni model çağrısı: {onb.cagri}\n")
    print(f"{'yöntem':<28}" + "".join(f"{t:>12}" for t in ("el", "daktilo", "matbu")) + f"{'TOPLAM':>12}")
    for yontem in yontemler:
        satir = f"{yontem:<28}"
        td = tt = 0
        for tur in ("el", "daktilo", "matbu"):
            d, t = sayim[tur][yontem]
            td += d
            tt += t
            satir += f"{f'{d}/{t}':>12}" if t else f"{'-':>12}"
        satir += f"{f'{td}/{tt} (%{100*td/tt:.0f})' if tt else '-':>12}"
        print(satir)

    print(f"\nel yazısı istemiyle hatalı kalan: {len(hatalar)}")
    print(f"  sıralar: {[s for s, _ in hatalar]}")


if __name__ == "__main__":
    main()
