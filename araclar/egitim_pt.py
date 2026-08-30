"""Faz 4: PyTorch + Hugging Face (transformers/peft) ile LoRA fine-tune.

    .venv/bin/python araclar/egitim_pt.py

mlx-vlm'in LoRA eğitimi bu sistemde güvenilmez çıktı (NaN/bozuk sayılar,
tekrarlanamaz sonuçlar — bkz. staj-gunlugu.md). PyTorch + Hugging Face
(transformers, peft) çok daha olgun ve yaygın kullanılan bir yığın; aynı
işi (Qwen2-VL-2B-Instruct'ı LoRA ile ince ayar) bununla deniyoruz.

Hem dil hem GÖRME katmanları hedefleniyor (mlx-vlm'de görme eğitimi
--train-vision ile deniyordu ama çöküyordu). Görme eğitilmeden bu görev
(el yazısı okuma) zaten iyileşemez — SPEC'te ölçülen bulgu.

Veri: egitim_seti_elyazisi/egitim_seti.csv + goruntuler/ (altin_set_elyazisi.py
ile aynı format). Yalnız dolu kayıtlar, yalnız normal boyuttaki (tam sayfa
yedek olmayan) görüntüler kullanılır.

Her N adımda bir LoRA adaptörü kaydedilir (egitim_seti_elyazisi/pt_adapters/).
Hiçbir ağ çağrısı model indirmesi dışında yapılmaz; kişisel veri hiçbir yere
gönderilmez.
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import araclar._kok  # noqa: F401

import torch
from PIL import Image
from peft import LoraConfig, get_peft_model
from transformers import AutoProcessor

from belge.isim_okuyucu import TALIMAT

HEDEF = Path("egitim_seti_elyazisi")
VARSAYILAN_MODEL = "Qwen/Qwen2-VL-2B-Instruct"
AZAMI_YUKSEKLIK = 300  # tam-sayfa yedek kırpmaları hariç tut


def _model_sinifi(model_id: str):
    """Model ailesine göre doğru transformers sınıfını döner.

    Qwen3-VL ile Qwen2-VL farklı sınıflar (8B/4B üretim modeli ailesi
    Qwen3-VL, ilk denediğimiz küçük model Qwen2-VL) — yanlış sınıfla
    yükleme sessizce yanlış mimariye zorlar (bkz. commit geçmişi).
    """
    if "qwen3-vl" in model_id.lower():
        from transformers import Qwen3VLForConditionalGeneration

        return Qwen3VLForConditionalGeneration
    from transformers import Qwen2VLForConditionalGeneration

    return Qwen2VLForConditionalGeneration

VARSAYILAN_EPOCH = 3
VARSAYILAN_LR = 5e-6
KAYIT_ARALIGI = 20  # kaç adımda bir adaptör kaydedilir


def _kayitlari_oku(min_sira: int = 0) -> list[tuple[Path, str]]:
    """min_sira: yalnız bu sıradan BÜYÜK kayıtlar (devam eğitimi için —
    zaten eğitilmiş adaptörün üstüne yalnız YENİ örnekleri gösterme)."""
    with (HEDEF / "egitim_seti.csv").open(encoding="utf-8") as f:
        satirlar = [s for s in csv.DictReader(f) if s["DOGRU_ISIM"].strip()]
    ornekler = []
    for s in satirlar:
        if int(s["sira"]) <= min_sira:
            continue
        yol = HEDEF / "goruntuler" / f"{int(s['sira']):03d}.png"
        if not yol.exists():
            continue
        with Image.open(yol) as im:
            if im.height > AZAMI_YUKSEKLIK:
                continue
        ornekler.append((yol, s["DOGRU_ISIM"].strip()))
    return ornekler


def main(
    epoch: str | int = VARSAYILAN_EPOCH,
    lr: str | float = VARSAYILAN_LR,
    model_id: str = VARSAYILAN_MODEL,
    baslangic_adaptor: str | None = None,
    min_sira: str | int = 0,
) -> None:
    """baslangic_adaptor: verilirse sıfırdan değil, bu adaptörün üstüne
    devam eğitimi yapılır (LoRA yeniden ilklendirilmez).
    min_sira: yalnız bu sıradan büyük kayıtları göster — devam eğitiminde
    zaten görülmüş eski örnekleri tekrar göstermemek için."""
    epoch, lr, min_sira = int(epoch), float(lr), int(min_sira)
    device = "mps" if torch.backends.mps.is_available() else "cpu"
    print(f"cihaz: {device}  model: {model_id}"
          + (f"  devam: {baslangic_adaptor}" if baslangic_adaptor else ""))

    ornekler = _kayitlari_oku(min_sira)
    print(f"{len(ornekler)} örnek (tam-sayfa yedekleri hariç, sira>{min_sira})")
    if not ornekler:
        print("Eğitim örneği yok, önce egitim_seti_elyazisi.py ile veri hazırlayın.")
        return

    # Model + öğrenme hızı başına ayrı kayıt klasörü — farklı denemelerin
    # kontrol noktaları birbirinin üstüne yazmasın (bir kez oldu, bkz.
    # commit geçmişi). Devam eğitimi de ayrıca ayrı alt klasöre yazar.
    cikti = HEDEF / "pt_adapters" / model_id.split("/")[-1] / f"lr{lr:.0e}"
    if baslangic_adaptor:
        cikti = cikti / "devam"

    print("model yükleniyor...")
    model_sinifi = _model_sinifi(model_id)
    model = model_sinifi.from_pretrained(model_id, dtype=torch.bfloat16)
    processor = AutoProcessor.from_pretrained(model_id)
    model = model.to(device)
    # 16 GB'lık makinede hem dil hem görme katmanlarını eğitmek bellek
    # sınırına çok yaklaşıyordu (17.73/18.13 GB, çöktü). Gradient checkpoint
    # aktivasyonları saklamak yerine geri yayılımda yeniden hesaplıyor —
    # bellek tasarrufu, biraz daha yavaş.
    model.gradient_checkpointing_enable()
    model.enable_input_require_grads()

    if baslangic_adaptor:
        from peft import PeftModel

        model = PeftModel.from_pretrained(model, baslangic_adaptor, is_trainable=True)
    else:
        lora_config = LoraConfig(
            r=8, lora_alpha=16, lora_dropout=0.0,
            target_modules=["q_proj", "k_proj", "v_proj", "o_proj", "qkv", "proj", "fc1", "fc2"],
            task_type="CAUSAL_LM",
        )
        model = get_peft_model(model, lora_config)
    model.print_trainable_parameters()
    model.train()

    optimizer = torch.optim.AdamW(model.parameters(), lr=lr)

    cikti.mkdir(parents=True, exist_ok=True)
    adim = 0
    toplam_adim = epoch * len(ornekler)
    for tur in range(1, epoch + 1):
        for yol, isim in ornekler:
            adim += 1
            img = Image.open(yol).convert("RGB")
            mesajlar = [
                {"role": "user", "content": [{"type": "image"}, {"type": "text", "text": TALIMAT}]},
                {"role": "assistant", "content": [{"type": "text", "text": isim}]},
            ]
            metin = processor.apply_chat_template(mesajlar, tokenize=False)
            girdi = processor(text=[metin], images=[img], return_tensors="pt", padding=True).to(device)
            girdi["labels"] = girdi["input_ids"].clone()

            optimizer.zero_grad()
            sonuc = model(**girdi)
            kayip = sonuc.loss
            kayip.backward()
            optimizer.step()

            if adim % 5 == 0 or adim == 1:
                print(f"tur {tur}/{epoch}  adım {adim}/{toplam_adim}  kayıp={kayip.item():.4f}")

            if adim % KAYIT_ARALIGI == 0:
                yol_kayit = cikti / f"adim_{adim:04d}"
                model.save_pretrained(str(yol_kayit))
                print(f"  kaydedildi: {yol_kayit}")

    yol_kayit = cikti / f"adim_{adim:04d}_son"
    model.save_pretrained(str(yol_kayit))
    print(f"\nEğitim bitti. Son kayıt: {yol_kayit}")


if __name__ == "__main__":
    main(*sys.argv[1:])
