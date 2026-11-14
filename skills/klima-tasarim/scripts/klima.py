"""klima-tasarim komut satırı aracı.

Kullanım (her komut --proje KLASOR ister):
  py klima.py durum
  py klima.py baslat PLAN.dwg --proje KLASOR [--ad "Proje adı"]
  py klima.py ayar --proje KLASOR bolge=marmara sistem_tipi=vrf du_kot_m=3 ...
  py klima.py analiz --proje KLASOR [--ada N | --bbox x0 y0 x1 y1] [--yeniden-cikar]
  py klima.py yuk    --proje KLASOR
  py klima.py ic     --proje KLASOR
  py klima.py dis    --proje KLASOR
  py klima.py boru   --proje KLASOR
  py klima.py cikti  --proje KLASOR [--kutuphane BLOKLAR.dxf]
  py klima.py hepsi  --proje KLASOR      (yuk -> cikti arası tüm adımlar, kontrol noktası olmadan)
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from ortak import Proje, hata, json_oku, json_yaz  # noqa: E402


def _yazdir(baslik, satirlar):
    print(f"\n== {baslik} ==")
    for s in satirlar:
        print(s)


def cmd_durum(a):
    import dwg_io
    print(json.dumps(dwg_io.durum(), indent=1, ensure_ascii=False))


def cmd_baslat(a):
    import dwg_io
    import onizleme
    import plan_cikar
    p = Proje(a.proje)
    girdi = Path(a.dosya).resolve()
    dxf = dwg_io.dwg_to_dxf(girdi, p.klasor / "kaynak")
    p.d["kaynak_dosya"] = str(girdi)
    p.d["kaynak_dxf"] = str(dxf)
    p.d["proje_adi"] = a.ad or girdi.stem
    plan = plan_cikar.cikar(dxf, p.ayar.get("olcek"), p.d.get("katman_duzeltme"))
    json_yaz(p.klasor / "plan.json", plan)
    png = onizleme.adalar(plan, p.dosya("onizleme", "0_adalar.png"))
    p.adim_yaz("baslat", {"dxf": str(dxf), "olcek": plan["olcek"], "adalar": plan["adalar"], "onizleme": png})
    _katman_ozeti(plan)
    _yazdir("Çizim adaları", [f"ADA {x['id']}: {x['baslik'] or '(başlıksız)'} tür={x['tur']} alan={x['alan']} m² bbox={x['bbox']}"
                              for x in plan["adalar"]])
    print(f"\nBirim tahmini: {plan['birim_tahmini']} (ölçek {plan['olcek']} m/birim)\nÖnizleme: {png}")


def _katman_ozeti(plan):
    sat = []
    for ad, k in list(plan["katmanlar"].items())[:80]:
        sat.append(f"{k['kategori']:>9} | {k['adet']:>6} | {ad}")
    _yazdir("Katmanlar (kategori | varlık | ad) - 'diger' olanlar gerekirse katman_duzeltme ile sınıflandırılmalı", sat)
    nes = {}
    for n in plan["nesneler"]:
        nes[n["kategori"]] = nes.get(n["kategori"], 0) + 1
    _yazdir("Blok nesneleri", [f"{k}: {v}" for k, v in nes.items()] or ["(yok)"])


def cmd_ayar(a):
    p = Proje(a.proje)
    for kv in a.ciftler:
        if "=" not in kv:
            hata(f"Geçersiz: {kv} (anahtar=deger)")
        k, v = kv.split("=", 1)
        try:
            v = json.loads(v)
        except json.JSONDecodeError:
            pass
        p.ayar[k] = v
    p.kaydet()
    print(json.dumps(p.ayar, indent=1, ensure_ascii=False))


def cmd_analiz(a):
    import oda_bul
    import onizleme
    import plan_cikar
    p = Proje(a.proje)
    if a.yeniden_cikar:
        plan = plan_cikar.cikar(p.d["kaynak_dxf"], p.ayar.get("olcek"), p.d.get("katman_duzeltme"))
        json_yaz(p.klasor / "plan.json", plan)
    plan = p.plan()
    bbox = None
    if a.bbox:
        bbox = a.bbox
    elif a.ada:
        ada = next((x for x in plan["adalar"] if x["id"] == a.ada), None)
        if not ada:
            hata(f"ADA {a.ada} yok")
        bbox = ada["bbox"]
    elif p.adim("analiz") and p.adim("analiz").get("bbox"):
        bbox = p.adim("analiz")["bbox"]
    elif len(plan["adalar"]) > 1:
        print("UYARI: birden fazla çizim adası var, en büyüğü kullanılıyor. --ada ile seçin.")
        bbox = plan["adalar"][0]["bbox"]
    if bbox:
        bbox = [bbox[0] - 3, bbox[1] - 3, bbox[2] + 3, bbox[3] + 3]
    sonuc = oda_bul.odalari_bul(plan, bbox, kapama_r=float(p.ayar.get("kapi_kapama_m", 0.55)),
                                duvar_haric=p.ayar.get("duvar_haric"))
    # kullanıcı oda düzeltmeleri (ad/tip) bu adımda görünür olsun
    for o in sonuc["odalar"]:
        d = p.d.get("oda_ayarlari", {}).get(o["id"], {})
        if "tip_ad" in d:
            o["tip"] = d["tip_ad"]
        if "ad" in d:
            o["ad"] = d["ad"]
    json_yaz(p.klasor / "analiz.json", sonuc)
    png = onizleme.odalar(sonuc, p.dosya("onizleme", "1_odalar.png"))
    p.adim_yaz("analiz", {"bbox": bbox, "oda_sayisi": len(sonuc["odalar"]), "onizleme": png})
    _yazdir("Odalar", [f"{o['id']:>4} | {o['tip']:<10} | {o['alan_m2']:>6.1f} m² | pencere {o['pencere_sayisi']} | "
                       f"{'dış cephe' if o['dis_cephe'] else 'iç'} | {o['ad']}" for o in sonuc["odalar"]])
    from collections import Counter
    katman_say = Counter(d["tip"] for d in sonuc["dis_alanlar"] if d.get("kaynak") == "katman")
    dis = [f"{t}: {n} çizim parçası (katmandan)" for t, n in katman_say.items()]
    dis += [f"{d['tip']}: {d.get('ad')}" for d in sonuc["dis_alanlar"] if d.get("kaynak") != "katman"][:30]
    _yazdir("Dış alanlar", dis or ["(yok)"])
    _yazdir("Uyarılar", sonuc["uyarilar"] or ["(yok)"])
    print(f"\nÖnizleme: {png}")


def _analiz(p):
    yol = p.klasor / "analiz.json"
    if not yol.exists():
        hata("Önce 'analiz' çalıştırın.")
    return json_oku(yol)


def cmd_yuk(a):
    import yuk_hesap
    p = Proje(a.proje)
    try:
        s = yuk_hesap.hesapla(_analiz(p), p.ayar, p.d.get("oda_ayarlari", {}))
    except ValueError as e:
        hata(str(e))
    json_yaz(p.klasor / "yuk.json", s)
    p.adim_yaz("yuk", {"sistem": s["sistem"], "toplam_ic_kw": s["toplam_ic_kw"]})
    _yazdir(f"Yük hesabı - bölge {s['bolge']} ({s['katsayi']}), sistem {s['sistem'].upper()} (öneri: {s['sistem_onerisi']})",
            [f"{o['id']:>4} | {o['ad'][:20]:<20} | {o['alan_m2']:>6.1f} m² | {o['yuk']['kisi']} kişi | x{o['yuk'].get('carpan', 1.0):.2f} | {o['yuk']['btu']:>6} BTU "
             f"({o['yuk']['kw']} kW) | tablo {o['yuk']['tablo_btu'] or '-'} | "
             + ", ".join(f"{u['id']} {u['tip']} {u['kw']}kW/{u['btu']}BTU" for u in o["uniteler"]) for o in s["odalar"]])
    print(f"\nToplam yük {s['toplam_yuk_kw']} kW, toplam iç ünite {s['toplam_ic_kw']} kW")
    print(f"Sistem gerekçesi: {s['sistem_gerekce']}")
    _yazdir("Öneriler", s["oneriler"] or ["(yok)"])


def cmd_ic(a):
    import ic_unite_yerlestir
    import onizleme
    p = Proje(a.proje)
    analiz = _analiz(p)
    yuk = json_oku(p.klasor / "yuk.json")
    s = ic_unite_yerlestir.yerlestir(analiz, yuk, p.plan(), p.d.get("elle_konum", {}))
    json_yaz(p.klasor / "ic.json", s)
    png = onizleme.ic_uniteler(analiz, s, p.dosya("onizleme", "2_ic_uniteler.png"))
    p.adim_yaz("ic", {"adet": len(s["ic_uniteler"]), "onizleme": png})
    _yazdir("İç üniteler", [f"{u['id']:>4} | {u.get('oda_ad', '')[:18]:<18} | {u['tip']:<6} {u['kw']} kW | konum {u['konum']} | {u['gerekce']}"
                            for u in s["ic_uniteler"]])
    _yazdir("Uyarılar", s["uyarilar"] or ["(yok)"])
    print(f"\nÖnizleme: {png}")


def cmd_dis(a):
    import dis_unite_yerlestir
    import onizleme
    p = Proje(a.proje)
    analiz = _analiz(p)
    yuk = json_oku(p.klasor / "yuk.json")
    ic = json_oku(p.klasor / "ic.json")
    s = dis_unite_yerlestir.yerlestir(analiz, yuk, ic, p.ayar, p.d.get("elle_konum", {}))
    json_yaz(p.klasor / "dis.json", s)
    png = onizleme.dis_uniteler(analiz, ic, s, p.dosya("onizleme", "3_dis_unite.png"))
    p.adim_yaz("dis", {"sistem_sayisi": len(s["sistemler"]), "onizleme": png})
    sat = []
    for g in s["sistemler"]:
        sat.append(f"{g['id']} ({g['tip']}) iç üniteler: {', '.join(g['ic'])}")
        for i, ad in enumerate(g.get("adaylar", [])):
            not_ = f" | {'; '.join(ad['notlar'])}" if ad.get("notlar") else ""
            sat.append(f"    aday {i + 1}: {ad['tur']:<7} konum {ad['konum']} tahmini boru ~{ad.get('tahmini_boru_m')} m{not_}")
    _yazdir("Dış ünite adayları", sat)
    _yazdir("Uyarılar", s["uyarilar"] or ["(yok)"])
    print(f"\nÖnizleme: {png}")


def cmd_boru(a):
    import onizleme
    import optimize
    p = Proje(a.proje)
    analiz = _analiz(p)
    yuk = json_oku(p.klasor / "yuk.json")
    ic = json_oku(p.klasor / "ic.json")
    dis = json_oku(p.klasor / "dis.json")
    secim = {k: int(v) - 1 for k, v in p.d.get("du_aday_secimi", {}).items()}
    s = optimize.calistir(analiz, yuk, ic, dis, p.ayar, secim)
    json_yaz(p.klasor / "boru.json", s)
    png = onizleme.borulama(analiz, ic, s, p.dosya("onizleme", "4_borulama.png"))
    p.adim_yaz("boru", {"onizleme": png})
    for sis in s["sistemler"]:
        h = sis["secilen"]["hesap"]
        du = h.get("du") or {}
        _yazdir(f"{sis['id']} ({sis['tip'].upper()}) - seçilen aday {sis['secilen']['aday_indeksi'] + 1} "
                f"({sis['secilen']['du_konum']['tur']})",
                [f"DÜ: {du.get('model', 'UYGUN DÜ YOK')} {du.get('kw', '')} kW | İÜ toplam {h['toplam_iu_kw']} kW | yük {h['yuk_kw']} kW | "
                 f"oran %{round((h.get('kombinasyon_orani') or 0) * 100)} | düzeltme k={h.get('duzeltme_katsayisi')}",
                 f"Toplam boru {h['toplam_boru_m']} m | en uzak eşdeğer {h.get('en_uzak_esdeger_m', '-')} m | "
                 f"ilave gaz {h['ilave_gaz_kg']} kg | Y-branch {len(h.get('y_branch', []))}"]
                + [f"  {g['id']:>4} {g['bas']}->{g['son']:<6} {g.get('sivi')}/{g.get('gaz')} L={g['uzunluk_m']} m dirsek={g['dirsek']} eşd={g.get('esdeger_m')}"
                   for g in h["segmentler"]]
                + [f"  [{'OK' if c['ok'] else 'AŞIM'}] {c['ad']}: {c['deger']} (limit {c['limit']})" for c in h["kontroller"]]
                + ["  Aday karşılaştırma:"]
                + [f"    aday {k['aday']} {k['tur']:<7} DÜ {k['du']} ({k['du_kw']} kW) boru {k['toplam_boru_m']} m "
                   f"k={k['duzeltme']} uygun={k['uygun']} maliyet={k['maliyet_endeksi']}" for k in sis["karsilastirma"]])
    _yazdir("Uyarılar", s["uyarilar"] or ["(yok)"])
    print(f"\nÖnizleme: {png}")


def cmd_cikti(a):
    import cizim_yaz
    import dwg_io
    import rapor
    p = Proje(a.proje)
    analiz = _analiz(p)
    yuk = json_oku(p.klasor / "yuk.json")
    ic = json_oku(p.klasor / "ic.json")
    opt = json_oku(p.klasor / "boru.json")
    plan = p.plan()
    ad = p.d.get("proje_adi", "Proje")
    kutuphane = a.kutuphane or p.ayar.get("blok_kutuphanesi_dxf")
    if kutuphane:
        # Kütüphane bir kez işlenir: DWG ise DXF'e çevrilir (92 MB DWG -> ~450 MB DXF), sonra yalnız eşlenen
        # bloklar küçük bir önbellek DXF'ine alınır. Eşleme (blok_eslesme.json) değişirse önbellek yenilenir.
        kaynak = Path(kutuphane)
        onbellek = kaynak.with_name(kaynak.stem + ".klima_bloklar.dxf")
        es_yol = Path(__file__).resolve().parent.parent / "data" / "blok_eslesme.json"
        guncel = onbellek.exists() and onbellek.stat().st_mtime > max(kaynak.stat().st_mtime, es_yol.stat().st_mtime)
        if not guncel:
            print("Blok kütüphanesi hazırlanıyor (bir kez, birkaç dakika sürebilir)...")
            import tempfile
            with tempfile.TemporaryDirectory() as td:
                buyuk = dwg_io.dwg_to_dxf(kaynak, Path(td)) if kaynak.suffix.lower() == ".dwg" else kaynak
                cizim_yaz.kucuk_kutuphane(str(buyuk), str(onbellek))
        kutuphane = str(onbellek)
    gizle = str(p.ayar.get("mevcut_klima_gizle", "evet")).lower() not in ("hayir", "hayır", "0", "false", "no")
    dxf = cizim_yaz.yaz(p.d["kaynak_dxf"], str(p.dosya("cikti", f"{ad}_klima.dxf")), plan["olcek"], ic, opt, kutuphane,
                        mevcut_gizle=gizle, du_kot_m=float(p.ayar.get("du_kot_m", 0) or 0))
    dwg = dwg_io.dxf_to_dwg(dxf, p.klasor / "cikti")
    xlsx = rapor.excel(p.dosya("cikti", f"{ad}_malzeme_teklif.xlsx"), ad, yuk, ic, opt, analiz)
    htm = rapor.html_rapor(p.dosya("cikti", f"{ad}_rapor.html"), ad, analiz, yuk, ic, opt,
                           str(p.klasor / "onizleme" / "4_borulama.png"))
    p.adim_yaz("cikti", {"dxf": dxf, "dwg": str(dwg) if dwg else None, "excel": xlsx, "rapor": htm})
    _yazdir("Çıktılar", [f"DXF : {dxf}", f"DWG : {dwg or '(dönüştürücü yok, DXF kullanın)'}", f"Excel: {xlsx}", f"Rapor: {htm}"])


def cmd_hepsi(a):
    for f in (cmd_yuk, cmd_ic, cmd_dis, cmd_boru, cmd_cikti):
        f(a)


def main():
    ap = argparse.ArgumentParser(description="Klima yerleşim ve borulama aracı")
    alt = ap.add_subparsers(dest="komut", required=True)
    alt.add_parser("durum")
    b = alt.add_parser("baslat")
    b.add_argument("dosya")
    b.add_argument("--proje", required=True)
    b.add_argument("--ad")
    ay = alt.add_parser("ayar")
    ay.add_argument("--proje", required=True)
    ay.add_argument("ciftler", nargs="*")
    an = alt.add_parser("analiz")
    an.add_argument("--proje", required=True)
    an.add_argument("--ada", type=int)
    an.add_argument("--bbox", type=float, nargs=4)
    an.add_argument("--yeniden-cikar", action="store_true")
    for k in ("yuk", "ic", "dis", "boru", "hepsi"):
        x = alt.add_parser(k)
        x.add_argument("--proje", required=True)
        if k == "hepsi":
            x.add_argument("--kutuphane")
    c = alt.add_parser("cikti")
    c.add_argument("--proje", required=True)
    c.add_argument("--kutuphane")
    a = ap.parse_args()
    {"durum": cmd_durum, "baslat": cmd_baslat, "ayar": cmd_ayar, "analiz": cmd_analiz, "yuk": cmd_yuk, "ic": cmd_ic,
     "dis": cmd_dis, "boru": cmd_boru, "cikti": cmd_cikti, "hepsi": cmd_hepsi}[a.komut](a)


if __name__ == "__main__":
    main()
