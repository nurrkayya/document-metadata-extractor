"""Yerel metadata çıkarma arayüzü.

    .venv/bin/python web/uygula.py
    .venv/bin/python -m uvicorn web.uygula:uygulama --host 127.0.0.1 --port 8765

Çıktı varsayılanı `web_cikti/` — proje `arsiv/` ile çakışmaz. `--cikti` ile değişir.
Kişisel veri makineden çıkmaz; VLM/OCR mevcut `belge/` kodunu çağırır.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

# `python web/uygula.py` ile çalışınca sys.path[0] web/ olur
_KOK = Path(__file__).resolve().parent.parent
if str(_KOK) not in sys.path:
    sys.path.insert(0, str(_KOK))

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from belge.yollar import PROJE_KOK
from web.kuyruk import Durum
from web.pdf_islem import ONIZLEME_DPI, YAKIN_DPI, isim_kirpma, kucuk_resim

STATIK = Path(__file__).resolve().parent / "statik"
KOK = PROJE_KOK


class _DurumVekil:
    """İçe aktarınca web_cikti/ açılmaz; ilk istekte veya --cikti ile kurulur."""

    def __init__(self) -> None:
        self._asıl: Durum | None = None

    def kur(self, kok: Path | None = None) -> Durum:
        self._asıl = Durum(kok)
        return self._asıl

    def _al(self) -> Durum:
        if self._asıl is None:
            self._asıl = Durum()
        return self._asıl

    def __getattr__(self, ad: str):
        return getattr(self._al(), ad)


durum = _DurumVekil()

uygulama = FastAPI(title="Sicil belgesi", docs_url=None, redoc_url=None)
uygulama.mount("/statik", StaticFiles(directory=STATIK), name="statik")


class IsleGovde(BaseModel):
    vlm: bool = True
    belge_idler: list[str] | None = None


class AtaGovde(BaseModel):
    atama: list[str]


class IsimGovde(BaseModel):
    isim: str = ""
    tc_no: str | None = None
    sicil_no: str | None = None


class OnayGovde(BaseModel):
    tek_kisi: bool = False


class BirlestirGovde(BaseModel):
    sira: list[dict] = Field(default_factory=list)


class TasiGovde(BaseModel):
    kaynak_id: str
    sayfa: int
    hedef_id: str
    konum: int | None = None


class AyirGovde(BaseModel):
    sayfalar: list[int]
    hedef_id: str | None = None


class ArsivGovde(BaseModel):
    idler: list[str] | None = None
    tek_kisi: bool = False


@uygulama.get("/")
def ana():
    return FileResponse(
        STATIK / "index.html",
        headers={"Cache-Control": "no-store"},
    )


@uygulama.get("/api/durum")
def api_durum():
    return durum.ozet()


@uygulama.get("/api/akim")
async def api_akim():
    async def uret():
        while True:
            try:
                olay = durum.olaylar.get_nowait()
            except Exception:
                olay = {"tur": "nabiz", **durum.ozet()["is"]}
            yield f"data: {json.dumps(olay, ensure_ascii=False)}\n\n"
            await asyncio.sleep(0.8)
            if olay.get("tur") == "bitti":
                yield f"data: {json.dumps(durum.ozet()['is'] | {'tur': 'bitti'}, ensure_ascii=False)}\n\n"
                break

    return StreamingResponse(uret(), media_type="text/event-stream")


@uygulama.post("/api/yukle")
async def api_yukle(dosyalar: list[UploadFile] = File(...)):
    eklenen = []
    hatalar = []
    for f in dosyalar:
        ad = Path(f.filename or "belge.pdf").name
        try:
            icerik = await f.read()
            if not icerik:
                raise ValueError("boş dosya")
            b = durum.yukle(ad, icerik)
            eklenen.append({"id": b.id, "ad": b.ad, "sayfa_sayisi": b.sayfa_sayisi})
        except Exception as e:
            hatalar.append({"ad": ad, "hata": str(e)})
    return {"belgeler": eklenen, "hatalar": hatalar}


@uygulama.post("/api/isle")
def api_isle(govde: IsleGovde):
    try:
        is_id = durum.isle(vlm=govde.vlm, belge_idler=govde.belge_idler)
    except RuntimeError as e:
        raise HTTPException(409, str(e)) from e
    return {"is_id": is_id, **durum.ozet()}


@uygulama.get("/api/belge/{belge_id}")
def api_belge(belge_id: str):
    try:
        return durum.belge_ayrinti(belge_id)
    except KeyError as e:
        raise HTTPException(404, str(e)) from e


@uygulama.get("/api/belge/{belge_id}/sayfa/{sayfa_no}")
def api_sayfa(belge_id: str, sayfa_no: int, dpi: int = 0):
    try:
        b = durum.belge_ayrinti(belge_id)
    except KeyError as e:
        raise HTTPException(404, str(e)) from e
    yol = durum.belgeler[belge_id].yol
    if not yol.exists():
        raise HTTPException(404, "dosya yok")
    kullan_dpi = dpi or ONIZLEME_DPI
    if kullan_dpi > YAKIN_DPI:
        kullan_dpi = YAKIN_DPI
    onizleme = durum.onizleme / belge_id / f"{sayfa_no}_{kullan_dpi}_{b['nesil']}.png"
    try:
        if not onizleme.exists():
            onizleme.parent.mkdir(parents=True, exist_ok=True)
            onizleme.write_bytes(kucuk_resim(yol, sayfa_no, dpi=kullan_dpi))
        return Response(onizleme.read_bytes(), media_type="image/png")
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@uygulama.get("/api/belge/{belge_id}/kirpma")
def api_kirpma(belge_id: str):
    try:
        yol = durum.belgeler[belge_id].yol
    except KeyError as e:
        raise HTTPException(404, str(e)) from e
    png = isim_kirpma(yol)
    if png is None:
        raise HTTPException(404, "kırpma yok")
    return Response(png, media_type="image/png")


@uygulama.post("/api/belge/{belge_id}/ata")
def api_ata(belge_id: str, govde: AtaGovde):
    try:
        b = durum.ata(belge_id, govde.atama)
    except KeyError as e:
        raise HTTPException(404, str(e)) from e
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    return durum.belge_ayrinti(b.id)


@uygulama.post("/api/belge/{belge_id}/isim")
def api_isim(belge_id: str, govde: IsimGovde):
    try:
        durum.isim_duzelt(belge_id, govde.isim, govde.tc_no, govde.sicil_no)
    except KeyError as e:
        raise HTTPException(404, str(e)) from e
    return durum.belge_ayrinti(belge_id)


@uygulama.post("/api/belge/{belge_id}/onayla")
def api_onayla(belge_id: str, govde: OnayGovde | None = None):
    govde = govde or OnayGovde()
    try:
        b = durum.belgeler[belge_id]
    except KeyError as e:
        raise HTTPException(404, str(e)) from e
    harita = "".join(b.atama or [])
    kisiler = {c for c in harita if c not in ("?", "X")}
    bol = (b.cok_kimlik or len(kisiler) > 1 or "X" in harita) and not govde.tek_kisi
    if bol:
        try:
            idler = durum.onayla_bol(belge_id)
        except ValueError as e:
            raise HTTPException(400, str(e)) from e
        return {"parcalar": idler, **durum.ozet()}
    try:
        sonuclar = durum.arsivle([belge_id], tek_kisi=govde.tek_kisi)
    except (KeyError, ValueError) as e:
        raise HTTPException(400, str(e)) from e
    return {"sonuclar": sonuclar, **durum.ozet()}


@uygulama.post("/api/belge/{belge_id}/atla")
def api_atla(belge_id: str):
    try:
        durum.atla(belge_id)
    except KeyError as e:
        raise HTTPException(404, str(e)) from e
    return durum.ozet()


@uygulama.post("/api/birlestir")
def api_birlestir(govde: BirlestirGovde):
    try:
        yeni = durum.birlestir(govde.sira)
    except (KeyError, ValueError) as e:
        raise HTTPException(400, str(e)) from e
    return {"id": yeni.id, **durum.ozet()}


@uygulama.post("/api/tasi")
def api_tasi(govde: TasiGovde):
    try:
        durum.tasi(govde.kaynak_id, govde.sayfa, govde.hedef_id, govde.konum)
    except (KeyError, ValueError) as e:
        raise HTTPException(400, str(e)) from e
    return durum.ozet()


@uygulama.post("/api/belge/{belge_id}/ayir")
def api_ayir(belge_id: str, govde: AyirGovde):
    try:
        yeni_id = durum.ayir(belge_id, govde.sayfalar, govde.hedef_id)
    except (KeyError, ValueError) as e:
        raise HTTPException(400, str(e)) from e
    return {"id": yeni_id, **durum.ozet()}


@uygulama.post("/api/arsivle")
def api_arsivle(govde: ArsivGovde | None = None):
    govde = govde or ArsivGovde()
    try:
        sonuclar = durum.arsivle(govde.idler, tek_kisi=govde.tek_kisi)
    except (KeyError, ValueError) as e:
        raise HTTPException(400, str(e)) from e
    return {"sonuclar": sonuclar, **durum.ozet()}


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description="Yerel sicil belgesi arayüzü")
    p.add_argument("--cikti", default=os.environ.get("WEB_CIKTI", "web_cikti"),
                   help="çıktı kökü (varsayılan web_cikti/)")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8765)
    args = p.parse_args(argv)
    os.environ["WEB_CIKTI"] = str(Path(args.cikti).resolve())
    d = durum.kur(Path(os.environ["WEB_CIKTI"]))
    import uvicorn

    print(f"Arayüz  http://{args.host}:{args.port}")
    print(f"Çıktı   {os.environ['WEB_CIKTI']}")
    if d.vlm_uyari:
        print(f"Uyarı   {d.vlm_uyari}")
    uvicorn.run(uygulama, host=args.host, port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
