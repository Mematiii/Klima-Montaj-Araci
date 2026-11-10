"""DXF'ten mimari geometriyi çıkarır: katman sınıflandırma, blok nesneleri, metinler, çizim adaları.

Çıktı plan.json (tüm koordinatlar METRE):
{
  "kaynak": "...dxf", "olcek": 0.01, "birim_tahmini": "cm",
  "katmanlar": {ad: {"adet": n, "kategori": "duvar", "kaynak": "otomatik|kullanici"}},
  "cizgiler": {kategori: [{"p": [[x,y],...], "k": bool, "l": katman}]},
  "nesneler": [{"kategori", "ad", "katman", "poligon", "merkez", "aci"}],
  "metinler": [{"t", "x", "y", "h", "l"}],
  "adalar": [{"id", "bbox", "baslik", "alan"}]
}
"""
from __future__ import annotations

import math
from collections import Counter, defaultdict
from pathlib import Path

import ezdxf
from ezdxf import path as ezpath
from shapely.geometry import MultiPoint, box
from shapely.ops import unary_union

from ortak import anahtar_eslesir, normalize, veri

SOZLUK = veri("katman_sozlugu.json")
NESNE_KATEGORILERI = {"pencere", "kapi", "kolon", "merdiven", "mobilya", "klima"}
MAX_DERINLIK = 8


def katman_kategorisi(ad: str, duzeltme: dict | None = None) -> str:
    if duzeltme and ad in duzeltme:
        return duzeltme[ad]
    n = normalize(ad)
    for kat in SOZLUK["sira"]:
        for a in SOZLUK["kategoriler"][kat]:
            if anahtar_eslesir(n, a):
                return kat
    return "diger"


def blok_kategorisi(ad: str) -> str | None:
    n = normalize(ad)
    if n.startswith("*"):  # anonim bloklar (dinamik bloklar *U..)
        return None
    for kat in ["pencere", "kapi", "kolon", "merdiven", "mobilya"]:
        for a in SOZLUK["blok_anahtar"][kat]:
            if anahtar_eslesir(n, a):
                return kat
    return None


def _efektif_blok_adi(ins) -> str:
    """Dinamik bloklarda (*U12) asıl blok adını bulmaya çalışır."""
    ad = ins.dxf.name
    if ad.startswith("*"):
        try:
            br = ins.block()
            if br is not None:
                # dinamik blok -> AcDbDynamicBlockReference / BLOCKRECORD xdata
                rec = br.block_record
                if rec is not None and rec.has_xdata("AcDbBlockRepBTag"):
                    h = rec.get_xdata("AcDbBlockRepBTag")
                    for code, val in h:
                        if code == 1005:
                            ana = ins.doc.entitydb.get(val)
                            if ana is not None and hasattr(ana.dxf, "name"):
                                return ana.dxf.name
        except Exception:
            pass
    return ad


class Cikarici:
    def __init__(self, doc, olcek: float, duzeltme: dict | None):
        self.doc = doc
        self.s = olcek
        self.duzeltme = duzeltme or {}
        self.kat_cache: dict[str, str] = {}
        self.katman_sayac = Counter()
        self.cizgiler = defaultdict(list)
        self.nesneler = []
        self.metinler = []
        self.blok_sayac = Counter()

    def kat(self, layer: str) -> str:
        if layer not in self.kat_cache:
            self.kat_cache[layer] = katman_kategorisi(layer, self.duzeltme)
        return self.kat_cache[layer]

    def pt(self, v):
        return [round(v[0] * self.s, 4), round(v[1] * self.s, 4)]

    def isle(self, entities, ust_katman: str | None = None, derinlik: int = 0):
        for e in entities:
            try:
                self._isle_tek(e, ust_katman, derinlik)
            except Exception:
                continue

    def _isle_tek(self, e, ust_katman, derinlik):
        tip = e.dxftype()
        layer = e.dxf.get("layer", "0")
        if layer == "0" and ust_katman:
            layer = ust_katman
        self.katman_sayac[layer] += 1
        kat = self.kat(layer)

        if tip in ("TEXT", "MTEXT", "ATTRIB"):
            if tip == "MTEXT":
                t = e.plain_text()
                h = e.dxf.get("char_height", 0)
            else:
                t = e.dxf.get("text", "")
                h = e.dxf.get("height", 0)
            t = (t or "").strip()
            if t:
                p = e.dxf.insert
                self.metinler.append({"t": t, "x": round(p[0] * self.s, 3), "y": round(p[1] * self.s, 3),
                                      "h": round(h * self.s, 3), "l": layer})
            return

        if tip == "INSERT":
            ad = _efektif_blok_adi(e)
            self.blok_sayac[ad] += 1
            for a in getattr(e, "attribs", []):
                self._isle_tek(a, layer, derinlik)
            bkat = blok_kategorisi(ad)
            nkat = bkat or (kat if kat in NESNE_KATEGORILERI else None)
            if nkat and derinlik < MAX_DERINLIK:
                noktalar = []
                for ve in e.virtual_entities():
                    if ve.dxftype() in ("TEXT", "MTEXT", "ATTRIB", "ATTDEF"):
                        continue
                    noktalar.extend(self._noktalar(ve))
                if len(noktalar) >= 2:
                    mrr = MultiPoint(noktalar).minimum_rotated_rectangle
                    if mrr.geom_type == "Polygon":
                        poly = [[round(x, 4), round(y, 4)] for x, y in list(mrr.exterior.coords)[:-1]]
                    else:
                        poly = [[round(x, 4), round(y, 4)] for x, y in mrr.coords]
                    c = mrr.centroid
                    self.nesneler.append({"kategori": nkat, "ad": ad, "katman": layer, "poligon": poly,
                                          "merkez": [round(c.x, 4), round(c.y, 4)],
                                          "aci": round(e.dxf.get("rotation", 0.0), 2)})
                return
            if derinlik < MAX_DERINLIK:
                self.isle(e.virtual_entities(), layer, derinlik + 1)
            return

        if kat in ("yok_say",) or tip in ("DIMENSION", "LEADER", "MLEADER", "VIEWPORT", "POINT", "IMAGE", "WIPEOUT", "OLE2FRAME"):
            return

        if tip == "HATCH":
            if kat in ("kolon", "duvar", "merdiven", "yol"):
                try:
                    for p in ezpath.from_hatch(e):
                        pts = [self.pt(v) for v in p.flattening(0.5 / max(self.s, 1e-9) * 0.01)]
                        if len(pts) >= 3:
                            self.cizgiler[kat].append({"p": pts, "k": True, "l": layer, "hatch": True})
                except Exception:
                    pass
            return

        if tip == "ARC" and kat not in ("mobilya", "merdiven", "kapi"):
            # kapı katmanı/bloğu olmayan planlarda kapı kanadı yayı: ~90°, yarıçap 0,6-1,3 m -> kapı nesnesi
            try:
                r = e.dxf.radius * self.s
                sweep = (e.dxf.end_angle - e.dxf.start_angle) % 360
                if 0.6 <= r <= 1.3 and 80 <= sweep <= 100:
                    c = e.dxf.center
                    a0, a1 = math.radians(e.dxf.start_angle), math.radians(e.dxf.end_angle)
                    cx, cy = c[0] * self.s, c[1] * self.s
                    sektor = [(cx, cy)] + [(cx + r * math.cos(a0 + (a1 - a0 if a1 > a0 else a1 + 2 * math.pi - a0) * t / 6),
                                            cy + r * math.sin(a0 + (a1 - a0 if a1 > a0 else a1 + 2 * math.pi - a0) * t / 6))
                                           for t in range(7)]
                    mrr = MultiPoint(sektor).minimum_rotated_rectangle
                    self.nesneler.append({"kategori": "kapi", "ad": "(yay)", "katman": layer,
                                          "poligon": [[round(x, 4), round(y, 4)] for x, y in list(mrr.exterior.coords)[:-1]],
                                          "merkez": [round(mrr.centroid.x, 4), round(mrr.centroid.y, 4)], "aci": 0.0})
            except Exception:
                pass

        if tip == "LWPOLYLINE" and kat not in ("mobilya", "merdiven", "kapi"):
            # kapı kanadı yayı bazen bulge'lı polyline olarak çizilir (ör. Revit/IFC çıktıları)
            try:
                from ezdxf.math import bulge_to_arc
                v = [(x, y, b) for x, y, *_s, b in e.get_points("xyseb")]
                if len(v) <= 4:
                    for (xa, ya, b), (xb, yb, _b) in zip(v, v[1:] + ([v[0]] if e.closed else [])):
                        if not 0.36 <= abs(b) <= 0.47:
                            continue
                        c, a0, a1, r0 = bulge_to_arc((xa, ya), (xb, yb), b)
                        r = r0 * self.s
                        if not 0.6 <= r <= 1.3:
                            continue
                        cx, cy = c[0] * self.s, c[1] * self.s
                        sw = (a1 - a0) % (2 * math.pi)
                        sektor = [(cx, cy)] + [(cx + r * math.cos(a0 + sw * t / 6), cy + r * math.sin(a0 + sw * t / 6))
                                               for t in range(7)]
                        mrr = MultiPoint(sektor).minimum_rotated_rectangle
                        self.nesneler.append({"kategori": "kapi", "ad": "(yay)", "katman": layer,
                                              "poligon": [[round(x, 4), round(y, 4)] for x, y in list(mrr.exterior.coords)[:-1]],
                                              "merkez": [round(mrr.centroid.x, 4), round(mrr.centroid.y, 4)], "aci": 0.0})
                        break
            except Exception:
                pass

        if tip in ("LINE", "LWPOLYLINE", "POLYLINE", "ARC", "CIRCLE", "ELLIPSE", "SPLINE"):
            try:
                p = ezpath.make_path(e)
            except Exception:
                return
            tol = 0.02 / max(self.s, 1e-9)  # ~2 cm sapma
            pts = [self.pt(v) for v in p.flattening(tol)]
            if len(pts) < 2:
                return
            kapali = bool(getattr(e, "closed", False)) or tip == "CIRCLE" or (
                len(pts) > 2 and abs(pts[0][0] - pts[-1][0]) < 1e-4 and abs(pts[0][1] - pts[-1][1]) < 1e-4)
            self.cizgiler[kat].append({"p": pts, "k": kapali, "l": layer})

    def _noktalar(self, e):
        tip = e.dxftype()
        if tip == "INSERT":
            out = []
            for ve in e.virtual_entities():
                out.extend(self._noktalar(ve))
            return out
        try:
            p = ezpath.make_path(e)
            return [(v[0] * self.s, v[1] * self.s) for v in p.flattening(0.05 / max(self.s, 1e-9))]
        except Exception:
            return []


def _yazi_olcek(doc) -> float | None:
    """Metin yüksekliği medyanından birim: plan yazıları gerçekte ~10-40 cm boyundadır."""
    hs = []
    for t in doc.modelspace().query("TEXT MTEXT"):
        try:
            h = t.dxf.height if t.dxftype() == "TEXT" else t.dxf.char_height
        except Exception:
            continue
        if h and h > 0:
            hs.append(h)
        if len(hs) > 5000:
            break
    if len(hs) < 10:
        return None
    med = sorted(hs)[len(hs) // 2]
    if 0.04 <= med <= 0.8:
        return 1.0
    if 4 <= med <= 80:
        return 0.01
    if 40 <= med <= 800:
        return 0.001
    return None


def olcek_tahmin(doc, cizgi_uzunluklari: list[float]) -> tuple[float, str]:
    """Çizim birimini tahmin eder: $INSUNITS ve metin yüksekliği uyuşuyorsa onlar, yoksa çizgi uzunlukları.

    Not: Çizgi uzunluğu medyanı tek başına güvenilmez (parçalı duvarlar, profil detayları, LATS sembolleri).
    """
    ins = doc.header.get("$INSUNITS", 0)
    ins_olcek = {1: 0.0254, 2: 0.3048, 4: 0.001, 5: 0.01, 6: 1.0}.get(ins)
    ad = {0.001: "mm", 0.01: "cm", 1.0: "m", 0.0254: "inch", 0.3048: "ft"}
    yazi = _yazi_olcek(doc)
    if ins_olcek and yazi and abs(math.log10(ins_olcek) - math.log10(yazi)) < 0.5:
        return ins_olcek, ad[ins_olcek]
    if yazi:
        return yazi, ad[yazi] + " (yazı boyundan)"
    if ins_olcek in (0.001, 0.01, 1.0):
        return ins_olcek, ad[ins_olcek] + " ($INSUNITS)"
    if cizgi_uzunluklari:
        u = sorted(cizgi_uzunluklari)
        med = u[len(u) // 2]
        if med > 150:
            tahmin = (0.001, "mm")
        elif med > 12:
            tahmin = (0.01, "cm")
        else:
            tahmin = (1.0, "m")
        if ins_olcek and abs(math.log10(ins_olcek) - math.log10(tahmin[0])) < 0.5:
            return tahmin
        return tahmin
    if ins_olcek:
        return ins_olcek, {0.001: "mm", 0.01: "cm", 1.0: "m"}.get(ins_olcek, "?")
    return 0.01, "cm (varsayım)"


def _ham_uzunluklar(doc) -> list[float]:
    out = []
    msp = doc.modelspace()
    for e in msp.query("LINE LWPOLYLINE"):
        kat = katman_kategorisi(e.dxf.layer)
        if kat not in ("duvar", "diger"):
            continue
        try:
            if e.dxftype() == "LINE":
                out.append(math.dist(e.dxf.start[:2], e.dxf.end[:2]))
            else:
                pts = list(e.get_points("xy"))
                for a, b in zip(pts, pts[1:]):
                    out.append(math.dist(a, b))
        except Exception:
            pass
        if len(out) > 20000:
            break
    if len(out) < 50:  # plan bir blok içinde olabilir
        for e in msp.query("INSERT"):
            try:
                for ve in e.virtual_entities():
                    if ve.dxftype() == "LINE":
                        out.append(math.dist(ve.dxf.start[:2], ve.dxf.end[:2]))
            except Exception:
                pass
            if len(out) > 20000:
                break
    return [x for x in out if x > 0]


def adalari_bul(cizgiler: dict, nesneler: list, metinler: list) -> list[dict]:
    kutular = []
    # vaziyet/topoğrafya çizgileri (diger) küçük kat planlarını tek dev adaya yapıştırır; mimari katman yeterliyse onlar kullanılır
    mimari = sum(len(cizgiler.get(k, [])) for k in ("duvar", "kolon", "pencere"))
    kategoriler = ("duvar", "kolon", "pencere") if mimari >= 150 else ("duvar", "kolon", "pencere", "diger")
    for kat in kategoriler:
        for c in cizgiler.get(kat, []):
            xs = [p[0] for p in c["p"]]
            ys = [p[1] for p in c["p"]]
            kutular.append(box(min(xs), min(ys), max(xs) + 1e-3, max(ys) + 1e-3))
    for n in nesneler:
        if n["kategori"] in ("pencere", "kapi", "kolon"):
            xs = [p[0] for p in n["poligon"]]
            ys = [p[1] for p in n["poligon"]]
            kutular.append(box(min(xs), min(ys), max(xs) + 1e-3, max(ys) + 1e-3))
    if not kutular:
        return []
    birlesik = unary_union([k.buffer(1.5, join_style=2) for k in kutular])
    geoms = list(birlesik.geoms) if birlesik.geom_type == "MultiPolygon" else [birlesik]
    geoms = [g.buffer(-1.5, join_style=2) if g.buffer(-1.5).area > 0 else g for g in geoms]
    geoms.sort(key=lambda g: -g.area)
    adalar = []
    anahtar = ("PLAN", "KAT", "KESIT", "GORUNUS", "VAZIYET", "CATI", "BODRUM", "ZEMIN", "ASMA", "NORMAL")
    for i, g in enumerate(geoms):
        if g.area < 20:
            continue
        x0, y0, x1, y1 = g.bounds
        genis = box(x0 - 2, y0 - 8, x1 + 2, y1 + 2)
        adaylar = [m for m in metinler if genis.contains(_P(m)) and any(a in normalize(m["t"]) for a in anahtar)
                   and not any(k in normalize(m["t"]) for k in ("KLIMA", "BTU"))]  # "ASMA TAVAN TIPI KLIMA" başlık değil
        adaylar.sort(key=lambda m: -m["h"])
        tur = "plan"
        if adaylar and any(k in normalize(adaylar[0]["t"]) for k in ("KESIT", "GORUNUS", "SECTION")):
            tur = "kesit/gorunus"
        adalar.append({"id": len(adalar) + 1, "bbox": [round(v, 2) for v in (x0, y0, x1, y1)],
                       "baslik": adaylar[0]["t"] if adaylar else "", "tur": tur,
                       "alan": round(g.area, 1)})
    return adalar


def _P(m):
    from shapely.geometry import Point
    return Point(m["x"], m["y"])


def cikar(dxf_yolu: str | Path, olcek: float | None = None, katman_duzeltme: dict | None = None) -> dict:
    doc = ezdxf.readfile(str(dxf_yolu))
    if olcek is None:
        olcek, birim = olcek_tahmin(doc, _ham_uzunluklar(doc))
    else:
        birim = "kullanici"
    c = Cikarici(doc, olcek, katman_duzeltme)
    c.isle(doc.modelspace())
    katmanlar = {}
    for ad, n in c.katman_sayac.most_common():
        katmanlar[ad] = {"adet": n, "kategori": c.kat(ad),
                         "kaynak": "kullanici" if katman_duzeltme and ad in katman_duzeltme else "otomatik"}
    adalar = adalari_bul(c.cizgiler, c.nesneler, c.metinler)
    return {
        "kaynak": str(dxf_yolu),
        "olcek": olcek,
        "birim_tahmini": birim,
        "katmanlar": katmanlar,
        "bloklar": dict(c.blok_sayac.most_common(200)),
        "cizgiler": dict(c.cizgiler),
        "nesneler": c.nesneler,
        "metinler": c.metinler,
        "adalar": adalar,
    }
