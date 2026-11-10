"""Oda bazında soğutma yükü, iç ünite tipi/kapasitesi seçimi, sistem tipi önerisi.

BTU = alan_m2 * bölge_katsayısı * kullanım_çarpanı + kişi * 600
(kullanım çarpanı: data/oda_tipleri.json 'yuk_carpani'; konut 1.0, ofis 1.3, mağaza 1.35 ...)
Kullanıcı/müşteri verdiği tip ve kapasiteyi 'oda_ayarlari' ile zorlar; skill yine de öneri üretir.
"""
from __future__ import annotations

import math

from ortak import btu_to_kw, kw_to_btu, veri

BOLGE = veri("bolgeler.json")
ODA_TABLO = veri("oda_btu_tablosu.json")
IC = veri("lg_multiv/ic_uniteler.json")
DIS = veri("lg_multiv/dis_uniteler.json")
ODA_TIPLERI = veri("oda_tipleri.json")["tipler"]

SPLIT_BTU = [9000, 12000, 18000, 24000]
SALON_BTU = [36000, 48000]


def kisi_sayisi(oda: dict) -> int:
    t = ODA_TIPLERI.get(oda["tip"], {})
    if "kisi_m2" in t:
        return max(1, round(oda["alan_m2"] / t["kisi_m2"]))
    return int(t.get("kisi", 2))


def tablo_btu(alan: float) -> int | None:
    for s in ODA_TABLO["tablo"]:
        if s["min_m2"] <= alan < s["max_m2"]:
            return s["btu"]
    return None


def kw_sec(tip: str, kw: float) -> float:
    for k in IC["tipler"][tip]["kw"]:
        if k >= kw - 1e-6:
            return k
    return IC["tipler"][tip]["kw"][-1]


def yuk_carpani(oda: dict, ayar: dict, genel: dict | None = None) -> float:
    """Alan terimine uygulanan kullanım çarpanı. Öncelik: oda ayarı > proje geneli > oda tipi varsayılanı.

    Bölge katsayısı konut içindir; cam cepheli, iç yükü yüksek ticari alanlarda (mağaza, ofis) gerçek
    projeler ~1,3-1,4 kat kapasite kullanıyor (örnek: istasyon marketi 117 m² -> 2x36000 BTU).
    """
    if "yuk_carpani" in ayar:
        return float(ayar["yuk_carpani"])
    if genel and genel.get("yuk_carpani") not in (None, ""):
        return float(genel["yuk_carpani"])
    return float(ODA_TIPLERI.get(oda["tip"], {}).get("yuk_carpani", 1.0))


def oda_yuk(oda: dict, katsayi: float, ayar: dict, genel: dict | None = None) -> dict:
    kisi = ayar.get("kisi", kisi_sayisi(oda))
    alan = ayar.get("alan_m2", oda["alan_m2"])
    carpan = yuk_carpani(oda, ayar, genel)
    btu = alan * katsayi * carpan + kisi * BOLGE["kisi_basina_btu"]
    return {"alan": alan, "kisi": kisi, "carpan": carpan, "btu": round(btu), "kw": round(btu_to_kw(btu), 2),
            "tablo_btu": tablo_btu(alan)}


def uniteleri_sec(oda: dict, yuk: dict, sistem: str, ayar: dict) -> tuple[list[dict], list[str]]:
    oneriler = []
    varsayilan_tip = ODA_TIPLERI.get(oda["tip"], {}).get("tercih_tip", "duvar")
    tip = ayar.get("tip", varsayilan_tip)
    if sistem in ("split", "multi") and tip in ("kaset4", "kanal") and oda["alan_m2"] < 40 and "tip" not in ayar:
        tip = "duvar"
    elif tip in ("kaset4", "kanal") and oda["alan_m2"] < 15 and "tip" not in ayar:
        tip = "duvar"  # küçük odada (ör. 7 m² mescit) kaset/kanallı gereksiz: duvar tipi yeter
    zorla_btu = ayar.get("btu")
    zorla_kw = ayar.get("kw")
    adet = ayar.get("adet")
    yuk_kw = yuk["kw"]

    if sistem == "split":
        if zorla_btu:
            btu_list = [zorla_btu] * (adet or 1)
        else:
            if yuk["btu"] <= 24000 * 1.05 and tip in ("duvar",):
                b = next((x for x in SPLIT_BTU if x >= yuk["btu"] * 0.95), 24000)
                btu_list = [b] * (adet or 1)
            elif tip in ("salon", "kaset4") or yuk["btu"] > 24000:
                if yuk["btu"] <= 48000 and not adet:
                    tip = "salon" if tip == "duvar" else tip
                    b = next(x for x in SALON_BTU + [48000] if x >= yuk["btu"] * 0.95)
                    btu_list = [b]
                else:
                    n = adet or math.ceil(yuk["btu"] / 24000)
                    b = next((x for x in SPLIT_BTU if x >= yuk["btu"] / n * 0.95), 24000)
                    btu_list = [b] * n
            else:
                btu_list = [24000]
        uniteler = [{"tip": tip, "btu": b, "kw": IC["split_btu_kw"].get(str(b), round(btu_to_kw(b), 1))} for b in btu_list]
    else:
        maxkw = IC["tipler"][tip]["kw"][-1]
        if zorla_kw or zorla_btu:
            k = zorla_kw or round(btu_to_kw(zorla_btu), 1)
            n = adet or 1
            uniteler = [{"tip": tip, "kw": kw_sec(tip, k), "btu": round(kw_to_btu(kw_sec(tip, k)), -2)} for _ in range(n)]
        else:
            n = adet or max(1, math.ceil(yuk_kw / maxkw - 0.05))
            # homojen dağıtım: tek kasetin etkin alanı ~40 m² (≈6x6 m atış); büyük salonlarda tek dev ünite yerine birkaç ünite
            kapsama = {"kaset4": 40, "kaset1": 20, "kanalli": 60, "salon": 50}.get(tip)
            if not adet and kapsama:
                n_kapsama = math.ceil(oda["alan_m2"] / kapsama - 0.1)
                min_kw = IC["tipler"][tip]["kw"][0]
                n = max(n, min(n_kapsama, max(1, int(yuk_kw / min_kw))))
            k = kw_sec(tip, yuk_kw / n * 0.95)
            uniteler = [{"tip": tip, "kw": k, "btu": round(kw_to_btu(k), -2)} for _ in range(n)]
    for u in uniteler:
        u["btu"] = int(u["btu"])

    toplam = sum(u["kw"] for u in uniteler)
    if (zorla_btu or zorla_kw) and toplam < yuk_kw * 0.85:
        oneriler.append(f"{oda['ad'] or oda['id']}: verilen kapasite ({toplam:.1f} kW) hesaplanan yükün ({yuk_kw:.1f} kW) altında, yetersiz kalabilir.")
    if (zorla_btu or zorla_kw) and toplam > yuk_kw * 1.35:
        oneriler.append(f"{oda['ad'] or oda['id']}: verilen kapasite ({toplam:.1f} kW) yükün çok üstünde; daha küçük ünite yeterli ve DÜ küçülebilir.")
    if tip == "duvar" and oda["alan_m2"] > 40:
        oneriler.append(f"{oda['ad'] or oda['id']} ({oda['alan_m2']:.0f} m²): duvar tipi yerine 4 yön kaset ya da salon tipi daha homojen dağıtım sağlar.")
    if tip == "duvar" and len(uniteler) >= 2:
        oneriler.append(f"{oda['ad'] or oda['id']}: {len(uniteler)} adet duvar tipi yerine 1 kaset/kanallı ünite düşünülebilir (daha az boru ve drenaj noktası).")
    if yuk["tablo_btu"] and abs(yuk["tablo_btu"] - yuk["btu"]) / yuk["tablo_btu"] > 0.35:
        oneriler.append(f"{oda['ad'] or oda['id']}: formül {yuk['btu']} BTU, pratik tablo {yuk['tablo_btu']} BTU; kişi sayısı/kullanım kontrol edilmeli.")
    return uniteler, oneriler


def sistem_oner(klimali_odalar: list[dict], toplam_kw: float, unite_sayisi: int) -> tuple[str, str]:
    if unite_sayisi <= 1:
        return "split", "Tek iç ünite: bağımsız split en ekonomik çözüm."
    ticari = any(o["tip"] in ("magaza", "kafe", "ortak", "toplanti") for o in klimali_odalar)
    if unite_sayisi <= 5 and toplam_kw <= 10.6 and not ticari:
        return "multi", (f"{unite_sayisi} iç ünite, toplam {toplam_kw:.1f} kW: tek dış üniteli multi-split (LG Multi F) cephede tek DÜ ile çözer. "
                         "Ayrı splitler daha ucuz ama cephede çok sayıda DÜ olur.")
    return "vrf", (f"~{unite_sayisi} iç ünite, toplam {toplam_kw:.1f} kW: VRF (LG Multi V) önerilir; tek DÜ, ortak boru hattı, "
                   "eşzamanlılıkla DÜ kapasitesi düşürülebilir.")


def hesapla(analiz: dict, ayarlar: dict, oda_ayarlari: dict) -> dict:
    bolge = ayarlar.get("bolge")
    if not bolge or bolge not in BOLGE["bolgeler"]:
        raise ValueError("İklim bölgesi ayarlanmamış. Kullanıcıya sorun: " + ", ".join(BOLGE["bolgeler"]))
    katsayi = BOLGE["bolgeler"][bolge]["katsayi"]
    odalar = []
    for o in analiz["odalar"]:
        a = oda_ayarlari.get(o["id"], {})
        o = dict(o)
        if "tip_ad" in a:
            o["tip"] = a["tip_ad"]
        if "ad" in a:
            o["ad"] = a["ad"]
        klima = a.get("klima", bool(ODA_TIPLERI.get(o["tip"], {}).get("klima", False)))
        if not klima:
            continue
        o["_ayar"] = a
        o["yuk"] = oda_yuk(o, katsayi, a, ayarlar)
        odalar.append(o)

    # sistem tipi: önce kaba ünite sayısı ile otomatik öneri
    kaba_n = sum(max(1, math.ceil(o["yuk"]["kw"] / 7.1 - 0.05)) for o in odalar)
    kaba_kw = sum(o["yuk"]["kw"] for o in odalar)
    oneri_sistem, gerekce = sistem_oner(odalar, kaba_kw, kaba_n)
    sistem = ayarlar.get("sistem_tipi") or "otomatik"
    if sistem == "otomatik":
        sistem = oneri_sistem

    oneriler = []
    sonuc_odalar = []
    no = 0
    for o in odalar:
        uniteler, on = uniteleri_sec(o, o["yuk"], sistem, o["_ayar"])
        oneriler += on
        for u in uniteler:
            no += 1
            u["id"] = f"IU{no}"
            u["oda"] = o["id"]
        sonuc_odalar.append({"id": o["id"], "ad": o["ad"], "tip": o["tip"], "alan_m2": o["alan_m2"],
                             "yuk": o["yuk"], "uniteler": uniteler})
    toplam_kw = sum(u["kw"] for o in sonuc_odalar for u in o["uniteler"])
    toplam_yuk = sum(o["yuk"]["kw"] for o in sonuc_odalar)
    if sistem != oneri_sistem:
        oneriler.append(f"Seçilen sistem '{sistem}', skill önerisi '{oneri_sistem}': {gerekce}")
    return {
        "bolge": bolge, "katsayi": katsayi, "sistem": sistem, "sistem_onerisi": oneri_sistem,
        "sistem_gerekce": gerekce, "odalar": sonuc_odalar,
        "toplam_ic_kw": round(toplam_kw, 2), "toplam_yuk_kw": round(toplam_yuk, 2),
        "oneriler": oneriler,
    }
