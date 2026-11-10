# LG Multi V verileri: doğrulama ve güncelleme

`data/lg_multiv/` altındaki dosyalar herkese açık bilgilerden derlenmiş **ön değerlerdir** (`"_dogrulanmali": true`). Kullanıcı LG katalog/PDB/kurulum kılavuzu verdiğinde:

1. PDF'i oku (pdf skill) ve aşağıdaki tabloları bul:
   - DÜ modelleri: model kodu, HP, nominal soğutma kW, fabrika gaz şarjı, bağlanabilir İÜ sayısı, kombinasyon oranı aralığı → `dis_uniteler.json`
   - İÜ tipleri ve kW kademeleri, ölçüler → `ic_uniteler.json`
   - Ana hat çapları (DÜ kapasitesine göre), branş hat çapları (alt yüke göre), İÜ bağlantı çapları, Y-branch modelleri (alt yüke göre), header modelleri → `boru_ve_limitler.json`
   - İlave gaz kg/m (sıvı çapına göre) ve İÜ başına CF değerleri (varsa) → `ilave_gaz_kg_m`
   - Boru uzunluğu ve kot farkına göre kapasite düzeltme eğrisi → `kapasite_duzeltme` (lineer yerine tablo istenirse `boru_cap_hesap.kapasite_duzeltme` güncellenir)
   - Borulama limitleri → `profiller.lg_multiv`
2. Değerleri güncelle, `_dogrulanmali` bayrağını `false` yap ve `_kaynak` alanına katalog adını ve yılını yaz.
3. `py -m pytest tests` ile testleri çalıştır. Test beklenen değerleri değiştiyse güncelle.

`fiyat_endeksi` gerçek fiyat değildir, yalnızca seçimde sıralama içindir. Kullanıcının gerçek fiyat listesi varsa `data/fiyatlar.json` oluşturulur:
```json
{"du:ARUM080LTE5": 250000, "iu:duvar:2.8": 22000, "ybranch:ARBLN01621": 3500,
 "boru:6.35": 120, "boru:12.7": 260, "izolasyon:6.35": 35, "drenaj": 40, "kablo": 30,
 "gaz_kg": 900, "iscilik:iu": 3000, "iscilik:du": 6000, "iscilik:devreye_alma": 5000}
```
