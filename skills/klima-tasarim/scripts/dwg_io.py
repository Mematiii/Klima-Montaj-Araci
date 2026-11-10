"""DWG <-> DXF dönüşümü.

Öncelik: AutoCAD accoreconsole (kuruluysa) -> ODA File Converter.
Ortam değişkenleri ile yol verilebilir: KLIMA_ACCORE, KLIMA_ODA.
"""
from __future__ import annotations

import glob
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from ortak import hata


def _ilk_var(adaylar):
    for a in adaylar:
        for p in sorted(glob.glob(a), reverse=True):
            if os.path.isfile(p):
                return p
    return None


def accore_bul() -> str | None:
    if os.environ.get("KLIMA_ACCORE") and os.path.isfile(os.environ["KLIMA_ACCORE"]):
        return os.environ["KLIMA_ACCORE"]
    return _ilk_var([r"C:\Program Files\Autodesk\AutoCAD*\accoreconsole.exe"])


def oda_bul() -> str | None:
    if os.environ.get("KLIMA_ODA") and os.path.isfile(os.environ["KLIMA_ODA"]):
        return os.environ["KLIMA_ODA"]
    w = shutil.which("ODAFileConverter")
    if w:
        return w
    return _ilk_var([
        r"C:\Program Files\ODA\ODAFileConverter*\ODAFileConverter.exe",
        r"C:\Program Files (x86)\ODA\ODAFileConverter*\ODAFileConverter.exe",
        "/usr/bin/ODAFileConverter",
        "/Applications/ODAFileConverter.app/Contents/MacOS/ODAFileConverter",
    ])


def durum() -> dict:
    return {"accoreconsole": accore_bul(), "oda": oda_bul()}


def _oda_cevir(exe: str, girdi: Path, cikti_klasor: Path, hedef_tip: str, surum: str = "ACAD2018") -> Path:
    # ODA klasör bazında çalışır; Türkçe karakter sorunlarına karşı ASCII adla geçici klasöre kopyala.
    with tempfile.TemporaryDirectory() as td_in, tempfile.TemporaryDirectory() as td_out:
        uzanti = girdi.suffix.lower()
        gecici = Path(td_in) / ("girdi" + uzanti)
        shutil.copy2(girdi, gecici)
        cmd = [exe, td_in, td_out, surum, hedef_tip, "0", "1", "*" + uzanti]
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=900)
        uz = ".dxf" if hedef_tip == "DXF" else ".dwg"
        sonuc = Path(td_out) / ("girdi" + uz)
        if not sonuc.exists():
            hata(f"ODA dönüşümü başarısız: {r.stdout}\n{r.stderr}")
        hedef = cikti_klasor / (girdi.stem + uz)
        cikti_klasor.mkdir(parents=True, exist_ok=True)
        shutil.copy2(sonuc, hedef)
        return hedef


def _accore_cevir(exe: str, girdi: Path, hedef: Path) -> Path:
    with tempfile.TemporaryDirectory() as td:
        g = Path(td) / ("girdi" + girdi.suffix.lower())
        shutil.copy2(girdi, g)
        h = Path(td) / ("cikti" + hedef.suffix.lower())
        scr = Path(td) / "cevir.scr"
        if hedef.suffix.lower() == ".dxf":
            scr.write_text(f'_.DXFOUT "{h}" _V _2018 16\n_.QUIT _Y\n', encoding="ascii")
        else:
            scr.write_text(f'_.SAVEAS _2018 "{h}"\n_.QUIT _Y\n', encoding="ascii")
        subprocess.run([exe, "/i", str(g), "/s", str(scr)], capture_output=True, timeout=900)
        if not h.exists():
            return None
        hedef.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(h, hedef)
        return hedef


def dwg_to_dxf(girdi: str | Path, cikti_klasor: str | Path) -> Path:
    girdi, cikti_klasor = Path(girdi), Path(cikti_klasor)
    if girdi.suffix.lower() == ".dxf":
        return girdi
    acc = accore_bul()
    if acc:
        r = _accore_cevir(acc, girdi, cikti_klasor / (girdi.stem + ".dxf"))
        if r:
            return r
    oda = oda_bul()
    if oda:
        return _oda_cevir(oda, girdi, cikti_klasor, "DXF")
    hata("DWG okunamıyor: AutoCAD (accoreconsole) ya da ODA File Converter bulunamadı.\n"
         "ODA File Converter'ı https://www.opendesign.com/guestfiles/oda_file_converter adresinden kurun\n"
         "veya dosyayı AutoCAD'den DXF olarak kaydedip onu verin.")


def dxf_to_dwg(girdi: str | Path, cikti_klasor: str | Path) -> Path | None:
    girdi, cikti_klasor = Path(girdi), Path(cikti_klasor)
    acc = accore_bul()
    if acc:
        r = _accore_cevir(acc, girdi, cikti_klasor / (girdi.stem + ".dwg"))
        if r:
            return r
    oda = oda_bul()
    if oda:
        return _oda_cevir(oda, girdi, cikti_klasor, "DWG")
    return None


if __name__ == "__main__":
    import json
    import sys
    if len(sys.argv) == 1:
        print(json.dumps(durum(), indent=1))
    else:
        print(dwg_to_dxf(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else Path(sys.argv[1]).parent))
