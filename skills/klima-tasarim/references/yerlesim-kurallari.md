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

## İç ünite: kanallı
Koridor/hol ile ortak duvarın iç yüzüne, asma tavan içine konur. Menfez ve kanal projesi bu aracın kapsamında değildir; raporda belirtilir.

## Dış ünite
Adaylar: balkon/teras iç kenarları, bina dış kabuğu (cephe konsolu), "BAHÇE/BOŞ ALAN" metinleri.
**Yasaklar:** kapıya < 1,5 m (balkonda 1,0 m, kaçış yolu), merdivene < 1 m, yol poligonu + 0,5 m ve "YOL/CADDE" metnine < 3 m, parsel dışı, iç mekan.
**Puan:** Manhattan MST tahmini boru + tür cezası (balkon 0, teras 0, bahçe 2 m, cephe 5 m). `du_tercih` ayarı seçilen türe −10 m avantaj verir.
Kesin seçim borulama sonrası maliyetle yapılır (`optimize.py`).

## Sahada kullanıcıya sorulacaklar (plandan okunamaz)
- Kiriş alt kotu ve asma tavan var mı (kaset/kanallı için gerekli)
- Cephe konsolu izni (site yönetimi, cephe estetiği)
- Çatı ve teras erişimi, vinç ihtiyacı
- Drenaj için uygun düşey hat ya da gider noktası
