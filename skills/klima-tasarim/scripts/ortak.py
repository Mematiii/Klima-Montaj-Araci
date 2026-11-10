"""Ortak yardımcılar: proje durumu, veri dosyaları, isim normalizasyonu."""
from __future__ import annotations

import json
import math
import os
import re
import sys
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = SKILL_DIR / "data"

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

_TR = str.maketrans({"İ": "I", "ı": "I", "Ş": "S", "ş": "S", "Ğ": "G", "ğ": "G",
                     "Ü": "U", "ü": "U", "Ö": "O", "ö": "O", "Ç": "C", "ç": "C",
                     "Â": "A", "â": "A", "Î": "I", "î": "I", "Û": "U", "û": "U"})


def normalize(s: str) -> str:
    """Türkçe karakterleri ASCII'ye çevirip büyük harf yapar."""
    return (s or "").translate(_TR).upper()


def anahtar_eslesir(metin_norm: str, anahtar: str) -> bool:
    """<=3 harf: tam kelime; 4 harf: kelime başı (IMAR, MIMARI içinde eşleşmesin); uzunlar: alt dize."""
    a = normalize(anahtar)
    n = len(a.strip("-. "))
    if n <= 3:
        return re.search(r"(^|[^A-Z0-9])" + re.escape(a) + r"([^A-Z0-9]|$)", metin_norm) is not None
    if n == 4:
        return re.search(r"(^|[^A-Z])" + re.escape(a), metin_norm) is not None
    return a in metin_norm


def veri(ad: str) -> dict:
    with open(DATA_DIR / ad, encoding="utf-8") as f:
        return json.load(f)


def json_yaz(yol: Path | str, obj) -> None:
    yol = Path(yol)
    yol.parent.mkdir(parents=True, exist_ok=True)
    tmp = yol.with_suffix(yol.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)
    os.replace(tmp, yol)


def json_oku(yol: Path | str):
    with open(yol, encoding="utf-8-sig") as f:  # Not Defteri/PowerShell BOM'lu kaydedebilir
        return json.load(f)


class Proje:
    """Bir projenin çalışma klasörü ve proje.json durum dosyası.

    Klasör yapısı:
      proje.json      -> ayarlar, kullanıcı kısıtları ve adım sonuçları
      plan.json       -> DXF'ten çıkarılan geometri (metre)
      onizleme/*.png  -> kontrol noktası görselleri
      cikti/          -> DXF/DWG, rapor, Excel
    """

    def __init__(self, klasor: str | Path):
        self.klasor = Path(klasor).resolve()
        self.klasor.mkdir(parents=True, exist_ok=True)
        self.yol = self.klasor / "proje.json"
        self.d = json_oku(self.yol) if self.yol.exists() else {
            "surum": 1,
            "ayarlar": {},
            "musteri_istekleri": [],
            "adimlar": {},
        }

    # --- kısayollar ---
    @property
    def ayar(self) -> dict:
        return self.d.setdefault("ayarlar", {})

    def adim(self, ad: str) -> dict | None:
        return self.d.get("adimlar", {}).get(ad)

    def adim_yaz(self, ad: str, sonuc: dict) -> None:
        self.d.setdefault("adimlar", {})[ad] = sonuc
        self.kaydet()

    def gerekli(self, ad: str) -> dict:
        s = self.adim(ad)
        if s is None:
            hata(f"Önce '{ad}' adımı çalıştırılmalı.")
        return s

    def kaydet(self) -> None:
        json_yaz(self.yol, self.d)

    def dosya(self, *parca) -> Path:
        p = self.klasor.joinpath(*parca)
        p.parent.mkdir(parents=True, exist_ok=True)
        return p

    def plan(self) -> dict:
        p = self.klasor / "plan.json"
        if not p.exists():
            hata("plan.json yok. Önce 'analiz' adımını çalıştırın.")
        return json_oku(p)


def hata(mesaj: str, kod: int = 2):
    print(f"HATA: {mesaj}", file=sys.stderr)
    sys.exit(kod)


def btu_to_kw(btu: float) -> float:
    return btu * 0.000293071


def kw_to_btu(kw: float) -> float:
    return kw / 0.000293071


def tablo_sec(tablo: list[dict], deger: float, anahtar: str = "max_kw") -> dict:
    """max_kw sıralı tablodan değere uyan ilk satırı döndürür."""
    for satir in tablo:
        if deger <= satir[anahtar] + 1e-9:
            return satir
    return tablo[-1]


def mesafe(a, b) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])
