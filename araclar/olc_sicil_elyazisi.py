"""El yazısı külliyatında sicil no okuma ölçümü (SPEC Adım 13).

    .venv/bin/python araclar/olc_sicil_elyazisi.py

Neden ayrı ele alınıyor
-----------------------
Sicil no, isimden üç bakımdan kolay:
  - MATBU: yapıştırılmış etiket üzerinde basılı, el yazısı değil
  - SABİT KONUM: 32/32 belgede 1. sayfada, üst kenardan %3-13 arasında,
    %94'ü sol üst çeyrekte (ölçüldü)
  - ÇAPRAZ DOĞRULANABİLİR: numaralar belge sırasıyla ilişkili

Bu yüzden OCR'ın DN'i görmediği belgelerde bile GEOMETRİK kırpma yapılabilir:
etiket aramaya gerek yok, sayfanın üst şeridi kırpılır.

Doğrulama kaynağı
-----------------
Altın sette sicil için insan girdisi henüz yok. Ama belgelerin bir kısmında
OCR metinden DN'i okuyabiliyor; bu, VLM okumasından tamamen BAĞIMSIZ bir
kaynak. İkisi uyuşuyorsa ikisinin de doğru olma olasılığı çok yüksek.
Uyuşmuyorsa hangisinin yanıldığı bilinmez — o vakalar ayrı raporlanır.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import araclar._kok  # noqa: F401

import csv
import json
import re
import sys
from pathlib import Path

import pymupdf  # noqa: E402

from belge.alan_cikarici import DESEN_DN  # noqa: E402
from olc_elyazisi import HEDEF, KAYNAK, Onbellek  # noqa: E402

# Ölçülen konum: y0 %3.2-13.3. Pay bırakarak üst %22.
SERIT_ORANI = 0.22

TALIMAT_DN = (
    "This image is the top strip of a scanned Turkish official form from the "
    "1980s. Somewhere in it there is a registry number printed as the letters "
    "'DN' followed immediately by digits, for example DN1234.\n"
    "Transcribe ONLY the digits that follow 'DN'.\n"
    "Rules:\n"
    "- Output ONLY those digits, nothing else. No letters, no spaces.\n"
    "- The number usually has 4 digits, sometimes 3 or 5.\n"
    "- Do NOT output any other number on the page (dates, document numbers, "
    "amounts, addresses).\n"
    "- If you cannot find 'DN' followed by digits, output exactly: YOK"
)


def serit(yol: Path) -> bytes:
    with pymupdf.open(yol) as belge:
        sayfa = belge[0]
        r = pymupdf.Rect(sayfa.rect.x0, sayfa.rect.y0,
                         sayfa.rect.x1, sayfa.rect.y0 + sayfa.rect.height * SERIT_ORANI)
        return sayfa.get_pixmap(dpi=300, clip=r).tobytes("png")


def main() -> None:
    from belge.isim_okuyucu import IsimOkuyucu, argv_model, secilen_model

    altin = list(csv.DictReader((HEDEF / "altin_set.csv").open(encoding="utf-8")))
    tah = json.loads((HEDEF / "_tahminler.json").read_text(encoding="utf-8"))
    model = secilen_model(argv_model())
    onb = Onbellek()
    print(f"{len(altin)} belge, model yükleniyor ({model})...")
    onb.gercek = IsimOkuyucu(model)

    uyusan = celisen = ocr_yok_vlm_var = ikisi_yok = 0
    celisenler, uretilenler = [], []
    for s in altin:
        yol = KAYNAK / tah[s["sira"]]["kaynak_dosya"]
        with pymupdf.open(yol) as b:
            tam = "\n".join(p.get_text() for p in b)
        ocr = set(DESEN_DN.findall(tam))
        ocr_deger = ocr.pop() if len(ocr) == 1 else ""

        ham = onb.uret(TALIMAT_DN, serit(yol), azami_belirtec=20)
        ilk = ham.strip().splitlines()[0] if ham.strip() else ""
        vlm = re.sub(r"\D", "", ilk)
        vlm = vlm if 3 <= len(vlm) <= 5 else ""

        if ocr_deger and vlm:
            if ocr_deger == vlm:
                uyusan += 1
            else:
                celisen += 1
                celisenler.append((s["sira"], len(ocr_deger), len(vlm)))
        elif vlm and not ocr_deger:
            ocr_yok_vlm_var += 1
        elif not vlm:
            ikisi_yok += 1
        if vlm:
            uretilenler.append((s["sira"], vlm))

    onb.kaydet()
    n = len(altin)
    print(f"yeni model çağrısı: {onb.cagri}\n")
    print(f"{n} belgede geometrik şerit + VLM:")
    print(f"  OCR ve VLM UYUŞUYOR        : {uyusan:>3}   <- iki bağımsız kaynak doğruladı")
    print(f"  OCR ve VLM ÇELİŞİYOR       : {celisen:>3}   {celisenler}")
    print(f"  OCR bulamadı, VLM okudu    : {ocr_yok_vlm_var:>3}   <- asıl kazanç, doğrulanmamış")
    print(f"  VLM de okuyamadı           : {ikisi_yok:>3}")
    print(f"\n  VLM kapsaması: {len(uretilenler)}/{n} (%{100*len(uretilenler)/n:.0f})")
    ocr_kaps = sum(1 for s in altin
                   if len(set(DESEN_DN.findall("\n".join(
                       p.get_text() for p in pymupdf.open(KAYNAK / tah[s["sira"]]["kaynak_dosya"]))))) == 1)
    print(f"  OCR kapsaması: {ocr_kaps}/{n} (%{100*ocr_kaps/n:.0f})")


if __name__ == "__main__":
    main()
