"""Hibrit katmanın üç kuralını ölçer (blank/duplex, ek/şüpheli, ilgisiz).

    .venv/bin/python araclar/olc_hibrit_katman.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import araclar._kok  # noqa: F401


from belge.alan_cikarici import belge_resmi_mi
from belge.bolucu import plan_cikar
from belge.pdf_okuyucu import bos_sayfa_mi
import pymupdf


def main(klasor: str = "ornekler") -> None:
  ilgisiz = 0
  bos_sayilan = 0
  toplam_sayfa = 0

  kok_dizin = Path(__file__).resolve().parent.parent
  hedef_klasor = Path(klasor)
  if not hedef_klasor.is_absolute():
    hedef_klasor = kok_dizin / klasor

  print(f"Bakılan hedef klasör: {hedef_klasor.resolve()}")

  # TEŞHİS: klasör gerçekten var mı, symlink mi, boş mu?
  if not hedef_klasor.exists():
    print(f"HATA: klasör yok: {hedef_klasor}")
    return
  if hedef_klasor.is_symlink():
    print(f"UYARI: {hedef_klasor} bir symlink, hedefi: {hedef_klasor.resolve()}")
  tum_dosyalar = list(hedef_klasor.iterdir())
  print(f"Klasördeki TÜM öğeler ({len(tum_dosyalar)}): {[p.name for p in tum_dosyalar[:10]]}")

  # Büyük/küçük harf duyarsız glob — case-sensitive dosya sistemlerinde
  # .PDF uzantılı dosyaları da yakalar.
  # Alt klasörlerin içindeki tüm PDF'leri rekürsif olarak bulur
  dosyalar = sorted(
      p for p in hedef_klasor.rglob("*") 
      if p.is_file() and p.suffix.lower() == ".pdf"
  )
  print(f"Bulunan PDF'ler: {len(dosyalar)} adet")
  if not dosyalar and tum_dosyalar:
    print("UYARI: klasörde dosya var ama hiçbiri .pdf/.PDF uzantılı değil.")

if __name__ == "__main__":
    main(*sys.argv[1:])