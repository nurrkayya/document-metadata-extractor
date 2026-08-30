"""`dogrulanmali/` kuyruğunu insana doğrulatır (SPEC 6.12).

    .venv/bin/python araclar/dogrula.py                    # sayfa üret
    .venv/bin/python araclar/dogrula.py birlestir <csv>     # KURU, ne olacağını yazar
    .venv/bin/python araclar/dogrula.py birlestir <csv> --uygula
    .venv/bin/python araclar/dogrula.py --cikti /tmp/cikti     # kuyruk kökü (yoksa .)

Katı kipte uzlaşma sağlanamayan okumalar arşive girmiyor, bu klasörde
bekliyor. Buradaki isimler **çöp değil, yakın**: ölçümde hatalar harf
düzeyinde çıktı (`Çınar` -> `Ginar`, `Nalbant` -> `Nolbant`). Bu yüzden iş
"sıfırdan oku" değil, "öneriyi düzelt ya da onayla" — belirgin şekilde hızlı.

Neden ayrı bir araç
-------------------
`isle.py` belgeleri sınıflandırır ama insan kararını beklemez. Bu araç o
kararı toplar ve sonucunu arşive işler: onaylanan belge `arsiv/`e taşınır,
adı düzeltilmiş hâliyle kaydedilir ve `person_data.json`'a girer.

TC ve sicil ne zaman çıkarılıyor
--------------------------------
Birleştirme sırasında ve **yalnız onaylanan belgeler için**. Doğrulanmamış
belgeye model harcamak boşuna; kullanıcı zaten bir kısmını eleyecek.
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

from belge.adlandirma import cakismasiz, dosya_adi, json_anahtari  # noqa: E402
from belge.alan_cikarici import ETIKET_AD, cikar, etiket_kutusu, satir_kutusu  # noqa: E402
from belge.arsiv import (  # noqa: E402
    ARSIVLE,
    DOGRULANMALI,
    DOGRULANMALI_VERI,
    OKUNAMADI,
    Arsiv,
)

KUYRUK = Path(DOGRULANMALI)
SAYFA = KUYRUK / "dogrula.html"
# Kırpmalar diske yazılıp GÖRELİ YOLLA çağrılır. 175 görüntüyü base64 gömmek
# sayfayı 45 MB yapıyordu; tarayıcıda açılması dakikalar sürerdi. Göreli yol
# da ağ isteği yapmaz — kişisel veri makineden çıkmaz.
KIRPMA_KLASORU = KUYRUK / "_kirpmalar"
KIRPMA_DPI = 300


def _oneri(ad: str, veri: dict) -> str:
    """Model önerisini döndürür — varsa Türkçe hâliyle.

    `dogrulanmali.json` sonradan eklendi; ondan önceki koşularda yalnız ASCII
    dosya adı kaldı (`mehmet_ginar`). Türkçe karakterler o kayıtlarda geri
    getirilemiyor, kullanıcı elle yazacak.
    """
    kayit = veri.get(ad)
    if kayit and kayit.get("isim_onerisi"):
        return kayit["isim_onerisi"]
    return Path(ad).stem.replace("_", " ").upper()


def _kirpma(pdf_yolu: Path) -> bytes | None:
    with pymupdf.open(pdf_yolu) as belge:
        for sayfa in belge:
            kutu = etiket_kutusu(sayfa, ETIKET_AD)
            if kutu is None:
                continue
            r = pymupdf.Rect(*satir_kutusu(sayfa, kutu)) & sayfa.rect
            return sayfa.get_pixmap(dpi=KIRPMA_DPI, clip=r).tobytes("png")
        return belge[0].get_pixmap(dpi=120).tobytes("png")


def hazirla(onceki_csv: str = "", kok: Path | str = ".") -> None:
    """Sayfayı üretir. onceki_csv verilirse cevaplar önden doldurulur ve
    kırpması DEĞİŞEN kartlar işaretlenir — kullanıcı yalnız onlara bakar."""
    kok = Path(kok)
    kuyruk = kok / DOGRULANMALI
    sayfa_yolu = kuyruk / "dogrula.html"
    kirpma_klasoru = kuyruk / "_kirpmalar"
    onceki: dict[str, str] = {}
    if onceki_csv and Path(onceki_csv).exists():
        onceki = {
            s["dosya"]: s.get("DOGRU_ISIM", "")
            for s in csv.DictReader(Path(onceki_csv).open(encoding="utf-8"))
        }
    dosyalar = sorted(kuyruk.glob("*.pdf"))
    if not dosyalar:
        print(f"{kuyruk}/ boş.")
        return
    veri_yolu = kok / DOGRULANMALI_VERI
    veri = json.loads(veri_yolu.read_text(encoding="utf-8")) if veri_yolu.exists() else {}

    kirpma_klasoru.mkdir(exist_ok=True)
    kartlar = []
    print(f"{len(dosyalar)} belge için kırpma üretiliyor...")
    for i, p in enumerate(dosyalar, 1):
        kirpma_adi = f"{p.stem}.png"
        yeni_png = _kirpma(p)
        eski_yol = kirpma_klasoru / kirpma_adi
        degisti = eski_yol.exists() and eski_yol.read_bytes() != yeni_png
        eski_yol.write_bytes(yeni_png)
        # Önceki cevap varsa onu göster; yoksa modelin önerisi.
        oneri = onceki.get(p.name) or _oneri(p.name, veri)
        kartlar.append(
            f"""<div class="kart{' degisti' if degisti else ''}">
  <div class="ust"><span class="dosya">{p.name}</span>
    {'<span class="rozet">KIRPMA DEĞİŞTİ — yeniden bak</span>' if degisti else ''}</div>
  <img src="{kirpma_klasoru.name}/{kirpma_adi}" loading="lazy" alt="isim">
  <input type="text" data-dosya="{p.name}" value="{oneri}"
         autocapitalize="characters" autocomplete="off" spellcheck="false">
  <label class="atla"><input type="checkbox" data-atla="{p.name}"> okunamıyor</label>
</div>"""
        )
        if i % 25 == 0:
            print(f"  {i}/{len(dosyalar)}", flush=True)

    sayfa = """<!doctype html>
<meta charset="utf-8">
<title>Doğrulama kuyruğu</title>
<style>
  body { font-family: system-ui, sans-serif; max-width: 1000px; margin: 2rem auto;
         padding: 0 1rem; background: #fafafa; color: #111; }
  .kart { background: #fff; border: 1px solid #ddd; border-radius: 8px;
          padding: .9rem; margin-bottom: 1rem; }
  .kart.degisti { border-left: 5px solid #c62828; background: #fffafa; }
  .rozet { color: #c62828; font-weight: 700; font-size: .78rem; }
  .ust { display: flex; justify-content: space-between; font-size: .8rem;
         color: #888; margin-bottom: .4rem; }
  img { max-width: 100%; max-height: 110px; border: 1px solid #eee;
        display: block; margin-bottom: .6rem; cursor: zoom-in; }
  img.buyuk { max-height: none; max-width: none; cursor: zoom-out; }
  input[type=text] { width: 100%; padding: .55rem; font-size: 1.05rem;
                     border: 2px solid #e0a800; border-radius: 6px;
                     background: #fffdf5; }
  input[type=text]:focus { border-color: #0066cc; outline: none; }
  input[type=text].onayli { border-color: #2e7d32; background: #f4fbf4; }
  .atla { font-size: .85rem; color: #666; display: inline-block; margin-top: .4rem; }
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
<h1>Doğrulama kuyruğu</h1>
<p>Her kutuda <b>modelin önerisi</b> yazılı (sarı çerçeve). Görüntüyle
karşılaştır: doğruysa dokunma, yanlışsa düzelt. Türkçe karakterleri
kullanabilirsin — öneri ASCII'ye indirgenmiş olabilir. Okunamıyorsa
kutucuğu işaretle; o belge arşive girmez.</p>
__KARTLAR__
<script>
const girisler = () => [...document.querySelectorAll('input[data-dosya]')];
function say() {
  const t = girisler().length;
  const atlanan = [...document.querySelectorAll('input[data-atla]:checked')].length;
  document.getElementById('durum').textContent = t + ' belge, ' + atlanan + ' okunamıyor';
}
girisler().forEach(g => {
  g.dataset.ilk = g.value;
  g.addEventListener('input', () => g.classList.toggle('onayli', g.value !== g.dataset.ilk));
});
document.addEventListener('change', say);
document.addEventListener('click', e => {
  if (e.target.tagName === 'IMG') e.target.classList.toggle('buyuk');
});
function indir() {
  const satirlar = [['dosya', 'DOGRU_ISIM']];
  girisler().forEach(g => {
    const atla = document.querySelector('input[data-atla="' + g.dataset.dosya + '"]').checked;
    satirlar.push([g.dataset.dosya, atla ? '' : g.value.trim()]);
  });
  const csv = satirlar.map(r => r.map(h => '"' + String(h).replace(/"/g,'""') + '"').join(',')).join('\\n');
  const a = document.createElement('a');
  a.href = URL.createObjectURL(new Blob([csv], {type:'text/csv;charset=utf-8'}));
  a.download = 'dogrulama.csv';
  a.click();
}
say();
</script>
"""
    sayfa_yolu.write_text(sayfa.replace("__KARTLAR__", "\n".join(kartlar)), encoding="utf-8")
    print(f"\n  Doldurulacak: {sayfa_yolu}  ({len(dosyalar)} belge)")
    print(f"  Sayfa boyutu: {sayfa_yolu.stat().st_size // 1024} KB")


def _orijinal_ad(dosya: str, arsiv: Arsiv) -> str:
    """Kuyruktaki öneri adından orijinal tarama adını bulur."""
    kayit = arsiv.dogrulanmali_veri.get(dosya)
    if kayit and kayit.get("kaynak"):
        return kayit["kaynak"]
    for v in arsiv.hashler.values():
        if v.get("hedef") == dosya and v.get("kaynak"):
            return v["kaynak"]
    return dosya


def birlestir(
    csv_yolu: str,
    uygula: bool = False,
    kok: Path | str = ".",
    vlm: bool = True,
) -> None:
    """Onaylanan belgeleri arşive taşır; TC/sicil'i yalnız onlar için çıkarır.

    Onay: hash hedefi YENİ arşiv adı, kaynak orijinal tarama adı kalır.
    DOGRU_ISIM boş: okunamadi/ altına orijinal adla, kuyruktan düş, hash güncelle.
    Kuru kipte taşıma yok; raporda okunamıyor sayısı vardır.
    """
    kok = Path(kok)
    kuyruk = kok / DOGRULANMALI
    satirlar = list(csv.DictReader(Path(csv_yolu).open(encoding="utf-8")))
    onayli = [s for s in satirlar if s.get("DOGRU_ISIM", "").strip()]
    okunamiyor = [s for s in satirlar if not s.get("DOGRU_ISIM", "").strip()]
    print(f"{len(satirlar)} kayıt: {len(onayli)} onaylı, {len(okunamiyor)} okunamıyor\n")

    arsiv = Arsiv.yukle(kok)
    okuyucu = None
    if uygula and vlm:
        from belge.isim_okuyucu import IsimOkuyucu, argv_model

        print("Model yükleniyor (TC/sicil için)...")
        okuyucu = IsimOkuyucu(argv_model())

    import shutil

    tasinacak = []
    okunamadi_tasinacak = []
    # Çıkarma ve taşıma BELGE BELGE yapılır. Önceden bütün belgeler
    # çıkarılıp taşıma en sonda tek seferde yapılıyordu: koşu yarıda
    # kesilirse saatlerce süren çıkarma işi tamamen kayboluyordu.
    for sira, satir in enumerate(onayli, 1):
        kaynak = kuyruk / satir["dosya"]
        if not kaynak.exists():
            print(f"  uyarı: {satir['dosya']} kuyrukta yok, atlandı")
            continue
        isim = satir["DOGRU_ISIM"].strip()
        taban = dosya_adi(isim)
        if not taban:
            print(f"  uyarı: {satir['dosya']} adı ASCII'ye çevrilemedi, atlandı")
            continue
        orijinal = _orijinal_ad(satir["dosya"], arsiv)
        # Belgenin KENDİ mevcut adı havuzdan çıkarılır: ad havuzuna
        # dogrulanmali/ de dahil, dolayısıyla kullanıcı öneriyi onayladığında
        # belge kendi adıyla çakışıyor ve gereksiz `_2` alıyordu.
        arsiv.kullanilan_adlar.discard(kaynak.stem)
        ad = cakismasiz(taban, arsiv.kullanilan_adlar)
        arsiv.kullanilan_adlar.add(ad)

        alanlar = cikar(kaynak)
        if okuyucu is not None:
            from belge.sayi_okuyucu import tamamla

            alanlar = tamamla(okuyucu, kaynak, alanlar)
        kayit = {"isim": isim, "tc_no": alanlar.tc_no, "sicil_no": alanlar.sicil_no}
        arsiv.person_data.setdefault(json_anahtari(isim), []).append(kayit)
        hedef = kok / ARSIVLE / f"{ad}.pdf"
        tasinacak.append((kaynak, hedef, orijinal))
        arsiv.dogrulanmali_veri.pop(satir["dosya"], None)
        arsiv.hash_hedef_guncelle(satir["dosya"], f"{ad}.pdf", orijinal)

        if uygula:
            hedef.parent.mkdir(parents=True, exist_ok=True)
            if hedef.exists():
                raise FileExistsError(f"hedef zaten var: {hedef}")
            shutil.move(str(kaynak), str(hedef))
            arsiv.kaydet()          # her belgede kalıcı: kesilirse iş durur, kaybolmaz
        if sira % 10 == 0:
            print(f"  {sira}/{len(onayli)} ...", flush=True)

    for satir in okunamiyor:
        kaynak = kuyruk / satir["dosya"]
        if not kaynak.exists():
            print(f"  uyarı: {satir['dosya']} kuyrukta yok, atlandı")
            continue
        orijinal = _orijinal_ad(satir["dosya"], arsiv)
        hedef = kok / OKUNAMADI / orijinal
        okunamadi_tasinacak.append((kaynak, hedef, orijinal))
        arsiv.dogrulanmali_veri.pop(satir["dosya"], None)
        arsiv.kullanilan_adlar.discard(Path(satir["dosya"]).stem)
        arsiv.hash_hedef_guncelle(satir["dosya"], orijinal, orijinal)
        if uygula:
            hedef.parent.mkdir(parents=True, exist_ok=True)
            if hedef.exists():
                raise FileExistsError(f"hedef zaten var: {hedef}")
            shutil.move(str(kaynak), str(hedef))
            arsiv.kaydet()

    print(f"\n{len(tasinacak)} belge arşive taşınacak:")
    for kaynak, hedef, _orj in tasinacak[:10]:
        print(f"  {kaynak.name:<34} -> {hedef.name}")
    if len(tasinacak) > 10:
        print(f"  ... {len(tasinacak) - 10} tane daha")
    print(f"{len(okunamadi_tasinacak)} belge okunamadi/ altına (orijinal tarama adı)")

    if not uygula:
        print("\nKURU: hiçbir dosya taşınmadı. Uygulamak için --uygula")
        return
    print(f"\n{len(tasinacak)} belge arşive taşındı, {len(okunamadi_tasinacak)} okunamadi/, "
          "person_data.json güncellendi.")


def _cikti_arg(argv: list[str]) -> Path:
    if "--cikti" in argv:
        return Path(argv[argv.index("--cikti") + 1])
    return Path(".")


if __name__ == "__main__":
    cikti = _cikti_arg(sys.argv)
    if len(sys.argv) > 1 and sys.argv[1] == "birlestir":
        birlestir(sys.argv[2], uygula="--uygula" in sys.argv, kok=cikti)
    else:
        onceki = sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith("-") else ""
        hazirla(onceki, kok=cikti)
