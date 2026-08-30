"""İsim satırını görüntüden okuyan VLM katmanı.

Neden gerekli
-------------
OCR katmanı isimlerin yarısını bozuyor (`KEMAL ŞAHİNOĞLU` → `rEMaL
şaHİNoĞru`) ve bitişik yazılanlarda boşlukları kaybediyor (`AYŞE NUR DEMİR`
→ `AYŞENURDEMİR`). Bu bilgi yalnızca sayfa görüntüsünde var.

Modele tüm sayfa verilmez: OCR bize isim satırının koordinatını veriyor, o
bölge kırpılıp verilir (SPEC bölüm 10, kaldıraç 2). Görev "bir satırdaki
büyük harfli ismi oku"ya indirgenmiş olur.

Talimat İngilizce, okunan değer Türkçe (SPEC 5.1): küçük modellerde
İngilizce talimat takibi belirgin şekilde daha güvenilir.
"""

from __future__ import annotations

import difflib
import os
import re
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

VARSAYILAN_MODEL = "mlx-community/Qwen3-VL-8B-Instruct-8bit"


def argv_model(argv: list[str] | None = None) -> str | None:
    """`--model <hf-id>` varsa kimliği döner; yoksa None.

    `isle.py` ve `araclar/olc_*` aynı kancayı kullanır. Üretim varsayılanı
    değişmez: None → `VLM_MODEL` ortamı → `VARSAYILAN_MODEL`.
    """
    argv = list(argv if argv is not None else sys.argv[1:])
    if "--model" not in argv:
        return None
    i = argv.index("--model")
    if i + 1 >= len(argv) or argv[i + 1].startswith("-"):
        raise SystemExit("--model bir Hugging Face kimliği bekler")
    return argv[i + 1]


def secilen_model(istek: str | None = None) -> str:
    """Açık istek > VLM_MODEL > varsayılan. Varsayılanı değiştirmez."""
    if istek and istek.strip():
        return istek.strip()
    ortam = os.environ.get("VLM_MODEL", "").strip()
    return ortam or VARSAYILAN_MODEL


def onbellek_yolu(varsayilan: Path, argv: list[str] | None = None) -> Path:
    """Ölçüm önbelleği: VLM_ONBELLEK > model-özel dosya > varsayılan.

    Anahtar talimat+görüntü; model yoksa başka VLM'in sonucu sessizce
    yeniden kullanılır. Varsayılan modelde mevcut dosya aynı kalır.
    """
    ortam = os.environ.get("VLM_ONBELLEK", "").strip()
    if ortam:
        return Path(ortam)
    model = secilen_model(argv_model(argv))
    if model == VARSAYILAN_MODEL:
        return varsayilan
    slug = model.replace("/", "_")
    return varsayilan.with_name(f"{varsayilan.stem}__{slug}{varsayilan.suffix}")

TALIMAT = (
    "This image is a cropped line from a scanned Turkish official document. "
    "It contains one person's full name, printed in capital letters.\n"
    "Transcribe the name exactly as printed.\n"
    "Rules:\n"
    "- Output ONLY the name, nothing else.\n"
    "- Turkish has TWO capital I letters and they are different letters:\n"
    "    'İ' has a dot on top (capital of 'i')\n"
    "    'I' has no dot (capital of 'ı')\n"
    "  Look carefully at each one and reproduce exactly what is printed.\n"
    "- Keep the other Turkish letters exactly: Ç Ğ Ö Ş Ü.\n"
    "- Keep the spacing between words as printed.\n"
    "- Do not translate, correct, or complete the name.\n"
    "- Ignore any leading colon or field label.\n"
    "- If no name is legible, output exactly: YOK"
)

# Modelin döndürebileceği fazlalıkları temizlemek için
BASTAKI_ETIKET = re.compile(r"^\s*[:\-–]\s*")
IZINLI_KARAKTER = re.compile(r"[^A-ZÇĞİIÖŞÜ ]")


@dataclass
class OkunanIsim:
    isim: str
    ham_cikti: str


def turkce_buyut(metin: str) -> str:
    """Türkçe kurallarına uyan büyük harfe çevirme.

    Python'un .upper() metodu 'i' harfini 'I' yapar, oysa Türkçe'de karşılığı
    'İ'dir. Bu ayrım isimlerde anlam taşır (noktalı İ ile noktasız I ayrı harflerdir), bu yüzden
    dönüşümden önce elle eşlenir.
    """
    return metin.replace("i", "İ").replace("ı", "I").upper()


def normalize(metin: str) -> str:
    """Karşılaştırma için sadeleştirir: büyük harf, tek boşluk, noktalama yok."""
    metin = turkce_buyut(metin.strip())
    metin = IZINLI_KARAKTER.sub("", metin)
    return re.sub(r"\s+", " ", metin).strip()


def noktasizlastir(metin: str) -> str:
    """İ/I ayrımını siler — iki okumanın harflerde uyuşup uyuşmadığını görmek için."""
    return metin.replace("İ", "I")


# Türkçe işaretli harfleri işaretsiz karşılıklarına indirger. İki okumanın
# "aynı harfleri" okuyup okumadığını, işaret farklarını yok sayarak görmek için.
ISARETSIZ = str.maketrans("ÇĞİÖŞÜ", "CGIOSU")


def isaretsizlestir(metin: str) -> str:
    return metin.translate(ISARETSIZ)


def _isaretli_mi(harf: str) -> bool:
    return isaretsizlestir(harf) != harf


def _bosluk_konumlari(metin: str) -> set[int]:
    """Kaçıncı harften sonra boşluk geldiğini döndürür."""
    konumlar = set()
    sayac = 0
    for karakter in metin:
        if karakter == " ":
            konumlar.add(sayac)
        else:
            sayac += 1
    return konumlar


def _yazimi_birlestir(vlm: str, ocr: str) -> str:
    """İki okumanın daha zengin olanını harf harf birleştirir.

    Başta "boşluklar VLM'den, işaretler OCR'dan" kuralı denendi ve ölçüldü:
    üç belgeyi düzeltirken üç belgeyi bozdu. Sebep, varsayımın yanlış
    olmasıydı — hangi tarafın hangi bilgiyi kaybettiği belgeye göre değişiyor.
    OCR `SEZAİÇOBAN` derken boşluğu, `ÖZGUR` derken işareti düşürüyor;
    VLM de aynısını başka belgelerde yapıyor.

    Doğru ilke simetrik: **her iki kayıp da olur, uydurma olmaz.** Bir tarafta
    boşluk varsa gerçekten vardır; bir tarafta işaret varsa gerçekten vardır.
    Bu yüzden ikisinin birleşimi alınır.

    Yalnızca harf dizisi (işaretsiz, boşluksuz) aynı olduğunda çağrılır,
    dolayısıyla harf sayıları eşittir.
    """
    vlm_harfler = [k for k in vlm if k != " "]
    ocr_harfler = [k for k in ocr if k != " "]
    bosluklar = _bosluk_konumlari(vlm) | _bosluk_konumlari(ocr)

    sonuc: list[str] = []
    for sira, (v, o) in enumerate(zip(vlm_harfler, ocr_harfler)):
        if sira in bosluklar and sonuc:
            sonuc.append(" ")
        if _isaretli_mi(v):
            sonuc.append(v)
        elif _isaretli_mi(o):
            sonuc.append(o)
        else:
            sonuc.append(v)
    return "".join(sonuc)


def _noktalari_aktar(vlm: str, ocr: str) -> str:
    """Hizalanan konumlarda OCR'dan VLM'e SADECE işaret ekler.

    Modelin sistematik hatası işareti düşürmek (İ→I, Ü→U), eklemek değil.
    Bu yüzden aktarım tek yönlüdür: OCR'da işaretli, VLM'de işaretsiz olan
    harfler düzeltilir; tersi yapılmaz.

    Çift yönlü denendi ve ölçüldü: iki belgeyi düzeltirken bir belgeyi
    bozuyordu (VLM'in doğru okuduğu 'İLKER'i OCR'a bakıp 'ILKER'
    yapıyordu). Tek yönlü hâli hiçbirini bozmadan ikisini düzeltiyor.

    Karşılaştırma işaretsiz hâl üzerinde yapılır: amaç harflerin hangi
    konumda eşleştiğini bulmak, işaretleri değil.
    """
    if not vlm or not ocr:
        return vlm or ocr

    eslesme = difflib.SequenceMatcher(
        None, isaretsizlestir(vlm), isaretsizlestir(ocr), autojunk=False
    )
    harfler = list(vlm)
    for etiket, i1, i2, j1, _ in eslesme.get_opcodes():
        if etiket != "equal":
            continue
        for kayma in range(i2 - i1):
            vlm_harf = harfler[i1 + kayma]
            ocr_harf = ocr[j1 + kayma]
            # Yalnızca işaretsizden işaretliye geçişe izin verilir; ters yön
            # (işaretliyi silmek) ölçümde zarar veriyordu.
            if not _isaretli_mi(vlm_harf) and isaretsizlestir(ocr_harf) == vlm_harf:
                harfler[i1 + kayma] = ocr_harf
    return "".join(harfler)


def birlestir(vlm_okumasi: str, ocr_okumasi: str) -> str:
    """VLM ve OCR okumalarını birleştirip nihai ismi üretir.

    İki durum var:

    1. Harf dizisi uzlaşıyorsa (işaret ve boşluk farkları yok sayılarak):
       iki okumanın **birleşimi** alınır. Hangi taraf boşluğu ya da işareti
       yakalamışsa o kazanır; biri diğerine tercih edilmez.

    2. Uzlaşmıyorsa: OCR harfleri bozmuş demektir, VLM esas alınır. Yine de
       kısmen hizalanan konumlarda OCR'ın işaretleri aktarılır.

    80 belgelik altın sette ölçüldü: tek başına OCR %56.2, tek başına VLM
    %80.0, bu birleştirmeyle %95.0.
    """
    vlm = normalize(vlm_okumasi)
    ocr = normalize(ocr_okumasi)
    if not vlm:
        return ocr
    if not ocr:
        return vlm

    def sadelestir(metin: str) -> str:
        return isaretsizlestir(metin).replace(" ", "")

    if sadelestir(vlm) == sadelestir(ocr):
        # Harfler uzlaşıyor: iki okumanın daha zengin hâli birleştirilir.
        return _yazimi_birlestir(vlm, ocr)
    # Uzlaşma yok — OCR harfleri bozmuş. VLM'in harfleri esas alınır, ama
    # kısmen hizalanan yerlerde OCR'ın işaretleri yine de aktarılır.
    return _noktalari_aktar(vlm, ocr)


def _temizle(ham: str) -> str:
    """Model çıktısını dosya adına dönüştürülebilir bir isme indirger."""
    metin = ham.strip().splitlines()[0] if ham.strip() else ""
    metin = BASTAKI_ETIKET.sub("", metin).strip()
    if turkce_buyut(metin) == "YOK":
        return ""
    # Belgede isimler büyük harf basılı; model küçük harf üretirse düzeltilir.
    metin = turkce_buyut(metin)
    metin = IZINLI_KARAKTER.sub("", metin)
    return re.sub(r"\s+", " ", metin).strip()


class IsimOkuyucu:
    """Modeli bir kez yükler, çok sayıda kırpma için tekrar kullanır.

    Model yüklemesi ~9 GB ve onlarca saniye sürer; her belge için yeniden
    yüklemek kabul edilemez.
    """

    def __init__(self, model_adi: str | None = None, adapter_yolu: str | None = None) -> None:
        from mlx_vlm import load
        from mlx_vlm.utils import load_config

        self.model_adi = secilen_model(model_adi)
        # adapter_yolu: Faz 4 fine-tune deneyi için geçici kanca (--model gibi,
        # üretim varsayılanını değiştirmez). LoRA eğitimi belge/isim_okuyucu.py
        # dışında araclar/egitim_verisi_hazirla.py + mlx_vlm.lora ile yapılır.
        self.model, self.processor = load(self.model_adi, adapter_path=adapter_yolu)
        self.config = load_config(self.model_adi)

    def oku(
        self,
        png_baytlari: bytes,
        ocr_ipucu: str = "",
        azami_belirtec: int = 40,
    ) -> OkunanIsim:
        """Kırpılmış isim satırını okur.

        ocr_ipucu: OCR'ın aynı satır için ürettiği metin. OCR harfleri sık
        bozuyor ama noktalı/noktasız I ayrımını çoğu zaman doğru yakalıyor —
        modelin zayıf olduğu tam nokta bu. İpucu "doğru cevap" olarak değil,
        yalnızca dikkat çekmek için verilir.

        DİKKAT: Faydası henüz kanıtlanmadı. 3 belgelik ilk denemede ipuçlu ve
        ipuçsuz sonuçlar aynı çıktı. Varsayılan olarak kapalıdır; altın set
        hazır olunca ölçülüp kalması ya da kaldırılması kararlaştırılacak.
        """
        talimat = TALIMAT
        if ocr_ipucu.strip():
            talimat += (
                "\n\nA low-quality OCR engine read this line as:\n"
                f"    {ocr_ipucu.strip()}\n"
                "That OCR output is unreliable for letter shapes, but it is "
                "often right about which I letters carry a dot. The image is "
                "the authority — use the OCR only as a hint for the dots."
            )

        ham = self.uret(talimat, png_baytlari, azami_belirtec)
        return OkunanIsim(isim=_temizle(ham), ham_cikti=ham)

    def uret(self, talimat: str, png_baytlari: bytes, azami_belirtec: int = 40) -> str:
        """Ham model çağrısı — bir görüntü, bir talimat, ham metin.

        `belge/sayi_okuyucu.py` de bunu kullanır. Model ~9 GB ve yüklemesi
        onlarca saniye sürüyor; isim ve sayı okumaları aynı örneği paylaşmak
        zorunda, bu yüzden çağrı burada ortak bir yöntemde duruyor.
        """
        from mlx_vlm import generate
        from mlx_vlm.prompt_utils import apply_chat_template

        istem = apply_chat_template(self.processor, self.config, talimat, num_images=1)

        # generate() görüntüyü dosya yolundan alıyor
        with tempfile.NamedTemporaryFile(suffix=".png", delete=True) as gecici:
            gecici.write(png_baytlari)
            gecici.flush()
            sonuc = generate(
                self.model,
                self.processor,
                istem,
                image=[gecici.name],
                max_tokens=azami_belirtec,
                temperature=0.0,  # aynı görüntü hep aynı sonucu vermeli
                verbose=False,
            )

        return sonuc.text if hasattr(sonuc, "text") else str(sonuc)


@dataclass
class CokluOkuma:
    """Bir belgenin isim satırının tüm sayfalardaki okumaları."""

    okumalar: list[str]
    uzlasan: str = ""       # en az UZLASMA_ESIGI sayfanın aynı dediği değer
    uzlasma_adedi: int = 0
    cogunluk: str = ""      # en çok tekrar eden okuma (uzlaşma olmasa da)


# Kaç sayfanın aynı demesi "uzlaşma" sayılır. 2 ölçülmüş değer: el yazısında
# %88 isabet veriyor. 3'e çıkarmak isabeti artırmıyor (%80) ama kapsamayı
# yarıya indiriyor.
UZLASMA_ESIGI = 2


def oy_birlestir(okumalar: list[str]) -> tuple[str, int]:
    """Sayfa okumalarını işaret-duyarsız gruplayıp en büyük grubu döner.

    "MAHMUT DUNDAR" ile "MAHMUT DÜNDAR" farklı yazım, aynı isim — tam
    eşleşme arayan oylama bunları ayrı sayıp uzlaşmayı kaçırıyordu (88
    belgelik altın sette ölçüldü: 5 belge "uzlaşma yok"tan "doğru
    uzlaşma"ya geçti, yeni yanlış eklenmedi). Grup temsilcisi olarak en
    çok Türkçe işaretli harf içeren okuma seçilir (altın değerler daima
    düzgün işaretli).

    Ölçüm aracı (`araclar/olc_coklu_sayfa.py`) da aynı fonksiyonu
    kullanır — üretim ile ölçümün birbirinden sapmaması için (bkz.
    `coklu_sayfa_oku` docstring'indeki azami_sayfa geçmişi).

    Temsilci karakter-pozisyonu bazlı çoğunluk oyuyla kurulur (katlama
    tek-tek harf değişimi olduğu için grup üyeleri hep aynı uzunlukta ve
    hizalı — pozisyon bazlı oy güvenli). Önceki sürüm "en çok aksanlı
    harf içeren okumayı seç" diyordu; bu, karışık durumlarda (bir kelimede
    aksan doğru bir kelimede yanlış) tüm okumayı yanlış seçebiliyordu
    (ör. 'AKIN'/'AKİN' karışıklığında gerçek çoğunluk yerine rastgele
    üye seçilmesi — 88 belgelik altın sette 3 belgede görüldü, düzeltildi).

    Döner: (temsilci, grup_büyüklüğü). okumalar boşsa ("", 0).
    """
    if not okumalar:
        return "", 0
    from collections import Counter

    gruplar: dict[str, list[str]] = {}
    for o in okumalar:
        gruplar.setdefault(isaretsizlestir(o), []).append(o)
    _, uyeler = max(gruplar.items(), key=lambda kv: len(kv[1]))
    harfler = []
    for i in range(len(uyeler[0])):
        sayim = Counter(u[i] for u in uyeler).most_common()
        azami = sayim[0][1]
        adaylar = [h for h, adet in sayim if adet == azami]
        aksanli = [h for h in adaylar if h in "ÇĞİÖŞÜ"]
        harfler.append(aksanli[0] if aksanli else adaylar[0])
    temsilci = "".join(harfler)
    return temsilci, len(uyeler)


def coklu_sayfa_oku(okuyucu, pdf_yolu, azami_sayfa: int = 50) -> CokluOkuma:
    """İsim etiketi taşıyan HER sayfayı ayrı okur ve oylar (SPEC Adım 6).

    Neden tek sayfa yetmiyor: belgelerin %81'inde isim etiketi birden fazla
    sayfada bulunuyor (ortanca 3) ve tek sayfa okumak elimizdeki bilginin
    üçte birini kullanmak demek.

    Neden uzlaşma bir güven sinyali: model tek sayfada uydurduğunda aynı
    uydurmayı başka sayfada tekrarlamıyor — her sayfada yazı farklı görünüyor.
    Doğru okuduğunda sayfalar birbirini tutuyor. Ölçüldü (el yazısı, 18 belge):
    ilk sayfa %44, çoğunluk %50, **≥2 uzlaşma %88**.

    Kırpma etikete çıpalanır (`alan_cikarici.etiket_kutusu`), değer kutusuna
    değil: el yazısını OCR görmediği için değer kutusu yanlış yere oturuyor.

    Oylama `oy_birlestir()` ile yapılır — işaret-duyarsız gruplama, gerekçesi
    orada. 88 belgelik altın sette (önbellekten, VLM'e yeni çağrı yapmadan)
    ölçüldü: bu tek değişiklik 5 belgeyi "uzlaşma yok"tan "doğru uzlaşma"ya
    taşıyor, yanlış sayısı artmıyor (26→31 doğru, 3 yanlış sabit, kapsama
    %33→%39).

    azami_sayfa: 6'ydı — 1. külliyat (ortalama 9.1 sayfa/belge) için ölçülmüş
    bir sınırdı (SPEC 6.11). Kontrol edildi: 88 belgelik el yazısı altın
    setinde bir belgenin bile 6'dan fazla ETİKETLİ (isim alanı gerçekten
    eşleşen) sayfası yok (dağılım: 1-5 arası, tek istisna 8) — yani bu sınır
    şu an ölçülebilir hiçbir belgeyi etkilemiyor; "68 okunmamış aday sayfa"
    bulgusu etikete bakılmaksızın HAM sayfa sayısıydı, yanıltıcıydı. 50'ye
    çıkarmak yine de zararsız (kapsanmayan tek 8 sayfalık belgede bile sonuç
    değişmedi) ve külliyatın en uzun belgesi 47 sayfa olduğu için ileride
    daha uzun/çok-etiketli belgeler çıkarsa payı önceden açıyor.
    """
    import pymupdf

    from belge.alan_cikarici import ETIKET_AD, etiket_kutusu, satir_kutusu
    from belge.pdf_okuyucu import bos_sayfa_mi

    okumalar: list[str] = []
    with pymupdf.open(Path(pdf_yolu)) as belge:
        for sayfa in belge:
            if len(okumalar) >= azami_sayfa:
                break
            if bos_sayfa_mi(sayfa):
                continue
            kutu = etiket_kutusu(sayfa, ETIKET_AD)
            if kutu is None:
                continue
            kirpma = pymupdf.Rect(*satir_kutusu(sayfa, kutu)) & sayfa.rect
            png = sayfa.get_pixmap(dpi=300, clip=kirpma).tobytes("png")
            okunan = okuyucu.oku(png).isim if hasattr(okuyucu, "oku") else ""
            if not okunan.strip():
                continue
            okumalar.append(normalize(okunan))

    sonuc = CokluOkuma(okumalar=okumalar)
    temsilci, adet = oy_birlestir(okumalar)
    sonuc.cogunluk = temsilci
    sonuc.uzlasma_adedi = adet
    if adet >= UZLASMA_ESIGI:
        sonuc.uzlasan = temsilci
    return sonuc


def kirpma_oku(
    okuyucu: IsimOkuyucu,
    pdf_yolu: Path | str,
    sayfa_no: int,
    kutu: tuple[float, float, float, float],
    ocr_ipucu: str = "",
) -> OkunanIsim:
    """Bir PDF'teki isim bölgesini kırpıp modele okutur."""
    from belge.pdf_okuyucu import bolge_goruntusu

    png = bolge_goruntusu(pdf_yolu, sayfa_no, kutu)
    return okuyucu.oku(png, ocr_ipucu=ocr_ipucu)
