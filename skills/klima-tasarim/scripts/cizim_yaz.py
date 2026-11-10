"""Sonuçları orijinal DXF'e katmanlar halinde işler.

Katmanlar: KLIMA-IC, KLIMA-DIS, KLIMA-BORU-SIVI, KLIMA-BORU-GAZ, KLIMA-YBRANCH, KLIMA-YAZI
Bloklar: blok kütüphanesi DXF'i ve data/blok_eslesme.json varsa oradan, yoksa basit dahili bloklar.
Koordinatlar metre -> çizim birimi (1/olcek) çevrilir.
"""
from __future__ import annotations

import math
from pathlib import Path

import ezdxf
from ezdxf import bbox, xref

from ortak import DATA_DIR, json_oku

# Renkler mimari çizimlerde sık kullanılan yeşil/camgöbeğinden ayrışsın: sıvı turuncu, gaz eflatun, Y-branch kırmızı
KATMANLAR = {"KLIMA-IC": 5, "KLIMA-DIS": 1, "KLIMA-BORU-SIVI": 30, "KLIMA-BORU-GAZ": 6, "KLIMA-YBRANCH": 1, "KLIMA-YAZI": 7}
KALINLIK = {"KLIMA-BORU-SIVI": 40, "KLIMA-BORU-GAZ": 50, "KLIMA-IC": 35, "KLIMA-DIS": 35}  # 1/100 mm


def _katmanlar(doc):
    for ad, renk in KATMANLAR.items():
        if ad not in doc.layers:
            doc.layers.add(ad, color=renk)
        lay = doc.layers.get(ad)
        lay.color = renk
        if ad in KALINLIK:
            lay.dxf.lineweight = KALINLIK[ad]


def _dahili_bloklar(doc, k):
    """k: 1 metre kaç çizim birimi."""
    def blok(ad, w, d, yazi):
        if ad in doc.blocks:
            return
        b = doc.blocks.new(ad)
        b.add_lwpolyline([(-w / 2 * k, 0), (w / 2 * k, 0), (w / 2 * k, d * k), (-w / 2 * k, d * k)], close=True)
        b.add_line((-w / 2 * k, 0), (w / 2 * k, d * k))
        b.add_text(yazi, height=0.08 * k, dxfattribs={"insert": (-w / 2 * k + 0.03 * k, d * k * 0.4)})
    blok("KLIMA_IU_DUVAR", 1.0, 0.25, "IU")
    blok("KLIMA_IU_SALON", 1.6, 0.3, "IU-S")
    blok("KLIMA_IU_KASET", 0.95, 0.95, "KASET")
    blok("KLIMA_IU_KANAL", 1.2, 0.7, "KANAL")
    blok("KLIMA_DU", 1.0, 0.8, "DU")
    if "KLIMA_YBRANCH" not in doc.blocks:
        b = doc.blocks.new("KLIMA_YBRANCH")
        b.add_circle((0, 0), 0.12 * k)
        b.add_line((-0.12 * k, -0.12 * k), (0.12 * k, 0.12 * k))


def _sarmala(doc, tip: str, lib_ad: str, gercek_m: float, k: float):
    """Kütüphane bloğunu, sınır kutusu merkezi orijinde ve uzun kenarı X ekseninde, gerçek ölçüsüne
    ölçeklenmiş bir 'KLIMA_LIB_<tip>' bloğuna sarar. Döner: (blok adı, derinlik [çizim birimi])."""
    blk = doc.blocks.get(lib_ad)
    ext = bbox.extents(blk, fast=True)
    if not ext.has_data or ext.size.x <= 0 or ext.size.y <= 0:
        return None
    w, h = ext.size.x, ext.size.y
    cx, cy = ext.center.x, ext.center.y
    dondur = h > w * 1.15
    s = gercek_m * k / max(w, h)
    if dondur:  # 90° döndürme: (x, y) -> (-y, x)
        ox, oy = s * cy, -s * cx
    else:
        ox, oy = -s * cx, -s * cy
    ad = f"KLIMA_LIB_{tip.upper()}"
    if ad in doc.blocks:
        doc.blocks.delete_block(ad, safe=False)
    sar = doc.blocks.new(ad)
    sar.add_blockref(lib_ad, (ox, oy), dxfattribs={"xscale": s, "yscale": s, "rotation": 90 if dondur else 0})
    return ad, min(w, h) * s


def kucuk_kutuphane(buyuk_dxf: str, hedef: str) -> str:
    """Büyük kütüphane DXF'inden yalnız blok_eslesme.json'da geçen blokları küçük bir DXF'e çıkarır."""
    adlar = {v for t, v in json_oku(DATA_DIR / "blok_eslesme.json").items() if not t.startswith("_") and v}
    kdoc = ezdxf.readfile(buyuk_dxf)
    yeni = ezdxf.new(kdoc.dxfversion)
    yuk = xref.Loader(kdoc, yeni, conflict_policy=xref.ConflictPolicy.KEEP)
    for ad in adlar:
        if ad in kdoc.blocks:
            yuk.load_block_layout(kdoc.blocks.get(ad))
    yuk.execute()
    yeni.saveas(hedef)
    return hedef


def _kutuphane_bloklari(doc, kutuphane_dxf: str | None, k: float) -> dict:
    """data/blok_eslesme.json'daki eşlemeleri yükler. Döner: {tip: (sarmal blok adı, derinlik)}."""
    es_yol = DATA_DIR / "blok_eslesme.json"
    if not kutuphane_dxf or not es_yol.exists() or not Path(kutuphane_dxf).exists():
        return {}
    ham = json_oku(es_yol)
    es = {t: v for t, v in ham.items() if not t.startswith("_") and v}
    olcu = ham.get("_gercek_genislik_m", {})
    try:
        kdoc = ezdxf.readfile(kutuphane_dxf)
        yukleyici = xref.Loader(kdoc, doc, conflict_policy=xref.ConflictPolicy.KEEP)
        for ad in set(es.values()):
            if ad in kdoc.blocks and ad not in doc.blocks:
                yukleyici.load_block_layout(kdoc.blocks.get(ad))
        yukleyici.execute()
    except Exception as e:  # kütüphane okunamazsa dahili bloklarla devam
        print(f"UYARI: blok kütüphanesi yüklenemedi: {e}")
        return {}
    out = {}
    for tip, lib_ad in es.items():
        if lib_ad not in doc.blocks:
            print(f"UYARI: kütüphanede '{lib_ad}' bloğu yok ({tip}); dahili blok kullanılacak.")
            continue
        try:
            r = _sarmala(doc, tip, lib_ad, float(olcu.get(tip, 1.0)), k)
        except Exception as e:
            print(f"UYARI: '{lib_ad}' ölçeklenemedi: {e}")
            r = None
        if r:
            out[tip] = r
    out["_du_buyuk_kw"] = float(ham.get("_du_buyuk_kw", 28.0))
    return out


def mevcut_klimayi_gizle(doc) -> list[str]:
    """Plandaki eski/mevcut klima tasarımı katmanlarını KAPATIR (silmez). Kütüphane bloklarının iç katmanları
    (LATS_PANEL, LATS_AIR_DIRECTION ...) açık kalır; yalnız mevcut ünitelerin yerleştirildiği LATS_EQ_* kapanır."""
    from ortak import normalize
    from plan_cikar import katman_kategorisi
    kapanan = []
    for lay in doc.layers:
        ad = lay.dxf.name
        n = normalize(ad)
        if ad.startswith("KLIMA-"):
            continue
        if n.startswith("LATS_") and not n.startswith("LATS_EQ_"):
            continue
        if katman_kategorisi(ad) == "klima" or "MEKANIK" in n or n == "KLIMAYAZI":
            if not (lay.is_off() and lay.is_frozen()):
                # yalnız kapatmak, blok içindeki başka katmanlardaki çizgileri (LATS_CASSETE, LATS_PANEL ...)
                # gizlemez; dondurmak (freeze) mevcut ünite bloğunu tümüyle gizler
                if doc.header.get("$CLAYER", "0") == ad:
                    doc.header["$CLAYER"] = "0"
                lay.off()
                lay.freeze()
                kapanan.append(ad)
    return kapanan


def yaz(kaynak_dxf: str, cikti_dxf: str, olcek: float, ic: dict, opt: dict, kutuphane_dxf: str | None = None,
        mevcut_gizle: bool = True, du_kot_m: float = 0.0) -> str:
    doc = ezdxf.readfile(kaynak_dxf)
    msp = doc.modelspace()
    k = 1.0 / olcek
    if mevcut_gizle:
        kapanan = mevcut_klimayi_gizle(doc)
        if kapanan:
            print(f"Mevcut klima katmanları kapatıldı (silinmedi): {', '.join(kapanan)}")
    _katmanlar(doc)
    _dahili_bloklar(doc, k)
    es = _kutuphane_bloklari(doc, kutuphane_dxf, k)
    bolge = lambda p: (p[0] * k, p[1] * k)
    h = 0.12 * k
    ic_blok = {"duvar": "KLIMA_IU_DUVAR", "kaset1": "KLIMA_IU_DUVAR", "salon": "KLIMA_IU_SALON",
               "kaset4": "KLIMA_IU_KASET", "kanal": "KLIMA_IU_KANAL"}

    for u in ic["ic_uniteler"]:
        x, y = bolge(u["konum"])
        rot = u.get("aci", 0) - 90  # blok +Y yönüne üfler
        a = math.radians(u.get("aci", 0))
        if u["tip"] in es:
            # sarmal kütüphane bloğu merkezlidir: duvar tipleri duvardan derinliğin yarısı kadar içeri
            ad, der = es[u["tip"]]
            if u["tip"] in ("duvar", "kaset1", "salon"):
                x += math.cos(a) * der / 2
                y += math.sin(a) * der / 2
            elif u["tip"] == "kaset4":
                rot = 0
        else:
            ad = ic_blok.get(u["tip"], "KLIMA_IU_DUVAR")
            # dahili bloklarda taban (y=0) duvar hattındadır; kaset/kanal için merkeze kaydır
            if u["tip"] == "kaset4":
                y -= 0.475 * k
                rot = 0
            elif u["tip"] == "kanal":
                x -= math.cos(a) * 0.35 * k
                y -= math.sin(a) * 0.35 * k
        msp.add_blockref(ad, (x, y), dxfattribs={"layer": "KLIMA-IC", "rotation": rot})
        tx, ty = bolge(u["konum"])
        msp.add_text(f"{u['id']} {u['tip'].upper()} {u['kw']} kW ({u['btu']} BTU)", height=h,
                     dxfattribs={"layer": "KLIMA-YAZI", "insert": (tx + 0.2 * k, ty + 0.3 * k)})

    for s in opt["sistemler"]:
        sec = s["secilen"]
        du = sec["du_konum"]
        x, y = bolge(du["konum"])
        du_kw = float((sec["hesap"].get("du") or {}).get("kw") or 0)
        if s["tip"] == "split":
            tip_du = "du_split"
        else:
            tip_du = "du_vrf_buyuk" if (du_kw > es.get("_du_buyuk_kw", 28.0) and "du_vrf_buyuk" in es) else "du_vrf"
        if tip_du in es:
            ad = es[tip_du][0]  # merkezli: konum = DÜ ayak izi merkezi
        else:
            ad = "KLIMA_DU"
            a = math.radians(du.get("aci", 0) - 90)
            x -= (math.cos(a) * 0.0 - math.sin(a) * 0.4) * k
            y -= (math.sin(a) * 0.0 + math.cos(a) * 0.4) * k
        msp.add_blockref(ad, (x, y), dxfattribs={"layer": "KLIMA-DIS", "rotation": du.get("aci", 0) - 90})
        model = (sec["hesap"].get("du") or {}).get("model", "?")
        dkw = (sec["hesap"].get("du") or {}).get("kw", "?")
        tx, ty = bolge(du["konum"])
        kot = float(du_kot_m or 0)
        yer = f" - CATIDA (kot +{kot:g} m), DUSEY HAT BURADAN" if kot >= 2 else (f" (kot {kot:+g} m)" if kot else "")
        msp.add_text(f"{s['id']} DU {model} {dkw} kW{yer}", height=h * 1.2,
                     dxfattribs={"layer": "KLIMA-YAZI", "insert": (tx + 0.3 * k, ty - 0.6 * k)})
        for seg in sec["hesap"]["segmentler"]:
            pts = [bolge(p) for p in seg["noktalar"]]
            if len(pts) < 2:
                continue
            ofs = 0.05 * k
            msp.add_lwpolyline(pts, dxfattribs={"layer": "KLIMA-BORU-GAZ"})
            msp.add_lwpolyline([(p[0] + ofs, p[1] + ofs) for p in pts], dxfattribs={"layer": "KLIMA-BORU-SIVI"})
            m = pts[len(pts) // 2]
            msp.add_text(f"{seg['id']} {seg.get('sivi')}/{seg.get('gaz')} L={seg['uzunluk_m']}m", height=h * 0.8,
                         dxfattribs={"layer": "KLIMA-YAZI", "insert": (m[0] + 0.1 * k, m[1] + 0.1 * k)})
        for yb in sec["hesap"].get("y_branch", []):
            x, y = bolge(yb["konum"])
            msp.add_blockref(es["ybranch"][0] if "ybranch" in es else "KLIMA_YBRANCH", (x, y), dxfattribs={"layer": "KLIMA-YBRANCH"})
            msp.add_text(f"{yb['ad']} {yb['model']}", height=h * 0.8,
                         dxfattribs={"layer": "KLIMA-YAZI", "insert": (x + 0.15 * k, y - 0.25 * k)})
    Path(cikti_dxf).parent.mkdir(parents=True, exist_ok=True)
    doc.saveas(cikti_dxf)
    return cikti_dxf
