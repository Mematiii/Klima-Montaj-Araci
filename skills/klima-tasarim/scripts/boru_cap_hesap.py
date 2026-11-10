"""Boru çapı, eşdeğer uzunluk, ilave gaz, kapasite düzeltmesi, DÜ seçimi ve limit kontrolleri."""
from __future__ import annotations

from collections import defaultdict

from ortak import btu_to_kw, tablo_sec, veri

BL = veri("lg_multiv/boru_ve_limitler.json")
DIS = veri("lg_multiv/dis_uniteler.json")
SPLIT = veri("split_boru_caplari.json")

GAZ_SIRASI = [12.7, 15.88, 19.05, 22.2, 28.58, 34.9, 41.3]
INCH = {6.35: '1/4"', 9.52: '3/8"', 12.7: '1/2"', 15.88: '5/8"', 19.05: '3/4"', 22.2: '7/8"',
        25.4: '1"', 28.58: '1 1/8"', 34.9: '1 3/8"', 41.3: '1 5/8"'}


def inch(mm: float) -> str:
    return INCH.get(round(mm, 2), f"Ø{mm}")


def dirsek_esdeger(gaz_mm: float) -> float:
    t = {float(k): v for k, v in BL["dirsek_esdeger_m"].items()}
    k = min(t, key=lambda x: abs(x - gaz_mm))
    return t[k]


def gaz_kg_m(sivi_mm: float, tablo: dict) -> float:
    t = {float(k): v for k, v in tablo.items()}
    k = min(t, key=lambda x: abs(x - sivi_mm))
    return t[k]


def kapasite_duzeltme(leq: float, dh: float) -> float:
    kd = BL["kapasite_duzeltme"]
    k = 1 - kd["egim_1_m"] * max(0.0, leq - kd["referans_m"]) - kd["yukseklik_egim_1_m"] * abs(dh)
    return round(max(kd["min"], min(1.0, k)), 3)


def _kontrol(ad, deger, limit, kucuk_esit=True):
    ok = deger <= limit if kucuk_esit else deger >= limit
    return {"ad": ad, "deger": round(deger, 2), "limit": limit, "ok": bool(ok)}


# ---------------------------------------------------------------- VRF
def vrf_hesapla(rota: dict, iu: dict, du_id: str, ayarlar: dict, yuk_kw: float) -> dict:
    seg = rota["segmentler"]
    dug = rota["dugumler"]
    cocuk = defaultdict(list)
    for s in seg:
        cocuk[s["bas"]].append(s)

    def alt_iu(dugum):
        if dug.get(dugum, {}).get("tip") == "IU":
            return [dugum]
        out = []
        for s in cocuk[dugum]:
            out += alt_iu(s["son"])
        return out

    for s in seg:
        s["alt_iu"] = alt_iu(s["son"])
        s["alt_kw"] = round(sum(iu[i]["kw"] for i in s["alt_iu"]), 2)

    dh = abs(float(ayarlar.get("du_kot_m", 0)) - float(ayarlar.get("iu_kot_m", 0)))
    iu_dusey = float(ayarlar.get("iu_dusey_m", 0.5))
    toplam_iu_kw = sum(iu[i]["kw"] for i in iu if i in dug)
    n_iu = sum(1 for d in dug.values() if d["tip"] == "IU")
    esz = float(ayarlar.get("eszamanlilik", 1.0))

    def boyutla(du_kw):
        ana = tablo_sec(BL["ana_hat_dis_uniteye_gore"], du_kw)
        for s in seg:
            if s["bas"] == du_id:
                s["sivi"], s["gaz"], s["rol"] = ana["sivi"], ana["gaz"], "ana hat"
            elif dug.get(s["son"], {}).get("tip") == "IU":
                t = tablo_sec(BL["ic_unite_baglanti"], iu[s["son"]]["kw"])
                s["sivi"], s["gaz"], s["rol"] = t["sivi"], t["gaz"], "iç ünite bağlantı"
            else:
                t = tablo_sec(BL["brans_hat_alt_yuke_gore"], s["alt_kw"])
                s["sivi"], s["gaz"], s["rol"] = min(t["sivi"], ana["sivi"]), min(t["gaz"], ana["gaz"]), "branş hat"
        _esdeger(seg, du_id, dh, iu_dusey, dug)
        yollar = _yollar(seg, du_id, dug)
        leq_max = max((p["esdeger_m"] for p in yollar.values()), default=0)
        if leq_max > BL["ana_hat_buyutme"]["esdeger_uzunluk_esigi_m"]:
            for s in seg:
                if s["rol"] == "ana hat":
                    i = GAZ_SIRASI.index(s["gaz"]) if s["gaz"] in GAZ_SIRASI else -1
                    if 0 <= i < len(GAZ_SIRASI) - 1:
                        s["gaz"] = GAZ_SIRASI[i + 1]
                        s["not"] = "eşdeğer uzunluk eşiği aşıldığı için gaz hattı bir çap büyütüldü"
            _esdeger(seg, du_id, dh, iu_dusey, dug)
            yollar = _yollar(seg, du_id, dug)
            leq_max = max((p["esdeger_m"] for p in yollar.values()), default=0)
        return yollar, leq_max

    # DÜ seçimi (iteratif: önce kaba boyut)
    yollar, leq_max = boyutla(toplam_iu_kw)
    k = kapasite_duzeltme(leq_max, dh)
    secim, alternatif = du_sec(toplam_iu_kw, yuk_kw * esz, k, n_iu, ayarlar)
    if secim:
        yollar, leq_max = boyutla(secim["kw"])
        k = kapasite_duzeltme(leq_max, dh)
        secim2, alternatif = du_sec(toplam_iu_kw, yuk_kw * esz, k, n_iu, ayarlar)
        if secim2 and secim2["kw"] != secim["kw"]:
            secim = secim2
            yollar, leq_max = boyutla(secim["kw"])
    du_kw = secim["kw"] if secim else toplam_iu_kw

    # Y-branch
    ybr = []
    for ad, d in dug.items():
        if d["tip"] == "Y":
            alt = sum(s["alt_kw"] for s in cocuk[ad])
            ybr.append({"ad": ad, "alt_kw": round(alt, 2), "model": tablo_sec(BL["y_branch"], alt)["model"], "konum": d["konum"]})

    # ilave gaz
    # düşey hatlar (DÜ kot farkı, İÜ inişleri) da sıvı hattıdır; ilave gaza dahil
    ilave = sum((s["uzunluk_m"] + s.get("dikey_m", 0)) * gaz_kg_m(s["sivi"], BL["ilave_gaz_kg_m"]) for s in seg)
    fabrika = secim["fabrika_gaz_kg"] if secim else 0

    # limitler
    prof = BL["profiller"][ayarlar.get("limit_profili", "lg_multiv")]
    mini = du_kw <= BL["mini_vrf_esigi_kw"]
    toplam_L = sum(s["uzunluk_m"] for s in seg) + n_iu * iu_dusey + dh
    kontroller = [
        _kontrol("Toplam boru uzunluğu (m)", toplam_L, prof["toplam_boru_m"]["mini" if mini else "buyuk"]),
        _kontrol("En uzak iç ünite, gerçek (m)", max((p["gercek_m"] for p in yollar.values()), default=0), prof["en_uzak_gercek_m"]),
        _kontrol("En uzak iç ünite, eşdeğer (m)", leq_max, prof["en_uzak_esdeger_m"]),
        _kontrol("DÜ-İÜ yükseklik farkı (m)", dh, prof["yukseklik_du_iu_m"]),
    ]
    ilk_y = None
    for s in seg:
        if s["bas"] == du_id and dug.get(s["son"], {}).get("tip") == "Y":
            ilk_y = s
    if ilk_y is not None:
        if "ilk_bransmana_kadar_m" in prof:
            kontroller.append(_kontrol("DÜ -> ilk branşman (m)", ilk_y["uzunluk_m"] + dh, prof["ilk_bransmana_kadar_m"]))
        if "ilk_bransmandan_en_uzaga_m" in prof:
            en = max((p["gercek_m"] - ilk_y["uzunluk_m"] - dh for p in yollar.values()), default=0)
            kontroller.append(_kontrol("İlk branşmandan en uzak İÜ'ye (m)", en, prof["ilk_bransmandan_en_uzaga_m"]))
    yy = [s for s in seg if dug.get(s["bas"], {}).get("tip") == "Y" and dug.get(s["son"], {}).get("tip") == "Y"]
    if yy:
        kontroller.append(_kontrol("Branşmanlar arası en kısa (m)", min(s["uzunluk_m"] for s in yy), prof["brans_arasi_min_m"], kucuk_esit=False))
    son = [s for s in seg if dug.get(s["son"], {}).get("tip") == "IU" and s["bas"] != du_id]
    if son:
        kontroller.append(_kontrol("Branşman sonrası en uzun hat (m)", max(s["uzunluk_m"] + iu_dusey for s in son), prof["brans_sonrasi_max_m"]))
    oran = toplam_iu_kw / du_kw if du_kw else 0
    kontroller.append(_kontrol("Kombinasyon oranı (%)", oran * 100, 130))
    kontroller.append(_kontrol("Kombinasyon oranı alt sınır (%)", oran * 100, 50, kucuk_esit=False))
    if secim:
        kontroller.append(_kontrol("Düzeltilmiş DÜ kapasitesi >= yük (kW)", du_kw * k, round(yuk_kw * esz, 2), kucuk_esit=False))
    return {
        "tip": "vrf", "du": secim, "du_alternatif": alternatif, "duzeltme_katsayisi": k,
        "toplam_iu_kw": round(toplam_iu_kw, 2), "yuk_kw": round(yuk_kw, 2), "eszamanlilik": esz,
        "kombinasyon_orani": round(oran, 3), "segmentler": seg, "yollar": yollar, "y_branch": ybr,
        "toplam_boru_m": round(toplam_L, 1), "en_uzak_esdeger_m": round(leq_max, 1), "yukseklik_farki_m": dh,
        "ilave_gaz_kg": round(ilave, 2), "fabrika_gaz_kg": fabrika, "toplam_gaz_kg": round(ilave + fabrika, 2),
        "kontroller": kontroller, "uygun": all(c["ok"] for c in kontroller) and secim is not None,
    }


def _esdeger(seg, du_id, dh, iu_dusey, dug):
    for s in seg:
        ek = s["dirsek"] * dirsek_esdeger(s["gaz"])
        if dug.get(s["bas"], {}).get("tip") == "Y":
            ek += BL["y_branch_esdeger_m"]
        dikey = (dh if s["bas"] == du_id else 0) + (iu_dusey if dug.get(s["son"], {}).get("tip") == "IU" else 0)
        s["dikey_m"] = round(dikey, 2)
        s["esdeger_m"] = round(s["uzunluk_m"] + dikey + ek + (1 if dikey else 0) * dirsek_esdeger(s["gaz"]) * 2, 2)


def _yollar(seg, du_id, dug):
    ebeveyn = {s["son"]: s for s in seg}
    out = {}
    for ad, d in dug.items():
        if d["tip"] != "IU":
            continue
        g = e = 0.0
        n = ad
        while n in ebeveyn:
            s = ebeveyn[n]
            g += s["uzunluk_m"] + s["dikey_m"]
            e += s["esdeger_m"]
            n = s["bas"]
        out[ad] = {"gercek_m": round(g, 2), "esdeger_m": round(e, 2)}
    return out


def du_sec(toplam_iu_kw: float, gereken_kw: float, k: float, n_iu: int, ayarlar: dict, seri: str | None = None):
    """Kombinasyon oranı ve düzeltilmiş kapasiteyi sağlayan en ucuz DÜ."""
    if seri:
        seriler = [seri]
    elif ayarlar.get("du_serisi"):
        seriler = [ayarlar["du_serisi"]]
    else:
        seriler = ["multi_v_s", "multi_v_5"]
    uygunlar = []
    for sad in seriler:
        s = DIS["seriler"][sad]
        for m in s["modeller"]:
            oran = toplam_iu_kw / m["kw"]
            maxn = s["max_ic_unite"].get(str(m["kw"]), 999)
            if s["kombinasyon_min"] <= oran <= s["kombinasyon_max"] and m["kw"] * k >= gereken_kw and n_iu <= maxn:
                uygunlar.append(dict(m, seri=s["ad"], oran=round(oran, 3)))
    uygunlar.sort(key=lambda m: (m["fiyat_endeksi"], m["kw"]))
    if not uygunlar:
        return None, []
    return uygunlar[0], uygunlar[1:3]


# ---------------------------------------------------------------- split / multi
def split_cap(btu: int) -> dict:
    t = SPLIT["tablo"]
    satir = next((s for s in t if s["btu"] >= btu), t[-1])
    mm = SPLIT["inch_mm"]
    return {"sivi": mm[satir["sivi"]], "gaz": mm[satir["gaz"]],
            "alternatif": satir.get("alternatif_gaz") or satir.get("alternatif_sivi")}


def split_hesapla(rota: dict, iu: dict, ayarlar: dict, tip: str, yuk_kw: float) -> dict:
    seg = rota["segmentler"]
    dh = abs(float(ayarlar.get("du_kot_m", 0)) - float(ayarlar.get("iu_kot_m", 0)))
    iu_dusey = float(ayarlar.get("iu_dusey_m", 0.5))
    lim = SPLIT["limitler"]
    kontroller, ilave = [], 0.0
    for s in seg:
        u = iu[s["son"]]
        c = split_cap(u["btu"])
        s["sivi"], s["gaz"], s["rol"] = c["sivi"], c["gaz"], "split hat"
        if c["alternatif"]:
            s["not"] = f"tabloda alternatif çap: {c['alternatif']}"
        s["alt_iu"] = [s["son"]]
        s["alt_kw"] = u["kw"]
        s["dikey_m"] = round(dh + iu_dusey, 2)
        s["esdeger_m"] = round(s["uzunluk_m"] + s["dikey_m"] + s["dirsek"] * 0.3, 2)
        L = s["uzunluk_m"] + s["dikey_m"]
        anahtarlar = sorted(int(k) for k in lim["max_boru_m"])
        anahtar = str(next((k for k in anahtarlar if k >= u["btu"]), anahtarlar[-1]))
        if L < lim["min_boru_m"]:
            s["not"] = (s.get("not", "") + f" minimum {lim['min_boru_m']} m boru için {lim['min_boru_m'] - L:.1f} m kangal/serpantin bırakılmalı").strip()
            s["uzunluk_m"] = round(s["uzunluk_m"] + lim["min_boru_m"] - L, 2)
            L = lim["min_boru_m"]
        if tip == "split":
            kontroller.append(_kontrol(f"{s['son']} boru uzunluğu (m)", L, lim["max_boru_m"][anahtar]))
            kontroller.append(_kontrol(f"{s['son']} yükseklik farkı (m)", dh, lim["max_yukseklik_m"][anahtar]))
        ilave += max(0.0, L - lim["fabrika_dolum_m"]) * gaz_kg_m(s["sivi"], lim["ilave_gaz_kg_m"])
    toplam_iu_kw = sum(iu[s["son"]]["kw"] for s in seg)
    sonuc = {"tip": tip, "segmentler": seg, "toplam_iu_kw": round(toplam_iu_kw, 2), "yuk_kw": round(yuk_kw, 2),
             "toplam_boru_m": round(sum(s["uzunluk_m"] + s["dikey_m"] for s in seg), 1), "yukseklik_farki_m": dh,
             "ilave_gaz_kg": round(ilave, 2), "y_branch": [], "duzeltme_katsayisi": 1.0}
    if tip == "split":
        u = iu[seg[0]["son"]] if seg else None
        std = [9000, 12000, 18000, 24000, 36000, 48000]
        btu = next((b for b in std if u and b >= u["btu"] * 0.97), 48000) if u else 0
        sonuc["du"] = {"model": f"Split DÜ {btu} BTU" if u else "-", "kw": u["kw"] if u else 0,
                       "fiyat_endeksi": btu / 1000, "fabrika_gaz_kg": 0}
        sonuc["kombinasyon_orani"] = 1.0
    else:
        prof = BL["profiller"]["multi_f"]
        for s in seg:
            kontroller.append(_kontrol(f"{s['son']} hat uzunluğu (m)", s["uzunluk_m"] + s["dikey_m"], prof["tek_hat_max_m"]))
        kontroller.append(_kontrol("Toplam boru (m)", sonuc["toplam_boru_m"], prof["toplam_boru_m"]["mini"]))
        secim, alt = du_sec(toplam_iu_kw, yuk_kw * float(ayarlar.get("eszamanlilik", 1.0)), 1.0, len(seg), ayarlar, seri="multi_f")
        sonuc["du"], sonuc["du_alternatif"] = secim, alt
        sonuc["kombinasyon_orani"] = round(toplam_iu_kw / secim["kw"], 3) if secim else None
        if secim:
            sonuc["fabrika_gaz_kg"] = secim["fabrika_gaz_kg"]
        else:
            kontroller.append({"ad": "Uygun multi-split DÜ", "deger": toplam_iu_kw, "limit": "katalog", "ok": False})
    sonuc["kontroller"] = kontroller
    sonuc["toplam_gaz_kg"] = round(sonuc["ilave_gaz_kg"] + (sonuc.get("fabrika_gaz_kg") or 0), 2)
    sonuc["uygun"] = all(c["ok"] for c in kontroller) and sonuc.get("du") is not None
    return sonuc
