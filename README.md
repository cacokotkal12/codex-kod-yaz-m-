# codex-kod-yaz-m-zxczxczx

## Manuel test senaryosu (otomatik pazar yenileme)

1. GUI'de **Pazar yenileme aktif** kutusunu işaretleyin ve **Yenileme aralığı (saat)** alanına örneğin `3` yazıp kaydedin.
2. Makroyu Item Satış modunda başlatın; ilk pazar açılışından sonra ayarın yeniden yüklendiğini loglardan doğrulayın.
3. Belirlenen saat aralığı dolduğunda logda "Otomatik pazar yenileme tetiklendi" mesajının çıktığını ve pazarın mevcut yenileme akışını kullandığını gözlemleyin.
4. Manuel eşik tetiklemeleri (boş slot eşiği vb.) geldiğinde otomatik yenilemenin kilitlenmediğini ve en son yenileme zamanının buna göre güncellendiğini doğrulayın.
