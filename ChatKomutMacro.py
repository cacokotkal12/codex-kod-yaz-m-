import ctypes
import json
import os
import queue
import threading
import time
import tkinter as tk
from ctypes import wintypes
from tkinter import messagebox

# ===== Duzenlenebilir ayarlar =====
TICK_MS = 200
KEY_DELAY = 0.05
SONRASI_GECIKME = 0.03
MIN_SURE = 0.1
KONFIG_KLASOR = "ChatKomutMacro"
KONFIG_DOSYA = "config.json"

# ===== WinAPI sabitleri =====
CF_UNICODETEXT = 13
GMEM_MOVEABLE = 0x0002
VK_RETURN = 0x0D
VK_CONTROL = 0x11
VK_V = 0x56
INPUT_KEYBOARD = 1
KEYEVENTF_KEYUP = 0x0002


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", wintypes.ULONG_PTR),
    ]


class INPUTUNION(ctypes.Union):
    _fields_ = [("ki", KEYBDINPUT)]


class INPUT(ctypes.Structure):
    _fields_ = [("type", wintypes.DWORD), ("union", INPUTUNION)]


class SatirUI:
    def __init__(self, parent, sil_callback):
        self.aktif = tk.BooleanVar(value=True)
        self.sure = tk.StringVar(value="10")
        self.metin = tk.StringVar(value="")
        self.adet = tk.StringVar(value="1")
        self.sonsuz = tk.BooleanVar(value=False)
        self.kalan = tk.StringVar(value="Kalan: -")
        self.gonderildi = tk.StringVar(value="Gonderildi: 0")

        self.gonderilen_sayi = 0
        self.sonraki_gonderim = None

        self.chk_aktif = tk.Checkbutton(parent, variable=self.aktif)
        self.ent_sure = tk.Entry(parent, textvariable=self.sure, width=8)
        self.ent_metin = tk.Entry(parent, textvariable=self.metin, width=44)
        self.ent_adet = tk.Entry(parent, textvariable=self.adet, width=8)
        self.chk_sonsuz = tk.Checkbutton(parent, variable=self.sonsuz, command=self._sonsuz_degisti)
        self.lbl_kalan = tk.Label(parent, textvariable=self.kalan, fg="#1c4587", anchor="w")
        self.lbl_gonderildi = tk.Label(parent, textvariable=self.gonderildi, fg="#38761d", anchor="w")
        self.btn_sil = tk.Button(parent, text="Satir Sil", command=lambda: sil_callback(self))

        self._sonsuz_degisti()

    def grid(self, row_index):
        self.chk_aktif.grid(row=row_index, column=0, padx=3, pady=2)
        self.ent_sure.grid(row=row_index, column=1, padx=3, pady=2)
        self.ent_metin.grid(row=row_index, column=2, padx=3, pady=2, sticky="we")
        self.ent_adet.grid(row=row_index, column=3, padx=3, pady=2)
        self.chk_sonsuz.grid(row=row_index, column=4, padx=3, pady=2)
        self.lbl_kalan.grid(row=row_index, column=5, padx=3, pady=2, sticky="w")
        self.lbl_gonderildi.grid(row=row_index, column=6, padx=3, pady=2, sticky="w")
        self.btn_sil.grid(row=row_index, column=7, padx=3, pady=2)

    def destroy(self):
        self.chk_aktif.destroy()
        self.ent_sure.destroy()
        self.ent_metin.destroy()
        self.ent_adet.destroy()
        self.chk_sonsuz.destroy()
        self.lbl_kalan.destroy()
        self.lbl_gonderildi.destroy()
        self.btn_sil.destroy()

    def _sonsuz_degisti(self):
        if self.sonsuz.get():
            self.ent_adet.config(state="disabled")
        else:
            self.ent_adet.config(state="normal")

    def parse_sure(self):
        try:
            return max(MIN_SURE, float(self.sure.get().strip().replace(",", ".")))
        except Exception:
            return 10.0

    def parse_adet(self):
        if self.sonsuz.get():
            return None
        try:
            adet = int(float(self.adet.get().strip().replace(",", ".")))
            return max(0, adet)
        except Exception:
            return 0

    def reset_sayac(self, baslangic_zamani):
        self.gonderilen_sayi = 0
        self.gonderildi.set("Gonderildi: 0")
        self.sonraki_gonderim = baslangic_zamani + self.parse_sure()
        self.kalan.set(f"Kalan: {self.parse_sure():.1f} sn")

    def kayit_dict(self):
        return {
            "aktif": bool(self.aktif.get()),
            "sure": self.sure.get(),
            "metin": self.metin.get(),
            "adet": self.adet.get(),
            "sonsuz": bool(self.sonsuz.get()),
        }


class ChatKomutMacroApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Chat Komut Macro")
        self.satirlar = []
        self.calisiyor = False
        self.kuyruk = queue.Queue()
        self.stop_event = threading.Event()
        self.worker_thread = None
        self.genel_durum = tk.StringVar(value="Hazir")
        self._api_hazirla()
        self._config_yolu_hazirla()
        self._ui_kur()
        self._load_config()
        if not self.satirlar:
            self.satir_ekle()
        self._satir_grid_yenile()
        self.root.protocol("WM_DELETE_WINDOW", self.kapat)
        self.root.after(TICK_MS, self.tick)

    def _api_hazirla(self):
        self.user32 = ctypes.windll.user32
        self.kernel32 = ctypes.windll.kernel32

    def _config_yolu_hazirla(self):
        appdata = os.environ.get("APPDATA") or os.path.expanduser("~")
        self.config_klasor = os.path.join(appdata, KONFIG_KLASOR)
        self.config_path = os.path.join(self.config_klasor, KONFIG_DOSYA)

    def _ui_kur(self):
        ust = tk.Frame(self.root)
        ust.pack(fill="x", padx=8, pady=8)

        self.btn_baslat = tk.Button(ust, text="Baslat", bg="#6aa84f", fg="white", width=12, command=self.baslat)
        self.btn_durdur = tk.Button(ust, text="Durdur", bg="#e69138", fg="white", width=12, command=self.durdur)
        self.btn_kaydet = tk.Button(ust, text="Kaydet", bg="#3d85c6", fg="white", width=12, command=self.kaydet)
        self.btn_ekle = tk.Button(ust, text="Satir Ekle", width=12, command=self.satir_ekle)

        self.btn_baslat.pack(side="left", padx=3)
        self.btn_durdur.pack(side="left", padx=3)
        self.btn_kaydet.pack(side="left", padx=3)
        self.btn_ekle.pack(side="left", padx=3)
        tk.Label(ust, textvariable=self.genel_durum, fg="#134f5c").pack(side="right", padx=4)

        baslik = tk.Frame(self.root)
        baslik.pack(fill="x", padx=8)
        etiketler = ["Aktif", "Sure(sn)", "Metin", "Adet", "Sonsuz", "Kalan", "Sayac", "Islem"]
        genislik = [6, 8, 44, 8, 8, 16, 14, 8]
        for i, txt in enumerate(etiketler):
            tk.Label(baslik, text=txt, width=genislik[i], anchor="w").grid(row=0, column=i, padx=3, pady=(0, 3), sticky="w")

        self.liste = tk.Frame(self.root)
        self.liste.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        self.liste.grid_columnconfigure(2, weight=1)

    def satir_ekle(self, veri=None):
        satir = SatirUI(self.liste, self.satir_sil)
        if veri:
            satir.aktif.set(bool(veri.get("aktif", True)))
            satir.sure.set(str(veri.get("sure", "10")))
            satir.metin.set(str(veri.get("metin", "")))
            satir.adet.set(str(veri.get("adet", "1")))
            satir.sonsuz.set(bool(veri.get("sonsuz", False)))
            satir._sonsuz_degisti()
        self.satirlar.append(satir)
        self._satir_grid_yenile()

    def satir_sil(self, satir):
        if satir in self.satirlar:
            satir.destroy()
            self.satirlar.remove(satir)
            self._satir_grid_yenile()

    def _satir_grid_yenile(self):
        for i, satir in enumerate(self.satirlar):
            satir.grid(i)

    def _load_config(self):
        if not os.path.exists(self.config_path):
            return
        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            geometry = data.get("geometry")
            if geometry:
                self.root.geometry(geometry)
            satirlar = data.get("satirlar", [])
            if isinstance(satirlar, list):
                for s in satirlar:
                    self.satir_ekle(s)
        except Exception:
            pass

    def kaydet(self):
        os.makedirs(self.config_klasor, exist_ok=True)
        data = {
            "geometry": self.root.geometry(),
            "satirlar": [s.kayit_dict() for s in self.satirlar],
        }
        with open(self.config_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        self.genel_durum.set("Kaydedildi")

    def baslat(self):
        if self.calisiyor:
            return
        if not self.satirlar:
            messagebox.showwarning("Uyari", "En az bir satir ekleyin.")
            return
        self.calisiyor = True
        self.stop_event.clear()
        while not self.kuyruk.empty():
            try:
                self.kuyruk.get_nowait()
            except queue.Empty:
                break
        now = time.time()
        for satir in self.satirlar:
            satir.reset_sayac(now)
        if self.worker_thread is None or not self.worker_thread.is_alive():
            self.worker_thread = threading.Thread(target=self.worker_dongu, daemon=True)
            self.worker_thread.start()
        self.genel_durum.set("Calisiyor")

    def durdur(self):
        self.calisiyor = False
        self.stop_event.set()
        while not self.kuyruk.empty():
            try:
                self.kuyruk.get_nowait()
            except queue.Empty:
                break
        self.genel_durum.set("Durduruldu")

    def tick(self):
        simdi = time.time()
        en_yakin = None
        aktif_var = False

        if self.calisiyor:
            for satir in self.satirlar:
                if not satir.aktif.get():
                    satir.kalan.set("Kalan: pasif")
                    continue

                hedef_adet = satir.parse_adet()
                if hedef_adet is not None and satir.gonderilen_sayi >= hedef_adet:
                    satir.kalan.set("Kalan: tamamlandi")
                    continue

                aktif_var = True
                if satir.sonraki_gonderim is None:
                    satir.sonraki_gonderim = simdi + satir.parse_sure()

                kalan = max(0.0, satir.sonraki_gonderim - simdi)
                satir.kalan.set(f"Kalan: {kalan:.1f} sn")

                if en_yakin is None or kalan < en_yakin:
                    en_yakin = kalan

                if simdi >= satir.sonraki_gonderim:
                    self.kuyruk.put(satir)
                    satir.sonraki_gonderim = simdi + satir.parse_sure()

            if not aktif_var:
                self.calisiyor = False
                self.stop_event.set()
                self.genel_durum.set("Tum satirlar tamamlandi")
            elif en_yakin is not None:
                self.genel_durum.set(f"Calisiyor | En yakin: {en_yakin:.1f} sn")

        self.root.after(TICK_MS, self.tick)

    def worker_dongu(self):
        while not self.stop_event.is_set():
            try:
                satir = self.kuyruk.get(timeout=0.2)
            except queue.Empty:
                continue
            if not self.calisiyor:
                continue
            self._gonderim_yap(satir)

    def _gonderim_yap(self, satir):
        metin = satir.metin.get()
        if not metin:
            return
        if not self._clipboard_yaz(metin):
            return
        self._key_tap(VK_RETURN)
        time.sleep(KEY_DELAY)
        self._ctrl_v()
        time.sleep(KEY_DELAY)
        self._key_tap(VK_RETURN)
        time.sleep(SONRASI_GECIKME)

        satir.gonderilen_sayi += 1
        yeni = satir.gonderilen_sayi
        self.root.after(0, lambda: satir.gonderildi.set(f"Gonderildi: {yeni}"))

    def _send_input(self, vk, keyup=False):
        flags = KEYEVENTF_KEYUP if keyup else 0
        ki = KEYBDINPUT(wVk=vk, wScan=0, dwFlags=flags, time=0, dwExtraInfo=0)
        data = INPUT(type=INPUT_KEYBOARD, union=INPUTUNION(ki=ki))
        self.user32.SendInput(1, ctypes.byref(data), ctypes.sizeof(INPUT))

    def _key_tap(self, vk):
        self._send_input(vk, keyup=False)
        time.sleep(KEY_DELAY)
        self._send_input(vk, keyup=True)

    def _ctrl_v(self):
        self._send_input(VK_CONTROL, keyup=False)
        time.sleep(KEY_DELAY)
        self._key_tap(VK_V)
        time.sleep(KEY_DELAY)
        self._send_input(VK_CONTROL, keyup=True)

    def _clipboard_yaz(self, metin):
        data = ctypes.create_unicode_buffer(metin + "\0")
        boyut = ctypes.sizeof(data)
        h_mem = self.kernel32.GlobalAlloc(GMEM_MOVEABLE, boyut)
        if not h_mem:
            return False
        kilitli_ptr = self.kernel32.GlobalLock(h_mem)
        if not kilitli_ptr:
            self.kernel32.GlobalFree(h_mem)
            return False
        ctypes.memmove(kilitli_ptr, ctypes.addressof(data), boyut)
        self.kernel32.GlobalUnlock(h_mem)

        if not self.user32.OpenClipboard(None):
            self.kernel32.GlobalFree(h_mem)
            return False
        try:
            self.user32.EmptyClipboard()
            if not self.user32.SetClipboardData(CF_UNICODETEXT, h_mem):
                self.kernel32.GlobalFree(h_mem)
                return False
            h_mem = None
            return True
        finally:
            self.user32.CloseClipboard()
            if h_mem:
                self.kernel32.GlobalFree(h_mem)

    def kapat(self):
        self.durdur()
        self.kaydet()
        self.root.destroy()


def main():
    if os.name != "nt":
        raise OSError("Bu uygulama yalnizca Windows icindir.")
    root = tk.Tk()
    ChatKomutMacroApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
