import json
import os
import threading
import time
import tkinter as tk
from tkinter import messagebox

try:
    from ko_input_backend import send_ctrl_v, send_enter
except ModuleNotFoundError:
    import importlib.util
    import sys

    _ko_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ko_input_backend.py")
    if os.path.exists(_ko_path):
        _spec = importlib.util.spec_from_file_location("ko_input_backend", _ko_path)
        _mod = importlib.util.module_from_spec(_spec)
        sys.modules["ko_input_backend"] = _mod
        _spec.loader.exec_module(_mod)
        send_ctrl_v = _mod.send_ctrl_v
        send_enter = _mod.send_enter
    else:
        def send_enter():
            return

        def send_ctrl_v():
            return

        print("[CHAT_MAKRO] ko_input_backend bulunamadi. Tus gonderimi pasif.")


AYAR_DOSYA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "chat_makro_ayar.json")


class Satir:
    def __init__(self, parent, idx, sil_callback):
        self.parent = parent
        self.idx = idx
        self.sil_callback = sil_callback
        self.aktif = tk.BooleanVar(value=True)
        self.metin = tk.StringVar(value="")
        self.sure = tk.DoubleVar(value=10.0)
        self.adet = tk.IntVar(value=0)
        self.kalan_yazi = tk.StringVar(value="-")
        self.sonraki_zaman = None
        self.gonderilen = 0

        self.chk = tk.Checkbutton(parent, variable=self.aktif)
        self.lbl_no = tk.Label(parent, text=f"{idx}.", width=3, anchor="w")
        self.ent_metin = tk.Entry(parent, textvariable=self.metin, width=38)
        self.ent_sure = tk.Entry(parent, textvariable=self.sure, width=8)
        self.ent_adet = tk.Entry(parent, textvariable=self.adet, width=8)
        self.lbl_kalan = tk.Label(parent, textvariable=self.kalan_yazi, width=18, anchor="w", fg="#004d99")
        self.btn_sil = tk.Button(parent, text="Sil", command=self.sil, bg="#f4cccc", activebackground="#ea9999")

    def yerlestir(self, row):
        self.chk.grid(row=row, column=0, padx=2, pady=2)
        self.lbl_no.grid(row=row, column=1, padx=2, pady=2, sticky="w")
        self.ent_metin.grid(row=row, column=2, padx=2, pady=2, sticky="we")
        self.ent_sure.grid(row=row, column=3, padx=2, pady=2)
        self.ent_adet.grid(row=row, column=4, padx=2, pady=2)
        self.lbl_kalan.grid(row=row, column=5, padx=2, pady=2, sticky="w")
        self.btn_sil.grid(row=row, column=6, padx=2, pady=2)

    def sil(self):
        self.chk.destroy()
        self.lbl_no.destroy()
        self.ent_metin.destroy()
        self.ent_sure.destroy()
        self.ent_adet.destroy()
        self.lbl_kalan.destroy()
        self.btn_sil.destroy()
        self.sil_callback(self)

    def kayda_donustur(self):
        return {
            "aktif": bool(self.aktif.get()),
            "metin": self.metin.get(),
            "sure": float(self.sure.get()),
            "adet": int(self.adet.get()),
        }


class ChatMakro:
    def __init__(self, root):
        self.root = root
        self.root.title("Chat Makro")
        self.root.geometry("860x430")

        self.calisiyor = False
        self.thread = None
        self.kilit = threading.Lock()
        self.satirlar = []

        self.ust_durum = tk.StringVar(value="Hazir")
        self.genel_sayac = tk.StringVar(value="Baslatilmadi")

        self.ust_bar = tk.Frame(root)
        self.ust_bar.pack(fill="x", padx=8, pady=6)

        self.btn_baslat = tk.Button(self.ust_bar, text="Baslat", command=self.baslat, bg="#93c47d", activebackground="#6aa84f", width=12)
        self.btn_durdur = tk.Button(self.ust_bar, text="Durdur", command=self.durdur, bg="#e06666", activebackground="#cc0000", width=12)
        self.btn_kaydet = tk.Button(self.ust_bar, text="Kaydet", command=self.kaydet, bg="#6fa8dc", activebackground="#3d85c6", width=12)
        self.btn_konum_kaydet = tk.Button(self.ust_bar, text="Konumu Kaydet", command=self.konum_kaydet, bg="#ffd966", activebackground="#f1c232", width=12)
        self.btn_satir_ekle = tk.Button(self.ust_bar, text="Satir Ekle", command=self.satir_ekle, bg="#d5a6bd", activebackground="#c27ba0", width=12)

        self.btn_baslat.pack(side="left", padx=3)
        self.btn_durdur.pack(side="left", padx=3)
        self.btn_kaydet.pack(side="left", padx=3)
        self.btn_konum_kaydet.pack(side="left", padx=3)
        self.btn_satir_ekle.pack(side="left", padx=3)

        self.lbl_durum = tk.Label(self.ust_bar, textvariable=self.ust_durum, fg="#1c4587")
        self.lbl_durum.pack(side="right", padx=6)

        self.baslik = tk.Frame(root)
        self.baslik.pack(fill="x", padx=8)
        tk.Label(self.baslik, text="", width=2).grid(row=0, column=0)
        tk.Label(self.baslik, text="#", width=3, anchor="w").grid(row=0, column=1, sticky="w")
        tk.Label(self.baslik, text="Metin", anchor="w").grid(row=0, column=2, sticky="w")
        tk.Label(self.baslik, text="Sure(sn)").grid(row=0, column=3)
        tk.Label(self.baslik, text="Adet(0=sonsuz)").grid(row=0, column=4)
        tk.Label(self.baslik, text="Kalan", anchor="w").grid(row=0, column=5, sticky="w")

        self.liste_frame = tk.Frame(root)
        self.liste_frame.pack(fill="both", expand=True, padx=8, pady=4)
        self.liste_frame.grid_columnconfigure(2, weight=1)

        self.alt_bar = tk.Frame(root)
        self.alt_bar.pack(fill="x", padx=8, pady=6)
        tk.Label(self.alt_bar, text="Sayac:").pack(side="left")
        tk.Label(self.alt_bar, textvariable=self.genel_sayac, fg="#38761d").pack(side="left", padx=6)

        self.ayarlari_yukle()
        if not self.satirlar:
            self.satir_ekle()
        self.satirlari_yeniden_numarala()

        self.root.protocol("WM_DELETE_WINDOW", self.cikis)
        self.root.after(200, self.sayac_guncelle)

    def satir_ekle(self, veri=None):
        idx = len(self.satirlar) + 1
        satir = Satir(self.liste_frame, idx, self.satir_silindi)
        if veri:
            satir.aktif.set(bool(veri.get("aktif", True)))
            satir.metin.set(str(veri.get("metin", "")))
            satir.sure.set(float(veri.get("sure", 10.0)))
            satir.adet.set(int(veri.get("adet", 0)))
        self.satirlar.append(satir)
        self.satirlari_yeniden_numarala()

    def satir_silindi(self, satir):
        if satir in self.satirlar:
            self.satirlar.remove(satir)
            self.satirlari_yeniden_numarala()

    def satirlari_yeniden_numarala(self):
        for i, satir in enumerate(self.satirlar, start=1):
            satir.idx = i
            satir.lbl_no.config(text=f"{i}.")
            satir.yerlestir(i - 1)

    def ayarlari_yukle(self):
        if not os.path.exists(AYAR_DOSYA):
            return
        try:
            with open(AYAR_DOSYA, "r", encoding="utf-8") as f:
                data = json.load(f)
            geo = data.get("pencere_konum", "")
            if geo:
                self.root.geometry(geo)
            satirlar = data.get("satirlar", [])
            if isinstance(satirlar, list):
                for s in satirlar:
                    self.satir_ekle(s)
        except Exception:
            pass

    def kaydet(self):
        data = {
            "pencere_konum": self.root.geometry(),
            "satirlar": [s.kayda_donustur() for s in self.satirlar],
        }
        with open(AYAR_DOSYA, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        self.ust_durum.set("Kaydedildi")

    def konum_kaydet(self):
        data = {}
        if os.path.exists(AYAR_DOSYA):
            try:
                with open(AYAR_DOSYA, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except Exception:
                data = {}
        data["pencere_konum"] = self.root.geometry()
        if "satirlar" not in data:
            data["satirlar"] = [s.kayda_donustur() for s in self.satirlar]
        with open(AYAR_DOSYA, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        self.ust_durum.set("Konum kaydedildi")

    def baslat(self):
        if self.calisiyor:
            return
        if not self.satirlar:
            messagebox.showwarning("Uyari", "En az bir satir ekleyin.")
            return
        self.calisiyor = True
        now = time.time()
        for s in self.satirlar:
            s.gonderilen = 0
            s.sonraki_zaman = now + max(0.1, float(s.sure.get()))
            s.kalan_yazi.set("hazirlaniyor")
        self.thread = threading.Thread(target=self.dongu, daemon=True)
        self.thread.start()
        self.ust_durum.set("Calisiyor")

    def durdur(self):
        self.calisiyor = False
        self.ust_durum.set("Durduruldu")

    def _satir_gonder(self, satir):
        metin = satir.metin.get()
        if metin == "":
            return
        try:
            self.root.clipboard_clear()
            self.root.clipboard_append(metin)
            self.root.update()
        except Exception:
            return
        send_enter()
        time.sleep(0.04)
        send_ctrl_v()
        time.sleep(0.04)
        send_enter()
        satir.gonderilen += 1

    def dongu(self):
        while self.calisiyor:
            now = time.time()
            aktif_satir_var = False
            for satir in self.satirlar:
                if not satir.aktif.get():
                    satir.kalan_yazi.set("pasif")
                    continue
                adet = int(satir.adet.get())
                if adet > 0 and satir.gonderilen >= adet:
                    satir.kalan_yazi.set("tamamlandi")
                    continue
                aktif_satir_var = True
                sure = max(0.1, float(satir.sure.get()))
                if satir.sonraki_zaman is None:
                    satir.sonraki_zaman = now + sure
                if now >= satir.sonraki_zaman:
                    self._satir_gonder(satir)
                    satir.sonraki_zaman = time.time() + sure
            if not aktif_satir_var:
                self.calisiyor = False
                self.ust_durum.set("Tum satirlar tamamlandi")
                break
            time.sleep(0.2)

    def sayac_guncelle(self):
        now = time.time()
        en_yakin = None
        en_yakin_idx = None
        for satir in self.satirlar:
            if not satir.aktif.get():
                continue
            adet = int(satir.adet.get())
            if adet > 0 and satir.gonderilen >= adet:
                continue
            if satir.sonraki_zaman is None:
                satir.kalan_yazi.set("hazir")
                continue
            kalan = satir.sonraki_zaman - now
            if kalan < 0:
                kalan = 0
            satir.kalan_yazi.set(f"{kalan:.1f} sn")
            if en_yakin is None or kalan < en_yakin:
                en_yakin = kalan
                en_yakin_idx = satir.idx

        if en_yakin is None:
            if self.calisiyor:
                self.genel_sayac.set("islem bekleniyor")
            else:
                self.genel_sayac.set("Hazir")
        else:
            self.genel_sayac.set(f"{en_yakin_idx}. metin icin {en_yakin:.1f} sn kaldi")
        self.root.after(200, self.sayac_guncelle)

    def cikis(self):
        self.durdur()
        self.kaydet()
        self.root.destroy()


def main():
    root = tk.Tk()
    ChatMakro(root)
    root.mainloop()


if __name__ == "__main__":
    main()
