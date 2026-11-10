---
name: klima-tasarim
description: Müşterinin DWG/DXF kat planından klima (VRF/LG Multi V, multi-split, split; duvar, kaset, kanallı, salon tipi) yerleşimi ve bakır borulama projesi çıkarır. Odaları tanır, BTU yük hesabı yapar, iç üniteleri pencere/kapı/kolon kurallarına göre, dış üniteyi yol/kapı/merdiven dışına yerleştirir, kiriş ve kolonlardan kaçan borulama çizer. Boru çapı, eşdeğer uzunluk, ilave gaz, kombinasyon oranı ve kapasite düzeltmesiyle en ucuz uygun DÜ'yü seçer. Çıktı olarak katmanlı DWG/DXF, HTML rapor ve Excel teklif/malzeme listesi verir. Kullanıcı kat planı, klima projesi, VRF borulama, klima teklifi, dış ünite yeri, boru çapı hesabı veya BTU hesabı istediğinde kullan.
---

# Klima Yerleşim ve Borulama (klima-tasarim)

Klima servisinin montaj ve teklif öncesi yaptığı işi adım adım yürütür. **Her adımın sonunda önizleme PNG'sini kullanıcıya göster (Read ile aç) ve onay al.** Kullanıcı düzeltme isterse `proje.json` dosyasına işle ve o adımı yeniden çalıştır. Onaysız bir sonraki adıma geçme; kullanıcı açıkça "hepsini yap" demişse geçebilirsin.

Araç: `scripts/klima.py`. Python 3.10+ ve `requirements.txt` gerekir. Windows'ta `py`, diğer sistemlerde `python3` kullan.

```
S=<bu skill klasörü>/scripts/klima.py
P=<müşteri dosyasının yanındaki proje klasörü, ör. ./klima_<dosya_adi>>
```

## 0. Hazırlık
1. `py $S durum` çalıştır. DWG için `accoreconsole` (AutoCAD) ya da `oda` (ODA File Converter) gerekir. İkisi de yoksa kullanıcıdan ODA File Converter'ı kurmasını (ücretsiz, opendesign.com) ya da dosyayı DXF olarak vermesini iste. İndirmeyi kendin yapma.
2. Bağımlılık eksikse: `py -m pip install -r <skill>/requirements.txt`.

## 1. Planı aç, alanları tanı
```
py $S baslat "<plan.dwg>" --proje "$P" --ad "<proje adı>"
```
- Katman listesini incele. `diger` kategorisinde çok varlığı olan katmanlar duvar, pencere ya da kolon olabilir. Emin değilsen kullanıcıya sor, sonra `proje.json` içine `"katman_duzeltme": {"KATMAN_ADI": "duvar"}` yaz. Kategoriler: duvar, pencere, kapi, kolon, kiris, merdiven, yol, parsel, mobilya, yok_say, klima. Sonra `analiz --yeniden-cikar` çalıştır.
- Birim tahminini kontrol et (cm/mm/m). Yanlışsa `py $S ayar --proje "$P" olcek=0.01` (cm) ve `--yeniden-cikar`.
- Dosyada birden fazla çizim adası (kat planları, kesitler) varsa `0_adalar.png` dosyasını göster ve hangisinin çalışılacağını sor.
```
py $S analiz --proje "$P" --ada <N>
```
- **Kontrol 1:** `onizleme/1_odalar.png`. Oda adları, tipleri ve alanları doğru mu? Kırmızı alanların tipi belirsizdir, kullanıcıya sor. Düzeltmeleri `proje.json` → `"oda_ayarlari": {"O3": {"tip_ad": "salon", "ad": "SALON"}}` olarak yaz. Oda tipleri `data/oda_tipleri.json` dosyasındadır.
- Dış alanlar (yol, bahçe, balkon, teras, parsel) doğru anlaşılmış mı, kontrol et.
- `acik_kenarli` odalar (cam cephe / yalnız kolonlu kenar) ve "planda yazan alan farklı" uyarıları birleşik alan olabilir (ör. SEKRETERYA + hol + koridor). Kullanıcıya sor.
- "Pencere ayırt edilemedi" uyarısı varsa kullanıcıya söyle: iç üniteler iç duvarlara yönlendirilecek; pencere katmanı varsa `katman_duzeltme` ile verilsin.
- Planda mevcut bir klima tasarımı varsa (`klima` kategorisi: LG LATS `LATS_EQ_IDU/ODU`, `1-MEKANIK` gibi katmanlarda "BTU" yazıları) kullanıcıya göster; skill sonucuyla karşılaştırma için faydalıdır.

## 2. Müşteri istekleri
Kullanıcıdan/müşteriden gelen istekleri sor ve `proje.json` dosyasına yaz:
- Oda bazında: `oda_ayarlari.<Oid>` = `{"klima": false}` (klima istemiyor), `{"tip": "kaset4"|"duvar"|"kanal"|"salon"|"kaset1"}`, `{"btu": 12000}` veya `{"kw": 3.6}`, `{"adet": 2}`, `{"kisi": 6}`, `{"yuk_carpani": 1.5}`.
- Genel ayarlar (`py $S ayar --proje "$P" anahtar=değer ...`):
  - `bolge` (**her projede kullanıcıya sor**): akdeniz, guneydogu, ege, marmara, karadeniz, ic_anadolu, dogu_anadolu
  - `sistem_tipi`: otomatik | vrf | multi | split
  - `du_tercih`: balkon | teras | bahce | cephe
  - `du_kot_m`, `iu_kot_m`: kot farkı (örn. DÜ çatıda: `du_kot_m=9`)
  - `eszamanlilik`: 1.0 varsayılan. Konutta 0.8–0.9 kullanıcı onayıyla, DÜ'yü küçültür.
  - `kiris_gecis`: yasak (varsayılan) | ceza
  - `yuk_carpani`: boş (varsayılan, oda tipine göre) | sayı (tüm odalara uygulanır, ör. 1.0 = çarpansız)
  - `mevcut_klima_gizle`: evet (varsayılan; plandaki eski klima katmanları çıktıda kapatılır) | hayir
  - `yasak_bolgeler` (proje.json → ayarlar): `[[x0, y0, x1, y1], ...]` metre; borunun asla geçmeyeceği alanlar. Merdiven çizgileri duvar katmanındaysa merdiven boşluğunu buraya yaz (önizlemede hattın merdivenden geçtiğini görürsen).
- DÜ aday numaraları her çalıştırmada değişebilir; kullanıcı belirli bir yeri seçtiyse `du_aday_secimi` yerine o adayın koordinatlarını `elle_konum`a yaz.
- Üst katlarda VRF DÜ'yü cepheye konsolla asmak yerine çatıyı öner: `elle_konum.S1 = {"konum": [x, y], "baglanti": [x, y]}` (düşey hattın geçeceği köşe, ör. depo/arşiv) ve `ayar du_kot_m=<kat yüksekliği>`. Çizimde DÜ yazısı "ÇATIDA" olarak çıkar.
  - `limit_profili`: lg_multiv (varsayılan) | genel
- Serbest metin istekleri `musteri_istekleri` listesine not et.

## 3. Yük ve ürün seçimi
```
py $S yuk --proje "$P"
```
BTU = alan × bölge katsayısı × kullanım çarpanı + kişi × 600. Pratik oda tablosuyla karşılaştırılır. Kullanım çarpanı oda tipinden gelir (`data/oda_tipleri.json` → `yuk_carpani`): konut tipleri 1,0; ofis/çalışma ve toplantı 1,3; mağaza 1,35; kafe/restoran 1,4; lobi/bekleme 1,2. Bu değerler örnek projelerdeki mevcut LG/BEKO tasarımlarına göre ayarlandı (cam cephe, buzdolabı, aydınlatma, müşteri yükü). Tablodaki `x1.35` sütununu kullanıcıya göster. Proje geneli için `ayar yuk_carpani=1.0`, tek oda için `oda_ayarlari.<Oid>.yuk_carpani` ile değiştirilebilir (öncelik: oda > proje > tip). Büyük alanlarda (kaset için ~40 m²'de bir) ünite sayısı otomatik artırılır. Çıktıdaki **Öneriler** bölümünü kullanıcıya mutlaka aktar (ör. "duvar tipi yerine kaset", "verilen kapasite yetersiz", sistem tipi gerekçesi). Kendi mühendislik önerini de ekle. Verilen kapasite kullanılır ama daha verimli seçenek varsa söylenir.

## 4. İç ünite yerleşimi
```
py $S ic --proje "$P"
```
**Kontrol 2:** `onizleme/2_ic_uniteler.png`. Kurallar `references/yerlesim-kurallari.md` dosyasında. Kullanıcı başka bir konum isterse alternatiflerden birini (gri x) ya da verdiği konumu yaz: `"elle_konum": {"IU2": {"konum": [x, y], "aci": 90}}` (metre, plan koordinatı; aci = üfleme yönü derece), sonra yeniden çalıştır.

## 5. Dış ünite yeri
```
py $S dis --proje "$P"
```
**Kontrol 3:** `onizleme/3_dis_unite.png`. En iyi 3 aday gelir. 1 numara önerilendir; kesin seçim 6. adımda borulama ile yapılır. Kullanıcı belirli bir adayı isterse `"du_aday_secimi": {"S1": 2}`, kendi konumunu isterse `"elle_konum": {"S1": {"konum": [x, y], "aci": 0}}`.

## 6–7. Borulama, çap ve optimizasyon
```
py $S boru --proje "$P"
```
Her DÜ adayı için güzergah çizilir, çaplar seçilir ve limitler kontrol edilir. En düşük maliyetli uygun çözüm seçilir. **Kontrol 4:** `onizleme/4_borulama.png` ve konsoldaki tablo. Kullanıcıya şunları özetle:
- Seçilen DÜ modeli, kombinasyon oranı, düzeltme katsayısı, toplam boru, en uzak eşdeğer uzunluk, ilave gaz
- AŞIM olan kontroller ve nasıl çözüleceği (DÜ yerini değiştirmek, header kullanmak, üniteyi taşımak)
- Aday karşılaştırması: kısa borunun DÜ'yü küçültüp küçültmediği
Borulama kuralları `references/borulama-kurallari.md` dosyasında.

## 8. Çıktılar
```
py $S cikti --proje "$P" [--kutuphane "<blok kütüphanesi.dxf>"]
```
- `cikti/<ad>_klima.dxf` (ve dönüştürücü varsa `.dwg`): KLIMA-IC, KLIMA-DIS, KLIMA-BORU-SIVI, KLIMA-BORU-GAZ, KLIMA-YBRANCH, KLIMA-YAZI katmanları
- `cikti/<ad>_rapor.html`: hesap raporu (tarayıcıdan PDF'e yazdırılabilir)
- `cikti/<ad>_malzeme_teklif.xlsx`: teklif, odalar, boru hatları, kontroller, havşa/tork

Blok kütüphanesi kullanılacaksa önce kütüphane DWG'sini DXF'e çevir, `py <skill>/scripts/blok_tara.py <kutuphane.dxf>` ile blok listesini çıkar ve `data/blok_eslesme.json` dosyasını doldur (bkz. `references/blok-kutuphanesi.md`).

## Önemli notlar
- `data/lg_multiv/*.json` içindeki değerler **ön değerdir** (`_dogrulanmali: true`). Kullanıcı LG katalog/PDB dosyalarını verdiyse tabloları onlardan güncelle ve bayrağı kaldır. Raporda bu durum belirtilir.
- Hesap ön boyutlandırmadır. Kesin seçim için LG LATS ile teyit önerilir.
- Kesit/kot bilgisi 2D plandan okunamaz. Kiriş altı yüksekliği, asma tavan ve şaft gibi konuları kullanıcıya sor.
- Hata ya da "bağlanamayan iç ünite" uyarısında `references/sorun-giderme.md` dosyasına bak.
