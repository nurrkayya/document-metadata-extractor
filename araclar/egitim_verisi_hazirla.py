"""Eğitim setinden (egitim_seti_elyazisi/) mlx-vlm LoRA veri seti üretir (Faz 4).

    .venv/bin/python araclar/egitim_verisi_hazirla.py

Yalnız DOLU (isim girilmiş) kayıtlar kullanılır. Boş bırakılan kayıtlar İKİ
farklı sebepten olabilir — gerçekten okunamayan el yazısı, ya da yanlış
alan/görevli bloğu yakalanmış kırpma — ve CSV bu ikisini ayırt etmiyor.
İkincisini "YOK" olarak öğretmek modele yanlış sinyal verir (görüntüde
okunabilir bir metin varken "okunamadı" demeyi öğretir), bu yüzden boş
kayıtlar eğitime hiç girmez.

Talimat metni belge/isim_okuyucu.py:TALIMAT ile BİREBİR aynıdır — eğitim ve
çalışma zamanı istemi tutarsızsa fine-tune'un öğrettiği davranış üretimde
tetiklenmeyebilir.

Çıktı tamamen yerel: `datasets` kütüphanesinin parquet biçimiyle,
egitim_seti_elyazisi/mlx_veri/{train,val} altına yazılır. Hiçbir ağ
çağrısı yapılmaz, Hub'a hiçbir şey yüklenmez (kişisel veri kurum dışına
çıkamaz kuralı — bkz. README).
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import araclar._kok  # noqa: F401

import csv
import random

from PIL import Image  # noqa: E402

from belge.isim_okuyucu import TALIMAT  # noqa: E402

HEDEF = Path("egitim_seti_elyazisi")
CALISMA = HEDEF / "egitim_seti.csv"
GORUNTU = HEDEF / "goruntuler"
CIKTI = HEDEF / "mlx_veri"

VAL_ORANI = 0.1
TOHUM = 7
AZAMI_YUKSEKLIK = 300  # px; bunun üstü tam-sayfa yedek kırpması sayılır


def _kayitlari_oku() -> list[dict]:
    with CALISMA.open(encoding="utf-8") as f:
        satirlar = list(csv.DictReader(f))
    return [s for s in satirlar if s.get("DOGRU_ISIM", "").strip()]


def _mesaj_uret(isim: str) -> list[dict]:
    return [
        {
            "role": "user",
            "content": [{"type": "image"}, {"type": "text", "text": TALIMAT}],
        },
        {
            "role": "assistant",
            "content": [{"type": "text", "text": isim}],
        },
    ]


def main() -> None:
    from datasets import Dataset

    dolu = _kayitlari_oku()
    if not dolu:
        print(f"{CALISMA} boş ya da hiç dolu kayıt yok. Önce doldur.html'i doldurup birleştirin.")
        return

    random.Random(TOHUM).shuffle(dolu)
    n_val = max(1, round(len(dolu) * VAL_ORANI))
    val_satirlar, train_satirlar = dolu[:n_val], dolu[n_val:]

    for ad, satirlar in (("train", train_satirlar), ("val", val_satirlar)):
        kayitlar = {"images": [], "messages": []}
        buyuk_atlanan = 0
        for s in satirlar:
            goruntu_yolu = GORUNTU / f"{int(s['sira']):03d}.png"
            if not goruntu_yolu.exists():
                print(f"  uyarı: {goruntu_yolu} yok, {s['sira']} atlandı")
                continue
            img = Image.open(goruntu_yolu).convert("RGB")
            # Etiket bulunamayınca tam sayfa gösterilir (SPEC: "tam sayfa
            # gösterilecek"); bu görüntüler normal isim satırı kırpmasından
            # (~100-130px yükseklik) çok daha büyük (~1300-1600px). Farklı
            # boyutlardaki görüntüler görsel kodlayıcıda sayısal taşmaya
            # (NaN) sebep olduğu ölçüldü — eğitimden hariç tutuluyor.
            if img.height > AZAMI_YUKSEKLIK:
                buyuk_atlanan += 1
                continue
            kayitlar["images"].append([img])
            kayitlar["messages"].append(_mesaj_uret(s["DOGRU_ISIM"].strip()))
        if buyuk_atlanan:
            print(f"  {buyuk_atlanan} tam-sayfa/aşırı büyük görüntü hariç tutuldu ({ad})")

        ds = Dataset.from_dict(kayitlar)
        cikti_dizin = CIKTI / ad
        cikti_dizin.mkdir(parents=True, exist_ok=True)
        ds.to_parquet(str(cikti_dizin / "veri.parquet"))
        print(f"{ad}: {len(kayitlar['images'])} örnek -> {cikti_dizin}")

    print(f"\nToplam: {len(dolu)} dolu kayıttan {len(train_satirlar)} train + {len(val_satirlar)} val üretildi.")
    print("Hiçbir ağ çağrısı yapılmadı, Hub'a bir şey yüklenmedi.")


if __name__ == "__main__":
    main()
