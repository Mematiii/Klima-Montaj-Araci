"""Her sistem için DÜ adaylarını dener: güzergah + çap + DÜ seçimi; en düşük maliyetli uygun çözümü seçer.

Maliyet (göreli endeks) = DÜ fiyat endeksi + toplam boru (m) x boru_m_endeks + Y-branch adedi x 2
Limitleri aşan çözümler büyük ceza alır. Daha kısa boru -> daha yüksek düzeltme katsayısı -> daha küçük DÜ.
"""
from __future__ import annotations

from borulama import Izgara, rota_ayri, rota_vrf
from boru_cap_hesap import split_hesapla, vrf_hesapla


def iu_yukleri(yuk: dict) -> dict:
    out = {}
    for o in yuk["odalar"]:
        n = len(o["uniteler"])
        for u in o["uniteler"]:
            out[u["id"]] = o["yuk"]["kw"] / n
    return out


def calistir(analiz: dict, yuk: dict, ic: dict, dis: dict, ayarlar: dict, sabit_aday: dict | None = None) -> dict:
    """sabit_aday: {sistem_id: aday_indeksi} -> kullanıcının seçtiği DÜ adayı."""
    sabit_aday = sabit_aday or {}
    iu = {u["id"]: u for u in ic["ic_uniteler"]}
    iu_yuk = iu_yukleri(yuk)
    ek = [a["konum"] for s in dis["sistemler"] for a in s.get("adaylar", [])]
    iz = Izgara(analiz, ek, ayarlar)
    boru_endeks = float(ayarlar.get("boru_m_endeks", 0.6))
    sistemler, uyarilar = [], []
    for s in dis["sistemler"]:
        iu_list = [iu[i] for i in s["ic"]]
        yuk_kw = sum(iu_yuk.get(i, iu[i]["kw"]) for i in s["ic"])
        denemeler = []
        adaylar = s.get("adaylar", [])
        indeksler = [sabit_aday[s["id"]]] if s["id"] in sabit_aday else range(len(adaylar))
        for i in indeksler:
            aday = adaylar[i]
            du = dict(aday, id=f"{s['id']}-DU")
            iz.kur(iz.kiris_yasak)
            if s["tip"] == "vrf":
                rota, uy = rota_vrf(iz, du, iu_list, donus_ceza=float(ayarlar.get("donus_ceza_m", 1.0)))
                h = vrf_hesapla(rota, iu, du["id"], ayarlar, yuk_kw)
            else:
                rota, uy = rota_ayri(iz, du, iu_list, donus_ceza=float(ayarlar.get("donus_ceza_m", 1.0)))
                h = split_hesapla(rota, iu, ayarlar, s["tip"], yuk_kw)
            bagli = sum(1 for d in rota["dugumler"].values() if d["tip"] == "IU")
            du_endeks = (h.get("du") or {}).get("fiyat_endeksi", 500)
            maliyet = du_endeks + h["toplam_boru_m"] * boru_endeks + 2 * len(h.get("y_branch", []))
            if not h["uygun"]:
                maliyet += 1000
            if bagli < len(iu_list):
                maliyet += 5000
            denemeler.append({"aday_indeksi": i, "du_konum": du, "rota": rota, "hesap": h, "uyarilar": uy,
                              "maliyet_endeksi": round(maliyet, 1)})
        if not denemeler:
            uyarilar.append(f"{s['id']}: DÜ adayı yok, hesap yapılamadı.")
            continue
        denemeler.sort(key=lambda d: d["maliyet_endeksi"])
        en = denemeler[0]
        karsilastirma = [{"aday": d["aday_indeksi"] + 1, "tur": d["du_konum"]["tur"],
                          "du": (d["hesap"].get("du") or {}).get("model", "-"),
                          "du_kw": (d["hesap"].get("du") or {}).get("kw"),
                          "toplam_boru_m": d["hesap"]["toplam_boru_m"],
                          "en_uzak_esdeger_m": d["hesap"].get("en_uzak_esdeger_m"),
                          "duzeltme": d["hesap"].get("duzeltme_katsayisi"),
                          "uygun": d["hesap"]["uygun"], "maliyet_endeksi": d["maliyet_endeksi"]} for d in denemeler]
        sistemler.append({"id": s["id"], "tip": s["tip"], "ic": s["ic"], "secilen": en, "karsilastirma": karsilastirma})
        uyarilar += [f"{s['id']}: {u}" for u in en["uyarilar"]]
    return {"izgara_m": iz.res, "sistemler": sistemler, "uyarilar": uyarilar}
