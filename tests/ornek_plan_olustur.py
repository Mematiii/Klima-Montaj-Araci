"""Test için cm birimli sentetik bir daire planı üretir (DUVAR, PENCERE/KAPI blokları, KOLON, KIRIS, YOL, PARSEL)."""
import sys
from pathlib import Path

import ezdxf

S = 100  # m -> cm


def olustur(yol):
    doc = ezdxf.new("R2018")
    doc.header["$INSUNITS"] = 5
    for ad in ("A-DUVAR", "PENCERE", "KAPI", "KOLON", "KIRIS", "YAZI", "YOL", "PARSEL", "MOBILYA"):
        doc.layers.add(ad)
    msp = doc.modelspace()

    # bloklar (cm, birim genişlik 100 -> ölçeklenecek)
    pb = doc.blocks.new("PENCERE_STD")
    pb.add_lwpolyline([(0, -12), (100, -12), (100, 12), (0, 12)], close=True)
    pb.add_line((0, 0), (100, 0))
    kb = doc.blocks.new("KAPI_STD")
    kb.add_line((0, 0), (0, 90))
    kb.add_arc((0, 0), 90, 0, 90)
    kb.add_line((0, 0), (90, 0))
    db = doc.blocks.new("DOLAP_GARDROP")
    db.add_lwpolyline([(0, 0), (180, 0), (180, 60), (0, 60)], close=True)

    def duvar(x0, y0, x1, y1, t, bosluklar=()):
        """Eksen (x0,y0)-(x1,y1), kalınlık t (m); bosluklar: eksen boyunca (bas, son) m."""
        import math
        L = math.dist((x0, y0), (x1, y1))
        ux, uy = (x1 - x0) / L, (y1 - y0) / L
        nx, ny = -uy * t / 2, ux * t / 2
        parcalar, onceki = [], 0.0
        for b, s in sorted(bosluklar):
            parcalar.append((onceki, b))
            onceki = s
        parcalar.append((onceki, L))
        for a, b in parcalar:
            if b - a < 1e-6:
                continue
            p0 = (x0 + ux * a, y0 + uy * a)
            p1 = (x0 + ux * b, y0 + uy * b)
            for sgn in (1, -1):
                msp.add_line(((p0[0] + sgn * nx) * S, (p0[1] + sgn * ny) * S), ((p1[0] + sgn * nx) * S, (p1[1] + sgn * ny) * S),
                             dxfattribs={"layer": "A-DUVAR"})
            # boşluk kenar kapatmaları
            msp.add_line(((p0[0] + nx) * S, (p0[1] + ny) * S), ((p0[0] - nx) * S, (p0[1] - ny) * S), dxfattribs={"layer": "A-DUVAR"})
            msp.add_line(((p1[0] + nx) * S, (p1[1] + ny) * S), ((p1[0] - nx) * S, (p1[1] - ny) * S), dxfattribs={"layer": "A-DUVAR"})

    def pencere(x, y, uzunluk, aci):
        msp.add_blockref("PENCERE_STD", (x * S, y * S), dxfattribs={"layer": "PENCERE", "xscale": uzunluk, "rotation": aci})

    def kapi(x, y, aci):
        msp.add_blockref("KAPI_STD", (x * S, y * S), dxfattribs={"layer": "KAPI", "rotation": aci})

    # dış duvarlar (0.25) - pencere/kapı boşluklarıyla
    duvar(0, 0, 12, 0, 0.25, [(1, 3), (4.6, 5.6), (6.6, 7.4)])          # güney: Y1 pencere, giriş kapısı, banyo pencere
    duvar(12, 0, 12, 10, 0.25, [(2, 4)])                               # doğu: Y2 pencere
    duvar(12, 10, 0, 10, 0.25, [(1, 3), (8.3, 9.2), (9.5, 11)])        # kuzey: mutfak pencere(1-3 => x 9-11), salon pencere x 2.8-3.7 kapı, x1-2.5
    duvar(0, 10, 0, 0, 0.25, [(7, 8.5)])                               # batı: Y1 pencere (y 1.5-3)
    # iç duvarlar (0.10)
    duvar(0, 5, 8, 5, 0.10, [(4.5, 5.4)])
    duvar(4, 0, 4, 5, 0.10, [(3.5, 4.4)])
    duvar(6, 0, 6, 5, 0.10, [(1.0, 1.9), (3.6, 4.5)])
    duvar(6, 3, 8, 3, 0.10)
    duvar(8, 0, 8, 6, 0.10)
    duvar(8, 6, 12, 6, 0.10, [(0.5, 1.4)])
    duvar(7, 5, 7, 10, 0.10, [(2.0, 2.9)])
    # balkon korkuluğu (salonun kuzeyi)
    duvar(0, 10, 0, 11.5, 0.08)
    duvar(0, 11.5, 4, 11.5, 0.08)
    duvar(4, 11.5, 4, 10, 0.08)

    # pencereler (eksen üzerinde)
    pencere(1, 0, 2, 0)
    pencere(6.6, 0, 0.8, 0)
    pencere(12, 2, 2, 90)
    pencere(11, 10, 2, 180)       # mutfak x 9-11
    pencere(2.5, 10, 1.5, 180)    # salon x1-2.5
    pencere(0, 3, 1.5, 270)
    # kapılar
    kapi(4.6, 0, 0)
    kapi(4.5, 5, 0)
    kapi(4, 3.5, 90)
    kapi(6, 1.0, 90)
    kapi(6, 3.6, 90)
    kapi(8.5, 6, 0)
    kapi(7, 7.0, 90)
    kapi(3.7, 10, 180)            # balkon kapısı (x 2.8-3.7)

    # kolonlar (30x30, köşeler) + tarama
    for cx, cy in ((0, 0), (12, 0), (12, 10), (0, 10), (7, 10), (8, 0)):
        pts = [((cx - .15) * S, (cy - .15) * S), ((cx + .15) * S, (cy - .15) * S), ((cx + .15) * S, (cy + .15) * S), ((cx - .15) * S, (cy + .15) * S)]
        msp.add_lwpolyline(pts, close=True, dxfattribs={"layer": "KOLON"})
        h = msp.add_hatch(dxfattribs={"layer": "KOLON"})
        h.paths.add_polyline_path(pts, is_closed=True)
    # kiriş: salonda kolonlar arası değil, mutfakta kısa
    msp.add_lwpolyline([(7 * S, 8.4 * S), (12 * S, 8.4 * S), (12 * S, 8.65 * S), (7 * S, 8.65 * S)], close=True, dxfattribs={"layer": "KIRIS"})

    # mobilya: Y2 gardırop
    msp.add_blockref("DOLAP_GARDROP", (9.5 * S, 0.15 * S), dxfattribs={"layer": "MOBILYA"})

    # yazılar
    for t, x, y in (("SALON", 3.5, 7.5), ("MUTFAK", 9.5, 7.5), ("YATAK ODASI", 2, 2.5), ("ÇOCUK ODASI", 10, 3.5),
                    ("HOL", 5, 2.5), ("BANYO", 7, 1.5), ("WC", 7, 4), ("BALKON", 2, 10.8), ("CADDE", 6, -4.5), ("BAHÇE", 13.2, 5)):
        msp.add_text(t, height=25, dxfattribs={"layer": "YAZI", "insert": (x * S, y * S)})
    msp.add_text("NORMAL KAT PLANI", height=50, dxfattribs={"layer": "YAZI", "insert": (2 * S, -1.5 * S)})
    # yol ve parsel
    msp.add_lwpolyline([(-5 * S, -6 * S), (17 * S, -6 * S), (17 * S, -3 * S), (-5 * S, -3 * S)], close=True, dxfattribs={"layer": "YOL"})
    msp.add_lwpolyline([(-1.5 * S, -2.5 * S), (14.5 * S, -2.5 * S), (14.5 * S, 13 * S), (-1.5 * S, 13 * S)], close=True, dxfattribs={"layer": "PARSEL"})
    doc.saveas(yol)
    return yol


if __name__ == "__main__":
    print(olustur(sys.argv[1] if len(sys.argv) > 1 else "ornek_daire.dxf"))
