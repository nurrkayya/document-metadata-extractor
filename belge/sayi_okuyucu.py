"""TC kimlik no ve sicil no'yu görüntüden okuyan VLM katmanı (SPEC Adım 10).

Neden gerekli
-------------
Ölçüm (SPEC 6.4) iki alanın sorununun **doğruluk değil kapsama** olduğunu
gösterdi: çıkarıcı bir değer ürettiğinde TC'de %100, sicilde %98.6 isabetli.
Sorun ürettiğinde yanılmak değil, 18 belgede TC'yi hiç üretememek.

Ve o 18 belgenin **18'inde de** `T.C. Kimlik No` etiketinin konumu
bulunabiliyor. Yani çıkarıcı alanın nerede olduğunu biliyor, yalnızca OCR
katmanı rakamları okunamaz hâlde veriyor. Bilgi sayfa görüntüsünde duruyor —
tam olarak isimdeki durum, tam olarak VLM'in işi.

Birleştirme neden isimdekinden farklı
-------------------------------------
İsimde iki okumanın **birleşimi** alınıyor, çünkü orada her iki taraf da bilgi
kaybediyordu ve hangisinin kaybettiği belgeye göre değişiyordu (SPEC 6.3).

Burada durum simetrik değil ve bu **ölçülmüş** bir asimetri: OCR bir TC
ürettiğinde 59/59 doğru. Böyle bir kaynağı model okumasıyla harmanlamak
yalnızca zarar verebilir. Bu yüzden kural basit:

    OCR bir değer ürettiyse o kalır. VLM yalnızca boş alanları doldurur.

Model çıktısı da doğrulamadan geçmeden kabul edilmez: TC checksum tutmalı,
sicil 4-5 hane olmalı (hane sayısı külliyata göre değişiyor, SPEC 2.3).
Tutmazsa alan boş kalır — uydurma değer, boş alandan çok daha zararlı.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from belge.alan_cikarici import CikarilanAlanlar, tc_gecerli
from belge.isim_okuyucu import IsimOkuyucu
from belge.pdf_okuyucu import bolge_goruntusu

TALIMAT_TC = (
    "This image is a cropped line from a scanned Turkish official document. "
    "It contains a Turkish national identity number (T.C. Kimlik No).\n"
    "Transcribe the number exactly as printed.\n"
    "Rules:\n"
    "- The number has exactly 11 digits.\n"
    "- Output ONLY the digits, with no spaces, dots or other separators.\n"
    "- Ignore any field label such as 'T.C. Kimlik No' and any leading colon.\n"
    "- Do not guess or complete missing digits.\n"
    "- If no 11-digit number is legible, output exactly: YOK"
)

TALIMAT_SICIL = (
    "This image is a cropped region from a scanned Turkish official document. "
    "It contains a trade registry number, printed either as 'DN47789' or as "
    "'32/47789'.\n"
    "Transcribe ONLY the digits that follow the 'DN' prefix or the '32/' "
    "prefix.\n"
    "Rules:\n"
    "- That number has 4 or 5 digits (older forms use 4).\n"
    "- Output ONLY those digits, nothing else.\n"
    "- Do NOT output the '32' prefix and do NOT output the letters 'DN'.\n"
    "- Do not guess or complete missing digits.\n"
    "- If no such number is legible, output exactly: YOK"
)

SADECE_RAKAM = re.compile(r"\D")


@dataclass
class OkunanSayi:
    deger: str
    ham_cikti: str


def _rakamlari_ayikla(ham: str, uzunluk: int | tuple[int, int]) -> str:
    """Model çıktısından beklenen uzunlukta rakam dizisi çeker.

    uzunluk bir aralık da olabilir: sicil no külliyata göre 4 ya da 5 hane
    (SPEC 2.3). Tam 5 dayatmak ikinci külliyatın tüm sicillerini eliyordu.
    """
    ilk_satir = ham.strip().splitlines()[0] if ham.strip() else ""
    rakamlar = SADECE_RAKAM.sub("", ilk_satir)
    if isinstance(uzunluk, tuple):
        return rakamlar if uzunluk[0] <= len(rakamlar) <= uzunluk[1] else ""
    return rakamlar if len(rakamlar) == uzunluk else ""


def tc_oku(okuyucu: IsimOkuyucu, png_baytlari: bytes) -> OkunanSayi:
    ham = okuyucu.uret(TALIMAT_TC, png_baytlari, azami_belirtec=30)
    aday = _rakamlari_ayikla(ham, 11)
    # Checksum, modelin uydurduğu rakamlara karşı ücretsiz bir süzgeç.
    return OkunanSayi(deger=aday if tc_gecerli(aday) else "", ham_cikti=ham)


def sicil_oku(okuyucu: IsimOkuyucu, png_baytlari: bytes) -> OkunanSayi:
    ham = okuyucu.uret(TALIMAT_SICIL, png_baytlari, azami_belirtec=30)
    return OkunanSayi(deger=_rakamlari_ayikla(ham, (4, 5)), ham_cikti=ham)


# `DN` kelimesinin ölçülen konumu: 32/32 belgede 1. sayfa, üst kenardan
# %3.2–13.3 arası, %94'ü sol üst çeyrekte. Pay bırakarak üst %22 alınır.
SERIT_ORANI = 0.22

TALIMAT_SERIT = (
    "This image is the top strip of a scanned Turkish official form. "
    "Somewhere in it there is a registry number printed as the letters 'DN' "
    "followed immediately by digits, for example DN1234.\n"
    "Transcribe ONLY the digits that follow 'DN'.\n"
    "Rules:\n"
    "- Output ONLY those digits, nothing else. No letters, no spaces.\n"
    "- The number has 4 or 5 digits.\n"
    "- Do NOT output any other number on the page (dates, document numbers, "
    "amounts, addresses).\n"
    "- If you cannot find 'DN' followed by digits, output exactly: YOK"
)


def serit_oku(okuyucu: IsimOkuyucu, pdf_yolu: Path | str) -> OkunanSayi:
    """1. sayfanın üst şeridinden sicil no okur — koordinat gerekmez.

    `DN` metin katmanında bulunamadığında tek yol bu. Konum tahmin değil,
    ölçüm: örneklemin tamamında 1. sayfanın üst şeridinde çıktı.

    Ölçülen sonuç: ikinci külliyatta 16 örtüşen vakada OCR ile **sıfır
    çelişki**, kapsama %40'tan %82'ye. İlk külliyatta OCR'ın son rakamı
    düşürdüğü 5 çekişmeli belgenin **5'inde de** doğru değeri verdi.

    Tam sayfa vermekten kaçınılır: ölçümde tam sayfa %70 isabet verip
    3 uydurma üretmişti. Şerit dar olduğu için harf başına düşen çözünürlük
    yüksek kalıyor.
    """
    import pymupdf

    with pymupdf.open(Path(pdf_yolu)) as belge:
        sayfa = belge[0]
        kirpma = pymupdf.Rect(
            sayfa.rect.x0, sayfa.rect.y0,
            sayfa.rect.x1, sayfa.rect.y0 + sayfa.rect.height * SERIT_ORANI,
        )
        png = sayfa.get_pixmap(dpi=300, clip=kirpma).tobytes("png")

    ham = okuyucu.uret(TALIMAT_SERIT, png, azami_belirtec=20)
    ilk = ham.strip().splitlines()[0] if ham.strip() else ""
    rakamlar = SADECE_RAKAM.sub("", ilk)
    return OkunanSayi(deger=rakamlar if 4 <= len(rakamlar) <= 5 else "", ham_cikti=ham)


def tamamla(
    okuyucu: IsimOkuyucu,
    pdf_yolu: Path | str,
    sonuc: CikarilanAlanlar,
) -> CikarilanAlanlar:
    """OCR'ın boş bıraktığı `tc_no` / `sicil_no` alanlarını VLM ile doldurur.

    Dolu alanlara dokunulmaz (bkz. modül başlığı: OCR ürettiğinde isabeti
    ölçülmüş şekilde çok yüksek). Yalnızca boş alanlar ve yalnızca çıkarıcının
    koordinat verebildiği yerler için model çağrılır — koordinat yoksa model
    tüm sayfaya bakmak zorunda kalır ki bu hem yavaş hem daha hatalı.
    """
    if not sonuc.tc_no and sonuc.tc_kutusu and sonuc.tc_sayfa:
        png = bolge_goruntusu(pdf_yolu, sonuc.tc_sayfa, sonuc.tc_kutusu, dpi=300)
        okunan = tc_oku(okuyucu, png)
        if okunan.deger:
            sonuc.tc_no = okunan.deger
            sonuc.uyarilar.append("tc_no VLM'den okundu")

    if not sonuc.sicil_no:
        if sonuc.sicil_kutusu and sonuc.sicil_sayfa:
            png = bolge_goruntusu(pdf_yolu, sonuc.sicil_sayfa, sonuc.sicil_kutusu, dpi=300)
            okunan = sicil_oku(okuyucu, png)
            kaynak = "kirpma"
        else:
            # DN kelimesi metinde yok: koordinat üretilemiyor. Geometrik
            # şeride düşülür — konum ölçüldü, tahmin değil (bkz. serit_oku).
            okunan = serit_oku(okuyucu, pdf_yolu)
            kaynak = "serit"
        if okunan.deger:
            sonuc.sicil_no = okunan.deger
            sonuc.uyarilar.append(f"sicil_no VLM'den okundu ({kaynak})")

    return sonuc
