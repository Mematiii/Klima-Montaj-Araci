"""Duvar geometrisinden oda poligonlarını, isimlerini ve tiplerini çıkarır; dış alanları sınıflandırır.

Yöntem: duvar + kolon + pencere + kapı geometrisi ince tamponlanıp birleştirilir, morfolojik kapama
(buffer(+r).buffer(-r)) ile kapı boşlukları kapatılır; kütlenin iç boşlukları (interiors) odalardır.
"""
from __future__ import annotations

import re

from shapely.geometry import LineString, Point, Polygon, box, shape, mapping
from shapely.ops import unary_union
import shapely

from ortak import anahtar_eslesir, normalize, veri

ODA_TIPLERI = veri("oda_tipleri.json")["tipler"]


def _geom_listesi(plan: dict, kategoriler, bbox=None):
    g = []
    kutu = box(*bbox) if bbox else None
    for kat in kategoriler:
        for c in plan["cizgiler"].get(kat, []):
            pts = c["p"]
            if len(pts) < 2:
                continue
            geom = Polygon(pts) if (c.get("k") and len(pts) >= 3) else LineString(pts)
            if not geom.is_valid:
                geom = geom.buffer(0) if geom.geom_type == "Polygon" else geom
            # duvar katmanındaki kapalı ama geniş (>60 cm) şekil dolu duvar değil, oda/eleman çerçevesidir
            # (ör. duş ya da oda sınırı kapalı polyline); yalnız kenarı duvar sayılır. Tarama (hatch) hariç.
            if kat == "duvar" and geom.geom_type == "Polygon" and not c.get("hatch") \
                    and not geom.buffer(-0.3).is_empty:
                geom = LineString(list(geom.exterior.coords))
            if kutu is not None and not kutu.intersects(geom):
                continue
            g.append(geom)
    return g


def cevre_halkasi_ayikla(duvar: list) -> tuple[list, list]:
    """Binayı saran kaldırım/saçak/bordür çizgisini (duvar katmanına çizilmiş) duvarlardan ayırır.

    Ölçüt: tüm duvarları kuşatan büyük bir çizgi, uzunluğunun >= %70'inde diğer duvarlardan >= 0,5 m uzaktaysa
    gerçek dış duvar değildir (dış duvarın dış yüzü, iç yüzüne ve bölmelere hep bitişiktir). Ona 0,15 m'den yakın
    paralel ikiz çizgiler de ayıklanır. Döner: (kalan duvarlar, ayıklanan halkalar)
    """
    if len(duvar) < 10:
        return duvar, []
    tum = unary_union([g.boundary if g.geom_type == "Polygon" else g for g in duvar])
    x0, y0, x1, y1 = tum.bounds
    W, H = x1 - x0, y1 - y0
    halkalar = []
    for g in duvar:
        hat = g.exterior if g.geom_type == "Polygon" else g
        bx0, by0, bx1, by1 = hat.bounds
        if (bx1 - bx0) < 0.8 * W or (by1 - by0) < 0.8 * H:
            continue
        bant = hat.buffer(0.15)  # bordür çift çizgisi ~10 cm; dış duvarın iç yüzü (>= ~20 cm) ikiz sayılmamalı
        digerleri = []
        for d in duvar:
            if d is g:
                continue
            dh = d.boundary if d.geom_type == "Polygon" else d
            if dh.length > 0 and dh.difference(bant).length < 0.5 * dh.length:
                continue  # adayın paralel ikizi (çift çizgi) - karşılaştırmaya katma
            digerleri.append(dh)
        digerleri = unary_union(digerleri) if digerleri else None
        if digerleri is None:
            continue
        if digerleri.is_empty:
            continue
        uzak = hat.difference(digerleri.buffer(0.5)).length
        if uzak >= 0.7 * hat.length:
            halkalar.append(g)
    if not halkalar:
        return duvar, []
    halka_bant = unary_union([(h.exterior if h.geom_type == "Polygon" else h).buffer(0.15) for h in halkalar])
    kalan = []
    for d in duvar:
        if any(d is h for h in halkalar):
            continue
        hat = d.boundary if d.geom_type == "Polygon" else d
        if hat.length > 0 and hat.difference(halka_bant).length < 0.1 * hat.length:
            continue  # halkanın paralel ikizi
        kalan.append(d)
    return kalan, halkalar


def _nesne_poligonlari(plan: dict, kategori: str, bbox=None):
    kutu = box(*bbox) if bbox else None
    out = []
    for n in plan["nesneler"]:
        if n["kategori"] != kategori:
            continue
        p = Polygon(n["poligon"]) if len(n["poligon"]) >= 3 else LineString(n["poligon"]).buffer(0.05)
        if kutu is not None and not kutu.intersects(p):
            continue
        out.append(p)
    return out


def oda_tipi_bul(metin: str) -> tuple[str | None, int]:
    n = normalize(metin)
    en_iyi, uz = None, 0
    for tip, bilgi in ODA_TIPLERI.items():
        for a in bilgi["anahtar"]:
            skor = len(a) + bilgi.get("oncelik", 0)  # ıslak hacim anahtarları (WC, DUŞ) "ÇOCUK & ENG. WC" gibi adlarda kazanır
            if anahtar_eslesir(n, a) and skor > uz:
                en_iyi, uz = tip, skor
    return en_iyi, uz


def _mahal_katmani(m: dict) -> bool:
    n = normalize(m.get("l", ""))
    return any(k in n for k in ("MAHAL", "ROOM", "MEKAN ADI", "ODA ADI", "AREA-IDEN", "A-AREA"))


def _klima_yazisi(m: dict) -> bool:
    n = normalize(m.get("l", ""))
    if any(k in n for k in ("MEKANIK", "HVAC", "KLIMA", "LATS", "M-", "KAPI", "DOOR", "POZ", "PENCERE", "KOT", "OLCU"))\
            and not _mahal_katmani(m):
        return True  # tesisat etiketleri, kapı/pencere pozları ("K3 900/2100"), kotlar oda adı değildir
    t = normalize(m["t"])
    return any(k in t for k in ("BTU", "KLIMA", "DIS UNITE", "IC UNITE", "QSOG", "QISI"))


_ALAN_RE = re.compile(r"(\d+[.,]?\d*)\s*(M2|M²|M\^2)", re.I)


def duvar_haric_uygula(duvar: list, kutular: list | None) -> list:
    """Kullanıcının işaretlediği kutuların içindeki duvar çizgilerini çıkarır (ör. duvar katmanına
    çizilmiş ölçü/not çizgisi oda içinde sahte duvar oluşturuyorsa). Kutu: [x0, y0, x1, y1] metre."""
    if not kutular:
        return duvar
    from shapely.geometry import box
    maske = unary_union([box(*k) for k in kutular])
    kalan = []
    for g in duvar:
        if not g.intersects(maske):
            kalan.append(g)
            continue
        f = g.difference(maske)
        if not f.is_empty:
            kalan.extend(getattr(f, "geoms", [f]))
    return kalan


def odalari_bul(plan: dict, bbox=None, kapama_r: float = 0.55, min_oda_m2: float = 1.5, kabuk_r: float = 2.6,
                duvar_haric: list | None = None) -> dict:
    acik_kenarli = []
    duvar = _geom_listesi(plan, ["duvar", "kolon"], bbox)
    duvar = duvar_haric_uygula(duvar, duvar_haric)
    duvar, halkalar = cevre_halkasi_ayikla(duvar)
    pencere = _nesne_poligonlari(plan, "pencere", bbox) + [g.buffer(0.02) for g in _geom_listesi(plan, ["pencere"], bbox)]
    kapi = _nesne_poligonlari(plan, "kapi", bbox)
    kolon = _nesne_poligonlari(plan, "kolon", bbox) + [g if g.geom_type == "Polygon" else g.buffer(0.02)
                                                         for g in _geom_listesi(plan, ["kolon"], bbox)]
    kiris = [g.buffer(0.02) if g.geom_type != "Polygon" else g for g in _geom_listesi(plan, ["kiris"], bbox)]
    merdiven = _nesne_poligonlari(plan, "merdiven", bbox) + [g.buffer(0.02) if g.geom_type != "Polygon" else g
                                                               for g in _geom_listesi(plan, ["merdiven"], bbox)]
    if not duvar:
        return {"odalar": [], "uyarilar": ["Duvar katmanı bulunamadı; katman_duzeltme ile duvar katmanlarını belirtin."]}

    ince = [g.buffer(0.03, cap_style=2, join_style=2) if g.geom_type != "Polygon" else g.buffer(0.01) for g in duvar]
    kutle = unary_union(ince + [p.buffer(0.02) for p in pencere] + [k.buffer(0.01) for k in kolon])
    kapali = kutle.buffer(kapama_r, join_style=2).buffer(-kapama_r, join_style=2)
    kapali = unary_union([kapali, kutle])
    parcalar = list(kapali.geoms) if kapali.geom_type == "MultiPolygon" else [kapali]

    odalar_geom = []
    for p in parcalar:
        for ic in p.interiors:
            oda = Polygon(ic)
            if oda.area >= min_oda_m2:
                odalar_geom.append(oda.simplify(0.02))
    # bina dış kabuğu: cam cephe / yalnız kolonlu kenarlar açık kalabildiği için geniş kapama (kolon aralığı ~5 m)
    # not: genişletilmiş şeklin delikleri (iç holler) daraltmadan ÖNCE doldurulur; yoksa delik büyüyüp
    # yalnız kolonlu ince cepheyi delerek dışarıyla birleşir.
    # simplify: 1 cm tamponun yuvarlak köşeleri, mitre genişletmeyi de yuvarlatıp kolon aralarında çentik bırakıyor
    genis = unary_union([kutle, *[p.buffer(0.01) for p in kapi]]).simplify(0.05).buffer(kabuk_r, join_style=2)
    genis = unary_union([Polygon(p.exterior) for p in (list(genis.geoms) if genis.geom_type == "MultiPolygon" else [genis])])
    genis = genis.buffer(-kabuk_r, join_style=2)
    kabuk = unary_union([Polygon(p.exterior) for p in (list(genis.geoms) if genis.geom_type == "MultiPolygon" else [genis])]
                        + [Polygon(p.exterior) for p in parcalar])
    if kabuk.geom_type == "MultiPolygon":
        en_buyuk = max(kabuk.geoms, key=lambda g: g.area)
    else:
        en_buyuk = kabuk
    # kabuk içinde hiçbir odaya girmeyen büyük boşluklar (açık plan salon, mağaza holü) da oda sayılır
    kalan = en_buyuk.difference(unary_union([kapali, *odalar_geom]))
    for g in (list(kalan.geoms) if kalan.geom_type in ("MultiPolygon", "GeometryCollection") else [kalan]):
        if g.geom_type != "Polygon":
            continue
        g = g.buffer(-0.15, join_style=2).buffer(0.15, join_style=2)  # duvar diplerindeki şeritleri at
        for gg in (list(g.geoms) if g.geom_type == "MultiPolygon" else [g]):
            if gg.area >= max(min_oda_m2, 4.0):
                yeni = Polygon(gg.exterior).simplify(0.02)
                odalar_geom.append(yeni)
                acik_kenarli.append(yeni)

    metinler = plan["metinler"]
    if bbox:
        k = box(*bbox)
        metinler = [m for m in metinler if k.contains(Point(m["x"], m["y"]))]

    odalar = []
    kullanilan_metin = set()
    for i, g in enumerate(sorted(odalar_geom, key=lambda g: (-g.centroid.y, g.centroid.x))):
        icindeki = [(j, m) for j, m in enumerate(metinler) if g.contains(Point(m["x"], m["y"]))
                    and not _klima_yazisi(m)]  # mevcut tesisat etiketleri ("BEKO-LG DUVAR TİPİ KLİMA") oda adı değildir
        ad, tip, alan_yazi = "", None, None
        en_iyi = 0
        for j, m in icindeki:
            t, skor = oda_tipi_bul(m["t"])
            if _mahal_katmani(m):
                skor += 5  # mahal/oda adı katmanındaki yazı önceliklidir
            am = _ALAN_RE.search(m["t"].replace(" ", ""))
            if am:
                try:
                    alan_yazi = float(am.group(1).replace(",", "."))
                except ValueError:
                    pass
            if t and skor + m["h"] > en_iyi:
                ad, tip, en_iyi = m["t"], t, skor + m["h"]
                kullanilan_metin.add(j)
        if not ad:
            yazilar = [m for _, m in icindeki if not re.fullmatch(r"[\d\s.,+\-=m²M2:()]+", m["t"])
                       and not m["t"].startswith("%%")  # %%C120 = çap, %%P = ± gibi AutoCAD kodları
                       and len(m["t"].strip()) >= 3]  # "T" (termostat), "A" (kesit) gibi semboller ad değildir
            if yazilar:
                ad = max(yazilar, key=lambda m: (_mahal_katmani(m), m["h"]))["t"]
        dis_kenar = g.exterior.buffer(0.6).intersection(en_buyuk.exterior.buffer(0.6)).area > 0.05
        pencere_say = sum(1 for p in pencere if p.distance(g) < 0.4)
        odalar.append({
            "id": f"O{i + 1}",
            "ad": ad.replace("\n", " ").strip() if ad else "",
            "tip": tip or "bilinmiyor",
            "alan_m2": round(g.area, 2),
            "alan_yazi_m2": alan_yazi,
            "poligon": [[round(x, 3), round(y, 3)] for x, y in g.exterior.coords[:-1]],
            "dis_cephe": bool(dis_kenar),
            "pencere_sayisi": pencere_say,
            "klima": bool(ODA_TIPLERI.get(tip or "", {}).get("klima", False)),
            "acik_kenarli": any(g is x for x in acik_kenarli),
        })

    # dış alanlar: kabuk dışındaki metinlerden ve yol/parsel katmanlarından
    dis_alanlar = []
    ic_kabuk = en_buyuk.buffer(-0.3)
    for g in _geom_listesi(plan, ["yol"], bbox):
        poly = g if g.geom_type == "Polygon" else g.buffer(1.0, cap_style=2)
        if poly.area > 0 and poly.intersection(ic_kabuk).area > 0.5 * poly.area:
            continue  # bina içinde yol olmaz (bariyer/bordür çizgisi iç planda kullanılmış olabilir)
        dis_alanlar.append({"tip": "yol", "poligon": _poly_json(poly), "kaynak": "katman"})
    for m in metinler:
        p = Point(m["x"], m["y"])
        if en_buyuk.contains(p):
            continue
        t, _ = oda_tipi_bul(m["t"])
        if t in ("yol", "dis_alan", "teras", "balkon"):
            dis_alanlar.append({"tip": t, "nokta": [m["x"], m["y"]], "ad": m["t"], "kaynak": "metin"})

    parsel = None
    parsel_adaylar = [g for g in _geom_listesi(plan, ["parsel"], None) if g.geom_type == "Polygon" and g.contains(en_buyuk.centroid)]
    if parsel_adaylar:
        parsel = _poly_json(min(parsel_adaylar, key=lambda g: g.area))

    uyarilar = []
    adsiz = [o["id"] for o in odalar if o["tip"] == "bilinmiyor"]
    if adsiz:
        uyarilar.append(f"Tipi belirlenemeyen alanlar: {', '.join(adsiz)} (kullanıcıya sorulmalı)")
    pencere_bilinmiyor = not pencere and any(o["dis_cephe"] for o in odalar)
    if pencere_bilinmiyor:
        uyarilar.append("Planda pencere ayırt edilemedi (pencereler duvar katmanında olabilir). Dış cephe duvarları pencere "
                        "varsayılıp iç üniteler iç duvarlara yönlendirilecek; pencere katmanı varsa katman_duzeltme ile belirtin.")
    acik = [o["id"] for o in odalar if o["acik_kenarli"]]
    if acik:
        uyarilar.append(f"Duvarla kapanmayan (cam cephe / kolonlu) alanlar: {', '.join(acik)} - sınırları önizlemede kontrol edilmeli")
    for o in odalar:
        if o["alan_yazi_m2"] and abs(o["alan_yazi_m2"] - o["alan_m2"]) / max(o["alan_yazi_m2"], 1) > 0.15:
            uyarilar.append(f"{o['id']} {o['ad']}: hesaplanan alan {o['alan_m2']} m², planda yazan {o['alan_yazi_m2']} m² (açık plan / birleşik oda olabilir)")

    return {
        "bbox": bbox,
        "bina_kabugu": _poly_json(en_buyuk),
        "odalar": odalar,
        "dis_alanlar": dis_alanlar,
        "parsel": parsel,
        "engeller": {
            "kolon": [_poly_json(g) for g in kolon if g.area > 0.01],
            "kiris": [_poly_json(g) for g in kiris],
            "pencere": [_poly_json(g) for g in pencere],
            "kapi": [_poly_json(g) for g in kapi],
            "merdiven": [_poly_json(g) for g in merdiven],
        },
        "duvar_kutlesi": mapping(kutle.simplify(0.01)),
        "pencere_bilinmiyor": pencere_bilinmiyor,
        "uyarilar": uyarilar,
    }


def _poly_json(g):
    if g.geom_type == "MultiPolygon":
        g = max(g.geoms, key=lambda x: x.area)
    if g.geom_type != "Polygon":
        g = g.buffer(0.02)
    return [[round(x, 3), round(y, 3)] for x, y in g.exterior.coords[:-1]]


def duvar_kutlesi(analiz: dict):
    return shape(analiz["duvar_kutlesi"])
