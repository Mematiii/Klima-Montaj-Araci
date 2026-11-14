import subprocess
import sys
from pathlib import Path

import pytest
from shapely.geometry import Polygon

KOK = Path(__file__).resolve().parent.parent
SCR = KOK / "skills" / "klima-tasarim" / "scripts"
sys.path.insert(0, str(SCR))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import boru_cap_hesap as bch  # noqa: E402
import yuk_hesap  # noqa: E402
from ortak import json_oku  # noqa: E402


def test_btu_formulu():
    oda = {"id": "O1", "ad": "SALON", "tip": "salon", "alan_m2": 20.0}
    y = yuk_hesap.oda_yuk(oda, 385, {})
    assert y["btu"] == round(20 * 385 + 4 * 600)
    assert y["tablo_btu"] == 12000


def test_yuk_carpani():
    magaza = {"id": "O1", "ad": "MARKET", "tip": "magaza", "alan_m2": 100.0}
    y = yuk_hesap.oda_yuk(magaza, 385, {"kisi": 0})
    assert y["carpan"] == 1.35 and y["btu"] == round(100 * 385 * 1.35)
    # proje geneli ve oda ayarı varsayılanı ezer (öncelik: oda > proje > tip)
    assert yuk_hesap.oda_yuk(magaza, 385, {"kisi": 0}, {"yuk_carpani": 1.0})["btu"] == 38500
    assert yuk_hesap.oda_yuk(magaza, 385, {"kisi": 0, "yuk_carpani": 1.5}, {"yuk_carpani": 1.0})["btu"] == round(100 * 385 * 1.5)
    # konut tipleri değişmez
    assert yuk_hesap.oda_yuk({"id": "O2", "ad": "SALON", "tip": "salon", "alan_m2": 20.0}, 385, {})["carpan"] == 1.0


def test_split_cap_tablosu():
    assert bch.split_cap(9000) == {"sivi": 6.35, "gaz": 9.52, "alternatif": None}
    c = bch.split_cap(24000)
    assert (c["sivi"], c["gaz"]) == (9.52, 15.88)


def test_kapasite_duzeltme_monoton():
    assert bch.kapasite_duzeltme(7.5, 0) == 1.0
    assert bch.kapasite_duzeltme(50, 0) > bch.kapasite_duzeltme(100, 0) >= 0.75


def test_du_secimi_kisa_boru_kucuk_du():
    # aynı yük, kısa boruda k yüksek -> daha küçük DÜ yetebilir
    kisa, _ = bch.du_sec(14.0, 13.8, bch.kapasite_duzeltme(10, 0), 5, {})
    uzun, _ = bch.du_sec(14.0, 13.8, bch.kapasite_duzeltme(120, 0), 5, {})
    assert kisa["kw"] <= uzun["kw"]


def test_vrf_agaci_ve_cap():
    rota = {
        "dugumler": {"DU": {"tip": "DU", "konum": [0, 0]}, "Y1": {"tip": "Y", "konum": [5, 0]},
                     "IU1": {"tip": "IU", "konum": [5, 5]}, "IU2": {"tip": "IU", "konum": [10, 0]}},
        "segmentler": [
            {"id": "H1", "bas": "DU", "son": "Y1", "noktalar": [[0, 0], [5, 0]], "uzunluk_m": 5, "dirsek": 0},
            {"id": "H2", "bas": "Y1", "son": "IU1", "noktalar": [[5, 0], [5, 5]], "uzunluk_m": 5, "dirsek": 1},
            {"id": "H3", "bas": "Y1", "son": "IU2", "noktalar": [[5, 0], [10, 0]], "uzunluk_m": 5, "dirsek": 0},
        ]}
    iu = {"IU1": {"kw": 2.8}, "IU2": {"kw": 7.1}}
    h = bch.vrf_hesapla(rota, iu, "DU", {}, 9.5)
    s = {x["id"]: x for x in h["segmentler"]}
    assert s["H2"]["sivi"] == 6.35 and s["H3"]["sivi"] == 9.52
    assert len(h["y_branch"]) == 1 and h["y_branch"][0]["model"] == "ARBLN01621"
    assert h["du"] is not None and 0.5 <= h["kombinasyon_orani"] <= 1.3
    assert h["ilave_gaz_kg"] > 0


def test_anahtar_kelime_basi():
    from ortak import anahtar_eslesir, normalize
    assert not anahtar_eslesir(normalize("1-MIMARI"), "IMAR")  # MIMARI parsel sayılmamalı
    assert anahtar_eslesir(normalize("Z-IMAR-HATTI"), "IMAR")
    assert anahtar_eslesir(normalize("A-WALL-FNSH"), "WALL")


def test_islak_hacim_onceligi():
    import oda_bul
    assert oda_bul.oda_tipi_bul("ÇOCUK & ENG. WC")[0] == "islak"
    assert oda_bul.oda_tipi_bul("KADIN PER.SOY.")[0] == "giyinme"


def test_kolonlu_cam_cepheli_salon():
    """Bir kenarı yalnız kolon, bir kenarı cam olan mağaza holü de oda olarak bulunmalı (gerçek planda kaçıyordu)."""
    import oda_bul

    def cizgi(a, b):
        return {"p": [list(a), list(b)], "k": False, "l": "DUVAR"}

    def kolon(x, y):
        return {"p": [[x, y], [x + .4, y], [x + .4, y + .4], [x, y + .4]], "k": True, "l": "KOLON"}

    plan = {
        "cizgiler": {
            "duvar": [cizgi((0, 0), (0, 10)), cizgi((0, 10), (14, 10))],          # sol ve üst duvar
            "kolon": [kolon(13.6, 9.6), kolon(13.6, 5.0), kolon(13.6, 0.0)],     # sağ kenar: yalnız kolonlar
            "pencere": [{"p": [[0, 0], [14, 0]], "k": False, "l": "DOGRAMA"}],   # alt kenar: cam cephe
        },
        "nesneler": [], "metinler": [{"t": "MARKET", "x": 7, "y": 5, "h": .3, "l": "TEXT"}],
    }
    s = oda_bul.odalari_bul(plan)
    market = [o for o in s["odalar"] if o["tip"] == "magaza"]
    assert market and market[0]["alan_m2"] > 120
    assert market[0]["acik_kenarli"]


def test_kaldirim_halkasi_duvar_sayilmaz():
    """Binayı 1 m mesafeden saran kaldırım çizgisi duvar katmanında olsa da bina kabuğu sayılmamalı."""
    from shapely.geometry import LineString, Polygon
    import oda_bul
    duvar = [Polygon([(0, 0), (10, 0), (10, 8), (0, 8)]).exterior,              # dış duvar dış yüzü
             Polygon([(0.25, 0.25), (9.75, 0.25), (9.75, 7.75), (0.25, 7.75)]).exterior,
             LineString([(5, 0.25), (5, 7.75)]), LineString([(5.1, 0.25), (5.1, 7.75)])]
    duvar += [LineString([(0.25, y), (5, y)]) for y in (2, 4, 6)]               # birkaç bölme
    duvar += [LineString([(5.1, y), (9.75, y)]) for y in (2.5, 5.5)]
    duvar += [LineString([(2.5, 0.25), (2.5, 2)]), LineString([(7.5, 0.25), (7.5, 2.5)])]
    halka = Polygon([(-1, -1), (11, -1), (11, 9), (-1, 9)])                      # kaldırım (kapalı)
    duvar = [LineString(list(g.coords)) if hasattr(g, "coords") else g for g in duvar] + [halka]
    kalan, ayiklanan = oda_bul.cevre_halkasi_ayikla(duvar)
    assert len(ayiklanan) == 1 and ayiklanan[0] is halka
    assert len(kalan) == len(duvar) - 1  # gerçek dış duvar korunur


def test_kaset_kolon_onune_konmaz():
    """Odanın ortasındaki kolon, 4 yön kasetin hiçbir üfleme yönünün 1,5 m içinde kalmamalı."""
    import ic_unite_yerlestir as iu
    oda = {"id": "O1", "poligon": [[0, 0], [10, 0], [10, 8], [0, 8]]}
    kolon = [[5.6, 3.8], [6.0, 3.8], [6.0, 4.2], [5.6, 4.2]]   # merkezin hemen sağında
    eng = {"kiris": [], "kolon": [kolon], "pencere": [], "kapi": []}
    k = iu.kaset_konumlari(oda, 1, 0.95, eng)[0]
    bos = iu.kaset_yon_bosluklari(k["konum"], 0.95, Polygon(oda["poligon"]), [Polygon(kolon)])
    assert all(b["bosluk"] >= iu.KASET_KOLON_M for b in bos if b["engel"] == "kolon")
    assert not k["kapali_yonler"]
    # kolonun tam önündeki bir konum yakalanmalı (3 yön önerisi)
    bos2 = iu.kaset_yon_bosluklari((4.8, 4.0), 0.95, Polygon(oda["poligon"]), [Polygon(kolon)])
    kapali = iu.kaset_kapali_yonler(bos2)
    assert [b["yon"] for b in kapali] == ["sağ (+x)"] and kapali[0]["engel"] == "kolon"
    # çapraz kolon üfleme bandında değildir
    bos3 = iu.kaset_yon_bosluklari((4.0, 2.0), 0.95, Polygon(oda["poligon"]), [Polygon(kolon)])
    assert not any(b["engel"] == "kolon" for b in bos3)


def _du_analiz(kabuk, pencere=()):
    return {"bina_kabugu": kabuk, "odalar": [{"id": "O1", "tip": "salon", "poligon": kabuk}],
            "engeller": {"kapi": [], "merdiven": [], "pencere": [list(p) for p in pencere]},
            "dis_alanlar": [], "parsel": None}


def test_du_pencere_onune_konmaz():
    import dis_unite_yerlestir as du
    kabuk = [[0, 0], [10, 0], [10, 8], [0, 8]]
    pen = [[3, -0.1], [5, -0.1], [5, 0.1], [3, 0.1]]           # güney cephede 2 m pencere
    ad = du.aday_noktalar(_du_analiz(kabuk, [pen]), du.DU_OLCU["split"], tip="split")
    guney = [a for a in ad if a["konum"][1] < 0]
    assert guney and all(a["pencere_m"] >= du.PENCERE_YASAK_M for a in guney)
    assert not any(2.6 < a["konum"][0] < 5.4 for a in guney)    # pencerenin önü boş
    yakin = [a for a in guney if a["pencere_m"] < du.PENCERE_TERCIH_M]
    assert yakin and all(a["ek_ceza"] > 0 and any("pencere" in n for n in a["notlar"]) for a in yakin)


def test_du_nis_ve_servis_boslugu():
    import dis_unite_yerlestir as du
    # U biçimli bina: kuzeyde 2 m genişliğinde, 4 m derinliğinde avlu (niş)
    kabuk = [[0, 0], [10, 0], [10, 8], [6.0, 8], [6.0, 4], [4.0, 4], [4.0, 8], [0, 8]]
    ad = du.aday_noktalar(_du_analiz(kabuk), du.DU_OLCU["vrf"], tip="vrf")
    avlu = [a for a in ad if 4.0 < a["konum"][0] < 6.0 and 4 < a["konum"][1] < 8]
    assert avlu and all(a["ek_ceza"] >= 6 for a in avlu)
    assert all(any("niş" in n or "engel" in n for n in a["notlar"]) for a in avlu)
    # 1 m ön boşluğu sığmayan yerde VRF adayı olmamalı (avlu yan duvarlarına bakan adaylar)
    for a in avlu:
        if abs(a["aci"]) < 1 or abs(abs(a["aci"]) - 180) < 1:  # doğu/batı bakan
            assert False, "2 m avluda karşı duvara bakan VRF için ön boşluk yok"
    dis = [a for a in ad if a["konum"][1] < 0]
    assert dis and min(a["ek_ceza"] for a in dis) == 0


def test_vrf_cephe_cezasi():
    import dis_unite_yerlestir as du
    assert du.vrf_cephe_cezasi("split", 30) == 0
    assert du.vrf_cephe_cezasi("vrf", 28) > du.vrf_cephe_cezasi("vrf", 12) >= du.VRF_CEPHE_CEZA_M
    a = {"baglanti": [0, 0], "tur": "cephe"}
    b = {"baglanti": [0, 0], "tur": "teras"}
    assert du._puanla(a, [[5, 0]], None, "vrf", 28) - du._puanla(b, [[5, 0]], None, "vrf", 28) > 15


def test_uctan_uca(tmp_path):
    import ornek_plan_olustur
    dxf = ornek_plan_olustur.olustur(str(tmp_path / "ornek.dxf"))
    k = [sys.executable, str(SCR / "klima.py")]
    P = str(tmp_path / "proje")

    def calis(*a):
        r = subprocess.run(k + list(a), capture_output=True, text=True, encoding="utf-8")
        assert r.returncode == 0, r.stderr + r.stdout
        return r.stdout

    calis("baslat", dxf, "--proje", P, "--ad", "test")
    calis("analiz", "--proje", P, "--ada", "1")
    analiz = json_oku(Path(P) / "analiz.json")
    tipler = sorted(o["tip"] for o in analiz["odalar"])
    assert tipler.count("yatak") == 2 and "salon" in tipler and "mutfak" in tipler and "balkon" in tipler
    calis("ayar", "--proje", P, "bolge=marmara")
    calis("hepsi", "--proje", P)
    ic = json_oku(Path(P) / "ic.json")
    assert len(ic["ic_uniteler"]) == 4
    boru = json_oku(Path(P) / "boru.json")
    h = boru["sistemler"][0]["secilen"]["hesap"]
    assert h["uygun"]
    # her iç ünite yaprak düğüm olmalı (ara düğüm değil)
    baslar = {s["bas"] for s in h["segmentler"]}
    assert not any(b.startswith("IU") for b in baslar)
    assert (Path(P) / "cikti" / "test_klima.dxf").exists()
    assert (Path(P) / "cikti" / "test_malzeme_teklif.xlsx").exists()
