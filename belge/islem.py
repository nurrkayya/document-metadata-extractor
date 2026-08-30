"""Belge işleme çekirdeği — CLI ve web aynı çıkarımı kullanır.

Dosya taşımaz; arşiv kararı çağırana aittir (`belge.arsiv.Arsiv`).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from belge.alan_cikarici import cikar, gecerli_tcler, sicil_adaylari
from belge.arsiv import Arsiv, Eylem
from belge.yollar import AYRILDI

# kaynak dosya adı -> kaç sayfa uzlaştı (CLI raporu)
_UZLASMA: dict[str, int] = {}


@dataclass
class Sonuc:
    """Arşive yazılacak nihai alanlar."""

    isim: str = ""
    tc_no: str = ""
    sicil_no: str = ""
    # Kaç sayfa aynı ismi verdi. 0 = uzlaşma yok (tek sayfadan okundu).
    uzlasma: int = 0
    # Tek sayfada OCR (metin katmanı) ile VLM (görsel okuma) birbirinden
    # BAĞIMSIZ aynı ismi verdiyse True. Çok sayfalı uzlaşmaya alternatif
    # bir güven sinyali: SPEC'teki "iki bağımsız kaynak aynı derse güven"
    # ilkesinin sayfalar arası değil, yöntemler arası (OCR vs VLM) hâli.
    capraz_dogrulandi: bool = False
    uyarilar: list[str] = field(default_factory=list)


def belge_analiz(
    pdf_yolu: Path, okuyucu: object | None = None
) -> tuple[Sonuc, bool, object | None]:
    """Tek belge: alanlar, çok kimlik, bölme planı. Dosya taşımaz.

    Web ve CLI aynı çıkarımı kullansın diye. Arşiv kararı çağırana aittir.
    Çok kimlikli ama birincil kimlik yoksa plan None kalır — sessiz tek kişi olmaz.
    """
    from belge.bolucu import plan_cikar
    from belge.isim_okuyucu import normalize

    yol = Path(pdf_yolu)
    sonuc = _alanlari_topla(yol, okuyucu)
    cok = _cok_kimlikli(yol)
    plan = None
    if cok and (sonuc.tc_no or sonuc.isim):
        birincil = sonuc.tc_no or f"isim:{normalize(sonuc.isim)}"
        plan = plan_cikar(yol, birincil, okuyucu, birincil_isim=sonuc.isim)
    return sonuc, cok, plan


def kova_oner(sonuc: Sonuc, cok_kimlik: bool, kati: bool = True) -> str:
    """Web kuyruk kovası. Varsayılan katı: belirsizler incelemeye düşer.

    Güven iki yoldan biriyle kurulabilir: birden fazla sayfa aynı ismi
    verdi (`uzlasma >= 2`) YA DA tek sayfada OCR ile VLM birbirinden
    bağımsız aynı ismi verdi (`capraz_dogrulandi`).
    """
    if cok_kimlik:
        return "incele"
    if not (sonuc.isim or "").strip():
        return "okunamadi"
    if kati and sonuc.uzlasma < 2 and not sonuc.capraz_dogrulandi:
        return "incele"
    return "arsivlenecek"


def cok_kimlik_gerekce(sonuc: Sonuc, person_data: dict[str, list[dict]] | None = None) -> str:
    """TC bulunamayan çok kimlikli belge için gerekçe metni.

    person_data verilirse isimle eşleşme ÖNERİSİ üretir (öneri, karar değil).
    """
    if person_data:
        from belge.kisi_esleme import kisi_esleme_onerisi

        oneri = kisi_esleme_onerisi(sonuc.isim, person_data) if sonuc.isim else None
        if oneri is not None:
            if oneri.belirsiz:
                return (
                    f"TC yok, isimle birden fazla FARKLI kişi eşleşti "
                    f"(en yakını '{oneri.isim}') — otomatik seçilmedi, elle karar gerekli"
                )
            return (
                f"TC yok — isme göre '{oneri.isim}' ÖNERİLİYOR (mesafe {oneri.mesafe}). "
                "OTOMATİK ATANMADI, elle onay gerekli."
            )
    return "çok kimlikli, birincil TC çıkarılamadı"


def _cok_kimlikli(pdf_yolu: Path) -> bool:
    """Belgede birden fazla kişi izi var mı? (SPEC R8 tespiti)"""
    import pymupdf

    with pymupdf.open(pdf_yolu) as belge:
        metin = "".join(s.get_text() for s in belge)
    return len(gecerli_tcler(metin)) > 1 or len(sicil_adaylari(metin)) > 1


def _alanlari_topla(pdf_yolu: Path, okuyucu: object | None) -> Sonuc:
    alanlar = cikar(pdf_yolu)

    if okuyucu is None:
        return Sonuc(
            isim=alanlar.isim_bosluksuz,
            tc_no=alanlar.tc_no,
            sicil_no=alanlar.sicil_no,
            uyarilar=list(alanlar.uyarilar),
        )

    from belge.isim_okuyucu import coklu_sayfa_oku, kirpma_oku, normalize
    from belge.isim_okuyucu import isaretsizlestir
    from belge.sayi_okuyucu import tamamla

    alanlar = tamamla(okuyucu, pdf_yolu, alanlar)

    coklu = coklu_sayfa_oku(okuyucu, pdf_yolu)
    if coklu.uzlasan:
        return Sonuc(
            isim=_birlestir_guvenli(coklu.uzlasan, alanlar.isim_bosluksuz),
            tc_no=alanlar.tc_no,
            sicil_no=alanlar.sicil_no,
            uzlasma=coklu.uzlasma_adedi,
            uyarilar=list(alanlar.uyarilar),
        )

    def _capraz_mi(vlm_isim: str) -> bool:
        # OCR'ın metin katmanından okuduğu ham isim ile VLM'nin (sayfa
        # taraması veya yedek kırpma — hangi yoldan geldiği fark etmez)
        # okuduğu isim, işaret farkları dışında birbirini tutuyorsa iki
        # bağımsız yöntem aynı şeyi söylüyor demektir — sayfalar arası
        # uzlaşamasa da bu tek başına bir güven sinyali.
        return bool(vlm_isim) and bool(alanlar.isim_bosluksuz) and (
            isaretsizlestir(normalize(vlm_isim))
            == isaretsizlestir(normalize(alanlar.isim_bosluksuz))
        )

    capraz = False
    if coklu.cogunluk:
        isim = _birlestir_guvenli(coklu.cogunluk, alanlar.isim_bosluksuz)
        capraz = _capraz_mi(coklu.cogunluk)
    elif alanlar.isim_sayfa:
        kutu = _yedek_kirpma_kutusu(pdf_yolu, alanlar.isim_sayfa)
        if kutu:
            vlm = kirpma_oku(okuyucu, pdf_yolu, alanlar.isim_sayfa, kutu)
            isim = _birlestir_guvenli(vlm.isim, alanlar.isim_bosluksuz)
            capraz = _capraz_mi(vlm.isim)
        else:
            isim = alanlar.isim_bosluksuz
    else:
        isim = alanlar.isim_bosluksuz

    return Sonuc(
        isim=isim,
        tc_no=alanlar.tc_no,
        sicil_no=alanlar.sicil_no,
        uzlasma=coklu.uzlasma_adedi,
        capraz_dogrulandi=capraz,
        uyarilar=(
            list(alanlar.uyarilar) + ["isim OCR ve VLM'de bağımsız eşleşti (çapraz doğrulama)"]
            if capraz
            else list(alanlar.uyarilar)
        ),
    )


def _kati_uyarisi(vlm: bool, kati: bool, kuru: bool) -> str:
    """--vlm --uygula ve --kati yoksa uyarı. Girdi beklemez."""
    if vlm and not kati and not kuru:
        return (
            "Uyarı: --vlm --uygula, --kati yok. Uzlaşmayan okumalar da arşive girecek. "
            "İkinci külliyat için --kati önerilir."
        )
    return ""


def _yedek_kirpma_kutusu(
    pdf_yolu: Path, sayfa_no: int
) -> tuple[float, float, float, float] | None:
    """Etiket çıpalı kırpma kutusu. Değer kutusu kullanılmaz."""
    import pymupdf

    from belge.alan_cikarici import ETIKET_AD, ETIKET_AD_YEDEK, etiket_kutusu, satir_kutusu

    with pymupdf.open(pdf_yolu) as belge:
        sayfa = belge[sayfa_no - 1]
        ek = etiket_kutusu(sayfa, ETIKET_AD) or etiket_kutusu(sayfa, ETIKET_AD_YEDEK)
        if ek is None:
            return None
        return satir_kutusu(sayfa, ek)


def _birlestir_guvenli(vlm: str, ocr: str) -> str:
    """OCR isim değilse birleştirme yapılmaz; VLM/uzlaşan ham kalır."""
    from belge.alan_cikarici import isim_makul_mu
    from belge.isim_okuyucu import birlestir

    if isim_makul_mu(ocr):
        return birlestir(vlm, ocr)
    return vlm


def _birlestirme_isle(yol: Path, arsiv: Arsiv, okuyucu) -> tuple:
    """Yanlış birleştirilmiş belge: bölünebiliyorsa ayrılır, yoksa işaretlenir."""
    from belge.bolucu import plan_cikar, uygula

    sonuc = _alanlari_topla(yol, okuyucu)
    if not sonuc.tc_no:
        gerekce = cok_kimlik_gerekce(sonuc, arsiv.person_data)
        return arsiv.bolunmeli_planla(yol, gerekce), None

    plan = plan_cikar(yol, sonuc.tc_no, okuyucu)
    if not plan.bolunebilir:
        return arsiv.bolunmeli_planla(yol, plan.gerekce), None

    parcalar = uygula(yol, plan, arsiv.kok / AYRILDI, kuru_calistir=True)
    asil_hedef = arsiv.kok / AYRILDI / "asil" / yol.name
    arsiv.isaretle(yol, yol.name)
    return Eylem(
        kaynak=yol,
        tur=AYRILDI,
        hedef=asil_hedef,
        not_=f"{len(parcalar)} parçaya ayrılacak: "
        + ", ".join(f"s{b[1]}-{b[2]}({b[0]})" for b in plan.bloklar),
        uyarilar=list(sonuc.uyarilar),
    ), plan


def _bolmeleri_uygula(bolunecek) -> list[Path]:
    """Parçaları yazar ve yollarını döndürür."""
    from belge.bolucu import uygula

    parcalar: list[Path] = []
    for asil_yol, plan in bolunecek:
        parcalar += uygula(asil_yol, plan, asil_yol.parent.parent, kuru_calistir=False)
    return parcalar
