# Sorun giderme

| Belirti | Olası sebep | Çözüm |
|---|---|---|
| Hiç oda yok / tek dev oda | Duvar katmanı `diger` olarak sınıflanmış ya da duvarlar blok içinde | `baslat` çıktısındaki katman listesine bak, `katman_duzeltme` ekle, `analiz --yeniden-cikar` |
| Odalar birleşik (salon+mutfak) | Açık plan ya da kapı boşluğu > 1,1 m | Normal olabilir. Ayırmak için `ayar kapi_kapama_m=0.8` |
| Alanlar 100 kat büyük/küçük | Birim yanlış tahmin edilmiş (önce `$INSUNITS` + yazı boyu, sonra çizgi uzunluğu bakılır) | `ayar olcek=0.01` (cm) / `0.001` (mm) / `1` (m), `analiz --yeniden-cikar` |
| Pencere algılanmadı | Pencere bloğu adı veya katmanı tanınmıyor | `katman_duzeltme` ile katmanı `pencere` yap; blok adı için `data/katman_sozlugu.json` → `blok_anahtar` |
| "Planda pencere ayırt edilemedi" | Duvar, pencere ve kapı tek katmanda (ör. `1-MIMARI`) | Araç dış cephe duvarlarını pencere sayıp iç üniteleri iç duvarlara yönlendirir. Pencere ayrı katmandaysa `katman_duzeltme` ile belirt |
| Cam cepheli / kolonlu salon oda olarak çıkmıyor ya da çok küçük | Bir kenarında duvar yok | Kabuk 2,6 m'lik kapama ile kurulur ve kabuk içindeki boşluk oda olur (`acik_kenarli`). Sınırı önizlemede kontrol et |
| Oda adı "BEKO-LG", "36.000 Btu/h" gibi | Planda eski/mevcut klima tasarımı var | Klima/mekanik katmanındaki yazılar oda adı sayılmaz; kalırsa `oda_ayarlari.Ox.ad` ile düzelt. Mevcut tasarım karşılaştırma için kullanıcıya gösterilebilir |
| Bir katta iç bölmeler yok, tek dev oda | Bölme duvarları alışılmadık katmanda (ör. bir örnek planda `ÖLÇÜ` ve `SERAMIK-KESIT`) | Katmanları uzun çizgi toplamına göre sırala, şüphelileri ayrı ayrı çiz; doğru olanı `katman_duzeltme` ile `duvar` yap. DIMENSION nesneleri zaten atlanır |
| Çıktıda eski klima tasarımı yenisiyle üst üste | Planda mevcut tasarım var | `cikti` eski klima katmanlarını (`1-MEKANIK`, `KLIMA`, `LATS_EQ_*` ...) kapatır, silmez. İstenmezse `ayar mevcut_klima_gizle=hayir` |
| Bina kabuğu çok büyük, köşelerde küçük "odalar", bütün odalar "iç" | Kaldırım/saçak/bordür çizgisi duvar katmanında, binayı sarıyor | Otomatik ayıklanır (diğer duvarlardan >= 0,5 m uzak saran çizgi). Kalırsa `katman_duzeltme` ya da `analiz --bbox` |
| Kapılar algılanmadı (kapı katmanı/bloğu yok) | Kapılar duvar katmanında yay olarak çizilmiş | ~90° ve 0,6-1,3 m yarıçaplı yaylar kapı sayılır. Sürgülü/otomatik kapılar yay içermez: DÜ'nün giriş önüne düşmediğini önizlemede kontrol et |
| Hiç oda yok, oda yazıları var | Duvarlar alışılmadık katmanda (ör. bir Revit çıktısında bölmeler `3`, oda sınırları `alan` poligonu) | Bölgedeki katmanları uzunluğa göre listele; `katman_duzeltme` ile `duvar` yap. Revit çıktılarında `alan`/`area` poligonları doğrudan oda sınırıdır |
| Oda adı "T", "Ç.Ö: 370x370", "VESTİYER" | Termostat/difüzör/mobilya yazısı oda adı sanılmış | 3 harften kısa yazılar atlanır; kalanı `oda_ayarlari.Ox.ad/tip_ad` ile düzelt |
| Çıktıda eski kasetler hâlâ görünüyor | Eski blokların iç çizgileri `LATS_CASSETE` gibi başka katmanlarda | Eski klima katmanları kapatılır **ve dondurulur** (freeze); blok tümüyle gizlenir |
| "KAPAT (3 yön)" uyarısı / kaset kolonun önünde | 4 yön kasetin bir üfleme yönünde 1,5 m içinde kolon ya da 0,7 m içinde duvar var | Önce üniteyi `elle_konum` ile kaydır; olmuyorsa o yönün kanadını kapat (3 yön). Küçük odada kaçınılmazsa duvar tipi ya da 1 yön kaset düşün |
| Boru merdivenin üstünden geçiyor | Merdiven çizgileri duvar katmanında | `ayarlar.yasak_bolgeler` ile merdiven boşluğunu kapat |
| Boru binanın dışından dolaşıyor | Dış hücreler ucuz | Varsayılan `dis_cephe_carpan` 4; yine de oluyorsa iç güzergah duvar/kolonla kapalıdır, önizlemeye bak |
| Çizim adası tüm vaziyeti kapsıyor | Topoğrafya/yol çizgileri planları birbirine bağlıyor | Adalar mimari katmanlardan kurulur; yine de olmazsa `analiz --bbox x0 y0 x1 y1` |
| İki ünite sırt sırta, biri diğerinin hattında | Çok yakın İÜ'ler | Araç ara düğüm olan İÜ'yü otomatik Y-branch'e çevirir; hesap çıktısında `IUx->IUy` segmenti görülmemeli |
| "Yeterli uygun duvar yok" | Oda küçük, her duvarda pencere veya kapı var | Kaset/kanallı öner ya da `elle_konum` |
| "Bağlanamayan iç ünite" | Kolon, perde, pencere ya da kiriş ile çevrili | Önizlemeye bak; ilgili katmanın yanlış sınıflandırılmadığını kontrol et, `kiris_gecis=ceza` |
| Kiriş uyarısı | Kirişler plan boyunca hatları kesiyor | 2D planda kiriş altından geçiş görünür. Kiriş alt kotunu kullanıcıya sor |
| Rota çok yavaş | Plan çok büyük | `ayar izgara_m=0.3` ya da daha küçük ada/bbox seç |
| DWG açılmıyor | Dönüştürücü yok | ODA File Converter kur ya da DXF iste |
