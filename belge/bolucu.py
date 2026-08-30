"""Yanlış birleştirilmiş belgeleri sayfa sahiplerine ayırır (SPEC Adım 11, R8).

Bazı PDF'ler iki ayrı kişinin evrakını taşıyor (13/288, SPEC R8). Belge tek
isimle arşivlenirse ikinci kişi sessizce kaybolur.

Sayfa sahipliği nasıl belirleniyor
----------------------------------
Her sayfa için sırayla:

1. `T.C. Kimlik No` etiketinin sağındaki değer (en güvenilir — etiketli)
2. Etiket bulunup değer okunamadıysa o bölge VLM'e verilir (Adım 10 altyapısı)
3. Hâlâ yoksa sayfadaki **etiketsiz** geçerli TC'ler aranır; sayfada tam bir
   tane varsa o kabul edilir

3. adım ölçümle eklendi: ikinci kişinin sayfası çoğu zaman etiketli bir TC
alanı taşımıyor (nüfus fotokopisi, e-devlet çıktısı). Yalnız 1. ve 2. adımla
6 işaretli belgenin 3'ünde ikinci kişi hiç görünmüyordu; 3. adımla 4'e çıktı.

Neden her belge bölünmüyor
--------------------------
Ölçüm iki farklı kusur türü olduğunu gösterdi ve tek kural ikisine de uymuyor:

  bölüm birleşmesi  — A'nın evrakı bitiyor, B'ninki başlıyor. Harita `AAABBB`
                      biçiminde iki bitişik blok veriyor, sınır belli.
  araya giren sayfa — B'ye ait tek bir sayfa A'nın evrakının ortasında.
                      Harita `AAABAAA` veriyor. Bu durumda bilinmeyen
                      sayfaların kime ait olduğu belirsiz: ileri yayma B'nin
                      bölümünü olduğundan büyük gösteriyor.

**Yalnız birinci durum otomatik bölünür.** İkincisinde bölme yapılmaz, belge
elle incelenmek üzere işaretlenir. Gerekçe ölçülmüş bir ilke: yanlış bölmek
hiç bölmemekten kötü — A'nın sayfalarını B'nin adıyla arşivlemek, sessiz
kaybın yerine sessiz bozulma koyar.

Bilinmeyen (?) sayfaların bloklara dahil edilmesi
--------------------------------------------------
Etiketsiz/boş sayfalar (tür EK — mühür, imza, boş arka yüz) bir kişinin
evrakının doğal parçasıdır ve komşu bilinen sahipten **miras alınır**
(ileri doldurma, baştaki boşluklar için geri doldurma). Bu doldurulmuş harita
yalnızca blok sayısını belirlemek için kullanılır; `plan.harita` alanı
kullanıcıya gösterilecek ham hâliyle (doldurulmamış) kalır.

Şüpheli türdeki (SAYFA_TURU_SUPHELI) sayfalar bu mirasa hiç girmez — onlar
için fonksiyon zaten daha önce elle-incele kararıyla döner.
"""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass, field
from pathlib import Path

import pymupdf

from belge.alan_cikarici import (
    DESEN_11_HANE,
    ETIKET_TC,
    etiket_degeri,
    gecerli_tcler,
    isim_makul_mu,
    tc_gecerli,
    resmi_belge_gostergesi_var_mi,
)
from belge.isim_okuyucu import normalize as _isim_normalize

BELIRSIZ = "?"


@dataclass
class BolmePlani:
    """Bir belgenin sayfalarının kimlere ait olduğu ve bölünüp bölünemeyeceği."""

    harita: str # "AAABBB" - A birincil sahip, B ikinci kişi, ? bilinmiyor
    birincil: str = ""
    ikincil: str = ""
    bolunebilir: bool = False
    gerekce: str = ""
    sayfa_turleri: list[str] = field(default_factory=list)
    bloklar: list[tuple[str, int, int]] = field(default_factory=list) # (kim, ilk, son) 1'den
    # Sayfa sayfa okunan TC (boş = bilinmiyor). Web atamasında A/B/C ayrımı için.
    sayfa_tcler: list[str] = field(default_factory=list)

# Yeni sabitler
SAYFA_TURU_SAHIPLI = "sahipli"   # TC bulundu ya da resmi alanları var
SAYFA_TURU_EK = "ek"             # metin yok/çok az -> pul/mühür, öncekine miras
SAYFA_TURU_SUPHELI = "supheli"   # metin var AMA resmi hiçbir gösterge yok

SUPHELI_METIN_ESIGI = 40  # bu karakterin üstü "pul" değil, gerçek içeriktir

def _sayfa_turu(sayfa: pymupdf.Page, tc_bulundu: bool) -> str:
    if tc_bulundu:
        return SAYFA_TURU_SAHIPLI
    if resmi_belge_gostergesi_var_mi(sayfa):
        return SAYFA_TURU_SAHIPLI  # TC yok ama form devam ediyor, normal ek
    if len(sayfa.get_text().strip()) <= SUPHELI_METIN_ESIGI:
        return SAYFA_TURU_EK
    return SAYFA_TURU_SUPHELI


def _sayfa_tcsi(
    belge: pymupdf.Document,
    indeks: int,
    pdf_yolu: Path | str,
    okuyucu: object | None,
) -> str:
    sayfa = belge[indeks]
    ham, kutu = etiket_degeri(sayfa, ETIKET_TC)
    eslesme = DESEN_11_HANE.search(re.sub(r"\D", "", ham))
    if eslesme and tc_gecerli(eslesme.group()):
        return eslesme.group()

    if kutu is not None and okuyucu is not None:
        from belge.pdf_okuyucu import bolge_goruntusu
        from belge.sayi_okuyucu import tc_oku

        okunan = tc_oku(okuyucu, bolge_goruntusu(pdf_yolu, indeks + 1, kutu, dpi=300))
        if okunan.deger:
            return okunan.deger

    # Etiketsiz serbest arama — yalnız sayfada TEK bir geçerli TC varsa.
    # Birden fazlaysa hangisinin sayfanın sahibi olduğu belirsiz, susulur.
    serbest = gecerli_tcler(sayfa.get_text())
    return serbest.pop() if len(serbest) == 1 else ""

def _sayfa_ismi(
    belge: pymupdf.Document,
    indeks: int,
    pdf_yolu: Path | str,
    okuyucu: object | None,
) -> str:
    """Sayfadaki 'Adı Soyadı' değerini normalize edip döndürür.

    TC bulunamayan sayfalarda sahiplik kararına ikinci sinyal sağlar.
    """
    from belge.alan_cikarici import ETIKET_AD

    sayfa = belge[indeks]
    ham, kutu = etiket_degeri(sayfa, ETIKET_AD)
    if ham and isim_makul_mu(ham):
        temiz = re.sub(r"[^A-Za-zÇĞİÖŞÜçğıöşü ]", "", ham).strip()
        if temiz:
            return _isim_normalize(temiz)
    if kutu is not None and okuyucu is not None:
        from belge.isim_okuyucu import kirpma_oku
        okunan = kirpma_oku(okuyucu, pdf_yolu, indeks + 1, kutu)
        if okunan.isim:
            return _isim_normalize(okunan.isim)
    return ""


def _isim_eslesir(a: str, b: str, esik: float = 0.88) -> bool:
    """OCR/VLM farklarına rağmen aynı kişi mi (fuzzy karşılaştırma)."""
    if not a or not b:
        return False
    return a == b or difflib.SequenceMatcher(None, a, b).ratio() >= esik


def _bloklara_ayir(etiketler: list[str]) -> list[tuple[str, int, int]]:
    """Ardışık aynı etiketleri (kim, ilk_sayfa, son_sayfa) bloklarına toplar."""
    bloklar: list[tuple[str, int, int]] = []
    for no, c in enumerate(etiketler, start=1):
        if bloklar and bloklar[-1][0] == c:
            bloklar[-1] = (c, bloklar[-1][1], no)
        else:
            bloklar.append((c, no, no))
    return bloklar

def plan_cikar(pdf_yolu, birincil_tc, okuyucu=None, birincil_isim="") -> BolmePlani:
    from belge.pdf_okuyucu import bos_sayfa_mi

    birincil_isim_n = _isim_normalize(birincil_isim) if birincil_isim else ""
    ikincil_isim_n = ""

    with pymupdf.open(Path(pdf_yolu)) as belge:
        sahipler, turler, isim_sahipler = [], [], []
        for i in range(len(belge)):
            sayfa = belge[i]
            if bos_sayfa_mi(sayfa):
                sahipler.append(None)
                isim_sahipler.append("")
                turler.append(SAYFA_TURU_EK)
                continue
            tc = _sayfa_tcsi(belge, i, pdf_yolu, okuyucu) or None
            isim = _sayfa_ismi(belge, i, pdf_yolu, okuyucu)
            isim_sahipler.append(isim)
            sahipler.append(tc)
            turler.append(_sayfa_turu(sayfa, tc_bulundu=bool(tc)))

    # EK (boş/pul/mühür) sayfalar komşu sahipli sayfadan miras alır.
    sahipler = _miras_doldur(sahipler, turler)

    # TC bulunamayan sayfalarda isim ikinci sinyaldir.
    if birincil_isim_n:
        for i, (tc, isim) in enumerate(zip(sahipler, isim_sahipler)):
            if tc or not isim or turler[i] == SAYFA_TURU_SUPHELI:
                continue
            if _isim_eslesir(isim, birincil_isim_n):
                sahipler[i] = birincil_tc
            elif not ikincil_isim_n:
                ikincil_isim_n = isim
                sahipler[i] = f"isim:{isim}"
            elif _isim_eslesir(isim, ikincil_isim_n):
                sahipler[i] = f"isim:{ikincil_isim_n}"

    digerleri = [t for t in sahipler if t and t != birincil_tc]
    ikincil = digerleri[0] if digerleri else ""
    harita = "".join("A" if t == birincil_tc else "B" if t else BELIRSIZ for t in sahipler)

    plan = BolmePlani(harita=harita, birincil=birincil_tc, ikincil=ikincil,
                      sayfa_tcler=[t or "" for t in sahipler],
                      sayfa_turleri=turler)

    # GÜVENLİK: şüpheli sayfa varsa otomatik bölünmez — miras mantığı
    # yalnız "ek" (pul) sayfalar için güvenli, "supheli" için değil.
    supheli = [i + 1 for i, t in enumerate(turler) if t == SAYFA_TURU_SUPHELI]
    if supheli:
        plan.gerekce = (
            f"{len(supheli)} sayfada resmi gösterge yok, muhtemelen ilgisiz "
            f"(sayfa {supheli}) — elle incelenmeli"
        )
        return plan  # bolunebilir=False

    if not ikincil:
        plan.gerekce = "ikinci kişi bulunamadı"
        return plan

    # Bilinmeyen (EK türü) sayfaları komşu bilinen sahipten miras aldır:
    # önce ileri doldurma (bir önceki sahip), sonra baştaki kalan boşluklar
    # için geri doldurma. Yalnız blok SAYISINI belirlemek için kullanılır;
    # plan.harita alanı kullanıcıya gösterilen ham hâliyle kalır.
    dolu: list[str | None] = list(sahipler)
    son_bilinen: str | None = None
    for i, t in enumerate(dolu):
        if t is None:
            dolu[i] = son_bilinen
        else:
            son_bilinen = t
    ilk_bilinen: str | None = None
    for i in range(len(dolu) - 1, -1, -1):
        if dolu[i] is None:
            dolu[i] = ilk_bilinen
        else:
            ilk_bilinen = dolu[i]

    etiketli = [
        "A" if t == birincil_tc else ("B" if t == ikincil else BELIRSIZ)
        for t in dolu
    ]
    bloklar = _bloklara_ayir(etiketli)

    # Yalnız İKİ bitişik blok (A...A B...B ya da B...B A...A) otomatik
    # bölünür: "bölüm birleşmesi". Üç ve üzeri blok (ör. A-B-A) "araya giren
    # sayfa" demektir — bilinmeyen sayfaların kime ait olduğu belirsiz kalır,
    # ileri/geri doldurma ikinci kişinin bölümünü olduğundan büyük gösterir.
    if len(bloklar) != 2:
        plan.gerekce = (
            f"sayfalar arası geçiş {len(bloklar)} bloklu, iki bitişik bölüm "
            "değil (araya giren sayfa) — elle incelenmeli"
        )
        return plan

    plan.bloklar = bloklar
    plan.bolunebilir = True
    plan.gerekce = "iki bitişik bölüm tespit edildi (bölüm birleşmesi)"
    return plan


def uygula(
    pdf_yolu: Path | str,
    plan: BolmePlani,
    hedef_klasor: Path | str,
    kuru_calistir: bool = True,
) -> list[Path]:
    """Planı uygular: her blok için ayrı PDF yazar.

    kuru_calistir açıkken hiçbir dosya yazılmaz, yalnızca üretilecek yollar
    döndürülür. Bölme geri alması zor bir işlem (SPEC Adım 7), bu yüzden
    varsayılan kuru.
    """
    if not plan.bolunebilir:
        raise ValueError(f"plan bölünebilir değil: {plan.gerekce}")

    kaynak = Path(pdf_yolu)
    hedef = Path(hedef_klasor)
    yazilanlar = []
    for kim, ilk, son in plan.bloklar:
        cikti = hedef / f"{kaynak.stem}_bolum{ilk}-{son}_{kim}.pdf"
        yazilanlar.append(cikti)
        if kuru_calistir:
            continue
        hedef.mkdir(parents=True, exist_ok=True)
        with pymupdf.open(kaynak) as belge, pymupdf.open() as yeni:
            yeni.insert_pdf(belge, from_page=ilk - 1, to_page=son - 1)
            yeni.save(cikti)
    return yazilanlar


def plan_sozluge(plan: BolmePlani) -> dict:
    """Bölme planını web API'nin beklediği JSON-uyumlu sözlüğe çevirir.

    `harita` / `bloklar` otomatik kuralın çıktısıdır (A/B/?). `sayfalar` ise
    her sayfanın TC'sini taşır; üçüncü kişi web'de C olarak gösterilebilir.
    """
    tcler = list(plan.sayfa_tcler or [])
    if len(tcler) < len(plan.harita):
        tcler.extend("" for _ in range(len(plan.harita) - len(tcler)))
    harfler = _tc_harfleri(tcler, plan.birincil)
    sayfalar = []
    for i, harf in enumerate(plan.harita):
        tc = tcler[i]
        if not tc:
            if harf == "A":
                tc = plan.birincil
            elif harf == "B":
                tc = plan.ikincil
        sayfalar.append({
            "no": i + 1,
            "sahip": harfler[i] if i < len(harfler) else harf,
            "oneri": harf,
            "tc": tc,
        })
    return {
        "harita": plan.harita,
        "birincil": plan.birincil,
        "ikincil": plan.ikincil,
        "bolunebilir": plan.bolunebilir,
        "gerekce": plan.gerekce,
        "bloklar": [{"kim": k, "ilk": i, "son": s} for k, i, s in plan.bloklar],
        "sayfalar": sayfalar,
    }


def _tc_harfleri(tcler: list[str], birincil: str) -> list[str]:
    """Benzersiz TC'lere A, B, C… atar. Boş sayfa '?'."""
    tablo: dict[str, str] = {}
    if birincil:
        tablo[birincil] = "A"
    harf_iter = iter("BCDEFGH")
    sonuc = []
    for t in tcler:
        if not t:
            sonuc.append("?")
            continue
        if t not in tablo:
            tablo[t] = "A" if not tablo else next(harf_iter, "?")
        sonuc.append(tablo[t])
    return sonuc


def plan_gruplari(harita: str) -> dict[str, list[int]]:
    """Haritadaki her harf için 1-tabanlı sayfa numaraları (sıra korunur)."""
    gruplar: dict[str, list[int]] = {}
    for no, harf in enumerate(harita, start=1):
        gruplar.setdefault(harf, []).append(no)
    return gruplar


def kullanici_plani(
    harita: str,
    birincil: str = "",
    ikincil: str = "",
) -> BolmePlani:
    """Operatör atamasından plan. X = bu belgeye ait değil, ? = atanmamış.

    Otomatik AAABBB kuralı uygulanmaz: insan onayladıysa bölünebilir.
    Atanmamış (`?`) sayfa varsa bölünemez — sessiz tahmin yok.
    """
    if not harita:
        raise ValueError("harita boş")
    izinli = set("ABCDEFGHX?")
    bozuk = {c for c in harita if c not in izinli}
    if bozuk:
        raise ValueError(f"geçersiz harita karakteri: {''.join(sorted(bozuk))}")

    plan = BolmePlani(harita=harita, birincil=birincil, ikincil=ikincil)
    bloklar: list[tuple[str, int, int]] = []
    for no, c in enumerate(harita, start=1):
        if bloklar and bloklar[-1][0] == c:
            bloklar[-1] = (c, bloklar[-1][1], no)
        else:
            bloklar.append((c, no, no))
    plan.bloklar = bloklar

    if "?" in harita:
        plan.gerekce = "atanmamış sayfa var — önce her sayfayı atayın"
        return plan
    kisiler = {c for c in harita if c not in ("X", "?")}
    if not kisiler:
        plan.gerekce = "hiçbir sayfa bir kişiye atanmadı"
        return plan
    plan.bolunebilir = True
    plan.gerekce = "kullanıcı onayı"
    return plan


def sayfalari_yaz(
    pdf_yolu: Path | str,
    gruplar: dict[str, list[int]],
    hedef_klasor: Path | str,
    kok_ad: str | None = None,
    kuru_calistir: bool = True,
) -> dict[str, Path]:
    """Sayfaları kişiye göre (bitişik olmak zorunda değil) ayrı PDF'lere yazar.

    `uygula` yalnız AAABBB bloklarını bilir; operatör A'nın 1 ve 5. sayfasını
    aynı kişiye verebilir. Boş gruplar atlanır. Sayfa numaraları 1-den.
    """
    kaynak = Path(pdf_yolu)
    hedef = Path(hedef_klasor)
    kok = kok_ad or kaynak.stem
    yazilanlar: dict[str, Path] = {}
    with pymupdf.open(kaynak) as belge:
        n = len(belge)
        for kim, sayfalar in gruplar.items():
            if not sayfalar:
                continue
            for no in sayfalar:
                if no < 1 or no > n:
                    raise ValueError(f"sayfa {no} yok (belge {n} sayfa)")
            cikti = hedef / f"{kok}_{kim}.pdf"
            yazilanlar[kim] = cikti
            if kuru_calistir:
                continue
            hedef.mkdir(parents=True, exist_ok=True)
            with pymupdf.open() as yeni:
                for no in sayfalar:
                    yeni.insert_pdf(belge, from_page=no - 1, to_page=no - 1)
                yeni.save(cikti)
    return yazilanlar

def _miras_doldur(sahipler: list[str | None], turler: list[str]) -> list[str | None]:
    """EK (boş/pul/mühür) sayfaların sahibini komşu SAHİPLİ sayfadan doldurur.

    Yalnız SAYFA_TURU_EK sayfalar içindir: bunlar kimlik bilgisi taşımıyor,
    dolayısıyla tek başlarına bir bloğu BÖLMEMELİ. Önce önceki sahipli
    sayfadan miras alınır (ek sayfa akışta genelde bir önceki evrakın
    devamıdır); belgenin başındaysa sonraki sahipli sayfadan alınır.

    SUPHELI sayfalar buraya girmez — onlar ayrı bir güvenlik kontrolünden
    geçip bilinçli olarak elle incelemeye düşüyor, bu davranış değişmiyor.
    """
    doldurulmus = list(sahipler)
    son_sahip: str | None = None
    for i, (sahip, tur) in enumerate(zip(doldurulmus, turler)):
        if tur == SAYFA_TURU_EK and sahip is None:
            doldurulmus[i] = son_sahip
        elif sahip is not None:
            son_sahip = sahip
    sonraki_sahip: str | None = None
    for i in range(len(doldurulmus) - 1, -1, -1):
        if turler[i] == SAYFA_TURU_EK and doldurulmus[i] is None:
            doldurulmus[i] = sonraki_sahip
        elif doldurulmus[i] is not None:
            sonraki_sahip = doldurulmus[i]
    return doldurulmus