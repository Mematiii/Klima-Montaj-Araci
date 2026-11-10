# Blok kütüphanesi (ör. "2020_VRS Blokları_11611 yeni.dwg")

`data/blok_eslesme.json` bu kütüphanedeki LG LATS bloklarına önceden eşlenmiştir:

| Tip | Blok |
|---|---|
| duvar | `LATS_IDU_WALL_MOUNTED_SJ` |
| kaset4 | `LATS_IDU_4way_cassete_TP_TM_TN` |
| kaset1 | `LATS_IDU_1way_cassete_TU` |
| kanal | `LATS_IDU_MIDDLE_STATIC_M3` |
| salon | `LATS_IDU_ceiling_floor_ceiling_VE` |
| du_vrf | `LATS_ODU_multiv_mini_U4` (DÜ ≤ 28 kW) |
| du_vrf_buyuk | `LATS_ODU_MULTIV_SUPER5_UXB` (DÜ > 28 kW) |
| du_split, ybranch | kütüphanede yok, dahili sembol çizilir |

Kullanım: `py scripts/klima.py ayar --proje P "blok_kutuphanesi_dxf=<kutuphane.dwg>"` ve ardından `cikti`. DWG doğrudan verilebilir: ilk `cikti` çalışmasında DXF'e çevrilir (92 MB DWG ≈ 450 MB DXF, ~4 dk), yalnız eşlenen bloklar `<ad>.klima_bloklar.dxf` önbelleğine (~8 MB) alınır, sonraki çalışmalar bunu kullanır. `blok_eslesme.json` değişince önbellek kendiliğinden yenilenir.

Ölçek ve baz noktası: Kütüphane blokları otomatik oturtulur. Bloğun sınır kutusu merkezi ünite merkezine konur, uzun kenarı `_gercek_genislik_m` değerine ölçeklenir. Kütüphanenin mm ya da cm olması önemli değildir. Hava yönü bloğun +Y yönü kabul edilir (LATS duvar bloğunda doğrulandı).

Başka bir kütüphane için:
1. Blokları listele: `py scripts/blok_tara.py "<kutuphane.dxf>"`. Klima ile ilgili olabilecek bloklar başta, `aday_kategori` ile gelir.
2. Kullanıcıyla `data/blok_eslesme.json` dosyasını güncelle.
3. Çıktıyı al ve bir üniteyi yakından kontrol et (ölçü, hava yönü oku odaya mı bakıyor).
