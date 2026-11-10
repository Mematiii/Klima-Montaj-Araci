"""Blok kütüphanesi DXF'indeki blokları listeler (ad, boyut, varlık sayısı) ve klima ile ilgili olanları işaretler.

Kullanım: py blok_tara.py KUTUPHANE.dxf [cikti.json]
"""
import json
import sys
from pathlib import Path

import ezdxf
from ezdxf import bbox

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ortak import anahtar_eslesir, normalize  # noqa: E402

IPUCU = {
    "duvar": ["DUVAR", "WALL", "SJ", "ARTCOOL", "ART COOL", "HIGH WALL"],
    "kaset4": ["KASET", "CASSETTE", "4WAY", "4 YON", "TL", "TM"],
    "kaset1": ["1WAY", "1 YON", "TU"],
    "kanal": ["KANAL", "DUCT", "M3", "L3", "B8"],
    "salon": ["SALON", "CEILING", "FLOOR", "VE", "CE", "TAVAN"],
    "du_vrf": ["DIS UNITE", "OUTDOOR", "ODU", "ARUM", "ARUN", "MULTI V"],
    "ybranch": ["Y-BRANCH", "YBRANCH", "REFNET", "ARBLN", "JOINT", "BRANS"],
}


def tara(yol):
    doc = ezdxf.readfile(yol)
    out = []
    for b in doc.blocks:
        if b.name.startswith("*") or b.name.startswith("_"):
            continue
        ents = list(b)
        if not ents:
            continue
        try:
            e = bbox.extents(ents, fast=True)
            boyut = [round(e.size.x, 1), round(e.size.y, 1)] if e.has_data else None
        except Exception:
            boyut = None
        n = normalize(b.name)
        aday = [k for k, kel in IPUCU.items() if any(anahtar_eslesir(n, x) for x in kel)]  # "TL","CE" alt dize olarak her yerde geçer
        out.append({"ad": b.name, "varlik": len(ents), "boyut": boyut, "aday_kategori": aday})
    out.sort(key=lambda x: (not x["aday_kategori"], x["ad"]))
    return out


if __name__ == "__main__":
    liste = tara(sys.argv[1])
    hedef = sys.argv[2] if len(sys.argv) > 2 else str(Path(sys.argv[1]).with_suffix(".bloklar.json"))
    Path(hedef).write_text(json.dumps(liste, ensure_ascii=False, indent=1), encoding="utf-8")
    for b in liste[:150]:
        print(f"{','.join(b['aday_kategori']) or '-':<14} {str(b['boyut']):<18} {b['ad']}")
    print(f"\nToplam {len(liste)} blok -> {hedef}")
