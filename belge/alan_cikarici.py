"""OCR metin katmanından alan çıkarma. Modele hiç ihtiyaç duymaz.

SPEC.md 5.2 adım 1: sicil_no, tc_no ve (boşluksuz) isim OCR katmanından
desenle çıkarılır. VLM yalnızca bu katmanın çözemediklerine bakar.

Belge sahibinin kimliği nasıl belirlenir
---------------------------------------
Bir dosyada başka kişilerin TC'si de geçebiliyor (288 belgenin 13'ünde birden
fazla **geçerli** TC var; bunlar yanlış birleştirilmiş dosyalar — SPEC R8).
Yanlış TC'yi almak yanlış kişiyi kaydetmek demek. Bu yüzden burada **sayfadaki
herhangi bir 11 haneli sayı kabul edilmez**; yalnızca "T.C. Kimlik No"
etiketinin sağındaki değer alınır.

Etiket-değer eşleştirmesi metin sırasına değil **koordinata** dayanır: OCR
satırları sıra dışı üretebiliyor, ama etiket ile değeri aynı yatay bantta
duruyor.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import pymupdf

# --- Desenler. Gerçek belgelere göre kalibre edildi ------------------------

# Sicil no 5 hanelidir ve DN'den sonra tire yoktur: "DN47789"
DESEN_DN = re.compile(r"DN[\s:.\-]*(\d{4,6})")
# OCR "32/" ayıracını bazen "321" veya "32|" olarak okuyor
DESEN_32 = re.compile(r"\b32\s*[/1|]\s*(\d{4,6})")
# R8 tespiti: #32'deki ikinci kişi "Sicil No : 35197" yazıyor — ne DN ne 32/.
# Yalnız TESPİT; `_sicil_no_bul` bu deseni kullanmaz (çıkarma kuralları ayrı).
DESEN_SICIL_ETIKET = re.compile(r"Sicil\s+No\s*:?\s*(\d{4,5})", re.IGNORECASE)

DESEN_11_HANE = re.compile(r"\b[1-9]\d{10}\b")

# Etiketler OCR'da sık bozuluyor: "Adı Soyadı" gerçek belgelerde
# "Adı Soyıdı" ve "Atlı Soyadı" olarak da çıkıyor. Bu yüzden birebir desen
# yerine, katlanmış (ASCII, büyük harf, harf dışı atılmış) hâl üzerinde
# düzenleme mesafesiyle eşleştirilir.
ETIKET_AD = "ADISOYADI"
ETIKET_TC = "TCKIMLIKNO"
AZAMI_ETIKET_MESAFESI = 2

# Yedek etiket: bazı belgelerde OCR "Adı / Soyadı" hücresinin yalnızca
# "/ Soyadı" kısmını üretebiliyor; "SOYADI" tek başına asıl hedefe 3 mesafede
# kalıyor ve eşiği geçemiyor. Bu yedek YALNIZCA asıl etiket belgenin hiçbir
# sayfasında bulunamadığında denenir — tek başına daha zayıf bir sinyal.
ETIKET_AD_YEDEK = "SOYADI"

# Türkçe harfleri ASCII karşılıklarına indirger; OCR'ın ı/i, ş/s gibi
# karışıklıkları eşleşmeyi bozmasın diye. Küçük 'l' de 'I'ya katlanır: eski
# daktilo taramalarında OCR "ADI"/"SOYADI" içindeki İ/I'yı tutarlı biçimde
# küçük l okuyor ("ADl", "SoYADl") — gerçek bir belgede (DN2709) bu yüzden
# etiket_kutusu 4 sayfada da eşleşemeyip yanlış bir sayfaya (tablo başlığı)
# düşmüştü, kullanıcı web arayüzünde canlı yakaladı.
KATLAMA = str.maketrans("ÇĞİIÖŞÜçğıiöşül", "CGIIOSUCGIIOSUI")

# Belge çok sütunlu: "Adı Soyadı" satırının sağında, sayfanın öbür ucunda
# "Veriliş Tarihi" gibi başka alanlar var. Değer kelimeleri arasındaki boşluk
# bunu aşarsa yeni bir sütuna geçilmiş sayılır ve okuma orada kesilir.
SUTUN_ARALIGI = 25.0


@dataclass
class CikarilanAlanlar:
    """Bir belgeden OCR katmanıyla çıkarılabilen her şey."""

    sicil_no: str = ""
    tc_no: str = ""
    # OCR boşlukları kaybettiği için isim bitişik gelir: "AYŞENURDEMİR".
    # Boşluklandırma VLM'e bırakılır (SPEC 2.2).
    isim_bosluksuz: str = ""
    # İsim satırının sayfa numarası ve kutusu — VLM'e tüm sayfa yerine
    # yalnızca bu bölgenin kırpılıp verilmesi için.
    isim_sayfa: int | None = None
    isim_kutusu: tuple[float, float, float, float] | None = None
    # TC ve sicil için de aynısı. Bunlar değer okunabilmiş olsa da doldurulur:
    # ölçümde kaçan 18 TC'nin 18'inde de etiket bulunabiliyordu, yani çıkarıcı
    # alanın NEREDE olduğunu biliyor ama OKUYAMIYOR. Koordinatı elde tutmak
    # VLM'in tam sayfa yerine tek satıra bakmasını sağlar.
    tc_sayfa: int | None = None
    tc_kutusu: tuple[float, float, float, float] | None = None
    sicil_sayfa: int | None = None
    sicil_kutusu: tuple[float, float, float, float] | None = None
    uyarilar: list[str] = field(default_factory=list)


def tc_gecerli(no: str) -> bool:
    """TC kimlik no checksum doğrulaması."""
    if not re.fullmatch(r"[1-9]\d{10}", no):
        return False
    h = [int(x) for x in no]
    tek = h[0] + h[2] + h[4] + h[6] + h[8]
    cift = h[1] + h[3] + h[5] + h[7]
    if (tek * 7 - cift) % 10 != h[9]:
        return False
    return sum(h[:10]) % 10 == h[10]


# OCR rakam aralarına ayraç serpiştirebiliyor: "123 456 789 01" ile
# "12345678901" aynı sayıdır.
_AYRAC = re.compile(r"[ .\-]")


def gecerli_tcler(metin: str) -> set[str]:
    """Metindeki checksum'ı tutan tüm 11 haneli sayılar.

    Etiketten bağımsızdır: sayfada geçen her TC'yi bulur, sahibininkini
    seçmez. Belgede kaç ayrı kişinin TC'si geçtiğini görmek için (SPEC R6).
    """
    return {x for x in DESEN_11_HANE.findall(_AYRAC.sub("", metin)) if tc_gecerli(x)}


def sicil_adaylari(metin: str) -> set[str]:
    """Belgedeki tüm sicil no adayları — TESPİT, çıkarma değil.

    R8 için: birden fazla farklı sicil = yanlış birleştirme sinyali.
    DN, 32/ ve `Sicil No` / `Sicil No:` / `Sicil No :` + 4–5 hane.
    `_sicil_no_bul` bu kümeyi kullanmaz; çıkarma kuralları değişmez.
    Önek elemesi OCR kesik okumasını ikinci kişi sanmasın diye uygulanır.
    """
    ham = set()
    for desen in (DESEN_DN, DESEN_32, DESEN_SICIL_ETIKET):
        ham |= {d for d in desen.findall(metin) if 4 <= len(d) <= 5}
    return _onekleri_ele(ham)


def _dikey_ortusuyor(a: tuple, b: tuple) -> bool:
    """İki kutu aynı yatay bantta mı? (etiket ile değeri eşleştirmek için)

    Orta nokta içerme testi kullanılır: kutulardan birinin dikey ortası
    diğerinin içinde olmalı. Oransal örtüşme testi çok gevşek kalıyor ve
    komşu satırları da içine alıyordu.
    """
    a_orta = (a[1] + a[3]) / 2
    b_orta = (b[1] + b[3]) / 2
    return (b[1] < a_orta < b[3]) or (a[1] < b_orta < a[3])


def katla(metin: str) -> str:
    """Karşılaştırma için sadeleştirir: ASCII, büyük harf, yalnızca harfler."""
    return re.sub(r"[^A-Z]", "", metin.translate(KATLAMA).upper())


def mesafe(a: str, b: str) -> int:
    """Levenshtein düzenleme mesafesi.

    OCR etiketleri bir iki karakter bozuyor ("Adı"→"Atlı"). Kaç karakterlik
    bozulmaya izin verdiğimizi açıkça kontrol edebilmek için oran yerine
    mesafe kullanılır.
    """
    if a == b:
        return 0
    onceki = list(range(len(b) + 1))
    for i, ka in enumerate(a, start=1):
        simdiki = [i]
        for j, kb in enumerate(b, start=1):
            simdiki.append(
                min(onceki[j] + 1, simdiki[j - 1] + 1, onceki[j - 1] + (ka != kb))
            )
        onceki = simdiki
    return onceki[-1]


def etiket_degeri(
    sayfa: pymupdf.Page,
    etiket: str,
    azami_mesafe: int = AZAMI_ETIKET_MESAFESI,
) -> tuple[str, tuple | None]:
    """Etiketin sağındaki değeri ve o değerin kutusunu döndürür.

    etiket: katlanmış hedef metin (ör. "ADISOYADI").
    Değer yoksa ("", None) döner.
    """
    kelimeler = sayfa.get_text("words")  # (x0, y0, x1, y1, kelime, ...)
    if not kelimeler:
        return "", None

    # Etiket birden fazla kelimeye bölünmüş olabilir ("T.C." + "KimlikNo").
    # Kelimeleri yatay banda göre gruplayıp satırın soldan gelen ilk
    # kelimelerini birleştirerek etikete benzeyen bir önek arıyoruz.
    for kelime in kelimeler:
        kutu = kelime[:4]
        satir = [w for w in kelimeler if _dikey_ortusuyor(kutu, w[:4])]
        satir.sort(key=lambda w: w[0])

        # Etiket satırın başında olmak zorunda değil: çok sütunlu sayfalarda
        # aynı yatay bantta soldan başka alanlar gelebiliyor. Bu yüzden
        # ardışık kelimelerden oluşan her pencere denenir.
        #
        # İlk eşleşen değil EN İYİ eşleşen seçilir: "T.C. Kimlik" parçası
        # "TCKIMLIKNO" hedefine 2 mesafede olduğu için eşiği geçiyor ve
        # "No" kelimesi değer sanılıyordu. Önce en küçük mesafe, eşitlikte
        # en uzun pencere tercih edilir.
        en_iyi = None  # (mesafe, -uzunluk, etiket_sonu)
        for basla in range(len(satir)):
            for kac in range(1, min(4, len(satir) - basla) + 1):
                parca = katla("".join(w[4] for w in satir[basla : basla + kac]))
                if not parca:
                    continue
                d = mesafe(parca, etiket)
                if d > azami_mesafe:
                    continue
                aday = (d, -len(parca), satir[basla + kac - 1][2])
                if en_iyi is None or aday < en_iyi:
                    en_iyi = aday
        if en_iyi is None:
            continue
        etiket_sonu = en_iyi[2]

        adaylar = [w for w in satir if w[0] >= etiket_sonu - 0.5]
        if not adaylar:
            continue

        # Sütun sınırında kes: büyük bir yatay boşluktan sonrası başka alandır.
        sagdakiler = []
        onceki_sag = None
        for w in adaylar:
            if onceki_sag is not None and w[0] - onceki_sag > SUTUN_ARALIGI:
                break
            sagdakiler.append(w)
            onceki_sag = w[2]

        deger = " ".join(w[4] for w in sagdakiler).lstrip(": ").strip()
        if not deger:
            continue
        x0 = min(w[0] for w in sagdakiler)
        y0 = min(w[1] for w in sagdakiler)
        x1 = max(w[2] for w in sagdakiler)
        y1 = max(w[3] for w in sagdakiler)
        return deger, (x0, y0, x1, y1)

    return "", None


# Formların altında kurum görevlisinin imza bloğu var ve orada da bir
# "Adı Soyadı" etiketi geçiyor. O blok belgenin sahibini değil, evrakı
# düzenleyen memuru gösterir; oraya çıpalanmak yanlış kişiyi okutur.
GOREVLI_SOZCUKLERI = (
    "VEZNEDAR", "MEMUR", "YETKILI", "IMZA", "MUDUR", "MUDURLUGU",
    "SEKRETER", "BASKAN", "TASDIK", "ONAY", "KATIP",
)
# Görevli sözcüğü etiketin kaç satır yakınında aranacak (punto cinsinden).
# 40'tı; altın set etiketlemesinde bir "Sicil Memurunun Adı, Soyadı" bloğu
# gerçek formülle 55.7pt mesafede kalıp kaçtı. Pay bırakılarak yükseltildi.
GOREVLI_YAKINLIK = 65.0

# Görevli sözcüğü etiketten yatayda en çok kaç punto uzakta olabilir. Yalnız
# dikey yakınlık yeterli değil: sayfa üstündeki kurum adresi/başlığı
# ("...SİCİLİ MÜDÜRLÜĞÜNE") çoğu zaman "Adı Soyadı" alanına dikeyde yakın
# ama yatayda bambaşka bir sütunda/hizada duruyor — bu YANLIŞ reddediliyordu
# (88 belgelik altın sette 28 belge, 34 sayfa etkilendi, ölçüldü). Gerçek
# "Memurunun Adı Soyadı" bloğunda sözcük etikete bitişik (~0-5pt); sahte
# örnekte kurum başlığı ~196pt uzakta. 120pt: iki uçtan da geniş pay.
GOREVLI_YATAY_MESAFE = 120.0


def _form_etiketi_mi(pencere: list) -> bool:
    """Eşleşme form etiketi mi, yoksa cümle içindeki aynı kelimeler mi?

    Belgelerin gövdesinde "...adı ve soyadı yazılı üyemizin şahsi dosyasına
    sicil kaydı işlenmiştir." gibi cümleler geçiyor ve bulanık eşleştirici
    bunları alan etiketi sanıyordu. Doğrulama kuyruğunda okunamayan belgelerin
    büyük kısmı buydu.

    Ayırt edici işaret BÜYÜK HARF: form etiketi `Adı ve Soyadı` ya da
    `ADI VE SOYADI` biçiminde yazılı, cümle içindeki ifade ise küçük harfle
    (`adı ve soyadı`) başlıyor.

    İki nokta şartı da denendi ve ÇOK DAHA KÖTÜ çıktı: değer el yazısı olduğu
    için OCR etiketin sağında çoğu zaman hiçbir şey görmüyor, iki noktayı da
    yakalamıyor. Onaylanmış 142 belgenin 96'sında kutu tamamen kayboluyordu.
    """
    ilk = pencere[0][4].lstrip(".:-–( ")
    return bool(ilk) and ilk[0].isupper()


def _gorevli_blogu_mu(kelimeler: list, pencere: list) -> bool:
    """Etiket, kurum görevlisinin imza bloğunun içinde mi?

    Yalnız dikey yakınlık yanlış pozitif üretiyordu: sayfa üstündeki kurum
    başlığı ("...MÜDÜRLÜĞÜNE") dikeyde yakın ama yataydaysa alakasız bir
    sütunda oluyor. Yatay yakınlık da şart koşulur (bkz. GOREVLI_YATAY_MESAFE).
    """
    ust = min(w[1] for w in pencere)
    alt = max(w[3] for w in pencere)
    sol = min(w[0] for w in pencere)
    sag = max(w[2] for w in pencere)
    for w in kelimeler:
        if ust - GOREVLI_YAKINLIK <= w[1] <= alt + GOREVLI_YAKINLIK:
            yatay_bosluk = max(0.0, w[0] - sag, sol - w[2])
            if yatay_bosluk > GOREVLI_YATAY_MESAFE:
                continue
            if any(s in katla(w[4]) for s in GOREVLI_SOZCUKLERI):
                return True
    return False


def etiket_kutusu(
    sayfa: pymupdf.Page,
    etiket: str,
    azami_mesafe: int = AZAMI_ETIKET_MESAFESI,
) -> tuple | None:
    """Etiketin **kendi** kutusunu döndürür (değerin değil).

    `etiket_degeri` değeri OCR kelimelerinden okur ve kutusunu ona göre kurar.
    Bu, değer matbu olduğunda doğru çalışıyor ama **el yazısı alanlarda
    çöküyor**: OCR el yazısını görmediği için kutu yazının üstüne oturmuyor,
    noktalı çizginin görülebilen kadarını kapsıyor. Ölçümde iki ayrı bozulma
    görüldü — soyadı kırpılıp düşüyor, ya da tamamen başka bir alan
    yakalanıyor.

    Etiket ise her zaman matbudur ve OCR onu güvenilir biçimde görür. Bu yüzden
    el yazısı formlarda kırpma **etikete çıpalanır**: satır etiketten bulunur,
    sağındaki her şey kırpılır. Değerin nerede bittiğini tahmin etmeye
    çalışmayız — sayfanın sağ kenarına kadar alırız.
    """
    kelimeler = sayfa.get_text("words")
    en_iyi = None  # (üst_y, mesafe, -uzunluk, pencere)
    for kelime in kelimeler:
        satir = sorted(
            [w for w in kelimeler if _dikey_ortusuyor(kelime[:4], w[:4])],
            key=lambda w: w[0],
        )
        for basla in range(len(satir)):
            for kac in range(1, min(4, len(satir) - basla) + 1):
                pencere = satir[basla : basla + kac]
                parca = katla("".join(w[4] for w in pencere))
                if not parca:
                    continue
                d = mesafe(parca, etiket)
                if d > azami_mesafe:
                    continue
                # Küçük harfle başlayan eşleşme form etiketi değil, düz metin.
                if not _form_etiketi_mi(pencere):
                    continue
                # Görevli imza bloğu REDDEDİLİR, geri plana atılmaz. Önceden
                # sıralamada sona konuyordu ama sayfadaki tek aday oysa yine
                # seçiliyordu ve evrakı düzenleyen memur okunuyordu. Reddedince
                # arama sonraki sayfaya geçiyor.
                if _gorevli_blogu_mu(kelimeler, pencere):
                    continue
                ust = min(w[1] for w in pencere)
                aday = (ust, d, -len(parca), pencere)
                if en_iyi is None or aday[:3] < en_iyi[:3]:
                    en_iyi = aday
    if en_iyi is None:
        return None
    pencere = en_iyi[3]
    return (
        min(w[0] for w in pencere),
        min(w[1] for w in pencere),
        max(w[2] for w in pencere),
        max(w[3] for w in pencere),
    )


def satir_kutusu(sayfa: pymupdf.Page, etiket_kutu: tuple, pay_orani: float = 0.6) -> tuple:
    """Etiket kutusundan, satırın tamamını kapsayan kırpma bölgesi üretir."""
    x0, y0, x1, y1 = etiket_kutu
    pay = (y1 - y0) * pay_orani
    return (max(sayfa.rect.x0, x0 - 2), y0 - pay, sayfa.rect.x1, y1 + pay)


HARF_DESENI = re.compile(r"[A-Za-zÇĞİÖŞÜçğıöşü ]")


def isim_makul_mu(ham: str) -> bool:
    """Etiketten gelen değerin isim olma ihtimalini kabaca değerlendirir.

    Etiket bazı sayfalarda tablo başlığına veya bozuk bir OCR bloğuna
    denk gelebiliyor; o zaman değer olarak noktalama dolu bir dizge dönüyor
    (ör. `Reıaİİş.?'#"'X?H.,J??:İi}'3İŞ`). Böyle bir değeri kabul etmek,
    aynı belgenin ilerideki sayfasındaki temiz ismin bulunmasını engelliyor.

    Sözlük veya isim listesi kullanılmaz (SPEC R1) — yalnızca biçimsel
    makullük bakılır.
    """
    if not ham:
        return False
    harf_orani = sum(1 for k in ham if HARF_DESENI.match(k)) / len(ham)
    if harf_orani < 0.75:
        return False
    temiz = "".join(k for k in ham if HARF_DESENI.match(k)).strip()
    if len(temiz) < 5:
        return False
    # En fazla 4 kelime: çift isim + çift soyisim ("Ali Rıza Demir Kaya") bu
    # sınıra sığıyor. 5 kelimeye izin verildiğinde tablo başlıkları
    # ("Baba Adı Şirket Türü Vergi Dairesi ...") isim sanılıyordu.
    return 1 <= len(temiz.split()) <= 4


def _onekleri_ele(adaylar: set[str]) -> set[str]:
    """Bir adayın uzunu varsa kısasını atar.

    OCR bozulduğunda son rakamı düşürüyor: `46488` -> `4648`. İkisi de aynı
    metinde göründüğünde kısası kesik okumadır. Bu eleme yapılmazsa kesik
    değer çapraz doğrulamadan geçip doğrulanmış gibi kabul edilebiliyor
    (ölçümde #12, #42, #50 böyleydi).
    """
    return {a for a in adaylar if not any(b != a and b.startswith(a) for b in adaylar)}


def _sicil_no_bul(sayfa_metinleri: list[str], sonuc: CikarilanAlanlar) -> str:
    """DN ve 32/ değerlerini çapraz doğrular (SPEC 3)."""
    tam = "\n".join(sayfa_metinleri)
    # Hane sayısı külliyata göre değişiyor: ilk külliyatta 5, ikinci
    # külliyatta (1980'ler) 4. Bir zamanlar burada sabit "5 hane" süzgeci
    # vardı; ilk külliyatta işe yarıyordu ama ikincisinin TÜM sicillerini
    # eliyordu (SPEC 2.3).
    #
    # Süzgeç yerine ölçülmüş bir gözlem kullanılıyor: OCR bozulduğunda
    # **son rakamı düşürüyor**, yani 4 haneli bir aday 5 hanelinin öneki
    # olabiliyor (#23 4647 -> gerçek 46471, #72 4670 -> 46701). Bu yüzden
    # 4 haneli tek aday güvenilmezdir ve görüntüden doğrulanması gerekir;
    # kararı `sayi_okuyucu` şeridi veriyor (5/5 doğru çözdü).
    ham_dn = {d for d in DESEN_DN.findall(tam) if 4 <= len(d) <= 5}
    ham_32 = {d for d in DESEN_32.findall(tam) if 4 <= len(d) <= 5}
    # Önek elemesi İKİ KAYNAĞIN BİRLEŞİMİ üzerinde yapılır. Kaynak içinde
    # yapılsaydı, bir kaynağın kesik (`4648`) öbürünün sağlam (`46488`) okuduğu
    # belgelerde iki değer ayrı kümelerde kalır, kesişim boşalır ve sağlam
    # değer de kaybolurdu (ölçümde #12, #42, #50).
    atilacak = {a for a in ham_dn | ham_32
                if any(b != a and b.startswith(a) for b in ham_dn | ham_32)}
    dn = ham_dn - atilacak
    otuziki = ham_32 - atilacak

    ortak = dn & otuziki
    if len(ortak) == 1:
        deger = ortak.pop()
        # Çapraz doğrulama 4 hanede YETMEZ: OCR her iki kaynakta da son
        # rakamı düşürebiliyor ve iki kesik okuma birbirini "doğruluyor"
        # (ölçümde #23 ve #72). Hane sayısı külliyata göre değiştiği için
        # 4 haneyi reddetmek de olmaz; karar görüntüye bırakılır.
        if len(deger) == 5:
            return deger
        sonuc.uyarilar.append("sicil_no 4 hane, goruntuden dogrulanmali")
        return ""
    if dn and otuziki and not ortak:
        sonuc.uyarilar.append("sicil_no capraz dogrulama cakisti")
        return ""
    # Tek kaynak: 5 haneliyse kabul edilir (ilk külliyatta ölçülen isabet
    # %98.6). 4 haneliyse kabul EDİLMEZ -- OCR'ın son rakamı düşürmüş olma
    # ihtimali var ve ayırt edilemez. Boş bırakılır, şerit karar verir.
    tek_kaynak = dn or otuziki
    if len(tek_kaynak) == 1:
        deger = next(iter(tek_kaynak))
        if len(deger) == 5:
            sonuc.uyarilar.append("sicil_no tek kaynaktan, capraz dogrulanamadi")
            return deger
        sonuc.uyarilar.append("sicil_no tek kaynak ve 4 hane, goruntuden dogrulanmali")
        return ""
    if not tek_kaynak:
        sonuc.uyarilar.append("sicil_no bulunamadi")
    else:
        sonuc.uyarilar.append("sicil_no birden fazla aday")
    return ""


def _sicil_kutusu_bul(belge: pymupdf.Document) -> tuple[int, tuple] | None:
    """Sicil no'nun sayfadaki konumu — VLM'e verilecek bölge.

    Yalnızca `DN47789` kelimesi aranır (1. sayfanın sol üstü, en temiz konum).
    Bulunamazsa konum verilmez ve VLM çağrılmaz.

    `Esnaf ve Sanatkar Sicil No` etiketine düşen bir yedek yol denendi ve
    **ölçümde başarısız oldu (0/7)**. İki hata üst üste biniyordu:

    1. Etiket sayfa başlığını yakalıyor. `Esnaf ve Sanatkar Sicil` dört
       kelimelik pencerede hedefe 2 mesafede kalıyor, eşiği geçiyor ve
       sağındaki değer `Müdürlüğü` oluyor — yani hiç rakam içermeyen bir bölge.
    2. Model o bölgeden yine de 5 hane üretiyor. "Okunamıyorsa YOK yaz"
       talimatı bunu engellemedi: istenen biçimde çıktı üretme eğilimi
       talimattan güçlü çıktı.

    DN kelimesinden gelen konum ise 2/2 doğru okuma verdi. Zayıf konum
    sinyalini modele vermek, boş bırakmaktan kötü.
    """
    for indeks, sayfa in enumerate(belge):
        for kelime in sayfa.get_text("words"):
            if DESEN_DN.search(kelime[4]):
                return indeks + 1, kelime[:4]
    return None


def cikar(pdf_yolu: Path | str) -> CikarilanAlanlar:
    """Bir PDF'ten OCR katmanıyla çıkarılabilen alanları toplar."""
    sonuc = CikarilanAlanlar()
    # Etiketi bulunduğu hâlde OCR değeri kullanılamayan ilk konum. Hiçbir
    # sayfada okunabilir isim çıkmazsa VLM bu bölgeden okur.
    yedek_kutu: tuple[int, tuple[float, float, float, float]] | None = None

    with pymupdf.open(Path(pdf_yolu)) as belge:
        sayfa_metinleri = [s.get_text() for s in belge]
        sonuc.sicil_no = _sicil_no_bul(sayfa_metinleri, sonuc)
        konum = _sicil_kutusu_bul(belge)
        if konum:
            sonuc.sicil_sayfa, sonuc.sicil_kutusu = konum

        # Sahibin kimliği: DN'nin geçtiği sayfa esas alınır. DN yoksa
        # etiketlerin bulunduğu ilk sayfaya düşülür.
        dn_sayfa = next(
            (i for i, m in enumerate(sayfa_metinleri) if DESEN_DN.search(m)),
            None,
        )
        # Önce DN sayfası denenir (sahibin kimlik alanları oradadır), sonra
        # diğerleri. Sayfa ön elemesi yapılmaz: etiketler OCR'da bozulduğu
        # için metin araması güvenilir değil, kararı esnek eşleştirici verir.
        aday_sayfalar = [dn_sayfa] if dn_sayfa is not None else []
        aday_sayfalar += [i for i in range(len(sayfa_metinleri)) if i != dn_sayfa]

        for indeks in aday_sayfalar:
            sayfa = belge[indeks]

            if not sonuc.tc_no:
                ham, tc_kutu = etiket_degeri(sayfa, ETIKET_TC)
                # Konum, değer okunamasa da saklanır: VLM'in bakacağı yer bu.
                if tc_kutu and sonuc.tc_kutusu is None:
                    sonuc.tc_sayfa, sonuc.tc_kutusu = indeks + 1, tc_kutu
                rakamlar = re.sub(r"\D", "", ham)
                eslesme = DESEN_11_HANE.search(rakamlar)
                if eslesme:
                    aday = eslesme.group()
                    if tc_gecerli(aday):
                        sonuc.tc_no = aday
                    else:
                        sonuc.uyarilar.append("tc_no checksum tutmadi")

            if not sonuc.isim_bosluksuz:
                ham, kutu = etiket_degeri(sayfa, ETIKET_AD)
                temiz = re.sub(r"[^A-Za-zÇĞİÖŞÜçğıöşü ]", "", ham).strip()
                if temiz and isim_makul_mu(ham):
                    sonuc.isim_bosluksuz = temiz
                    sonuc.isim_sayfa = indeks + 1
                    sonuc.isim_kutusu = kutu
                elif kutu:
                    # OCR değeri çöp ama etiket bulundu. Koordinat yine de
                    # değerli: görüntüde isim okunabilir olabilir, VLM oradan
                    # okur. Metni kaybetmek koordinatı kaybettirmemeli.
                    # En erken sayfa tercih edilir: kimlik alanları belgenin
                    # başında olur, ilerideki sayfalar genelde tablo/ek.
                    if yedek_kutu is None or indeks + 1 < yedek_kutu[0]:
                        yedek_kutu = (indeks + 1, kutu)

            if sonuc.tc_no and sonuc.isim_bosluksuz:
                break

        # Asıl etiket okunabilir bir isim vermediyse yedek etiket denenir.
        if not sonuc.isim_bosluksuz:
            for indeks in aday_sayfalar:
                ham, kutu = etiket_degeri(belge[indeks], ETIKET_AD_YEDEK)
                if not kutu:
                    continue
                temiz = re.sub(r"[^A-Za-zÇĞİÖŞÜçğıöşü ]", "", ham).strip()
                if temiz and isim_makul_mu(ham):
                    sonuc.isim_bosluksuz = temiz
                    sonuc.isim_sayfa = indeks + 1
                    sonuc.isim_kutusu = kutu
                    break
                if yedek_kutu is None or indeks + 1 < yedek_kutu[0]:
                    yedek_kutu = (indeks + 1, kutu)

    if not sonuc.tc_no:
        sonuc.uyarilar.append("tc_no etiketten bulunamadi")
    if not sonuc.isim_bosluksuz:
        if yedek_kutu is not None:
            # İsim metni okunamadı ama nerede olduğunu biliyoruz; VLM'e
            # o bölge verilecek.
            sonuc.isim_sayfa, sonuc.isim_kutusu = yedek_kutu
            sonuc.uyarilar.append("isim OCR'dan okunamadi, kutu VLM'e birakildi")
        else:
            sonuc.uyarilar.append("isim etiketten bulunamadi")
    return sonuc

def resmi_belge_gostergesi_var_mi(sayfa: pymupdf.Page) -> bool:
    """Sayfada bilinen HİÇBİR resmi alan göstergesi yoksa False.

    'Adı Soyadı', 'T.C. Kimlik No', 'DN', '32/', 'Sicil No' — bunların
    hiçbiri yoksa sayfa muhtemelen bu belge takımına ait değildir
    (yanlışlıkla karışmış bir sayfa, ör. el yazısı serbest not).
    """
    metin = sayfa.get_text()
    if DESEN_DN.search(metin) or DESEN_32.search(metin) or DESEN_SICIL_ETIKET.search(metin):
        return True
    if etiket_kutusu(sayfa, ETIKET_AD) or etiket_kutusu(sayfa, ETIKET_AD_YEDEK):
        return True
    if etiket_degeri(sayfa, ETIKET_TC)[1] is not None:
        return True
    return False

def belge_resmi_mi(pdf_yolu: Path | str, azami_sayfa: int = 5) -> bool:
    """İlk birkaç sayfada hiçbir resmi gösterge yoksa False.

    Amaç: yanlışlıkla karışmış tamamen alakasız belgeleri (spiralli defter
    yaprağı, serbest el yazısı not) VLM'e hiç göndermeden elemek. Yalnız
    ilk `azami_sayfa` sayfaya bakılır — kimlik alanları resmi belgelerde
    hep baştadır (SPEC 3); tüm belgeyi taramak gereksiz maliyet.

    Genişletme noktası: burada `resmi_belge_gostergesi_var_mi` yerine/yanına
    bir HTR modeli (TrOCR/EasyOCR) çağrılıp metnin "resmi form dili" mi yoksa
    "serbest el yazısı" mı olduğuna bakılabilir. Ağır bağımlılık eklemeden
    önce mevcut ölçüm kültürüne uyarak `araclar/olc_hibrit_katman.py` ile
    kaç belgenin bu kapıdan yanlış geçtiği ölçülmeli.
    """
    import pymupdf

    with pymupdf.open(Path(pdf_yolu)) as belge:
        for sayfa in belge[:azami_sayfa]:
            if resmi_belge_gostergesi_var_mi(sayfa):
                return True
    return False