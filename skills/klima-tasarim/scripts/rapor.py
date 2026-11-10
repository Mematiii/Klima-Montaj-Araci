"""HTML hesap raporu ve Excel malzeme listesi / teklif."""
from __future__ import annotations

import base64
import html
import math
from collections import defaultdict
from datetime import date
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from shapely.geometry import Point, Polygon

from boru_cap_hesap import inch
from ortak import DATA_DIR, json_oku
from havsa import havsa_satiri

TIP_AD = {"duvar": "Duvar tipi", "kaset4": "4 yön kaset", "kaset1": "1 yön kaset", "kanal": "Kanallı", "salon": "Salon tipi"}


def _fiyatlar() -> dict:
    p = DATA_DIR / "fiyatlar.json"
    return json_oku(p) if p.exists() else {}


def metraj(ic: dict, opt: dict, analiz: dict, fire: float = 0.10) -> dict:
    boru = defaultdict(float)
    ybr = defaultdict(int)
    du = defaultdict(int)
    gaz = 0.0
    rota_m = 0.0
    for s in opt["sistemler"]:
        h = s["secilen"]["hesap"]
        for seg in h["segmentler"]:
            L = seg["uzunluk_m"] + seg.get("dikey_m", 0)
            boru[seg["sivi"]] += L
            boru[seg["gaz"]] += L
            rota_m += L
        for y in h.get("y_branch", []):
            ybr[y["model"]] += 1
        if h.get("du"):
            du[(h["du"]["model"], h["du"].get("kw"))] += 1
        gaz += h.get("ilave_gaz_kg", 0)
    kabuk = Polygon(analiz["bina_kabugu"])
    drenaj = sum(Point(u["konum"]).distance(kabuk.exterior) + 1.5 for u in ic["ic_uniteler"])
    iu = defaultdict(int)
    for u in ic["ic_uniteler"]:
        iu[(u["tip"], u["kw"], u["btu"])] += 1
    return {
        "boru": {d: round(m * (1 + fire), 1) for d, m in sorted(boru.items())},
        "boru_net": {d: round(m, 1) for d, m in sorted(boru.items())},
        "y_branch": dict(ybr), "du": dict(du), "iu": dict(iu),
        "ilave_gaz_kg": round(gaz, 2), "drenaj_m": round(drenaj * (1 + fire), 1),
        "kablo_m": round(rota_m * (1 + fire) + 3 * len(ic["ic_uniteler"]), 1), "fire": fire,
    }


def excel(yol: str | Path, proje_adi: str, yuk: dict, ic: dict, opt: dict, analiz: dict) -> str:
    m = metraj(ic, opt, analiz)
    f = _fiyatlar()
    wb = Workbook()
    ws = wb.active
    ws.title = "Teklif"
    bas = Font(bold=True, color="FFFFFF")
    dolgu = PatternFill("solid", fgColor="1F6F8B")
    ws.append([f"{proje_adi} - Klima Sistemi Malzeme Listesi / Teklif", "", "", "", "", ""])
    ws["A1"].font = Font(bold=True, size=13)
    ws.append([f"Tarih: {date.today().isoformat()}  |  Sistem: {yuk['sistem'].upper()}  |  Bölge: {yuk['bolge']}"])
    ws.append([])
    ws.append(["Kalem", "Açıklama", "Miktar", "Birim", "Birim Fiyat", "Tutar"])
    for c in range(1, 7):
        ws.cell(row=4, column=c).font = bas
        ws.cell(row=4, column=c).fill = dolgu
    satirlar = []
    for (model, kw), n in m["du"].items():
        satirlar.append((f"Dış ünite {model}", f"{kw} kW", n, "adet", f.get(f"du:{model}")))
    for (tip, kw, btu), n in sorted(m["iu"].items()):
        satirlar.append((f"İç ünite {TIP_AD.get(tip, tip)}", f"{kw} kW / {btu} BTU", n, "adet", f.get(f"iu:{tip}:{kw}")))
    for model, n in m["y_branch"].items():
        satirlar.append((f"Y-branch {model}", "LG refnet", n, "adet", f.get(f"ybranch:{model}")))
    for d, metre in m["boru"].items():
        satirlar.append((f"Bakır boru {inch(d)} (Ø{d})", f"%{int(m['fire'] * 100)} fire dahil", metre, "m", f.get(f"boru:{d}")))
    for d, metre in m["boru"].items():
        satirlar.append((f"Kauçuk izolasyon {inch(d)}", "boru ile aynı metraj", metre, "m", f.get(f"izolasyon:{d}")))
    satirlar.append(("Drenaj borusu", "tahmini, en yakın cepheye", m["drenaj_m"], "m", f.get("drenaj")))
    satirlar.append(("İletişim / enerji kablosu", "tahmini", m["kablo_m"], "m", f.get("kablo")))
    satirlar.append(("R410A ilave gaz", "boru hattı için", m["ilave_gaz_kg"], "kg", f.get("gaz_kg")))
    satirlar.append(("İç ünite montajı", "", len(ic["ic_uniteler"]), "adet", f.get("iscilik:iu")))
    satirlar.append(("Dış ünite montajı", "", sum(m["du"].values()), "adet", f.get("iscilik:du")))
    satirlar.append(("Azot basınç testi, vakum, devreye alma", "", len(opt["sistemler"]), "sistem", f.get("iscilik:devreye_alma")))
    ilk = ws.max_row + 1
    for kalem, acik, mik, birim, fiyat in satirlar:
        ws.append([kalem, acik, mik, birim, fiyat])
        r = ws.max_row
        ws.cell(row=r, column=6, value=f"=C{r}*E{r}")
    son = ws.max_row
    ws.append([])
    ws.append(["", "", "", "", "Ara toplam", f"=SUM(F{ilk}:F{son})"])
    r = ws.max_row
    ws.append(["", "", "", "", "KDV %20", f"=F{r}*0.2"])
    ws.append(["", "", "", "", "Genel toplam", f"=F{r}+F{r + 1}"])
    for rr in range(r, r + 3):
        ws.cell(row=rr, column=5).font = Font(bold=True)
        ws.cell(row=rr, column=6).font = Font(bold=True)
    for col, w in zip("ABCDEF", (40, 30, 10, 8, 14, 16)):
        ws.column_dimensions[col].width = w
    for row in ws.iter_rows(min_row=ilk, max_row=r + 2, min_col=5, max_col=6):
        for c in row:
            c.number_format = '#,##0.00'
    ws.append([])
    ws.append(["Birim fiyatlar boşsa data/fiyatlar.json ile otomatik doldurulabilir ya da elle girilebilir."])

    # odalar
    w2 = wb.create_sheet("Odalar ve Yük")
    w2.append(["Oda", "Ad", "Tip", "Alan m²", "Kişi", "Yük BTU", "Yük kW", "Tablo BTU", "İç üniteler"])
    for o in yuk["odalar"]:
        w2.append([o["id"], o["ad"], o["tip"], o["alan_m2"], o["yuk"]["kisi"], o["yuk"]["btu"], o["yuk"]["kw"],
                   o["yuk"]["tablo_btu"], ", ".join(f"{u['id']} {u['tip']} {u['kw']}kW" for u in o["uniteler"])])
    # boru hatları
    w3 = wb.create_sheet("Boru Hatları")
    w3.append(["Sistem", "Hat", "Başlangıç", "Bitiş", "Rol", "Alt yük kW", "Sıvı", "Gaz", "Uzunluk m", "Düşey m", "Dirsek", "Eşdeğer m", "Not"])
    for s in opt["sistemler"]:
        for seg in s["secilen"]["hesap"]["segmentler"]:
            w3.append([s["id"], seg["id"], seg["bas"], seg["son"], seg.get("rol"), seg.get("alt_kw"),
                       f"{inch(seg['sivi'])} ({seg['sivi']})", f"{inch(seg['gaz'])} ({seg['gaz']})",
                       seg["uzunluk_m"], seg.get("dikey_m"), seg["dirsek"], seg.get("esdeger_m"), seg.get("not", "")])
    # kontroller
    w4 = wb.create_sheet("Kontroller")
    w4.append(["Sistem", "Kontrol", "Değer", "Limit", "Durum"])
    for s in opt["sistemler"]:
        for c in s["secilen"]["hesap"]["kontroller"]:
            w4.append([s["id"], c["ad"], c["deger"], c["limit"], "UYGUN" if c["ok"] else "AŞIM"])
    # havşa / tork
    w5 = wb.create_sheet("Havşa ve Tork")
    w5.append(["Çap mm", "inch", "Havşa max mm", "Havşa min mm", "Sıkma torku kg.m", "Ek sıkma torku kg.m"])
    for d in sorted({seg[k] for s in opt["sistemler"] for seg in s["secilen"]["hesap"]["segmentler"] for k in ("sivi", "gaz")}):
        r_ = havsa_satiri(d)
        if r_:
            w5.append([r_["mm"], r_["inch"], r_["havsa_max"], r_["havsa_min"], r_["tork"], r_["ek_tork"]])
    for wsx in (w2, w3, w4, w5):
        for c in wsx[1]:
            c.font = bas
            c.fill = dolgu
        for i in range(1, wsx.max_column + 1):
            wsx.column_dimensions[get_column_letter(i)].width = 16
    yol = Path(yol)
    yol.parent.mkdir(parents=True, exist_ok=True)
    wb.save(yol)
    return str(yol)


def _img(p):
    p = Path(p)
    if not p.exists():
        return ""
    return f'<img src="data:image/png;base64,{base64.b64encode(p.read_bytes()).decode()}" style="max-width:100%">'


def _tablo(basliklar, satirlar):
    h = "".join(f"<th>{html.escape(str(b))}</th>" for b in basliklar)
    rows = "".join("<tr>" + "".join(f"<td>{html.escape(str(c))}</td>" for c in r) + "</tr>" for r in satirlar)
    return f"<table><thead><tr>{h}</tr></thead><tbody>{rows}</tbody></table>"


def html_rapor(yol: str | Path, proje_adi: str, analiz: dict, yuk: dict, ic: dict, opt: dict, onizleme_png: str,
               dogrulanmali: bool = True) -> str:
    m = metraj(ic, opt, analiz)
    parts = [f"<h1>{html.escape(proje_adi)} - Klima Yerleşim ve Borulama Raporu</h1>",
             f"<p>Tarih: {date.today().isoformat()} · Sistem: <b>{yuk['sistem'].upper()}</b> · Bölge: {yuk['bolge']} "
             f"(katsayı {yuk['katsayi']}) · Toplam yük {yuk['toplam_yuk_kw']} kW · Toplam iç ünite {yuk['toplam_ic_kw']} kW</p>"]
    if dogrulanmali:
        parts.append('<p class="uyari">LG Multi V tabloları ön değerdir (katalogla doğrulanmalı). Sonuçlar ön boyutlandırmadır; '
                     'kesin seçim için LG LATS / üretici seçim yazılımı ile teyit edin.</p>')
    parts.append("<h2>Sistem özeti</h2>")
    ozet = []
    for s in opt["sistemler"]:
        h = s["secilen"]["hesap"]
        du = h.get("du") or {}
        ozet.append([s["id"], s["tip"].upper(), du.get("model", "-"), du.get("kw", "-"), len(s["ic"]), h["toplam_iu_kw"],
                     h["yuk_kw"], f"%{round((h.get('kombinasyon_orani') or 0) * 100)}", h.get("duzeltme_katsayisi"),
                     h["toplam_boru_m"], h.get("en_uzak_esdeger_m", "-"), h.get("toplam_gaz_kg", h["ilave_gaz_kg"]),
                     "UYGUN" if h["uygun"] else "KONTROL ET"])
    parts.append(_tablo(["Sistem", "Tip", "DÜ", "DÜ kW", "İÜ adet", "İÜ toplam kW", "Yük kW", "Kombinasyon", "Düzeltme k",
                         "Toplam boru m", "En uzak eşd. m", "Gaz kg", "Durum"], ozet))
    parts.append(_img(onizleme_png))
    parts.append("<h2>Dış ünite konum karşılaştırması</h2>")
    for s in opt["sistemler"]:
        parts.append(f"<h3>{s['id']}</h3>")
        parts.append(_tablo(["Aday", "Konum türü", "DÜ", "DÜ kW", "Toplam boru m", "En uzak eşd. m", "Düzeltme", "Uygun", "Maliyet endeksi"],
                            [[k["aday"], k["tur"], k["du"], k["du_kw"], k["toplam_boru_m"], k["en_uzak_esdeger_m"], k["duzeltme"],
                              "evet" if k["uygun"] else "hayır", k["maliyet_endeksi"]] for k in s["karsilastirma"]]))
    parts.append("<h2>Odalar ve yük hesabı</h2><p>BTU = alan × bölge katsayısı + kişi × 600</p>")
    parts.append(_tablo(["Oda", "Ad", "Tip", "Alan m²", "Kişi", "BTU", "kW", "Tablo BTU", "İç ünite"],
                        [[o["id"], o["ad"], o["tip"], o["alan_m2"], o["yuk"]["kisi"], o["yuk"]["btu"], o["yuk"]["kw"],
                          o["yuk"]["tablo_btu"] or "-", ", ".join(f"{u['id']} {TIP_AD.get(u['tip'], u['tip'])} {u['kw']} kW" for u in o["uniteler"])]
                         for o in yuk["odalar"]]))
    parts.append("<h2>İç ünite konumları</h2>")
    parts.append(_tablo(["İÜ", "Oda", "Tip", "kW", "Gerekçe"],
                        [[u["id"], u.get("oda_ad", u["oda"]), u["tip"], u["kw"], u["gerekce"]] for u in ic["ic_uniteler"]]))
    parts.append("<h2>Boru hatları</h2>")
    for s in opt["sistemler"]:
        h = s["secilen"]["hesap"]
        parts.append(f"<h3>{s['id']}</h3>")
        parts.append(_tablo(["Hat", "Baş", "Son", "Rol", "Alt kW", "Sıvı", "Gaz", "L m", "Düşey m", "Dirsek", "Eşd. m"],
                            [[g["id"], g["bas"], g["son"], g.get("rol"), g.get("alt_kw"), f"{inch(g['sivi'])} ({g['sivi']})",
                              f"{inch(g['gaz'])} ({g['gaz']})", g["uzunluk_m"], g.get("dikey_m"), g["dirsek"], g.get("esdeger_m")]
                             for g in h["segmentler"]]))
        if h.get("y_branch"):
            parts.append(_tablo(["Y-branch", "Alt yük kW", "Model"], [[y["ad"], y["alt_kw"], y["model"]] for y in h["y_branch"]]))
        parts.append("<h4>Limit kontrolleri</h4>")
        parts.append(_tablo(["Kontrol", "Değer", "Limit", "Durum"],
                            [[c["ad"], c["deger"], c["limit"], "✓" if c["ok"] else "✗ AŞIM"] for c in h["kontroller"]]))
    parts.append("<h2>Metraj özeti</h2>")
    parts.append(_tablo(["Çap", "Net m", f"Fire dahil m (%{int(m['fire'] * 100)})"],
                        [[f"{inch(d)} (Ø{d})", m["boru_net"][d], m["boru"][d]] for d in m["boru"]]))
    uy = analiz.get("uyarilar", []) + ic.get("uyarilar", []) + opt.get("uyarilar", []) + yuk.get("oneriler", [])
    if uy:
        parts.append("<h2>Uyarılar ve öneriler</h2><ul>" + "".join(f"<li>{html.escape(u)}</li>" for u in uy) + "</ul>")
    css = ("body{font-family:Segoe UI,Arial,sans-serif;margin:24px;color:#222;font-size:13px}"
           "h1{color:#1f6f8b}h2{border-bottom:2px solid #1f6f8b;padding-bottom:3px;margin-top:28px}"
           "table{border-collapse:collapse;margin:8px 0;width:100%}th,td{border:1px solid #ccc;padding:4px 6px;text-align:left}"
           "th{background:#1f6f8b;color:#fff}tr:nth-child(even){background:#f4f8fa}.uyari{background:#fff3cd;padding:8px;border-left:4px solid #e0a800}"
           "@media print{img{page-break-inside:avoid}}")
    doc = f"<!DOCTYPE html><html lang='tr'><head><meta charset='utf-8'><title>{html.escape(proje_adi)}</title><style>{css}</style></head><body>{''.join(parts)}</body></html>"
    yol = Path(yol)
    yol.parent.mkdir(parents=True, exist_ok=True)
    yol.write_text(doc, encoding="utf-8")
    return str(yol)
