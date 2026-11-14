# Yerleşim kuralları

## İç ünite: duvar tipi / salon tipi / 1 yön kaset
Oda kenarları 0,2 m adımla taranır. Her aday nokta için ünite izdüşümü (genişlik × derinlik) kontrol edilir.

**Kesin yasaklar** (`ic_unite_yerlestir.duvar_adaylari`):
| Kural | Eşik |
|---|---|
| Pencere üstü/yanı | ünite şeridi (genişlik + 2×10 cm) pencereye < 12 cm |
| Kapı üstü/yanı | < 25 cm |
| Kolon yüzeyi | < 5 cm |
| Kiriş altı | izdüşüm kirişe < 10 cm |
| Dolap, gardırop, ocak, fırın, buzdolabı önü | izdüşüm + 50 cm |
| Odaya sığmama | izdüşüm oda poligonunun dışına taşıyor |
| Islak hacim, hol, depo, merdiven | `oda_tipleri.json` → `klima: false` |

**Puan** (düşük olan iyi):
- `1.0 × (1 − atış/uzun_kenar)`: hava odanın karşı duvarına kadar gidebilsin
- `0.6 × (1 − |n·uzun_eksen|)`: uzun eksen boyunca üflesin
- `0.8 × min(cepheye_mesafe/8, 1)`: dış duvara yakın olsun (kısa boru, kolay drenaj)
- `0.25 × |kenar ortasından sapma|`
- `+0.3`: kapıya 0,8 m'den yakınsa

Bir odada birden fazla ünite varsa aralarında en az `max(2,5 m, uzun_kenar/(n+0,5))` mesafe bırakılır.

## İç ünite: 4 yön kaset
Oda, uzun ekseni boyunca n eşit hücreye bölünür ve ünite hücre merkezine konur. Duvara en az (genişlik/2 + 0,6 m), kirişe en az 0,3 m mesafe aranır (spiral arama, en fazla 3 m).

**Üfleme yönü engeli:** Kaset dört kenarından düz üfler. Her yönde, panel genişliğindeki üfleme bandında panel kenarından ilk engele boşluk ölçülür (çaprazdaki kolonlar sayılmaz).
- Kolon: en az **1,5 m**. Daha yakın kolon havayı kırıp aşağı çevirir (cereyan) ve o yönün atışı boşa gider.
- Duvar: tercihen 1,0 m; **0,7 m** altı kabul edilmez.
- İki kaset merkezi arası tercihen 3 m.

Arama, hedeften kayma + engel cezası + kasetler arası yakınlık toplamını en aza indiren noktayı seçer. Kaçılamayan yön raporda "KAPAT (3 yön)" olarak çıkar: o yönün kanadı kapatılır ya da ünite elle kaydırılır. Elle konulan kasetler de aynı kontrolden geçer ve uyarı verir. Eşikler `ic_unite_yerlestir.py` başındaki `KASET_*` sabitleridir; LG montaj kılavuzundaki engel boşluğuyla teyit edilmeli.

## İç ünite: kanallı
Koridor/hol ile ortak duvarın iç yüzüne, asma tavan içine konur. Menfez ve kanal projesi bu aracın kapsamında değildir; raporda belirtilir.

## Dış ünite
Adaylar: balkon/teras iç kenarları, bina dış kabuğu (cephe konsolu), "BAHÇE/BOŞ ALAN" metinleri.
**Yasaklar:** kapıya < 1,5 m (balkonda 1,0 m, kaçış yolu), merdivene < 1 m, yol poligonu + 0,5 m ve "YOL/CADDE" metnine < 3 m, parsel dışı, iç mekan.
**Servis/hava boşluğu** (`DU_BOSLUK`, doğrulanmalı): VRF ön 1,0 / arka 0,3 / yan 0,3 m; multi ön 0,6 / arka 0,15 / yan 0,3 m; split ön 0,5 / arka 0,15 / yan 0,3 m. Ön boşluk bina kütlesine, iç mekana, merdivene ya da yola çarpıyorsa aday elenir; yan boşluk dar ise +3 m ceza.
**Pencere:** ünite pencereye 0,3 m'den yakınsa (önünde/altında) elenir; 1,5 m'ye kadar yakınlık cezalı ((1,5 − mesafe) × 6 m). Planda pencere ayırt edilemiyorsa uyarı verilir.
**Sıcak hava sıkışması (cephe):** ön yüzden ±75° ışınlar atılır. Tam karşıdaki bina kütlesi 2 m'den yakınsa (2 − mesafe) × 5 m ceza; ışınların yarısından fazlası 3 m içinde kütleye çarpıyorsa (niş/avlu) +6 m ceza.
**Büyük VRF cephede:** VRF için cephe adayına +10 m, 14 kW üstü her kW için +0,5 m ek ceza (100–300 kg konsol, taşıyıcı, izin). Yine de cephe seçilirse uyarı verilir; çatı/zemin `elle_konum` ile verilmeli.
**Puan:** Manhattan MST tahmini boru + tür cezası (balkon 0, teras 0, bahçe 2 m, cephe 5 m) + yukarıdaki cezalar + kapıya < 4 m ise 5 m. `du_tercih` ayarı seçilen türe −10 m avantaj verir. Adayların cezalı olduğu nedenler `dis` çıktısında aday satırında yazılır.
**Bilinmeyenler:** kapalı hol/fabrika içi (plan dışı), komşu bina pencereleri, gürültü yönetmeliği, güneş/yön, defrost suyu gideri, vinç ve erişim. Kullanıcıya sorulmalı.
Kesin seçim borulama sonrası maliyetle yapılır (`optimize.py`).

## Sahada kullanıcıya sorulacaklar (plandan okunamaz)
- Kiriş alt kotu ve asma tavan var mı (kaset/kanallı için gerekli)
- Cephe konsolu izni (site yönetimi, cephe estetiği)
- Çatı ve teras erişimi, vinç ihtiyacı
- Drenaj için uygun düşey hat ya da gider noktası
