"""Havşa boyu ve sıkma torku tablosu erişimi."""
from ortak import veri

_T = veri("havsa_tork.json")["tablo"]


def havsa_satiri(mm: float):
    for r in _T:
        if abs(r["mm"] - mm) < 0.1:
            return r
    return None
