"""PDF okuma: metin katmanı tespiti ve sayfa görüntüsü üretimi.

Bu modül modelden tamamen bağımsızdır. Tek işi bir PDF'i işlenebilir hale
getirmektir:

  - Metin katmanı var mı? (dijital PDF mi, taranmış mı)
  - Taranmışsa sayfaları 300 DPI görüntüye çevirmek

SPEC.md bölüm 5.2'deki iki yollu akışın giriş noktasıdır.
"""


from __future__ import annotations

import statistics
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

import pymupdf

VARSAYILAN_DPI = 300

# "Silik" duplex artefaktı: beyaz oranı boş eşiğini (0.98) geçmese de
# karşı yüzden sızan bir mühür/yazı hayaleti olabilir. Gerçek içerik
# (mürekkep + kağıt) yüksek varyans üretir; sızıntı izi düşük varyanslı,
# tekdüze bir gri değerdir.
DUPLEX_BEYAZ_ALT_SINIR = 0.90
DUPLEX_STD_ESIGI = 5.0

# Bir sayfada bu kadar karakter varsa metin katmanı kullanılabilir sayılır.
# Taranmış sayfalar genelde 0-20 karakter döndürür (tarayıcı artıkları,
# gömülü başlık/altbilgi). Dijital PDF'lerde bir form sayfası bile
# yüzlerce karakter içerir.
METIN_KATMANI_ESIGI = 100

# Boş sayfa: az metin VE neredeyse beyaz. İkisi birden şart — nüfus
# fotokopisi az metinli olabilir ama fotoğraf yüzünden beyaz değildir.
BOS_METIN_ESIGI = 20
BOS_BEYAZ_ORANI = 0.98
BOS_BEYAZ_ESIK = 250


@dataclass(frozen=True)
class PdfBilgi:
    """Bir PDF'in hangi yoldan işleneceğine karar vermek için gereken bilgi."""

    yol: Path
    sayfa_sayisi: int
    sayfa_karakter_sayilari: list[int]

    @property
    def ortanca_karakter(self) -> float:
        """Sayfa başına ortanca karakter sayısı.

        Ortalama yerine ortanca kullanılır: tek bir metin dolu kapak sayfası
        taranmış bir belgeyi 'dijital' göstermesin.
        """
        if not self.sayfa_karakter_sayilari:
            return 0.0
        return statistics.median(self.sayfa_karakter_sayilari)

    @property
    def metinli_sayfa_sayisi(self) -> int:
        return sum(1 for n in self.sayfa_karakter_sayilari if n >= METIN_KATMANI_ESIGI)

    @property
    def metin_katmani_var(self) -> bool:
        """True ise dijital PDF yolu, False ise görüntü (VLM) yolu."""
        return self.ortanca_karakter >= METIN_KATMANI_ESIGI


def incele(pdf_yolu: Path | str) -> PdfBilgi:
    """PDF'i açmadan içeriğini değiştirmeden inceler; hangi yola gideceğini söyler."""
    yol = Path(pdf_yolu)
    with pymupdf.open(yol) as belge:
        karakter_sayilari = [len(sayfa.get_text().strip()) for sayfa in belge]
    return PdfBilgi(
        yol=yol,
        sayfa_sayisi=len(karakter_sayilari),
        sayfa_karakter_sayilari=karakter_sayilari,
    )


def sayfa_yogunluk_metrikleri(sayfa: pymupdf.Page, dpi: int = 36) -> tuple[float, float]:
    """(beyaz_orani, piksel_std) döndürür — boş/silik kararının temeli."""
    pix = sayfa.get_pixmap(dpi=dpi, colorspace=pymupdf.csGRAY)
    ornek = pix.samples
    if not ornek:
        return 1.0, 0.0
    n = len(ornek)
    beyaz = sum(1 for b in ornek if b >= BOS_BEYAZ_ESIK) / n
    ortalama = sum(ornek) / n
    varyans = sum((b - ortalama) ** 2 for b in ornek) / n
    return beyaz, varyans ** 0.5


def bos_sayfa_mi(sayfa: pymupdf.Page, dpi: int = 36) -> bool:
    """Az metin VE (gerçekten beyaz YA DA silik/tekdüze duplex artefaktı).

    İki ayrı boşluk biçimi:
      1. gerçek beyaz sayfa   -> beyaz oranı >= 0.98
      2. silik duplex izi     -> beyaz oranı 0.90-0.98 arası AMA std çok
                                  düşük (yazı değil, hayalet)

    Deskew/CLAHE yok; sayfa PDF'den silinmez, yalnız VLM/OCR akışından
    atlanır (SPEC 5.4).
    """
    if len(sayfa.get_text().strip()) > BOS_METIN_ESIGI:
        return False
    beyaz, std = sayfa_yogunluk_metrikleri(sayfa, dpi=dpi)
    if beyaz >= BOS_BEYAZ_ORANI:
        return True
    return beyaz >= DUPLEX_BEYAZ_ALT_SINIR and std <= DUPLEX_STD_ESIGI


def sayfa_metinleri(pdf_yolu: Path | str) -> list[str]:
    """Dijital PDF yolu için: her sayfanın metin katmanını döndürür."""
    with pymupdf.open(Path(pdf_yolu)) as belge:
        return [sayfa.get_text() for sayfa in belge]


def sayfa_goruntuleri(
    pdf_yolu: Path | str,
    dpi: int = VARSAYILAN_DPI,
) -> Iterator[tuple[int, bytes]]:
    """Görüntü yolu için: sayfaları PNG olarak tek tek üretir.

    Üreteç (generator) olarak yazılmıştır: 300 DPI'da bir sayfa ~25 MB yer
    kaplar, 288 belgenin tamamı belleğe sığmaz. Model her sayfayı sırayla
    okuyacağı için sayfa sayfa üretmek hem yeterli hem de bellek kullanımını
    sabit tutar.

    Döndürür: (sayfa_no, png_baytlari) — sayfa_no 1'den başlar.

    SPEC.md 5.4: ön işleme (deskew/kontrast) uygulanmaz, ham görüntü verilir.
    """
    with pymupdf.open(Path(pdf_yolu)) as belge:
        for sayfa_indeksi, sayfa in enumerate(belge, start=1):
            pixmap = sayfa.get_pixmap(dpi=dpi)
            yield sayfa_indeksi, pixmap.tobytes("png")


def bolge_goruntusu(
    pdf_yolu: Path | str,
    sayfa_no: int,
    kutu: tuple[float, float, float, float],
    dpi: int = VARSAYILAN_DPI,
    pay: float = 6.0,
) -> bytes:
    """Sayfanın belirli bir bölgesini PNG olarak kırpar.

    OCR bize isim satırının koordinatını veriyor (SPEC 2.2). Modele tüm sayfa
    yerine yalnızca o satırı vermek işi kolaylaştırır ve doğruluğu artırır.

    kutu    : PDF punto biriminde (x0, y0, x1, y1) — alan_cikarici'den gelir
    sayfa_no: 1'den başlar
    pay     : kutunun çevresine eklenen punto cinsinden boşluk. OCR kutusu
              harflerin tepesini/altını kırpabildiği için biraz pay bırakılır.
    """
    with pymupdf.open(Path(pdf_yolu)) as belge:
        sayfa = belge[sayfa_no - 1]
        x0, y0, x1, y1 = kutu
        kirpma = pymupdf.Rect(x0 - pay, y0 - pay, x1 + pay, y1 + pay)
        kirpma = kirpma & sayfa.rect  # sayfa dışına taşmasın
        pixmap = sayfa.get_pixmap(dpi=dpi, clip=kirpma)
        return pixmap.tobytes("png")


def goruntuleri_kaydet(
    pdf_yolu: Path | str,
    hedef_klasor: Path | str,
    dpi: int = VARSAYILAN_DPI,
) -> list[Path]:
    """Sayfa görüntülerini diske yazar. Gözle kontrol ve hata ayıklama içindir.

    Normal akışta kullanılmaz — model görüntüleri bellekten alır.
    """
    hedef = Path(hedef_klasor)
    hedef.mkdir(parents=True, exist_ok=True)
    kok = Path(pdf_yolu).stem

    yazilanlar = []
    for sayfa_no, png in sayfa_goruntuleri(pdf_yolu, dpi=dpi):
        cikti = hedef / f"{kok}_sayfa_{sayfa_no:03d}.png"
        cikti.write_bytes(png)
        yazilanlar.append(cikti)
    return yazilanlar
