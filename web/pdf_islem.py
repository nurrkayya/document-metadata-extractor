"""Sayfa birleştirme, taşıma, ayırma ve küçük resim — pymupdf.

İş mantığı (kim arşivlenir, R8 tespiti) burada yok; yalnız PDF sayfaları.
"""

from __future__ import annotations

from pathlib import Path

import pymupdf

ONIZLEME_DPI = 72
YAKIN_DPI = 140


def sayfa_sayisi(pdf_yolu: Path | str) -> int:
    with pymupdf.open(Path(pdf_yolu)) as belge:
        return len(belge)


def kucuk_resim(pdf_yolu: Path | str, sayfa_no: int, dpi: int = ONIZLEME_DPI) -> bytes:
    """1-tabanlı sayfa PNG. dpi düşük tutulur — base64 gömmek sayfayı şişirir."""
    with pymupdf.open(Path(pdf_yolu)) as belge:
        if sayfa_no < 1 or sayfa_no > len(belge):
            raise ValueError(f"sayfa {sayfa_no} yok")
        return belge[sayfa_no - 1].get_pixmap(dpi=dpi).tobytes("png")


def isim_kirpma(pdf_yolu: Path | str) -> bytes | None:
    """Adı Soyadı satırı; yoksa ilk sayfanın düşük çözünürlüklü hali."""
    from belge.alan_cikarici import ETIKET_AD, etiket_kutusu, satir_kutusu

    with pymupdf.open(Path(pdf_yolu)) as belge:
        for sayfa in belge:
            kutu = etiket_kutusu(sayfa, ETIKET_AD)
            if kutu is None:
                continue
            r = pymupdf.Rect(*satir_kutusu(sayfa, kutu)) & sayfa.rect
            return sayfa.get_pixmap(dpi=200, clip=r).tobytes("png")
        if len(belge) == 0:
            return None
        return belge[0].get_pixmap(dpi=ONIZLEME_DPI).tobytes("png")


def pdfleri_birlestir(
    parcalar: list[tuple[Path, list[int]]],
    hedef: Path,
) -> Path:
    """(pdf, 1-tabanlı sayfa noları) sırasıyla yeni PDF. Boş liste = tüm sayfalar."""
    if not parcalar:
        raise ValueError("birleştirilecek parça yok")
    hedef = Path(hedef)
    hedef.parent.mkdir(parents=True, exist_ok=True)
    with pymupdf.open() as yeni:
        for yol, sayfalar in parcalar:
            with pymupdf.open(Path(yol)) as belge:
                if not sayfalar:
                    yeni.insert_pdf(belge)
                    continue
                for no in sayfalar:
                    if no < 1 or no > len(belge):
                        raise ValueError(f"{Path(yol).name}: sayfa {no} yok")
                    yeni.insert_pdf(belge, from_page=no - 1, to_page=no - 1)
        if len(yeni) == 0:
            raise ValueError("birleşen belgede sayfa kalmadı")
        yeni.save(hedef)
    return hedef


def sayfalari_cikar(pdf_yolu: Path | str, sayfalar: list[int], hedef: Path) -> Path:
    """Belirtilen sayfaları çıkarıp kalanı yazar. Tümü çıkarsa hata."""
    atla = set(sayfalar)
    hedef = Path(hedef)
    hedef.parent.mkdir(parents=True, exist_ok=True)
    with pymupdf.open(Path(pdf_yolu)) as belge, pymupdf.open() as yeni:
        for i in range(len(belge)):
            if (i + 1) not in atla:
                yeni.insert_pdf(belge, from_page=i, to_page=i)
        if len(yeni) == 0:
            raise ValueError("belgede sayfa kalmaz")
        yeni.save(hedef)
    return hedef


def sayfalari_al(pdf_yolu: Path | str, sayfalar: list[int], hedef: Path) -> Path:
    """Yalnız seçilen sayfaları (verilen sırada) yeni PDF'e yazar."""
    if not sayfalar:
        raise ValueError("alınacak sayfa yok")
    hedef = Path(hedef)
    hedef.parent.mkdir(parents=True, exist_ok=True)
    with pymupdf.open(Path(pdf_yolu)) as belge, pymupdf.open() as yeni:
        for no in sayfalar:
            if no < 1 or no > len(belge):
                raise ValueError(f"sayfa {no} yok")
            yeni.insert_pdf(belge, from_page=no - 1, to_page=no - 1)
        yeni.save(hedef)
    return hedef
