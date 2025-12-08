# codex-kod-yaz-m-zxczxczx

## PyInstaller/EXE dönüştürme notu
- Merdiven.py'yi PyInstaller ile .exe'ye çevirirken 0xc000007b hatası alırsanız genellikle 32/64-bit uyumsuzluğu veya eksik Visual C++ runtime neden olur.
- Çözüm: 64-bit Python ve 64-bit PyInstaller kullanın; Windows için "x64" Visual C++ Redistributable paketini kurun; Tesseract gibi harici DLL'lerin de aynı mimaride olduğundan emin olun.
- Eğer farklı bir Python sürümünden gelen `pywintypesXX.dll` karışıyorsa, derleme öncesi `pip install --upgrade pywin32` komutuyla modülü güncelleyin ve `.spec` dosyasındaki `binaries` bölümüne dahil olduğundan emin olun.

## 1289. satır hatası neyi ifade ediyor?
- Ekran görüntüsünde görünen 1289. satır aslında `_wm_close_hwnds` fonksiyonunun hemen önündeki boş satıra denk geliyor; hata, altındaki Windows API çağrısından (`ctypes.windll.user32`) kaynaklanıyor.
- Bu kod yalnızca Windows'ta çalışır. Script'i WSL/Linux/macOS gibi ortamlarda çalıştırırsanız `ctypes` içinde `windll` olmadığı için "module 'ctypes' has no attribute 'windll'" benzeri hatalar alırsınız. Çözüm: script'i ve PyInstaller derlemesini yerel bir Windows oturumunda çalıştırın.

## "'type' object is not subscriptable" hatası ne demek?
- Python 3.8 ve öncesinde yerleşik tipleri (list, set vb.) `list[int]`, `set[str]` gibi köşeli parantezle kullandığınızda doğrudan `TypeError: 'type' object is not subscriptable` alırsınız; çünkü bu sözdizimi 3.9+ sürümlerinde desteklenir.
- Merdiven.py içindeki satır 1289 civarındaki yardımcı fonksiyonlar (`_pids_by_image`, `_pids_from_hwnds`, `_wm_close_hwnds`, `_kill_pids`) bu sözdizimini kullanıyordu; Python 3.8 tabanlı bir PyInstaller/EXE çalıştırıldığında hata tam bu satırlara işaret eder.
- Çözüm: Ya Python 3.9+ kullanın ya da kodda yapıldığı gibi `typing.List` / `typing.Set` ile generik tip ipuçlarını tanımlayın; böylece 3.8 ve üstü sürümlerde sorunsuz çalışır.

## Manuel test senaryosu (otomatik pazar yenileme)

1. GUI'de **Pazar yenileme aktif** kutusunu işaretleyin ve **Yenileme aralığı (saat)** alanına örneğin `3` yazıp kaydedin.
2. Makroyu Item Satış modunda başlatın; ilk pazar açılışından sonra ayarın yeniden yüklendiğini loglardan doğrulayın.
3. Belirlenen saat aralığı dolduğunda logda "Otomatik pazar yenileme tetiklendi" mesajının çıktığını ve pazarın mevcut yenileme akışını kullandığını gözlemleyin.
4. Manuel eşik tetiklemeleri (boş slot eşiği vb.) geldiğinde otomatik yenilemenin kilitlenmediğini ve en son yenileme zamanının buna göre güncellendiğini doğrulayın.
