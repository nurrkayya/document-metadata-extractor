"""Altın set çalışma dosyasını hazırlar ve genişletir (SPEC bölüm 6).

    .venv/bin/python araclar/altin_set_hazirla.py [hedef_toplam] [tohum]

Varsayılan hedef 80 belge. Araç **artımlıdır**: mevcut `altin_set.csv`
içindeki doldurulmuş cevaplar korunur, yalnızca eksik kalan sayıda yeni belge
örneklenir ve `doldur.html` sayfasına yalnızca **henüz doldurulmamış**
kayıtlar konur. Böylece genişletme, daha önce yapılmış işi tekrarlatmaz.

Neden OCR ve VLM okumaları çalışma dosyasına konmuyor
-----------------------------------------------------
Kullanıcı modelin cevabını görürse ona bakıp onaylama eğilimine girer
(doğrulama yanlılığı) ve ölçüm modelin kendini doğrulamasına döner. Doğru
değer yalnızca görüntüye bakılarak girilmelidir. Tahminler ayrı bir dosyada
tutulur, puanlama sırasında eşleştirilir.

Örnekleme
---------
İlk 30'luk set zor vakalara ağırlık verecek şekilde seçilmişti; bu ölçümü
kötümser yapıyordu. Genişletmede yeni belgeler **külliyattaki gerçek
dağılıma orantılı** seçilir, böylece toplam set temsilîliğe yaklaşır.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import araclar._kok  # noqa: F401

import base64
import csv
import json
import random
import re
import sys
from collections import Counter
from pathlib import Path

from belge.alan_cikarici import cikar  # noqa: E402
from belge.pdf_okuyucu import bolge_goruntusu, sayfa_goruntuleri  # noqa: E402

HEDEF = Path("altin_set")
GORUNTU_KLASORU = HEDEF / "goruntuler"
CALISMA_DOSYASI = HEDEF / "altin_set.csv"
TAHMIN_DOSYASI = HEDEF / "_tahminler.json"
DOLDURMA_SAYFASI = HEDEF / "doldur.html"

SADECE_BUYUK = re.compile(r"[A-ZÇĞİÖŞÜ ]+")
HAFIF_BOZULMA = re.compile(r"[A-ZÇĞİÖŞÜil ]+")

VARSAYILAN_HEDEF = 80


def _katman(ad: str) -> str:
    if not ad:
        return "isim_yok"
    if SADECE_BUYUK.fullmatch(ad):
        return "temiz"
    if HAFIF_BOZULMA.fullmatch(ad):
        return "hafif"
    return "agir"


def _sayfa_yaz(satirlar: list[dict], hedef: Path) -> None:
    """Doldurulmamış kayıtlar için yerel HTML üretir.

    Görüntüler base64 gömülür; sayfa hiçbir ağ isteği yapmaz — kişisel veri
    makineden çıkmaz (SPEC 5.1: bulut kalıcı olarak kapalı).
    """
    kartlar = []
    for satir in satirlar:
        png = (GORUNTU_KLASORU / satir["goruntu"]).read_bytes()
        veri = base64.b64encode(png).decode("ascii")
        tam_sayfa = "TAM SAYFA" in satir["tip"]
        not_metni = (
            '<p class="uyari">Bu belgede isim satırı bulunamadı — sayfaya bakıp ismi kendin bul.</p>'
            if tam_sayfa
            else ""
        )
        kartlar.append(
            f"""<div class="kart{' tam-sayfa' if tam_sayfa else ''}">
  <div class="sira">{satir["sira"]}</div>
  {not_metni}
  <img src="data:image/png;base64,{veri}" alt="isim {satir["sira"]}">
  <input type="text" data-sira="{satir["sira"]}" placeholder="Buraya doğru ismi yaz"
         autocapitalize="characters" autocomplete="off" spellcheck="false">
</div>"""
        )

    sayfa = """<!doctype html>
<meta charset="utf-8">
<title>Altın set doldurma</title>
<style>
  body { font-family: system-ui, sans-serif; max-width: 900px; margin: 2rem auto;
         padding: 0 1rem; background: #fafafa; color: #111; }
  h1 { font-size: 1.4rem; }
  .kart { background: #fff; border: 1px solid #ddd; border-radius: 8px;
          padding: 1rem; margin-bottom: 1rem; display: flex; align-items: center;
          gap: 1rem; flex-wrap: wrap; }
  .kart.tam-sayfa { border-color: #e0a800; }
  .sira { font-weight: 700; color: #888; min-width: 2rem; }
  img { max-width: 420px; max-height: 300px; border: 1px solid #eee; }
  .tam-sayfa img { max-width: 100%; max-height: 700px; }
  input { flex: 1; min-width: 240px; padding: .6rem; font-size: 1.1rem;
          border: 2px solid #ccc; border-radius: 6px; }
  input:focus { border-color: #0066cc; outline: none; }
  input.dolu { border-color: #2e7d32; background: #f4fbf4; }
  .uyari { width: 100%; color: #a67c00; margin: 0; font-size: .9rem; }
  #cubuk { position: sticky; top: 0; background: #fafafa; padding: 1rem 0;
           border-bottom: 2px solid #ddd; margin-bottom: 1rem; z-index: 10; }
  button { padding: .7rem 1.4rem; font-size: 1rem; border: 0; border-radius: 6px;
           background: #0066cc; color: #fff; cursor: pointer; }
  #durum { margin-left: 1rem; color: #555; }
</style>
<div id="cubuk">
  <button onclick="indir()">CSV olarak indir</button>
  <span id="durum">0 / __TOPLAM__ dolduruldu</span>
</div>
<h1>Altın set: doğru isimleri gir</h1>
<p>Her görüntüde yazan ismi <b>aynen</b> yaz. Türkçe karakterleri koru
(<b>İ</b> noktalı, <b>I</b> noktasız). Baştaki iki nokta işaretini yazma.
Bitince yukarıdaki düğmeyle CSV indir.</p>
__KARTLAR__
<script>
const girisler = () => [...document.querySelectorAll('input[data-sira]')];
function say() {
  const dolu = girisler().filter(g => g.value.trim()).length;
  document.getElementById('durum').textContent = dolu + ' / ' + girisler().length + ' dolduruldu';
}
girisler().forEach(g => g.addEventListener('input', () => {
  g.classList.toggle('dolu', !!g.value.trim());
  say();
}));
function indir() {
  const satirlar = [['sira', 'DOGRU_ISIM']];
  girisler().forEach(g => satirlar.push([g.dataset.sira, g.value.trim()]));
  const csv = satirlar.map(s => s.map(h => '"' + String(h).replace(/"/g, '""') + '"').join(',')).join('\\n');
  const bag = document.createElement('a');
  bag.href = URL.createObjectURL(new Blob([csv], {type: 'text/csv;charset=utf-8'}));
  bag.download = 'altin_set_yeni.csv';
  bag.click();
}
say();
</script>
"""
    sayfa = sayfa.replace("__KARTLAR__", "\n".join(kartlar))
    sayfa = sayfa.replace("__TOPLAM__", str(len(satirlar)))
    hedef.write_text(sayfa, encoding="utf-8")


def main(hedef_toplam: str | int = VARSAYILAN_HEDEF, tohum: str | int = 42) -> None:
    hedef_toplam, tohum = int(hedef_toplam), int(tohum)

    # Satırlar bütün olarak okunur: altın sette DOGRU_ISIM dışında sütunlar da
    # var (DOGRU_TC, DOGRU_SICIL — bkz. araclar/altin_set_tc_sicil.py). Yalnız
    # DOGRU_ISIM okunup geri yazılsaydı, seti her genişletme onları silerdi.
    basliklar = ["sira", "DOGRU_ISIM"]
    mevcut_cevaplar: dict[str, dict[str, str]] = {}
    if CALISMA_DOSYASI.exists():
        with CALISMA_DOSYASI.open(encoding="utf-8") as f:
            okuyucu = csv.DictReader(f)
            basliklar = list(okuyucu.fieldnames or basliklar)
            mevcut_cevaplar = {s["sira"]: dict(s) for s in okuyucu}
    mevcut_tahminler: dict[str, dict] = {}
    if TAHMIN_DOSYASI.exists():
        mevcut_tahminler = json.loads(TAHMIN_DOSYASI.read_text(encoding="utf-8"))

    kullanilan = {k["kaynak_dosya"] for k in mevcut_tahminler.values()}
    eklenecek = hedef_toplam - len(mevcut_tahminler)
    if eklenecek <= 0:
        print(f"Set zaten {len(mevcut_tahminler)} belge içeriyor, ekleme gerekmiyor.")
        return

    dosyalar = sorted(Path("ornekler").glob("*.pdf"))
    print(f"{len(dosyalar)} belge taranıyor...")
    katmanlar: dict[str, list] = {}
    dagilim: Counter[str] = Counter()
    for yol in dosyalar:
        sonuc = cikar(yol)
        katman = _katman(sonuc.isim_bosluksuz.strip())
        dagilim[katman] += 1
        if yol.name not in kullanilan:
            katmanlar.setdefault(katman, []).append((yol, sonuc))

    # Yeni belgeler külliyattaki gerçek dağılıma orantılı seçilir.
    rastgele = random.Random(tohum)
    secilenler = []
    toplam_belge = sum(dagilim.values())
    for katman, havuz in katmanlar.items():
        pay = round(eklenecek * dagilim[katman] / toplam_belge)
        secilenler += rastgele.sample(havuz, min(pay, len(havuz)))
    # Yuvarlamadan kaynaklanan eksik/fazlayı düzelt
    artakalan = [x for k in katmanlar.values() for x in k if x not in secilenler]
    rastgele.shuffle(artakalan)
    while len(secilenler) < eklenecek and artakalan:
        secilenler.append(artakalan.pop())
    secilenler = secilenler[:eklenecek]
    rastgele.shuffle(secilenler)

    GORUNTU_KLASORU.mkdir(parents=True, exist_ok=True)
    sonraki = max((int(s) for s in mevcut_tahminler), default=0) + 1

    yeni_satirlar = []
    for kayma, (yol, sonuc) in enumerate(secilenler):
        sira = sonraki + kayma
        if sonuc.isim_kutusu and sonuc.isim_sayfa:
            png = bolge_goruntusu(yol, sonuc.isim_sayfa, sonuc.isim_kutusu, dpi=300)
            tip = "isim satiri"
        else:
            _, png = next(iter(sayfa_goruntuleri(yol, dpi=150)))
            tip = "TAM SAYFA - ismi kendin bul"

        goruntu_adi = f"{sira:02d}.png"
        (GORUNTU_KLASORU / goruntu_adi).write_bytes(png)
        yeni_satirlar.append({"sira": str(sira), "goruntu": goruntu_adi, "tip": tip})
        mevcut_tahminler[str(sira)] = {
            "kaynak_dosya": yol.name,
            "ocr": sonuc.isim_bosluksuz,
            "sicil_no": sonuc.sicil_no,
            "tc_no": sonuc.tc_no,
        }
        mevcut_cevaplar.setdefault(str(sira), {"sira": str(sira), "DOGRU_ISIM": ""})

    with CALISMA_DOSYASI.open("w", newline="", encoding="utf-8") as f:
        yazici = csv.DictWriter(f, fieldnames=basliklar, quoting=csv.QUOTE_ALL)
        yazici.writeheader()
        for sira in sorted(mevcut_cevaplar, key=int):
            yazici.writerow({b: mevcut_cevaplar[sira].get(b, "") for b in basliklar})

    TAHMIN_DOSYASI.write_text(
        json.dumps(mevcut_tahminler, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    _sayfa_yaz(yeni_satirlar, DOLDURMA_SAYFASI)

    print(f"\nSete {len(yeni_satirlar)} belge eklendi (toplam {len(mevcut_tahminler)}).")
    print(f"  Doldurulacak  : {DOLDURMA_SAYFASI}  ({len(yeni_satirlar)} yeni kayıt)")
    korunan = sum(1 for v in mevcut_cevaplar.values() if v.get("DOGRU_ISIM", "").strip())
    print(f"  Mevcut cevaplar korundu: {korunan}")
    print(f"  Külliyat dağılımı: {dict(dagilim)}")


if __name__ == "__main__":
    main(*sys.argv[1:])
