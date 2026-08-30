"""Altın sete `tc_no` ve `sicil_no` doğru değerlerini toplar (SPEC bölüm 3, R6).

    .venv/bin/python araclar/altin_set_tc_sicil.py            # doldurma sayfası üret
    .venv/bin/python araclar/altin_set_tc_sicil.py birlestir <indirilen.csv>

İsim alanı 80 belgede ölçüldü, ama `tc_no` ve `sicil_no` için altın sette hiç
doğru değer yoktu. Elimizdeki %76 ve %84.4 rakamları **kapsama**dır (bir değer
üretilebildi mi), doğruluk değil. Bu araç o boşluğu kapatır.

Hangi görüntü gösteriliyor
--------------------------
İki alanın zorluğu bağımsız, bu yüzden ayrı ayrı karar verilir:

`tc_no`
  Belgede **tam bir** geçerli TC varsa (67/80) sahiplik sorusu yoktur: o
  satırın kırpması gösterilir. Etiket de kırpmaya dahil edilir — çıkarıcı
  yanlış etiketi ("Vergi No" gibi) yakaladıysa bu ancak etiket görünürse
  fark edilir.

  Belgede **birden fazla ya da hiç** geçerli TC varsa (13/80) kırpma
  göstermek ölçümü döngüsel yapar: çıkarıcının seçtiği bölgeyi onaylamış
  oluruz ve R6'da tarif edilen sahiplik hatası görünmez kalır. Bu belgelerde
  TC geçen **tüm sayfalar** tam olarak gösterilir; hangi TC'nin DN sahibine
  ait olduğuna insan karar verir.

`sicil_no`
  DN metinde bulunuyorsa (67/80) DN'in bulunduğu köşe kırpılır. Bulunmuyorsa
  1. sayfa tam gösterilir (SPEC 3: DN 1. sayfanın sol üstündedir).

Yanlılık
--------
`altin_set_hazirla.py` ile aynı ilke: çıkarıcının/modelin ürettiği değerler
sayfada **gösterilmez**. Kullanıcı değeri yalnızca görüntüden okur, yoksa
ölçüm modelin kendini doğrulamasına döner.

Görüntüler neden gömülü değil
-----------------------------
İsim sayfası PNG'leri base64 gömüyordu; oradaki kırpmalar küçüktü. Burada 54
tam sayfa var, gömülse sayfa yüzlerce MB olurdu. Görüntüler diske yazılıp
**göreli yolla** çağrılır — sayfa yine hiçbir ağ isteği yapmaz, kişisel veri
makineden çıkmaz. `altin_set/` zaten `.gitignore`'da.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import araclar._kok  # noqa: F401

import csv
import json
import sys
from pathlib import Path

import pymupdf  # noqa: E402

from belge.alan_cikarici import (  # noqa: E402
    DESEN_DN,
    ETIKET_TC,
    etiket_degeri,
    gecerli_tcler,
)

HEDEF = Path("altin_set")
GORUNTU_KLASORU = HEDEF / "tc_sicil_goruntuler"
CALISMA_DOSYASI = HEDEF / "altin_set.csv"
TAHMIN_DOSYASI = HEDEF / "_tahminler.json"
DOLDURMA_SAYFASI = HEDEF / "doldur_tc_sicil.html"

SUTUNLAR = ["DOGRU_TC", "DOGRU_SICIL"]

# Bazı PDF'ler yanlış bölünmüş: bir dosyada birden fazla kişinin evrakı var.
# Bu bir tarama/bölme kusuru, çıkarıcı hatası değil. Böyle belgelerde doğru
# değer DN sahibine aittir; işaret ölçümü değil, külliyatın durumunu izler.
# SUTUNLAR'a dahil DEĞİL: belgelerin çoğu işaretsiz kalacak, işaretsizlik
# "doldurulmadı" sayılırsa artımlı araç onları sonsuza kadar tekrar sorar.
ISARET_SUTUNU = "YANLIS_BIRLESTIRME"

KIRPMA_DPI = 300
SAYFA_DPI = 200
PAY = 6.0


def _satir_kirpmasi(sayfa: pymupdf.Page, kutu: tuple) -> pymupdf.Rect:
    """Değer kutusunu, satırın soluna doğru genişleterek etiketi de içine alır."""
    _, y0, x1, y1 = kutu
    return pymupdf.Rect(sayfa.rect.x0, y0 - PAY, x1 + PAY, y1 + PAY) & sayfa.rect


def _yaz(ad: str, veri: bytes) -> str:
    (GORUNTU_KLASORU / ad).write_bytes(veri)
    return ad


def _tc_goruntuleri(belge: pymupdf.Document, sira: str) -> tuple[list[str], bool]:
    """(görüntü adları, tam_sayfa_mi) döndürür."""
    metinler = [s.get_text() for s in belge]
    tcler = {t for m in metinler for t in gecerli_tcler(m)}

    if len(tcler) == 1:
        for indeks, sayfa in enumerate(belge):
            _, kutu = etiket_degeri(sayfa, ETIKET_TC)
            if kutu:
                kirpma = _satir_kirpmasi(sayfa, kutu)
                png = sayfa.get_pixmap(dpi=KIRPMA_DPI, clip=kirpma).tobytes("png")
                return [_yaz(f"{sira}_tc.png", png)], False

    # Belirsiz (0 veya >1 TC) ya da etiket hiç bulunamadı: tam sayfa göster.
    gerekli = sorted({i for i, m in enumerate(metinler) if gecerli_tcler(m)} | {0})
    adlar = []
    for indeks in gerekli:
        jpg = belge[indeks].get_pixmap(dpi=SAYFA_DPI).tobytes("jpeg", jpg_quality=80)
        adlar.append(_yaz(f"{sira}_tc_sayfa{indeks + 1}.jpg", jpg))
    return adlar, True


def _sicil_goruntuleri(belge: pymupdf.Document, sira: str) -> tuple[list[str], bool]:
    for indeks, sayfa in enumerate(belge):
        if not DESEN_DN.search(sayfa.get_text()):
            continue
        for kelime in sayfa.get_text("words"):
            if DESEN_DN.search(kelime[4]):
                kirpma = _satir_kirpmasi(sayfa, kelime[:4])
                png = sayfa.get_pixmap(dpi=KIRPMA_DPI, clip=kirpma).tobytes("png")
                return [_yaz(f"{sira}_sicil.png", png)], False

    jpg = belge[0].get_pixmap(dpi=SAYFA_DPI).tobytes("jpeg", jpg_quality=80)
    return [_yaz(f"{sira}_sicil_sayfa1.jpg", jpg)], True


def _sayfa_yaz(kartlar_verisi: list[dict]) -> None:
    kartlar = []
    for k in kartlar_verisi:
        bolumler = []
        for alan, baslik, ipucu in (
            ("tc", "TC KİMLİK NO", "11 hane"),
            ("sicil", "SİCİL NO", "5 hane, yalnızca rakam"),
        ):
            gorseller = "\n".join(
                f'<img src="{GORUNTU_KLASORU.name}/{ad}" loading="lazy" alt="{alan}">'
                for ad in k[f"{alan}_goruntuler"]
            )
            uyari = (
                '<p class="uyari">Tam sayfa: değeri kendin bul. '
                "Birden fazla numara varsa <b>DN sahibine ait olanı</b> yaz; "
                "belirleyemiyorsan boş bırak.</p>"
                if k[f"{alan}_tam_sayfa"]
                else ""
            )
            bolumler.append(
                f"""<div class="alan{' zor' if k[f'{alan}_tam_sayfa'] else ''}">
  <h3>{baslik} <span class="ipucu">({ipucu})</span></h3>
  {uyari}
  <div class="gorseller">{gorseller}</div>
  <input type="text" data-sira="{k["sira"]}" data-alan="{alan}"
         inputmode="numeric" autocomplete="off" spellcheck="false"
         placeholder="Okuyamıyorsan boş bırak">
</div>"""
            )
        kartlar.append(
            f'<div class="kart"><div class="sira">#{k["sira"]}</div>'
            + "\n".join(bolumler)
            + "</div>"
        )

    sayfa = """<!doctype html>
<meta charset="utf-8">
<title>Altın set: TC ve sicil no</title>
<style>
  body { font-family: system-ui, sans-serif; max-width: 1000px; margin: 2rem auto;
         padding: 0 1rem; background: #fafafa; color: #111; }
  h1 { font-size: 1.4rem; }
  .kart { background: #fff; border: 1px solid #ddd; border-radius: 8px;
          padding: 1rem; margin-bottom: 1.5rem; }
  .sira { font-weight: 700; color: #888; margin-bottom: .5rem; }
  .alan { border-top: 1px solid #eee; padding-top: .8rem; margin-top: .8rem; }
  .alan.zor { border-left: 4px solid #e0a800; padding-left: .8rem; }
  .alan h3 { font-size: .95rem; margin: 0 0 .5rem; letter-spacing: .04em; }
  .ipucu { font-weight: 400; color: #888; letter-spacing: 0; }
  .gorseller { display: flex; flex-wrap: wrap; gap: .5rem; margin-bottom: .6rem; }
  img { max-width: 100%; border: 1px solid #eee; cursor: zoom-in; }
  .alan:not(.zor) img { max-height: 90px; }
  .alan.zor img { max-height: 620px; }
  img.buyuk { max-height: none; max-width: none; cursor: zoom-out; }
  input { width: 100%; max-width: 320px; padding: .6rem; font-size: 1.1rem;
          border: 2px solid #ccc; border-radius: 6px; font-variant-numeric: tabular-nums; }
  input:focus { border-color: #0066cc; outline: none; }
  input.dolu { border-color: #2e7d32; background: #f4fbf4; }
  input.hatali { border-color: #c62828; background: #fdf4f4; }
  .uyari { color: #a67c00; margin: 0 0 .5rem; font-size: .9rem; }
  #cubuk { position: sticky; top: 0; background: #fafafa; padding: 1rem 0;
           border-bottom: 2px solid #ddd; margin-bottom: 1rem; z-index: 10; }
  button { padding: .7rem 1.4rem; font-size: 1rem; border: 0; border-radius: 6px;
           background: #0066cc; color: #fff; cursor: pointer; }
  #durum { margin-left: 1rem; color: #555; }
</style>
<div id="cubuk">
  <button onclick="indir()">CSV olarak indir</button>
  <span id="durum"></span>
</div>
<h1>Altın set: TC kimlik no ve sicil no</h1>
<p>Her alanda görüntüde <b>yazan</b> değeri gir. Okuyamıyorsan ya da emin
değilsen <b>boş bırak</b> — uydurma değer ölçümü bozar. Görüntüye tıklayınca
büyür. Sarı çerçeveli alanlar tam sayfadır, değeri kendin bulman gerekir.</p>
__KARTLAR__
<script>
const girisler = () => [...document.querySelectorAll('input[data-sira]')];
// TC checksum: girilen değerin kendisi de yanlış olabilir. Kırmızı çerçeve
// "yanlış yazdın" demez, "bir daha bak" der.
function tcGecerli(n) {
  if (!/^[1-9][0-9]{10}$/.test(n)) return false;
  const h = [...n].map(Number);
  const tek = h[0]+h[2]+h[4]+h[6]+h[8], cift = h[1]+h[3]+h[5]+h[7];
  if ((tek*7 - cift) % 10 !== h[9]) return false;
  return h.slice(0,10).reduce((a,b)=>a+b,0) % 10 === h[10];
}
function kontrol(g) {
  const v = g.value.trim();
  g.classList.toggle('dolu', !!v);
  const bozuk = v && (g.dataset.alan === 'tc' ? !tcGecerli(v) : !/^[0-9]{5}$/.test(v));
  g.classList.toggle('hatali', !!bozuk);
}
function say() {
  const dolu = girisler().filter(g => g.value.trim()).length;
  document.getElementById('durum').textContent =
    dolu + ' / ' + girisler().length + ' alan dolduruldu';
}
girisler().forEach(g => g.addEventListener('input', () => { kontrol(g); say(); }));
document.addEventListener('click', e => {
  if (e.target.tagName === 'IMG') e.target.classList.toggle('buyuk');
});
function indir() {
  const satir = {};
  girisler().forEach(g => {
    satir[g.dataset.sira] = satir[g.dataset.sira] || {tc: '', sicil: ''};
    satir[g.dataset.sira][g.dataset.alan] = g.value.trim();
  });
  const satirlar = [['sira', 'DOGRU_TC', 'DOGRU_SICIL']];
  Object.keys(satir).sort((a,b) => a-b).forEach(s =>
    satirlar.push([s, satir[s].tc, satir[s].sicil]));
  const csv = satirlar.map(s => s.map(h => '"' + String(h).replace(/"/g, '""') + '"').join(',')).join('\\n');
  const bag = document.createElement('a');
  bag.href = URL.createObjectURL(new Blob([csv], {type: 'text/csv;charset=utf-8'}));
  bag.download = 'altin_set_tc_sicil_yeni.csv';
  bag.click();
}
say();
</script>
"""
    DOLDURMA_SAYFASI.write_text(
        sayfa.replace("__KARTLAR__", "\n".join(kartlar)), encoding="utf-8"
    )


def _csv_oku() -> tuple[list[str], dict[str, dict]]:
    if not CALISMA_DOSYASI.exists():
        return ["sira"], {}
    with CALISMA_DOSYASI.open(encoding="utf-8") as f:
        okuyucu = csv.DictReader(f)
        return list(okuyucu.fieldnames or ["sira"]), {s["sira"]: dict(s) for s in okuyucu}


def _csv_yaz(basliklar: list[str], satirlar: dict[str, dict]) -> None:
    for sutun in [*SUTUNLAR, ISARET_SUTUNU]:
        if sutun not in basliklar:
            basliklar.append(sutun)
    with CALISMA_DOSYASI.open("w", newline="", encoding="utf-8") as f:
        yazici = csv.DictWriter(f, fieldnames=basliklar, quoting=csv.QUOTE_ALL)
        yazici.writeheader()
        for sira in sorted(satirlar, key=int):
            yazici.writerow({b: satirlar[sira].get(b, "") for b in basliklar})


def hazirla() -> None:
    tahminler = json.loads(TAHMIN_DOSYASI.read_text(encoding="utf-8"))
    basliklar, satirlar = _csv_oku()

    # Artımlı: iki alanı da dolu olan belge yeniden sorulmaz.
    eksik = [
        s
        for s in sorted(tahminler, key=int)
        if not all(satirlar.get(s, {}).get(c, "").strip() for c in SUTUNLAR)
    ]
    if not eksik:
        print("Tüm TC/sicil cevapları dolu, yapacak iş yok.")
        return

    GORUNTU_KLASORU.mkdir(parents=True, exist_ok=True)
    print(f"{len(eksik)} belge için görüntü üretiliyor...")

    kartlar, zor_tc, zor_sicil = [], 0, 0
    for sira in eksik:
        yol = Path("ornekler") / tahminler[sira]["kaynak_dosya"]
        with pymupdf.open(yol) as belge:
            tc_goruntuler, tc_zor = _tc_goruntuleri(belge, sira)
            sicil_goruntuler, sicil_zor = _sicil_goruntuleri(belge, sira)
        zor_tc += tc_zor
        zor_sicil += sicil_zor
        kartlar.append(
            {
                "sira": sira,
                "tc_goruntuler": tc_goruntuler,
                "tc_tam_sayfa": tc_zor,
                "sicil_goruntuler": sicil_goruntuler,
                "sicil_tam_sayfa": sicil_zor,
            }
        )
        satirlar.setdefault(sira, {"sira": sira})

    _csv_yaz(basliklar, satirlar)
    _sayfa_yaz(kartlar)

    print(f"\n  Doldurulacak : {DOLDURMA_SAYFASI}  ({len(kartlar)} belge, {2 * len(kartlar)} alan)")
    print(f"  TC    : {len(kartlar) - zor_tc} kırpma, {zor_tc} tam sayfa")
    print(f"  Sicil : {len(kartlar) - zor_sicil} kırpma, {zor_sicil} tam sayfa")
    print(f"  Sütunlar {SUTUNLAR} {CALISMA_DOSYASI} dosyasına eklendi (boş).")


def birlestir(indirilen: str) -> None:
    """Tarayıcıdan indirilen CSV'yi altın sete işler."""
    basliklar, satirlar = _csv_oku()
    yeni = {s["sira"]: s for s in csv.DictReader(Path(indirilen).open(encoding="utf-8"))}

    islenen = 0
    for sira, kayit in yeni.items():
        if sira not in satirlar:
            print(f"  uyarı: {sira} altın sette yok, atlandı")
            continue
        for sutun in SUTUNLAR:
            deger = kayit.get(sutun, "").strip()
            if deger:
                satirlar[sira][sutun] = deger
                islenen += 1

    _csv_yaz(basliklar, satirlar)
    dolu = {c: sum(1 for s in satirlar.values() if s.get(c, "").strip()) for c in SUTUNLAR}
    print(f"{islenen} değer işlendi. Altın sette dolu: {dolu} / {len(satirlar)} belge")


def duzelt(sira: str, sutun: str, deger: str) -> None:
    """Altın setteki tek bir doğru değeri düzeltir.

    Altın set hatasız değil (bkz. staj günlüğü, 17 numaralı belgedeki
    MURAK/MURAT vakası). Ölçüm bir uyuşmazlık gösterdiğinde suçlu her zaman
    çıkarıcı olmuyor; karar **kaynak görüntüye bakarak** verilmeli.
    """
    if sutun not in SUTUNLAR:
        raise SystemExit(f"Bilinmeyen sütun: {sutun} (seçenekler: {SUTUNLAR})")
    basliklar, satirlar = _csv_oku()
    if sira not in satirlar:
        raise SystemExit(f"{sira} altın sette yok")
    eski = satirlar[sira].get(sutun, "")
    satirlar[sira][sutun] = deger
    _csv_yaz(basliklar, satirlar)
    print(f"#{sira} {sutun}: {len(eski)} haneli değer {len(deger)} haneliyle değiştirildi")


def isaretle(siralar: list[str]) -> None:
    """Verilen belgeleri yanlış birleştirme olarak işaretler (yalnız verilenler)."""
    basliklar, satirlar = _csv_oku()
    bilinmeyen = [s for s in siralar if s not in satirlar]
    if bilinmeyen:
        raise SystemExit(f"Altın sette olmayan sıra: {bilinmeyen}")
    for sira in satirlar:
        satirlar[sira][ISARET_SUTUNU] = "EVET" if sira in siralar else ""
    _csv_yaz(basliklar, satirlar)
    print(f"{len(siralar)} belge '{ISARET_SUTUNU}' olarak işaretlendi: {sorted(siralar, key=int)}")
    print(f"Kalan {len(satirlar) - len(siralar)} belge işaretsiz.")


if __name__ == "__main__":
    komut = sys.argv[1] if len(sys.argv) > 1 else ""
    if komut == "birlestir":
        birlestir(sys.argv[2])
    elif komut == "duzelt":
        duzelt(sys.argv[2], sys.argv[3], sys.argv[4])
    elif komut == "isaretle":
        isaretle(sys.argv[2:])
    else:
        hazirla()
