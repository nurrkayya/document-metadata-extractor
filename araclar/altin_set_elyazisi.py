"""El yazısı külliyatı için altın set (SPEC Adım 12).

    .venv/bin/python araclar/altin_set_elyazisi.py [kaç_belge]
    .venv/bin/python araclar/altin_set_elyazisi.py birlestir <indirilen.csv>

Neden ayrı bir altın set
------------------------
`ornekler/` klasörüne ikinci bir belge grubu eklendi ve ilk gruptan temelde
farklı:

  ilk grup   1990 sonrası, alanlar matbu, sicil no 5 haneli, TC her belgede
  yeni grup  1980'ler, alanlar DAKTİLO ya da EL YAZISI, sicil no 4 haneli,
             TC kimlik no alanı formda hiç yok

Mevcut altın set (80 belge) yalnız ilk grubu temsil ediyor ve oradaki %95'lik
isim doğruluğu bu grup için hiçbir şey söylemiyor. Karıştırmak iki ölçümü de
yararsız hale getirirdi, bu yüzden ayrı set.

Belge türü neden ayrıca işaretleniyor
-------------------------------------
Daktilo ile el yazısı çok farklı zorluklar. Karışık bir ortalama ("yeni
külliyatta %X") hangi kısmın çözülüp hangisinin çözülmediğini gizler. Tür
etiketi sayesinde doğruluk her popülasyon için ayrı raporlanabilir.

Yanlılık
--------
İlk altın setle aynı ilke: çıkarıcının ve modelin okumaları doldurma
sayfasında GÖSTERİLMEZ. Değer yalnızca görüntüye bakılarak girilir; yoksa
ölçüm modelin kendini doğrulamasına döner.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import araclar._kok  # noqa: F401

import csv
import json
import random

import pymupdf  # noqa: E402

from belge.alan_cikarici import (  # noqa: E402
    ETIKET_AD,
    cikar,
    etiket_kutusu,
    satir_kutusu,
)

KAYNAK = Path("ornekler")
HEDEF = Path("altin_set_elyazisi")
GORUNTU = HEDEF / "goruntuler"
CALISMA = HEDEF / "altin_set.csv"
TAHMIN = HEDEF / "_tahminler.json"
SAYFA = HEDEF / "doldur.html"

SUTUNLAR = ["DOGRU_ISIM", "TUR"]
VARSAYILAN = 40
KIRPMA_DPI = 300
SAYFA_DPI = 130


def _csv_oku() -> tuple[list[str], dict[str, dict]]:
    if not CALISMA.exists():
        return ["sira", *SUTUNLAR], {}
    with CALISMA.open(encoding="utf-8") as f:
        o = csv.DictReader(f)
        return list(o.fieldnames or ["sira", *SUTUNLAR]), {s["sira"]: dict(s) for s in o}


def _csv_yaz(basliklar: list[str], satirlar: dict[str, dict]) -> None:
    for s in ["sira", *SUTUNLAR]:
        if s not in basliklar:
            basliklar.append(s)
    with CALISMA.open("w", newline="", encoding="utf-8") as f:
        y = csv.DictWriter(f, fieldnames=basliklar, quoting=csv.QUOTE_ALL)
        y.writeheader()
        for sira in sorted(satirlar, key=int):
            y.writerow({b: satirlar[sira].get(b, "") for b in basliklar})


def _sayfa_yaz(kartlar_verisi: list[dict]) -> None:
    kartlar = []
    for k in kartlar_verisi:
        uyari = (
            '<p class="uyari">İsim satırı bulunamadı — tam sayfa. İsmi kendin bul.</p>'
            if k["tam_sayfa"]
            else ""
        )
        turler = "".join(
            f'<label><input type="radio" name="tur{k["sira"]}" value="{d}"'
            f'{" checked" if k.get("onceki_tur") == d else ""}> {e}</label>'
            for d, e in (("el", "el yazısı"), ("daktilo", "daktilo"), ("matbu", "matbu"))
        )
        kartlar.append(
            f"""<div class="kart{' tam' if k["tam_sayfa"] else ''}">
  <div class="sira">#{k["sira"]}</div>
  {uyari}
  <img src="{GORUNTU.name}/{k["goruntu"]}" loading="lazy" alt="isim {k["sira"]}">
  <input type="text" class="isim{" onceki" if k.get("onceki") else ""}" data-sira="{k["sira"]}"
         value="{k.get("onceki", "")}"
         placeholder="Görüntüde yazan ismi aynen yaz — okunmuyorsa boş bırak"
         autocapitalize="characters" autocomplete="off" spellcheck="false">
  <div class="turler" data-sira="{k["sira"]}">{turler}</div>
</div>"""
        )

    sayfa = """<!doctype html>
<meta charset="utf-8">
<title>El yazısı altın seti</title>
<style>
  body { font-family: system-ui, sans-serif; max-width: 1000px; margin: 2rem auto;
         padding: 0 1rem; background: #fafafa; color: #111; }
  .kart { background: #fff; border: 1px solid #ddd; border-radius: 8px;
          padding: 1rem; margin-bottom: 1.2rem; }
  .kart.tam { border-left: 4px solid #e0a800; }
  .sira { font-weight: 700; color: #888; margin-bottom: .4rem; }
  img { max-width: 100%; max-height: 130px; border: 1px solid #eee; cursor: zoom-in;
        display: block; margin-bottom: .6rem; }
  .kart.tam img { max-height: 640px; }
  img.buyuk { max-height: none; max-width: none; cursor: zoom-out; }
  input.isim { width: 100%; padding: .6rem; font-size: 1.1rem; border: 2px solid #ccc;
               border-radius: 6px; }
  input.isim:focus { border-color: #0066cc; outline: none; }
  input.isim.dolu { border-color: #2e7d32; background: #f4fbf4; }
  input.isim.onceki { border-color: #e0a800; background: #fffdf5; }
  .turler { margin-top: .5rem; display: flex; gap: 1rem; font-size: .9rem; color: #555; }
  .turler label { cursor: pointer; }
  .turler.secili { color: #2e7d32; font-weight: 600; }
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
<h1>El yazısı altın seti</h1>
<p class="uyari"><b>Kırpmalar düzeltildi.</b> Önceki turda kırpma etiketi
göstermiyordu ve bazı alanlarda soyadı kesiliyor, bazılarında yanlış alan
gösteriliyordu. Önceki cevapların <b>sarı çerçeveyle önden dolduruldu</b> —
görüntüyle karşılaştırıp yanlış olanları düzelt, doğru olanlara dokunma.</p>
<p>Her görüntüde yazan ismi <b>aynen</b> yaz — Türkçe karakterleri koru,
düzeltme yapma. <b>Okuyamıyorsan boş bırak</b>; uydurma değer ölçümü bozar.
Ayrıca alanın nasıl doldurulduğunu işaretle: bu, el yazısı ile daktiloyu
ayrı ölçebilmek için gerekli. Görüntüye tıklayınca büyür.</p>
__KARTLAR__
<script>
const isimler = () => [...document.querySelectorAll('input.isim')];
function say() {
  const d = isimler().filter(g => g.value.trim()).length;
  const t = [...document.querySelectorAll('.turler')]
            .filter(x => x.querySelector('input:checked')).length;
  document.getElementById('durum').textContent =
    d + ' isim, ' + t + ' tür işaretlendi / ' + isimler().length;
}
isimler().forEach(g => g.addEventListener('input', () => {
  g.classList.toggle('dolu', !!g.value.trim()); say();
}));
document.addEventListener('change', e => {
  if (e.target.type === 'radio') { e.target.closest('.turler').classList.add('secili'); say(); }
});
document.addEventListener('click', e => {
  if (e.target.tagName === 'IMG') e.target.classList.toggle('buyuk');
});
function indir() {
  const satirlar = [['sira', 'DOGRU_ISIM', 'TUR']];
  isimler().forEach(g => {
    const s = g.dataset.sira;
    const t = document.querySelector('.turler[data-sira="' + s + '"] input:checked');
    satirlar.push([s, g.value.trim(), t ? t.value : '']);
  });
  const csv = satirlar.map(r => r.map(h => '"' + String(h).replace(/"/g,'""') + '"').join(',')).join('\\n');
  const a = document.createElement('a');
  a.href = URL.createObjectURL(new Blob([csv], {type:'text/csv;charset=utf-8'}));
  a.download = 'altin_set_elyazisi_yeni.csv';
  a.click();
}
say();
</script>
"""
    SAYFA.write_text(sayfa.replace("__KARTLAR__", "\n".join(kartlar)), encoding="utf-8")


EGITIM_SETI_TAHMIN = Path("egitim_seti_elyazisi") / "_tahminler.json"


def _egitim_seti_disla() -> set[str]:
    """Fine-tune eğitiminde kullanılan belgelerin göreli yollarını döner.

    Altın set doğruluk ÖLÇÜMÜ için ayrılmıştır; eğitimde görülmüş bir
    belge altın sete girerse ölçüm kendi kendini doğrulamaya döner —
    tıpkı tersi yönde egitim_verisi_hazirla.py'nin altın seti dışlaması
    gibi.
    """
    if not EGITIM_SETI_TAHMIN.exists():
        return set()
    tahminler = json.loads(EGITIM_SETI_TAHMIN.read_text(encoding="utf-8"))
    return {v["kaynak_dosya"] for v in tahminler.values()}


def hazirla(kac: str | int = VARSAYILAN, tohum: str | int = 42) -> None:
    kac, tohum = int(kac), int(tohum)
    basliklar, satirlar = _csv_oku()
    tahminler = json.loads(TAHMIN.read_text(encoding="utf-8")) if TAHMIN.exists() else {}

    kullanilan = {v["kaynak_dosya"] for v in tahminler.values()}
    disla = _egitim_seti_disla()
    eklenecek = kac - len(tahminler)
    if eklenecek <= 0:
        print(f"Set zaten {len(tahminler)} belge içeriyor.")
        return

    havuz = [
        p for p in sorted(KAYNAK.rglob("*.pdf"))
        if str(p.relative_to(KAYNAK)) not in kullanilan
        and str(p.relative_to(KAYNAK)) not in disla
    ]
    if not havuz:
        print(f"{KAYNAK}/ boş ya da tüm belgeler sette.")
        return
    secilen = random.Random(tohum).sample(havuz, min(eklenecek, len(havuz)))

    GORUNTU.mkdir(parents=True, exist_ok=True)
    sonraki = max((int(s) for s in tahminler), default=0) + 1

    yeni, tam_sayfa_say = [], 0
    print(f"{len(secilen)} belge işleniyor... ({len(disla)} eğitim seti belgesi hariç tutuldu)")
    for kayma, yol in enumerate(secilen):
        sira = sonraki + kayma
        alanlar = cikar(yol)
        # Kırpma ETİKETE çıpalanır, değer kutusuna değil: el yazısını OCR
        # görmediği için değer kutusu ya soyadını kesiyor ya da tamamen başka
        # bir alana oturuyor (bkz. alan_cikarici.etiket_kutusu).
        png, tam = None, True
        with pymupdf.open(yol) as belge:
            for sayfa in belge:
                kutu = etiket_kutusu(sayfa, ETIKET_AD)
                if kutu is None:
                    continue
                kirpma = pymupdf.Rect(*satir_kutusu(sayfa, kutu)) & sayfa.rect
                png = sayfa.get_pixmap(dpi=KIRPMA_DPI, clip=kirpma).tobytes("png")
                tam = False
                break
            if png is None:
                png = belge[0].get_pixmap(dpi=SAYFA_DPI).tobytes("png")
                tam_sayfa_say += 1

        ad = f"{sira:03d}.png"
        (GORUNTU / ad).write_bytes(png)
        yeni.append({"sira": str(sira), "goruntu": ad, "tam_sayfa": tam,
                     "onceki": satirlar.get(str(sira), {}).get("DOGRU_ISIM", ""),
                     "onceki_tur": satirlar.get(str(sira), {}).get("TUR", "")})
        tahminler[str(sira)] = {
            "kaynak_dosya": str(yol.relative_to(KAYNAK)),
            "ocr_isim": alanlar.isim_bosluksuz,
            "ocr_sicil": alanlar.sicil_no,
        }
        satirlar.setdefault(str(sira), {"sira": str(sira)})

    _csv_yaz(basliklar, satirlar)
    TAHMIN.write_text(json.dumps(tahminler, ensure_ascii=False, indent=2), encoding="utf-8")
    _sayfa_yaz(yeni)
    print(f"\n  Doldurulacak : {SAYFA}  ({len(yeni)} belge)")
    print(f"  isim satırı kırpıldı : {len(yeni) - tam_sayfa_say}")
    print(f"  tam sayfa gösterilecek: {tam_sayfa_say}")


def birlestir(indirilen: str) -> None:
    basliklar, satirlar = _csv_oku()
    yeni = {s["sira"]: s for s in csv.DictReader(Path(indirilen).open(encoding="utf-8"))}
    islenen = 0
    for sira, kayit in yeni.items():
        if sira not in satirlar:
            print(f"  uyarı: {sira} sette yok, atlandı")
            continue
        for sutun in SUTUNLAR:
            deger = kayit.get(sutun, "").strip()
            if deger:
                satirlar[sira][sutun] = deger
                islenen += 1
    _csv_yaz(basliklar, satirlar)
    from collections import Counter

    tur = Counter(s.get("TUR", "") for s in satirlar.values() if s.get("TUR", "").strip())
    dolu = sum(1 for s in satirlar.values() if s.get("DOGRU_ISIM", "").strip())
    print(f"{islenen} değer işlendi. İsim dolu: {dolu}/{len(satirlar)}")
    print(f"  tür dağılımı: {dict(tur)}")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "birlestir":
        birlestir(sys.argv[2])
    else:
        hazirla(*sys.argv[1:])
