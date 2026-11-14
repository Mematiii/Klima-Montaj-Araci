"""Dış ünite aday konumları ve sistem gruplaması.

Adaylar: balkon/teras/çatı alanları, bina cephesi (dış duvar boyu), bahçe/boş alan metinleri.
Yasaklar: yol/otopark, kapı önü (kaçış yolu), merdiven, parsel dışı, bina kütlesi içi,
  pencere önü/altı, ön servis boşluğunun sığmaması.
Puan: tahmini boru uzunluğu (Manhattan MST) + konum tipi cezası + pencere yakınlığı + dar yan boşluk
  + sıcak hava sıkışması (karşıda duvar, niş/avlu) + büyük VRF'yi cepheye asma cezası (eşdeğer metre).
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

# Servis/hava boşlukları (m): ön = hava atışı + bakım, arka = emiş (duvara), yan = emiş + bakım.
# _dogrulanmali: tipik montaj kılavuzu değerleri; LG kataloğu gelince güncellenmeli.
DU_BOSLUK = {"vrf": {"on": 1.0, "arka": 0.3, "yan": 0.3},
             "multi": {"on": 0.6, "arka": 0.15, "yan": 0.3},
             "split": {"on": 0.5, "arka": 0.15, "yan": 0.3}}
PENCERE_YASAK_M = 0.3    # ünite pencerenin önünde/altında
PENCERE_TERCIH_M = 1.5   # sıcak hava ve gürültü pencereden içeri girmesin
SICAK_KARSI_M = 2.0      # ön yüzün karşısındaki engel (sıcak hava geri emilir)
SICAK_KAPALI_ORAN = 0.5  # ön yarım düzlemde 3 m içinde engel olan ışın oranı (niş/avlu)
VRF_CEPHE_CEZA_M = 10.0  # VRF'yi cepheye konsolla asmak: ağırlık, taşıyıcı, izin
VRF_CEPHE_KW_CEZA = 0.5  # 14 kW üstü her kW için ek ceza (büyüdükçe daha ağır)


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


def _dikdortgen(m, u, n, a0, a1, b0, b1) -> Polygon:
    """m merkezli yerel çerçevede (u boyunca a0..a1, n boyunca b0..b1) dikdörtgen."""
    return Polygon([(m[0] + u[0] * a + n[0] * b, m[1] + u[1] * a + n[1] * b)
                    for a, b in ((a0, b0), (a1, b0), (a1, b1), (a0, b1))])


def servis_bolgeleri(m, u, n, g: float, d: float, bosluk: dict) -> dict:
    """Ön (n yönü), sol/sağ yan boşluk dikdörtgenleri. Arka, adayın duvardan uzaklığıyla sağlanır."""
    on, yan = bosluk["on"], bosluk["yan"]
    return {"on": _dikdortgen(m, u, n, -g / 2, g / 2, d / 2, d / 2 + on),
            "yan1": _dikdortgen(m, u, n, -g / 2 - yan, -g / 2, -d / 2, d / 2),
            "yan2": _dikdortgen(m, u, n, g / 2, g / 2 + yan, -d / 2, d / 2)}


def sicak_hava(m, n, d: float, engel, maks: float = 4.0) -> tuple[float, float]:
    """Ön yüzden yarım düzleme ışınlar: (tam karşıdaki engele mesafe, 3 m içinde kapalı ışın oranı)."""
    if engel is None or engel.is_empty:
        return maks, 0.0
    o = (m[0] + n[0] * d / 2, m[1] + n[1] * d / 2)
    taban = math.atan2(n[1], n[0])
    karsi, kapali, say = maks, 0, 0
    for derece in range(-75, 76, 15):
        a = taban + math.radians(derece)
        hat = LineString([(o[0] + math.cos(a) * 0.05, o[1] + math.sin(a) * 0.05),
                          (o[0] + math.cos(a) * maks, o[1] + math.sin(a) * maks)])
        kes = hat.intersection(engel)
        dist = maks if kes.is_empty else Point(o).distance(kes)
        say += 1
        if dist < 3.0:
            kapali += 1
        if derece == 0:
            karsi = dist
    return karsi, kapali / say


def aday_noktalar(analiz: dict, olcu=(1.0, 0.8), adim: float = 0.5, tip: str = "vrf") -> list[dict]:
    kabuk = orient(Polygon(analiz["bina_kabugu"]), 1.0)
    odalar = analiz["odalar"]
    eng = analiz["engeller"]
    kapilar = [Polygon(p) for p in eng["kapi"]]
    pencereler = [Polygon(p) for p in eng.get("pencere", []) if len(p) >= 3]
    bosluk = DU_BOSLUK.get(tip, DU_BOSLUK["vrf"])
    # sıcak hava engeli: bina kütlesinin kenarı (adayın kendi duvarı ışınların arkasında kalır)
    kutle_sinir = kabuk.exterior
    merdiven = [Polygon(p) for p in eng["merdiven"]]
    yollar = [Polygon(d["poligon"]) for d in analiz["dis_alanlar"] if d.get("tip") == "yol" and "poligon" in d]
    yol_noktalari = [Point(d["nokta"]) for d in analiz["dis_alanlar"] if d.get("tip") == "yol" and "nokta" in d]
    parsel = Polygon(analiz["parsel"]) if analiz.get("parsel") else None
    ic_odalar = unary_union([Polygon(o["poligon"]) for o in odalar if o["tip"] not in ("balkon", "teras")])
    g, d = olcu
    adaylar = []
    engel_kutle = unary_union([kabuk.buffer(-0.02), ic_odalar, *merdiven, *yollar])

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
            arka = max(0.15, bosluk["arka"])
            while t <= L - g / 2 - 0.1 + 1e-6:
                base = (a[0] + u[0] * t, a[1] + u[1] * t)
                m = (base[0] + n[0] * (d / 2 + arka), base[1] + n[1] * (d / 2 + arka))
                ayak = Polygon([(m[0] + s1 * u[0] * g / 2 + s2 * n[0] * d / 2, m[1] + s1 * u[1] * g / 2 + s2 * n[1] * d / 2)
                                for s1, s2 in ((-1, -1), (1, -1), (1, 1), (-1, 1))])
                t += adim
                if iceri and not poly.buffer(0.02).contains(ayak):
                    continue
                sebep = kontrol(Point(m), ayak, tur)
                if sebep:
                    continue
                notlar, ek = [], 0.0
                # 1) servis / hava boşluğu: ön kesin, yanlar tercih
                sb = servis_bolgeleri(m, u, n, g, d, bosluk)
                if iceri:
                    alan = poly.buffer(0.02)
                    kapali = {k: not alan.contains(z) for k, z in sb.items()}
                else:
                    kapali = {k: z.intersects(engel_kutle) for k, z in sb.items()}
                if kapali["on"]:
                    continue
                if kapali["yan1"] or kapali["yan2"]:
                    ek += 3.0
                    notlar.append("yan servis boşluğu dar")
                # 2) pencere: önünde/altında olamaz, yakını cezalı
                pen_m = min((ayak.distance(w) for w in pencereler), default=99.0)
                if pen_m < PENCERE_YASAK_M:
                    continue
                if pen_m < PENCERE_TERCIH_M:
                    ek += (PENCERE_TERCIH_M - pen_m) * 6.0
                    notlar.append(f"pencereye {pen_m:.1f} m")
                # 3) sıcak hava sıkışması (cephe): karşıda duvar, niş/avlu
                if not iceri:
                    karsi, oran = sicak_hava(m, n, d, kutle_sinir)
                    if karsi < SICAK_KARSI_M:
                        ek += (SICAK_KARSI_M - karsi) * 5.0
                        notlar.append(f"önünde engel {karsi:.1f} m")
                    if oran > SICAK_KAPALI_ORAN:
                        ek += 6.0
                        notlar.append("niş/avlu: sıcak hava sıkışabilir")
                adaylar.append({"konum": [round(m[0], 3), round(m[1], 3)], "tur": tur,
                                "kapi_m": round(min((ayak.distance(k) for k in kapilar), default=99.0), 2),
                                "pencere_m": round(pen_m, 2), "ek_ceza": round(ek, 2), "notlar": notlar,
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
            pen_m = min((ayak.distance(w) for w in pencereler), default=99.0)
            if not kontrol(p, ayak, "bahce") and pen_m >= PENCERE_YASAK_M:
                ek = max(0.0, PENCERE_TERCIH_M - pen_m) * 6.0
                adaylar.append({"konum": da["nokta"], "tur": "bahce", "aci": 0, "pencere_m": round(pen_m, 2),
                                "ek_ceza": round(ek, 2), "notlar": [f"pencereye {pen_m:.1f} m"] if ek else [],
                                "poligon": [[round(x, 3), round(y, 3)] for x, y in ayak.exterior.coords[:-1]],
                                "baglanti": da["nokta"]})
    return adaylar


def vrf_cephe_cezasi(sistem_tip: str, toplam_kw: float) -> float:
    """Büyük VRF DÜ'yü (100-300 kg) cepheye konsolla asmak çoğu zaman gerçekçi değil."""
    if sistem_tip != "vrf":
        return 0.0
    return VRF_CEPHE_CEZA_M + max(0.0, toplam_kw - 14.0) * VRF_CEPHE_KW_CEZA


def _puanla(aday: dict, ic_noktalar: list, tercih: str | None, sistem_tip: str = "split",
            toplam_kw: float = 0.0) -> float:
    boru = mst_uzunluk([aday["baglanti"]] + ic_noktalar)
    ceza = TIP_CEZA_M.get(aday["tur"], 3.0) + aday.get("ek_ceza", 0.0)
    if aday["tur"] == "cephe":
        ceza += vrf_cephe_cezasi(sistem_tip, toplam_kw)
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
            havuz_cache[olcu] = aday_noktalar(analiz, olcu, tip=g["tip"])
        havuz = havuz_cache[olcu]
        toplam_kw = sum(iu[i].get("kw", 0) for i in g["ic"])
        noktalar = [iu[i]["baglanti"] for i in g["ic"]]
        if g["id"] in elle:
            e = elle[g["id"]]
            g["adaylar"] = [{"konum": e["konum"], "baglanti": e.get("baglanti", e["konum"]), "tur": "elle",
                             "aci": e.get("aci", 0), "poligon": e.get("poligon", []), "tahmini_boru_m": None}]
            continue
        uygun = [a for a in havuz if all(math.dist(a["konum"], k) > 1.2 for k in kullanilan)]
        for a in uygun:
            a["_p"] = _puanla(a, noktalar, tercih, g["tip"], toplam_kw)
        uygun.sort(key=lambda a: a["_p"])
        sec = _farkli_sec(uygun, n_aday if g["tip"] != "split" else 2)
        if not sec:
            uyarilar.append(f"{g['id']}: uygun dış ünite yeri bulunamadı, elle konum verilmeli.")
        elif sec[0]["tur"] == "cephe" and g["tip"] == "vrf":
            uyarilar.append(f"{g['id']}: VRF dış ünitesi ({toplam_kw:.0f} kW iç ünite) cepheye konsolla öneriliyor; "
                            "balkon/teras/bahçe adayı yok. Taşıyıcı, ağırlık ve cephe iznini kontrol edin; "
                            "çatı ya da zemin mümkünse elle_konum ile verin.")
        if sec and sec[0].get("notlar"):
            uyarilar.append(f"{g['id']} aday 1: {'; '.join(sec[0]['notlar'])}")
        if analiz.get("pencere_bilinmiyor") and any(a["tur"] == "cephe" for a in sec):
            uyarilar.append(f"{g['id']}: planda pencere ayırt edilemedi; cephe adaylarının pencere önüne/altına "
                            "düşmediğini önizlemede kontrol edin.")
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
