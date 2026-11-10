# Borulama kuralları ve hesap yöntemi

## Güzergah (borulama.py)
Plan 0,2 m'lik bir ızgaraya bölünür (220 bin hücreyi aşarsa ızgara büyütülür). Her hücrenin maliyeti metre eşdeğeridir:

| Hücre | Maliyet |
|---|---|
| Oda/koridor içi | `res × (1 + 1,5 × min(duvara_mesafe, 1,6 m))`: duvar dibi ucuz, oda ortası pahalı |
| Bina dışı (cephe) | × 1,3 |
| Duvar kütlesi | `res × 6` (delik açılarak geçilir, boyuna gidilmez) |
| Kapı, merdiven | + `res × 3` |
| Kiriş | `kiris_gecis=yasak` → geçilemez. Rota yoksa otomatik olarak cezalı geçişe (+`res × 15`) düşülür ve uyarı verilir |
| Kolon, perde, pencere, yol, parsel dışı | geçilemez |
| Dönüş (dirsek) | + 1,0 m (`donus_ceza_m`) |

Yalnızca 4 yönlü hareket vardır, borular dik açılı gider.

**VRF:** Prim benzeri Steiner ağacı kurulur. Her adımda mevcut ağaca en ucuz bağlanan iç ünite eklenir. Birleşme noktası Y-branch olur (+0,5 m). DÜ'ye 1 m, Y-branch'e ve iç üniteye 0,6 m mesafede birleşme yapılmaz. Ağacın bu bölgelerinden geçilmez, böylece iç ünite ara düğüm olmaz.
**Split / multi-split:** her iç ünite DÜ'ye ayrı hatla bağlanır (tek kaynaklı Dijkstra).

## Çap seçimi (boru_cap_hesap.py, LG Multi V ön değerleri)
- Ana hat (DÜ → ilk Y): DÜ kapasitesine göre `ana_hat_dis_uniteye_gore`. Eşdeğer uzunluk 90 m'yi aşarsa gaz hattı bir çap büyütülür.
- Branş hat: hattın beslediği iç ünitelerin toplam kW'ına göre `brans_hat_alt_yuke_gore`; ana hattan büyük olamaz.
- İç ünite bağlantısı: ünite kW'ına göre `ic_unite_baglanti`.
- Split/multi: kullanıcının BTU tablosu (`split_boru_caplari.json`).

## Eşdeğer uzunluk
`L_eş = L + düşey + dirsek × k(gaz çapı) + Y-branch 0,5 m (+ düşey varsa 2 dirsek)`

## Gaz
- VRF ilave gaz = Σ (sıvı hat uzunluğu × kg/m). R410A için 6,35: 0,022 · 9,52: 0,059 · 12,7: 0,12 · 15,88: 0,18 · 19,05: 0,27 · 22,2: 0,35 kg/m
- Split: fabrika dolumu 5 m'yi aşan uzunluk × 20 g/m (6,35)
- Gerçek uzunluk kullanılır (LG yöntemi). Ekran görüntüsündeki araç eşdeğer uzunluk kullanıyor; fark raporda bilinmeli.

## DÜ seçimi ve optimizasyon
1. Kapasite düzeltme katsayısı: `k = 1 − 0,0011 × (L_eş_max − 7,5) − 0,0008 × |Δh|` (alt sınır 0,75). Katalog eğrisiyle değiştirilmeli.
2. Uygun DÜ şunları sağlamalı: `0,5 ≤ ΣİÜ / DÜ ≤ 1,3`, `DÜ × k ≥ yük × eşzamanlılık` ve iç ünite sayısı modelin üst sınırını aşmamalı.
3. En düşük fiyat endeksli uygun model seçilir.
4. Her DÜ adayı için 1–3 adımları tekrarlanır. Maliyet = DÜ endeksi + 0,6 × toplam boru + 2 × Y adedi (+1000 limit aşımı). Daha kısa boru, daha yüksek k ve dolayısıyla daha küçük DÜ demektir.

## Limit profilleri (`boru_ve_limitler.json` → `profiller`)
- `lg_multiv`: toplam 300/1000 m, en uzak 150 m (eşdeğer 175), ilk branşmandan en uzağa 40 m, DÜ-İÜ 50 m, İÜ-İÜ 15 m
- `genel`: ekran görüntüsündeki üreticiden bağımsız VRF aracının limitleri (ilk branşmana 70 m, branşman sonrası 40 m, joint-joint 1–90 m, DÜ-İÜ 40 m)
- `multi_f`: tek hat 25 m, toplam 50 m

## Havşa ve tork
`havsa_tork.json`: 6,35 / 9,52 / 12,7 / 15,88 mm için havşa boyu ve sıkma torkları Excel'e eklenir.
