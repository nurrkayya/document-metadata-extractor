"""Arşivleme, `person_data.json` ve mükerrer atlama (SPEC 4.2–4.5).

Bu modül **planlar ve uygular, ama karar vermez**: hangi belgenin nereye
gideceği `alan_cikarici` + `sayi_okuyucu` sonuçlarından çıkar, burada yalnızca
o karar dosya sistemine yazılır.

Kuru çalıştırma
---------------
Arşivleme geri alması zor tek adım (SPEC Adım 7): dosyaları taşıyor. Bu yüzden
plan üretimi ile uygulama **ayrı**. `planla()` hiçbir şeye dokunmaz, ne
yapılacağını döndürür; `uygula()` yazar. CLI varsayılan olarak yalnızca
planlar.

Durumun bellekte tutulması
--------------------------
Çakışma çözümü ve mükerrer tespiti bütün koşuya bakmayı gerektiriyor: aynı
koşuda iki `ahmet_yilmaz` gelirse ikincisi `ahmet_yilmaz_2` olmalı, ve bu
kuru kipte de doğru raporlanmalı. Bu yüzden ad/hash kümeleri bellekte
biriktirilir ve plan üretilirken güncellenir — dosya yazılmasa bile.
"""

from __future__ import annotations

import hashlib
import json
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from belge.adlandirma import cakismasiz, dosya_adi, json_anahtari
from belge.yollar import (
    ARSIV as ARSIVLE,
    AYRILDI,
    BOLUNMELI,
    DOGRULANMALI,
    HATA,
    ILGISIZ,
    OKUNAMADI,
    cikti_klasorlerini_hazirla,
)

PERSON_DATA = "person_data.json"
# Doğrulanmamış okumaların çıkarılan alanları. person_data.json'a GİRMEZ --
# oraya yalnız doğrulanmış kayıtlar yazılır. Ama tc_no ve sicil_no isimden
# bağımsız doğrulanıyor (checksum, çapraz kontrol) ve atılmaları saatlerce
# süren bir koşunun bir kısmını çöpe atmak olur. İnsan ismi düzelttiğinde
# bu dosyadan devralınır.
DOGRULANMALI_VERI = "dogrulanmali.json"
HASH_KAYDI = ".islenmis_hashler.json"

# Eylem türleri (klasör adlarıyla aynı; tek kaynak: belge.yollar)
ATLA = "atlandi"


@dataclass
class Eylem:
    kaynak: Path
    tur: str
    hedef: Path | None = None
    kayit: dict[str, str] | None = None
    not_: str = ""
    uyarilar: list[str] = field(default_factory=list)


@dataclass
class Arsiv:
    kok: Path
    person_data: dict[str, list[dict]] = field(default_factory=dict)
    # dosya adı -> çıkarılan alanlar (doğrulanmamış)
    dogrulanmali_veri: dict[str, dict] = field(default_factory=dict)
    # hash -> {"kaynak": orijinal ad, "hedef": arşivdeki ad}
    # Yalnız hedef saklansaydı koşu geri alınamazdı: arşivdeki dosyanın hangi
    # tarama bölümünden geldiği bilinemez, çünkü ad tamamen değişiyor.
    hashler: dict[str, dict[str, str]] = field(default_factory=dict)
    kullanilan_adlar: set[str] = field(default_factory=set)

    @classmethod
    def yukle(cls, kok: Path | str) -> Arsiv:
        kok = Path(kok)
        arsiv = cls(kok=kok)
        pd = kok / PERSON_DATA
        if pd.exists():
            arsiv.person_data = json.loads(pd.read_text(encoding="utf-8"))
        dv = kok / DOGRULANMALI_VERI
        if dv.exists():
            arsiv.dogrulanmali_veri = json.loads(dv.read_text(encoding="utf-8"))
        hk = kok / HASH_KAYDI
        if hk.exists():
            arsiv.hashler = json.loads(hk.read_text(encoding="utf-8"))
        # Zaten arşivde duran adlar çakışma havuzuna katılır; yoksa ikinci
        # koşu birinci koşunun dosyalarının üzerine yazardı.
        # Ad havuzuna hem arşiv hem doğrulanmalı katılır: ikisi ayrı klasör
        # ama aynı ad uzayını paylaşıyor -- bir belge kuyruktan arşive
        # geçtiğinde çakışma çıkmasın.
        for klasor in (ARSIVLE, DOGRULANMALI):
            d = kok / klasor
            if d.exists():
                arsiv.kullanilan_adlar |= {p.stem for p in d.glob("*.pdf")}
        return arsiv

    def planla(
        self, pdf_yolu: Path | str, alanlar: object, kati: bool = False
    ) -> Eylem:
        """Bir belge için ne yapılacağını belirler. Hiçbir şeye dokunmaz.

        alanlar: `isim`, `tc_no`, `sicil_no` niteliklerini taşıyan sonuç
        nesnesi (`CikarilanAlanlar` ya da benzeri).
        kati   : açıkken, sayfalar arası uzlaşma sağlanamamış okumalar
                 arşive girmez; `dogrulanmali/` kuyruğuna alınır. Alanlar
                 nesnesi `uzlasma` sayısını taşımalı.
        """
        kaynak = Path(pdf_yolu)
        uyarilar = list(getattr(alanlar, "uyarilar", []) or [])
        ozet = dosya_ozeti(kaynak)
        m_ozet = metin_ozeti(kaynak)
        # İki özetten biri tutarsa mükerrer: dosya özeti birebir kopyayı,
        # metin özeti yeniden dışa aktarılmış kopyayı yakalar.
        for anahtar in (ozet, m_ozet):
            if anahtar and anahtar in self.hashler:
                onceki = self.hashler[anahtar]
                return Eylem(
                    kaynak=kaynak,
                    tur=ATLA,
                    not_=f"aynı içerik daha önce işlendi ({onceki['hedef']})",
                    uyarilar=uyarilar,
                )

        isim = (getattr(alanlar, "isim", "") or "").strip()
        taban = dosya_adi(isim)
        if not taban:
            # İsim yoksa dosya adı üretilemez; belge orijinal adıyla ayrılır.
            self._isaretle(ozet, m_ozet, kaynak.name, kaynak.name)
            return Eylem(
                kaynak=kaynak,
                tur=OKUNAMADI,
                hedef=self.kok / OKUNAMADI / kaynak.name,
                not_="isim okunamadı",
                uyarilar=uyarilar,
            )

        # Katı kipte doğrulanmamış okuma arşive girmez. Dosya adı yine model
        # önerisiyle kurulur -- insan sıfırdan okumak yerine öneriyi
        # doğrulasın diye.
        if kati and getattr(alanlar, "uzlasma", 0) < 2:
            # Çakışma çözümü BURADA DA gerekli. Unutulmuştu ve iki belge
            # üzerine yazılıp kalıcı olarak kayboldu (250 belgelik koşu,
            # sadeddin_kul ve verildigi_tarih adlarında ikişer belge).
            ad = cakismasiz(taban, self.kullanilan_adlar)
            self.kullanilan_adlar.add(ad)
            self._isaretle(ozet, m_ozet, kaynak.name, f"{ad}.pdf")
            kayit = {
                "isim_onerisi": isim,
                "tc_no": getattr(alanlar, "tc_no", "") or "",
                "sicil_no": getattr(alanlar, "sicil_no", "") or "",
                "kaynak": kaynak.name,
            }
            self.dogrulanmali_veri[f"{ad}.pdf"] = kayit
            return Eylem(
                kaynak=kaynak,
                tur=DOGRULANMALI,
                hedef=self.kok / DOGRULANMALI / f"{ad}.pdf",
                kayit=kayit,
                not_="sayfalar arası uzlaşma yok, doğrulanmalı",
                uyarilar=uyarilar,
            )

        ad = cakismasiz(taban, self.kullanilan_adlar)
        self.kullanilan_adlar.add(ad)
        self._isaretle(ozet, m_ozet, kaynak.name, f"{ad}.pdf")

        kayit = {
            "isim": isim,
            "tc_no": getattr(alanlar, "tc_no", "") or "",
            "sicil_no": getattr(alanlar, "sicil_no", "") or "",
        }
        anahtar = json_anahtari(isim)
        self.person_data.setdefault(anahtar, []).append(kayit)

        return Eylem(
            kaynak=kaynak,
            tur=ARSIVLE,
            hedef=self.kok / ARSIVLE / f"{ad}.pdf",
            kayit=kayit,
            uyarilar=uyarilar,
        )

    def hata_planla(self, pdf_yolu: Path | str, gerekce: str) -> Eylem:
        """İşlenemeyen belge: hash işaretlenir, hata/ altına taşınır."""
        kaynak = Path(pdf_yolu)
        try:
            ozet = dosya_ozeti(kaynak)
        except Exception:
            ozet = ""
        try:
            m_ozet = metin_ozeti(kaynak)
        except Exception:
            m_ozet = ""
        self._isaretle(ozet, m_ozet, kaynak.name, kaynak.name)
        return Eylem(
            kaynak=kaynak,
            tur=HATA,
            hedef=self.kok / HATA / kaynak.name,
            not_=gerekce,
        )

    def bolunmeli_planla(self, pdf_yolu: Path | str, gerekce: str) -> Eylem:
        """Otomatik bölünemeyen yanlış birleştirme (SPEC R8, bölüm 6.6)."""
        kaynak = Path(pdf_yolu)
        self._isaretle(dosya_ozeti(kaynak), metin_ozeti(kaynak), kaynak.name, kaynak.name)
        return Eylem(
            kaynak=kaynak,
            tur=BOLUNMELI,
            hedef=self.kok / BOLUNMELI / kaynak.name,
            not_=gerekce,
        )

    def ilgisiz_planla(self, pdf_yolu: Path | str, gerekce: str) -> Eylem:
        """Hiçbir resmi gösterge taşımayan belge — VLM'e hiç gitmeden ayrılır."""
        kaynak = Path(pdf_yolu)
        self._isaretle(dosya_ozeti(kaynak), metin_ozeti(kaynak), kaynak.name, kaynak.name)
        return Eylem(
            kaynak=kaynak,
            tur=ILGISIZ,
            hedef=self.kok / ILGISIZ / kaynak.name,
            not_=gerekce,
        )

    def isaretle(self, pdf_yolu: Path | str, hedef_adi: str) -> None:
        """Belgeyi işlenmiş sayar. Dosya taşımaz; hash bellekte güncellenir."""
        kaynak = Path(pdf_yolu)
        self._isaretle(dosya_ozeti(kaynak), metin_ozeti(kaynak), kaynak.name, hedef_adi)

    def _isaretle(self, ozet: str, m_ozet: str, kaynak: str, hedef: str) -> None:
        """Belgeyi işlenmiş olarak kaydeder; varsa metin özetiyle birlikte."""
        kayit = {"kaynak": kaynak, "hedef": hedef}
        for anahtar in (ozet, m_ozet):
            if anahtar:
                self.hashler[anahtar] = kayit

    def hash_hedef_guncelle(self, eski_hedef: str, yeni_hedef: str, kaynak: str) -> None:
        """Taşınan belgenin hash kaydında hedefi günceller; kaynak orijinal kalır."""
        bulundu = False
        for kayit in self.hashler.values():
            if kayit.get("hedef") == eski_hedef or kayit.get("kaynak") == kaynak:
                kayit["hedef"] = yeni_hedef
                kayit["kaynak"] = kaynak
                bulundu = True
        if not bulundu:
            self.hashler[f"hedef:{eski_hedef}"] = {"kaynak": kaynak, "hedef": yeni_hedef}

    def uygula(self, eylemler: list[Eylem], kuru_calistir: bool = True) -> None:
        """Planı dosya sistemine yazar. Kuru kipte hiçbir şey yapmaz.

        Her başarılı taşımadan sonra JSON/hash diske yazılır: koşu yarıda
        kesilirse biten belgeler kalır, kalanlar sonraki koşuda işlenir.
        """
        if kuru_calistir:
            return
        cikti_klasorlerini_hazirla(self.kok)
        for eylem in eylemler:
            if eylem.tur == ATLA or eylem.hedef is None:
                continue
            eylem.hedef.parent.mkdir(parents=True, exist_ok=True)
            # Üzerine yazma KESİNLİKLE engellenir. shutil.move sessizce
            # üzerine yazıyor; bir ad çakışması hatası yüzünden iki belge
            # böyle kaybedildi. Ad üretimi zaten çakışmayı çözmeli, ama
            # burada da durulur: sessiz veri kaybı yerine gürültülü hata.
            if eylem.hedef.exists():
                raise FileExistsError(
                    f"hedef zaten var, üzerine yazılmayacak: {eylem.hedef}\n"
                    f"  kaynak: {eylem.kaynak}\n"
                    "  ad üretiminde çakışma çözümü atlanmış olabilir."
                )
            # SPEC 4.4: işlenen belge kaynak klasörden taşınır.
            shutil.move(str(eylem.kaynak), str(eylem.hedef))
            self.kaydet()

    def kaydet(self) -> None:
        self.kok.mkdir(parents=True, exist_ok=True)
        (self.kok / PERSON_DATA).write_text(
            json.dumps(self.person_data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        (self.kok / DOGRULANMALI_VERI).write_text(
            json.dumps(self.dogrulanmali_veri, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        (self.kok / HASH_KAYDI).write_text(
            json.dumps(self.hashler, ensure_ascii=False, indent=2), encoding="utf-8"
        )


def kaynaktan_bul(orijinal_ad: str, kok: Path | str = ".") -> Path | None:
    """Orijinal tarama adından belgenin ŞU ANKİ yerini bulur.

    Arşivleme dosyayı taşıyıp yeniden adlandırıyor; ölçüm araçları ise altın
    seti orijinal adla tutuyor. Gerçek koşudan sonra `ornekler/` altında
    hiçbiri kalmadığı için bütün ölçümler kırılmıştı. Hash kaydındaki
    kaynak->hedef eşlemesi bu bağı yeniden kuruyor.

    Bulunamazsa None döner; çağıran belgeyi atlayabilir.
    """
    kok = Path(kok)
    dogrudan = kok / "ornekler" / orijinal_ad
    if dogrudan.exists():
        return dogrudan

    # Bölünen belgelerin ASLI orijinal adıyla ayrildi/asil altında durur ve
    # hash kaydında girdisi yoktur (parçaları kaydedilir, aslı değil).
    asil = kok / AYRILDI / "asil" / orijinal_ad
    if asil.exists():
        return asil

    kayit = kok / HASH_KAYDI
    if not kayit.exists():
        return None
    hashler = json.loads(kayit.read_text(encoding="utf-8"))
    hedefler = {v["hedef"] for v in hashler.values() if v.get("kaynak") == orijinal_ad}
    for hedef in hedefler:
        for klasor in (
            ARSIVLE,
            OKUNAMADI,
            BOLUNMELI,
            DOGRULANMALI,
            HATA,
            ILGISIZ,
            f"{AYRILDI}/asil",
            AYRILDI,
        ):
            aday = kok / klasor / hedef
            if aday.exists():
                return aday
    kuyruk = kok / DOGRULANMALI / orijinal_ad
    if kuyruk.exists():
        return kuyruk
    return None


def dosya_ozeti(yol: Path | str, blok: int = 1 << 20) -> str:
    """Dosya içeriğinin SHA-256 özeti (SPEC 4.5).

    Ad değil içerik esas alınır: aynı belge farklı adla ikinci kez gelirse de
    yakalanmalı.
    """
    ozet = hashlib.sha256()
    with Path(yol).open("rb") as f:
        while parca := f.read(blok):
            ozet.update(parca)
    return ozet.hexdigest()


# Metin özeti bu uzunluğun altındaki belgelerde kullanılmaz: taranmış ama
# metin katmanı zayıf olan belgelerin metni birbirine benzer (hatta boş) olur
# ve hepsi aynı özeti üretip birbirinin mükerreri sanılır.
ASGARI_METIN = 200


def metin_ozeti(yol: Path | str) -> str:
    """Belgenin METİN içeriğinin özeti; kısa metinlerde boş döner.

    Neden dosya özeti yetmiyor: külliyatta aynı belgenin farklı PDF baytlarıyla
    yeniden dışa aktarılmış kopyaları var (aynı sayfalar, aynı metin, farklı
    sıkıştırma). Ölçüldü: 721 dosyada 1 grup, 2 fazlalık kopya. Dosya özeti
    bunların sıfırını yakalıyor; yakalanmazsa tek kişi arşive üç kez girer.
    """
    import pymupdf

    with pymupdf.open(Path(yol)) as belge:
        metin = "".join(sayfa.get_text() for sayfa in belge).strip()
    if len(metin) < ASGARI_METIN:
        return ""
    return hashlib.sha256(metin.encode("utf-8")).hexdigest()