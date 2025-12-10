# Tkinter Sekmeli Arayüz Şablonları (Görsel Taslaklar)

Aşağıdaki üç şablon, Merdiven.py arayüzü için önerilen yerleşimlerin kutu diyagramlarıdır. Sekmeler ve gruplar Türkçe başlıklarla işaretlendi. Çizimler kabaca konum/padding ilişkisini göstermek içindir; kesin boyutlar Tkinter içinde `grid`/`pack` ayarlarıyla belirlenecektir.

---

## Şablon 1 – "Çift Sütun, Sade Çerçeveler"

```
+---------------------------------------------------------------+
|                        ttk.Notebook                           |
|  [Genel] [Satın Alma] [Item Satış] [Hız / Gelişmiş] [Log]     |
|                                                               |
|  Sekme: Genel                                                 |
|  +--------------------+    +-------------------------------+  |
|  | Giriş Bilgileri    |    | Sunucu / Kanal                |  |
|  | username / passwd  |    | item_basma_server combobox    |  |
|  | açıklama metni     |    |                               |  |
|  +--------------------+    +-------------------------------+  |
|  +--------------------+    +-------------------------------+  |
|  | Çalışma Modu       |    | Telegram / Bildirim           |  |
|  | operation_mode cb  |    | token / chat_id / mesaj /     |  |
|  |                    |    | interval girişleri            |  |
|  +--------------------+    +-------------------------------+  |
|                                                               |
|  [Başlat] [Durdur]                           [Ayarları Kaydet] |
+---------------------------------------------------------------+
```

---

## Şablon 2 – "Kart Tarzı, Yumuşak Kenarlar"

```
+---------------------------------------------------------------+
| ttk.Notebook (kart stili, aralıklı)                           |
|                                                               |
|  Sekme: Satın Alma                                            |
|                                                               |
|  +-----------+   +-------------------+   +-------------------+|
|  | Satın     |   | Alım Döngüsü      |   | Gelişmiş NPC      ||
|  | Alma Modu |   | (tur/scroll/basma)|   | Ayarları (süre/   ||
|  | combobox  |   | spinbox kartı     |   | koordinat)        ||
|  +-----------+   +-------------------+   +-------------------+|
|                                                               |
|  Kart kenarları yumuşak; her kart kendi başlığıyla ayrılmış.  |
+---------------------------------------------------------------+
```

---

## Şablon 3 – "Grid Yoğun, Yönetim Paneli"

```
+--------------------------------------------------------------------+
| ttk.Notebook (kompakt grid)                                        |
|                                                                    |
| Sekme: Item Satış                                                  |
|                                                                    |
| +----------------+ +----------------+ +--------------------------+ |
| | Pazar Temel    | | Yenileme/Bekl. | | Tıklama Ayarları         | |
| | (fiyat/slot)   | | (ilk bekleme,  | | (902/899 hız/adet)       | |
| +----------------+ | min/max)       | +--------------------------+ |
| +----------------+ +----------------+ +--------------------------+ |
| | Banka Entegr.  | | Park/Krallık   | | Otomatik Pazar Yenileme  | |
| | (eşik/çek/adn) | | (park X, krall.| | (aktif, saat aralığı)    | |
| +----------------+ +----------------+ +--------------------------+ |
|                                                                    |
| +----------------------------------------------------------------+ |
| | Canlı Bilgi (Boş slot sayısı, son yenileme zamanı)             | |
| +----------------------------------------------------------------+ |
+--------------------------------------------------------------------+
```

---

> Not: "Hız / Gelişmiş" sekmesi tüm şablonlarda, solda hız profili + fren, sağda otomatik ölçüm ve altında geniş "Gelişmiş Parametreler (YAMA GUI)" alanı olacak şekilde planlanmıştır. "Log / İzleme" sekmesi ise üstte stage etiketi ve altta geniş bir readonly metin alanı içerir.
