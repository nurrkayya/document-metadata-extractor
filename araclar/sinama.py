"""Dosyaya dokunan mantığın sınaması (SPEC Adım 7).

    .venv/bin/python araclar/sinama.py

Neden bu dosya var
------------------
Doğruluk ölçümleri (`olc_*.py`) modelin ve çıkarıcının **ne kadar doğru**
okuduğunu ölçer. Bu dosya farklı bir soruyu sorar: adlandırma, çakışma
çözümü, mükerrer atlama ve bölme **kurallarına göre mi davranıyor?**

Bu mantık ilk yazıldığında tek seferlik betiklerle sınanmıştı ve o sınamalar
kayboldu. Arşivleme geri alması zor bir işlem; kurallarının doğrulaması
kalıcı olmalı.

Kişisel veri kullanılmaz: sınama PDF'leri pymupdf ile burada üretilir,
içlerindeki isimler ve numaralar uydurmadır (TC'ler checksum'ı tutacak
şekilde hesaplanır, gerçek kimliklere karşılık gelmez).
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import araclar._kok  # noqa: F401

import tempfile

import pymupdf  # noqa: E402

from belge.adlandirma import cakismasiz, dosya_adi, json_anahtari  # noqa: E402
from belge.alan_cikarici import (  # noqa: E402
    cikar, isim_makul_mu, sicil_adaylari, tc_gecerli,
)
from belge.isim_okuyucu import (  # noqa: E402
    VARSAYILAN_MODEL,
    argv_model,
    birlestir,
    onbellek_yolu,
    secilen_model,
)
from belge.arsiv import (  # noqa: E402
    ARSIVLE, ATLA, DOGRULANMALI, HATA, HASH_KAYDI, OKUNAMADI, Arsiv,
    dosya_ozeti, kaynaktan_bul, metin_ozeti,
)
from belge.bolucu import (  # noqa: E402
    kullanici_plani, plan_cikar, plan_gruplari, plan_sozluge, sayfalari_yaz, uygula,
)

_gecti = 0
_kaldi: list[str] = []


def esit(bulunan, beklenen, ad: str) -> None:
    global _gecti
    if bulunan == beklenen:
        _gecti += 1
    else:
        _kaldi.append(f"{ad}: beklenen {beklenen!r}, bulunan {bulunan!r}")


def tc_uret(onek: str) -> str:
    """9 haneli önekten checksum'ı tutan 11 haneli sayı üretir (uydurma)."""
    h = [int(x) for x in onek]
    tek = h[0] + h[2] + h[4] + h[6] + h[8]
    cift = h[1] + h[3] + h[5] + h[7]
    onuncu = (tek * 7 - cift) % 10
    onbirinci = (sum(h) + onuncu) % 10
    return onek + str(onuncu) + str(onbirinci)


def pdf_uret(yol: Path, sayfalar: list[str]) -> None:
    """Her sayfası verilen metni taşıyan bir PDF yazar."""
    belge = pymupdf.open()
    for metin in sayfalar:
        sayfa = belge.new_page()
        sayfa.insert_text((72, 100), metin, fontsize=11)
    belge.save(yol)
    belge.close()


# --- adlandırma (SPEC 4.1, 4.3) -------------------------------------------


def sina_adlandirma() -> None:
    for giris, beklenen in [
        ("Şener Çeliköz", "sener_celikoz"),
        ("Ayşe Nur Demir", "ayse_nur_demir"),
        ("Ali Rıza Demir Kaya", "ali_riza_demir_kaya"),
        ("IŞIL IŞIK", "isil_isik"),
        ("  fazla   boşluk  ", "fazla_bosluk"),
        ("", ""),
        ("...", ""),
    ]:
        esit(dosya_adi(giris), beklenen, f"dosya_adi({giris!r})")

    esit(json_anahtari("Ayşe Nur Demir"), "AYSE_NUR_DEMIR", "json_anahtari")

    kullanilan = {"ahmet_yilmaz"}
    esit(cakismasiz("ahmet_yilmaz", kullanilan), "ahmet_yilmaz_2", "ilk çakışma")
    kullanilan.add("ahmet_yilmaz_2")
    esit(cakismasiz("ahmet_yilmaz", kullanilan), "ahmet_yilmaz_3", "ikinci çakışma")
    esit(cakismasiz("baska_ad", kullanilan), "baska_ad", "çakışma yok")
    # cakismasiz kümeyi değiştirmemeli: kuru kipte ad rezerve edilmemeli
    esit(len(kullanilan), 2, "cakismasiz kümeyi değiştirmiyor")


# --- TC checksum ----------------------------------------------------------


def sina_checksum() -> None:
    gecerli = tc_uret("123456789")
    esit(tc_gecerli(gecerli), True, "üretilen TC geçerli")
    esit(len(gecerli), 11, "TC 11 hane")
    # son haneyi bozunca tutmamalı
    bozuk = gecerli[:-1] + str((int(gecerli[-1]) + 1) % 10)
    esit(tc_gecerli(bozuk), False, "bozuk checksum reddedilir")
    esit(tc_gecerli("0" + gecerli[1:]), False, "0 ile başlayan reddedilir")
    esit(tc_gecerli("123"), False, "kısa sayı reddedilir")


# --- arşivleme (SPEC 4.2, 4.4, 4.5) ---------------------------------------


class SahteAlanlar:
    def __init__(self, isim="", tc_no="", sicil_no="", uzlasma=0):
        self.isim, self.tc_no, self.sicil_no = isim, tc_no, sicil_no
        self.uzlasma = uzlasma


def sina_arsivleme() -> None:
    with tempfile.TemporaryDirectory() as gecici:
        kok = Path(gecici)
        girdi = kok / "girdi"
        girdi.mkdir()
        for ad in ("a.pdf", "b.pdf", "c.pdf", "isimsiz.pdf"):
            pdf_uret(girdi / ad, ["sınama sayfası"])
        # a ile aynı içerikte ikinci dosya: mükerrer atlama sınaması
        (girdi / "a_kopya.pdf").write_bytes((girdi / "a.pdf").read_bytes())

        arsiv = Arsiv.yukle(kok)
        e_a = arsiv.planla(girdi / "a.pdf", SahteAlanlar("Ahmet Yılmaz", "1", "2"))
        e_b = arsiv.planla(girdi / "b.pdf", SahteAlanlar("Ahmet Yılmaz", "3", "4"))
        e_c = arsiv.planla(girdi / "c.pdf", SahteAlanlar("Şener Çeliköz"))
        e_bos = arsiv.planla(girdi / "isimsiz.pdf", SahteAlanlar(""))
        e_kopya = arsiv.planla(girdi / "a_kopya.pdf", SahteAlanlar("Ahmet Yılmaz"))

        esit(e_a.hedef.name, "ahmet_yilmaz.pdf", "ilk ad")
        esit(e_b.hedef.name, "ahmet_yilmaz_2.pdf", "çakışan ad")
        esit(e_c.hedef.name, "sener_celikoz.pdf", "türkçe ad")
        esit(e_bos.tur, OKUNAMADI, "isimsiz -> okunamadi")
        esit(e_bos.hedef.name, "isimsiz.pdf", "okunamadi orijinal adla")
        esit(e_kopya.tur, ATLA, "aynı içerik atlanır")

        esit(len(arsiv.person_data), 2, "person_data anahtar sayısı")
        esit(len(arsiv.person_data["AHMET_YILMAZ"]), 2, "aynı ada iki kayıt")
        esit(
            sorted(arsiv.person_data["AHMET_YILMAZ"][0].keys()),
            ["isim", "sicil_no", "tc_no"],
            "kayıt şeması",
        )

        # kuru kip hiçbir şey yazmamalı
        arsiv.uygula([e_a, e_b, e_c, e_bos, e_kopya], kuru_calistir=True)
        esit((kok / ARSIVLE).exists(), False, "kuru kip klasör açmıyor")
        esit((kok / "person_data.json").exists(), False, "kuru kip JSON yazmıyor")

        arsiv.uygula([e_a, e_b, e_c, e_bos, e_kopya], kuru_calistir=False)
        esit(sorted(p.name for p in (kok / ARSIVLE).glob("*.pdf")),
             ["ahmet_yilmaz.pdf", "ahmet_yilmaz_2.pdf", "sener_celikoz.pdf"],
             "arşive yazılanlar")
        esit((kok / OKUNAMADI / "isimsiz.pdf").exists(), True, "okunamadi yazıldı")
        esit((girdi / "a_kopya.pdf").exists(), True, "atlanan taşınmadı")
        esit((girdi / "a.pdf").exists(), False, "işlenen kaynaktan taşındı")

        # ikinci koşu: her şey mükerrer sayılmalı
        arsiv2 = Arsiv.yukle(kok)
        e_tekrar = arsiv2.planla(girdi / "a_kopya.pdf", SahteAlanlar("Ahmet Yılmaz"))
        esit(e_tekrar.tur, ATLA, "tekrar koşuda mükerrer")

        # Yeniden dışa aktarılmış kopya: aynı metin, farklı PDF baytları.
        # Külliyatta ölçüldü (721 dosyada 1 grup); dosya özeti bunu kaçırır.
        # Metin ASGARI_METIN eşiğini aşmalı; tek satır sayfa kenarında
        # kırpıldığı için çok sayfa kullanılıyor.
        uzun = [f"sinama sayfasi {i} dolgu metni buraya yaziliyor" for i in range(8)]
        yeni_pdf = girdi / "yeniden_aktarilmis.pdf"
        pdf_uret(yeni_pdf, uzun)
        ikiz = girdi / "ikiz.pdf"
        pdf_uret(ikiz, uzun)
        esit(yeni_pdf.read_bytes() == ikiz.read_bytes(), False, "baytlar farklı")
        esit(metin_ozeti(yeni_pdf) != "", True, "metin özeti üretilebildi")
        arsiv3 = Arsiv.yukle(kok)
        e1 = arsiv3.planla(yeni_pdf, SahteAlanlar("Metin Ozet"))
        e2 = arsiv3.planla(ikiz, SahteAlanlar("Metin Ozet"))
        esit(e1.tur, ARSIVLE, "ilk kopya arşivlenir")
        esit(e2.tur, ATLA, "metni aynı kopya atlanır")

        # İzlenebilirlik: arşivdeki addan orijinaline dönülebilmeli. Ad
        # tamamen değiştiği için bu kayıt olmadan koşu geri alınamaz.
        geri = {v["hedef"]: v["kaynak"] for v in arsiv2.hashler.values()}
        esit(geri.get("ahmet_yilmaz.pdf"), "a.pdf", "kaynak adı korunuyor")
        esit(geri.get("ahmet_yilmaz_2.pdf"), "b.pdf", "çakışan ad da izlenebilir")
        esit(geri.get("isimsiz.pdf"), "isimsiz.pdf", "okunamadi izlenebilir")


def sina_kati_kip() -> None:
    """Katı kip: uzlaşmayan okuma arşive değil dogrulanmali/'ya gider."""
    with tempfile.TemporaryDirectory() as gecici:
        kok = Path(gecici)
        girdi = kok / "girdi"
        girdi.mkdir()
        for ad, sayfa in (("uzlasan.pdf", ["a"]), ("uzlasmayan.pdf", ["b"])):
            pdf_uret(girdi / ad, sayfa)

        arsiv = Arsiv.yukle(kok)
        e1 = arsiv.planla(girdi / "uzlasan.pdf", SahteAlanlar("Ahmet Yılmaz", uzlasma=2), kati=True)
        e2 = arsiv.planla(girdi / "uzlasmayan.pdf", SahteAlanlar("Mehmet Kaya", uzlasma=0), kati=True)
        esit(e1.tur, ARSIVLE, "uzlaşan arşive gider")
        esit(e2.tur, DOGRULANMALI, "uzlaşmayan doğrulanmalıya gider")
        esit(e2.hedef.name, "mehmet_kaya.pdf", "öneri adı korunur (sıfırdan okuma olmasın)")
        # person_data'ya YALNIZ arşivlenen girer
        esit(list(arsiv.person_data), ["AHMET_YILMAZ"], "doğrulanmamış JSON'a girmez")

        # Doğrulanmamış okumanın ÇIKARILAN ALANLARI kaybolmamalı: isim
        # doğrulanmamış olsa da tc/sicil bağımsız doğrulanıyor ve saatlerce
        # süren koşunun sonucu. person_data'ya girmez, ayrı dosyaya yazılır.
        esit(arsiv.dogrulanmali_veri.get("mehmet_kaya.pdf", {}).get("tc_no"), "",
             "doğrulanmalı verisi tutuluyor")
        esit("mehmet_kaya.pdf" in arsiv.dogrulanmali_veri, True,
             "doğrulanmalı kaydı var")
        esit(arsiv.dogrulanmali_veri["mehmet_kaya.pdf"]["isim_onerisi"], "Mehmet Kaya",
             "isim ÖNERİ olarak saklanır")

        # ÇAKIŞMA: aynı ada iki belge kuyruğa düşerse üzerine YAZMAMALI.
        # Bu sınama gerçek bir veri kaybından sonra yazıldı: 250 belgelik
        # koşuda iki belge aynı adla dogrulanmali/'ya taşınıp kayboldu.
        pdf_uret(girdi / "ayni_ad_1.pdf", ["x"])
        pdf_uret(girdi / "ayni_ad_2.pdf", ["y"])
        c1 = arsiv.planla(girdi / "ayni_ad_1.pdf", SahteAlanlar("Aynı Ad", uzlasma=0), kati=True)
        c2 = arsiv.planla(girdi / "ayni_ad_2.pdf", SahteAlanlar("Aynı Ad", uzlasma=0), kati=True)
        esit(c1.hedef.name, "ayni_ad.pdf", "kuyrukta ilk ad")
        esit(c2.hedef.name, "ayni_ad_2.pdf", "kuyrukta çakışan ad çözülür")
        arsiv.uygula([c1, c2], kuru_calistir=False)
        esit(sorted(p.name for p in (kok / DOGRULANMALI).glob("*.pdf")),
             ["ayni_ad.pdf", "ayni_ad_2.pdf"], "iki dosya da korundu")

        # GÜVENLİK AĞI: hedef zaten varsa taşıma DURMALI, üzerine yazmamalı
        pdf_uret(girdi / "carpisan.pdf", ["z"])
        from belge.arsiv import Eylem
        çarpisan = Eylem(kaynak=girdi / "carpisan.pdf", tur=DOGRULANMALI,
                         hedef=kok / DOGRULANMALI / "ayni_ad.pdf")
        try:
            arsiv.uygula([çarpisan], kuru_calistir=False)
            esit("üzerine yazdı", "hata vermeliydi", "üzerine yazma engellenir")
        except FileExistsError:
            esit(True, True, "üzerine yazma engellenir")
        esit((girdi / "carpisan.pdf").exists(), True, "engellenen dosya yerinde kaldı")

        # Katı kip KAPALIYKEN uzlaşmayan da arşivlenir. Taze bir dosyayla
        # sınanır: yukarıdakiler artık hash kaydında ve mükerrer sayılırlar.
        pdf_uret(girdi / "kati_kapali.pdf", ["w"])
        arsiv2 = Arsiv.yukle(kok)
        e3 = arsiv2.planla(girdi / "kati_kapali.pdf", SahteAlanlar("Kati Kapali", uzlasma=0))
        esit(e3.tur, ARSIVLE, "katı kapalıyken arşive gider")


# --- bölme (SPEC R8, bölüm 6.6) -------------------------------------------


def sina_bolme() -> None:
    a, b = tc_uret("111111111"), tc_uret("222222222")
    with tempfile.TemporaryDirectory() as gecici:
        kok = Path(gecici)

        temiz = kok / "temiz.pdf"
        pdf_uret(temiz, [
            f"T.C. Kimlik No : {a}", "ara sayfa", f"T.C. Kimlik No : {a}",
            f"T.C. Kimlik No : {b}", "son sayfa",
        ])
        plan = plan_cikar(temiz, a)
        esit(plan.harita, "AAABB", "temiz harita")
        esit(plan.bolunebilir, True, "temiz bölünebilir")
        esit(plan.bloklar, [("A", 1, 3), ("B", 4, 5)], "blok sınırları")

        parcalar = uygula(temiz, plan, kok / "ayrildi", kuru_calistir=False)
        toplam = 0
        for p in parcalar:
            with pymupdf.open(p) as belge:
                toplam += len(belge)
        esit(toplam, 5, "sayfa korunumu")

        # araya giren sayfa: ABA -> bölünmemeli
        karisik = kok / "karisik.pdf"
        pdf_uret(karisik, [
            f"T.C. Kimlik No : {a}", f"T.C. Kimlik No : {b}", f"T.C. Kimlik No : {a}",
        ])
        plan2 = plan_cikar(karisik, a)
        esit(plan2.harita, "ABA", "karışık harita")
        esit(plan2.bolunebilir, False, "karışık bölünmez")

        # tek kişi: bölünecek bir şey yok
        tek = kok / "tek.pdf"
        pdf_uret(tek, [f"T.C. Kimlik No : {a}", "ara"])
        plan3 = plan_cikar(tek, a)
        esit(plan3.bolunebilir, False, "tek kişi bölünmez")
        esit(plan3.gerekce, "ikinci kişi bulunamadı", "tek kişi gerekçesi")


def sina_kesinti() -> None:
    """--uygula yarıda kesilirse biten belgenin JSON/hash'i diskte kalır."""
    with tempfile.TemporaryDirectory() as gecici:
        kok = Path(gecici)
        girdi = kok / "girdi"
        girdi.mkdir()
        pdf_uret(girdi / "a.pdf", ["kesinti a"])
        pdf_uret(girdi / "b.pdf", ["kesinti b"])
        pdf_uret(girdi / "c.pdf", ["kesinti c"])

        arsiv = Arsiv.yukle(kok)
        e_a = arsiv.planla(girdi / "a.pdf", SahteAlanlar("Ali Veli"))
        arsiv.uygula([e_a], kuru_calistir=False)

        esit((kok / "person_data.json").exists(), True, "ilk belgede JSON yazıldı")
        esit((kok / HASH_KAYDI).exists(), True, "ilk belgede hash yazıldı")
        esit((girdi / "a.pdf").exists(), False, "ilk belge taşındı")
        esit((girdi / "b.pdf").exists(), True, "kesinti sonrası kalan duruyor")
        esit((girdi / "c.pdf").exists(), True, "işlenmeyen üçüncü duruyor")

        # Koşu öldü, bellek gitti — diskten yükle.
        arsiv2 = Arsiv.yukle(kok)
        esit("ALI_VELI" in arsiv2.person_data, True, "kesinti sonrası kayıt duruyor")
        e_b = arsiv2.planla(girdi / "b.pdf", SahteAlanlar("Ayse Nur"))
        esit(e_b.tur, ARSIVLE, "kalan belge işlenebilir")

        (girdi / "a_tekrar.pdf").write_bytes((kok / ARSIVLE / "ali_veli.pdf").read_bytes())
        e_tekrar = arsiv2.planla(girdi / "a_tekrar.pdf", SahteAlanlar("Ali Veli"))
        esit(e_tekrar.tur, ATLA, "işlenmiş belge tekrarında atlanır")

        # FileExistsError sessiz üzerine yazmaz; önceki kayıt diskte kalır.
        pdf_uret(girdi / "carpisan.pdf", ["z"])
        from belge.arsiv import Eylem
        carpisan = Eylem(
            kaynak=girdi / "carpisan.pdf",
            tur=ARSIVLE,
            hedef=kok / ARSIVLE / "ali_veli.pdf",
        )
        try:
            arsiv2.uygula([carpisan], kuru_calistir=False)
            esit("üzerine yazdı", "hata vermeliydi", "kesintide üzerine yazma yok")
        except FileExistsError:
            esit(True, True, "kesintide üzerine yazma yok")
        esit((kok / ARSIVLE / "ali_veli.pdf").exists(), True, "önceki dosya duruyor")
        esit("ALI_VELI" in Arsiv.yukle(kok).person_data, True, "önceki JSON duruyor")

        # AYRILDI: asıl alınır alınmaz hash işaretlenir.
        a, b = tc_uret("111111111"), tc_uret("222222222")
        iki = girdi / "iki_kisi.pdf"
        pdf_uret(iki, [
            f"T.C. Kimlik No : {a}", "ara sayfa", f"T.C. Kimlik No : {a}",
            f"T.C. Kimlik No : {b}", "son sayfa",
        ])
        from isle import _birlestirme_isle
        arsiv3 = Arsiv.yukle(kok)
        eylem, plan = _birlestirme_isle(iki, arsiv3, None)
        esit(eylem.tur, "ayrildi", "çok kimlikli ayrılır")
        esit(plan is not None, True, "bölme planı döner")
        esit(dosya_ozeti(iki) in arsiv3.hashler, True, "asıl alınır alınmaz hash işaretli")
        arsiv3.uygula([eylem], kuru_calistir=False)
        esit(eylem.hedef.exists(), True, "asıl ayrildi/asil altında")
        esit(dosya_ozeti(eylem.hedef) in Arsiv.yukle(kok).hashler, True,
             "asıl hash kesintide diskte")


def sina_r8_tespit() -> None:
    """R8: birden fazla TC veya birden fazla sicil adayı; Sicil No : TESPİT only."""
    from isle import _birlestirme_isle, _cok_kimlikli

    a, b = tc_uret("111111111"), tc_uret("222222222")
    with tempfile.TemporaryDirectory() as gecici:
        kok = Path(gecici)

        iki_tc = kok / "iki_tc.pdf"
        pdf_uret(iki_tc, [f"T.C. Kimlik No : {a}", f"T.C. Kimlik No : {b}"])
        esit(_cok_kimlikli(iki_tc), True, "iki TC → çok kimlikli")

        # Bir TC + iki farklı sicil (DN ve Sicil No :). İkinci kişi yoksa
        # sessiz arşiv değil, bolunmeli.
        bir_tc_iki_sicil = kok / "bir_tc_iki_sicil.pdf"
        pdf_uret(bir_tc_iki_sicil, [
            f"DN47789  T.C. Kimlik No : {a}",
            "Sicil No : 35197",
        ])
        esit(_cok_kimlikli(bir_tc_iki_sicil), True, "bir TC + iki sicil → çok kimlikli")
        arsiv = Arsiv.yukle(kok)
        eylem, plan = _birlestirme_isle(bir_tc_iki_sicil, arsiv, None)
        esit(eylem.tur, "bolunmeli", "ikinci kişi yoksa bolunmeli")
        esit(plan is None, True, "bölünemez, plan yok")

        # Yalnız "Sicil No : 35197" — tespit eder, çıkarıcı sicil_no BOŞ bırakır.
        yalniz = kok / "sicil_etiket.pdf"
        pdf_uret(yalniz, ["Sicil No : 35197"])
        esit(sicil_adaylari("Sicil No : 35197"), {"35197"}, "Sicil No : aday")
        esit(sicil_adaylari("Sicil No: 35197"), {"35197"}, "Sicil No: aday")
        esit(sicil_adaylari("Sicil No  35197"), {"35197"}, "Sicil No boşluklu aday")
        alanlar = cikar(yalniz)
        esit(alanlar.sicil_no, "", "cikar() Sicil No : etiketini sicil_no yapmaz")
        esit(_cok_kimlikli(yalniz), False, "tek sicil adayı çok kimlikli değil")

        tek = kok / "tek.pdf"
        pdf_uret(tek, [f"DN47789  T.C. Kimlik No : {a}\nEsnaf Sicil No: 32/47789"])
        esit(_cok_kimlikli(tek), False, "aynı sicilin DN+32/ tek aday")


def sina_dogrula_sozlesme() -> None:
    """Onayda hash hedefi yeni arşiv adı; boş isim okunamadi/orijinal; kuru taşımaz."""
    from araclar.dogrula import birlestir

    with tempfile.TemporaryDirectory() as gecici:
        kok = Path(gecici)
        kuyruk = kok / DOGRULANMALI
        kuyruk.mkdir()
        pdf_uret(kuyruk / "mehmet_ginar.pdf", ["onay belgesi"])
        pdf_uret(kuyruk / "okunamayan.pdf", ["okunamayan belge"])

        arsiv = Arsiv.yukle(kok)
        arsiv.dogrulanmali_veri = {
            "mehmet_ginar.pdf": {
                "isim_onerisi": "Mehmet Ginar", "tc_no": "", "sicil_no": "",
                "kaynak": "bolum_001.pdf",
            },
            "okunamayan.pdf": {
                "isim_onerisi": "???", "tc_no": "", "sicil_no": "",
                "kaynak": "bolum_002.pdf",
            },
        }
        arsiv.hashler = {
            "h1": {"kaynak": "bolum_001.pdf", "hedef": "mehmet_ginar.pdf"},
            "h2": {"kaynak": "bolum_002.pdf", "hedef": "okunamayan.pdf"},
        }
        arsiv.kaydet()

        esit(kaynaktan_bul("bolum_001.pdf", kok).name, "mehmet_ginar.pdf",
             "kaynaktan_bul dogrulanmali'yi görür")

        csv_yol = kok / "dogrulama.csv"
        csv_yol.write_text(
            "dosya,DOGRU_ISIM\nmehmet_ginar.pdf,Ahmet Yılmaz\nokunamayan.pdf,\n",
            encoding="utf-8",
        )

        birlestir(str(csv_yol), uygula=False, kok=kok, vlm=False)
        esit((kok / ARSIVLE).exists(), False, "kuru birleştirmede taşıma yok")
        esit((kuyruk / "mehmet_ginar.pdf").exists(), True, "kuru kuyruğu bozmaz")
        esit((kuyruk / "okunamayan.pdf").exists(), True, "kuru okunamayanı taşımaz")

        birlestir(str(csv_yol), uygula=True, kok=kok, vlm=False)
        esit((kok / ARSIVLE / "ahmet_yilmaz.pdf").exists(), True, "onay arşive gider")
        esit((kuyruk / "mehmet_ginar.pdf").exists(), False, "onay kuyruktan düşer")
        esit((kok / OKUNAMADI / "bolum_002.pdf").exists(), True,
             "boş isim okunamadi/orijinal ad")
        esit((kuyruk / "okunamayan.pdf").exists(), False, "okunamayan kuyruktan düşer")

        arsiv2 = Arsiv.yukle(kok)
        esit(arsiv2.hashler["h1"]["kaynak"], "bolum_001.pdf", "hash kaynağı orijinal kalır")
        esit(arsiv2.hashler["h1"]["hedef"], "ahmet_yilmaz.pdf", "hash hedefi yeni arşiv adı")
        esit(arsiv2.hashler["h2"]["kaynak"], "bolum_002.pdf", "okunamadi kaynağı orijinal")
        esit(arsiv2.hashler["h2"]["hedef"], "bolum_002.pdf", "okunamadi hedefi orijinal ad")
        esit("mehmet_ginar.pdf" in arsiv2.dogrulanmali_veri, False, "onay kuyruk JSON'dan çıkar")
        esit("okunamayan.pdf" in arsiv2.dogrulanmali_veri, False, "okunamayan kuyruk JSON'dan çıkar")
        esit("AHMET_YILMAZ" in arsiv2.person_data, True, "onay person_data'ya girer")
        esit(kaynaktan_bul("bolum_001.pdf", kok).name, "ahmet_yilmaz.pdf",
             "onay sonrası kaynaktan_bul arşiv adı")


def sina_cikarici() -> None:
    """OCR çıkarıcı: etiketli TC, DN↔32/ sicil, boşluksuz isim."""
    tc = tc_uret("123456789")
    with tempfile.TemporaryDirectory() as gecici:
        yol = Path(gecici) / "form.pdf"
        belge = pymupdf.open()
        sayfa = belge.new_page()
        sayfa.insert_text((72, 50), "DN47789", fontsize=11)
        sayfa.insert_text((72, 80), "Esnaf ve Sanatkar Sicil No: 32/47789", fontsize=11)
        sayfa.insert_text((72, 120), "Adı Soyadı : AYSENURDEMIR", fontsize=11)
        sayfa.insert_text((72, 160), f"T.C. Kimlik No : {tc}", fontsize=11)
        belge.save(yol)
        belge.close()

        alanlar = cikar(yol)
        esit(alanlar.sicil_no, "47789", "cikar sicil DN↔32/")
        esit(alanlar.tc_no, tc, "cikar etiketli TC")
        esit(alanlar.isim_bosluksuz.replace(" ", ""), "AYSENURDEMIR", "cikar isim")
        esit(bool(alanlar.isim_kutusu), True, "isim kutusu var")
        esit(bool(alanlar.tc_kutusu), True, "TC kutusu var")


def sina_sicil_desen() -> None:
    """Sicil aday desenleri: DN, 32/, Sicil No; 4–5 hane; önek elemesi."""
    esit(sicil_adaylari("DN47789"), {"47789"}, "DN aday")
    esit(sicil_adaylari("32/47789"), {"47789"}, "32/ aday")
    esit(sicil_adaylari("Sicil No : 35197"), {"35197"}, "Sicil No : aday")
    esit(sicil_adaylari("DN47789 ve 32/47789"), {"47789"}, "aynı numara tek aday")
    esit(sicil_adaylari("DN47789 Sicil No : 35197"), {"47789", "35197"}, "iki farklı sicil")
    esit(sicil_adaylari("DN46488 ve 32/4648"), {"46488"}, "önek kesik okuma elenir")
    esit(sicil_adaylari("DN123"), set(), "3 hane aday değil")
    esit(sicil_adaylari("DN123456"), set(), "6 hane aday değil")


def sina_birlestir() -> None:
    """VLM+OCR birleştirme: boşluk ve işaret birleşir, çöp OCR ayrı senaryo."""
    esit(birlestir("AYSE NUR DEMIR", "AYSENURDEMIR"), "AYSE NUR DEMIR",
         "boşluk VLM'den korunur")
    esit(birlestir("SEZAI COBAN", "SEZAİÇOBAN"), "SEZAİ ÇOBAN",
         "işaret OCR'dan, boşluk VLM'den")
    esit(birlestir("ILKER YILMAZ", "İLKER YILMAZ"), "İLKER YILMAZ",
         "OCR işareti VLM'e aktarılır")
    esit(birlestir("AHMET YILMAZ", ""), "AHMET YILMAZ", "OCR boşsa VLM kalır")
    esit(birlestir("", "AHMETYILMAZ"), "AHMETYILMAZ", "VLM boşsa OCR kalır")
    esit(isim_makul_mu("AYSENURDEMIR"), True, "temiz OCR isim makul")
    esit(isim_makul_mu("Reıaİİş.?'#\"'X?H.,J??:İi}'3İŞ"), False, "çöp OCR makul değil")

    from isle import _birlestir_guvenli
    cop = "Reıaİİş.?'#\"'X?H.,J??:İi}'3İŞ"
    esit(_birlestir_guvenli("IZZET GOKTAS", cop), "IZZET GOKTAS",
         "çöp OCR'da VLM/uzlaşan ham kalır")
    esit(_birlestir_guvenli("AYSE NUR", "AYSENUR"), "AYSE NUR",
         "makul OCR'da birleştirme açık")
    esit(_birlestir_guvenli("", cop), "",
         "çöp OCR ve boş VLM isim üretmez")


def sina_model_kanca() -> None:
    """--model / VLM_MODEL varsayılanı değiştirmez; önbellek modele göre ayrılır."""
    import os

    esit(argv_model(["ornekler", "--vlm"]), None, "argv_model yok")
    esit(argv_model(["--vlm", "--model", "mlx-community/X"]),
         "mlx-community/X", "argv_model --model")
    esit(secilen_model(None), VARSAYILAN_MODEL, "secilen_model varsayılan")
    esit(secilen_model("mlx-community/X"), "mlx-community/X", "secilen_model istek")
    eski = os.environ.get("VLM_MODEL")
    os.environ["VLM_MODEL"] = "mlx-community/Y"
    try:
        esit(secilen_model(None), "mlx-community/Y", "secilen_model ortam")
        esit(secilen_model("mlx-community/X"), "mlx-community/X",
             "istek ortamdan önce")
    finally:
        if eski is None:
            os.environ.pop("VLM_MODEL", None)
        else:
            os.environ["VLM_MODEL"] = eski
    temel = Path("altin_set_elyazisi/_vlm_okumalari.json")
    onb_eski = os.environ.pop("VLM_ONBELLEK", None)
    try:
        esit(onbellek_yolu(temel, ["olc_elyazisi.py"]), temel,
             "varsayılan önbellek aynı dosya")
        esit(
            onbellek_yolu(temel, ["--model", "mlx-community/InternVL3-14B-4bit"]),
            Path("altin_set_elyazisi/_vlm_okumalari__mlx-community_InternVL3-14B-4bit.json"),
            "başka model ayrı önbellek",
        )
    finally:
        if onb_eski is not None:
            os.environ["VLM_ONBELLEK"] = onb_eski


def sina_cikti_uyari() -> None:
    """--cikti kökü değiştirir; CWD varsayılanı bozulmaz; uyarilar rapora geçer."""
    from isle import _alanlari_topla, main as isle_main

    with tempfile.TemporaryDirectory() as gecici:
        kok = Path(gecici)
        girdi = kok / "girdi"
        cikti = kok / "cikti"
        girdi.mkdir()
        pdf_uret(girdi / "ahmet.pdf", ["Adı Soyadı : AHMETYILMAZ"])
        isle_main([str(girdi), "--uygula", "--cikti", str(cikti)])
        esit((cikti / "person_data.json").exists(), True, "--cikti JSON yazar")
        esit((girdi / "ahmet.pdf").exists(), False, "kaynak --cikti köküne taşındı")
        esit((cikti / ARSIVLE / "ahmetyilmaz.pdf").exists()
             or (cikti / OKUNAMADI / "ahmet.pdf").exists(), True,
             "--cikti belgeyi köke taşır")

        yalniz = kok / "sicil.pdf"
        pdf_uret(yalniz, ["Sicil No : 35197"])
        sonuc = _alanlari_topla(yalniz, None)
        esit(bool(sonuc.uyarilar), True, "Sonuc.uyarilar dolu")
        arsiv = Arsiv.yukle(kok / "arsiv2")
        eylem = arsiv.planla(yalniz, sonuc)
        esit(bool(eylem.uyarilar), True, "Eylem.uyarilar planla'dan gelir")


def sina_bos_sayfa() -> None:
    """Beyaz boş sayfa elenir; dolu sayfa ve nüfus fotokopisi elenmez."""
    from belge.pdf_okuyucu import bos_sayfa_mi

    with tempfile.TemporaryDirectory() as gecici:
        yol = Path(gecici) / "sayfalar.pdf"
        belge = pymupdf.open()
        belge.new_page()  # beyaz
        dolu = belge.new_page()
        dolu.insert_text((72, 100), "Adı Soyadı : AHMET YILMAZ " * 4, fontsize=11)
        fotokopi = belge.new_page()
        fotokopi.insert_text((72, 50), "T.C.", fontsize=10)
        fotokopi.draw_rect(pymupdf.Rect(200, 80, 380, 280), color=(0.15, 0.15, 0.15),
                           fill=(0.2, 0.2, 0.2))
        belge.save(yol)
        belge.close()

        with pymupdf.open(yol) as b:
            esit(bos_sayfa_mi(b[0]), True, "beyaz sayfa boş")
            esit(bos_sayfa_mi(b[1]), False, "dolu sayfa boş değil")
            esit(bos_sayfa_mi(b[2]), False, "nüfus fotokopisi elenmez")

        # Bölme haritasında boş sayfa '?' olur, PDF'den silinmez.
        a = tc_uret("111111111")
        karisik = Path(gecici) / "boslu.pdf"
        belge = pymupdf.open()
        s1 = belge.new_page()
        s1.insert_text((72, 100), f"T.C. Kimlik No : {a}", fontsize=11)
        belge.new_page()  # boş
        s3 = belge.new_page()
        s3.insert_text((72, 100), f"T.C. Kimlik No : {a}", fontsize=11)
        belge.save(karisik)
        belge.close()
        plan = plan_cikar(karisik, a)
        esit("?" not in plan.harita, True, "tek kişide boş sayfa artık ? değil, mirasla dolar")
        esit(plan.harita, "AAA", "boş sayfa komşu A'dan miras alır")
        esit(len(plan.harita), 3, "sayfa silinmez, harita 3 uzunluk")

def sina_hata() -> None:
    """Belge hatası koşuyu durdurmaz; uygula ise hata/ + hash."""
    from isle import main as isle_main

    with tempfile.TemporaryDirectory() as gecici:
        kok = Path(gecici)
        girdi = kok / "girdi"
        cikti = kok / "cikti"
        girdi.mkdir()
        (girdi / "bozuk.pdf").write_bytes(b"%PDF-1.4 not a real pdf")
        pdf_uret(girdi / "iyi.pdf", ["Adı Soyadı : AHMETYILMAZ"])
        isle_main([str(girdi), "--uygula", "--cikti", str(cikti)])
        esit((cikti / HATA / "bozuk.pdf").exists(), True, "bozuk hata/ altına")
        esit((cikti / ARSIVLE / "ahmetyilmaz.pdf").exists()
             or (cikti / OKUNAMADI / "iyi.pdf").exists(), True,
             "sağlam belge hata yüzünden durmaz")
        arsiv = Arsiv.yukle(cikti)
        esit(any(v.get("kaynak") == "bozuk.pdf" for v in arsiv.hashler.values()),
             True, "hata hash işaretli")

        girdi2 = kok / "girdi2"
        girdi2.mkdir()
        pdf_uret(girdi2 / "x.pdf", ["Adı Soyadı : DENEME KISI"])
        from unittest.mock import patch

        def patla(*_a, **_k):
            raise MemoryError("sim")

        try:
            with patch("isle._alanlari_topla", patla):
                isle_main([str(girdi2), "--cikti", str(kok / "cikti2")])
            esit("yakalandı", "fırlatmalıydı", "MemoryError yakalanmaz")
        except MemoryError:
            esit(True, True, "MemoryError yakalanmaz")


def sina_kati_uyari() -> None:
    from isle import _kati_uyarisi

    esit(bool(_kati_uyarisi(True, False, False)), True, "vlm+uygula, kati yok → uyarı")
    esit(_kati_uyarisi(True, True, False), "", "kati açıkken uyarı yok")
    esit(_kati_uyarisi(True, False, True), "", "kuru kipte uyarı yok")
    esit(_kati_uyarisi(False, False, False), "", "vlm yokken uyarı yok")


def sina_web_plan_json() -> None:
    """Bölme planı web API'nin beklediği JSON anahtarlarını taşır."""
    import json

    from isle import Sonuc, belge_analiz, kova_oner
    from web.pdf_islem import pdfleri_birlestir, sayfalari_al, sayfalari_cikar

    a, b = tc_uret("111111111"), tc_uret("222222222")
    with tempfile.TemporaryDirectory() as gecici:
        kok = Path(gecici)
        temiz = kok / "temiz.pdf"
        pdf_uret(temiz, [
            f"T.C. Kimlik No : {a}", "ara sayfa", f"T.C. Kimlik No : {a}",
            f"T.C. Kimlik No : {b}", "son sayfa",
        ])
        plan = plan_cikar(temiz, a)
        d = plan_sozluge(plan)
        for anahtar in ("harita", "birincil", "ikincil", "bolunebilir",
                        "gerekce", "bloklar", "sayfalar"):
            esit(anahtar in d, True, f"plan json {anahtar}")
        esit(d["harita"], "AAABB", "json harita")
        esit(d["bolunebilir"], True, "json bolunebilir")
        esit(d["birincil"], a, "json birincil")
        esit(d["ikincil"], b, "json ikincil")
        esit(d["bloklar"], [{"kim": "A", "ilk": 1, "son": 3},
                            {"kim": "B", "ilk": 4, "son": 5}], "json bloklar")
        esit(len(d["sayfalar"]), 5, "json sayfa sayısı")
        esit(d["sayfalar"][0]["no"], 1, "json ilk sayfa no")
        esit(d["sayfalar"][0]["oneri"], "A", "json ilk sayfa öneri")
        esit(d["sayfalar"][0]["sahip"], "A", "json ilk sayfa sahip")
        esit(d["sayfalar"][0]["tc"], a, "json ilk sayfa TC")
        esit(d["sayfalar"][3]["sahip"], "B", "json dördüncü sahip B")
        json.dumps(d, ensure_ascii=False)
        esit(True, True, "plan json serileşir")

        # Kullanıcı ataması: bitişik olmayan A sayfaları tek PDF.
        harita = "AXABA"
        kp = kullanici_plani(harita, a, b)
        esit(kp.bolunebilir, True, "kullanıcı planı bölünebilir")
        kp_bos = kullanici_plani("A?A", a)
        esit(kp_bos.bolunebilir, False, "atanmamış sayfa bölünmez")
        gruplar = plan_gruplari("AABXA")
        esit(gruplar["A"], [1, 2, 5], "grup A bitişik değil")
        esit(gruplar["X"], [4], "grup X")
        yazilan = sayfalari_yaz(temiz, gruplar, kok / "parca", kuru_calistir=False)
        with pymupdf.open(yazilan["A"]) as belge:
            esit(len(belge), 3, "A parçası 3 sayfa")
        with pymupdf.open(yazilan["B"]) as belge:
            esit(len(belge), 1, "B parçası 1 sayfa")

        sonuc, cok, plan2 = belge_analiz(temiz, None)
        esit(cok, True, "analiz çok kimlik")
        esit(plan2 is not None, True, "analiz plan üretir")
        esit(kova_oner(sonuc, True, kati=True), "incele", "çok kimlik incele")
        esit(kova_oner(Sonuc(isim="ALI", uzlasma=0), False, kati=True),
             "incele", "katı + uzlaşma yok incele")
        esit(kova_oner(Sonuc(isim="ALI", uzlasma=2), False, kati=True),
             "arsivlenecek", "uzlaşan arşivlenecek")

        # Birleştir / ayır sayfa korunumu.
        p1, p2 = kok / "p1.pdf", kok / "p2.pdf"
        pdf_uret(p1, ["bir", "iki"])
        pdf_uret(p2, ["uc"])
        birlesik = kok / "birlesik.pdf"
        pdfleri_birlestir([(p1, [2, 1]), (p2, [1])], birlesik)
        with pymupdf.open(birlesik) as belge:
            esit(len(belge), 3, "birleşik 3 sayfa")
            esit("iki" in belge[0].get_text(), True, "birleşik sıra 2-1-3")
        kalan = kok / "kalan.pdf"
        sayfalari_cikar(birlesik, [2], kalan)
        with pymupdf.open(kalan) as belge:
            esit(len(belge), 2, "çıkarınca 2 sayfa")
        alinan = kok / "alinan.pdf"
        sayfalari_al(birlesik, [1, 3], alinan)
        with pymupdf.open(alinan) as belge:
            esit(len(belge), 2, "alınan 2 sayfa")


def sina_web_incele_alan() -> None:
    """İnceleme masası: isim/TC/sicil taslak; boş isim okunamadi; ata kırılmaz."""
    from web.kuyruk import Durum

    tc = tc_uret("123456789")
    with tempfile.TemporaryDirectory() as gecici:
        d = Durum(Path(gecici))
        pdf = Path(gecici) / "kaynak.pdf"
        pdf_uret(pdf, ["sayfa bir", "sayfa iki"])
        icerik = pdf.read_bytes()
        b = d.yukle("deneme.pdf", icerik)
        with d.kilit:
            b.durum = "bitti"
            b.kova = "incele"
            b.neden = "dogrulanmali"
        d.isim_duzelt(b.id, "Ali Veli")
        esit(d.belge_ayrinti(b.id)["isim"], "Ali Veli", "isim_duzelt yalnız isim")
        d.isim_duzelt(b.id, "Ali Veli", tc_no=tc, sicil_no="47789")
        ayr = d.belge_ayrinti(b.id)
        esit(ayr["tc_no"], tc, "isim_duzelt tc")
        esit(ayr["sicil_no"], "47789", "isim_duzelt sicil")
        d.isim_duzelt(b.id, "Ali Veli Yeni")
        esit(d.belge_ayrinti(b.id)["tc_no"], tc, "tc yokken silinmez")
        d.ata(b.id, ["A", "X"])
        esit(d.belge_ayrinti(b.id)["atama"], ["A", "X"], "ata sayfa")
        esit(d.belgeler[b.id].cok_kimlik, True, "karışık atama çok kimlik")

        b2 = d.yukle("okunamayan.pdf", icerik)
        with d.kilit:
            b2.durum = "bitti"
            b2.kova = "incele"
            b2.neden = "dogrulanmali"
        d.isim_duzelt(b2.id, "")
        d.atla(b2.id)
        son = d.arsivle([b2.id])
        esit(not son[0].get("hata"), True, "atla arşivlenir")
        esit(d.belgeler[b2.id].kova, OKUNAMADI, "boş isim okunamadi")


def sina_kirpma_yedek() -> None:
    """Yedek kırpma etiket çıpalıdır; OCR değer kutusu VLM'e gitmez."""
    from belge.alan_cikarici import ETIKET_AD, etiket_degeri, etiket_kutusu
    from isle import _yedek_kirpma_kutusu

    with tempfile.TemporaryDirectory() as gecici:
        yol = Path(gecici) / "etiket.pdf"
        belge = pymupdf.open()
        sayfa = belge.new_page()
        sayfa.insert_text((72, 100), "Adı Soyadı", fontsize=14)
        sayfa.insert_text((400, 100), "XXXX", fontsize=14)
        belge.save(yol)
        belge.close()

        yedek = _yedek_kirpma_kutusu(yol, 1)
        esit(yedek is not None, True, "yedek kutu üretildi")
        esit(yedek[0] < 100, True, "yedek etiket solundan başlar")
        esit(yedek[2] > 400, True, "yedek satırın sağına uzanır")

        with pymupdf.open(yol) as b:
            deger, deger_kutu = etiket_degeri(b[0], ETIKET_AD)
            ek = etiket_kutusu(b[0], ETIKET_AD)
        esit(deger.replace(" ", "").startswith("XXXX") or "XXXX" in deger, True,
             "değer kutusu XXXX'i görür")
        if deger_kutu is not None:
            esit(yedek[0] < deger_kutu[0], True, "yedek değer kutusundan solda")
        if ek is not None:
            esit(abs(yedek[0] - (ek[0] - 2)) < 1 or yedek[0] <= ek[0], True,
                 "yedek etiket kutusuna çıpalı")


def main() -> int:
    for sina in (sina_adlandirma, sina_checksum, sina_arsivleme,
                 sina_kati_kip, sina_bolme, sina_kesinti, sina_r8_tespit,
                 sina_dogrula_sozlesme, sina_cikarici, sina_sicil_desen,
                 sina_birlestir, sina_model_kanca, sina_cikti_uyari, sina_bos_sayfa,
                 sina_hata, sina_kati_uyari, sina_web_plan_json, sina_web_incele_alan,
                 sina_kirpma_yedek):
        sina()
    print(f"{_gecti} sınama geçti, {len(_kaldi)} kaldı")
    for satir in _kaldi:
        print(f"  KALDI  {satir}")
    return 1 if _kaldi else 0


if __name__ == "__main__":
    sys.exit(main())

def sina_miras_doldur() -> None:
    from belge.bolucu import _miras_doldur, SAYFA_TURU_EK, SAYFA_TURU_SAHIPLI

    turler = [SAYFA_TURU_SAHIPLI, SAYFA_TURU_EK, SAYFA_TURU_SAHIPLI]
    sahipler = ["A", None, "A"]
    esit(_miras_doldur(sahipler, turler), ["A", "A", "A"], "araya giren boş sayfa mirasla dolar")

    # Belgenin başında boş sayfa: sonraki sahipten alır
    esit(_miras_doldur([None, "A"], [SAYFA_TURU_EK, SAYFA_TURU_SAHIPLI]),
         ["A", "A"], "baştaki boş sayfa sonrakinden miras alır")

    # Gerçek içerikli B sayfası hâlâ ayrı kalmalı (SUPHELI/SAHIPLI etkilenmez)
    turler2 = [SAYFA_TURU_SAHIPLI, SAYFA_TURU_SAHIPLI, SAYFA_TURU_SAHIPLI]
    esit(_miras_doldur(["A", "B", "A"], turler2), ["A", "B", "A"],
         "gerçek B sayfası mirasla ezilmez")
    
    def sina_kisi_esleme() -> None:
        from belge.kisi_esleme import kisi_esleme_onerisi

        veri = {
            "AHMET_YILMAZ": [{"isim": "Ahmet Yılmaz"}],
            "MEHMET_KAYA": [{"isim": "Mehmet Kaya"}],
        }
        o = kisi_esleme_onerisi("AHMETYLMAZ", veri)  # OCR bir harf düşürmüş
        esit(o is not None, True, "yakın isim önerilir")
        esit(o.anahtar, "AHMET_YILMAZ", "doğru aday seçilir")
        esit(o.belirsiz, False, "tek aday belirsiz değil")
        esit(kisi_esleme_onerisi("BAMBASKA ISIM ISTE", veri), None, "uzak isim önerilmez")

        # iki farklı kişi aynı mesafede -> belirsiz, hiçbiri otomatik seçilmez
        cakisan = {
            "AHMET YILMAZ": [{"isim": "Ahmet Yılmaz"}],
            "AHMET YILDIR": [{"isim": "Ahmet Yıldır"}],
        }
        o2 = kisi_esleme_onerisi("AHMET YILDAR", cakisan)
        esit(o2.belirsiz, True, "eşit mesafeli farklı kişiler belirsiz sayılır")