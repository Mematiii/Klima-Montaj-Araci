"""Boru güzergahı: maliyet ızgarası üzerinde dönüş cezalı Dijkstra/A*.

Maliyet kuralları (metre eşdeğeri / hücre):
  - Kolon, perde, pencere, yol, parsel dışı: geçilemez.
  - Kiriş: varsayılan geçilemez ('kiris_gecis': 'yasak'); rota bulunamazsa cezalı geçişe düşülür ve uyarılır.
  - Duvar kütlesi: geçilebilir (delik açılır) ama pahalı (içinden boylamasına gitmek istenmez).
  - Oda/koridor ortası: duvardan uzaklaştıkça pahalanır -> borular duvar diplerinden gider, oda ortasını kesmez.
  - Kapı üstü / merdiven: cezalı.
  - Her dönüş (dirsek): ek ceza.
VRF: Prim benzeri Steiner ağacı. Her adımda mevcut ağaca en yakın iç ünite bağlanır, birleşme noktası Y-branch olur.
Split/multi: her iç ünite DÜ'ye ayrı hat (tek kaynaklı Dijkstra).
"""
from __future__ import annotations

import heapq
import math

import numpy as np
import shapely
from shapely.geometry import Polygon, box, shape

INF = float("inf")
DIRS = [(1, 0), (0, 1), (-1, 0), (0, -1)]


class Izgara:
    def __init__(self, analiz: dict, ek_noktalar: list, ayarlar: dict):
        self.ayar = ayarlar
        kabuk = Polygon(analiz["bina_kabugu"])
        x0, y0, x1, y1 = kabuk.bounds
        for p in ek_noktalar:
            x0, y0, x1, y1 = min(x0, p[0]), min(y0, p[1]), max(x1, p[0]), max(y1, p[1])
        pay = 2.0
        x0, y0, x1, y1 = x0 - pay, y0 - pay, x1 + pay, y1 + pay
        res = float(ayarlar.get("izgara_m", 0.2))
        while (x1 - x0) / res * (y1 - y0) / res > float(ayarlar.get("max_hucre", 220000)):
            res *= 1.25
        self.res = res
        self.x0, self.y0 = x0, y0
        self.nx = int(math.ceil((x1 - x0) / res))
        self.ny = int(math.ceil((y1 - y0) / res))
        xs = x0 + (np.arange(self.nx) + 0.5) * res
        ys = y0 + (np.arange(self.ny) + 0.5) * res
        X, Y = np.meshgrid(xs, ys)  # [iy, ix]
        self.X, self.Y = X, Y

        def maske(geoms, tampon=0.0):
            m = np.zeros(X.shape, dtype=bool)
            for g in geoms:
                if tampon:
                    g = g.buffer(tampon)
                if g.is_empty:
                    continue
                bx0, by0, bx1, by1 = g.bounds
                i0, i1 = max(0, int((bx0 - x0) / res) - 1), min(self.nx, int((bx1 - x0) / res) + 2)
                j0, j1 = max(0, int((by0 - y0) / res) - 1), min(self.ny, int((by1 - y0) / res) + 2)
                if i0 >= i1 or j0 >= j1:
                    continue
                m[j0:j1, i0:i1] |= shapely.contains_xy(g, X[j0:j1, i0:i1], Y[j0:j1, i0:i1])
            return m

        eng = analiz["engeller"]
        P = lambda lst: [Polygon(p) for p in lst if len(p) >= 3]
        kutle = shape(analiz["duvar_kutlesi"])
        duvar = maske([kutle], tampon=res * 0.3)
        kolon = maske(P(eng["kolon"]), tampon=0.02)
        kiris = maske(P(eng["kiris"]), tampon=res * 0.5)
        pencere = maske(P(eng["pencere"]), tampon=max(0.05, res * 0.25))
        kapi = maske(P(eng["kapi"]))
        merdiven = maske(P(eng["merdiven"]))
        ic = maske([kabuk])
        yol = maske([Polygon(d["poligon"]) for d in analiz["dis_alanlar"] if d.get("tip") == "yol" and "poligon" in d])
        disari = np.zeros_like(ic)
        if analiz.get("parsel"):
            disari = ~maske([Polygon(analiz["parsel"])])

        # duvara uzaklık (hücre), 1.6 m'de kesilir
        K = max(1, int(1.6 / res))
        d = np.where(duvar | kolon | pencere, 0.0, np.inf)
        for _ in range(K):
            dd = d.copy()
            dd[1:, :] = np.minimum(dd[1:, :], d[:-1, :] + 1)
            dd[:-1, :] = np.minimum(dd[:-1, :], d[1:, :] + 1)
            dd[:, 1:] = np.minimum(dd[:, 1:], d[:, :-1] + 1)
            dd[:, :-1] = np.minimum(dd[:, :-1], d[:, 1:] + 1)
            d = dd
        d = np.minimum(d, K) * res

        # 1.5 gerçek planda yetmedi: kapıdan giren hat duvara 1 m mesafede odayı boydan kesiyordu
        k_orta = float(ayarlar.get("orta_ceza", 3.0))
        maliyet = res * (1.0 + k_orta * d)
        # bina dışından dolaşan hat (cephede açık boru) son çare olmalı; 1.3 iken çatı şaftından çıkan hat
        # duvarları aşmamak için dışarıdan dolanıyordu
        maliyet = np.where(~ic, maliyet * float(ayarlar.get("dis_cephe_carpan", 4.0)), maliyet)
        maliyet = np.where(duvar, res * float(ayarlar.get("duvar_ceza", 6.0)), maliyet)
        maliyet = np.where(kapi & ~duvar, maliyet + res * 3.0, maliyet)
        # merdiven boşluğu katlar arası açıktır; hattın merdiven üstünden geçmesi son çare (kiriş altı kadar ceza)
        maliyet = np.where(merdiven, maliyet + res * float(ayarlar.get("merdiven_ceza", 15.0)), maliyet)
        self.kiris = kiris
        self.kiris_ceza = res * 15.0
        maliyet = np.where(kolon | pencere | (yol & ~ic) | disari, np.inf, maliyet)  # bina içinde "yol" engel olmaz
        # kullanıcı yasak bölgeleri (ör. katman ayrımı olmayan planlarda merdiven boşluğu, galeri): [[x0, y0, x1, y1], ...]
        yb = ayarlar.get("yasak_bolgeler") or []
        if yb:
            yasak_m = maske([box(*b) for b in yb])
            maliyet = np.where(yasak_m, np.inf, maliyet)
        self.temel = maliyet
        self.kiris_yasak = ayarlar.get("kiris_gecis", "yasak") == "yasak"
        self.maske = {"duvar": duvar, "kolon": kolon, "kiris": kiris, "pencere": pencere, "ic": ic}
        self.kur(self.kiris_yasak)

    def kur(self, kiris_yasak: bool):
        m = np.where(self.kiris, np.inf if kiris_yasak else self.temel + self.kiris_ceza, self.temel)
        self.maliyet = m.ravel().tolist()
        self.aktif_kiris_yasak = kiris_yasak

    # --- dönüşümler ---
    def hucre(self, p) -> int:
        i = min(self.nx - 1, max(0, int((p[0] - self.x0) / self.res)))
        j = min(self.ny - 1, max(0, int((p[1] - self.y0) / self.res)))
        return j * self.nx + i

    def nokta(self, c: int):
        j, i = divmod(c, self.nx)
        return (self.x0 + (i + 0.5) * self.res, self.y0 + (j + 0.5) * self.res)

    def serbest_hucre(self, p, r_max=1.5) -> int:
        c = self.hucre(p)
        if self.maliyet[c] < INF:
            return c
        j0, i0 = divmod(c, self.nx)
        en, ed = c, INF
        R = int(r_max / self.res) + 1
        for dj in range(-R, R + 1):
            for di in range(-R, R + 1):
                j, i = j0 + dj, i0 + di
                if 0 <= j < self.ny and 0 <= i < self.nx:
                    k = j * self.nx + i
                    if self.maliyet[k] < INF and di * di + dj * dj < ed:
                        en, ed = k, di * di + dj * dj
        return en

    def dijkstra(self, kaynaklar: dict, hedefler: set, hepsi: bool = False, donus_ceza: float = 1.0, engel: set | None = None):
        """kaynaklar: hücre -> başlangıç maliyeti; engel: girilemeyen hücreler. Döner: (bulunan hedefler, ebeveyn)."""
        engel = engel or set()
        nx, ny = self.nx, self.ny
        mal = self.maliyet
        dist = {}
        ebeveyn = {}
        h = []
        for c, m0 in kaynaklar.items():
            for d in range(4):
                s = c * 4 + d
                dist[s] = m0
                ebeveyn[s] = -1
                h.append((m0, s))
        heapq.heapify(h)
        kalan = set(hedefler)
        bulunan = []
        bitti = set()
        while h:
            m, s = heapq.heappop(h)
            if s in bitti:
                continue
            bitti.add(s)
            c, d = divmod(s, 4)
            if c in kalan:
                kalan.discard(c)
                bulunan.append((c, s, m))
                if not hepsi or not kalan:
                    break
            j, i = divmod(c, nx)
            for nd, (di, dj) in enumerate(DIRS):
                ii, jj = i + di, j + dj
                if ii < 0 or jj < 0 or ii >= nx or jj >= ny:
                    continue
                nc = jj * nx + ii
                w = mal[nc]
                if w == INF or nc in engel:
                    continue
                nm = m + w + (donus_ceza if (nd != d and ebeveyn[s] != -1) else 0.0)
                ns = nc * 4 + nd
                if nm < dist.get(ns, INF):
                    dist[ns] = nm
                    ebeveyn[ns] = s
                    heapq.heappush(h, (nm, ns))
        return bulunan, ebeveyn

    @staticmethod
    def geri_iz(ebeveyn: dict, s: int) -> list[int]:
        yol = []
        while s != -1:
            c = s // 4
            if not yol or yol[-1] != c:
                yol.append(c)
            s = ebeveyn[s]
        return yol  # hedef -> kaynak


def _sadelestir(noktalar):
    if len(noktalar) <= 2:
        return noktalar
    out = [noktalar[0]]
    for a, b, c in zip(noktalar, noktalar[1:], noktalar[2:]):
        if abs((b[0] - a[0]) * (c[1] - b[1]) - (b[1] - a[1]) * (c[0] - b[0])) > 1e-9:
            out.append(b)
    out.append(noktalar[-1])
    return out


def _dirsek_say(noktalar) -> int:
    return max(0, len(_sadelestir(noktalar)) - 2)


def _yol_metre(iz: Izgara, hucreler: list[int]) -> float:
    return max(0, len(hucreler) - 1) * iz.res


def rota_vrf(iz: Izgara, du: dict, iu_list: list[dict], donus_ceza: float = 1.0):
    """Steiner ağacı. Döner: dugumler, segmentler, uyarilar."""
    import networkx as nx
    du_c = iz.serbest_hucre(du["baglanti"])
    G = nx.Graph()
    G.add_node(du_c)
    etiket = {du_c: ("DU", du.get("id", "DU"))}
    iu_hucre = {}
    for u in iu_list:
        c = iz.serbest_hucre(u["baglanti"])
        iu_hucre[c] = u["id"]
    bekleyen = set(iu_hucre)
    jointler = set()
    uyarilar = []
    yasak_r = max(1, int(round(0.6 / iz.res)))

    def kaynaklar():
        out = {}
        yasak = set()
        for c in [du_c] + list(jointler) + [k for k, v in etiket.items() if v[0] == "IU"]:
            j0, i0 = divmod(c, iz.nx)
            r = yasak_r if c != du_c else max(1, int(round(1.0 / iz.res)))
            for dj in range(-r, r + 1):
                for di in range(-r, r + 1):
                    yasak.add((j0 + dj) * iz.nx + (i0 + di))
        for c in G.nodes:
            if G.number_of_nodes() == 1 or c not in yasak:
                out[c] = 0.5  # Y-branch eşdeğeri
        if not out:
            out = {c: 0.5 for c in G.nodes}
        if G.number_of_nodes() == 1:
            out = {du_c: 0.0}
        return out

    while bekleyen:
        kay = kaynaklar()
        engel = set(G.nodes) - set(kay)  # ağacın kaynak olmayan hücrelerinden geçilmez (İÜ/DÜ/Y çevresi)
        bulunan, eb = iz.dijkstra(kay, bekleyen, hepsi=False, donus_ceza=donus_ceza, engel=engel)
        if not bulunan:
            if iz.aktif_kiris_yasak:
                iz.kur(False)
                uyarilar.append("Bazı hatlar kiriş geçişi olmadan bağlanamadı; kiriş altından geçiş cezalı olarak açıldı (sahada kontrol edin).")
                continue
            uyarilar.append(f"Bağlanamayan iç üniteler: {', '.join(iu_hucre[c] for c in bekleyen)}")
            break
        hedef, s, _ = bulunan[0]
        yol = iz.geri_iz(eb, s)  # hedef -> ağaç
        bekleyen.discard(hedef)
        birlesme = yol[-1]
        if G.number_of_nodes() > 1 and birlesme not in etiket:
            jointler.add(birlesme)
            etiket[birlesme] = ("Y", f"Y{len(jointler)}")
        for a, b in zip(yol, yol[1:]):
            G.add_edge(a, b)
        if hedef in etiket and etiket[hedef][0] == "Y":
            # hedef hücre zaten ağaçta (nadiren) -> etiketi IU yap
            pass
        etiket[hedef] = ("IU", iu_hucre[hedef])
    _iu_yaprak_yap(iz, G, etiket, jointler)
    return _agaci_segmentle(iz, G, du_c, etiket), uyarilar


def _iu_yaprak_yap(iz: Izgara, G, etiket: dict, jointler: set):
    """İÜ hiçbir zaman ara düğüm olamaz (çok yakın iki İÜ'de olabiliyor): o hücre Y olur, İÜ komşu boş hücreye yaprak olarak taşınır."""
    for c, (t, ad) in list(etiket.items()):
        if t != "IU" or c not in G or G.degree(c) <= 1:
            continue
        j0, i0 = divmod(c, iz.nx)
        for dj, di in ((0, 1), (1, 0), (0, -1), (-1, 0)):
            j, i = j0 + dj, i0 + di
            n = j * iz.nx + i
            if 0 <= i < iz.nx and 0 <= j < iz.ny and n not in G and iz.maliyet[n] != INF:
                G.add_edge(c, n)
                jointler.add(c)
                etiket[c] = ("Y", f"Y{len(jointler)}")
                etiket[n] = ("IU", ad)
                break


def _agaci_segmentle(iz: Izgara, G, kok: int, etiket: dict):
    """Ağacı kök (DU) -> yapraklara doğru düğümler arası segmentlere böler."""
    dugumler = {}
    for c, (t, ad) in etiket.items():
        if c in G or c == kok:
            dugumler[ad] = {"tip": t, "konum": [round(v, 3) for v in iz.nokta(c)]}
    # derece>2 olup etiketsiz hücreler de Y olur
    sayac = sum(1 for v in etiket.values() if v[0] == "Y")
    for c in G.nodes:
        if G.degree(c) > 2 and c not in etiket:
            sayac += 1
            etiket[c] = ("Y", f"Y{sayac}")
            dugumler[f"Y{sayac}"] = {"tip": "Y", "konum": [round(v, 3) for v in iz.nokta(c)]}
    segmentler = []
    ziyaret = {kok}
    yigin = [(kok, None)]
    while yigin:
        bas, _ = yigin.pop()
        for komsu in G.neighbors(bas):
            if komsu in ziyaret:
                continue
            hucreler = [bas, komsu]
            ziyaret.add(komsu)
            onceki, simdi = bas, komsu
            while simdi not in etiket and G.degree(simdi) == 2:
                sonraki = [k for k in G.neighbors(simdi) if k != onceki][0]
                ziyaret.add(sonraki)
                hucreler.append(sonraki)
                onceki, simdi = simdi, sonraki
            noktalar = [iz.nokta(c) for c in hucreler]
            bas_ad = etiket[bas][1] if bas in etiket else None
            son_ad = etiket.get(simdi, ("?", "?"))[1]
            segmentler.append({
                "id": f"H{len(segmentler) + 1}", "bas": bas_ad, "son": son_ad,
                "noktalar": [[round(x, 3), round(y, 3)] for x, y in _sadelestir(noktalar)],
                "uzunluk_m": round(_yol_metre(iz, hucreler), 2),
                "dirsek": _dirsek_say(noktalar),
            })
            yigin.append((simdi, None))
    return {"dugumler": dugumler, "segmentler": segmentler}


def rota_ayri(iz: Izgara, du: dict, iu_list: list[dict], donus_ceza: float = 1.0):
    """Split / multi-split: her iç üniteye DÜ'den ayrı hat."""
    du_c = iz.serbest_hucre(du["baglanti"])
    hedef = {}
    for u in iu_list:
        hedef[iz.serbest_hucre(u["baglanti"])] = u["id"]
    uyarilar = []
    bulunan, eb = iz.dijkstra({du_c: 0.0}, set(hedef), hepsi=True, donus_ceza=donus_ceza)
    if len(bulunan) < len(hedef) and iz.aktif_kiris_yasak:
        iz.kur(False)
        uyarilar.append("Kiriş geçişi olmadan bağlanamayan hat var; kiriş altından geçiş cezalı açıldı.")
        bulunan, eb = iz.dijkstra({du_c: 0.0}, set(hedef), hepsi=True, donus_ceza=donus_ceza)
    dugumler = {du.get("id", "DU"): {"tip": "DU", "konum": [round(v, 3) for v in iz.nokta(du_c)]}}
    segmentler = []
    for c, s, _ in bulunan:
        yol = iz.geri_iz(eb, s)[::-1]
        noktalar = [iz.nokta(k) for k in yol]
        dugumler[hedef[c]] = {"tip": "IU", "konum": [round(v, 3) for v in iz.nokta(c)]}
        segmentler.append({"id": f"H{len(segmentler) + 1}", "bas": du.get("id", "DU"), "son": hedef[c],
                           "noktalar": [[round(x, 3), round(y, 3)] for x, y in _sadelestir(noktalar)],
                           "uzunluk_m": round(_yol_metre(iz, yol), 2), "dirsek": _dirsek_say(noktalar)})
    eksik = set(hedef) - {c for c, _, _ in bulunan}
    if eksik:
        uyarilar.append(f"Bağlanamayan iç üniteler: {', '.join(hedef[c] for c in eksik)}")
    return {"dugumler": dugumler, "segmentler": segmentler}, uyarilar
