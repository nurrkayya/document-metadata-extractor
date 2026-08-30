"""Oturum durumu ve arka plan iş kuyruğu.

VLM senkron istekte saatlerce tutulmaz: belgeler sırayla bir işçi işler,
istemci job id + poll/SSE ile bakar. MLX aynı işçi ipliğinde yüklenir.
"""

from __future__ import annotations

import os
import platform
import queue
import shutil
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from belge.arsiv import Arsiv
from belge.bolucu import (
    kullanici_plani,
    plan_gruplari,
    plan_sozluge,
    sayfalari_yaz,
)
from belge.islem import Sonuc, belge_analiz, cok_kimlik_gerekce, kova_oner
from belge.yollar import AYRILDI, WEB_CIKTI
from web import pdf_islem

VARSAYILAN_CIKTI = WEB_CIKTI


def cikti_kok() -> Path:
    return Path(os.environ.get("WEB_CIKTI", VARSAYILAN_CIKTI)).resolve()


def vlm_uygun_mu() -> tuple[bool, str]:
    makine = platform.machine().lower()
    if makine not in ("arm64", "aarch64"):
        return False, "VLM Apple Silicon ister; bu makinede yalnız OCR kullanılacak."
    try:
        import mlx  # noqa: F401
        import mlx_vlm  # noqa: F401
    except ImportError:
        return False, "MLX yüklü değil; yalnız OCR kullanılacak."
    return True, ""


@dataclass
class Belge:
    id: str
    ad: str
    yol: Path
    durum: str = "kuyrukta"  # kuyrukta | isleniyor | bitti | hata
    kova: str = ""  # arsivlenecek | incele | okunamadi | hata | ayrildi
    neden: str = ""  # cok_kimlik | dogrulanmali | okunamadi | hata | ""
    isim: str = ""
    tc_no: str = ""
    sicil_no: str = ""
    uzlasma: int = 0
    uyarilar: list[str] = field(default_factory=list)
    cok_kimlik: bool = False
    plan: dict | None = None
    atama: list[str] = field(default_factory=list)
    sayfa_sayisi: int = 0
    hata: str = ""
    gerekce: str = ""
    nesil: int = 1
    not_: str = ""


@dataclass
class IsDurum:
    id: str = ""
    durum: str = "bos"  # bos | yukleniyor | isleniyor | bitti
    biten: int = 0
    toplam: int = 0
    su_an: str = ""
    baslangic: float = 0.0
    eta_sn: float | None = None


class Durum:
    """Tek operatör, tek oturum. Kilit altında okunur/yazılır."""

    def __init__(self, kok: Path | None = None) -> None:
        self.kok = Path(kok) if kok else cikti_kok()
        self.yuklenen = self.kok / "yuklenen"
        self.calisma = self.kok / "calisma"
        self.onizleme = self.kok / "_onizleme"
        self.yuklenen.mkdir(parents=True, exist_ok=True)
        self.calisma.mkdir(parents=True, exist_ok=True)
        self.onizleme.mkdir(parents=True, exist_ok=True)

        self.kilit = threading.Lock()
        self.belgeler: dict[str, Belge] = {}
        self.is_ = IsDurum()
        self.okuyucu = None
        self.vlm_istek = False
        uygun, uyari = vlm_uygun_mu()
        self.vlm_uygun = uygun
        self.vlm_uyari = uyari
        self.vlm_durum = "hazir" if uygun else "yok"
        self.olaylar: queue.Queue = queue.Queue()
        self._is_kuyrugu: queue.Queue = queue.Queue()
        self._isci = threading.Thread(target=self._calis, daemon=True)
        self._isci.start()

    def ozet(self) -> dict:
        with self.kilit:
            say = {"arsivlenecek": 0, "incele": 0, "okunamadi": 0, "hata": 0,
                   "kuyrukta": 0, "ayrildi": 0}
            for b in self.belgeler.values():
                if b.durum == "kuyrukta":
                    say["kuyrukta"] += 1
                elif b.kova in say:
                    say[b.kova] += 1
            is_d = {
                "id": self.is_.id,
                "durum": self.is_.durum,
                "biten": self.is_.biten,
                "toplam": self.is_.toplam,
                "su_an": self.is_.su_an,
                "yuzde": (int(100 * self.is_.biten / self.is_.toplam)
                          if self.is_.toplam else 0),
                "eta_sn": self.is_.eta_sn,
            }
            return {
                "vlm": {
                    "durum": self.vlm_durum,
                    "uygun": self.vlm_uygun,
                    "uyari": self.vlm_uyari,
                    "acik": self.okuyucu is not None,
                },
                "is": is_d,
                "belgeler": [self._ozet_belge(b) for b in self.belgeler.values()],
                "ozet": say,
            }

    def _ozet_belge(self, b: Belge) -> dict:
        return {
            "id": b.id,
            "ad": b.ad,
            "durum": b.durum,
            "kova": b.kova,
            "neden": b.neden,
            "isim": b.isim,
            "tc_no": b.tc_no,
            "sicil_no": b.sicil_no,
            "uzlasma": b.uzlasma,
            "cok_kimlik": b.cok_kimlik,
            "sayfa_sayisi": b.sayfa_sayisi,
            "gerekce": b.gerekce,
            "uyarilar": list(b.uyarilar),
            "hata": b.hata,
            "not": b.not_,
            "nesil": b.nesil,
        }

    def belge_ayrinti(self, belge_id: str) -> dict:
        with self.kilit:
            b = self._al(belge_id)
            d = self._ozet_belge(b)
            d["plan"] = b.plan
            d["atama"] = list(b.atama)
            return d

    def yukle(self, ad: str, icerik: bytes) -> Belge:
        if not ad.lower().endswith(".pdf"):
            raise ValueError(f"yalnız PDF: {ad}")
        belge_id = uuid.uuid4().hex[:12]
        asil = self.yuklenen / f"{belge_id}.pdf"
        asil.write_bytes(icerik)
        calisma = self.calisma / f"{belge_id}.pdf"
        shutil.copy2(asil, calisma)
        try:
            n = pdf_islem.sayfa_sayisi(calisma)
        except Exception as e:
            asil.unlink(missing_ok=True)
            calisma.unlink(missing_ok=True)
            raise ValueError(f"{ad} açılamadı: {e}") from e
        b = Belge(id=belge_id, ad=ad, yol=calisma, sayfa_sayisi=n,
                  atama=["?"] * n)
        with self.kilit:
            self.belgeler[belge_id] = b
        return b

    def isle(self, vlm: bool, belge_idler: list[str] | None = None) -> str:
        with self.kilit:
            if self.is_.durum in ("yukleniyor", "isleniyor"):
                raise RuntimeError("şu an bir iş yürüyor")
            if belge_idler:
                adaylar = [self._al(i) for i in belge_idler]
            else:
                adaylar = [b for b in self.belgeler.values()
                           if b.durum in ("kuyrukta", "hata")]
            if not adaylar:
                raise RuntimeError("işlenecek belge yok")
            for b in adaylar:
                b.durum = "kuyrukta"
                b.hata = ""
            is_id = uuid.uuid4().hex[:10]
            self.is_ = IsDurum(
                id=is_id, durum="yukleniyor" if vlm else "isleniyor",
                toplam=len(adaylar), baslangic=time.time(),
            )
            self.vlm_istek = bool(vlm)
            idler = [b.id for b in adaylar]
        self._is_kuyrugu.put(("isle", idler, bool(vlm)))
        return is_id

    def ata(self, belge_id: str, atama: list[str]) -> Belge:
        with self.kilit:
            b = self._al(belge_id)
            if len(atama) != b.sayfa_sayisi:
                raise ValueError(
                    f"atama {len(atama)} sayfa, belge {b.sayfa_sayisi} sayfa"
                )
            kullanici_plani("".join(atama), b.tc_no)
            b.atama = [c.upper() for c in atama]
            harf = set(b.atama)
            if "X" in harf or len(harf - {"?", "X"}) > 1:
                b.cok_kimlik = True
                if b.neden != "cok_kimlik":
                    b.neden = "cok_kimlik"
            return b

    def isim_duzelt(
        self,
        belge_id: str,
        isim: str,
        tc_no: str | None = None,
        sicil_no: str | None = None,
    ) -> Belge:
        with self.kilit:
            b = self._al(belge_id)
            b.isim = isim.strip()
            if tc_no is not None:
                b.tc_no = tc_no.strip()
            if sicil_no is not None:
                b.sicil_no = sicil_no.strip()
            if b.isim and b.kova == "okunamadi":
                b.kova = "incele"
                b.neden = "dogrulanmali"
            return b

    def onayla_bol(self, belge_id: str) -> list[str]:
        """Kullanıcı atamasına göre böl; parçaları kuyruğa al, aslı ayrıldı say."""
        with self.kilit:
            b = self._al(belge_id)
            harita = "".join(b.atama) if b.atama else ""
            if not harita or len(harita) != b.sayfa_sayisi:
                raise ValueError("önce her sayfayı atayın")
            plan = kullanici_plani(harita, b.tc_no)
            if not plan.bolunebilir:
                raise ValueError(plan.gerekce)
            yol = b.yol
            ad = b.ad
        gruplar = {k: v for k, v in plan_gruplari(harita).items() if k != "?"}
        parca_klasor = self.calisma / f"parca_{belge_id}"
        yazilan = sayfalari_yaz(
            yol, gruplar, parca_klasor, kok_ad=Path(ad).stem, kuru_calistir=False
        )
        yeni_idler = []
        for kim, parca_yol in yazilan.items():
            yeni = self._parcadan(parca_yol, f"{ad} · {kim}", not_=f"{ad} / {kim}")
            yeni_idler.append(yeni.id)
        asil_hedef = self.kok / AYRILDI / "asil" / ad
        asil_hedef.parent.mkdir(parents=True, exist_ok=True)
        if yol.exists() and not asil_hedef.exists():
            shutil.move(str(yol), str(asil_hedef))
        with self.kilit:
            b.durum = "bitti"
            b.kova = "ayrildi"
            b.gerekce = f"{len(yazilan)} parçaya ayrıldı"
            b.yol = asil_hedef if asil_hedef.exists() else b.yol
        self._is_kuyrugu.put(("isle", yeni_idler, self.okuyucu is not None))
        with self.kilit:
            if self.is_.durum not in ("yukleniyor", "isleniyor"):
                self.is_ = IsDurum(
                    id=uuid.uuid4().hex[:10], durum="isleniyor",
                    toplam=len(yeni_idler), baslangic=time.time(),
                )
        return yeni_idler

    def birlestir(self, sira: list[dict]) -> Belge:
        """sira: [{id, sayfa}, ...] — sayfa 1-tabanlı."""
        if len(sira) < 1:
            raise ValueError("birleştirilecek sayfa yok")
        with self.kilit:
            parcalar_bilgi = []
            kaynak_idler = []
            for adim in sira:
                b = self._al(adim["id"])
                parcalar_bilgi.append((b.yol, int(adim["sayfa"]), b.ad, b.id))
                if b.id not in kaynak_idler:
                    kaynak_idler.append(b.id)
        gruplu: list[tuple[Path, list[int]]] = []
        son_yol: Path | None = None
        sayfalar: list[int] = []
        for yol, sayfa, _ad, _i in parcalar_bilgi:
            if son_yol is None or yol != son_yol:
                if son_yol is not None:
                    gruplu.append((son_yol, sayfalar))
                son_yol = yol
                sayfalar = [sayfa]
            else:
                sayfalar.append(sayfa)
        if son_yol is not None:
            gruplu.append((son_yol, sayfalar))

        yeni_id = uuid.uuid4().hex[:12]
        hedef = self.calisma / f"{yeni_id}.pdf"
        pdf_islem.pdfleri_birlestir(gruplu, hedef)
        ad = " + ".join(
            self.belgeler[i].ad for i in kaynak_idler if i in self.belgeler
        )
        if len(ad) > 80:
            ad = f"birlesik_{len(kaynak_idler)}_belge.pdf"
        elif not ad.lower().endswith(".pdf"):
            ad = ad + ".pdf"
        n = pdf_islem.sayfa_sayisi(hedef)
        yeni = Belge(
            id=yeni_id, ad=ad, yol=hedef, sayfa_sayisi=n,
            atama=["?"] * n, not_="birleştirildi",
        )
        with self.kilit:
            self.belgeler[yeni_id] = yeni
            for kid in kaynak_idler:
                eski = self.belgeler.get(kid)
                if eski is None:
                    continue
                eski.durum = "bitti"
                eski.kova = "ayrildi"
                eski.gerekce = f"birleştirildi → {yeni_id}"
        self._is_kuyrugu.put(("isle", [yeni_id], self.okuyucu is not None))
        with self.kilit:
            if self.is_.durum not in ("yukleniyor", "isleniyor"):
                self.is_ = IsDurum(
                    id=uuid.uuid4().hex[:10], durum="isleniyor",
                    toplam=1, baslangic=time.time(),
                )
        return yeni

    def tasi(self, kaynak_id: str, sayfa: int, hedef_id: str, konum: int | None = None) -> None:
        with self.kilit:
            kaynak = self._al(kaynak_id)
            hedef = self._al(hedef_id)
            if kaynak_id == hedef_id:
                raise ValueError("aynı belgeye taşınamaz — sırayı birleştirde düzenleyin")
            ky, hy = kaynak.yol, hedef.yol
            kn, hn = kaynak.sayfa_sayisi, hedef.sayfa_sayisi
            harf = kaynak.atama[sayfa - 1] if 0 < sayfa <= len(kaynak.atama) else "?"
        if sayfa < 1 or sayfa > kn:
            raise ValueError("kaynak sayfa yok")
        if kn <= 1:
            raise ValueError("kaynak belgede sayfa kalmaz; ayır veya birleştir kullanın")
        tmp_sayfa = self.calisma / f"_tasi_{uuid.uuid4().hex[:8]}.pdf"
        pdf_islem.sayfalari_al(ky, [sayfa], tmp_sayfa)
        yeni_hedef = self.calisma / f"{hedef_id}_n.pdf"
        sira_hedef = list(range(1, hn + 1))
        if konum is None or konum > hn:
            sira_hedef.append(-1)
        else:
            sira_hedef.insert(max(0, konum - 1), -1)
        parcalar: list[tuple[Path, list[int]]] = []
        for no in sira_hedef:
            if no == -1:
                parcalar.append((tmp_sayfa, [1]))
            else:
                parcalar.append((hy, [no]))
        pdf_islem.pdfleri_birlestir(parcalar, yeni_hedef)
        yeni_kaynak = self.calisma / f"{kaynak_id}_n.pdf"
        pdf_islem.sayfalari_cikar(ky, [sayfa], yeni_kaynak)
        tmp_sayfa.unlink(missing_ok=True)
        shutil.move(str(yeni_hedef), str(hy))
        shutil.move(str(yeni_kaynak), str(ky))
        ek_konum = konum if konum is not None and 1 <= konum <= hn + 1 else hn + 1
        with self.kilit:
            kaynak = self._al(kaynak_id)
            hedef = self._al(hedef_id)
            kaynak.sayfa_sayisi = kn - 1
            kaynak.atama = kaynak.atama[: sayfa - 1] + kaynak.atama[sayfa:]
            if len(kaynak.atama) != kaynak.sayfa_sayisi:
                kaynak.atama = ["?"] * kaynak.sayfa_sayisi
            hedef.sayfa_sayisi = hn + 1
            hedef.atama = hedef.atama[: ek_konum - 1] + [harf] + hedef.atama[ek_konum - 1:]
            if len(hedef.atama) != hedef.sayfa_sayisi:
                hedef.atama = ["?"] * hedef.sayfa_sayisi
            kaynak.nesil += 1
            hedef.nesil += 1
            kaynak.durum = "kuyrukta"
            hedef.durum = "kuyrukta"
            kaynak.kova = ""
            hedef.kova = ""
        self._onizleme_sil(kaynak_id)
        self._onizleme_sil(hedef_id)
        self._isle_sonra([kaynak_id, hedef_id])

    def ayir(self, belge_id: str, sayfalar: list[int], hedef_id: str | None = None) -> str:
        """Sayfaları belgeden çıkar; yeni belge veya mevcut hedefe ekle."""
        sayfalar = sorted(set(int(s) for s in sayfalar))
        if not sayfalar:
            raise ValueError("ayrılacak sayfa yok")
        with self.kilit:
            kaynak = self._al(belge_id)
            yol = kaynak.yol
            n = kaynak.sayfa_sayisi
            ad = kaynak.ad
            if any(s < 1 or s > n for s in sayfalar):
                raise ValueError("sayfa numarası geçersiz")
            if len(sayfalar) >= n:
                raise ValueError("bütün sayfalar ayrılamaz")
            hedef = self._al(hedef_id) if hedef_id else None
            hy = hedef.yol if hedef else None
        parca = self.calisma / f"_ayir_{uuid.uuid4().hex[:8]}.pdf"
        pdf_islem.sayfalari_al(yol, sayfalar, parca)
        kalan = self.calisma / f"{belge_id}_n.pdf"
        pdf_islem.sayfalari_cikar(yol, sayfalar, kalan)
        shutil.move(str(kalan), str(yol))
        with self.kilit:
            kaynak = self._al(belge_id)
            kalan_atama = [h for i, h in enumerate(kaynak.atama, 1) if i not in set(sayfalar)]
            kaynak.sayfa_sayisi = n - len(sayfalar)
            kaynak.atama = kalan_atama or ["?"] * kaynak.sayfa_sayisi
            kaynak.nesil += 1
            kaynak.durum = "kuyrukta"
            kaynak.kova = ""
        self._onizleme_sil(belge_id)
        if hedef_id and hy is not None:
            hn = pdf_islem.sayfa_sayisi(hy)
            yeni_hedef = self.calisma / f"{hedef_id}_n.pdf"
            pdf_islem.pdfleri_birlestir([(hy, []), (parca, [])], yeni_hedef)
            shutil.move(str(yeni_hedef), str(hy))
            parca.unlink(missing_ok=True)
            ek = len(sayfalar)
            with self.kilit:
                hedef = self._al(hedef_id)
                hedef.sayfa_sayisi = hn + ek
                hedef.atama = (hedef.atama + ["?"] * ek)
                if len(hedef.atama) != hedef.sayfa_sayisi:
                    hedef.atama = ["?"] * hedef.sayfa_sayisi
                hedef.nesil += 1
                hedef.durum = "kuyrukta"
                hedef.kova = ""
            self._onizleme_sil(hedef_id)
            self._isle_sonra([belge_id, hedef_id])
            return hedef_id
        yeni = self._parcadan(parca, f"{Path(ad).stem}_ayrilan.pdf",
                              not_=f"{ad} sayfa {sayfalar}")
        if parca.exists() and parca.resolve() != yeni.yol.resolve():
            parca.unlink(missing_ok=True)
        self._isle_sonra([belge_id, yeni.id])
        return yeni.id

    def arsivle(
        self,
        belge_idler: list[str] | None = None,
        kati: bool = False,
        tek_kisi: bool = False,
    ) -> list[dict]:
        """Onaylanan belgeleri web_cikti altına taşır. İnsan onayladığı için kati kapalı."""
        with self.kilit:
            if belge_idler:
                adaylar = [self._al(i) for i in belge_idler]
            else:
                adaylar = [
                    b for b in self.belgeler.values()
                    if b.durum == "bitti" and b.kova in ("arsivlenecek", "okunamadi")
                ]
            kopya = [(b.id, b.yol, b.ad, b.isim, b.tc_no, b.sicil_no, b.uzlasma,
                      b.uyarilar, b.kova, b.neden, b.cok_kimlik) for b in adaylar]
        arsiv = Arsiv.yukle(self.kok)
        sonuclar = []
        for (bid, yol, ad, isim, tc, sicil, uz, uyarilar, kova, neden, cok) in kopya:
            if not yol.exists():
                sonuclar.append({"id": bid, "hata": "dosya yok"})
                continue
            if cok and not tek_kisi:
                sonuclar.append({
                    "id": bid,
                    "hata": "çok kişili belge sessiz arşivlenmez — önce sayfaları atayın",
                })
                continue
            if kova == "okunamadi" or (neden == "okunamadi" and not isim.strip()):
                eylem = arsiv.planla(yol, Sonuc(isim="", tc_no=tc, sicil_no=sicil,
                                               uyarilar=list(uyarilar)))
            else:
                eylem = arsiv.planla(
                    yol,
                    Sonuc(isim=isim, tc_no=tc, sicil_no=sicil, uzlasma=max(uz, 2),
                          uyarilar=list(uyarilar)),
                    kati=kati,
                )
            try:
                arsiv.uygula([eylem], kuru_calistir=False)
            except Exception as e:
                sonuclar.append({"id": bid, "hata": str(e)})
                continue
            with self.kilit:
                b = self.belgeler.get(bid)
                if b:
                    b.kova = eylem.tur
                    b.gerekce = eylem.not_
                    b.yol = eylem.hedef or b.yol
                    b.durum = "bitti"
                    if eylem.hedef:
                        b.ad = eylem.hedef.name
            sonuclar.append({
                "id": bid,
                "tur": eylem.tur,
                "hedef": str(eylem.hedef) if eylem.hedef else "",
            })
        return sonuclar

    def atla(self, belge_id: str) -> None:
        with self.kilit:
            b = self._al(belge_id)
            b.kova = "okunamadi"
            b.neden = "okunamadi"
            b.gerekce = "operatör atladı"

    def _parcadan(self, yol: Path, ad: str, not_: str = "") -> Belge:
        yeni_id = uuid.uuid4().hex[:12]
        hedef = self.calisma / f"{yeni_id}.pdf"
        if Path(yol).resolve() != hedef.resolve():
            shutil.copy2(yol, hedef)
        n = pdf_islem.sayfa_sayisi(hedef)
        b = Belge(id=yeni_id, ad=ad, yol=hedef, sayfa_sayisi=n,
                  atama=["?"] * n, not_=not_, durum="kuyrukta")
        with self.kilit:
            self.belgeler[yeni_id] = b
        return b

    def _al(self, belge_id: str) -> Belge:
        b = self.belgeler.get(belge_id)
        if b is None:
            raise KeyError(f"belge yok: {belge_id}")
        return b

    def _onizleme_sil(self, belge_id: str) -> None:
        klasor = self.onizleme / belge_id
        if klasor.exists():
            shutil.rmtree(klasor, ignore_errors=True)

    def _calis(self) -> None:
        while True:
            is_tur, idler, vlm = self._is_kuyrugu.get()
            try:
                if is_tur == "isle":
                    self._isle_idler(idler, vlm)
            except Exception:
                with self.kilit:
                    self.is_.durum = "bitti"
                self._yayin({"tur": "bitti"})

    def _isle_sonra(self, idler: list[str]) -> None:
        self._is_kuyrugu.put(("isle", idler, self.okuyucu is not None))
        with self.kilit:
            if self.is_.durum not in ("yukleniyor", "isleniyor"):
                self.is_ = IsDurum(
                    id=uuid.uuid4().hex[:10], durum="isleniyor",
                    toplam=len(idler), baslangic=time.time(),
                )

    def _isle_idler(self, idler: list[str], vlm: bool) -> None:
        okuyucu = None
        if vlm:
            with self.kilit:
                self.is_.durum = "yukleniyor"
                self.is_.su_an = "Model yükleniyor…"
                self.is_.toplam = len(idler)
                self.is_.biten = 0
                self.vlm_durum = "yukleniyor"
            self._yayin({"tur": "ilerleme", "su_an": "Model yükleniyor…"})
            okuyucu = self._okuyucu_al()
            with self.kilit:
                self.vlm_durum = "hazir" if okuyucu else "yok"
                self.is_.durum = "isleniyor"
                self.is_.baslangic = time.time()
        else:
            with self.kilit:
                okuyucu = self.okuyucu
                self.is_.durum = "isleniyor"
                self.is_.toplam = len(idler)
                self.is_.biten = 0
                self.is_.baslangic = time.time()

        for i, bid in enumerate(idler):
            with self.kilit:
                b = self.belgeler.get(bid)
                if b is None:
                    self.is_.biten += 1
                    continue
                b.durum = "isleniyor"
                self.is_.su_an = b.ad
                self.is_.biten = i
                gecen = time.time() - self.is_.baslangic
                self.is_.eta_sn = (gecen / i * (len(idler) - i)) if i else None
            self._yayin({
                "tur": "ilerleme",
                "biten": i,
                "toplam": len(idler),
                "belge_id": bid,
                "ad": b.ad,
            })
            try:
                self._bir_belge(bid, okuyucu)
            except (KeyboardInterrupt, MemoryError):
                raise
            except Exception as e:
                with self.kilit:
                    b = self.belgeler.get(bid)
                    if b:
                        b.durum = "hata"
                        b.kova = "hata"
                        b.neden = "hata"
                        b.hata = str(e)
            with self.kilit:
                self.is_.biten = i + 1
                gecen = time.time() - self.is_.baslangic
                kalan = len(idler) - (i + 1)
                self.is_.eta_sn = (gecen / (i + 1) * kalan) if (i + 1) else None
        with self.kilit:
            self.is_.durum = "bitti"
            self.is_.su_an = ""
            self.is_.eta_sn = 0
        self._yayin({"tur": "bitti"})

    def _bir_belge(self, belge_id: str, okuyucu) -> None:
        with self.kilit:
            b = self._al(belge_id)
            yol = b.yol
        sonuc, cok, plan = belge_analiz(yol, okuyucu)
        kova = kova_oner(sonuc, cok, kati=True)
        neden = ""
        gerekce = ""
        plan_d = None
        atama: list[str] = []
        if cok:
            neden = "cok_kimlik"
            kova = "incele"
            if plan is None:
                gerekce = cok_kimlik_gerekce(sonuc, Arsiv.yukle(self.kok).person_data)
            else:
                plan_d = plan_sozluge(plan)
                gerekce = plan.gerekce
                atama = [s["sahip"] for s in plan_d["sayfalar"]]
                # İkinci kişi yoksa sessiz tek kişi değil — incele ekranı.
                if not plan.ikincil or not plan.bolunebilir:
                    kova = "incele"
        elif kova == "incele":
            neden = "dogrulanmali"
            gerekce = "sayfalar arası uzlaşma yok, doğrulanmalı"
        elif kova == "okunamadi":
            neden = "okunamadi"
            gerekce = "isim okunamadı"
        with self.kilit:
            b = self.belgeler.get(belge_id)
            if b is None:
                return
            b.durum = "bitti"
            b.kova = kova
            b.neden = neden
            b.isim = sonuc.isim
            b.tc_no = sonuc.tc_no
            b.sicil_no = sonuc.sicil_no
            b.uzlasma = sonuc.uzlasma
            b.uyarilar = list(sonuc.uyarilar)
            b.cok_kimlik = cok
            b.plan = plan_d
            b.gerekce = gerekce
            if atama and len(atama) == b.sayfa_sayisi:
                b.atama = atama
            elif not cok:
                # Tek kişilik belge: tüm sayfalar otomatik Kişi A'ya atanır.
                b.atama = ["A"] * b.sayfa_sayisi
            elif len(b.atama) != b.sayfa_sayisi:
                b.atama = ["?"] * b.sayfa_sayisi

    def _okuyucu_al(self):
        if self.okuyucu is not None:
            return self.okuyucu
        uygun, uyari = vlm_uygun_mu()
        if not uygun:
            with self.kilit:
                self.vlm_uygun = False
                self.vlm_uyari = uyari
                self.vlm_durum = "yok"
            return None
        from belge.isim_okuyucu import IsimOkuyucu, secilen_model

        try:
            self.okuyucu = IsimOkuyucu(secilen_model())
            return self.okuyucu
        except Exception as e:
            with self.kilit:
                self.vlm_uyari = f"VLM yüklenemedi ({e}); OCR ile devam."
                self.vlm_durum = "yok"
            return None

    def _yayin(self, olay: dict) -> None:
        try:
            self.olaylar.put_nowait(olay)
        except Exception:
            pass
