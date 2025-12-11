# Codex Prompt Scripts

This repository contains two ready-to-use prompts for analysing and refactoring `Merdiven.py`. Copy the relevant section directly into Codex when needed.

## 🧩 PROMPT 1 – Merdiven.py’yi önce analiz ettir (hiç kod yazdırmadan)

**BAŞLANGIÇ (ANALİZ) MESAJI – Codex’e göndereceğin metin:**

> Aşağıya Knight Online için yazdığım `Merdiven.py` makro dosyasını ekliyorum.
> Şimdilik **kesinlikle hiçbir kod yazma veya değiştirme.**
> Sadece bu dosyayı satır satır incele ve bana **ayrıntılı bir “proje haritası”** çıkar.
>
> Özellikle şunları madde madde yazmanı istiyorum:
>
> 1. **Genel Mimari**
>
>    * Bu dosya hangi ana modüllerden oluşuyor? (örneğin: oyun başlatma & login, merdiven +7/+8 basma, pazar/item satışı, NPC’den satın alma, banka & depo, PC hızlandırma, GUI, JSON config sistemi, log sistemi, vs.)
>    * Her modül için hangi ana fonksiyon(lar) sorumlu? Fonksiyon isimlerini ve temel görevlerini yaz.
> 2. **Config & GUI Yapısı**
>
>    * `self.v` sözlüğü nasıl kullanılıyor? Hangi önemli ayar değişkenleri var? (örneğin SPEED_PROFILE, BASMA_HAKKI, KOORDİNAT ayarları, NPC/Banka koordinatları, pazar zamanlamaları, vb.)
>    * JSON config yükleme / kaydetme mantığını (hangi dosya, hangi fonksiyonlar) açıkla.
>    * GUI nasıl organize edilmiş? Hangi sekmeler (Genel, Satın Alma, Item Satış, Hız, Gelişmiş, Durum, Hız/Anvil/PREC598, vs.) var ve her sekme hangi ayar gruplarını içeriyor?
> 3. **Ana Akış (Makro Çalışma Mantığı)**
>
>    * Program çalıştığında hangi fonksiyon(lar) sırayla çağrılıyor? `if __name__ == "__main__":` bloğundan itibaren akışı anlat.
>    * `start()`, `stop()`, `apply_core()`, `_MERDIVEN_RUN_GUI()` gibi kritik fonksiyonların rolünü kısaca açıkla.
>    * Merdiven +7/+8 basma akışı nasıl başlıyor, hangi fonksiyonlar üzerinden ilerliyor? (kısaca adım adım yaz).
>    * Pazar (item satış) modu, NPC’den satın alma modu, banka modları nereden tetikleniyor, hangi OPERATION_MODE değerleri kullanılıyor?
> 4. **Önemli Özel Davranışlar**
>
>    * HP bar kontrolü, CapsLock ile durdur/devam, F12 ile çıkış, DC sonrası oyuna yeniden giriş, /town fallback, 598→597 mikro adım gibi özel mantıkları ayrı başlıklar halinde açıkla.
>    * YAMA / patch ile ilgili özel hook’lar (örneğin “[YAMA]” logları, patch fonksiyonları) varsa isimleriyle birlikte kısaca anlat.
> 5. **Riskli / Karışık Kısımlar**
>
>    * Kodun hangi bölümleri **çok karmaşık veya kırılgan** görünüyor? (örneğin: birbirine çok bağlı fonksiyonlar, çok fazla global kullanan yerler, aynı işi yapan tekrar eden fonksiyonlar, vs.)
>    * Hangi kısımlar **refactor için aday**? Örneğin:
>
>      * Çok uzun fonksiyonlar,
>      * Aynı işi yapan ama isimleri farklı olan fonksiyonlar,
>      * Tekrarlayan `pyautogui` tıklama ve koordinat kodları,
>      * Aynı log mesajını veya kontrolü tekrar eden bölümler.
> 6. **Özet**
>
>    * Son olarak, bu dosyayı tamamen baştan, daha temiz ve modüler şekilde yazmak isteseydin, hangi ana **bölüm başlıkları** altında toplardın? Örneğin:
>
>      * `core_input.py` (klavye/mouse/DirectInput),
>      * `ko_window.py` (pencere bulma & login),
>      * `stairs_module.py` (merdiven +7/+8),
>      * `market_module.py` (pazar),
>      * `bank_module.py` (banka),
>      * `gui.py` (Tkinter arayüz),
>      * vs.
>
> Çıktında **kesinlikle yeni kod yazma**; sadece Merdiven.py dosyamı ayrıntılı şekilde analiz eden bir doküman ver.
> Amacım: Önce mevcut yapıyı anlamak, sonra senden “aynı davranışı koruyan ama daha temiz yazılmış yeni bir sürüm” istemek.

---

## 🛠 PROMPT 2 – “Aynı davranış, daha temiz stil” (Refactor / Baştan yazdırma)

**REFRAKTOR / YENİDEN YAZIM MESAJI – Codex’e göndereceğin metin:**

> Aşağıya Knight Online için yazdığım mevcut `Merdiven.py` dosyasını ekliyorum.
> Bu dosyanın yaptığı işi ve ana modülleri bir önceki adımda birlikte analiz ettik.
>
> Şimdi senden şunu istiyorum:
>
> 👉 Aynı davranışı koruyan, ama **daha düzenli, temiz ve okunabilir** bir **`Merdiven_v2.py`** sürümü yaz.
>
> Lütfen aşağıdaki kurallara **çok dikkat et**:
>
> ---
>
> ### A. DAVRANIŞ KESİNLİKLE KORUNACAK
>
> * Yeni dosya, oyun içinde **eski Merdiven.py ile aynı mantıkta** çalışmalı:
>
>   * Oyun penceresini bulma, login, server seçme,
>   * Merdiven +7/+8 basma döngüsü (NPC’den alış, Anvil’e gitme, +7→+8 denemeleri),
>   * Banka & depo mantığı (itemleri al, bas, +7’leri bankaya at),
>   * Pazar / item satışı modu,
>   * NPC’den item satın alma modu,
>   * DC sonrası oyuna yeniden giriş mantığı,
>   * HP bar kontrolü, CapsLock durdur/devam, F12 ile çıkış,
>   * /town ve koordinat reset mantığı,
>   * 598→597 mikro adım ve diğer hassas koordinat akışları.
> * Yani **özellik silme veya davranış değiştirme** yok.
>   Sadece kod stili ve yapısı sadeleşsin.
>
> ---
>
> ### B. FONKSİYON İSİMLERİ VE API MÜMKÜN OLDUĞUNCA AYNI KALSIN
>
> * `_MERDIVEN_RUN_GUI()`, `start()`, `stop()`, `apply_core()`, `load()`, `save()`, GUI class’ı (`_GUI`), log fonksiyonları, vs. **mümkün olduğunca aynı isimlerle** kalsın.
> * JSON config sisteminde kullanılan key’ler (`self.v["..."]` sözlüğü) **değişmesin**:
>
>   * Örneğin: `speed_profile`, `operation_mode`, NPC/Banka koordinatları, zamanlayıcılar, boş slot eşikleri vb.
> * YAMA / patch sistemimin eski log anahtarlarına güvendiğini unutma:
>
>   * Örn: `[YAMA]`, `[BUY_MODE]`, `[TOWN]`, `[SCROLL]` gibi log prefix’leri varsa **aynen bırak**.
>
> Amacım, gerekirse bir süre eski ve yeni sürümü paralel kullanabilmek; bu yüzden dış API ve önemli isimler korunmalı.
>
> ---
>
> ### C. KODU NASIL TEMİZLEMENİ İSTİYORUM (REFRAKTOR KURALLARI)
>
> 1. **İlgili fonksiyonları grupla ve sırala**
>
>    * Örneğin:
>
>      * Üstte import’lar + sabitler,
>      * Sonra input/DirectInput yardımcı fonksiyonları,
>      * Sonra pencere & login fonksiyonları,
>      * Sonra Merdiven +7/+8 modülü,
>      * Sonra Pazar modülü,
>      * Sonra NPC alış, banka modülleri,
>      * En sonda GUI ve `if __name__ == "__main__":` bloğu.
> 2. **Tekrarlayan kodları yardımcı fonksiyonlara al**
>
>    * Aynı tıklama/mouse hareketi / bekleme kalıplarını mümkün olduğunca bir fonksiyon haline getir (örn. `click_and_wait(x, y, delay_ms)` gibi).
>    * Aynı log satırını 5 yerde yazmak yerine bir helper fonksiyon kullan.
> 3. **Gereksiz / kullanılmayan fonksiyonları tespit et ve ÇIKARTMADAN ÖNCE yorum satırına al**
>
>    * Eğer tamamen kullanılmayan fonksiyonlar bulursan:
>
>      * Önce onları kodun altına taşımayı ve üzerlerine “UNUSED / ESKİ VERSİYON” yorumu yazmayı,
>      * Ya da gövdesini yorum satırı yapıp başına açıklama eklemeyi tercih et.
>    * Benim için güvenlik önemli; kritik bir şeyi yanlışlıkla silmeni istemiyorum.
>      O yüzden **silmek yerine, “eski ama tutuluyor” şeklinde yorumlayabilirsin**.
> 4. **Büyük fonksiyonları böl**
>
>    * Çok uzun (örneğin 200+ satır) fonksiyonları daha küçük anlamlı parçalara böl ama:
>
>      * Dışarıdan çağrılan ana fonksiyon isimleri aynı kalsın,
>      * İçerde mantığı parçalayan `_step1`, `_step2` gibi yardımcılar kullan.
> 5. **Yorum satırlarını sadeleştir**
>
>    * Faydasız, “açık olanı” söyleyen yorumları kaldırabilirsin.
>    * Önemli akış noktalarına (örneğin “DC tespit edildi → yeniden giriş başlatılıyor”) kısa ama anlamlı yorumlar ekle.
> 6. **Boşluk ve stil**
>
>    * PEP8’e makul seviyede yaklaş (çok takılmana gerek yok ama göze hoş görünsün).
>    * Gereksiz boş satırları azalt, çok sıkışık da yapma.
>
> ---
>
> ### D. GUI VE CONFIG DAVRANIŞI KESİNLİKLE AYNI KALSIN
>
> * Tkinter GUI’deki tab sayısı, tab adları ve ana alanlar **aynen kalsın** (Genel, Satın Alma, Item Satış, Hız, Gelişmiş, Durum, Hız/Anvil/PREC598, vs.).
> * `self.v[...]` içindeki değişkenlerin GUI alanlarıyla bağları bozulmasın.
> * `save()` fonksiyonu:
>
>   * Aynı JSON dosya yoluna yazsın,
>   * Aynı key’leri kullansın.
> * `load()` ve `apply_core()`:
>
>   * Ayarları eskisi gibi global değişkenlere uygulasın,
>   * Harici dosyalar / template’ler / resimler varsa aynı şekilde yüklensin.
>
> Bu projede dış dünyaya dokunan kısımlar (pencere başlığı, exe yolları, resim dosyaları, tesseract yolu, vb.) çok hassas; bu yüzden **bunların değerlerini veya temel kullanım şeklini değiştirme**.
>
> ---
>
> ### E. ÇIKTI ŞEKLİ
>
> * Bana tek bir Python dosyası olarak **tamamen çalışabilir** bir `Merdiven_v2.py` ver. 
> * Dosyanın en üstüne kısa bir yorum bloğu ekle:
>
>   * Versiyon notu,
>   * “Eski Merdiven.py’nin refactor edilmiş sürümü” açıklaması,
>   * Hangi ana bölümler olduğunu (header, core, modules, GUI, main).
> * Eski `Merdiven.py` ile yan yana diff kontrolü yapabilmem için:
>
>   * Mümkün olduğunca aynı fonksiyon isimlerini ve log mesajlarını kullan,
>   * Sadece yapıyı ve düzeni iyileştir.
>
> Eğer davranışın bire bir korunmasından emin olamadığın yerler olursa, kodun o bölümünün üstüne kısa bir `# TODO:` yorumu ekleyerek beni uyar.
>
> Lütfen tüm bu kurallara uyarak, Merdiven.py dosyamdan yola çıkıp **daha temiz, modüler ve okunabilir ama aynı işi yapan** bir `Merdiven_v2.py` üret.
