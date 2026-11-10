"""İç ünitelerin oda içinde yerleştirilmesi.

Duvar / salon tipi: oda kenarlarında aday noktalar puanlanır.
  Kesin yasaklar: pencere ve kapı üstü/yanı, kolon yüzeyi, dolap önü, ocak üstü, odaya sığmama.
  Tercihler: hava uzun eksen boyunca atılsın, dış cepheye yakın (kısa boru + drenaj), kenar ortası, kapıdan uzak.
Kaset: oda alanı n eşit hücreye bölünür, hücre merkezine; kiriş ve duvara mesafe korunur.
Kanallı: koridora/çekirdeğe bakan duvarın iç yüzüne (asma tavan içi).
"""
from __future__ import annotations

import math

from shapely.geometry import LineString, Point, Polygon
from shapely.geometry.polygon import orient
from shapely.ops import unary_union

from ortak import normalize, veri

IC = veri("lg_multiv/ic_uniteler.json")
YASAK_MOBILYA = ("DOLAP", "GARDROP", "OCAK", "FIRIN", "BUZDOLABI", "WARDROBE", "STOVE")


def unite_olcu(tip: str, kw: float) -> tuple[float, float]:
    t = IC["tipler"].get(tip, IC["tipler"]["duvar"])
    gen = 0.9
    for k, v in sorted(((float(a), b) for a, b in t["genislik_m"].items())):
        gen = v
        if kw <= k:
            break
    der = t["derinlik_m"] or gen
    return gen, der


def _isin_uzunlugu(P: Polygon, p, n, maks=30.0) -> float:
    q = (p[0] + n[0] * maks, p[1] + n[1] * maks)
    hat = LineString([(p[0] + n[0] * 0.05, p[1] + n[1] * 0.05), q])
    kesisim = hat.intersection(P.exterior)
    if kesisim.is_empty:
        return maks
    return Point(p).distance(kesisim)


def _ana_eksen(P: Polygon) -> tuple[float, float, tuple[float, float]]:
    mrr = P.minimum_rotated_rectangle
    c = list(mrr.exterior.coords)
    k1 = math.dist(c[0], c[1])
    k2 = math.dist(c[1], c[2])
    if k1 >= k2:
        v = ((c[1][0] - c[0][0]) / k1, (c[1][1] - c[0][1]) / k1)
        return k1, k2, v
    v = ((c[2][0] - c[1][0]) / k2, (c[2][1] - c[1][1]) / k2)
    return k2, k1, v


def duvar_adaylari(oda: dict, gen: float, der: float, engeller: dict, kabuk: Polygon, mobilya: list,
                   adim: float = 0.2, pencere_bilinmiyor: bool = False) -> list[dict]:
    P = orient(Polygon(oda["poligon"]), 1.0)
    uzun, kisa, eksen = _ana_eksen(P)
    pencereler = [Polygon(p) for p in engeller["pencere"] if Polygon(p).distance(P) < 0.6]
    kapilar = [Polygon(p) for p in engeller["kapi"] if Polygon(p).distance(P) < 0.6]
    kolonlar = [Polygon(p) for p in engeller["kolon"] if Polygon(p).distance(P) < 0.3]
    kirisler = [Polygon(p) for p in engeller["kiris"] if Polygon(p).distance(P) < 0.3]
    yasak_mob = [m for m in mobilya if any(k in normalize(m["ad"]) for k in YASAK_MOBILYA) and m["geom"].distance(P) < 0.5]
    coords = list(P.exterior.coords)
    adaylar = []
    for a, b in zip(coords, coords[1:]):
        L = math.dist(a, b)
        if L < gen + 0.3:
            continue
        d = ((b[0] - a[0]) / L, (b[1] - a[1]) / L)
        n = (-d[1], d[0])  # CCW poligonda sol taraf = iç
        bas = gen / 2 + 0.15
        t = bas
        while t <= L - bas + 1e-6:
            p = (a[0] + d[0] * t, a[1] + d[1] * t)
            p1 = (p[0] - d[0] * (gen / 2 + 0.1), p[1] - d[1] * (gen / 2 + 0.1))
            p2 = (p[0] + d[0] * (gen / 2 + 0.1), p[1] + d[1] * (gen / 2 + 0.1))
            serit = LineString([p1, p2])
            ayak = Polygon([
                (p[0] - d[0] * gen / 2, p[1] - d[1] * gen / 2),
                (p[0] + d[0] * gen / 2, p[1] + d[1] * gen / 2),
                (p[0] + d[0] * gen / 2 + n[0] * der, p[1] + d[1] * gen / 2 + n[1] * der),
                (p[0] - d[0] * gen / 2 + n[0] * der, p[1] - d[1] * gen / 2 + n[1] * der),
            ])
            t += adim
            sebep = None
            if any(serit.distance(w) < 0.12 for w in pencereler):
                sebep = "pencere"
            elif any(serit.distance(k) < 0.25 for k in kapilar):
                sebep = "kapi"
            elif any(serit.distance(k) < 0.05 for k in kolonlar):
                sebep = "kolon"
            elif any(ayak.distance(k) < 0.1 for k in kirisler):
                sebep = "kiriş altı"
            elif not P.buffer(0.02).contains(ayak):
                sebep = "sigmiyor"
            elif any(ayak.buffer(0.5).intersects(m["geom"]) for m in yasak_mob):
                sebep = "dolap/ocak"
            if sebep:
                continue
            isin = _isin_uzunlugu(P, p, n)
            hiza = abs(n[0] * eksen[0] + n[1] * eksen[1])  # 1: uzun eksen boyunca üflüyor
            c_isin = 1 - min(isin / max(uzun, 0.1), 1.0)
            c_hiza = 1 - hiza
            dcephe = Point(p).distance(kabuk.exterior)
            c_boru = min(dcephe / 8.0, 1.0)
            c_orta = abs((t - adim) / L - 0.5)
            dkapi = min((Point(p).distance(k) for k in kapilar), default=9)
            c_kapi = 0.3 if dkapi < 0.8 else 0.0
            # pencereler planda ayırt edilemiyorsa dış cephe duvarı pencere olabilir: iç duvarı tercih et
            # dış duvar mı: duvarın 0,9 m arkası bina dışındaysa (kalın dış duvar + cam payı dahil)
            # (dış kapı rüzgarlığı/çıkıntı kabuğu genişletebilir: kabuğa 0,9 m'den yakınlık da dış duvar sayılır)
            dis_duvar = (not kabuk.contains(Point(p[0] - n[0] * 0.9, p[1] - n[1] * 0.9))) or dcephe < 0.9
            c_pen = 2.0 if (pencere_bilinmiyor and dis_duvar) else 0.0
            skor = 1.0 * c_isin + 0.6 * c_hiza + 0.8 * c_boru + 0.25 * c_orta + c_kapi + c_pen
            adaylar.append({
                "konum": [round(p[0], 3), round(p[1], 3)],
                "aci": round(math.degrees(math.atan2(n[1], n[0])), 1),
                "poligon": [[round(x, 3), round(y, 3)] for x, y in ayak.exterior.coords[:-1]],
                "baglanti": [round(p[0] + n[0] * 0.1, 3), round(p[1] + n[1] * 0.1, 3)],
                "skor": round(skor, 3),
                "gerekce": f"atış {isin:.1f} m, cepheye {dcephe:.1f} m, {'uzun eksen' if hiza > 0.7 else 'kısa eksen'}"
                           + (" - DIŞ DUVAR: pencere yok mu sahada kontrol" if c_pen else ""),
            })
    adaylar.sort(key=lambda x: x["skor"])
    return adaylar


def kaset_konumlari(oda: dict, n: int, gen: float, engeller: dict) -> list[dict]:
    P = Polygon(oda["poligon"])
    uzun, kisa, eksen = _ana_eksen(P)
    kirisler = [Polygon(p) for p in engeller["kiris"] if Polygon(p).distance(P) < 1]
    ic_bolge = P.buffer(-(gen / 2 + 0.6))
    if ic_bolge.is_empty:
        ic_bolge = P.buffer(-gen / 2)
    c = P.centroid
    out = []
    for i in range(n):
        off = (i + 0.5) / n - 0.5
        hedef = (c.x + eksen[0] * off * uzun, c.y + eksen[1] * off * uzun)
        en_iyi = None
        for r in [x * 0.2 for x in range(0, 15)]:
            for k in range(max(1, int(r * 20))):
                aci = 2 * math.pi * k / max(1, int(r * 20))
                q = Point(hedef[0] + r * math.cos(aci), hedef[1] + r * math.sin(aci))
                kare = q.buffer(gen / 2, cap_style=3)
                if not ic_bolge.contains(q) or any(kare.distance(b) < 0.3 for b in kirisler):
                    continue
                en_iyi = q
                break
            if en_iyi:
                break
        if en_iyi is None:
            en_iyi = P.representative_point()
        kare = en_iyi.buffer(gen / 2, cap_style=3)
        out.append({"konum": [round(en_iyi.x, 3), round(en_iyi.y, 3)], "aci": 0.0,
                    "poligon": [[round(x, 3), round(y, 3)] for x, y in kare.exterior.coords[:-1]],
                    "baglanti": [round(en_iyi.x, 3), round(en_iyi.y, 3)], "skor": 0,
                    "gerekce": "oda hücre merkezi, kiriş ve duvardan uzak"})
    return out


def kanal_konumu(oda: dict, gen: float, der: float, analiz: dict) -> dict:
    """Kanallı ünite: koridor/hol ile ortak duvara yakın (menfezler odaya, cihaz asma tavanda)."""
    P = orient(Polygon(oda["poligon"]), 1.0)
    hol = [Polygon(o["poligon"]) for o in analiz["odalar"] if o["tip"] == "hol"]
    coords = list(P.exterior.coords)
    en_iyi, ed = None, 1e9
    for a, b in zip(coords, coords[1:]):
        L = math.dist(a, b)
        if L < gen + 0.2:
            continue
        m = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
        d = min((Point(m).distance(h) for h in hol), default=5)
        if d < ed:
            ed, en_iyi = d, (a, b, L)
    if en_iyi is None:
        c = P.representative_point()
        return {"konum": [c.x, c.y], "aci": 0, "poligon": [], "baglanti": [c.x, c.y], "skor": 0, "gerekce": "uygun kenar yok"}
    a, b, L = en_iyi
    d = ((b[0] - a[0]) / L, (b[1] - a[1]) / L)
    n = (-d[1], d[0])
    m = ((a[0] + b[0]) / 2 + n[0] * (der / 2 + 0.1), (a[1] + b[1]) / 2 + n[1] * (der / 2 + 0.1))
    ayak = Polygon([(m[0] + s1 * d[0] * gen / 2 + s2 * n[0] * der / 2, m[1] + s1 * d[1] * gen / 2 + s2 * n[1] * der / 2)
                    for s1, s2 in ((-1, -1), (1, -1), (1, 1), (-1, 1))])
    return {"konum": [round(m[0], 3), round(m[1], 3)], "aci": round(math.degrees(math.atan2(n[1], n[0])), 1),
            "poligon": [[round(x, 3), round(y, 3)] for x, y in ayak.exterior.coords[:-1]],
            "baglanti": [round(m[0], 3), round(m[1], 3)], "skor": 0,
            "gerekce": "koridora bakan duvar, asma tavan içi (menfez/kanal ayrıca projelendirilmeli)"}


def yerlestir(analiz: dict, yuk: dict, plan: dict, elle: dict | None = None) -> dict:
    elle = elle or {}
    from shapely.geometry import Polygon as _P
    kabuk = _P(analiz["bina_kabugu"])
    mobilya = [{"ad": n["ad"], "geom": _P(n["poligon"]) if len(n["poligon"]) >= 3 else Point(n["merkez"]).buffer(0.3)}
               for n in plan.get("nesneler", []) if n["kategori"] == "mobilya"]
    odalar = {o["id"]: o for o in analiz["odalar"]}
    sonuc, uyarilar = [], []
    for yo in yuk["odalar"]:
        oda = odalar[yo["id"]]
        uniteler = yo["uniteler"]
        tip = uniteler[0]["tip"]
        gen, der = unite_olcu(tip, uniteler[0]["kw"])
        if tip in ("duvar", "salon", "kaset1"):
            adaylar = duvar_adaylari(oda, gen, der, analiz["engeller"], kabuk, mobilya,
                                     pencere_bilinmiyor=analiz.get("pencere_bilinmiyor", False))
            secilen = []
            uzun = _ana_eksen(Polygon(oda["poligon"]))[0]
            for a in adaylar:
                if len(secilen) == len(uniteler):
                    break
                if all(math.dist(a["konum"], s["konum"]) >= max(2.5, uzun / (len(uniteler) + 0.5)) for s in secilen):
                    secilen.append(a)
            if len(secilen) < len(uniteler):
                uyarilar.append(f"{oda['id']} {oda['ad']}: {tip} için yeterli uygun duvar yok "
                                f"({len(secilen)}/{len(uniteler)}); kaset/kanallı ya da elle konum gerekli.")
                while len(secilen) < len(uniteler):
                    c = Polygon(oda["poligon"]).representative_point()
                    secilen.append({"konum": [c.x, c.y], "aci": 0, "poligon": [], "baglanti": [c.x, c.y],
                                    "skor": 99, "gerekce": "UYGUN DUVAR YOK - elle düzeltilmeli"})
            alternatifler = [a for a in adaylar if a not in secilen][:3]
        elif tip == "kanal":
            secilen = [kanal_konumu(oda, gen, der, analiz) for _ in uniteler]
            alternatifler = []
        else:
            secilen = kaset_konumlari(oda, len(uniteler), gen, analiz["engeller"])
            alternatifler = []
        for u, k in zip(uniteler, secilen):
            kayit = dict(u)
            kayit.update(k)
            kayit["oda_ad"] = oda["ad"]
            if u["id"] in elle:
                e = elle[u["id"]]
                kayit["konum"] = e["konum"]
                kayit["baglanti"] = e.get("baglanti", e["konum"])
                kayit["aci"] = e.get("aci", kayit["aci"])
                kayit["poligon"] = e.get("poligon", [])
                kayit["gerekce"] = "kullanıcı konumu"
            kayit["alternatifler"] = [{"konum": a["konum"], "aci": a["aci"], "skor": a["skor"], "gerekce": a["gerekce"]}
                                      for a in alternatifler]
            sonuc.append(kayit)
    return {"ic_uniteler": sonuc, "uyarilar": uyarilar}
