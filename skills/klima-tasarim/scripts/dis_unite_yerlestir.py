"""Dış ünite aday konumları ve sistem gruplaması.

Adaylar: balkon/teras/çatı alanları, bina cephesi (dış duvar boyu), bahçe/boş alan metinleri.
Yasaklar: yol/otopark, kapı önü (kaçış yolu), merdiven, parsel dışı, bina kütlesi içi.
Puan: tahmini boru uzunluğu (Manhattan MST) + konum tipi cezası (eşdeğer metre).
"""
from __future__ import annotations

import math

from shapely.geometry import LineString, Point, Polygon
from shapely.geometry.polygon import orient
from shapely.ops import unary_union

from ortak import veri

DIS = veri("lg_multiv/dis_uniteler.json")
TIP_CEZA_M = {"balkon": 0.0, "teras": 0.0, "bahce": 2.0, "cephe": 5.0, "elle": 0.0}
DU_OLCU = {"vrf": (1.0, 0.8), "multi": (0.87, 0.34), "split": (0.8, 0.3)}


def _manhattan(a, b):
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


def mst_uzunluk(noktalar: list) -> float:
    if len(noktalar) < 2:
        return 0.0
    icinde = {0}
    dist = {i: _manhattan(noktalar[0], noktalar[i]) for i in range(1, len(noktalar))}
    toplam = 0.0
    while dist:
        j = min(dist, key=dist.get)
        toplam += dist.pop(j)
        icinde.add(j)
        for k in dist:
            dist[k] = min(dist[k], _manhattan(noktalar[j], noktalar[k]))
    return toplam


def aday_noktalar(analiz: dict, olcu=(1.0, 0.8), adim: float = 0.5) -> list[dict]:
    kabuk = orient(Polygon(analiz["bina_kabugu"]), 1.0)
    odalar = analiz["odalar"]
    eng = analiz["engeller"]
    kapilar = [Polygon(p) for p in eng["kapi"]]
    merdiven = [Polygon(p) for p in eng["merdiven"]]
    yollar = [Polygon(d["poligon"]) for d in analiz["dis_alanlar"] if d.get("tip") == "yol" and "poligon" in d]
    yol_noktalari = [Point(d["nokta"]) for d in analiz["dis_alanlar"] if d.get("tip") == "yol" and "nokta" in d]
    parsel = Polygon(analiz["parsel"]) if analiz.get("parsel") else None
    ic_odalar = unary_union([Polygon(o["poligon"]) for o in odalar if o["tip"] not in ("balkon", "teras")])
    g, d = olcu
    adaylar = []

    def kontrol(p: Point, ayak: Polygon, tur: str) -> str | None:
        if any(ayak.distance(k) < (1.0 if tur == "balkon" else 1.5) for k in kapilar):
            return "kapı önü"
        if any(ayak.distance(m) < 1.0 for m in merdiven):
            return "merdiven"
        if any(ayak.intersects(y.buffer(0.5)) for y in yollar) or any(p.distance(y) < 3.0 for y in yol_noktalari):
            return "yol"
        if parsel is not None and not parsel.contains(ayak):
            return "parsel dışı"
        if ayak.intersects(ic_odalar):
            return "iç mekan"
        return None

    def kenar_ornekle(poly: Polygon, iceri: bool, tur: str):
        poly = orient(poly, 1.0)
        c = list(poly.exterior.coords)
        for a, b in zip(c, c[1:]):
            L = math.dist(a, b)
            if L < g + 0.2:
                continue
            u = ((b[0] - a[0]) / L, (b[1] - a[1]) / L)
            n = (-u[1], u[0]) if iceri else (u[1], -u[0])
            t = g / 2 + 0.1
            while t <= L - g / 2 - 0.1 + 1e-6:
                base = (a[0] + u[0] * t, a[1] + u[1] * t)
                m = (base[0] + n[0] * (d / 2 + 0.15), base[1] + n[1] * (d / 2 + 0.15))
                ayak = Polygon([(m[0] + s1 * u[0] * g / 2 + s2 * n[0] * d / 2, m[1] + s1 * u[1] * g / 2 + s2 * n[1] * d / 2)
                                for s1, s2 in ((-1, -1), (1, -1), (1, 1), (-1, 1))])
                t += adim
                if iceri and not poly.buffer(0.02).contains(ayak):
                    continue
                sebep = kontrol(Point(m), ayak, tur)
                if sebep:
                    continue
                adaylar.append({"konum": [round(m[0], 3), round(m[1], 3)], "tur": tur,
                                "kapi_m": round(min((ayak.distance(k) for k in kapilar), default=99.0), 2),
                                "aci": round(math.degrees(math.atan2(n[1], n[0])), 1),
                                "poligon": [[round(x, 3), round(y, 3)] for x, y in ayak.exterior.coords[:-1]],
                                "baglanti": [round(base[0] + n[0] * 0.05, 3), round(base[1] + n[1] * 0.05, 3)]})

    for o in odalar:
        if o["tip"] in ("balkon", "teras"):
            kenar_ornekle(Polygon(o["poligon"]), True, "balkon" if o["tip"] == "balkon" else "teras")
    kenar_ornekle(kabuk, False, "cephe")
    for da in analiz["dis_alanlar"]:
        if da.get("tip") in ("dis_alan", "teras") and "nokta" in da:
            p = Point(da["nokta"])
            ayak = p.buffer(max(g, d) / 2, cap_style=3)
            if not kontrol(p, ayak, "bahce"):
                adaylar.append({"konum": da["nokta"], "tur": "bahce", "aci": 0,
                                "poligon": [[round(x, 3), round(y, 3)] for x, y in ayak.exterior.coords[:-1]],
                                "baglanti": da["nokta"]})
    return adaylar


def _puanla(aday: dict, ic_noktalar: list, tercih: str | None) -> float:
    boru = mst_uzunluk([aday["baglanti"]] + ic_noktalar)
    ceza = TIP_CEZA_M.get(aday["tur"], 3.0)
    if aday.get("kapi_m", 99) < 4.0:
        ceza += 5.0  # giriş/kapı çevresi (vitrin önü, müşteri yolu) yerine kapısız cephe tercih edilir
    if tercih and aday["tur"] == tercih:
        ceza -= 10
    return boru + ceza


def _farkli_sec(adaylar: list, n: int, min_ara: float = 3.0) -> list:
    secilen = []
    for a in adaylar:
        if all(math.dist(a["konum"], s["konum"]) >= min_ara for s in secilen):
            secilen.append(a)
        if len(secilen) >= n:
            break
    return secilen


def gruplari_olustur(yuk: dict, ic_uniteler: list) -> list[dict]:
    sistem = yuk["sistem"]
    if sistem == "split":
        return [{"id": f"S{i + 1}", "tip": "split", "ic": [u["id"]]} for i, u in enumerate(ic_uniteler)]
    if sistem == "multi":
        # yük, en büyük multi-split DÜ kapasitesini aşmamalı (kombinasyon %130 olsa da yük karşılanmalı)
        maxn, maxkw = 5, max(m["kw"] for m in DIS["seriler"]["multi_f"]["modeller"])
        gruplar, kalan = [], sorted(ic_uniteler, key=lambda u: (u["konum"][0], u["konum"][1]))
        while kalan:
            g = [kalan.pop(0)]
            while kalan and len(g) < maxn:
                merkez = g[0]["konum"]
                j = min(range(len(kalan)), key=lambda i: math.dist(kalan[i]["konum"], merkez))
                if sum(u["kw"] for u in g) + kalan[j]["kw"] > maxkw:
                    break
                g.append(kalan.pop(j))
            gruplar.append(g)
        return [{"id": f"S{i + 1}", "tip": "multi" if len(g) > 1 else "split", "ic": [u["id"] for u in g]}
                for i, g in enumerate(gruplar)]
    return [{"id": "S1", "tip": "vrf", "ic": [u["id"] for u in ic_uniteler]}]


def yerlestir(analiz: dict, yuk: dict, ic: dict, ayarlar: dict, elle: dict | None = None, n_aday: int = 3) -> dict:
    elle = elle or {}
    ic_uniteler = ic["ic_uniteler"]
    iu = {u["id"]: u for u in ic_uniteler}
    gruplar = gruplari_olustur(yuk, ic_uniteler)
    tercih = ayarlar.get("du_tercih")
    uyarilar = []
    kullanilan = []
    havuz_cache = {}
    for g in gruplar:
        olcu = DU_OLCU[g["tip"]]
        if olcu not in havuz_cache:
            havuz_cache[olcu] = aday_noktalar(analiz, olcu)
        havuz = havuz_cache[olcu]
        noktalar = [iu[i]["baglanti"] for i in g["ic"]]
        if g["id"] in elle:
            e = elle[g["id"]]
            g["adaylar"] = [{"konum": e["konum"], "baglanti": e.get("baglanti", e["konum"]), "tur": "elle",
                             "aci": e.get("aci", 0), "poligon": e.get("poligon", []), "tahmini_boru_m": None}]
            continue
        uygun = [a for a in havuz if all(math.dist(a["konum"], k) > 1.2 for k in kullanilan)]
        for a in uygun:
            a["_p"] = _puanla(a, noktalar, tercih)
        uygun.sort(key=lambda a: a["_p"])
        sec = _farkli_sec(uygun, n_aday if g["tip"] != "split" else 2)
        if not sec:
            uyarilar.append(f"{g['id']}: uygun dış ünite yeri bulunamadı, elle konum verilmeli.")
        for a in sec:
            a["tahmini_boru_m"] = round(mst_uzunluk([a["baglanti"]] + noktalar), 1)
            a.pop("_p", None)
        g["adaylar"] = [dict(a) for a in sec]
        if sec:
            kullanilan.append(sec[0]["konum"])
    for a_list in havuz_cache.values():
        for a in a_list:
            a.pop("_p", None)
    return {"sistemler": gruplar, "uyarilar": uyarilar, "aday_sayisi": sum(len(v) for v in havuz_cache.values())}
