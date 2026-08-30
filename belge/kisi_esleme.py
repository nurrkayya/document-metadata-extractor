"""İsimle kişi eşleştirme — TC bulunamayan belgelerde ÖNERİ üretir, karar vermez.

Neden karar vermez, yalnızca önerir
------------------------------------
Bu projede tekrar eden ilke: sessiz yanlış, boş alandan çok daha pahalıdır
(SPEC 6.4, 6.5, R1 — sözlük reddi, MURAK/MURAT vakası). İsim eşleştirmesi bu
ilkeyi TC'den daha ağır çiğneme riski taşır:

  - Türkçe isimler BENZERSİZ DEĞİL. Aynı ad-soyad birden fazla gerçek kişiye
    ait olabilir. TC'de ucuz bir doğrulama var (checksum); isimde yok.
  - Bu belgeler resmi sicil kaydı taşıyor. Yanlış kişiye TC/sicil no
    iliştirmek — uyarı yazılsa bile — birinin kimlik bilgisini başka bir
    gerçek kişinin dosyasına sessizce yazmak demek.

Bu yüzden bu modül KARAR ÜRETMEZ, yalnızca insanın önündeki seçenekleri
daraltan bir ÖNERİ döner. Otomatik atama hiçbir çağıran kodda yapılmamalı;
öneri yalnızca `bolunmeli/` / `dogrulanmali/` kuyruklarında, insanın
onaylaması gereken bir alan olarak gösterilir (SPEC 6.12'deki "öneri model,
karar insan" deseninin devamı).
"""

from __future__ import annotations

from dataclasses import dataclass

from belge.alan_cikarici import katla, mesafe
from belge.isim_okuyucu import normalize

AZAMI_ISIM_MESAFESI = 2


@dataclass
class EslesmeOnerisi:
    anahtar: str
    isim: str
    mesafe: int
    belirsiz: bool = False


def kisi_esleme_onerisi(
    ocr_isim: str,
    person_data: dict[str, list[dict]],
    azami_mesafe: int = AZAMI_ISIM_MESAFESI,
) -> EslesmeOnerisi | None:
    hedef = katla(normalize(ocr_isim).replace(" ", ""))
    if not hedef or len(hedef) < 5:
        return None

    adaylar: list[tuple[int, str, str]] = []
    for anahtar, kayitlar in person_data.items():
        aday = katla(anahtar.replace("_", ""))
        d = mesafe(hedef, aday)
        if d <= azami_mesafe:
            insan_isim = kayitlar[0].get("isim", anahtar) if kayitlar else anahtar
            adaylar.append((d, anahtar, insan_isim))

    if not adaylar:
        return None

    adaylar.sort(key=lambda a: a[0])
    en_iyi_mesafe = adaylar[0][0]
    en_iyiler = [a for a in adaylar if a[0] == en_iyi_mesafe]
    farkli_kisi = len({a[1] for a in en_iyiler}) > 1

    d, anahtar, insan_isim = en_iyiler[0]
    return EslesmeOnerisi(anahtar=anahtar, isim=insan_isim, mesafe=d, belirsiz=farkli_kisi)