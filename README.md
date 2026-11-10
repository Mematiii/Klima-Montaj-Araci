# klima-tasarim: Claude Code klima yerleşim ve borulama skill'i

Müşterinin DWG/DXF kat planından, montaj ve teklif öncesi klima projesini çıkarır:

1. Planı açar; odaları (salon, yatak, mağaza, ıslak hacim…) ve dış alanları (yol, bahçe, balkon, parsel) tanır.
2. Müşteri isteklerini kısıt olarak alır.
3. BTU yük hesabı yapar (bölge katsayısı + kişi × 600). Ünite tipi ve kapasitesini seçer, daha verimli alternatif önerir.
4. İç üniteleri yerleştirir: pencere/kapı üstü yok, kolon yüzeyi yok, dolap önü yok; hava uzun eksen boyunca atılır.
5. Dış üniteye yer bulur: yol, kapı önü ve merdiven hariç; balkon, teras, bahçe ya da cephe.
6. Borulamayı çizer: kolon ve kirişten geçmez, oda ortasını kesmez, duvar diplerinden gider. VRF'te Y-branch ağacı kurulur.
7. Boru çapı, eşdeğer uzunluk, ilave gaz, kombinasyon oranı ve kapasite düzeltmesini hesaplar; DÜ adaylarını karşılaştırıp en ucuz uygun sistemi seçer.

Her adımın sonunda önizleme görseli gösterilir ve onayınız alınır. Çıktılar: katmanlı **DXF/DWG**, **HTML hesap raporu**, **Excel teklif/malzeme listesi**.

## Kurulum

### Claude Code plugin olarak
```bash
/plugin marketplace add Mematiii/Klima-Montaj-Araci
/plugin install klima-tasarim@klima-tasarim
```

### Elle (yalnızca skill)
`skills/klima-tasarim` klasörünü `~/.claude/skills/` altına (ya da projenizin `.claude/skills/` klasörüne) kopyalayın.

### Gereksinimler
- Python 3.10+: `pip install -r skills/klima-tasarim/requirements.txt`
- DWG okumak/yazmak için iki seçenekten biri:
  - AutoCAD (accoreconsole otomatik bulunur, ya da `KLIMA_ACCORE` ortam değişkeni)
  - [ODA File Converter](https://www.opendesign.com/guestfiles/oda_file_converter) (ücretsiz, ya da `KLIMA_ODA` ortam değişkeni)
  - İkisi de yoksa DXF dosyası verin.

## Kullanım
Claude Code'da: *"Bu planı (`plan.dwg`) klima için çalış, Marmara bölgesi, VRF olsun"* deyin ya da `/klima-tasarim` yazın.

Komut satırından:
```bash
py skills/klima-tasarim/scripts/klima.py baslat plan.dwg --proje klima_plan
py skills/klima-tasarim/scripts/klima.py analiz --proje klima_plan --ada 1
py skills/klima-tasarim/scripts/klima.py ayar --proje klima_plan bolge=marmara
py skills/klima-tasarim/scripts/klima.py hepsi --proje klima_plan
```

## Veriler
- `data/bolgeler.json`, `oda_btu_tablosu.json`, `split_boru_caplari.json`, `havsa_tork.json`: saha tabloları
- `data/lg_multiv/*.json`: **ön değerler**, LG katalogu ile doğrulanmalı (bkz. `references/lg-multiv.md`)
- `data/fiyatlar.json` (isteğe bağlı, repoya girmez): Excel teklif birim fiyatları

## Sorumluluk reddi
Hesaplar ön boyutlandırmadır. Kesin seçim için üreticinin seçim yazılımı (LG LATS) ve saha keşfi esastır.

## Test
```bash
py -m pytest tests
```
