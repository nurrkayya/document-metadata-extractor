# Belgelerden Metadata Çıkarma — Teknik Şartname

> 52 soruluk netleştirme turunun çıktısı.
> **v2 — 2026-08-08:** Gerçek belgeler incelendikten sonra ölçülen verilerle güncellendi.

---

## 1. Amaç

Taranmış sicil dosyalarından **isim, TC kimlik no ve sicil no** çıkarmak; belgeyi kişi adına
göre yeniden adlandırıp arşive taşımak ve çıkarılan veriyi merkezi bir JSON dosyasına
kaydetmek.

Bu bir **belge arşivleme/indeksleme** sistemidir. Sistemin başarısı büyük ölçüde tek bir alana
bağlıdır: **kişinin adı** (dosya adı buradan üretilir).

---

## 2. Külliyatın gerçek durumu (ölçüldü)

288 belgenin tamamı tarandı, 6 sayfa gözle incelendi.

| Ölçüm | Değer |
|---|---|
| Belge sayısı | 288 |
| Toplam sayfa | 2611 |
| Sayfa/belge | en az 1, en çok 38, **ortalama 9.1** |
| Metin (OCR) katmanı olan | **288/288** |
| Boş/az metinli sayfa | 221 (%8.5) — çoğu çift taraflı taramanın boş arka yüzü |
| Toplam boyut | 1.1 GB |

**Belgelerin niteliği:** Isparta Esnaf/Ticaret Sicil dosyaları. Her "bölüm" bir kişinin
dosyasıdır ve içinde birden fazla resmî evrak bulunur: sicil tasdiknamesi, kurum yazıları,
e-devlet ekran çıktıları, fotokopi nüfus cüzdanı.

**El yazısı durumu:** Çıkaracağımız alanlar (isim, TC, sicil no) **matbu/bilgisayar
çıktısıdır.** El yazısı belgelerde mevcuttur ancak yalnızca **imza ve mühürlerde** görülür —
bunlar çıkarılacak alanlar değildir. Bu, projenin başlangıçtaki "Türkçe el yazısı okuma"
varsayımını geçersiz kılar ve doğruluk hedefini belirgin şekilde kolaylaştırır.

**OCR katmanının kalitesi:** Orta. Taramanın üzerine bindirilmiş tek fontlu (Tahoma) bir OCR
katmanıdır. Temiz matbu alanlarda güvenilir; stilize/büyük puntolu başlıklarda bozuluyor
(`ESNAF VE SANATKAR SİCİL TASDİKNAMESİ` → `EsI\kF vE sANATKAR sicİr TAsDiKNAMEsi`).

### 2.1 OCR metninden alan bulunabilirliği (ölçüldü)

> Bu tablo ilk ölçüme aittir ve desenler o zaman 4–6 haneyi kabul ediyordu.
> Sonradan SPEC 5.3'ün 5 hane kuralı uygulandı (bölüm 6.4); süzgeçten sonraki
> gerçek rakamlar sağdaki sütunda.

| Alan | İlk ölçüm | 5 hane süzgecinden sonra |
|---|---|---|
| Sicil no — `DN47789` | 262/288 | **221/288** |
| Sicil no — `32/47789` | 248/288 | **204/288** |
| TC kimlik no | 250/288 | **253/288** (checksum'lı) |
| `Adı Soyadı` etiketli satır | 194/288 | — |

Düşüş bir gerileme değil: elenen eşleşmeler OCR'ın rakam düşürdüğü bozuk
değerlerdi ve ölçümde sessiz yanlış üretiyorlardı (bölüm 6.4).

### 2.2 Kritik kısıt: OCR isim boşluklarını kaybediyor

OCR `AdıSoyadı :AYŞENURDEMİR` üretiyor. Bu "Ayşe Nur Demir" mü, "Ayşenur Demir" mü?

**Harf koordinatlarıyla kurtarılamaz — ölçüldü:** 551 bitişik büyük-harf dizisinin 550'sinde
harfler arası mesafe tam **0.00**. OCR motoru harfleri bitişik yerleştirmiş; boşluk bilgisi
metin katmanında hiç yok.

**Sonuç: isim boşlukları yalnızca sayfa görüntüsünden okunabilir.** Bu, VLM'in külliyattaki
asıl varlık sebebidir.

### 2.3 İkinci külliyat (2026-08-10 eklendi)

`ornekler/` klasörüne ikinci bir belge grubu eklendi: **721 dosya, 14.7 GB.**
İlk gruptan temelde farklı ve ilk grup için ayarlanmış kurallar burada çalışmıyor.

| | İlk külliyat | İkinci külliyat |
|---|---|---|
| Dönem | 1990 sonrası | 1980'ler |
| Alanların doldurulması | matbu/bilgisayar | **daktilo ya da EL YAZISI** |
| `sicil_no` | 5 haneli | **4 haneli** |
| `tc_no` | 288/288 belgede | **~%10 belgede** |
| Bölüm numarası | bir bölüm = bir belge | **tekil değil**, 721 dosya 168 numaraya dağılmış |

**El yazısı:** 40 belgelik altın sette 18'i el yazısı, 9'u daktilo, 5'i matbu.
SPEC 2'deki "el yazısı yalnız imza ve mühürlerde görülür" tespiti bu grup için
**geçersizdir**; projenin başlangıçtaki varsayımı doğruymuş.

**`tc_no` — ölçüldü, 150 belgelik örneklem:**

| | Belge |
|---|---|
| `T.C. Kimlik No` etiketi var | 21 (%14) |
| Geçerli TC metinde var | 15 (%10) |
| Çıkarıcı değer üretti | 14 (%9) |
| Üretilenin geçerliliği | 14/14 |

Azınlık ama **yok değil** — külliyat geneline vurunca ~72 belge. Bu yüzden TC
araması bu grupta da açık kalır. Çıkarıcı zaten doğru davranıyor: alanı olan
belgede buluyor, olmayanda hiçbir şey üretmiyor. VLM yalnız etiket bulunduğunda
çağrıldığı için (`sayi_okuyucu.tamamla`), formda alan yoksa model hiç devreye
girmiyor; girdiği 6 belgede de TC checksum'ı süzgeç görevi görüyor.

**Bölüm numarası kişi kimliği DEĞİLDİR** (bkz. 6.8).

---

## 3. Çıkarılacak alanlar

| Alan | Açıklama | Doğrulama |
|---|---|---|
| `isim` | Ad + soyad, Türkçe karakterler korunur (`"Ayşe Nur Demir"`) | Çok sayfalı çapraz doğrulama |
| `tc_no` | 11 haneli TC kimlik no | TC checksum |
| `sicil_no` | **4 ya da 5 haneli**, sadece rakam | `DN` ↔ `32/` çapraz kontrol + görüntü |

### Sicil no

Belgede iki ayrı biçimde geçer:
- 1. sayfa sol üst: `DN47789` — **tire yoktur**
- Metin içinde: `Esnaf ve Sanatkar Sicil No: 32/47789`

İkisi de okunur ve karşılaştırılır. Uyuşurlarsa kesin kabul edilir.

**Sicil no belgenin kimliğidir:** hiçbir belgede birden fazla `DN` geçmiyor (221 belgede tam
1, 67 belgede 0). Bu yüzden en güvenilir alandır.

**Ancak `DN` ∪ `32/` birleşimine bakıldığında 5 belgede iki farklı sicil no var** — bunlar
yanlış birleştirilmiş dosyalar (R8). Ayrıca #32'de ikinci kişinin sicil no'su `Sicil No :
35197` biçiminde yazılmış: ne `DN` ne `32/` deseni yakalıyor. Yani "belgede tek sicil no
vardır" varsayımı yalnızca **doğru bölünmüş** dosyalar için geçerlidir.

### TC kimlik no — belirsizlik uyarısı

**13 belgede birden fazla geçerli TC var** (hepsinde tam 2 tane). Bu rakam ilk yazımdaki
40'ın yerini aldı: 40, checksum uygulanmadan sayılmıştı ve OCR'ın ürettiği 11 haneli
çöp sayıları da içeriyordu.

**İlk açıklama yanlıştı.** "Eş, baba, kefil gibi ilgili kişiler" varsayılmıştı. Altın
setteki 6 çoklu-TC belgesi gözle incelendi: **altısı da yanlış birleştirilmiş dosya** —
bir PDF'te iki ayrı kişinin evrakı bulunuyor. Bkz. R8.

**Kural (kullanıcı kararı): DN/sicil no'nun sahibi olan kişinin TC'si alınır.** Uygulamada
`Adı Soyadı` ve `T.C. Kimlik No` alanlarının DN ile aynı belge bölümünde geçtiği kayıt esas
alınır. Belirlenemezse alan boş bırakılır.

**Ölçüldü (bölüm 6.4):** kural işliyor. Çoklu-TC belgelerinde çıkarıcı 5 değer üretti,
5'i de DN sahibinin TC'siydi; yanlış kişi seçimi sıfır. Belirsizliği çözemediği 8 belgede
değer üretmeyi reddetti.

**Çıkarılmayacak:** Tarih (kapsam dışı).

---

## 4. Çıktı

### 4.1 Dosya adlandırma

- Format: `isim_soyisim.pdf`
- ASCII'ye çevrilir, küçük harf: `Şener Çeliköz` → `sener_celikoz.pdf`
- Çift isim/soyisim tamamen girer: `Ali Rıza Demir Kaya` → `ali_riza_demir_kaya.pdf`
- Çakışma: sona sayı eklenir → `ahmet_yilmaz_2.pdf`

### 4.2 Klasör yapısı

```
arsiv/                    ← düz dizin, alt klasör yok
  ayse_nur_demir.pdf
  sener_celikoz.pdf
okunamadi/                ← isim okunamayan belgeler, orijinal adıyla
  bolum_011_sayfa_67-73.pdf
dogrulanmali/             ← `--kati` ile: okundu ama sayfalar arası uzlaşma
  ayse_nur_demir.pdf        sağlanamadı. Dosya adı MODEL ÖNERİSİDİR;
                            person_data.json'a girmez (bölüm 6.11)
ayrildi/                  ← bölünen belgelerin parçaları arşive gider,
  asil/                     asılları buraya (SPEC R8, bölüm 6.6)
bolunmeli/                ← otomatik bölünemeyen yanlış birleştirmeler
hata/                     ← işlenirken patlayan belgeler (hash işaretli)
person_data.json          ← arsiv/ dışında, merkezi indeks
.islenmis_hashler.json    ← mükerrer atlama kaydı (SPEC 4.5)
```

### 4.3 person_data.json şeması

```json
{
  "AYSE_NUR_DEMIR": [
    {
      "isim": "Ayşe Nur Demir",
      "tc_no": "12345678901",
      "sicil_no": "47789"
    }
  ]
}
```

- Okunamayan alan → boş string `""`
- Güven skoru tutulmaz (kullanıcı kararı)

### 4.4 Orijinal dosyalar

İşlenen belge kaynak klasörden **taşınır**.

### 4.5 Tekrar işleme

Dosya içeriğinin hash'i tutulur; aynı belge ikinci kez gelirse **atlanır**.

---

## 5. Teknik yaklaşım

### 5.1 Model

| Konu | Karar | Gerekçe |
|---|---|---|
| Yaklaşım | Yerel VLM + OCR metni birlikte | Veri kurum dışına çıkamaz |
| Altyapı | **MLX-VLM** | Apple Silicon'da en verimli; kuantizasyon kontrolü bizde |
| Model boyutu | **8B sınıfı, 8-bit** (~9 GB) | 16 GB'ta rahat sığar |
| Prompt dili | İngilizce talimat → Türkçe değer | Küçük modellerde talimat takibi daha güvenilir |
| Bulut API | **Kalıcı olarak kapalı** | Belgeler kurum dışına çıkamaz |

**Donanım:** MacBook Air M4, 16 GB unified memory.

Geçici deneme: `--model` / `VLM_MODEL` (`IsimOkuyucu` tek kanca). Üretim varsayılanı 8B 8-bit kalır.

### 5.2 İşlem hattı

OCR katmanı her belgede var, bu yüzden akış **OCR öncelikli**dir. VLM yalnızca OCR'ın
yetmediği yerlerde devreye girer — bu hem çok daha hızlı hem daha doğrudur.

```
PDF
 │
 ├─ 1) OCR metninden desenle çıkar
 │      • sicil_no : DN47789 ↔ 32/47789 çapraz kontrolü
 │      • tc_no    : 11 hane + checksum (DN sahibine ait olan)
 │      • isim     : "Adı Soyadı" satırı  →  BOŞLUKSUZ gelir
 │
 ├─ 2) Boş sayfaları ele (metin yok + görüntü neredeyse beyaz)
 │
 └─ 3) VLM ile tamamla — yalnızca gerekli sayfalarda:
        • isim boşluklandırma (görüntüden okuma) — HER BELGEDE gerekli
        • OCR'ın bulamadığı/çakıştığı alanlar
        • çapraz doğrulama için ikinci okuma

 ortak devam:
   → doğrulama katmanı
   → dosya adı üretimi (ASCII, küçük harf, çakışma çözümü)
   → arsiv/ veya okunamadi/ + person_data.json
```

### 5.3 Doğrulama kuralları

| Kural | Başarısız olursa |
|---|---|
| TC checksum | Bölge büyütülüp VLM'e yeniden okutulur. Yine tutmazsa `""` |
| Sicil no 4–5 hane / rakam | `""` |
| Sicil no **4 hane** ve çapraz doğrulanmış | Yetmez — görüntüden onaylanır (6.10) |
| `DN` ↔ `32/` çapraz kontrol | Uyuşmazsa VLM'e sorulur, çözülmezse `""` |
| İsim sayfalar arası çapraz kontrol | Uyuşmazsa isim okunamamış sayılır |
| İsim okunamadı | Belge `okunamadi/` klasörüne, orijinal adıyla |

Genel ilke: **akış durmaz.**

### 5.4 Görüntü işleme

- 300 DPI
- **Ön işleme yok (deskew/kontrast uygulanmaz) — ham görüntü**

Bu karar başta matbu külliyat için alınmıştı. El yazısı külliyatı gelince yeniden
sınandı, çünkü soluk kurşun kalem/sararmış kağıtta kontrastın fark yaratması
beklenirdi. **Ölçüldü, yaratmadı** (32 belgelik el yazısı altın seti,
`araclar/olc_onisleme.py`):

| Yöntem | El yazısı | Tümü |
|---|---|---|
| **ham** | **8/18** | 14/32 |
| CLAHE (uyarlamalı histogram) | 5/18 | 10/32 |
| uyarlamalı eşikleme | 7/18 | 13/32 |
| keskinleştirme (unsharp) | 8/18 | 16/32 |

CLAHE ve eşikleme **zarar veriyor**: kontrastı artırmak kağıt dokusunu da
güçlendiriyor, ikili görüntü ise soluk kalem izlerinin bir kısmını siliyor.
Keskinleştirme el yazısında hiçbir şey değiştirmiyor; toplamda 2 belge
kazandırıyor ama 32'de 2 gürültü sınırında, iddia edilemez.

**Büyütme ve çözünürlük de denendi, o da zarar verdi:**

| Yöntem | El yazısı | Tümü |
|---|---|---|
| **ham (300 DPI)** | **8/18** | 14/32 |
| 2× interpolasyon | 6/18 | 13/32 |
| 600 DPI (gerçek detay) | 6/18 | 13/32 |

İkisinin **birebir aynı** sonucu vermesi teşhis niteliğinde: interpolasyonla piksel
eklemek ile gerçekten daha detaylı taramak arasında model fark görmüyor. Darboğaz
çözünürlük ya da görsel belirteç sayısı değil. Model görüntüyü zaten sabit bir ızgaraya
indiriyor olmalı; büyütmenin getirdiği yumuşama harf kenarlarını bozuyor.

**Sonuç: görüntü tarafında yapılacak bir şey kalmadı.** El yazısı için denenen dört ucuz
kaldıracın dördü de kapandı:

| Kaldıraç | Sonuç |
|---|---|
| İstem uyarlaması | fark yok (%44 → %44) |
| OCR ile birleştirme | zarar (7 → 6) |
| Ön işleme (CLAHE / eşikleme / keskinleştirme) | zarar ya da fark yok |
| Büyütme / yüksek DPI | zarar (8 → 6) |
| **Çok sayfalı uzlaşma** | **%44 → %88 isabet** |

Kalan tek denenmemiş kaldıraç **daha büyük model** (16 GB'da 4-bit); onun dışında yol
insan-döngüde tasarım (bölüm 6.12).

---

## 6. Doğruluk hedefi ve ölçüm

- **Hedef: isim alanında ~%95**
- **Ölçüm:** 30 belgelik katmanlı altın set (temiz 10, hafif bozuk 5, ağır bozuk 12, isim
  bulunamayan 3). Doğru değerler kullanıcı tarafından yalnızca görüntüye bakılarak girildi;
  yanlılık olmasın diye çalışma dosyasında OCR/VLM okumaları gösterilmedi.
  Araç: `araclar/olc_dogruluk.py`

### 6.1 Ölçülen sonuç (2026-08-08)

**30 belgelik ilk set** (zor vakalara ağırlıklı, dolayısıyla kötümser):

| Yöntem | İlk ölçüm | Çıkarıcı iyileştirmesi | + işaret aktarımı |
|---|---|---|---|
| Sadece OCR | 14/30 (%46.7) | 18/30 (%60.0) | 18/30 (%60.0) |
| Sadece VLM | 20/30 (%66.7) | 22/30 (%73.3) | 22/30 (%73.3) |
| Birleşik | 23/30 (%76.7) | 27/30 (%90.0) | 29/30 (%96.7) |

**80 belgelik genişletilmiş set** (yeni 50 belge külliyat dağılımına orantılı seçildi —
bu rakam daha güvenilir):

| Yöntem | Doğru |
|---|---|
| Sadece OCR | 45/80 (%56.2) |
| Sadece VLM | 64/80 (%80.0) |
| **Birleşik (kullanılan)** | **76/80 (%95.0)** |

**Hedefe ulaşıldı (%95).** Kalan 4 hata: 1 harf çiftlenmesi, 1 harf düşmesi, 1 İ/I (iki
kaynakta da nokta yok), 1 okunamayan belge (bkz. R7).

Dikkat: birleştirmenin katkısı belirleyici — ne OCR ne VLM tek başına %80'i geçemiyor,
ikisi birlikte %95 veriyor. Doğruluk tek bir bileşenden değil, ikisinin birbirinin
körlüğünü kapatmasından geliyor.

### 6.3 Birleştirme ilkesi

Başta "boşluklar VLM'den, işaretler OCR'dan" kuralı denendi ve **ölçümde başarısız oldu**:
üç belgeyi düzeltirken üç belgeyi bozdu. Varsayım yanlıştı — hangi tarafın hangi bilgiyi
kaybettiği belgeye göre değişiyor (OCR bir belgede boşluğu, başkasında işareti düşürüyor;
VLM de aynısını yapıyor).

Çalışan ilke simetrik: **her iki kayıp da olur, uydurma olmaz.** Bir tarafta boşluk varsa
gerçekten vardır; bir tarafta işaret (Ç Ğ İ Ö Ş Ü) varsa gerçekten vardır. Bu yüzden iki
okumanın **birleşimi** alınır, biri seçilmez.

### 6.4 `tc_no` ve `sicil_no` doğruluğu (2026-08-10)

Bu iki alan için altın sette uzun süre doğru değer yoktu; elimizdeki rakamlar **kapsama**ydı
(bir değer üretilebildi mi), doğruluk değil. 80 belgede doğru değerler girildi
(`araclar/altin_set_tc_sicil.py`), ölçüm `araclar/olc_tc_sicil.py`.

| | İsabet (üretilenin doğruluğu) | Kapsama | Sessiz yanlış |
|---|---|---|---|
| `tc_no` | **59/59 (%100)** | %76.6 | **0** |
| `sicil_no` | **69/70 (%98.6)** | %87.5 | 1 |

**İsabet burada kapsamadan daha önemli.** İki hata biçimi eşdeğer değil:

- *kaçırdı* — alan boş kalır. Zararsız: kimse yanlış bilgilendirilmez.
- *sessiz yanlış* — dolu ama hatalı. Tehlikeli: arşivde yanlış TC durur, fark edilmez.

Çıkarıcı bir değer ürettiğinde neredeyse hiç yanılmıyor. Kalan tek sessiz yanlış (#11):
DN metinde hiç yok, sicil tek kaynaktan geliyor, çapraz kontrol yapılamıyor — yapısal bir
kör nokta, ikinci bir kaynak (VLM) olmadan kapanmaz.

**Ölçümün ortaya çıkardığı iki şey:**

1. **Altın set iki yerde yanlıştı** (#6 TC, #76 sicil — ikisinde de 3. hane). Kaynak
   görüntüye bakılmasaydı olmayan bir çıkarıcı hatası "düzeltilecekti". 17 numaralı
   belgedeki `MURAK/MURAT` vakasının tekrarı.
2. **SPEC 5.3'ün "sicil no 5 hane değilse boş" kuralı hiç yazılmamıştı.** Eklendi — ama
   adayları topluca reddederek değil **tek tek süzerek**: OCR bir kaynakta rakam düşürüp
   öbüründe düşürmeyebiliyor. Sağlam kaynağı elde tutmak hem yanlış değeri engelledi hem
   kapsamayı artırdı (69 → 70).

### 6.5 Adım 10 — VLM ile TC/sicil okuma (2026-08-10)

6.4 sorunun **kapsama** olduğunu gösterdi, ve kaçan 18 TC'nin 18'inde de etiketin konumu
bulunabiliyordu: çıkarıcı alanın nerede olduğunu biliyor, yalnızca okuyamıyor. VLM devreye
alındı (`belge/sayi_okuyucu.py`), yalnızca **boş alanlar** için.

| | İsabet | Kapsama | Sessiz yanlış |
|---|---|---|---|
| `tc_no` | 59/59 → **76/76 (%100)** | %76.6 → **%98.7** | 0 → 0 |
| `sicil_no` | 69/70 → **71/72 (%98.6)** | %87.5 → **%90.0** | 1 → 1 |

R6 alt kümesi **13/13**, R8 alt kümesi **6/6** — ikisi de tam.

**Birleştirme kuralı isimdekinden farklı, çünkü asimetri ölçüldü.** İsimde iki okumanın
birleşimi alınır (6.3): orada her iki taraf da bilgi kaybediyordu. Burada OCR bir değer
ürettiğinde 59/59 doğru — böyle bir kaynağı model okumasıyla harmanlamak yalnızca zarar
verir. Kural: **OCR ürettiyse kalır, VLM yalnızca boşluk doldurur.**

**Başarısız olan deneme — sicil yedek konumu (0/7):** DN kelimesi okunamayan belgelerde
`Esnaf ve Sanatkar Sicil No` etiketine düşüldü. Sonuç 7 zararsız "kaçırdı"yı tehlikeli
"sessiz yanlış"a çevirdi. İki hata üst üste biniyordu:

1. Etiket sayfa **başlığını** yakalıyor: `Esnaf ve Sanatkar Sicil` dört kelimelik pencerede
   hedefe 2 mesafede kalıp eşiği geçiyor, sağındaki değer `Müdürlüğü` oluyor.
2. Model o bölgeden **yine de 5 hane üretiyor**. "Okunamıyorsa YOK yaz" talimatı bunu
   engellemedi — istenen biçimde çıktı üretme eğilimi talimattan güçlü çıktı.

DN kelimesinden gelen konum ise 2/2 doğru verdi. Yedek yol kaldırıldı. Genel ilke:
**zayıf konum sinyalini modele vermek, alanı boş bırakmaktan kötüdür.**

### 6.6 Adım 11 — yanlış birleştirilmiş belgelerin bölünmesi (2026-08-10)

`belge/bolucu.py`. Sayfa sahipliği üç aşamalı belirlenir: **etiketli TC** → bulunamazsa o
bölgeye **VLM** → o da yoksa sayfadaki **etiketsiz geçerli TC** (yalnız sayfada tam bir tane
varsa). Üçüncü aşama ölçümle eklendi: ikinci kişinin sayfası çoğu zaman etiketli bir TC alanı
taşımıyor (nüfus fotokopisi, e-devlet çıktısı). İlk iki aşamayla 6 belgenin 3'ünde ikinci kişi
hiç görünmüyordu; üçüncüsüyle 4'e çıktı.

| # | Sayfa haritası | Sonuç |
|---|---|---|
| 22 | `A?A???B??` | bölünebilir |
| 25 | `AAAAA?AAAA?AAB?` | bölünebilir |
| 32 | `A????A?AA?AAB??A??A???A` | elle (ABA) |
| 45 | `A???AA?B??` | bölünebilir |
| 53 | `AAA??AB?????BBB?B?????` | bölünebilir |
| 68 | `AA?????BA???A` | elle (ABA) |

**Otomatik bölünen: 4/6.**

**İki farklı kusur türü var ve tek kural ikisine de uymuyor:**

- *bölüm birleşmesi* — A'nın evrakı bitiyor, B'ninki başlıyor. Harita `AAABBB`, sınır belli.
  Otomatik bölünür.
- *araya giren sayfa* — B'ye ait tek sayfa A'nın evrakının ortasında. Harita `AAABAAA`.
  #32'nin 13. sayfasına bakıldı: başka bir kişiye ait, **kendi TC'si, adı ve sicil no'su olan
  tek sayfalık tam bir dilekçe**. Bu durumda bilinmeyen sayfaların kime ait olduğu belirsiz
  kalıyor — ileri yayma B'nin bölümünü olduğundan büyük gösterir. Bölünmez, işaretlenir.

Gerekçe ölçülmüş ilkenin devamı: **yanlış bölmek hiç bölmemekten kötü.** A'nın sayfalarını
B'nin adıyla arşivlemek, sessiz kaybın yerine sessiz bozulma koyar.

`uygula()` varsayılan olarak **kuru kiptedir**, dosya yazmaz. Sayfa korunumu sınandı.

**Yan bulgu:** #32'deki ikinci sicil no `Sicil No : 35197` biçiminde — ne `DN` ne `32/` deseni
yakalıyor. Çok-sicil taramasının bu belgeyi kaçırma sebebi bu; R8'in %4.5'lik tahmini bu
yüzden de bir alt sınırdır.

### 6.7 Adım 7 — uçtan uca akış (2026-08-10)

`isle.py`. Varsayılan **kuru**: plan üretimi (`Arsiv.planla`) ile uygulama (`Arsiv.uygula`)
ayrı tutuldu, arşivleme geri alması zor tek adım olduğu için.

288 belgede kuru çalıştırma: **274 arşivlenecek, 7 bölünecek, 6 elle bölünmeli, 1 isim
okunamadı.**

İzole kum havuzunda sınananlar: çakışma çözümü (`ahmet_yilmaz_2`), mükerrer atlama (aynı
içerik farklı adla gelince içerik hash'inden yakalandı), tekrar çalıştırma (ikinci koşu 0
belge), bölme (15 sayfa → 13+2, kayıp yok).

**İlk sürümdeki iki eksik, sınamada çıktı:**

1. Bölünen parçalar `ayrildi/` içinde kalıyor, arşive hiç girmiyordu — yani ikinci kişi yine
   `person_data.json`'a yazılmıyordu. Bölmenin bütün amacı buydu; yalnızca kaybolduğu klasör
   değişmiş oluyordu. Parçalar artık normal akıştan geçiriliyor.
2. Asıl dosya parçalarla aynı klasöre karışıyordu. Artık `ayrildi/asil/` altına taşınıyor:
   bölme yanlışsa geri dönülecek tek şey o.

### 6.8 Bölüm–dosya ilişkisi (ikinci külliyat)

**Soru:** Aynı bölüm numarasındaki dosyalar aynı kişiye mi ait? Öyleyse "bir dosya = bir belge"
modeli yanlış ve bir kişi sekiz ayrı isimle arşivlenir.

**Cevap: hayır.** Ölçüldü:

| | Sonuç |
|---|---|
| Karar verilebilen grupta tüm dosyalar aynı sicil | **0/110** |
| Grup içi dolu sayfalarda içerik tekrarı | %0 (345 sayfa, 345 tekil) |
| 404 okunabilir dosyada farklı sicil sayısı | 395 |

Yani her dosya ayrı kişi; arşivleme modeli doğru. Bölüm numarası kişi kimliği taşımıyor —
külliyat birden fazla tarama serisini iç içe geçirmiş (dosya tarihleri 8 ayrı gün, `3466,
3467, 3468...` gibi ardışık seriler farklı bölüm numaralarına dağılmış).

**Sonucu:** komşuluk kapısı (6.4'te ilk külliyatta 6/6 doğru karar vermişti) bu külliyatta
**kullanılamaz**: bölüm sırası ile sicil ilişkisi zayıf (17 artan / 10 azalan).

**Bulunan hata:** aynı belgenin farklı PDF baytlarıyla yeniden dışa aktarılmış kopyaları var
(aynı sayfa, aynı metin, farklı sıkıştırma). Mükerrer tespiti dosya hash'ine dayandığı için
bunların **sıfırını** yakalıyordu; 721 dosyada 1 grup, 2 fazlalık. `arsiv.metin_ozeti()`
eklendi, iki özetten biri tutarsa mükerrer sayılıyor.

### 6.9 El yazısı külliyatında isim (2026-08-11)

Ayrı altın set: 40 belge, 32'si dolu (el yazısı 18, daktilo 9, matbu 5).
`araclar/altin_set_elyazisi.py`, ölçüm `araclar/olc_elyazisi.py`.

| Yöntem | El yazısı | Daktilo | Matbu | Toplam |
|---|---|---|---|---|
| OCR | 2/18 | 0/9 | 2/5 | %12 |
| VLM, mevcut istem | 8/18 | 5/9 | 1/5 | %44 |
| VLM, el yazısına özel istem | 7/18 | 5/9 | 2/5 | %44 |
| Birleşik | 6/18 | 4/9 | 4/5 | %44 |

**İstem uyarlaması hiçbir şey kazandırmadı.** Sorun modele nasıl sorduğumuzda değil.

**Birleştirme burada ZARAR veriyor** (el yazısında 7→6), çünkü OCR gürültüden ibaret
(daktiloda 0/9). Matbuda ise en iyi sonucu veriyor (4/5) — yani birleştirme popülasyona
göre açılıp kapanmalı.

**Çok sayfalı uzlaşma (Adım 6):** belgelerin %81'inde isim etiketi birden fazla sayfada
(ortanca 3). Sayfaları ayrı okuyup oylamak:

| Eşik | İsabet | Kapsama |
|---|---|---|
| ilk sayfa (eski davranış) | %44 | %100 |
| çoğunluk | %50 | %100 |
| **≥2 sayfa uzlaşıyor** | **%82** | %34 |
| tüm sayfalar aynı | %100 | %9 |

El yazısına ayrılınca **≥2 uzlaşma %88 isabet** veriyor (7 doğru, 1 yanlış).

Mekanizma: model tek sayfada uydurduğunda aynı uydurmayı başka sayfada tekrarlamıyor,
çünkü her sayfada yazı farklı görünüyor. Doğru okuduğunda sayfalar birbirini tutuyor. Bu,
modelin vermediği güven sinyalini üretiyor.

**Örneklem küçük:** el yazısında kapıdan geçen 8 belge var. Yön güçlü, rakam kırılgan.

### 6.10 Sicil: geometrik şerit (2026-08-11)

`DN` metin katmanında bulunamadığında koordinat üretilemiyordu ve VLM hiç çağrılmıyordu.
Konum ölçüldü: **32/32 belgede 1. sayfa**, üst kenardan %3.2–13.3, %94'ü sol üst çeyrekte.
Pay bırakılarak üst **%22'lik şerit** kırpılıyor (`sayi_okuyucu.serit_oku`).

| | İkinci külliyat, 40 belge |
|---|---|
| OCR ve VLM uyuşuyor | 16 |
| OCR ve VLM **çelişiyor** | **0** |
| OCR bulamadı, VLM okudu | 17 |
| Kapsama | %40 → **%82** |

İlk külliyatta da sınandı: OCR'ın son rakamı düşürdüğü 5 çekişmeli belgede **5/5 doğru**
(`4647`→`46471`, `4670`→`46701`).

**Neden tam sayfa değil:** tam sayfa denendi, %70 isabet ve 3 uydurma verdi (6.5'teki
başarısız yedek yol gibi). Şerit dar olduğu için harf başına düşen çözünürlük yüksek kalıyor.
Bedeli hız: şerit 20.3 sn/çağrı, satır kırpması 5–7.5 sn.

**Hane kuralı kaldırıldı.** Sabit "5 hane" süzgeci ilk külliyat için doğruydu, ikincisinin
tüm sicillerini eliyordu. Sınıflandırıcı denendi (%91, hataları kötü yönde) ve vazgeçildi;
yerine doğrudan gözlem kullanılıyor — hane sayısını görüntüden okumak. Kurallar:

- adaylar 4–5 hane kabul edilir
- önek elemesi **iki kaynağın birleşimi** üzerinde yapılır (`4648` ile `46488` aynı metinde
  geçiyorsa kısası kesik okumadır)
- **çapraz doğrulama 4 hanede yetmez**: OCR her iki kaynakta da son rakamı düşürüp iki kesik
  okuma birbirini "doğrulayabiliyor" (#23, #72). 4 hane görüntüden onaylanmadan kabul edilmez.

İlk külliyat sonucu: sicil kapsaması %90.0 → **%96.2**, isabet %98.6 (değişmedi).

### 6.11 Adım 6 — çok sayfalı uzlaşma boru hattında (2026-08-11)

`isim_okuyucu.coklu_sayfa_oku` + `isle.py`. İsim etiketi taşıyan her sayfa ayrı okunur
(etiket çıpalı kırpmayla), okumalar oylanır. En az 2 sayfa aynı değeri veriyorsa o değer
alınır; uzlaşma yoksa **eski yola düşülür** (tek sayfa + OCR birleştirme), böylece 1.
külliyatta gerileme riski yok.

| | 1. külliyat (80 belge) | 2. külliyat, el yazısı (18 belge) |
|---|---|---|
| Uzlaşma sağlandı | 64 (%80) | 8 (%44) |
| Uzlaşan okumaların isabeti | **64/64 (%100)** | **7/8 (%88)** |

**Uzlaşma bir güven sinyalidir.** 1. külliyatta iki sayfa aynı ismi verdiğinde okuma her
seferinde doğru çıktı. Sistem artık hangi belgeye güvenebileceğini biliyor — daha önce
80 okuma vardı ve hangisinin doğru olduğu bilinmiyordu.

Uzlaşan değerin **üstüne** OCR birleştirmesi uygulanır: 1. külliyatta %95'i getiren şey
işaret ve boşlukları OCR'dan kurtarmaktı (6.3), uzlaşma onu silmemeli.

**Hız için satılmayan şey.** Denenen kısayollar ve bedelleri (aynı önbellek, 80 belge):

| Ayar | İsabet | Çağrı/belge |
|---|---|---|
| tam tarama, en çok 3 sayfa | %98 | 2.6 |
| tam tarama, en çok 4 sayfa | %98 | 3.1 |
| **tam tarama, en çok 6 sayfa** | **%100** | 3.6 |
| "iki sayfa uzlaşınca dur" | %98 | ~2 |

Erken durma cazipti ama isabeti düşürüyor: sayfalar `[A,B,B,A,A]` sırayla gelirse ilk
uzlaşan çift `B` oluyor, oysa çoğunluk `A`. Güvenilir kümenin %100 isabetli olması bu
tasarımın bütün değeri; %30 hız için satılmadı.

**Maliyet:** belge başına 3.6 model çağrısı, çağrı başına ~6.7 sn → belge başına ~36 sn.
2. külliyatın tam koşusu (721 belge) yaklaşık **5 saat**, artı sicil şeridi gereken
belgelerde 20'şer saniye.

### 6.12 Katı kip ve `dogrulanmali/` (2026-08-12)

`isle.py --kati`. Sayfalar arası uzlaşma sağlanamamış okumalar arşive girmez;
`dogrulanmali/` kuyruğuna alınır ve `person_data.json`'a yazılmaz.

Gerekçe ölçüm: uzlaşan okumalar 1. külliyatta %100, el yazısında %88 isabetli
(6.11). Uzlaşmayanlar el yazısında %44 ve hangisinin doğru olduğu bilinemiyor.
Sessiz yanlış boş alandan pahalı olduğu için (6.4) bu okumalar arşive
konmamalı.

**Dosya adı yine model önerisiyle kurulur.** İnsan sıfırdan okumak yerine
öneriyi doğrular — yanlışsa düzeltir, doğruysa onaylar. `okunamadi/`dan farkı
bu: orada isim hiç yok, burada var ama doğrulanmamış.

Varsayılan **kapalı**dır: 1. külliyatta uzlaşmayan 16 belgenin 12'si eski
yoldan doğru okunuyor, katı kip onları da kuyruğa atardı. Hangi külliyatta
açılacağı kullanıcı kararı.

### 6.13 İnsan-döngüde doğrulama: ilk gerçek tur (2026-08-12)

250 belgelik katı kip koşusu (rastgele örneklem, `--karisik`) 146 dakika sürdü:

| | Belge |
|---|---|
| `arsiv/` (uzlaşmış, otomatik) | 64 (%26) |
| `dogrulanmali/` (kuyruğa) | 175 |
| `okunamadi/` | 8 |

Kuyruk `araclar/dogrula.py` ile insana doğrulatıldı. **İki tur gerekti** ve
aradaki fark kırpma hatalarını ortaya çıkardı:

| Tur | Onaylanan | Okunamıyor |
|---|---|---|
| 1 | 142 | 33 |
| 2 (kırpma düzeltmelerinden sonra) | **163** | 12 |

Yani 21 belge kırpma hatası yüzünden "okunamıyor" sanılmıştı. Kullanıcının
"okunmuyor dediklerimin çoğu kırpma hatasıydı" geri bildirimi iki ayrı hatayı
buldurdu: düz metin eşleşmesi ve imza bloğu (bkz. `alan_cikarici`).

**Sonuç:** 515 belge arşivde, `person_data.json` 515 kayıt. Sicil %90 dolu,
TC %57 (ikinci külliyatta form alanı yok, bkz. 2.3).

**Ölçülen insan maliyeti:** 250 belgenin 175'i kuyruğa düştü, yani otomatik
geçiş oranı %26. Hedefe (%90 doğruluk) bu yoldan varılıyor: arşive giren her
kayıt ya uzlaşmış ya insan onaylı.

### 6.2 Külliyat geneli kapsama (288 belge)

OCR-only (modele hiç gitmeden), `araclar/olc_alan_cikarimi.py`:

| Alan | İlk | Şimdi |
|---|---|---|
| `isim` | 269 (%93.4) | **287 (%99.7)** |
| `tc_no` | 207 (%71.9) | **219 (%76.0)** |
| `sicil_no` | 243 (%84.4) | **250 (%86.8)** |
| üçü birden | 172 (%59.7) | **195 (%67.7)** |

VLM devredeyken bu rakamlar yükseliyor; altın sette ölçülen hâli bölüm 6.5'te. Külliyat
genelinde VLM'li kapsama henüz ölçülmedi (288 belgede model koşusu gerektirir).

**Örneklem notu:** Katmanlar gerçek dağılıma yakın (külliyatta temiz %42, hafif %11, ağır
%40, bulunamayan %7; örneklemde %33/%17/%40/%10). Temiz vakalar hafif eksik temsil edildiği
için gerçek ortalama bu rakamın bir miktar üzerinde beklenir.

**Altın setin kendisinde bulunan hata:** 17 numaralı belgede doğru değer `MURAK` girilmişti,
görüntüde `MURAT` yazıyor. Düzeltildi. Ölçüm aracının bulguları her zaman kaynağa karşı
doğrulanmalı — altın set de hatasız değil.

- Çoklu okuma (aynı sayfayı 2–3 kez okuyup oylama) şimdilik yok; taban ölçüldü, gerekirse
  eklenecek.

---

## 7. Çalışma düzeni

| Konu | Karar |
|---|---|
| Arayüz | Önce CLI, arayüz sonradan |
| Kod yapısı | Ayrı ayrı küçük modüller |
| Zaman baskısı | Yok — doğruluk öncelikli |
| Süre kısıtı | Belge başına süre önemsiz |
| Commit | Her çalışan adım sonunda |
| `.gitignore` | `ornekler/`, `arsiv/`, `okunamadi/`, `person_data.json`, model ağırlıkları |
| Ortam | Python 3.12 sanal ortamı (`.venv`), PyMuPDF |

**Kişisel veri git geçmişine asla girmeyecek.**

Bu kural bir kez daha çiğnendi (2026-08-12): doğrulama çıktısı `dogrulama.csv`
(142 kişi adı) `git add -A` ile körlemesine eklenip iki commit'te geçmişe girdi.
Sızıntı makineden çıkmamıştı (hiçbir commit gönderilmemişti); geçmiş yeniden
yazılıp temizlendi. **Ders: `git add -A` yeni türde bir çıktı dosyası
üretildiğinde tehlikeli.** Yeni bir çıktı biçimi eklenirken `.gitignore` aynı
commit'te güncellenmeli.

Şu an izlenen tek dosya türleri: `.py`, `.md`, `.txt`, `.gitignore`.

---

## 8. Yol haritası

Bulgular yol haritasını değiştirdi: OCR yolu artık **ana yol**, VLM ise isim boşluklandırma ve
boşluk doldurma katmanı.

| # | Adım | Durum |
|---|---|---|
| 1 | PDF okuma modülü (metin katmanı tespiti + 300 DPI görüntü) | ✅ `belge/pdf_okuyucu.py` |
| 1b | Örnek belgelerin incelenmesi | ✅ bölüm 2 |
| 2 | OCR metninden alan çıkarma | ✅ `belge/alan_cikarici.py` |
| 3 | Doğrulama (TC checksum, sicil çapraz, TC sahipliği) | ✅ aynı modülde |
| 3b | TC/sicil doğruluk ölçümü | ✅ bölüm 6.4, R6 kapandı |
| 4 | MLX kurulumu + model + bölge kırpma | ✅ `belge/isim_okuyucu.py` |
| 5 | VLM ile isim okuma + OCR birleştirme | ✅ %95.0 |
| 8 | Altın set + doğruluk ölçümü | ✅ 80 belge, `araclar/olc_dogruluk.py` |
| 9 | Ölçüme dayalı iyileştirme | ✅ iki tur |
| 10 | VLM ile TC/sicil okuma (kapsama artırma) | ✅ bölüm 6.5, TC %98.7 |
| 11 | Yanlış birleştirilmiş belgeleri bölme (R8) | ✅ bölüm 6.6, 4/6 otomatik |
| 7 | Uçtan uca CLI (adlandırma, arşivleme, JSON) | ✅ `isle.py`, bölüm 6.7 |
| 12 | El yazısı altın seti + taban ölçümü | ✅ bölüm 6.9 |
| 13 | Sicil geometrik şerit + hane kuralının kaldırılması | ✅ bölüm 6.10 |
| 6 | Çok sayfalı isim uzlaşması | ✅ bölüm 6.11, `isle.py`'ye bağlandı |
| 14 | Etiket çıpalı isim kırpması | ✅ aynı yolda |

### Adım 7 — uçlar yazıldı

Adım 7 kapandı (`isle.py`, bölüm 6.7): adlandırma, çakışma, `person_data.json`, arşivleme,
mükerrer atlama ve kuru/`--uygula` ayrımı çalışıyor. 515 belge arşivde (bölüm 6.13).

### Adım 7 sonrası — 13 Ağustos 2026

Boş sayfa eleme yazıldı (`pdf_okuyucu.bos_sayfa_mi`): az metin **ve** neredeyse beyaz
görüntü. Nüfus fotokopisi (az metin, koyu fotoğraf) elenmez. Sayfa PDF'den silinmez;
`coklu_sayfa_oku` atlar, `bolucu` haritada `?` koyar.

Yedek isim kırpması etiket + `satir_kutusu` çıpalı; OCR değer kutusu VLM'e gitmez.
`olc_kirpma.py` bu turda koşuldu: ham 8/18 (el yazısı) / 14/32 (tümü). `etiketsiz`
6/18, `murekkep` 6/18, `dar_bant` 5/18 — ham'den +2/18 kazanç yok, `satir_kutusu`
payı değişmedi.

Kalan açıklar:

- R8 alt sınır: 13/288 çoklu-TC; ikinci kişisi okunamayan birleştirmeler görünmez
  kalabilir. Sicil adayı tespiti genişledi (`Sicil No :`), çıkarıcının `sicil_no`
  kuralına bağlanmadı.
- sicil #11: DN yok, çapraz kontrol yok; tek sessiz yanlış duruyor.
- El yazısı kapsama %44 (uzlaşma kapısı); otomatik %90–95 bu model/donanımda iddia
  edilmiyor.
- git: kişisel veri geçmişe girdi, yerelde temizlendi; `origin`'e henüz push yok.
  İlk gönderiden önce geçmiş kontrol edilmeli.

---

## 9. Riskler — durum

### R1 — İsim doğrulaması ❗ AÇIK (tek gerçek risk)

**Çözüm:** Sözlük yerine **çok sayfalı çapraz doğrulama** — isim birden fazla sayfada
geçiyorsa bağımsız okunup karşılaştırılır.

**Sözlük neden kullanılmıyor (kullanıcı gerekçesi):** Sözlükte olmayan çok sayıda gerçek isim
var; sözlüğü otorite yapmak onları kaybettirir. Ayrıca `İmir` gerçek bir isimse otomatik
`Emir`e çevrilmesi adı fark edilmeden bozar.

**Yeni boyut:** OCR boşlukları kaybettiği için isim, alanlar içinde **tek başına VLM'e
bağımlı olan** alandır. Diğer ikisi desenle çözülebiliyor.

### R2 — Dijital PDF metin katmanı ✅ ÇÖZÜLDÜ

Metin katmanı 288/288 belgede var ve artık **ana yol** olarak kullanılıyor.

### R3 — Güven skoru ✅ KAPANDI (kabul edildi)

### R4 — Yerel model ✅ KAPANDI (değiştirilemez kısıt)

Bulut VLM seçeneği kalıcı olarak kapalıdır. Ayrıca bulgular sayesinde bu risk küçüldü:
alanlar el yazısı değil matbu olduğu için yerel modelden beklenen iş çok daha kolay.

### R5 — Şablon envanteri ✅ KAPANDI

Külliyat tek tip: Isparta sicil dosyaları. Her dosyada birkaç standart evrak türü var
(sicil tasdiknamesi, kurum yazısı, e-devlet çıktısı, nüfus cüzdanı fotokopisi).

### R6 — TC belirsizliği ✅ KAPANDI (ölçüldü)

Çoklu-TC belgelerinde çıkarıcı 5 değer üretti, **5'i de DN sahibinin**; yanlış kişi seçimi
sıfır. Çözemediği 8 belgede değer üretmeyi reddetti. İstenen hata biçimi tam olarak bu:
sahiplik belirsizken uydurmuyor, çekiliyor.

Risk kapandı ama sebebi değişti: belgelerde ikinci TC'nin **neden** bulunduğu yanlış
biliniyordu. Bkz. R8.

### R8 — Yanlış birleştirilmiş dosyalar ❗ AÇIK (yeni, gerçek risk)

**Bazı PDF'ler iki ayrı kişinin evrakını taşıyor.** Bu bir tarama/bölme kusuru; çıkarıcı
hatası değil ve çıkarıcı düzeltemez.

Altın setteki 6 çoklu-TC belgesi gözle incelendi, **altısı da yanlış birleştirilmiş**
(`altin_set.csv`, `YANLIS_BIRLESTIRME` sütunu). Külliyat genelinde çoklu-TC taşıyan
**13/288 belge (%4.5)** var.

**Bağımsız doğrulama — sayfa sayısı:** çoklu-TC belgelerinin ortancası **17 sayfa**,
diğerlerinin **8**. İki dosyanın birleşmesinde beklenen tam da bu.

**13 bir alt sınırdır.** Tespit ikinci kişinin TC'sinin OCR'da okunabilmesine dayanıyor;
TC kapsaması %76.6 olduğuna göre ikinci kişisi okunamayan birleştirmeler görünmez kalır.
Sicil no ise ayırt edici değil: 6 belgenin yalnızca 1'inde ikinci bir sicil no okunabiliyor
(ikinci kişinin evrakı çoğunlukla sicil tasdiknamesi değil, e-devlet çıktısı/nüfus fotokopisi).

**Neden ciddi:** Adım 7 belgeyi tek bir isimle arşivleyecek. Dosya iki kişininse ikinci kişi
**sessizce kaybolur** — `person_data.json`'a hiç girmez, `okunamadi/`'ya da düşmez, hiçbir
yerde iz bırakmaz. Sessiz kayıp, bu projedeki en kötü hata biçimi.

**Karar (kullanıcı): belge sayfalara ayrılıp her kişi ayrı PDF olarak yazılacak** — sadece
işaretlenip elle bırakılmayacak. Adım 10'dan sonraya bırakıldı ve **Adım 11'de yapıldı:
4/6 otomatik bölünüyor (bölüm 6.6), kalan 2 belge `bolunmeli/`ye işaretleniyor.**

Aşağıdaki ilk fizibilite ölçümü Adım 10 öncesine aittir, karşılaştırma için bırakılmıştır.

**Bölme fizibilitesi (ölçüldü, 6 işaretli belge):** Her sayfada `T.C. Kimlik No` etiketinin
değeri okunur, bulunamayan sayfalar bir öncekinden devralır. Sonuç:

| Belge | Sayfa haritası | Durum |
|---|---|---|
| #25 | `AAAAAAAAAAAAABB` | temiz iki bölüm |
| #53 | `AAAAAABBBBBBBBBBBBBBBB` | temiz iki bölüm |
| #22 | `??AAAABBB` | baştaki belirsizlik DN'den çözülür |
| #32 | `?????AAAAAAABBBAAAAAAAA` | B ortada sıkışmış, 4 blok |
| #45 | `??????????` | 10 sayfanın hiçbirinde okunabilir TC yok |
| #68 | `?????????????` | 13 sayfanın hiçbirinde yok |

Yarısında çalışıyor. Darboğaz sayfa başına kimlik okuma kapsaması: etiketli TC sayfa başına
0–6 kez okunabiliyor, OCR kimlik bloklarının çoğunu düşürüyor.

**Neden Adım 10'dan sonra:** bölmeyi mümkün kılan şey tam olarak Adım 10'un iyileştireceği
kapsama. Şimdi yazmak %50 başarıyı kalıcılaştırır. Ayrıca **yanlış bölmek hiç bölmemekten
kötüdür**: #32 gibi bir belge bölünürse A'nın sayfaları B'nin adıyla arşivlenir — sessiz
kayıp yerine sessiz bozulma geçer.

---

## 10. Doğruluk hedefi tutmazsa — kaldıraçlar

Bulut ve sözlük kapalı olduğundan, sırasıyla:

1. **Prompt iyileştirme** — İngilizce/Türkçe karşılaştırması, alan konumu ipuçları
2. **Bölgesel kırpma** — isim satırının koordinatı OCR'dan biliniyor; o bölge kırpılıp
   büyütülerek VLM'e verilebilir. Ucuz ve çok etkili olması beklenen ilk hamle.
3. **Çoklu okuma + oylama** — süre önemsiz, maliyet yok
4. **Daha büyük model** — 16 GB sınırında 4-bit
5. **OCR metnini modele ipucu verme** — boşluksuz isim modele gösterilip yalnızca
   boşlukları koyması istenir (görevi daraltır, hata payını düşürür)
