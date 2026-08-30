"""PyTorch/peft fine-tune sonucunu altın setle ölçer (Faz 4).

    .venv/bin/python araclar/olc_fine_tune_pt.py [adaptor_yolu] [model_id]

adaptor_yolu verilmezse yalnız taban model ölçülür. model_id verilmezse
varsayılan (Qwen2-VL-2B-Instruct). Aynı 40 belgelik altın setle
(`olc_elyazisi.py` ile aynı veri).
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import araclar._kok  # noqa: F401

import csv
import json
from collections import Counter

sys.path.insert(0, str(Path(__file__).resolve().parent))
from olc_elyazisi import HEDEF, KAYNAK  # noqa: E402
from egitim_pt import VARSAYILAN_MODEL, _model_sinifi  # noqa: E402


def main(adaptor_yolu: str | None = None, model_id: str = VARSAYILAN_MODEL) -> None:
    import torch
    import pymupdf
    from PIL import Image
    from transformers import AutoProcessor

    from belge.alan_cikarici import ETIKET_AD, etiket_kutusu, satir_kutusu
    from belge.isim_okuyucu import TALIMAT, normalize

    device = "mps" if torch.backends.mps.is_available() else "cpu"
    etiket = f"{model_id}" + (f" + adaptör({adaptor_yolu})" if adaptor_yolu else " (taban)")
    print(f"model yükleniyor: {etiket} (cihaz={device})...")

    model_sinifi = _model_sinifi(model_id)
    model = model_sinifi.from_pretrained(model_id, dtype=torch.bfloat16)
    processor = AutoProcessor.from_pretrained(model_id)
    if adaptor_yolu:
        from peft import PeftModel
        model = PeftModel.from_pretrained(model, adaptor_yolu)
    model = model.to(device)
    model.eval()

    altin = [s for s in csv.DictReader((HEDEF / "altin_set.csv").open(encoding="utf-8"))
             if s["DOGRU_ISIM"].strip()]
    tah = json.loads((HEDEF / "_tahminler.json").read_text(encoding="utf-8"))

    sayim = {"el": Counter(), "daktilo": Counter(), "matbu": Counter(), "toplam": Counter()}
    for satir in altin:
        dogru = normalize(satir["DOGRU_ISIM"])
        tur = satir["TUR"] or "?"
        yol = KAYNAK / tah[satir["sira"]]["kaynak_dosya"]

        okunan = ""
        with pymupdf.open(yol) as belge:
            for sayfa in belge:
                kutu = etiket_kutusu(sayfa, ETIKET_AD)
                if kutu is None:
                    continue
                kirpma = pymupdf.Rect(*satir_kutusu(sayfa, kutu)) & sayfa.rect
                png = sayfa.get_pixmap(dpi=300, clip=kirpma).tobytes("png")
                break
            else:
                png = None

        if png is not None:
            import io
            img = Image.open(io.BytesIO(png)).convert("RGB")
            mesajlar = [{"role": "user", "content": [{"type": "image"}, {"type": "text", "text": TALIMAT}]}]
            metin = processor.apply_chat_template(mesajlar, tokenize=False, add_generation_prompt=True)
            girdi = processor(text=[metin], images=[img], return_tensors="pt").to(device)
            with torch.no_grad():
                cikti = model.generate(**girdi, max_new_tokens=40, do_sample=False)
            uretilen = cikti[0][girdi["input_ids"].shape[1]:]
            okunan = normalize(processor.decode(uretilen, skip_special_tokens=True).strip())

        k = "bos" if not okunan else ("dogru" if okunan == dogru else "yanlis")
        sayim[tur if tur in sayim else "toplam"][k] += 1
        sayim["toplam"][k] += 1

    print(f"\nSonuç — {etiket}")
    print(f"{'tür':<10}{'doğru':>8}{'yanlış':>8}{'boş':>6}{'isabet':>10}")
    for tur in ("el", "daktilo", "matbu", "toplam"):
        c = sayim[tur]
        uretilen = c["dogru"] + c["yanlis"]
        isabet = f"%{100*c['dogru']/uretilen:.0f}" if uretilen else "-"
        print(f"{tur:<10}{c['dogru']:>8}{c['yanlis']:>8}{c['bos']:>6}{isabet:>10}")


if __name__ == "__main__":
    main(*sys.argv[1:])
