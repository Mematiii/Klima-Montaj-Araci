"""Kontrol noktası önizlemeleri (PNG)."""
from __future__ import annotations

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Polygon as MPoly
from shapely.geometry import shape

TIP_RENK = {"salon": "#ffd59e", "yatak": "#c9e4ff", "mutfak": "#ffe9a8", "calisma": "#d6f5d6", "toplanti": "#d6f5d6",
            "magaza": "#f7c6d9", "kafe": "#f7c6d9", "ortak": "#e6d5f7", "hol": "#eeeeee", "islak": "#c8f0f0",
            "depo": "#dddddd", "giyinme": "#e8e8e8", "merdiven": "#cccccc", "balkon": "#d9f2c4", "teras": "#d9f2c4",
            "bilinmiyor": "#ff9d9d"}
CAP_RENK = {12.7: "#2a9d8f", 15.88: "#457b9d", 19.05: "#1d3557", 22.2: "#6a4c93", 28.58: "#e76f51", 34.9: "#d62828", 41.3: "#9d0208"}


def _poly(ax, pts, **kw):
    if len(pts) >= 3:
        ax.add_patch(MPoly(pts, closed=True, **kw))


def _taban(ax, analiz, oda_etiket=True):
    kutle = shape(analiz["duvar_kutlesi"])
    geoms = list(kutle.geoms) if kutle.geom_type == "MultiPolygon" else [kutle]
    for o in analiz["odalar"]:
        _poly(ax, o["poligon"], facecolor=TIP_RENK.get(o["tip"], "#f2f2f2"), edgecolor="none", alpha=0.8)
        if oda_etiket:
            xs = [p[0] for p in o["poligon"]]
            ys = [p[1] for p in o["poligon"]]
            ax.text(sum(xs) / len(xs), sum(ys) / len(ys), f"{o['id']}\n{o['ad'][:18]}\n{o['alan_m2']:.1f} m²",
                    ha="center", va="center", fontsize=6, color="#333")
    from matplotlib.patches import PathPatch
    from matplotlib.path import Path as MPath
    for g in geoms:
        if g.geom_type == "Polygon":
            from shapely.geometry.polygon import orient
            g = orient(g, 1.0)
            yollar =[MPath(list(g.exterior.coords))] + [MPath(list(i.coords)) for i in g.interiors]
            ax.add_patch(PathPatch(MPath.make_compound_path(*yollar), facecolor="#555", edgecolor="#333", lw=0.3))
    e = analiz["engeller"]
    for p in e["pencere"]:
        _poly(ax, p, facecolor="#4cc9f0", edgecolor="#0077b6", lw=0.4)
    for p in e["kapi"]:
        _poly(ax, p, facecolor="none", edgecolor="#f77f00", lw=0.6)
    for p in e["kolon"]:
        _poly(ax, p, facecolor="black", edgecolor="black", lw=0.3)
    for p in e["kiris"]:
        _poly(ax, p, facecolor="none", edgecolor="#8d0801", lw=0.6, ls="--")
    for p in e["merdiven"]:
        _poly(ax, p, facecolor="none", edgecolor="#6c757d", lw=0.5, hatch="///")
    for d in analiz["dis_alanlar"]:
        if "poligon" in d:
            _poly(ax, d["poligon"], facecolor="#adb5bd" if d["tip"] == "yol" else "#b7e4c7", alpha=0.5, edgecolor="none")
        elif "nokta" in d:
            ax.text(d["nokta"][0], d["nokta"][1], d.get("ad", d["tip"]), fontsize=6, color="#2d6a4f")
    if analiz.get("parsel"):
        _poly(ax, analiz["parsel"], facecolor="none", edgecolor="#e63946", lw=0.8, ls="-.")
    # görünüm binaya odaklansın (geniş parsel/vaziyet çizgileri planı okunmaz hale getirmesin)
    kx = [p[0] for p in analiz["bina_kabugu"]]
    ky = [p[1] for p in analiz["bina_kabugu"]]
    ax._klima_kutu = (min(kx) - 4, min(ky) - 4, max(kx) + 4, max(ky) + 4)


def _iu(ax, ic):
    for u in ic:
        if u.get("poligon"):
            _poly(ax, u["poligon"], facecolor="#0096c7", edgecolor="#023e8a", lw=0.8)
        x, y = u["konum"]
        ax.plot(x, y, "o", ms=3, color="#023e8a")
        ax.text(x, y, f" {u['id']} {u['tip']} {u['kw']}kW", fontsize=6, color="#023e8a", fontweight="bold")


def _bitir(fig, ax, yol, baslik):
    ax.set_aspect("equal")
    ax.autoscale_view()
    kutu = getattr(ax, "_klima_kutu", None)
    if kutu:
        x0, x1 = ax.get_xlim()
        y0, y1 = ax.get_ylim()
        ax.set_xlim(max(x0, kutu[0]), min(x1, kutu[2]))
        ax.set_ylim(max(y0, kutu[1]), min(y1, kutu[3]))
    ax.set_title(baslik, fontsize=10)
    ax.tick_params(labelsize=6)
    fig.tight_layout()
    fig.savefig(yol, dpi=170)
    plt.close(fig)
    return str(yol)


def _fig(analiz):
    import numpy as np
    xs = [p[0] for p in analiz["bina_kabugu"]]
    ys = [p[1] for p in analiz["bina_kabugu"]]
    w, h = max(xs) - min(xs), max(ys) - min(ys)
    oran = h / w if w else 1
    fig, ax = plt.subplots(figsize=(12, max(5, min(16, 12 * oran))))
    return fig, ax


def odalar(analiz, yol):
    fig, ax = _fig(analiz)
    _taban(ax, analiz)
    return _bitir(fig, ax, yol, "Kontrol 1 - Odalar (kırmızı: tipi belirsiz) / pencere mavi, kapı turuncu, kolon siyah, kiriş kesikli")


def ic_uniteler(analiz, ic, yol):
    fig, ax = _fig(analiz)
    _taban(ax, analiz)
    _iu(ax, ic["ic_uniteler"])
    for u in ic["ic_uniteler"]:
        for i, a in enumerate(u.get("alternatifler", [])[:2]):
            ax.plot(a["konum"][0], a["konum"][1], "x", ms=4, color="#adb5bd")
    return _bitir(fig, ax, yol, "Kontrol 2 - İç ünite yerleşimi (gri x: alternatif konumlar)")


def dis_uniteler(analiz, ic, dis, yol):
    fig, ax = _fig(analiz)
    _taban(ax, analiz, oda_etiket=False)
    _iu(ax, ic["ic_uniteler"])
    renk = ["#d00000", "#e85d04", "#faa307"]
    for s in dis["sistemler"]:
        for i, a in enumerate(s.get("adaylar", [])):
            if a.get("poligon"):
                _poly(ax, a["poligon"], facecolor=renk[min(i, 2)], edgecolor="black", lw=0.5, alpha=0.9)
            ax.text(a["konum"][0], a["konum"][1], f" {s['id']}-{i + 1} ({a['tur']}, ~{a.get('tahmini_boru_m') or '?'} m)",
                    fontsize=6, color=renk[min(i, 2)], fontweight="bold")
    return _bitir(fig, ax, yol, "Kontrol 3 - Dış ünite adayları (1 = önerilen)")


def borulama(analiz, ic, opt, yol):
    fig, ax = _fig(analiz)
    _taban(ax, analiz, oda_etiket=False)
    _iu(ax, ic["ic_uniteler"])
    for s in opt["sistemler"]:
        sec = s["secilen"]
        du = sec["du_konum"]
        if du.get("poligon"):
            _poly(ax, du["poligon"], facecolor="#d00000", edgecolor="black", lw=0.6)
        m = (sec["hesap"].get("du") or {}).get("model", "")
        ax.text(du["konum"][0], du["konum"][1], f" {s['id']} DÜ {m}", fontsize=7, color="#d00000", fontweight="bold")
        for seg in sec["hesap"]["segmentler"]:
            xs = [p[0] for p in seg["noktalar"]]
            ys = [p[1] for p in seg["noktalar"]]
            ax.plot(xs, ys, "-", lw=1.6, color=CAP_RENK.get(seg.get("gaz"), "#000"))
            mid = seg["noktalar"][len(seg["noktalar"]) // 2]
            ax.text(mid[0], mid[1], f"{seg['id']} {seg.get('sivi')}/{seg.get('gaz')} {seg['uzunluk_m']}m", fontsize=5, color="#222")
        for y in sec["hesap"].get("y_branch", []):
            ax.plot(y["konum"][0], y["konum"][1], "D", ms=4, color="#ff006e")
            ax.text(y["konum"][0], y["konum"][1], f" {y['ad']}", fontsize=6, color="#ff006e")
    return _bitir(fig, ax, yol, "Kontrol 4 - Borulama (renk = gaz hattı çapı, pembe = Y-branch)")


def adalar(plan, yol):
    fig, ax = plt.subplots(figsize=(12, 8))
    for kat, renk in (("duvar", "#333"), ("diger", "#bbb"), ("kolon", "black"), ("pencere", "#00b4d8")):
        for c in plan["cizgiler"].get(kat, [])[:60000]:
            xs = [p[0] for p in c["p"]]
            ys = [p[1] for p in c["p"]]
            ax.plot(xs, ys, "-", lw=0.3, color=renk)
    for a in plan["adalar"]:
        x0, y0, x1, y1 = a["bbox"]
        ax.add_patch(MPoly([(x0, y0), (x1, y0), (x1, y1), (x0, y1)], fill=False, edgecolor="red", lw=1))
        ax.text(x0, y1, f"ADA {a['id']}: {a['baslik'][:30]}", fontsize=8, color="red", va="bottom")
    ax.set_aspect("equal")
    ax.set_title("Çizim adaları - hangi kat planı çalışılacak?", fontsize=10)
    fig.tight_layout()
    fig.savefig(yol, dpi=150)
    plt.close(fig)
    return str(yol)
