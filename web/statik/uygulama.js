"use strict";

const S = {
  gorunum: "yukle",
  belgeler: [],
  is: null,
  vlm: {},
  ozet: {},
  secili: null,
  detay: null,
  aktifKisi: "A",
  sayfaSecim: new Set(),
  birlestirSira: [],
  isaret: new Set(),
  poll: null,
  sayfaNo: 1,
  taslak: {},
  kisayolAcik: false,
  _masaKorun: false,
  _masaKilit: false,
};

const KISI_AD = { A: "Kişi A", B: "Kişi B", C: "Kişi C", X: "Bu belgeye ait değil" };

const KISAYOL_SATIR = [
  ["j / →", "sonraki sayfa"],
  ["k / ←", "önceki sayfa"],
  ["↑ / ↓", "görüntüyü kaydır"],
  ["n", "sonraki belge"],
  ["p", "önceki belge"],
  ["1 2 3", "sayfayı kişi A / B / C"],
  ["0 / x", "ait değil"],
  ["Enter", "onayla (böl veya kaydet)"],
  ["s", "atla — sonraya bırak"],
  ["e / /", "isim alanına odak"],
  ["Tab", "TC → sicil"],
  ["?", "bu liste"],
  ["Esc", "alanı / paneli kapat, masaya dön"],
];

async function api(yol, secenek = {}) {
  const r = await fetch(yol, {
    headers: secenek.govde && !(secenek.govde instanceof FormData)
      ? { "Content-Type": "application/json" } : {},
    method: secenek.method || "GET",
    body: secenek.govde instanceof FormData
      ? secenek.govde
      : secenek.govde ? JSON.stringify(secenek.govde) : undefined,
  });
  if (!r.ok) {
    let msg = r.statusText;
    try { const j = await r.json(); msg = j.detail || JSON.stringify(j); } catch (_) {
      try { msg = await r.text(); } catch (__) {}
    }
    throw new Error(typeof msg === "string" ? msg : JSON.stringify(msg));
  }
  const t = r.headers.get("content-type") || "";
  if (t.includes("application/json")) return r.json();
  return r;
}

function toast(mesaj) {
  const el = document.getElementById("toast");
  el.textContent = mesaj;
  el.hidden = false;
  clearTimeout(toast._t);
  toast._t = setTimeout(() => { el.hidden = true; }, 4200);
}

function kapatModal() {
  const m = document.getElementById("modal");
  if (!m) return;
  m.hidden = true;
  m.innerHTML = "";
  m.onclick = null;
  m.setAttribute("aria-hidden", "true");
  try { m.inert = true; } catch (_) {}
}

function acModal(html, tiklaKapat = true) {
  const m = document.getElementById("modal");
  m.innerHTML = html;
  m.hidden = false;
  m.setAttribute("aria-hidden", "false");
  try { m.inert = false; } catch (_) {}
  m.onclick = tiklaKapat
    ? (ev => { if (ev.target === m) kapatModal(); })
    : null;
}

function etaMetin(sn) {
  if (sn == null || sn <= 0) return "";
  if (sn < 60) return `~${Math.round(sn)} sn`;
  const dk = Math.round(sn / 60);
  if (dk < 60) return `~${dk} dk`;
  return `~${Math.floor(dk / 60)} sa ${dk % 60} dk`;
}

function kisaTc(tc) {
  if (!tc) return "";
  return tc.length === 11 ? `${tc.slice(0, 3)}…${tc.slice(-2)}` : tc;
}

function belgeler() { return S.belgeler || []; }
function belge(id) { return belgeler().find(b => b.id === id); }

function inceleKuyruk() {
  return belgeler().filter(b => b.kova === "incele");
}

function girdiOdakta() {
  const el = document.activeElement;
  if (!el) return false;
  const tag = el.tagName;
  if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return true;
  return !!el.isContentEditable;
}

function modalAcik() {
  const m = document.getElementById("modal");
  return m && !m.hidden;
}

function gorunume(ad) {
  if (ad === "incele" && !S.secili) {
    const k = inceleKuyruk();
    if (k.length) { acIncele(k[0].id); return; }
  }
  S.gorunum = ad;
  document.querySelectorAll(".sekme button").forEach(b => {
    b.classList.toggle("aktif", b.dataset.gorunum === ad);
  });
  const ince = document.getElementById("sekme-incele");
  const bir = document.getElementById("sekme-birlestir");
  const inceleSay = inceleKuyruk().length;
  ince.hidden = ad !== "incele" && inceleSay === 0 && !S.secili;
  bir.hidden = ad !== "birlestir" && S.birlestirSira.length === 0;
  if (ad === "incele") ince.hidden = false;
  if (ad === "birlestir") bir.hidden = false;
  document.body.classList.toggle("masa-modu", ad === "incele" && !!S.detay);
  ciz();
}

function durumImza(d) {
  return JSON.stringify({
    vlm: d.vlm,
    ozet: d.ozet,
    belgeler: (d.belgeler || []).map(b => [
      b.id, b.durum, b.kova, b.neden, b.nesil, b.isim, b.tc_no, b.sicil_no, b.uzlasma, b.hata,
    ]),
  });
}

async function yenile() {
  const d = await api("/api/durum");
  const imza = durumImza(d);
  const listeDegisti = imza !== S._imza;
  S._imza = imza;
  S.belgeler = d.belgeler;
  S.is = d.is;
  S.vlm = d.vlm;
  S.ozet = d.ozet;
  if (S.secili) {
    const varMi = S.belgeler.some(b => b.id === S.secili);
    if (!varMi) { S.secili = null; S.detay = null; }
  }
  cizUst();
  if (listeDegisti) ciz();
  const calisiyor = d.is && (d.is.durum === "isleniyor" || d.is.durum === "yukleniyor");
  if (calisiyor && !S.poll) {
    S.poll = setInterval(yenile, 900);
  } else if (!calisiyor && S.poll) {
    clearInterval(S.poll);
    S.poll = null;
    ciz();
  }
}

function cizUst() {
  const rozet = document.getElementById("vlm-rozet");
  if (!S.vlm.uygun) {
    rozet.textContent = "OCR";
    rozet.className = "rozet yok";
    rozet.title = S.vlm.uyari || "VLM yok";
  } else if (S.vlm.acik) {
    rozet.textContent = "VLM açık";
    rozet.className = "rozet acik";
  } else {
    rozet.textContent = "VLM hazır";
    rozet.className = "rozet";
  }
  const el = document.getElementById("ilerleme");
  const is_ = S.is;
  if (!is_ || is_.durum === "bos" || (is_.durum === "bitti" && !is_.su_an && is_.biten === is_.toplam && is_.toplam === 0)) {
    el.hidden = true;
  } else if (is_.durum === "bitti" && is_.toplam > 0 && is_.biten >= is_.toplam) {
    el.hidden = false;
    el.innerHTML = `<div class="ilerleme-kutu"><div class="ilerleme-ust"><span>İşlem bitti — ${is_.biten} belge</span></div>
      <div class="cubuk"><i style="width:100%"></i></div></div>`;
  } else {
    el.hidden = false;
    const yuz = is_.yuzde || 0;
    const eta = etaMetin(is_.eta_sn);
    const bas = is_.durum === "yukleniyor" ? "Model yükleniyor…" : (is_.su_an || "İşleniyor");
    el.innerHTML = `<div class="ilerleme-kutu">
      <div class="ilerleme-ust"><span>${bas}</span>
        <span>${is_.biten}/${is_.toplam}${eta ? " · " + eta : ""}</span></div>
      <div class="cubuk"><i style="width:${yuz}%"></i></div></div>`;
  }
  const n = (S.ozet.incele || 0) + (S.ozet.arsivlenecek || 0) + (S.ozet.okunamadi || 0) + (S.ozet.hata || 0);
  const oz = document.getElementById("ozet-rozet");
  oz.hidden = n === 0;
  oz.textContent = n;
  const inceSay = inceleKuyruk().length;
  const ir = document.getElementById("incele-rozet");
  if (ir) {
    ir.hidden = inceSay === 0;
    ir.textContent = inceSay;
  }
  const ince = document.getElementById("sekme-incele");
  if (ince && S.gorunum !== "incele") ince.hidden = inceSay === 0 && !S.secili;
}

function ciz() {
  const masaVar = !!document.getElementById("masa");
  document.body.classList.toggle("masa-modu", S.gorunum === "incele" && !!S.detay);
  if (S.gorunum === "incele" && S._masaKorun && masaVar && S.detay) {
    masaTaslakTopla();
    masaUstGuncelle();
    masaOnayDurum();
    return;
  }
  const kok = document.getElementById("kok");
  if (S.gorunum === "yukle") kok.innerHTML = yukleHtml();
  else if (S.gorunum === "sonuclar") kok.innerHTML = sonuclarHtml();
  else if (S.gorunum === "incele") kok.innerHTML = inceleHtml();
  else if (S.gorunum === "birlestir") kok.innerHTML = birlestirHtml();
  bagla();
  if (S.gorunum === "incele" && S.detay) {
    S._masaKorun = true;
    const masa = document.getElementById("masa");
    if (masa && !girdiOdakta()) masa.focus({ preventScroll: true });
  } else {
    S._masaKorun = false;
  }
}

function yukleHtml() {
  const hepsi = belgeler();
  const vlmKapali = S.vlm && S.vlm.uygun === false;
  return `
    <div class="birak" id="birak" tabindex="0" role="button" aria-label="PDF seç veya bırak">
      <h2>PDF bırakın veya tıklayın</h2>
      <p>Birden fazla dosya olabilir. Kişisel veri bu makineden çıkmaz.</p>
      <input class="gizli" id="dosya" type="file" accept="application/pdf" multiple>
    </div>
    ${vlmKapali ? `<div class="uyari-satir">${S.vlm.uyari || "VLM yok; OCR ile devam."}</div>` : ""}
    <div class="arac-cubugu">
      <label><input type="checkbox" id="vlm-kutu" ${vlmKapali ? "" : "checked"} ${vlmKapali ? "disabled" : ""}>
        VLM kullan <span class="kucuk">(önerilir, belge başına onlarca saniye)</span></label>
      <button class="birincil" id="isle-btn" ${hepsi.length ? "" : "disabled"}>İşle</button>
      <span class="kucuk">${hepsi.length} belge yüklü · belirsizler incelemeye düşer, sessiz arşiv yok</span>
    </div>
    <div class="dosya-listesi">
      ${hepsi.map(b => `
        <div class="dosya-satir">
          <span class="ad">${esc(b.ad)}</span>
          <span class="meta">${b.sayfa_sayisi} sayfa</span>
          <span><i class="durum-nokta ${b.durum}"></i> ${durumEtiket(b)}</span>
        </div>`).join("") || ""}
    </div>`;
}

function durumEtiket(b) {
  if (b.durum === "kuyrukta") return "kuyrukta";
  if (b.durum === "isleniyor") return "işleniyor";
  if (b.durum === "hata") return "hata";
  if (b.kova === "arsivlenecek") return "arşivlenecek";
  if (b.kova === "incele") return b.neden === "cok_kimlik" ? "çok kişili" : "doğrulanmalı";
  if (b.kova === "okunamadi") return "okunamadı";
  if (b.kova === "hata") return "hata";
  if (b.kova === "ayrildi") return "ayrıldı";
  if (b.kova === "arsiv") return "arşivlendi";
  return b.durum;
}

function sonuclarHtml() {
  const grup = {
    incele: belgeler().filter(b => b.kova === "incele"),
    arsivlenecek: belgeler().filter(b => b.kova === "arsivlenecek"),
    okunamadi: belgeler().filter(b => b.kova === "okunamadi"),
    hata: belgeler().filter(b => b.kova === "hata" || b.durum === "hata"),
  };
  const isaretli = [...S.isaret].filter(id => belge(id));
  return `
    <div class="secim-cubugu">
      <button class="birincil" id="incele-basla" ${grup.incele.length ? "" : "disabled"}>
        İncelemeye başla (${grup.incele.length})</button>
      <button class="birincil" id="arsivle-btn" ${grup.arsivlenecek.length ? "" : "disabled"}>
        Arşivlenecekleri onayla (${grup.arsivlenecek.length})</button>
      <button class="ikincil" id="birlestir-ac" ${isaretli.length >= 2 ? "" : "disabled"}>
        Seçilenleri birleştir (${isaretli.length})</button>
      <span class="kucuk">i veya Enter — inceleme masası · kartı tıklayınca o belgeden başlar</span>
    </div>
    <div class="kolonlar">
      ${kolonHtml("incele", "İncelenmeli", grup.incele)}
      ${kolonHtml("arsiv", "Arşivlenecek", grup.arsivlenecek)}
      ${kolonHtml("okunamadi", "Okunamadı", grup.okunamadi)}
      ${kolonHtml("hata", "Hata", grup.hata)}
    </div>`;
}

function kolonHtml(sinif, baslik, liste) {
  return `<section class="kolon ${sinif}">
    <h3>${baslik}<span>${liste.length}</span></h3>
    ${liste.map(kartHtml).join("") || `<div class="bos-kolon">boş</div>`}
  </section>`;
}

function kartHtml(b) {
  const isaret = S.isaret.has(b.id) ? "secili" : "";
  return `<article class="kart ${isaret}" data-id="${b.id}">
    <div class="kart-ust">
      <label class="kucuk" onclick="event.stopPropagation()">
        <input type="checkbox" data-isaret="${b.id}" ${S.isaret.has(b.id) ? "checked" : ""}> seç
      </label>
      <span class="rozet kart-ici">${durumEtiket(b)}</span>
    </div>
    <div class="ad">${esc(b.ad)}</div>
    <div class="alan alan-satir">
      ${b.isim ? `<b>${esc(b.isim)}</b><br>` : ""}
      ${b.tc_no ? `TC ${esc(b.tc_no)}` : "TC —"}
      ${b.sicil_no ? ` · sicil ${esc(b.sicil_no)}` : ""}
      ${b.uzlasma >= 2 ? ` · ${b.uzlasma} sayfa uzlaştı` : b.isim ? " · uzlaşma yok" : ""}
    </div>
    ${b.gerekce ? `<div class="alan">${esc(b.gerekce)}</div>` : ""}
    ${b.hata ? `<div class="alan">${esc(b.hata)}</div>` : ""}
  </article>`;
}

function taslakAl(id) {
  if (!S.taslak[id]) {
    S.taslak[id] = { isim: "", tc_no: "", sicil_no: "", atama: [], sayfa: 1 };
  }
  return S.taslak[id];
}

function taslakHazirla(b) {
  const n = b.sayfa_sayisi;
  const sunucu = (b.atama && b.atama.length === n) ? [...b.atama] : Array(n).fill("?");
  const eski = S.taslak[b.id];
  if (eski && Array.isArray(eski.atama) && eski.atama.length === n) {
    eski.sayfa = Math.min(Math.max(eski.sayfa || 1, 1), n);
    return eski;
  }
  S.taslak[b.id] = {
    isim: b.isim || "",
    tc_no: b.tc_no || "",
    sicil_no: b.sicil_no || "",
    atama: sunucu,
    sayfa: 1,
  };
  return S.taslak[b.id];
}

function masaTaslakTopla() {
  if (!S.detay) return;
  const t = taslakAl(S.detay.id);
  const isim = document.getElementById("isim-girdi");
  const tc = document.getElementById("tc-girdi");
  const sicil = document.getElementById("sicil-girdi");
  if (isim) t.isim = isim.value;
  if (tc) t.tc_no = tc.value;
  if (sicil) t.sicil_no = sicil.value;
  t.sayfa = S.sayfaNo;
  if (S.detay.atama) S.detay.atama = t.atama;
}

function sayfaUrl(b, no, dpi) {
  return `/api/belge/${b.id}/sayfa/${no}?dpi=${dpi}&n=${b.nesil || 1}`;
}

function inceleHtml() {
  if (!S.secili) {
    const k = inceleKuyruk();
    if (k.length) return `<p class="bos">Kuyruk yükleniyor…</p>`;
    return `<p class="bos">İncelenecek belge yok. Sonuçlardan «İncelemeye başla» deyin.</p>`;
  }
  const b = S.detay || belge(S.secili);
  if (!b) return `<p class="bos">Belge bulunamadı.</p>`;
  const t = taslakHazirla(b);
  S.sayfaNo = t.sayfa || 1;
  if (S.detay) S.detay.atama = t.atama;
  const n = b.sayfa_sayisi;
  const kuyruk = inceleKuyruk();
  const sira = kuyruk.findIndex(x => x.id === b.id) + 1;
  const atama = t.atama;
  const sayim = { A: 0, B: 0, C: 0, X: 0, "?": 0 };
  atama.forEach(h => { sayim[h] = (sayim[h] || 0) + 1; });
  const plan = (S.detay && S.detay.plan) || b.plan;
  const gerekce = b.gerekce || (plan && plan.gerekce) || "";
  const ikinciYok = /ikinci kişi bulunamadı/i.test(gerekce);
  const cok = !!(b.cok_kimlik || b.neden === "cok_kimlik");
  let banner = `<div class="banner sari">Öneri sarı kutuda. Görüntüyle karşılaştırın; boş isim + Enter = okunamadı.</div>`;
    if (cok) {
    banner = `<div class="banner bilgi">Sayfayı 1/2/3/0 ile işaretleyin. Onaylamadan bölünmez.</div>`;
    if (!plan) {
      banner = `<div class="banner uyari">${esc(gerekce)}</div>`;
    } else if (ikinciYok) {
      banner = `<div class="banner uyari">İkinci kişi otomatik bulunamadı. Sayfaları kontrol edin.</div>`;
    } else if (plan && !plan.bolunebilir) {
      banner = `<div class="banner uyari">${esc(gerekce)}</div>`;
    } else if (plan && plan.bolunebilir) {
      banner = `<div class="banner bilgi">Öneri: ${esc(gerekce)}. Harita <b>${esc(plan.harita)}</b></div>`;
    }
  }
  const hSahne = atama[S.sayfaNo - 1] || "?";
  const kisiler = ["A", "B", "C", "X"].map(k => {
    const tcK = k === "A" ? (plan && plan.birincil) : k === "B" ? (plan && plan.ikincil) : "";
    return { k, tc: tcK, n: sayim[k] || 0 };
  });
  return `
    <div id="masa" class="masa" tabindex="-1">
      <div class="masa-ust">
        <b id="masa-kuyruk">Belge ${sira || "—"}/${kuyruk.length || "—"}</b>
        <span class="ad" id="masa-ad">${esc(b.ad)}</span>
        <span class="bosluk"></span>
        <span class="kucuk" id="masa-sayfa-sayac">sayfa ${S.sayfaNo}/${n}</span>
        <span class="kucuk" id="masa-kalan">${sayim["?"] ? sayim["?"] + " atanmamış" : n + " sayfa"}</span>
        <button type="button" class="soluk-btn" id="kisayol-ac" title="Kısayollar">?</button>
      </div>
      <div class="masa-sahne ${hSahne === "?" ? "soru" : hSahne}" id="masa-sahne">
        <img id="masa-img" src="${sayfaUrl(b, S.sayfaNo, 140)}" alt="sayfa ${S.sayfaNo}">
      </div>
      <aside class="masa-yan">
        ${banner}
        <img class="masa-kirpma" id="kirpma-img" src="/api/belge/${b.id}/kirpma?n=${b.nesil || 1}" alt="isim kırpma">
        <label>İsim
          <input type="text" id="isim-girdi" value="${escAttr(t.isim)}" data-ilk="${escAttr(b.isim || "")}"
            autocapitalize="characters" autocomplete="off" spellcheck="false">
        </label>
        <label>TC
          <input type="text" id="tc-girdi" value="${escAttr(t.tc_no)}" data-ilk="${escAttr(b.tc_no || "")}"
            inputmode="numeric" autocomplete="off" spellcheck="false">
        </label>
        <label>Sicil
          <input type="text" id="sicil-girdi" value="${escAttr(t.sicil_no)}" data-ilk="${escAttr(b.sicil_no || "")}"
            inputmode="numeric" autocomplete="off" spellcheck="false">
        </label>
        <div class="kisi-liste">
          ${kisiler.map(k => `
            <button type="button" class="kisi ${k.k} ${S.aktifKisi === k.k ? "aktif" : ""}" data-kisi="${k.k}">
              <div class="kim">${KISI_AD[k.k] || k.k} · <span data-sayim="${k.k}">${k.n}</span></div>
              <div class="tc">${k.tc ? esc(k.tc) : (k.k === "X" ? "ayrı evrak / yeni belge" : "TC yok")}</div>
            </button>`).join("")}
        </div>
        <div class="eylem-grup birincil-grup">
          <button class="birincil" id="masa-onay" data-tooltip="Sayfalar tamamsa belgeyi arşivler (çok kişiliyse böler)">Onayla</button>
          <button class="soluk-btn" id="masa-atla" data-tooltip="Kaydetmeden kuyruktaki sonraki belgeye geç">Sonraya</button>
          <button class="soluk-btn" id="masa-okunamadi" data-tooltip="İsim hiç okunamıyorsa belgeyi 'okunamadı' olarak ayır">Okunamıyor</button>
        </div>

        <div class="eylem-grup yardimci-grup">
          <span class="eylem-grup-baslik">Otomatik</span>
          <button class="ikincil" id="oneri-yay" data-tooltip="Modelin önerdiği kişi atamasını boş (?) sayfalara otomatik doldurur">Öneriyi yay</button>
        </div>

        <div class="eylem-grup arac-grup">
          <span class="eylem-grup-baslik">Manuel düzeltme</span>
          <button class="soluk-btn tehlike-hafif" id="tek-kisi" data-tooltip="Çoklu kişi tespitini yok sayıp belgeyi TEK kişi olarak arşivler — ikinci kişi kaybolabilir">Tek kişi</button>
          <button class="soluk-btn" id="ayir-secim" ${S.sayfaSecim.size ? "" : "disabled"} data-tooltip="Şeritte seçtiğiniz sayfaları bu belgeden çıkarıp YENİ bir belge yapar">Seçileni ayır</button>
          <button class="soluk-btn" id="tasi-ac" ${S.sayfaSecim.size === 1 ? "" : "disabled"} data-tooltip="Seçili tek sayfayı başka bir mevcut belgeye taşır">Taşı…</button>
        </div>
      </aside>
      <div class="masa-serit" id="masa-serit">
        ${Array.from({ length: n }, (_, i) => {
          const no = i + 1;
          const h = atama[i] || "?";
          const sayfalar = (plan && plan.sayfalar) || [];
          const tc = (sayfalar[i] && sayfalar[i].tc) || "";
          const aktif = no === S.sayfaNo ? "aktif" : "";
          const sinif = h === "?" ? "soru" : h;
          return `<div class="serit-sayfa ${sinif} ${aktif}" data-sayfa="${no}">
            <img src="${sayfaUrl(b, no, 72)}" alt="s${no}" loading="lazy">
            <div class="serit-alt">
              <span class="no">s${no}</span>
              ${tc ? `<div class="tc">${esc(kisaTc(tc))}</div>` : ""}
              <div class="cip-sira">
                ${["A", "B", "C", "X"].map(k =>
                  `<button type="button" class="cip ${k} ${h === k ? "aktif" : ""}" data-ata="${no}:${k}">${k === "X" ? "≠" : k}</button>`
                ).join("")}
              </div>
            </div>
          </div>`;
        }).join("")}
      </div>
      <p class="kisayol-cubuk">
        <kbd>j</kbd>/<kbd>k</kbd> sayfa · <kbd>n</kbd>/<kbd>p</kbd> belge ·
        <kbd>1</kbd><kbd>2</kbd><kbd>3</kbd><kbd>0</kbd> ata ·
        <kbd>Enter</kbd> onay · <kbd>s</kbd> sonraya · <kbd>e</kbd> isim · <kbd>?</kbd> yardım
      </p>
    </div>`;
}

function birlestirHtml() {
  if (!S.birlestirSira.length) {
    return `<p class="bos">Sonuçlarda en az iki belge işaretleyip «Seçilenleri birleştir» deyin.</p>`;
  }
  return `
    <div class="banner bilgi">Sayfaları sürükleyerek sırayı değiştirin. Onayda tek PDF oluşur ve yeniden işlenir.</div>
    <div class="birlestir-serit" id="birlestir-serit">
      ${S.birlestirSira.map((p, i) => {
        const b = belge(p.id);
        return `<div class="sayfa" draggable="true" data-idx="${i}">
          <img src="/api/belge/${p.id}/sayfa/${p.sayfa}?dpi=72&n=${(b && b.nesil) || 1}" alt="" loading="lazy">
          <div class="sayfa-alt"><span class="no">${esc((b && b.ad) || p.id)} · s${p.sayfa}</span></div>
        </div>`;
      }).join("")}
    </div>
    <div class="eylem-sira">
      <button class="birincil" id="birlestir-onay">Birleştir</button>
      <button class="soluk-btn" id="birlestir-iptal">Vazgeç</button>
    </div>`;
}

function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, c => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));
}
function escAttr(s) { return esc(s); }

function bagla() {
  document.querySelectorAll(".sekme button").forEach(btn => {
    btn.onclick = () => gorunume(btn.dataset.gorunum);
  });
  if (S.gorunum === "yukle") baglaYukle();
  if (S.gorunum === "sonuclar") baglaSonuclar();
  if (S.gorunum === "incele") baglaIncele();
  if (S.gorunum === "birlestir") baglaBirlestir();
}

function baglaYukle() {
  const birak = document.getElementById("birak");
  const input = document.getElementById("dosya");
  if (!birak || !input) return;
  const acDosya = () => input.click();
  birak.onclick = acDosya;
  birak.onkeydown = e => {
    if (e.key === "Enter" || e.key === " ") { e.preventDefault(); acDosya(); }
  };
  birak.ondragover = e => { e.preventDefault(); e.stopPropagation(); birak.classList.add("ustunde"); };
  birak.ondragleave = () => birak.classList.remove("ustunde");
  birak.ondrop = e => {
    e.preventDefault();
    e.stopPropagation();
    birak.classList.remove("ustunde");
    yukleDosyalar(e.dataTransfer.files);
  };
  input.onchange = () => yukleDosyalar(input.files);
  const isle = document.getElementById("isle-btn");
  if (isle) isle.onclick = isleBaslat;
}

async function yukleDosyalar(files) {
  const pdf = [...files].filter(f => f.name.toLowerCase().endsWith(".pdf"));
  if (!pdf.length) { toast("PDF seçin"); return; }
  const fd = new FormData();
  pdf.forEach(f => fd.append("dosyalar", f, f.name));
  try {
    const r = await api("/api/yukle", { method: "POST", govde: fd });
    if (r.hatalar && r.hatalar.length) toast(r.hatalar.map(h => h.ad + ": " + h.hata).join("; "));
    await yenile();
  } catch (e) { toast(e.message); }
}

async function isleBaslat() {
  const vlm = !!(document.getElementById("vlm-kutu") && document.getElementById("vlm-kutu").checked);
  try {
    await api("/api/isle", { method: "POST", govde: { vlm } });
    gorunume("sonuclar");
    await yenile();
  } catch (e) { toast(e.message); }
}

function baglaSonuclar() {
  document.querySelectorAll(".kart").forEach(el => {
    el.onclick = () => acIncele(el.dataset.id);
  });
  document.querySelectorAll("input[data-isaret]").forEach(el => {
    el.onchange = () => {
      if (el.checked) S.isaret.add(el.dataset.isaret);
      else S.isaret.delete(el.dataset.isaret);
      ciz();
    };
  });
  const basla = document.getElementById("incele-basla");
  if (basla) basla.onclick = () => {
    const k = inceleKuyruk();
    if (k.length) acIncele(k[0].id);
  };
  const a = document.getElementById("arsivle-btn");
  if (a) a.onclick = async () => {
    try {
      const r = await api("/api/arsivle", { method: "POST", govde: {} });
      const hatalar = (r.sonuclar || []).filter(s => s.hata);
      toast(hatalar.length ? hatalar.map(h => h.hata).join("; ") : "Arşivlendi");
      await yenile();
    } catch (e) { toast(e.message); }
  };
  const b = document.getElementById("birlestir-ac");
  if (b) b.onclick = () => {
    const idler = [...S.isaret];
    S.birlestirSira = [];
    idler.forEach(id => {
      const bel = belge(id);
      if (!bel) return;
      for (let i = 1; i <= bel.sayfa_sayisi; i++) S.birlestirSira.push({ id, sayfa: i });
    });
    gorunume("birlestir");
  };
}

async function acIncele(id) {
  if (S.detay && S.detay.id !== id) {
    masaTaslakTopla();
    await kaydetTaslakSunucu();
  }
  S.secili = id;
  S.sayfaSecim = new Set();
  S._masaKorun = false;
  try {
    S.detay = await api(`/api/belge/${id}`);
  } catch (e) {
    toast(e.message);
    S.detay = belge(id);
  }
  if (S.detay) {
    const t = taslakHazirla(S.detay);
    S.sayfaNo = t.sayfa || 1;
    S.detay.atama = t.atama;
    if (S.detay.plan && S.detay.plan.harita && t.atama.every(h => h === "?")) {
      oneriYay();
    }
  }
  const ince = document.getElementById("sekme-incele");
  if (ince) ince.hidden = false;
  gorunume("incele");
}

function baglaIncele() {
  const b = S.detay;
  if (!b) return;
  const img = document.getElementById("masa-img");
  if (img) img.ondblclick = () => zoom(b.id, S.sayfaNo);
  const kirp = document.getElementById("kirpma-img");
  if (kirp) kirp.onerror = () => { kirp.hidden = true; };
  ["isim-girdi", "tc-girdi", "sicil-girdi"].forEach(id => {
    const g = document.getElementById(id);
    if (!g) return;
    g.oninput = () => {
      masaTaslakTopla();
      g.classList.toggle("onayli", g.value !== g.dataset.ilk);
    };
    g.onkeydown = e => {
      if (e.key === "Enter") { e.preventDefault(); masaOnay(); }
    };
  });
  document.querySelectorAll("[data-kisi]").forEach(el => {
    el.onclick = () => {
      S.aktifKisi = el.dataset.kisi;
      ataSayfa(S.sayfaNo, S.aktifKisi);
    };
    el.ondragover = e => e.preventDefault();
    el.ondrop = e => {
      e.preventDefault();
      const no = +e.dataTransfer.getData("text/plain");
      if (no) ataSayfa(no, el.dataset.kisi);
    };
  });
  document.querySelectorAll(".serit-sayfa[data-sayfa]").forEach(el => {
    const no = +el.dataset.sayfa;
    el.onclick = ev => {
      if (ev.target.closest("[data-ata]")) return;
      if (ev.shiftKey) {
        if (S.sayfaSecim.has(no)) S.sayfaSecim.delete(no);
        else S.sayfaSecim.add(no);
        masaSecimDurum();
        return;
      }
      masaSayfaGoster(no);
    };
    el.ondragstart = ev => {
      ev.dataTransfer.setData("text/plain", String(no));
    };
    el.draggable = true;
  });
  document.querySelectorAll("[data-ata]").forEach(el => {
    el.onclick = ev => {
      ev.stopPropagation();
      const [no, k] = el.dataset.ata.split(":");
      ataSayfa(+no, k);
    };
  });
  const onay = document.getElementById("masa-onay");
  if (onay) onay.onclick = masaOnay;
  const atla = document.getElementById("masa-atla");
  if (atla) atla.onclick = masaAtlaSonraya;
  const oku = document.getElementById("masa-okunamadi");
  if (oku) oku.onclick = masaOkunamadi;
  const yay = document.getElementById("oneri-yay");
  if (yay) yay.onclick = oneriYay;
  const tek = document.getElementById("tek-kisi");
  if (tek) tek.onclick = async () => {
    if (!confirm("Bu belge tek kişi olarak arşivlensin mi? İkinci kişi kaybolabilir.")) return;
    await masaTekKisi();
  };
  const ayir = document.getElementById("ayir-secim");
  if (ayir) ayir.onclick = async () => {
    const sayfalar = [...S.sayfaSecim].sort((a, c) => a - c);
    try {
      await kaydetTaslakSunucu();
      await api(`/api/belge/${b.id}/ayir`, { method: "POST", govde: { sayfalar } });
      toast("Sayfalar yeni belgeye ayrıldı");
      S.sayfaSecim = new Set();
      delete S.taslak[b.id];
      await yenile();
      S._masaKorun = false;
      S.detay = await api(`/api/belge/${b.id}`);
      taslakHazirla(S.detay);
      ciz();
    } catch (e) { toast(e.message); }
  };
  const tasi = document.getElementById("tasi-ac");
  if (tasi) tasi.onclick = tasiDialog;
  const yardim = document.getElementById("kisayol-ac");
  if (yardim) yardim.onclick = () => kisayolAc(true);
  masaOnayDurum();
  onyukleSayfa(S.sayfaNo + 1);
  onyukleSayfa(S.sayfaNo - 1);
}

function kisiHarf(e) {
  const map = {
    Digit1: "A", Digit2: "B", Digit3: "C", Digit0: "X",
    Numpad1: "A", Numpad2: "B", Numpad3: "C", Numpad0: "X",
  };
  if (map[e.code]) return map[e.code];
  if (e.key === "x" || e.key === "X") return "X";
  return "";
}

function inceleKlavye(e) {
  if (S._masaKilit || !S.detay) return;
  if (e.isComposing || e.metaKey || e.ctrlKey || e.altKey) return;
  if (modalAcik()) return;

  if (e.key === "Escape") return;

  const inputta = girdiOdakta();

  if (e.key === "?" && !inputta) {
    e.preventDefault();
    kisayolAc(!S.kisayolAcik);
    return;
  }

  if ((e.key === "e" || e.key === "E" || e.key === "/") && !inputta) {
    e.preventDefault();
    const g = document.getElementById("isim-girdi");
    if (g) { g.focus(); g.select(); }
    return;
  }

  if (e.key === "Enter" && !e.shiftKey) {
    if (e.target && e.target.id === "kisayol-ac") return;
    e.preventDefault();
    masaOnay();
    return;
  }

  if (inputta) return;

  const harf = kisiHarf(e);
  if (harf) {
    e.preventDefault();
    S.aktifKisi = harf;
    ataSayfa(S.sayfaNo, harf);
    return;
  }

  if (e.key === "j" || e.key === "ArrowRight") {
    e.preventDefault();
    masaSayfaGoster(S.sayfaNo + 1);
    return;
  }
  if (e.key === "k" || e.key === "ArrowLeft") {
    e.preventDefault();
    masaSayfaGoster(S.sayfaNo - 1);
    return;
  }
  if (e.key === "ArrowDown") {
    e.preventDefault();
    kaydirmaBaslat(1);
    return;
  }
  if (e.key === "ArrowUp") {
    e.preventDefault();
    kaydirmaBaslat(-1);
    return;
  }
  if (e.key === "n" || e.key === "N") {
    e.preventDefault();
    masaBelgeGec(1);
    return;
  }
  if (e.key === "p" || e.key === "P") {
    e.preventDefault();
    masaBelgeGec(-1);
    return;
  }
  if (e.key === "s" || e.key === "S") {
    e.preventDefault();
    masaAtlaSonraya();
  }
}

function sonuclarKlavye(e) {
  if (girdiOdakta() || modalAcik() || e.isComposing) return;
  if (e.metaKey || e.ctrlKey || e.altKey) return;
  const k = inceleKuyruk();
  if (!k.length) return;
  if (e.key === "i" || e.key === "İ" || e.key === "I") {
    e.preventDefault();
    acIncele(k[0].id);
    return;
  }
  if (e.key === "Enter" && e.target && e.target.tagName !== "BUTTON") {
    e.preventDefault();
    acIncele(k[0].id);
  }
}

// Yukarı/aşağı ok tuşu basılı tutulunca akıcı kaydırma. Tek seferlik
// "behavior: smooth" ile denendi ama tuş tekrarları üst üste binip
// sıçramalı/kontrolsüz kaymaya yol açıyordu (işletim sistemi basılı
// tutmayı hızlı keydown tekrarları olarak yolluyor). Bunun yerine her
// karede küçük bir adım atan bir requestAnimationFrame döngüsü kullanılır
// — tuş bırakılana kadar sürer, gerçek "basılı tut" hissi verir.
let kaydirmaYon = 0;
let kaydirmaAf = null;
function kaydirmaAdimi() {
  if (!kaydirmaYon) { kaydirmaAf = null; return; }
  window.scrollBy(0, kaydirmaYon * 16);
  kaydirmaAf = requestAnimationFrame(kaydirmaAdimi);
}
function kaydirmaBaslat(yon) {
  kaydirmaYon = yon;
  if (kaydirmaAf === null) kaydirmaAf = requestAnimationFrame(kaydirmaAdimi);
}
document.addEventListener("keyup", e => {
  if (e.key === "ArrowDown" || e.key === "ArrowUp") kaydirmaYon = 0;
});

function masaSayfaGoster(no) {
  const b = S.detay;
  if (!b) return;
  const n = b.sayfa_sayisi;
  no = Math.max(1, Math.min(n, no));
  masaTaslakTopla();
  S.sayfaNo = no;
  taslakAl(b.id).sayfa = no;
  const img = document.getElementById("masa-img");
  if (img) {
    img.src = sayfaUrl(b, no, 140);
    img.alt = `sayfa ${no}`;
  }
  const h = (taslakAl(b.id).atama[no - 1]) || "?";
  const sahne = document.getElementById("masa-sahne");
  if (sahne) {
    sahne.className = `masa-sahne ${h === "?" ? "soru" : h}`;
    sahne.scrollTop = 0;
  }
  document.querySelectorAll(".serit-sayfa").forEach(el => {
    el.classList.toggle("aktif", +el.dataset.sayfa === no);
  });
  const sayac = document.getElementById("masa-sayfa-sayac");
  if (sayac) sayac.textContent = `sayfa ${no}/${n}`;
  const aktif = document.querySelector(`.serit-sayfa[data-sayfa="${no}"]`);
  if (aktif) aktif.scrollIntoView({ inline: "center", block: "nearest" });
  // Pencereyi en son burada tepeye götür: yukarıdaki şerit scrollIntoView
  // çağrısı "nearest" ile sayfayı aşağı kaydırabiliyordu (şerit görünsün
  // diye), bu da tepeye kaydırmayı eziyordu. Sıra önemli — en son biz kazanalım.
  window.scrollTo({ top: 0 });
  onyukleSayfa(no + 1);
  onyukleSayfa(no - 1);
}

function onyukleSayfa(no) {
  const b = S.detay;
  if (!b || no < 1 || no > b.sayfa_sayisi) return;
  const img = new Image();
  img.src = sayfaUrl(b, no, 140);
}

function masaAtaDom() {
  const b = S.detay;
  if (!b) return;
  const t = taslakAl(b.id);
  const sayim = { A: 0, B: 0, C: 0, X: 0, "?": 0 };
  t.atama.forEach(h => { sayim[h] = (sayim[h] || 0) + 1; });
  document.querySelectorAll(".serit-sayfa[data-sayfa]").forEach(el => {
    const no = +el.dataset.sayfa;
    const h = t.atama[no - 1] || "?";
    const aktif = no === S.sayfaNo ? " aktif" : "";
    el.className = `serit-sayfa ${h === "?" ? "soru" : h}${aktif}`;
    el.querySelectorAll("[data-ata]").forEach(cip => {
      const k = cip.dataset.ata.split(":")[1];
      cip.classList.toggle("aktif", h === k);
    });
  });
  document.querySelectorAll("[data-sayim]").forEach(el => {
    el.textContent = sayim[el.dataset.sayim] || 0;
  });
  document.querySelectorAll("[data-kisi]").forEach(el => {
    el.classList.toggle("aktif", el.dataset.kisi === S.aktifKisi);
  });
  const h = t.atama[S.sayfaNo - 1] || "?";
  const sahne = document.getElementById("masa-sahne");
  if (sahne) sahne.className = `masa-sahne ${h === "?" ? "soru" : h}`;
  const kalan = document.getElementById("masa-kalan");
  if (kalan) kalan.textContent = sayim["?"] ? `${sayim["?"]} atanmamış` : `${b.sayfa_sayisi} sayfa`;
  masaOnayDurum();
}

function masaOnayDurum() {
  const btn = document.getElementById("masa-onay");
  if (!btn || !S.detay) return;
  const t = taslakAl(S.detay.id);
  const { bekler, bol, atanmamis } = masaKarar(t);
  if (bekler) {
    btn.disabled = true;
    btn.textContent = `Onayla (${atanmamis} atanmamış)`;
  } else {
    btn.disabled = false;
    btn.textContent = bol ? "Onayla ve böl" : "Onayla ve arşivle";
  }
  masaSecimDurum();
}

function masaSecimDurum() {
  const ayir = document.getElementById("ayir-secim");
  const tasi = document.getElementById("tasi-ac");
  if (ayir) ayir.disabled = !S.sayfaSecim.size;
  if (tasi) tasi.disabled = S.sayfaSecim.size !== 1;
}

function masaKarar(t) {
  const atama = t.atama || [];
  const atanmamis = atama.filter(x => x === "?").length;
  const kisiler = new Set(atama.filter(x => x !== "?" && x !== "X"));
  const cok = !!(S.detay && (S.detay.cok_kimlik || S.detay.neden === "cok_kimlik"));
  const karisik = kisiler.size > 1 || atama.includes("X");
  const bolmeyeAday = cok || karisik;
  return {
    bekler: bolmeyeAday && atanmamis > 0,
    bol: bolmeyeAday && atanmamis === 0,
    atanmamis,
  };
}

function masaUstGuncelle() {
  const kuyruk = inceleKuyruk();
  const sira = kuyruk.findIndex(x => x.id === S.secili) + 1;
  const el = document.getElementById("masa-kuyruk");
  if (el) el.textContent = `Belge ${sira || "—"}/${kuyruk.length || "—"}`;
}

function ataSayfa(no, kisi) {
  if (!S.detay) return;
  const t = taslakAl(S.detay.id);
  if (!t.atama) t.atama = [];
  if (S.sayfaSecim.size > 1 && S.sayfaSecim.has(no)) {
    S.sayfaSecim.forEach(n => { t.atama[n - 1] = kisi; });
  } else {
    t.atama[no - 1] = kisi;
  }
  S.detay.atama = t.atama;
  S.aktifKisi = kisi;
  masaAtaDom();
  kaydetAtama();
}

async function kaydetAtama() {
  if (!S.detay) return;
  try {
    await api(`/api/belge/${S.detay.id}/ata`, { method: "POST", govde: { atama: taslakAl(S.detay.id).atama } });
  } catch (e) { toast(e.message); }
}

async function kaydetTaslakSunucu() {
  if (!S.detay) return;
  masaTaslakTopla();
  const t = taslakAl(S.detay.id);
  try {
    await api(`/api/belge/${S.detay.id}/isim`, {
      method: "POST",
      govde: { isim: t.isim, tc_no: t.tc_no, sicil_no: t.sicil_no },
    });
    if (t.atama && t.atama.length === S.detay.sayfa_sayisi) {
      await api(`/api/belge/${S.detay.id}/ata`, { method: "POST", govde: { atama: t.atama } });
    }
  } catch (e) { toast(e.message); }
}

function sonrakiInceleId(hariç) {
  const k = inceleKuyruk();
  const i = k.findIndex(b => b.id === hariç);
  if (!k.length) return null;
  if (i < 0) return k[0].id;
  const aday = k[i + 1] || k[0];
  return aday.id === hariç ? null : aday.id;
}

async function masaBelgeGec(yon) {
  if (!S.detay) return;
  const k = inceleKuyruk();
  const i = k.findIndex(b => b.id === S.secili);
  if (k.length < 2 || i < 0) { toast("Kuyrukta başka incelenmeli yok"); return; }
  const j = (i + yon + k.length) % k.length;
  await acIncele(k[j].id);
}

async function masaAtlaSonraya() {
  toast("Sonraya bırakıldı");
  await masaBelgeGec(1);
}

async function masaIleri(bitenId, sonraki) {
  await yenile();
  const k = inceleKuyruk();
  const hedef = (sonraki && k.some(b => b.id === sonraki)) ? sonraki
    : (k.find(b => b.id !== bitenId) || k[0]);
  const hid = hedef && hedef.id;
  if (hid) {
    S._masaKorun = false;
    await acIncele(hid);
    return;
  }
  S._masaKorun = false;
  S.secili = null;
  S.detay = null;
  toast("İncelenecek belge kalmadı");
  gorunume("sonuclar");
}

async function masaOnay() {
  if (S._masaKilit || !S.detay) return;
  masaTaslakTopla();
  const t = taslakAl(S.detay.id);
  const isim = (t.isim || "").trim();
  const { bekler, bol } = masaKarar(t);
  if (bekler) {
    toast("Önce her sayfayı atayın (1 / 2 / 3 / 0)");
    return;
  }
  S._masaKilit = true;
  const id = S.detay.id;
  const sonraki = sonrakiInceleId(id);
  try {
    await api(`/api/belge/${id}/isim`, {
      method: "POST",
      govde: { isim: t.isim, tc_no: t.tc_no, sicil_no: t.sicil_no },
    });
    if (bol) {
      await api(`/api/belge/${id}/ata`, { method: "POST", govde: { atama: t.atama } });
      await api(`/api/belge/${id}/onayla`, { method: "POST", govde: { tek_kisi: false } });
      toast("Bölündü; parçalar işleniyor");
    } else if (!isim) {
      await api(`/api/belge/${id}/atla`, { method: "POST" });
      await api("/api/arsivle", { method: "POST", govde: { idler: [id], tek_kisi: true } });
      toast("Okunamadı olarak ayrıldı");
    } else {
      await api(`/api/belge/${id}/onayla`, { method: "POST", govde: { tek_kisi: true } });
      toast("Arşivlendi");
    }
    delete S.taslak[id];
    await masaIleri(id, sonraki);
  } catch (e) { toast(e.message); }
  finally { S._masaKilit = false; }
}

async function masaOkunamadi() {
  if (S._masaKilit || !S.detay) return;
  S._masaKilit = true;
  const id = S.detay.id;
  const sonraki = sonrakiInceleId(id);
  try {
    await api(`/api/belge/${id}/atla`, { method: "POST" });
    await api("/api/arsivle", { method: "POST", govde: { idler: [id], tek_kisi: true } });
    toast("Okunamadı olarak ayrıldı");
    delete S.taslak[id];
    await masaIleri(id, sonraki);
  } catch (e) { toast(e.message); }
  finally { S._masaKilit = false; }
}

async function masaTekKisi() {
  if (S._masaKilit || !S.detay) return;
  masaTaslakTopla();
  const t = taslakAl(S.detay.id);
  S._masaKilit = true;
  const id = S.detay.id;
  const sonraki = sonrakiInceleId(id);
  try {
    await api(`/api/belge/${id}/isim`, {
      method: "POST",
      govde: { isim: t.isim, tc_no: t.tc_no, sicil_no: t.sicil_no },
    });
    await api(`/api/belge/${id}/onayla`, { method: "POST", govde: { tek_kisi: true } });
    toast("Tek kişi olarak arşivlendi");
    delete S.taslak[id];
    await masaIleri(id, sonraki);
  } catch (e) { toast(e.message); }
  finally { S._masaKilit = false; }
}

function oneriYay() {
  const plan = S.detay.plan;
  if (!plan || !plan.harita) { toast("Öneri yok"); return; }
  let son = "A";
  let atama = [...plan.harita].map(c => {
    if (c !== "?") son = c;
    return c === "?" ? son : c;
  });
  if (plan.sayfalar && plan.sayfalar.some(s => s.sahip && s.sahip !== s.oneri)) {
    atama = plan.sayfalar.map((s, i) => s.sahip || plan.harita[i] || "?");
    let s2 = "A";
    atama = atama.map(c => {
      if (c !== "?") s2 = c;
      return c === "?" ? s2 : c;
    });
  }
  taslakAl(S.detay.id).atama = atama;
  S.detay.atama = atama;
  masaAtaDom();
  kaydetAtama();
}

async function tasiDialog() {
  const no = [...S.sayfaSecim][0];
  const diger = belgeler().filter(b => b.id !== S.secili && b.kova !== "ayrildi" && b.durum !== "hata");
  if (!diger.length) { toast("Taşınacak başka belge yok"); return; }
  acModal(`<div class="dogrula-kart" style="max-width:28rem">
    <h3 style="margin:.2rem 0 .8rem;font-family:var(--baslik)">Sayfa ${no} nereye?</h3>
    ${diger.map(b => `<button class="kisi" data-hedef="${b.id}" style="width:100%;margin-bottom:.4rem">
      <div class="kim">${esc(b.ad)}</div>
      <div class="tc">${b.sayfa_sayisi} sayfa${b.isim ? " · " + esc(b.isim) : ""}</div>
    </button>`).join("")}
    <button class="soluk-btn" id="tasi-iptal">Vazgeç</button>
  </div>`);
  const m = document.getElementById("modal");
  document.getElementById("tasi-iptal").onclick = kapatModal;
  m.querySelectorAll("[data-hedef]").forEach(el => {
    el.onclick = async () => {
      kapatModal();
      try {
        await kaydetTaslakSunucu();
        await api("/api/tasi", {
          method: "POST",
          govde: { kaynak_id: S.secili, sayfa: no, hedef_id: el.dataset.hedef },
        });
        toast("Sayfa taşındı");
        S.sayfaSecim = new Set();
        delete S.taslak[S.secili];
        await yenile();
        S._masaKorun = false;
        S.detay = await api(`/api/belge/${S.secili}`);
        taslakHazirla(S.detay);
        ciz();
      } catch (e) { toast(e.message); }
    };
  });
}

function zoom(id, no) {
  acModal(
    `<img src="/api/belge/${id}/sayfa/${no}?dpi=140&n=${(S.detay && S.detay.nesil) || 1}" alt="sayfa ${no}">`,
    true,
  );
}

function kisayolAc(acik) {
  S.kisayolAcik = !!acik;
  const p = document.getElementById("kisayol-panel");
  if (!p) return;
  if (!acik) {
    p.hidden = true;
    p.innerHTML = "";
    return;
  }
  p.hidden = false;
  p.innerHTML = `<h3>İnceleme kısayolları</h3>
    <table>${KISAYOL_SATIR.map(([tus, is]) =>
      `<tr><td>${tus.split(" / ").map(t => `<kbd>${esc(t)}</kbd>`).join(" ")}</td><td>${esc(is)}</td></tr>`
    ).join("")}</table>
    <p class="ipucu">İsim / TC / sicil yazarken harfler alana gider; 1–3 atama yapmaz. Esc alanı bırakır.</p>`;
}

function baglaBirlestir() {
  const serit = document.getElementById("birlestir-serit");
  if (!serit) return;
  let suruklenen = null;
  serit.querySelectorAll(".sayfa").forEach(el => {
    el.ondragstart = () => { suruklenen = +el.dataset.idx; el.classList.add("surukleniyor"); };
    el.ondragend = () => el.classList.remove("surukleniyor");
    el.ondragover = e => e.preventDefault();
    el.ondrop = e => {
      e.preventDefault();
      const hedef = +el.dataset.idx;
      if (suruklenen == null || hedef === suruklenen) return;
      const [al] = S.birlestirSira.splice(suruklenen, 1);
      S.birlestirSira.splice(hedef, 0, al);
      ciz();
    };
  });
  document.getElementById("birlestir-onay").onclick = async () => {
    try {
      await api("/api/birlestir", { method: "POST", govde: { sira: S.birlestirSira } });
      toast("Birleştirildi; yeniden işleniyor");
      S.birlestirSira = [];
      S.isaret = new Set();
      gorunume("sonuclar");
      await yenile();
    } catch (e) { toast(e.message); }
  };
  document.getElementById("birlestir-iptal").onclick = () => {
    S.birlestirSira = [];
    gorunume("sonuclar");
  };
}

document.addEventListener("DOMContentLoaded", () => {
  kapatModal();
  kisayolAc(false);
  ciz();
  yenile().catch(e => {
    toast(e.message || "Sunucuya bağlanılamadı");
    ciz();
  });
});

document.addEventListener("keydown", e => {
  if (e.key === "Escape") {
    if (modalAcik()) { kapatModal(); e.preventDefault(); return; }
    if (S.kisayolAcik) { kisayolAc(false); e.preventDefault(); return; }
    if (girdiOdakta()) {
      document.activeElement.blur();
      const masa = document.getElementById("masa");
      if (masa) masa.focus({ preventScroll: true });
      e.preventDefault();
      return;
    }
    return;
  }
  if (S.gorunum === "incele") inceleKlavye(e);
  else if (S.gorunum === "sonuclar") sonuclarKlavye(e);
});
