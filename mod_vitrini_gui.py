import tkinter as tk
from tkinter import ttk
from typing import Callable, Optional, Dict, Any


STATUS_COLORS = {
    "Beklemede": "#9e9e9e",
    "Çalışıyor": "#4caf50",
    "Hata": "#f44336",
}


class ModVitriniApp(tk.Tk):
    """Knight Online makrosu için mod vitrini ana penceresi."""

    def __init__(
        self,
        on_start_mode: Optional[Callable[[str, Optional[str]], Any]] = None,
        on_stop_mode: Optional[Callable[[str], Any]] = None,
        on_speed_profile_change: Optional[Callable[[str], Any]] = None,
        on_profile_selected: Optional[Callable[[str], Any]] = None,
        *args,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        self.title("Mod Vitrini - Merdiven Makro")
        self.geometry("1200x700")
        self.minsize(960, 600)

        self.on_start_mode = on_start_mode
        self.on_stop_mode = on_stop_mode
        self.on_speed_profile_change = on_speed_profile_change
        self.on_profile_selected = on_profile_selected

        self.configure(bg="#e6e6e6")

        self.submode_stairs = tk.StringVar(value="full_cycle")
        self.bank_page_var = tk.StringVar(value="1")
        self.bank_slot_var = tk.IntVar(value=28)

        self.modes: Dict[str, Dict[str, Any]] = {
            "stairs": {
                "name": "Merdiven +7/+8 Basma",
                "status": "Beklemede",
                "description": "Bankadan +1–+6 al, +7'ye kadar bas, +7'leri bankaya at, +8 denemelerini yap",
            },
            "market": {
                "name": "Pazar Kurma – Item Satış",
                "status": "Beklemede",
                "description": "Pazar kur, slotları takip et, süre dolunca pazarı yenile ve item satışını yönet",
            },
            "npc_buy": {
                "name": "NPC’den Satın Alma",
                "status": "Beklemede",
                "description": "NPC'den 28 item satın al, envanteri doldur, basma döngüsüne hazırla",
            },
            "pc_tune": {
                "name": "PC Hızlandırma / Sistem Ayarları",
                "status": "Beklemede",
                "description": "Mini/sanal PC için hızlandırma ve sistem optimizasyon ayarlarını uygula",
            },
        }
        self.current_mode_id: Optional[str] = None

        self._card_widgets: Dict[str, Dict[str, Any]] = {}

        self._build_layout()

    # Bölüm: Layout
    def _build_layout(self) -> None:
        main_container = ttk.Frame(self, padding=10)
        main_container.pack(fill="both", expand=True)

        # Sağ panel
        self._build_right_panel(main_container)

        # Alt panel
        self._build_bottom_panel(main_container)

        # Kart alanı (sol/orta)
        cards_container = ttk.Frame(main_container)
        cards_container.pack(side="left", fill="both", expand=True)
        cards_container.columnconfigure((0, 1), weight=1, uniform="cardcols")
        cards_container.rowconfigure((0, 1), weight=1, uniform="cardrows")

        # Kartları oluştur
        mode_ids = ["stairs", "market", "npc_buy", "pc_tune"]
        for index, mode_id in enumerate(mode_ids):
            row = index // 2
            column = index % 2
            card = self._create_mode_card(cards_container, mode_id)
            card.grid(row=row, column=column, padx=8, pady=8, sticky="nsew")

    def _build_right_panel(self, parent: ttk.Frame) -> None:
        right_panel = ttk.Frame(parent, padding=(10, 10))
        right_panel.pack(side="right", fill="y")

        # Aktif Mod
        active_frame = ttk.LabelFrame(right_panel, text="Aktif Mod", padding=10)
        active_frame.pack(fill="x", pady=(0, 10))
        self.active_mode_label = ttk.Label(active_frame, text="Yok", font=("Segoe UI", 12, "bold"))
        self.active_mode_label.pack(anchor="w", pady=(0, 4))
        self.active_status_label = ttk.Label(active_frame, text="Durum: Beklemede")
        self.active_status_label.pack(anchor="w")

        # Son log
        log_frame = ttk.LabelFrame(right_panel, text="Son Log Satırı", padding=10)
        log_frame.pack(fill="x", pady=(0, 10))
        self.last_log_var = tk.StringVar(value="Henüz log yok")
        log_label = ttk.Label(log_frame, textvariable=self.last_log_var, wraplength=220, justify="left")
        log_label.pack(fill="x")

        # Hız profili
        speed_frame = ttk.LabelFrame(right_panel, text="Hız Profili", padding=10)
        speed_frame.pack(fill="x")
        self.speed_profile_var = tk.StringVar(value="BALANCED")
        speed_combo = ttk.Combobox(
            speed_frame,
            textvariable=self.speed_profile_var,
            values=["FAST", "BALANCED", "SAFE"],
            state="readonly",
        )
        speed_combo.pack(fill="x")
        speed_combo.bind("<<ComboboxSelected>>", self._on_speed_profile_change)

    def _build_bottom_panel(self, parent: ttk.Frame) -> None:
        bottom_frame = ttk.LabelFrame(parent, text="Son Kullanılan Profiller", padding=10)
        bottom_frame.pack(side="bottom", fill="x", pady=(10, 0))

        profiles_container = ttk.Frame(bottom_frame)
        profiles_container.pack(fill="x")

        self.profile_buttons: Dict[str, ttk.Button] = {}
        for profile in ["V1_VMWARE_SAFE", "MiniPC_Hızlı"]:
            btn = ttk.Button(
                profiles_container,
                text=profile,
                command=lambda p=profile: self._on_profile_selected(p),
            )
            btn.pack(side="left", padx=4)
            self.profile_buttons[profile] = btn

    def _create_mode_card(self, parent: ttk.Frame, mode_id: str) -> ttk.Frame:
        mode_info = self.modes[mode_id]

        card = ttk.Frame(parent, padding=12, relief="groove", borderwidth=2)
        card.columnconfigure(0, weight=1)

        title_label = ttk.Label(card, text=mode_info["name"], font=("Segoe UI", 14, "bold"))
        title_label.grid(row=0, column=0, sticky="w")

        desc_label = ttk.Label(card, text=mode_info.get("description", ""), wraplength=420, justify="left")
        desc_label.grid(row=1, column=0, sticky="w", pady=(4, 6))

        # Durum alanı
        status_row = ttk.Frame(card)
        status_row.grid(row=2, column=0, sticky="w", pady=(0, 8))
        ttk.Label(status_row, text="Durum:").pack(side="left")
        status_label = tk.Label(status_row, text="Beklemede", width=12, relief="groove", bg=STATUS_COLORS["Beklemede"], fg="white")
        status_label.pack(side="left", padx=(6, 0))

        # Alt mod sadece Merdiven kartında
        submode_frame = None
        if mode_id == "stairs":
            submode_frame = ttk.LabelFrame(card, text="Alt Mod", padding=8)
            submode_frame.grid(row=3, column=0, sticky="ew", pady=(0, 8))
            submode_frame.columnconfigure(0, weight=1)

            ttk.Radiobutton(
                submode_frame,
                text="Tam Tur: +7 → +8 basma",
                value="full_cycle",
                variable=self.submode_stairs,
            ).grid(row=0, column=0, sticky="w", pady=2)
            ttk.Radiobutton(
                submode_frame,
                text="Sadece bankadaki itemleri +7'ye kadar bas",
                value="plus7_only",
                variable=self.submode_stairs,
            ).grid(row=1, column=0, sticky="w", pady=2)

            bank_opts = ttk.Frame(submode_frame)
            bank_opts.grid(row=2, column=0, sticky="w", pady=(6, 0))
            ttk.Label(bank_opts, text="Banka Sayfası:").grid(row=0, column=0, sticky="w", padx=(0, 4))
            bank_page = ttk.Combobox(bank_opts, textvariable=self.bank_page_var, values=["1", "2", "3", "4"], width=5, state="readonly")
            bank_page.grid(row=0, column=1, sticky="w")

            ttk.Label(bank_opts, text="Kaç Slot Alınacak:").grid(row=0, column=2, sticky="w", padx=(10, 4))
            slot_spin = ttk.Spinbox(bank_opts, from_=1, to=64, textvariable=self.bank_slot_var, width=5)
            slot_spin.grid(row=0, column=3, sticky="w")

        # Başlat/Durdur butonu
        action_button = ttk.Button(
            card,
            text="BAŞLAT",
            command=lambda mid=mode_id: self._on_toggle_mode(mid),
            style="StartStop.TButton",
        )
        action_button.grid(row=4, column=0, sticky="ew", pady=(4, 0))

        self._card_widgets[mode_id] = {
            "frame": card,
            "status_label": status_label,
            "button": action_button,
            "submode_frame": submode_frame,
        }

        return card

    # Bölüm: Event handlers
    def _on_toggle_mode(self, mode_id: str) -> None:
        current_status = self.modes[mode_id]["status"]
        if current_status == "Çalışıyor":
            self._stop_mode(mode_id)
            return

        # Başka çalışan mod varsa durdur
        if self.current_mode_id and self.current_mode_id != mode_id:
            self._stop_mode(self.current_mode_id)

        self._start_mode(mode_id)

    def _start_mode(self, mode_id: str) -> None:
        submode = self.submode_stairs.get() if mode_id == "stairs" else None
        if self.on_start_mode:
            self.on_start_mode(mode_id, submode=submode)

        # Diğer modları beklemeye çek
        for mid in self.modes.keys():
            if mid != mode_id:
                self.set_mode_status(mid, "Beklemede")

        self.set_mode_status(mode_id, "Çalışıyor")
        self.set_active_mode(mode_id)

    def _stop_mode(self, mode_id: str) -> None:
        if self.on_stop_mode:
            self.on_stop_mode(mode_id)

        self.set_mode_status(mode_id, "Beklemede")
        if self.current_mode_id == mode_id:
            self.set_active_mode(None)

    def _on_speed_profile_change(self, event: tk.Event) -> None:  # type: ignore[override]
        profile = self.speed_profile_var.get()
        if self.on_speed_profile_change:
            self.on_speed_profile_change(profile)

    def _on_profile_selected(self, profile_name: str) -> None:
        if self.on_profile_selected:
            self.on_profile_selected(profile_name)
        for name, btn in self.profile_buttons.items():
            btn.state(["!pressed"])
            if name == profile_name:
                btn.state(["pressed"])

    # Bölüm: Public metotlar (backend için)
    def gui_set_mode_status(self, mode_id: str, status: str) -> None:
        self.set_mode_status(mode_id, status)

    def gui_update_last_log(self, message: str) -> None:
        self.last_log_var.set(message)

    def gui_set_active_mode(self, mode_id_or_none: Optional[str]) -> None:
        self.set_active_mode(mode_id_or_none)

    # Bölüm: State helpers
    def set_mode_status(self, mode_id: str, status: str) -> None:
        if mode_id not in self.modes:
            return
        self.modes[mode_id]["status"] = status
        widgets = self._card_widgets.get(mode_id, {})
        status_label: tk.Label = widgets.get("status_label")  # type: ignore[assignment]
        if status_label:
            status_label.configure(text=status, bg=STATUS_COLORS.get(status, STATUS_COLORS["Beklemede"]))

        button: ttk.Button = widgets.get("button")  # type: ignore[assignment]
        if button:
            button.configure(text="DURDUR" if status == "Çalışıyor" else "BAŞLAT")

        if self.current_mode_id == mode_id or (status == "Çalışıyor"):
            self.active_status_label.configure(text=f"Durum: {status}")

    def set_active_mode(self, mode_id_or_none: Optional[str]) -> None:
        self.current_mode_id = mode_id_or_none
        if mode_id_or_none is None:
            self.active_mode_label.configure(text="Yok")
            self.active_status_label.configure(text="Durum: Beklemede")
            for mid in self.modes:
                if self.modes[mid]["status"] == "Çalışıyor":
                    self.set_mode_status(mid, "Beklemede")
            return

        mode_info = self.modes.get(mode_id_or_none)
        if not mode_info:
            return

        title = mode_info["name"]
        if mode_id_or_none == "stairs":
            submode = self.submode_stairs.get()
            title += " (Tam Tur)" if submode == "full_cycle" else " (Sadece +7)"
        self.active_mode_label.configure(text=title)
        self.active_status_label.configure(text=f"Durum: {mode_info['status']}")

        # Tek çalışan mod kuralını sağlamak için diğerlerini beklemeye çek
        for mid in self.modes:
            if mid != mode_id_or_none and self.modes[mid]["status"] == "Çalışıyor":
                self.set_mode_status(mid, "Beklemede")


if __name__ == "__main__":
    def demo_on_start(mode_id: str, submode: Optional[str] = None) -> None:
        print(f"[DEMO] {mode_id} modu başlatıldı. Alt mod: {submode}")

    def demo_on_stop(mode_id: str) -> None:
        print(f"[DEMO] {mode_id} modu durduruldu.")

    def demo_on_speed_change(profile_name: str) -> None:
        print(f"[DEMO] Hız profili seçildi: {profile_name}")

    def demo_on_profile_selected(profile_name: str) -> None:
        print(f"[DEMO] Profil seçildi: {profile_name}")

    app = ModVitriniApp(
        on_start_mode=demo_on_start,
        on_stop_mode=demo_on_stop,
        on_speed_profile_change=demo_on_speed_change,
        on_profile_selected=demo_on_profile_selected,
    )
    app.mainloop()
