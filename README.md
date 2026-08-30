# Taranmış Sicil Dosyalarından Metadata Çıkarma

Taranmış esnaf/ticaret sicil dosyalarından **isim, TC kimlik no ve sicil no** çıkarır;
belgeyi kişi adına göre yeniden adlandırıp arşive taşır ve çıkarılan veriyi merkezi bir
JSON dosyasına yazar.

Teknik şartname ve bütün ölçüm sonuçları: **[SPEC.md](SPEC.md)**
Çalışma günlüğü ve alınan derslerin kaydı: **[staj-gunlugu.md](staj-gunlugu.md)**

## Bağlayıcı kısıt

Belgeler kişisel veri içerir ve **kurum dışına çıkamaz.** Bulut API seçeneği kalıcı olarak
kapalıdır; tüm işlem yerel donanımda yapılır (MacBook Air M4, 16 GB). Kişisel veri git
geçmişine hiç girmez — `ornekler/`, `arsiv/`, `altin_set/` ve türevleri `.gitignore`'dadır.

## İki külliyat

Proje iki farklı belge grubuyla çalışıyor ve doğrulukları çok farklı:

| | **1. külliyat** (288 belge) | **2. külliyat** (721 belge) |
|---|---|---|
| Dönem | 1990 sonrası | 1980'ler |
| Alanların doldurulması | matbu | **daktilo ya da el yazısı** |
| `sicil_no` | 5 haneli | 4 haneli |
| `tc_no` | her belgede | ~%10 belgede |

## Doğruluk (insan tarafından doğrulanmış altın setlere karşı ölçüldü)

**1. külliyat** — 80 belgelik altın set:

| Alan | İsabet | Kapsama |
|---|---|---|
| `isim` | %95.0 (OCR+VLM birleşik) | %100 |
| `tc_no` | %100 | %98.7 |
| `sicil_no` | %98.6 | %96.2 |

**2. külliyat** — 40 belgelik ayrı altın set (el yazısı 18, daktilo 9, matbu 5):

| Alan | Sonuç |
|---|---|
| `isim`, tek sayfa | %44 isabet |
| `isim`, **çok sayfalı uzlaşma** | **%88 isabet** (el yazısı), kapsama %44 |
| `sicil_no` | kapsama %82, OCR ile 16/16 uyuşma |

*İsabet* = üretilen değerlerin kaçı doğru. *Kapsama* = kaç belgede değer üretilebildi.
Ayrım önemli: boş bırakmak zararsız, yanlış değer üretmek sessiz ve tehlikelidir.

El yazısında yüksek isabet ancak düşük kapsamayla elde ediliyor: sistem emin olduğunu
verir, olmadığını `okunamadi/`ya atar, kalanı insan tamamlar.

## Kullanım

```bash
python -m venv .venv && .venv/bin/pip install -r requirements.txt

# Web arayüzü (yerel; çıktı web_cikti/ — proje arsiv/ ile karışmaz)
.venv/bin/python web/uygula.py                   # http://127.0.0.1:8765
# PDF sürükle → İşle → çok kişili sayfa ata / birleştir-taşı → Onayla
# VLM yoksa OCR + uyarı. Model yavaştır; belgeler kuyrukta işlenir.

.venv/bin/python isle.py ornekler                # KURU — hiçbir dosya yazılmaz
.venv/bin/python isle.py ornekler --vlm          # VLM'li (gerçek koşuda gerekli)
.venv/bin/python isle.py ornekler --vlm --uygula # gerçekten taşır
.venv/bin/python isle.py ornekler --vlm --kati   # yalnız doğrulanmışı arşivle
.venv/bin/python isle.py ornekler --cikti /tmp/cikti  # çıktı kökü (yoksa .)
.venv/bin/python isle.py ornekler --vlm --model <hf-id>  # geçici VLM; varsayılan değişmez
```

Varsayılan kurudur: ne yapılacağı önce raporlanır. `--uygula` dosyaları taşır ve geri
alması zordur. İkinci külliyat (el yazısı) için `--vlm --kati` önerilir: uzlaşmayan
okumalar arşive girmez, `dogrulanmali/` kuyruğuna düşer. `--kati` varsayılan kapalıdır;
`--vlm --uygula` iken `--kati` yoksa uyarı basılır, onay istenmez.

**Çıktı klasörleri**

| Klasör | İçerik |
|---|---|
| `arsiv/` | `ad_soyad.pdf` olarak adlandırılmış belgeler |
| `okunamadi/` | ismi okunamayan belgeler, orijinal adıyla |
| `ayrildi/` | yanlış birleştirilmiş belgelerden ayrılan parçalar; `asil/` altında kaynakları |
| `bolunmeli/` | otomatik bölünemeyen yanlış birleştirmeler (elle inceleme) |
| `dogrulanmali/` | `--kati` ile: sayfalar arası uzlaşma sağlanamamış okumalar. Dosya adı model önerisidir, `person_data.json`'a girmez |
| `hata/` | işlenirken patlayan belgeler (`--uygula` ise taşınır, hash işaretlenir) |
| `person_data.json` | ad anahtarlı merkezi indeks |
| `web_cikti/` | web arayüzünün çıktı kökü (`arsiv/` ile karışmaz; `--cikti` ile değişir) |

## Yapı

```
belge/                 çekirdek (OCR, VLM, arşiv, bölme)
  yollar.py              proje kökü + çıktı klasör adları (tek kaynak)
  islem.py               alan toplama, uzlaşma, birleştirme (CLI+web ortak)
  pdf_okuyucu.py         metin katmanı, boş sayfa, sayfa/bölge görüntüsü
  alan_cikarici.py       OCR metninden alan çıkarma + doğrulama
  isim_okuyucu.py        VLM ile isim okuma, OCR ile birleştirme
  sayi_okuyucu.py        VLM ile TC/sicil okuma
  bolucu.py              yanlış birleştirilmiş belgeleri ayırma
  adlandirma.py          ASCII dosya adı, JSON anahtarı, çakışma
  arsiv.py               plan/uygula, person_data.json, mükerrer atlama
  kisi_esleme.py         isimle kişi önerisi (karar değil)
web/                   yerel arayüz (FastAPI + tek sayfa)
  uygula.py              sunucu; belge.islem / belge.arsiv kullanır
araclar/               ölçüm, altın set, kural sınaması (ana akış değil)
isle.py                uçtan uca CLI girişi
```

Görsel mimari şeması: **[architecture_diagram.svg](architecture_diagram.svg)**

Çıktı klasör adları `belge/yollar.py` içindedir; kişisel veri `.gitignore` ile
versiyon kontrolüne girmez.

## Model

Proje, ağırlıkları repoya **hiç dahil etmez** — VLM, çalışma anında Hugging Face
Hub'dan Apple MLX formatında indirilir (yerel donanımda çalışır, buluta veri
gitmez). Varsayılan model `belge/isim_okuyucu.py` içinde tek yerde tanımlıdır:

```python
VARSAYILAN_MODEL = "mlx-community/Qwen3-VL-8B-Instruct-8bit"
```

Geçici olarak başka bir model denemek için (varsayılanı değiştirmeden):

```bash
.venv/bin/python isle.py ornekler --vlm --model mlx-community/InternVL3-14B-4bit
# veya: VLM_MODEL=<hf-id> .venv/bin/python isle.py ornekler --vlm
```

## Bu repoda ne var, ne yok

Bu repo yalnızca **projeyi çalıştırmak için gereken kaynak kodu ve dokümantasyonu**
içerir. Aşağıdakiler bilinçli olarak dışarıda bırakılmıştır (`.gitignore`):

| Dışarıda bırakılan | Neden |
|---|---|
| `ornekler/`, `arsiv/`, `web_cikti/`, altın setler | kişisel veri (isim, TC no) |
| `models/`, `*.safetensors`, `.cache/` | model ağırlıkları — GB'larca, HF Hub'dan otomatik iner |
| `.venv/`, `__pycache__/` | Python sanal ortamı / derleme çıktısı, `requirements.txt` ile yeniden kurulur |
| `staj-gunlugu.md` ve AI-yardımcı bağlam dosyaları | proje çalışmasıyla ilgisiz kişisel/süreç notları |

## Ölçüm araçları

```bash
# model gerektirmeyenler
.venv/bin/python araclar/sinama.py               # kural sınamaları (bölme JSON dahil)
.venv/bin/python araclar/olc_alan_cikarimi.py    # külliyat geneli kapsama
.venv/bin/python araclar/incele_ornekler.py      # külliyat keşfi (tek seferlik)

# 1. külliyat ölçümleri
.venv/bin/python araclar/olc_dogruluk.py         # isim doğruluğu
.venv/bin/python araclar/olc_tc_sicil.py vlm     # TC/sicil doğruluğu
.venv/bin/python araclar/olc_bolme.py vlm        # bölme planı

# 2. külliyat (el yazısı) ölçümleri
.venv/bin/python araclar/olc_elyazisi.py         # isim, türe göre
.venv/bin/python araclar/olc_coklu_sayfa.py      # çok sayfalı uzlaşma
.venv/bin/python araclar/olc_sicil_elyazisi.py   # sicil, geometrik şerit

# doğrulama kuyruğu (--kati koşusundan sonra)
.venv/bin/python araclar/dogrula.py              # sayfa üret
.venv/bin/python araclar/dogrula.py birlestir dogrulama.csv           # KURU
.venv/bin/python araclar/dogrula.py birlestir dogrulama.csv --uygula  # arşive taşı

# altın set hazırlama / birleştirme
.venv/bin/python araclar/altin_set_hazirla.py    # 1. külliyat, isim
.venv/bin/python araclar/altin_set_tc_sicil.py   # 1. külliyat, TC + sicil
.venv/bin/python araclar/altin_set_elyazisi.py   # 2. külliyat, isim + tür
```

Altın set 80 belgeliktir ve doğru değerler yalnızca görüntüye bakılarak girilmiştir;
çıkarıcının/modelin okumaları doldurma sayfasında **gösterilmez**, yoksa ölçüm modelin
kendini doğrulamasına döner.

## Bilinen açıklar

- **R8 alt sınır:** 13/288 belge çoklu-TC ile bulundu; ikinci kişisi OCR'da görünmeyen
  birleştirmeler hâlâ sessiz kalabilir. Tespit artık birden fazla sicil adayına da
  bakıyor (`Sicil No :` dahil); ikinci kişi bulunamazsa `bolunmeli/`ye düşer.
- **sicil #11:** DN metinde yok, çapraz doğrulama yapılamıyor; tek sessiz yanlış.
- **El yazısı:** uzlaşma %88 isabet / %44 kapsama (18 belge). %90–95 otomatik doğruluk
  bu donanım/model sınıfıyla gerçekçi görünmüyor; kalanı `--kati` + insan.
- 2. külliyatın tam 721 belgelik koşusu henüz yapılmadı.
