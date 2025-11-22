# codex-kod-yaz-m-zxczxczx

## Manuel test senaryosu (otomatik pazar yenileme)

1. GUI'de **Pazar yenileme aktif** kutusunu işaretleyin ve **Yenileme aralığı (saat)** alanına örneğin `3` yazıp kaydedin.
2. Makroyu Item Satış modunda başlatın; ilk pazar açılışından sonra ayarın yeniden yüklendiğini loglardan doğrulayın.
3. Belirlenen saat aralığı dolduğunda logda "Otomatik pazar yenileme tetiklendi" mesajının çıktığını ve pazarın mevcut yenileme akışını kullandığını gözlemleyin.
4. Manuel eşik tetiklemeleri (boş slot eşiği vb.) geldiğinde otomatik yenilemenin kilitlenmediğini ve en son yenileme zamanının buna göre güncellendiğini doğrulayın.

## Manuel test senaryosu (krallık yazısı & doğrulama)

1. Item Satış sekmesinde **Krallık yazısı tıklama aktif** kutusunu işaretleyin, koordinatı varsayılan (800,281) bırakın ve **Tekrar aralığı** alanına `0` gibi geçersiz bir değer yazıp **Kaydet**'e basın; arayüzün değeri otomatik olarak `1` saniyeye çekip hatalı girdiyi engellediğini doğrulayın.
2. Aynı ekranda **Pazar yenileme aralığı (saat)** alanına `0.1` gibi düşük bir değer girin ve kaydedin; uygulamanın değeri en düşük 0.25 saat (15 dk) olarak tuttuğunu kontrol edin.
3. Makroyu Item Satış modunda başlatın; pazar kurulduktan sonra logda krallık yazısı tıklama satırlarının saatli olarak geldiğini görün.
4. Banka eşiğiyle pazar yenilemesini tetikleyin; yenilemeden hemen sonraki 5 saniye boyunca krallık yazısı tıklamasının beklediğini, süre dolduğunda yeniden başladığını doğrulayın.
5. Bilerek geçersiz/büyük sayılar girip kaydedin (ör. **Basılı tutma (ms)** alanına `50000`); değerlerin kayıttan sonra 2000 ms üst sınırına oturtulduğunu ve makronun sorunsuz devam ettiğini gözlemleyin.
