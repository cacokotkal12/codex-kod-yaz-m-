# DENEME: 11.11.2025 – küçük test
TOWN_HARD_LOCK = False

# -*- coding: utf-8 -*-
"""
Knight Online otomasyon makrosu (tek dosya, DPI aware, portable Tesseract, retry/crashguard, scroll alma stage)
Önemli notlar:
- Global değişken kullanan fonksiyonlarda `global ...` bildirimi EN BAŞTA.
- Login yazmama sorunu için perform_login_inputs() eklendi ve main()/relaunch() içinde kullanılıyor.
- Server listesi ve seçim koordinatları sabitler bölümünde.
- Kod PyInstaller (tek exe) ve Windows 10 uyumlu.
"""

# ====================== İTHALATLAR ======================
TOWN_MIN_INTERVAL_SEC = 8  # town debouncer (saniye)

TOWN_LOCKED = False  # Merdiven sonrası town kilidi (başta kapalı)

# === [PATCH] TOWN/GUI tek-sefer log helper ===
_TOWN_ONCE_KEYS = set()


def _town_log_once(*args, sep=' ', end='\n'):
    # NE İŞE YARAR: Aynı mesajı sadece BİR KEZ yazar.
    msg = sep.join(str(a) for a in args)
    if msg in _TOWN_ONCE_KEYS: return
    _TOWN_ONCE_KEYS.add(msg)
    try:
        print(msg, end=end)
    except Exception:
        pass


# === [/PATCH] ===


# [PATCH_Y_LOCK_BEGIN]
def _set_town_lock_by_y(y):
    # [YAMA] HardLock varken Y-tabanlı kilidi devre dışı tut
    if globals().get('TOWN_HARD_LOCK', False):
        gy = globals();
        gy['TOWN_LOCKED'] = True
        return
    # NE İŞE YARAR: Anlık Y'ye göre kilidi ayarlar; sadece Y==STAIRS_TOP_Y ise kilit ON
    try:
        gy = globals()
        top_y = int(gy.get('STAIRS_TOP_Y', 598))
        gy['TOWN_LOCKED'] = (int(y) == top_y)
    except Exception:
        gy = globals();
        gy['TOWN_LOCKED'] = False


def _read_y_now():
    # NE İŞE YARAR: Mevcut Y'yi güvenli şekilde okur (hata olursa None)
    try:
        return read_coord_y()
    except Exception:
        try:
            w = bring_game_window_to_front();
            _x, y = read_coordinates(w);
            return y
        except Exception:
            return None


# [PATCH_Y_LOCK_END]

import time, re, os, json, subprocess, ctypes, pyautogui, pytesseract, pygetwindow as gw, keyboard, cv2, numpy as np, \
    random, \
    sys, atexit, traceback, logging, functools, copy, math, threading, webbrowser
from ctypes import wintypes
from PIL import Image, ImageGrab, ImageEnhance, ImageFilter
from contextlib import contextmanager
from logging.handlers import RotatingFileHandler
from dataclasses import dataclass
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple


# [PATCH_TOWN_LOCK_BEGIN]
def _town_lock(v: bool, reason: str = ""):
    """Town kilidini aç/kapat (kısa log)."""
    global TOWN_LOCKED
    TOWN_LOCKED = bool(v)
    try:
        _town_log_once(
            '[TOWN] Kilit ' + ('AKTİF' if TOWN_LOCKED else 'sıfırlandı') + ((' — ' + reason) if reason else ''))
    except Exception:
        pass


# [PATCH_TOWN_LOCK_END]

# === Kalıcı ayar yolu (EXE/py fark etmez) ===
def PERSIST_PATH(name):
    import os
    base = os.path.join(os.getenv('APPDATA') or os.path.expanduser('~'), 'Merdiven')
    os.makedirs(base, exist_ok=True)
    return os.path.join(base, name)


def _MERDIVEN_CFG_PATH():
    """Ayar dosyası için tekil ve yazılabilir yol döndür."""
    import os
    try:
        path = PERSIST_PATH('merdiven_config.json')
    except Exception:
        path = os.path.join(os.path.expanduser('~'), 'merdiven_config.json')
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
    except Exception:
        pass
    return path


try:
    import mss
except Exception:
    mss = None

try:
    import requests
except Exception:
    requests = None

# ====================== BOOST: GENEL AYARLAR ======================
LOG_DIR = "logs";
CRASH_DIR = "crash_dumps"


def _set_dpi_aware():
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass


def resource_path(rel_path: str) -> str:
    base = getattr(sys, "_MEIPASS", os.path.abspath("."));
    return os.path.join(base, rel_path)


def _wire_tesseract_portable():
    try:
        cand = resource_path(r"tesseract/tesseract.exe")
        if os.path.isfile(cand): pytesseract.pytesseract.tesseract_cmd = cand; print(f"[TESS] Portable: {cand}")
    except Exception as e:
        print(f"[TESS] Portable hata: {e}")


os.makedirs(LOG_DIR, exist_ok=True);
os.makedirs(CRASH_DIR, exist_ok=True)
_logger = logging.getLogger("macro");
_logger.setLevel(logging.DEBUG)
_handler = RotatingFileHandler(os.path.join(LOG_DIR, "macro.log"), maxBytes=2_000_000, backupCount=5, encoding="utf-8")
_handler.setFormatter(logging.Formatter("[%(asctime)s] %(levelname)s %(message)s"))
_logger.addHandler(_handler)


def log(msg, lvl="info"): getattr(_logger, lvl, _logger.info)(msg)


_ORIG_SLEEP = time.sleep
_KEYBOARD_IS_PRESSED_ORIG = getattr(keyboard, "is_pressed", None)


def _abort_requested() -> bool:
    if globals().get("GUI_ABORT", False):
        return True
    if _KEYBOARD_IS_PRESSED_ORIG is not None:
        try:
            if _KEYBOARD_IS_PRESSED_ORIG("f12"):
                return True
        except Exception:
            pass
    return False


def _sleep_abortable(seconds: float):
    if seconds <= 0:
        return _ORIG_SLEEP(seconds)
    end = time.time() + float(seconds)
    while True:
        if _abort_requested():
            break
        remaining = end - time.time()
        if remaining <= 0:
            break
        _ORIG_SLEEP(remaining if remaining < 0.12 else 0.12)


time.sleep = _sleep_abortable


def _grab_full_bgr():
    try:
        if mss is not None:
            with mss.mss() as sct:
                mon = sct.monitors[1];
                im = np.array(sct.grab(mon))[:, :, :3];
                return im
    except Exception:
        pass
    im = ImageGrab.grab();
    return cv2.cvtColor(np.array(im), cv2.COLOR_RGB2BGR)


class GUIAbort(RuntimeError):
    """GUI'den gelen anlık durdurma isteği."""


def _raise_gui_abort(msg: str = "GUI durdurma isteği"):
    exc = globals().get("GUIAbort", GUIAbort)
    raise exc(msg)


def dump_crash(e: Exception, stage: str = "UNKNOWN"):
    try:
        ts = time.strftime("%Y%m%d_%H%M%S")
        with open(os.path.join(CRASH_DIR, f"crash_{ts}.txt"), "w", encoding="utf-8") as f:
            f.write(f"STAGE={stage}\n{traceback.format_exc()}")
        cv2.imwrite(os.path.join(CRASH_DIR, f"crash_{ts}_a.png"), _grab_full_bgr());
        time.sleep(0.12)
        cv2.imwrite(os.path.join(CRASH_DIR, f"crash_{ts}_b.png"), _grab_full_bgr())
        log(f"[CRASH] dump: {ts}", "error")
    except Exception:
        pass


def crashguard(stage=""):
    def deco(fn):
        @functools.wraps(fn)
        def wrap(*a, **kw):
            try:
                return fn(*a, **kw)
            except GUIAbort:
                raise
            except Exception as e:
                dump_crash(e, stage or fn.__name__);
                raise

        return wrap

    return deco


def with_retry(name="", attempts=4, delay=0.6):
    def deco(fn):
        def wrap(*a, **kw):
            for i in range(1, attempts + 1):
                try:
                    r = fn(*a, **kw)
                    if r not in (None, False):
                        if i > 1: log(f"[RETRY] {name or fn.__name__} deneme={i} OK", "warning")
                        return r
                except GUIAbort:
                    raise
                except Exception as e:
                    log(f"[RETRY] {name or fn.__name__} hata={e} deneme={i}", "warning")
                time.sleep(delay)
            log(f"[RETRY] {name or fn.__name__} BAŞARISIZ", "error");
            return None

        return wrap

    return deco


@atexit.register
def _bye(): log("[EXIT] program sonlandı")


# ============================== KULLANICI AYARLARI ==============================
# ---- Hız / Tıklama / Jitter ----
tus_hizi = 0.050;
mouse_hizi = 0.1;
jitter_px = 0
# ---- OCR / Tesseract ----
pytesseract.pytesseract.tesseract_cmd = os.getenv("TESSERACT_CMD", r"C:\Program Files\Tesseract-OCR\tesseract.exe")
pyautogui.FAILSAFE = False;
pyautogui.PAUSE = 0.030
# ---- Watchdog ----
WATCHDOG_TIMEOUT = 120;
F_WAIT_TIMEOUT_SECONDS = 30.0
# ---- Banka +8 otomatik başlatma ----
AUTO_BANK_PLUS8 = True  # True: 30 sn sonra otomatik +8 döngüsüne gir
AUTO_BANK_PLUS8_DELAY = 30.0  # saniye; istersen değeri değiştir
# ---- Merdiven Başlangıç Koord. ----
VALID_X_LEFT = {811, 812, 813};
VALID_X_RIGHT = {819, 820, 821};
VALID_X = VALID_X_LEFT | VALID_X_RIGHT
STOP_Y = {598};
STAIRS_TOP_Y = 598
# ---- Envanter / Banka Grid ----
INV_LEFT, INV_TOP, INV_RIGHT, INV_BOTTOM = 664, 449, 1007, 644
UPG_INV_LEFT, UPG_INV_TOP, UPG_INV_RIGHT, UPG_INV_BOTTOM = 650, 434, 996, 632
BANK_INV_LEFT, BANK_INV_TOP, BANK_INV_RIGHT, BANK_INV_BOTTOM = 648, 423, 996, 621
SLOT_COLS, SLOT_ROWS = 7, 4
# ---- Banka Sağ Üst Panel (6x4) ----
BANK_PANEL_LEFT, BANK_PANEL_TOP, BANK_PANEL_RIGHT, BANK_PANEL_BOTTOM = 665, 156, 980, 363
BANK_PANEL_COLS, BANK_PANEL_ROWS = 6, 4
# ---- Boş Slot Tespiti ----
EMPTY_SLOT_TEMPLATE_PATH = "empty_slot.png"
EMPTY_SLOT_MATCH_THRESHOLD = 0.85;
FALLBACK_MEAN_THRESHOLD = 55.0;
FALLBACK_EDGE_DENSITY_THRESHOLD = 0.030
EMPTY_SLOT_THRESHOLD = 24;
DEBUG_SAVE = False
# ---- UPG / Basma Param. ----
BASMA_HAKKI = 31
SCROLL_POS = (671, 459);
UPGRADE_BTN_POS = (747, 358);
CONFIRM_BTN_POS = (737, 479)
UPG_STEP_DELAY = 0.05
SCROLL_FIND_ROI_W = 128;
SCROLL_FIND_ROI_H = 128
# ---- Anvil/Scroll Yeniden Açma ----
SCROLL_PANEL_REOPEN_MAX = 10;
SCROLL_PANEL_REOPEN_DELAY = 0.1
# ---- Scroll Alma Ayarları ----
SCROLL_ALIM_ADET = 3000;
SCROLL_MID_ALIM_ADET = 199;
SCROLL_VENDOR_MID_POS = (737, 233)
# ---- NPC / Storage ----
TARGET_NPC_X = 768;
TARGET_Y_AFTER_TURN = 648
NPC_CONTEXT_RIGHTCLICK_POS = (535, 520)
NPC_OPEN_TEXT_TEMPLATE_PATH = "npc_acma.png";
NPC_OPEN_MATCH_THRESHOLD = 0.68;
NPC_OPEN_FIND_TIMEOUT = 5.0
NPC_OPEN_SCALES = (0.85, 0.9, 1.0, 1.1, 1.2)
USE_STORAGE_TEMPLATE_PATHS = ["use_storage.png", "use_stroge.png"];
USE_STORAGE_MATCH_THRESHOLD = 0.78;
USE_STORAGE_FIND_TIMEOUT = 6.0
USE_STORAGE_SCALES = (0.85, 0.9, 1.0, 1.1, 1.2)
# ---- Banka Sayfa Düğmeleri ----
BANK_NEXT_PAGE_POS = (731, 389);
BANK_PREV_PAGE_POS = (668, 389);
BANK_PAGE_CLICK_DELAY = 0.12
# ---- Game Start (Launcher sonrası) ----
GAME_START_TEMPLATE_PATH = "oyun_start.png";
GAME_START_MATCH_THRESHOLD = 0.70;
GAME_START_FIND_TIMEOUT = 8.0;
GAME_START_SCALES = (0.85, 0.9, 1.0, 1.1, 1.2)
TEMPLATE_EXTRA_CLICK_POS = (931, 602)
# ---- Launcher ----
LAUNCHER_EXE = r"C:\NTTGame\KnightOnlineEn\Launcher.exe";
LAUNCHER_START_CLICK_POS = (974, 726)
WINDOW_TITLE_KEYWORD = "Knight Online";
WINDOW_APPEAR_TIMEOUT = 120.0
# ---- Login Bilgileri ve Tıklama Koord. ----
LOGIN_USERNAME = os.getenv("KO_USER", "cacokotkal12");
LOGIN_PASSWORD = os.getenv("KO_PASS", "Vaz14999999jS@1")
# Bu alanları kendi ekranına göre ayarla (gerekirse TAB ile de ilerliyor):
LOGIN_USERNAME_CLICK_POS = (579, 326)  # kullanıcı adı alanı
LOGIN_PASSWORD_CLICK_POS = (579, 378)  # şifre alanı
SERVER_OPEN_POS = (455, 231)  # server list drop-down
SERVER_CHOICES = [(671, 254), (676, 281)]  # listeden seçimlerden biri
ITEM_SERVER_PRESETS = {"Server1": 0, "Server2": 1}
ITEM_BASMA_SERVER = "Server1"
OPERATION_MODE = "ITEM_BASMA"  # ITEM_BASMA veya ITEM_SATIS
PLUS7_BANK_MODE = "PLUS7_BANK"
PAZAR_PARK_X = 805
ITEM_SALE_VALID_X = (810, 805, 800)
ITEM_SALE_FACE_A_DURATION = 1.45
ITEM_SALE_PRICE_TEXT = "PAZAR_FIYAT_METNI"
PAZAR_ESIK_1 = 10
PAZAR_ESIK_2 = 15
PAZAR_ESIK_3 = 20
PAZAR_YENILEME_BEKELEME_MIN = 120.0
PAZAR_YENILEME_BEKELEME_MAX = 120.0
PAZAR_YENILEME_BEKELEME_SURESI = PAZAR_YENILEME_BEKELEME_MAX  # geriye dönük uyum
PAZAR_ILK_BEKELEME_SURESI = 5.0
AUTO_MARKET_REFRESH_ENABLED = False
AUTO_MARKET_REFRESH_INTERVAL_HOURS = 3.0
_AUTO_MARKET_LAST_REFRESH_TS = 0.0
_AUTO_MARKET_REFRESH_LOCK = threading.Lock()
CLICK_902_135_ADET = 3
CLICK_902_135_HIZ = 0.05
CLICK_899_399_ADET = 3
CLICK_899_399_HIZ = 0.05
BANKAYA_GIT_BOS_SLOT_ESIGI = 27
ITEM_SALE_SLOT_SCAN_INTERVAL = 10.0
ITEM_SALE_EXIT_DELAY_MIN = 0.0
ITEM_SALE_EXIT_DELAY_MAX = 0.0
PAZAR_BREAK_CLICK_POS = (434, 518)
PAZAR_REOPEN_KEY = 'H'
PAZAR_REOPEN_WAIT = 62.0
PAZAR_FIRST_CLICK_POS = (902, 135)
PAZAR_SECOND_CLICK_POS = (899, 399)
PAZAR_CONFIRM_CLICK_POS = (512, 290)
PAZAR_DROP_TARGET = (383, 237)
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
PLUS8_WAIT_MESSAGE = ""
PLUS8_WAIT_MESSAGE_INTERVAL_MIN = 10.0
ITEM_SALE_BANK_NOTIFY = True
ITEM_SALE_BANK_EMPTY_MESSAGE = "Bankada item kalmadı"
ITEM_SALE_BANK_WITHDRAW_COUNT = 28
KRALLIK_URL = os.getenv("KRALLIK_URL", "https://krallik.app")
KRALLIK_CLICK_X = 0
KRALLIK_CLICK_Y = 0
KRALLIK_TIKLAMA_ARALIGI = 0.0
KRALLIK_TIKLAMA_SURESI = 0.05

_GUI_UPDATE_SALE_SLOT = None


def _choose_server_xy():
    try:
        mode = str(globals().get("OPERATION_MODE", OPERATION_MODE)).upper()
    except Exception:
        mode = str(OPERATION_MODE).upper()

    # ITEM SATIŞ modunda kullanıcı seçimini kullan (deterministik), diğer modlarda rastgele server seç.
    if mode == "ITEM_SATIS":
        try:
            sel = str(globals().get("ITEM_BASMA_SERVER", "Server1"))
        except Exception:
            sel = "Server1"
        idx = ITEM_SERVER_PRESETS.get(sel, None)
        if isinstance(idx, int) and 0 <= idx < len(SERVER_CHOICES):
            return SERVER_CHOICES[idx]
        return SERVER_CHOICES[0] if SERVER_CHOICES else (0, 0)

    # ITEM BASMA dahil diğer modlar → rastgele server seçimi
    return random.choice(SERVER_CHOICES)


# ---- HP Bar / In-Game Teyit ----
HP_POINTS = [(185, 68), (218, 74)];
HP_RED_MIN = 120.0;
HP_RED_DELTA = 35.0
# ---- HASSAS X HEDEFİ (OVERSHOOT FIX) ----
X_TOLERANCE = 1  # hedef çevresi ölü bölge (±px) → 795 için 792..798 kabul
X_BAND_CONSEC = 2  # band içinde ardışık okuma sayısı (titreşim süzgeci)
X_TOL_READ_DELAY = 0.015  # X okuma aralığı (sn)
X_TOL_TIMEOUT = 20.0  # varsayılan zaman aşımı (sn), çağrıda override edilebilir
# ---- Mikro Adım ----
# === 598→597 MİKRO AYAR SABİTLERİ (KULLANICI DÜZENLER) ===
PRESS_MIN = 0.035  # S/W mikro basış minimum (sn)
PRESS_MAX = 0.090  # S/W mikro basış maksimum (sn)
MAX_STEPS = 400  # 598→597 düzeltmede en fazla adım
STUCK_TIMEOUT = 10  # (sn) değişim olmazsa güvenlik bırakma
# --- Mikro Adım güvenlik denetimi (OTOMATİK) ---
try:
    # süreleri makul aralığa kırp
    PRESS_MIN = float(PRESS_MIN);
    PRESS_MAX = float(PRESS_MAX)
    if PRESS_MIN > PRESS_MAX: PRESS_MIN, PRESS_MAX = PRESS_MAX, PRESS_MIN
    if PRESS_MIN < 0.01: PRESS_MIN = 0.01
    if PRESS_MAX > 0.20: PRESS_MAX = 0.20
    # adım ve timeout sınırları
    MAX_STEPS = int(MAX_STEPS) if int(MAX_STEPS) > 0 else 400
    if MAX_STEPS > 2000: MAX_STEPS = 2000
    STUCK_TIMEOUT = int(STUCK_TIMEOUT) if int(STUCK_TIMEOUT) >= 3 else 10
    if STUCK_TIMEOUT > 60: STUCK_TIMEOUT = 60
except Exception as _e:
    print('[MikroAdim] sabit denetimi uyarı:', _e)

PRE_BRAKE_DELTA = 2;
MICRO_PULSE_DURATION = 0.100;
MICRO_READ_DELAY = 0.010;
TARGET_STABLE_HITS = 10
MICRO_ADJUST_MAX_DURATION = 60.0  # mikro düzeltme döngüsü üst sınırı (sn)
# ---- Yürüme / Dönüş ----
ANVIL_WALK_TIME = 2.5;
NPC_GIDIS_SURESI = 5.0;
NPC_SEEK_TIMEOUT = 20.0;
Y_SEEK_TIMEOUT = 20.0
TURN_LEFT_SEC = 1.432;
TURN_RIGHT_SEC = 1.432
# ---- Town ----
TOWN_CLICK_POS = (775, 775);
TOWN_WAIT = 2.5
# ---- Splash/Login yardımcı tık ----
SPLASH_CLICK_POS = (700, 550)
# ---- Tooltip OCR

HOVER_WAIT_INV = 0.080;
HOVER_WAIT_BANK = 0.20;
TOOLTIP_ROI_W, TOOLTIP_ROI_H = 640, 480;
TOOLTIP_OFFSET_Y = 40;
TOOLTIP_FALLBACK_BBOX = (290, 95, 1007, 662)
# ---- +N (7/8) Şablon Yolları ----
PLUS7_TEMPLATE_PATHS = ["plus7.png", "plus7_var2.png"];
PLUS8_TEMPLATE_PATHS = ["plus8.png"]
# ---- Scroll Takası Şablon & Ayarlcacokotkal12 ar ----
SCROLL_LOW_TEMPLATE_PATHS = ["scroll_low.png", "scroll_low2.png"]
SCROLL_MID_TEMPLATE_PATHS = ["scroll_mid.png", "scroll_mid2.png"]
SCROLL_MATCH_THRESHOLD = 0.70;
SCROLL_SCALES = (0.80, 0.90, 1.00, 1.10, 1.20);
SCROLL_SWAP_MAX_STACKS = 8
# ---- Scroll arama (sabit nokta yerine tüm UPG/INV içinde) ----
SCROLL_SEARCH_ANYWHERE = True  # True: scroll'u UPG/INV içinde her yerde ara
SCROLL_SEARCH_REGIONS = ("UPG", "INV")  # istersen ("UPG", "INV") yapabilirsin
# ================== AYAR (en üste, diğer sabitlerin yanına) ==================
ON_TEMPLATE_TIMEOUT_RESTART = True  # True: npc_acma.png vb. zaman aşımında town yerine oyunu kapatıp yeniden başlat


def find_scroll_pos_anywhere(required: str, regions=SCROLL_SEARCH_REGIONS):
    """
    LOW/MID scroll'u verilen bölgelerde (grid tabanlı) ara ve merkez koordinatını döndür.
    Eşleşme bulunamazsa None.
    """
    if required not in ("LOW", "MID"):
        return None
    tmpl_list = SCROLL_LOW_TEMPLATES if required == "LOW" else SCROLL_MID_TEMPLATES
    if not tmpl_list:
        return None

    for region in regions:
        gray = grab_gray_region(region)
        cols, rows = get_region_grid(region)
        tmpl_empty = _load_empty_template()

        for r in range(rows):
            for c in range(cols):
                # boş slotları atla
                if slot_is_empty_in_gray(gray, c, r, region, tmpl_empty):
                    continue
                roi = _cell_roi(gray, region, c, r)
                if _roi_matches_any_template(roi, tmpl_list):
                    return slot_center(region, c, r)

    return None


def click_scroll_anywhere(required: str, regions=SCROLL_SEARCH_REGIONS) -> bool:
    """
    Scroll'u bulursa sağ tıklar. True/False döner.
    """
    pos = find_scroll_pos_anywhere(required, regions=regions)
    if pos is None:
        return False
    mouse_move(*pos)
    mouse_click("right")
    return True


# ---- NPC'den alış şablonu ----
NPC_BUY_STEPS = [((687, 237), 2, "right"), ((737, 237), 2, "right"), ((787, 237), 3, "right"), ((837, 237), 3, "right"),
                 ((887, 237), 4, "right"), ((912, 498), 1, "left"), ((729, 584), 1, "left")]
NPC_BUY_TURN_COUNT = 2;
NPC_MENU_PAGE2_POS = (968, 328)
# ---- NPC sonrası Anvil rotası ----
NPC_POSTBUY_FIRST_A_DURATION = 3.1;
NPC_POSTBUY_TARGET_X1 = 795;
NPC_POSTBUY_A_WHILE_W_DURATION = 0.08;
NPC_POSTBUY_TARGET_X2 = 815
NPC_POSTBUY_SECOND_A_DURATION = 1.4;
NPC_POSTBUY_FINAL_W_DURATION = 4.0;
NPC_POSTBUY_SEEK_TIMEOUT = 20.0
# ---- +7 taraması tur planı ----
PLUS7_START_FROM_TURN_AFTER_PURCHASE = 4;
GLOBAL_CYCLE = 1;
NEXT_PLUS7_CHECK_AT = 1
# ---- NPC Onay (shop kimliği) ----
NPC_CONFIRM_TEMPLATE_PATH = "npc_onay.png";
NPC_CONFIRM_RECT = (713, 51, 911, 84);
NPC_CONFIRM_MATCH_THRESHOLD = 0.75;
NPC_CONFIRM_SCALES = (0.60, 0.75, 0.90, 1.00, 1.10)

# ================== OTOMATİK HIZ PROFİLİ (Yeni) ==================
AUTO_SPEED_PROFILE = True;
AUTO_TUNE_INTERVAL = 120;
SPEED_PROFILE = "FAST"
_DEFAULTS_PROFILE = dict(tus_hizi=tus_hizi, mouse_hizi=mouse_hizi, UPG_STEP_DELAY=UPG_STEP_DELAY,
                         HOVER_WAIT_INV=HOVER_WAIT_INV, HOVER_WAIT_BANK=HOVER_WAIT_BANK,
                         BANK_PAGE_CLICK_DELAY=BANK_PAGE_CLICK_DELAY, MICRO_PULSE_DURATION=MICRO_PULSE_DURATION)
_PROFILES = {
    "FAST": dict(tus_hizi=0.025, mouse_hizi=0.050, UPG_STEP_DELAY=0.030, HOVER_WAIT_INV=0.050, HOVER_WAIT_BANK=0.10,
                 BANK_PAGE_CLICK_DELAY=0.100, MICRO_PULSE_DURATION=0.100),
    "BALANCED": _DEFAULTS_PROFILE.copy(),
    "SAFE": dict(tus_hizi=0.070, mouse_hizi=0.130, UPG_STEP_DELAY=0.060, HOVER_WAIT_INV=0.100, HOVER_WAIT_BANK=0.240,
                 BANK_PAGE_CLICK_DELAY=0.140, MICRO_PULSE_DURATION=0.100)}
_last_probe_ts = 0.0;
_last_applied = None


def _probe_runtime_cost(trials=4):
    times = [];
    bx1, by1, bx2, by2 = 720, 420, 780, 480
    for _ in range(trials):
        t0 = time.perf_counter();
        img = ImageGrab.grab(bbox=(bx1, by1, bx2, by2));
        arr = np.array(img);
        gray = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY);
        _ = cv2.Canny(gray, 60, 140);
        dt = (time.perf_counter() - t0) * 1000.0;
        times.append(dt);
        time.sleep(0.015)
    mu = float(np.mean(times));
    sd = float(np.std(times));
    return mu, sd


def _apply_profile(name: str):
    global tus_hizi, mouse_hizi, UPG_STEP_DELAY, HOVER_WAIT_INV, HOVER_WAIT_BANK, BANK_PAGE_CLICK_DELAY, MICRO_PULSE_DURATION, SPEED_PROFILE, _last_applied
    prof = _PROFILES.get(name) or _PROFILES["BALANCED"]
    tus_hizi = prof["tus_hizi"];
    mouse_hizi = prof["mouse_hizi"];
    UPG_STEP_DELAY = prof["UPG_STEP_DELAY"]
    HOVER_WAIT_INV = prof["HOVER_WAIT_INV"];
    HOVER_WAIT_BANK = prof["HOVER_WAIT_BANK"];
    BANK_PAGE_CLICK_DELAY = prof["BANK_PAGE_CLICK_DELAY"];
    MICRO_PULSE_DURATION = prof["MICRO_PULSE_DURATION"]
    SPEED_PROFILE = name;
    _last_applied = name;
    print(f"[AUTO-SPEED] {name} uygulandı | tus={tus_hizi:.3f} mouse={mouse_hizi:.3f}")


def _decide_profile(mean_ms: float, std_ms: float) -> str:
    base = "FAST" if mean_ms <= 12.0 else ("BALANCED" if mean_ms <= 22.0 else "SAFE")
    if std_ms >= 8.0:
        order = ["FAST", "BALANCED", "SAFE"];
        return order[min(order.index(base) + 1, len(order) - 1)]
    return base


def maybe_autotune(force=False):
    global _last_probe_ts
    if not AUTO_SPEED_PROFILE: return
    now = time.time()
    if not force and (now - _last_probe_ts) < AUTO_TUNE_INTERVAL: return
    _last_probe_ts = now
    try:
        mu, sd = _probe_runtime_cost(trials=5);
        newp = _decide_profile(mu, sd)
        if newp != SPEED_PROFILE:
            print(f"[AUTO-SPEED] avg={mu:.1f}ms, std={sd:.1f}ms → {SPEED_PROFILE}→{newp}");
            _apply_profile(newp)
        else:
            print(f"[AUTO-SPEED] avg={mu:.1f}ms, std={sd:.1f}ms → profil korunuyor")
    except Exception as e:
        print(f"[AUTO-SPEED] Ölçüm hatası: {e}")


# ================== MOD & DURUM ==================

AUTO_UNPAUSE_ON_CRITICAL = True
MODE = "NORMAL";
PLUS8_RESUME = False  # Relaunch sonrası +8 modunu hatırlamak için bayrak
BANK_FULL_FLAG = False;
ITEMS_DEPLETED_FLAG = False;
REQUEST_RELAUNCH = False;
BANK_OPEN = False;
FORCE_PLUS7_ONCE = False
NEED_STAIRS_REALIGN = True  # relaunch/yeniden giriş sonrası merdiven başlangıcı zorunlu


def _set_mode_normal(reason: str = None, *, reset_plus8_state: bool = True):
    """MODE'u NORMAL yapar; istenirse +8 devam bayrağını da temizler."""
    global MODE, PLUS8_RESUME
    MODE = "NORMAL"
    if reset_plus8_state:
        PLUS8_RESUME = False
    if reason:
        print(f"[MODE] NORMAL ({reason})")


def _set_mode_bank_plus8(reason: str = None):
    """MODE'u BANK_PLUS8 yapar ve yeniden girişlerde devam için bayrağı ayarlar."""
    global MODE, PLUS8_RESUME
    _stop_plus8_wait_notifier()
    MODE = "BANK_PLUS8"
    PLUS8_RESUME = True
    if reason:
        print(f"[MODE] BANK_PLUS8 ({reason})")


def _set_mode_bank_plus7(reason: str = None):
    """MODE'u BANK_PLUS7 yapar; çıkışta _set_mode_normal kullan."""
    global MODE
    MODE = "BANK_PLUS7"
    if reason:
        print(f"[MODE] BANK_PLUS7 ({reason})")


# ---- +8 bekleme Telegram bildirimi ----
_PLUS8_WAIT_STOP = threading.Event()
_PLUS8_WAIT_THREAD = None


def _plus8_wait_feature_enabled() -> bool:
    try:
        interval = float(globals().get("PLUS8_WAIT_MESSAGE_INTERVAL_MIN", 0))
    except Exception:
        interval = 0
    msg = str(globals().get("PLUS8_WAIT_MESSAGE", "") or "").strip()
    return bool(msg) and interval > 0


def _is_in_plus8_wait_state() -> bool:
    if not _plus8_wait_feature_enabled():
        return False
    if _abort_requested():
        return False
    try:
        if str(globals().get("OPERATION_MODE", OPERATION_MODE)).upper() != "ITEM_BASMA":
            return False
    except Exception:
        return False
    if not globals().get("BANK_FULL_FLAG", BANK_FULL_FLAG):
        return False
    if globals().get("MODE", MODE) == "BANK_PLUS8":
        return False
    if globals().get("MODE", MODE) != "NORMAL":
        return False
    if globals().get("PLUS8_RESUME", PLUS8_RESUME):
        return False
    if _kb_pressed('f'):
        return False
    return True


def _plus8_wait_notifier_loop():
    while not _PLUS8_WAIT_STOP.is_set():
        try:
            interval_min = float(globals().get("PLUS8_WAIT_MESSAGE_INTERVAL_MIN", 0))
        except Exception:
            interval_min = 0
        if interval_min <= 0 or not _is_in_plus8_wait_state():
            _PLUS8_WAIT_STOP.wait(1.0)
            continue
        if _PLUS8_WAIT_STOP.wait(interval_min * 60):
            break
        if not _is_in_plus8_wait_state():
            continue
        msg = str(globals().get("PLUS8_WAIT_MESSAGE", "") or "").strip()
        if not msg:
            continue
        for _ in range(3):
            if _PLUS8_WAIT_STOP.is_set() or not _is_in_plus8_wait_state():
                break
            send_telegram_message(msg)
            time.sleep(0.4)


def _start_plus8_wait_notifier():
    global _PLUS8_WAIT_THREAD
    if _PLUS8_WAIT_THREAD and _PLUS8_WAIT_THREAD.is_alive():
        return
    if not _plus8_wait_feature_enabled():
        return
    _PLUS8_WAIT_STOP.clear()
    t = threading.Thread(target=_plus8_wait_notifier_loop, daemon=True)
    _PLUS8_WAIT_THREAD = t
    t.start()


def _stop_plus8_wait_notifier():
    global _PLUS8_WAIT_THREAD
    _PLUS8_WAIT_STOP.set()
    thr = _PLUS8_WAIT_THREAD
    if thr and thr.is_alive():
        thr.join(timeout=0.2)
    _PLUS8_WAIT_THREAD = None


def _wait_for_f_with_countdown(deadline_ts: float, *, label: str = "+8 F bekleme") -> str:
    """F tuşu bekleme döngüsü; watchdog'u devre dışı bırakır ve geri sayım loglar."""
    countdown_step = 60  # sn
    last_log = None
    watchdog_suspend(label)
    try:
        while time.time() < deadline_ts:
            wait_if_paused()
            remaining = max(0.0, float(deadline_ts - time.time()))
            rounded = int(math.ceil(remaining / countdown_step) * countdown_step) if countdown_step > 0 else int(
                math.ceil(remaining))
            if rounded != last_log:
                stage_detail(f"[PLUS8_WAIT] F için bekleme: {rounded} sn kaldı")
                last_log = rounded
            if _kb_pressed('f'):
                return "F"
            if _kb_pressed('f12'):
                return "ABORT"
            time.sleep(0.1)
        return "TIMEOUT"
    finally:
        watchdog_resume()

# ---- LOW scroll genel reopen limiti (anvil) ----
SCROLL_GLOBAL_REOPEN_LIMIT_LOW = 5
_scroll_reopen_low_remaining = None


def _reset_scroll_reopen_budget(scroll_type: str):
    global _scroll_reopen_low_remaining
    if scroll_type == "LOW":
        _scroll_reopen_low_remaining = SCROLL_GLOBAL_REOPEN_LIMIT_LOW
    else:
        _scroll_reopen_low_remaining = None


def _consume_scroll_reopen_low():
    """LOW için global reopen bütçesinden 1 düş; (devam_edebilir_mi, kullanilan, limit) döndür."""
    global _scroll_reopen_low_remaining
    if _scroll_reopen_low_remaining is None:
        _reset_scroll_reopen_budget("LOW")
    if _scroll_reopen_low_remaining > 0:
        _scroll_reopen_low_remaining -= 1
        used = SCROLL_GLOBAL_REOPEN_LIMIT_LOW - _scroll_reopen_low_remaining
        return True, used, SCROLL_GLOBAL_REOPEN_LIMIT_LOW
    # bütçe bitti
    return False, SCROLL_GLOBAL_REOPEN_LIMIT_LOW, SCROLL_GLOBAL_REOPEN_LIMIT_LOW


# ================== İç Durum (Watchdog) ==================
class WatchdogTimeout(Exception): pass


_current_stage = "INIT";
_stage_enter_ts = time.time()
_GUI_STAGE_DETAIL = None
_WATCHDOG_SUSPENDED = False
_WATCHDOG_SUSPEND_REASON = None


def set_stage(name: str):
    global _current_stage, _stage_enter_ts
    _current_stage = name;
    _stage_enter_ts = time.time();
    print(f"[STAGE] {_current_stage}");
    maybe_autotune(False)


def stage_detail(info: str):
    text = str(info or "").strip()
    if not text:
        return
    if _current_stage:
        text = f"{_current_stage} — {text}"
    print(f"[STAGE-INFO] {text}")
    cb = globals().get("_GUI_STAGE_DETAIL")
    if callable(cb):
        try:
            cb(text)
        except Exception:
            pass


def watchdog_suspend(reason: str = None):
    """Watchdog'u geçici olarak devre dışı bırak."""
    global _WATCHDOG_SUSPENDED, _WATCHDOG_SUSPEND_REASON
    _WATCHDOG_SUSPENDED = True
    _WATCHDOG_SUSPEND_REASON = reason
    if reason:
        print(f"[WATCHDOG] Devre dışı (neden: {reason})")
    else:
        print("[WATCHDOG] Devre dışı")


def watchdog_resume():
    """Watchdog'u yeniden devreye al."""
    global _WATCHDOG_SUSPENDED, _WATCHDOG_SUSPEND_REASON, _stage_enter_ts
    if _WATCHDOG_SUSPENDED:
        _WATCHDOG_SUSPENDED = False
        _WATCHDOG_SUSPEND_REASON = None
        _stage_enter_ts = time.time()
        print("[WATCHDOG] Tekrar aktif")


def _resolve_range_values(min_val, max_val):
    try:
        lo = float(min_val)
    except Exception:
        lo = 0.0
    try:
        hi = float(max_val)
    except Exception:
        hi = lo
    if lo > hi:
        lo, hi = hi, lo
    lo = max(0.0, lo)
    hi = max(0.0, hi)
    return lo, hi


def _random_between(min_val, max_val) -> float:
    lo, hi = _resolve_range_values(min_val, max_val)
    if hi <= 0:
        return 0.0
    if abs(hi - lo) < 1e-6:
        return lo
    return random.uniform(lo, hi)


def _wait_with_stage_detail(total_seconds: float, detail_builder: Optional[Callable[[int], str]] = None):
    try:
        total = max(0.0, float(total_seconds or 0.0))
    except Exception:
        total = 0.0
    if total <= 0:
        return
    end = time.time() + total
    last_msg = None
    while True:
        wait_if_paused()
        if _abort_requested():
            _raise_gui_abort()
        remaining = end - time.time()
        if remaining <= 0:
            break
        rounded = max(0, int(math.ceil(remaining)))
        if detail_builder:
            try:
                msg = detail_builder(rounded)
            except Exception:
                msg = None
            if msg and msg != last_msg:
                stage_detail(msg)
                last_msg = msg
        time.sleep(min(1.0, remaining, 0.5))


def watchdog_enforce():
    global _stage_enter_ts
    if globals().get("_WATCHDOG_SUSPENDED", False):
        return
    if _abort_requested():
        raise GUIAbort("GUI durdurma isteği")
    if bool(ctypes.windll.user32.GetKeyState(0x14) & 1): _stage_enter_ts = time.time(); return
    if (time.time() - _stage_enter_ts) > WATCHDOG_TIMEOUT: raise WatchdogTimeout(
        f"Aşama '{_current_stage}' {WATCHDOG_TIMEOUT:.0f}s ilerlemiyor.")
    maybe_autotune(False)


# ================== DirectInput Key Codes ==================
SendInput = ctypes.windll.user32.SendInput;
PUL = ctypes.POINTER(ctypes.c_ulong)
SC_W = 0x11;
SC_A = 0x1E;
SC_S = 0x1F;
SC_D = 0x20;
SC_I = 0x17;
SC_C = 0x2E;
SC_H = 0x23;
SC_ENTER = 0x1C;
SC_B = 0x30;
SC_TAB = 0x0F;
SC_ESC = 0x01;
SC_O = 0x18
VK_CONTROL = 0x11;
VK_V = 0x56;
VK_BACKSPACE = 0x08;
VK_CAPITAL = 0x14


class KeyBdInput(ctypes.Structure): _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD),
                                                ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD),
                                                ("dwExtraInfo", PUL)]


class MouseInput(ctypes.Structure): _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG),
                                                ("mouseData", wintypes.DWORD), ("dwFlags", wintypes.DWORD),
                                                ("time", wintypes.DWORD), ("dwExtraInfo", PUL)]


class Input_I(ctypes.Union): _fields_ = [("ki", KeyBdInput), ("mi", MouseInput)]


class Input(ctypes.Structure): _fields_ = [("type", wintypes.DWORD), ("ii", Input_I)]


KEYEVENTF_SCANCODE = 0x0008;
KEYEVENTF_KEYUP = 0x0002
MOUSEEVENTF_LEFTDOWN = 0x0002;
MOUSEEVENTF_LEFTUP = 0x0004;
MOUSEEVENTF_RIGHTDOWN = 0x0008;
MOUSEEVENTF_RIGHTUP = 0x0010


# ================== Tuş / Fare / Pause ==================
def _kb_pressed(key_name: str) -> bool:
    try:
        return keyboard.is_pressed(key_name)
    except Exception:
        return False


def is_capslock_on(): return bool(ctypes.windll.user32.GetKeyState(VK_CAPITAL) & 1)


def wait_if_paused():
    told = False
    while is_capslock_on():
        if _abort_requested():
            _raise_gui_abort()
        if not told: print("[PAUSE] CapsLock AÇIK. Devam için kapat."); told = True
        _ORIG_SLEEP(0.1);
        watchdog_enforce()
    if _abort_requested():
        _raise_gui_abort()
    return True


def pause_point():
    wait_if_paused()
    if _abort_requested():
        _raise_gui_abort()
    return True


def press_key(sc):
    if not pause_point(): return
    extra = ctypes.c_ulong(0);
    ii_ = Input_I();
    ii_.ki = KeyBdInput(0, sc, KEYEVENTF_SCANCODE, 0, ctypes.pointer(extra))
    SendInput(1, ctypes.pointer(Input(ctypes.c_ulong(1), ii_)), ctypes.sizeof(Input));
    time.sleep(tus_hizi)


def release_key(sc):
    if not pause_point(): return
    extra = ctypes.c_ulong(0);
    ii_ = Input_I();
    ii_.ki = KeyBdInput(0, sc, KEYEVENTF_SCANCODE | KEYEVENTF_KEYUP, 0, ctypes.pointer(extra))
    SendInput(1, ctypes.pointer(Input(ctypes.c_ulong(1), ii_)), ctypes.sizeof(Input));
    time.sleep(tus_hizi)


def _rand(n): return 0 if n == 0 else np.random.randint(-n, n + 1)


def mouse_move(x, y):
    if not pause_point(): return
    ctypes.windll.user32.SetCursorPos(int(x) + _rand(jitter_px), int(y) + _rand(jitter_px));
    time.sleep(mouse_hizi)


def mouse_click(button="left"):
    if not pause_point(): return
    flags_down, flags_up = (MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP) if button == "left" else (
        MOUSEEVENTF_RIGHTDOWN, MOUSEEVENTF_RIGHTUP)
    extra = ctypes.c_ulong(0);
    ii_ = Input_I();
    ii_.mi = MouseInput(0, 0, 0, flags_down, 0, ctypes.pointer(extra))
    SendInput(1, ctypes.pointer(Input(ctypes.c_ulong(0), ii_)), ctypes.sizeof(Input));
    time.sleep(mouse_hizi / 2)
    if not pause_point(): return
    ii_.mi = MouseInput(0, 0, 0, flags_up, 0, ctypes.pointer(extra))
    SendInput(1, ctypes.pointer(Input(ctypes.c_ulong(0), ii_)), ctypes.sizeof(Input));
    time.sleep(mouse_hizi / 2)


def mouse_drag(src_x, src_y, dst_x, dst_y, hold=0.1):
    if not pause_point(): return
    ctypes.windll.user32.SetCursorPos(int(src_x) + _rand(jitter_px), int(src_y) + _rand(jitter_px))
    time.sleep(mouse_hizi)
    ctypes.windll.user32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
    time.sleep(max(0.02, float(hold)))
    ctypes.windll.user32.SetCursorPos(int(dst_x) + _rand(jitter_px), int(dst_y) + _rand(jitter_px))
    time.sleep(mouse_hizi)
    ctypes.windll.user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
    time.sleep(mouse_hizi)


def repeated_click(pos, count, delay):
    x, y = pos
    for _ in range(max(0, int(count))):
        mouse_move(x, y)
        mouse_click("left")
        time.sleep(max(0.0, float(delay)))


def right_click_enter_at(x, y):
    mouse_move(x, y);
    mouse_click("right");
    time.sleep(0.06);
    press_key(SC_ENTER);
    release_key(SC_ENTER);
    time.sleep(0.08)


# ---------- Kopyala-Yapıştır ----------
CF_UNICODETEXT = 13;
GMEM_MOVEABLE = 0x0002


def set_clipboard_text(text: str) -> bool:
    if not pause_point(): return False
    user32 = ctypes.windll.user32;
    kernel32 = ctypes.windll.kernel32
    for _ in range(5):
        if user32.OpenClipboard(0): break
        time.sleep(0.02)
    else:
        return False
    try:
        user32.EmptyClipboard();
        data = ctypes.create_unicode_buffer(text)
        size_bytes = ctypes.sizeof(ctypes.c_wchar) * (len(text) + 1)
        hGlobal = kernel32.GlobalAlloc(GMEM_MOVEABLE, size_bytes)
        if not hGlobal: return False
        lpGlobal = kernel32.GlobalLock(hGlobal)
        if not lpGlobal: kernel32.GlobalFree(hGlobal); return False
        ctypes.memmove(lpGlobal, ctypes.addressof(data), size_bytes);
        kernel32.GlobalUnlock(hGlobal)
        if not user32.SetClipboardData(CF_UNICODETEXT, hGlobal): kernel32.GlobalFree(hGlobal); return False
        return True
    finally:
        user32.CloseClipboard()


def press_vk(vk):
    if not pause_point(): return
    ctypes.windll.user32.keybd_event(vk, 0, 0, 0);
    time.sleep(tus_hizi)


def release_vk(vk):
    if not pause_point(): return
    ctypes.windll.user32.keybd_event(vk, 0, 2, 0);
    time.sleep(tus_hizi)


def paste_text_from_clipboard(text: str) -> bool:
    if not pause_point(): return False
    if set_clipboard_text(text):
        press_vk(VK_CONTROL);
        press_vk(VK_V);
        release_vk(VK_V);
        release_vk(VK_CONTROL);
        time.sleep(0.05);
        return True
    return False


def send_telegram_message(text: str) -> bool:
    token = str(globals().get("TELEGRAM_TOKEN", "") or "").strip()
    chat_id = str(globals().get("TELEGRAM_CHAT_ID", "") or "").strip()
    message = str(text or "").strip()
    if not token or not chat_id:
        print("[TELEGRAM] Token veya chat_id eksik (ayarları kontrol edin).")
        return False
    if not message:
        return False
    if requests is None:
        print("[TELEGRAM] requests modülü bulunamadı.")
        return False
    try:
        resp = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data={"chat_id": chat_id, "text": message},
            timeout=5,
        )
        if resp.ok:
            return True
        print(f"[TELEGRAM] HTTP {resp.status_code}: {resp.text}")
    except Exception as exc:
        print(f"[TELEGRAM] Hata: {exc}")
    return False


# ---- Merdiven tepe geri adım ayarı ----
STAIRS_TOP_S_BACKOFF_PULSES = 2  # kaç mikro S vuruşu
STAIRS_TOP_S_BACKOFF_DURATION = 0.045  # her vuruş süresi (sn)


def micro_tap(sc, dur: float):
    """Belirtilen tuşa çok kısa basıp bırak (mikro vuruş)."""
    with key_tempo(0.0):
        press_key(sc)
        time.sleep(max(0.002, float(dur)))
        release_key(sc)


# ---------- Tuş hızını geçici değiştirme ----------
@contextmanager
def key_tempo(seconds: float):
    global tus_hizi
    old = tus_hizi;
    tus_hizi = seconds
    try:
        yield
    finally:
        tus_hizi = old


# ==== HOTFIX: LAUNCHER KAPATMA ARAÇLARI (WM_CLOSE + TerminateProcess) ====
LAUNCHER_IMAGE_NAMES = {"launcher.exe", "kolauncher.exe", "nttlauncher.exe"}
LAUNCHER_KNOWN_TITLES = (
    "Knight Online Launcher",
    "Launcher",  # Görev Yöneticisi'nde "Launcher (32 bit)" olarak görünür
)

# -- Win32: process enumeration (Toolhelp32)
TH32CS_SNAPPROCESS = 0x00000002


class PROCESSENTRY32W(ctypes.Structure):
    _fields_ = [
        ("dwSize", wintypes.DWORD),
        ("cntUsage", wintypes.DWORD),
        ("th32ProcessID", wintypes.DWORD),
        ("th32DefaultHeapID", ctypes.c_void_p),
        ("th32ModuleID", wintypes.DWORD),
        ("cntThreads", wintypes.DWORD),
        ("th32ParentProcessID", wintypes.DWORD),
        ("pcPriClassBase", wintypes.LONG),
        ("dwFlags", wintypes.DWORD),
        ("szExeFile", wintypes.WCHAR * 260),
    ]


def _iter_processes():
    k32 = ctypes.windll.kernel32
    snapshot = k32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    INVALID = ctypes.c_void_p(-1).value
    if snapshot == INVALID:
        return
    try:
        e = PROCESSENTRY32W()
        e.dwSize = ctypes.sizeof(PROCESSENTRY32W)
        if not k32.Process32FirstW(snapshot, ctypes.byref(e)):
            return
        while True:
            yield int(e.th32ProcessID), (e.szExeFile or "")
            if not k32.Process32NextW(snapshot, ctypes.byref(e)):
                break
    finally:
        ctypes.windll.kernel32.CloseHandle(snapshot)


def _pids_by_image(names: set[str]) -> set[int]:
    want = {n.lower() for n in names}
    pids = set()
    try:
        for pid, exe in _iter_processes() or []:
            if (exe or "").lower() in want:
                pids.add(int(pid))
    except Exception:
        pass
    return pids


def _pids_from_hwnds(hwnds: list[int]) -> set[int]:
    pids = set()
    for h in hwnds:
        try:
            pid = wintypes.DWORD(0)
            ctypes.windll.user32.GetWindowThreadProcessId(int(h), ctypes.byref(pid))
            if pid.value:
                pids.add(int(pid.value))
        except Exception:
            pass
    return pids


def _enum_launcher_hwnds() -> list[int]:
    hwnds = []
    try:
        titles = []
        for t in LAUNCHER_KNOWN_TITLES:
            titles += gw.getWindowsWithTitle(t)
        # pygetwindow Window objelerini hwnd'e indir
        for w in titles:
            try:
                hwnds.append(int(w._hWnd))
            except Exception:
                pass
    except Exception:
        pass
    return hwnds


def _wm_close_hwnds(hwnds: list[int]):
    WM_CLOSE = 0x0010
    user32 = ctypes.windll.user32
    for h in hwnds:
        try:
            user32.PostMessageW(int(h), WM_CLOSE, 0, 0)
        except Exception:
            pass


def _kill_pids(pids: set[int]):
    k32 = ctypes.windll.kernel32
    PROCESS_TERMINATE = 0x0001
    for pid in list(pids):
        try:
            h = k32.OpenProcess(PROCESS_TERMINATE, False, int(pid))
            if h:
                try:
                    k32.TerminateProcess(h, 0)
                    k32.WaitForSingleObject(h, 1500)
                finally:
                    k32.CloseHandle(h)
        except Exception:
            pass


def _launcher_alive() -> bool:
    # pencere veya imaj adıyla çalışan var mı?
    if _enum_launcher_hwnds():
        return True
    if _pids_by_image(LAUNCHER_IMAGE_NAMES):
        return True
    return False


def _ensure_launcher_closed_strict(max_wait: float = 8.0):
    """Launcher'ı (pencere + süreç) kesin kapat. Yönetici gerekebilir."""
    start = time.time()
    step = 0
    while True:
        step += 1
        # 1) pencere bul → WM_CLOSE dene
        hwnds = _enum_launcher_hwnds()
        if hwnds:
            print(f"[KILL] Launcher pencere sayısı={len(hwnds)} → WM_CLOSE")
            _wm_close_hwnds(hwnds)
            time.sleep(0.6)

        # 2) isimden PID bul → TerminateProcess
        pids = _pids_by_image(LAUNCHER_IMAGE_NAMES) | _pids_from_hwnds(hwnds)
        if pids:
            print(f"[KILL] Launcher PID'ler: {sorted(pids)} → TerminateProcess")
            _kill_pids(pids)

        # 3) kontrol
        if not _launcher_alive():
            print("[KILL] Launcher tamamen kapandı.")
            return True

        if (time.time() - start) >= max_wait:
            print("[KILL] Uyarı: Launcher kapanmadı (muhtemelen yetki). Devam ediliyor.")
            return False

        time.sleep(0.6)


# ================== Pencere yardımları ==================
def bring_game_window_to_front():
    wins = gw.getWindowsWithTitle(WINDOW_TITLE_KEYWORD)
    if not wins: return None
    w = wins[0]
    if w.isMinimized: w.restore()
    w.activate();
    time.sleep(0.5);
    ctypes.windll.user32.SetForegroundWindow(w._hWnd);
    time.sleep(0.2);
    return w


def _is_window_valid(win) -> bool:
    try:
        _ = win.left;
        return True
    except Exception:
        return False


def bring_launcher_window_to_front():
    wins = gw.getWindowsWithTitle("Launcher") or gw.getWindowsWithTitle("Knight Online Launcher")
    if not wins: return None
    w = wins[0]
    if w.isMinimized: w.restore()
    w.activate();
    time.sleep(0.3);
    ctypes.windll.user32.SetForegroundWindow(w._hWnd);
    return w


# =============== OYUNU KAPAT (PID ile) ===============
def exit_game_fast(win=None):
    global BANK_OPEN
    killed = False;
    pid_val = None
    try:
        if win is not None and hasattr(win, "_hWnd"):
            hwnd = int(win._hWnd);
            pid = wintypes.DWORD(0);
            ctypes.windll.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid));
            pid_val = pid.value
            if pid_val:
                PROCESS_TERMINATE = 0x0001;
                hProc = ctypes.windll.kernel32.OpenProcess(PROCESS_TERMINATE, False, pid_val)
                if hProc:
                    if ctypes.windll.kernel32.TerminateProcess(hProc, 0): ctypes.windll.kernel32.WaitForSingleObject(
                        hProc, 2000); killed = True; print(f"[ÇIKIŞ] TerminateProcess PID={pid_val}")
                    ctypes.windll.kernel32.CloseHandle(hProc)
    except Exception as e:
        print(f"[ÇIKIŞ] PID kapatma hata: {e}")
    if not killed and pid_val:
        os.system(f'taskkill /F /T /PID {pid_val} >NUL 2>&1');
        time.sleep(0.2);
        print(f"[ÇIKIŞ] taskkill /PID PID={pid_val}");
        killed = True
    if not killed:
        for name in ["KnightOnLine.exe", "KnightOnline.exe", "KO.exe", "KOLauncher.exe", "Launcher.exe"]:
            os.system(f'taskkill /F /T /IM "{name}" >NUL 2>&1')
        print("[ÇIKIŞ] İsim bazlı taskkill.")
    t0 = time.time()
    while time.time() - t0 < 5.0:
        if not gw.getWindowsWithTitle(WINDOW_TITLE_KEYWORD): break
        time.sleep(0.2)
    print("[ÇIKIŞ] KO kapalı.");
    BANK_OPEN = False
    TOWN_LOCKED = False
    globals()['TOWN_HARD_LOCK'] = False
    _town_log_once('[TOWN] HardLock KAPALI (oyun kapandı).')
    _town_log_once("[TOWN] Kilit sıfırlandı (oyun kapandı).")


def close_all_game_instances():
    global TOWN_LOCKED
    # Oyunun tüm pencerelerini ve süreçlerini kapat
    wins = gw.getWindowsWithTitle(WINDOW_TITLE_KEYWORD)
    for w in wins:
        try:
            exit_game_fast(w)
        except Exception as e:
            print(f"[ÇIKIŞ] Kapatma hata: {e}")

    # Ardından Launcher'ı DAİMA sıkı şekilde kapat
    _ensure_launcher_closed_strict(max_wait=8.0)


# =============== OYUNU LAUNCHER İLE AÇ (HIZLI) ===============
@with_retry("LAUNCH_START", attempts=3, delay=1.2)
@crashguard("LAUNCH_START")
def launch_via_launcher_and_wait():
    # Önce oyunu ve özellikle LAUNCHER'ı tamamen kapat
    set_stage("LAUNCHER_CLEANUP")
    close_all_game_instances()  # bu çağrı artık _ensure_launcher_closed_strict kullanıyor
    _ensure_launcher_closed_strict(5.0)  # fazladan garanti (çift çağrı harmless)

    if not os.path.exists(LAUNCHER_EXE):
        print(f"[LAUNCHER] Yol yok: {LAUNCHER_EXE}")
        return None

    set_stage("LAUNCHER_START")
    try:
        try:
            os.startfile(LAUNCHER_EXE)
            print("[LAUNCHER] os.startfile")
        except Exception:
            subprocess.Popen([LAUNCHER_EXE], shell=False)
            print("[LAUNCHER] subprocess.Popen")
    except Exception as e:
        print(f"[LAUNCHER] Başlatılamadı: {e}")
        return None
    set_stage("LAUNCHER_FIND_WINDOW");
    clicked = False;
    deadline = time.time() + 2.0
    while time.time() < deadline:
        wait_if_paused();
        watchdog_enforce()
        wL = bring_launcher_window_to_front()
        if wL:
            time.sleep(0.1);
            mouse_move(*LAUNCHER_START_CLICK_POS);
            mouse_click("left");
            print(f"[LAUNCHER] Start tıklandı @ {LAUNCHER_START_CLICK_POS}");
            clicked = True;
            break
        time.sleep(1.5)
    if not clicked:
        mouse_move(*LAUNCHER_START_CLICK_POS);
        mouse_click("left");
        print(f"[LAUNCHER] Start fallback @ {LAUNCHER_START_CLICK_POS}")
    set_stage("LAUNCHER_WAIT_KO_WINDOW");
    t0 = time.time();
    w_detected = None
    while time.time() - t0 < WINDOW_APPEAR_TIMEOUT:
        wait_if_paused();
        watchdog_enforce()
        wins = gw.getWindowsWithTitle(WINDOW_TITLE_KEYWORD)
        if wins: w_detected = wins[0]; break
        time.sleep(0.3)
    if not w_detected: print("[LAUNCHER] Zaman aşımı: KO gelmedi."); return None
    try:
        if w_detected.isMinimized: w_detected.restore()
        w_detected.activate();
        time.sleep(0.3);
        ctypes.windll.user32.SetForegroundWindow(w_detected._hWnd);
        print("[LAUNCHER] KO öne getirildi.")
    except Exception as e:
        print(f"[LAUNCHER] Öne getirme hata: {e}")
    return w_detected


# ================== LOGIN: SAĞLAM GİRİŞ ==================
def perform_login_inputs(w):
    """NE İŞE YARAR: Login ekranında kullanıcı adı/şifreyi SAĞLAM şekilde yazar ve Enter basar."""
    # (Kendi ekranına göre LOGIN_*_CLICK_POS ayarlayabilirsin)
    mouse_move(*LOGIN_USERNAME_CLICK_POS);
    mouse_click("left");
    time.sleep(0.1)
    paste_text_from_clipboard(LOGIN_USERNAME);
    time.sleep(0.1)
    press_key(SC_TAB);
    release_key(SC_TAB);
    time.sleep(0.1)
    # Eğer TAB ile odak geçmiyorsa şifre alanını tıkla:
    mouse_move(*LOGIN_PASSWORD_CLICK_POS);
    mouse_click("left");
    time.sleep(0.05)
    paste_text_from_clipboard(LOGIN_PASSWORD);
    time.sleep(0.1)
    press_key(SC_ENTER);
    release_key(SC_ENTER);
    time.sleep(0.4)
    # Bazı clientlarda iki kez Enter gerekiyor:
    press_key(SC_ENTER);
    release_key(SC_ENTER);
    time.sleep(0.4)
    print("[LOGIN] Username/Password yazıldı ve Enter basıldı.")


# ================== OCR / INV / UPG Yardımcıları (devam Parça 2'de) ==================

# ---- NOT: Aşağıdaki büyük bloklar (OCR, template, upgrade, hover OCR, storage, rota, relaunch+main) Parça 2'de. ----
# ================== OCR / INV / UPG Yardımcıları ==================
def read_coordinates(window):
    """NE İŞE YARAR: Ekrandaki X,Y koordinatlarını küçük ROI'den OCR ile okur."""
    left, top = window.left, window.top;
    bbox = (left + 104, top + 102, left + 160, top + 120)
    img = ImageGrab.grab(bbox);
    gray = img.convert('L').resize((img.width * 2, img.height * 2))
    TOWN_LOCKED = False
    _town_log_once("[TOWN] Kilit sıfırlandı (tüm pencereler kapandı).")
    TOWN_LOCKED = False
    _town_log_once("[TOWN] Kilit sıfırlandı (tüm pencereler kapandı).")
    gray = ImageEnhance.Contrast(gray).enhance(3.0);
    gray = gray.filter(ImageFilter.MedianFilter()).filter(ImageFilter.SHARPEN)
    cfg = r'--psm 7 -c tessedit_char_whitelist=0123456789,.';
    text = pytesseract.image_to_string(gray, config=cfg).strip()
    parts = re.split(r'[,.\s]+', text);
    nums = [p for p in parts if p.isdigit()]
    if len(nums) >= 2: return int(nums[0]), int(nums[1])
    return None, None


def get_region_bounds(region):
    if region == "UPG":
        return UPG_INV_LEFT, UPG_INV_TOP, UPG_INV_RIGHT, UPG_INV_BOTTOM
    elif region == "BANK":
        return BANK_INV_LEFT, BANK_INV_TOP, BANK_INV_RIGHT, BANK_INV_BOTTOM
    elif region == "BANK_PANEL":
        return BANK_PANEL_LEFT, BANK_PANEL_TOP, BANK_PANEL_RIGHT, BANK_PANEL_BOTTOM
    else:
        return INV_LEFT, INV_TOP, INV_RIGHT, INV_BOTTOM


def get_region_grid(region): return (BANK_PANEL_COLS, BANK_PANEL_ROWS) if region == "BANK_PANEL" else (
    SLOT_COLS, SLOT_ROWS)


def grab_gray_region(region):
    L, T, R, B = get_region_bounds(region);
    img = ImageGrab.grab(bbox=(L, T, R, B));
    return cv2.cvtColor(np.array(img), cv2.COLOR_RGB2GRAY)


def cell_rect_in_img(col, row, gray_shape, region):
    H, W = gray_shape[:2];
    cols, rows = get_region_grid(region);
    cw = W // cols;
    ch = H // rows
    x1 = col * cw;
    y1 = row * ch;
    x2 = x1 + cw;
    y2 = y1 + ch;
    return x1, y1, x2, y2


def _fallback_is_empty(roi_gray):
    if roi_gray.size == 0: return False
    h, w = roi_gray.shape[:2];
    cx1, cy1 = int(w * 0.25), int(h * 0.25);
    cx2, cy2 = int(w * 0.75), int(h * 0.75)
    inner = roi_gray[cy1:cy2, cx1:cx2];
    mean_val = float(np.mean(inner));
    edges = cv2.Canny(inner, 50, 120)
    edge_density = float(edges.sum()) / (255.0 * max(inner.size, 1))
    return (mean_val <= FALLBACK_MEAN_THRESHOLD) and (edge_density <= FALLBACK_EDGE_DENSITY_THRESHOLD)


def _load_empty_template():
    p = resource_path(EMPTY_SLOT_TEMPLATE_PATH) if os.path.exists(
        resource_path(EMPTY_SLOT_TEMPLATE_PATH)) else EMPTY_SLOT_TEMPLATE_PATH
    if not os.path.exists(p): return None
    return cv2.imread(p, cv2.IMREAD_GRAYSCALE)


def slot_is_empty_in_gray(gray_region, col, row, region, tmpl):
    x1, y1, x2, y2 = cell_rect_in_img(col, row, gray_region.shape, region);
    roi = gray_region[y1:y2, x1:x2]
    if roi.size == 0: return False
    if tmpl is not None:
        try:
            t_resized = cv2.resize(tmpl, (roi.shape[1], roi.shape[0]))
            res = cv2.matchTemplate(roi, t_resized, cv2.TM_CCOEFF_NORMED);
            _, match_val, _, _ = cv2.minMaxLoc(res)
            if match_val >= EMPTY_SLOT_MATCH_THRESHOLD: return True
        except Exception:
            pass
    return _fallback_is_empty(roi)


def slot_center(region, col, row):
    L, T, R, B = get_region_bounds(region);
    cols, rows = get_region_grid(region)
    cw = (R - L) // cols;
    ch = (B - T) // rows;
    x = L + int((col + 0.5) * cw);
    y = T + int((row + 0.5) * ch);
    return x, y


def count_empty_slots(region="INV"):
    gray = grab_gray_region(region);
    tmpl = _load_empty_template();
    empty_count = 0
    cols, rows = get_region_grid(region)
    for r in range(rows):
        for c in range(cols):
            if slot_is_empty_in_gray(gray, c, r, region, tmpl): empty_count += 1
    print(f"[EMPTY][{region}] Boş slot: {empty_count}");
    return empty_count


def slot_order():
    order = []
    for c in range(1, 7): order.append((c, 0))
    for r in range(1, 4):
        for c in range(0, 7): order.append((c, r))
    return order


WRAP_SLOTS = [(1, 0), (2, 0), (3, 0), (4, 0), (5, 0), (6, 0),
              (0, 1), (1, 1), (2, 1), (3, 1), (4, 1), (5, 1), (6, 1),
              (0, 2), (1, 2), (2, 2), (3, 2), (4, 2), (5, 2), (6, 2),
              (0, 3), (1, 3), (2, 3), (3, 3), (4, 3), (5, 3), (6, 3)]


def find_next_filled_slot_from_index(start_index, used_slots, region):
    order = slot_order();
    tmpl = _load_empty_template()
    for i in range(start_index, len(order)):
        c, r = order[i]
        if (c, r) in used_slots: continue
        gray = grab_gray_region(region)
        if not slot_is_empty_in_gray(gray, c, r, region, tmpl): return (i, (c, r))
    return (None, None)


def open_upgrade_screen_fast():
    wait_if_paused();
    press_key(SC_B);
    release_key(SC_B);
    time.sleep(UPG_STEP_DELAY)
    mouse_move(526, 431);
    mouse_click("right");
    time.sleep(UPG_STEP_DELAY)
    mouse_move(514, 394);
    mouse_click("left");
    time.sleep(UPG_STEP_DELAY)


# ====== SCROLL ŞABLONLARI/TESPİT ======
SCROLL_LOW_TEMPLATES = [];
SCROLL_MID_TEMPLATES = []


def _load_templates_from(paths):
    arr = []
    for p in paths:
        pp = resource_path(p) if os.path.exists(resource_path(p)) else p
        if os.path.exists(pp):
            im = cv2.imread(pp, cv2.IMREAD_GRAYSCALE)
            if im is not None: arr.append(im)
    return arr


def load_scroll_templates():
    global SCROLL_LOW_TEMPLATES, SCROLL_MID_TEMPLATES
    SCROLL_LOW_TEMPLATES = _load_templates_from(SCROLL_LOW_TEMPLATE_PATHS)
    SCROLL_MID_TEMPLATES = _load_templates_from(SCROLL_MID_TEMPLATE_PATHS)
    print(f"[SCROLL] Low={len(SCROLL_LOW_TEMPLATES)}, Mid={len(SCROLL_MID_TEMPLATES)} yüklendi.")


def _roi_matches_any_template(roi_gray, tmpl_list, thr=SCROLL_MATCH_THRESHOLD):
    if roi_gray is None or roi_gray.size == 0 or not tmpl_list: return False
    try:
        edges_roi = cv2.Canny(roi_gray, 60, 140)
        for t in tmpl_list:
            for s in SCROLL_SCALES:
                tr = cv2.resize(t, (0, 0), fx=s, fy=s, interpolation=cv2.INTER_AREA);
                th, tw = tr.shape[:2]
                if th < 8 or tw < 8 or th > roi_gray.shape[0] or tw > roi_gray.shape[1]: continue
                te = cv2.Canny(tr, 60, 140);
                res = cv2.matchTemplate(edges_roi, te, cv2.TM_CCOEFF_NORMED);
                _, maxv, _, _ = cv2.minMaxLoc(res)
                if maxv >= thr: return True
    except Exception:
        pass
    return False


def _grab_gray_roi_around_point(x, y, w=SCROLL_FIND_ROI_W, h=SCROLL_FIND_ROI_H):
    x1 = max(0, int(x - w // 2));
    y1 = max(0, int(y - h // 2));
    x2 = x1 + w;
    y2 = y1 + h
    img = ImageGrab.grab(bbox=(x1, y1, x2, y2));
    return cv2.cvtColor(np.array(img), cv2.COLOR_RGB2GRAY)


def scroll_present_at_pos(required: str) -> bool:
    if SCROLL_SEARCH_ANYWHERE:
        return find_scroll_pos_anywhere(required) is not None

    # eski sabit-ROI davranışı (geri-uyumluluk)
    x, y = SCROLL_POS
    roi = _grab_gray_roi_around_point(x, y)
    if required == "LOW":
        return _roi_matches_any_template(roi, SCROLL_LOW_TEMPLATES)
    if required == "MID":
        return _roi_matches_any_template(roi, SCROLL_MID_TEMPLATES)
    return True


def wait_for_required_scroll(required: str) -> bool:
    if required not in ("LOW", "MID", None): required = None
    if required is None: return True
    print(f"[SCROLL] Bekleniyor: {required} @ {SCROLL_POS}");
    last_log = 0.0
    while True:
        wait_if_paused();
        watchdog_enforce()
        if _kb_pressed('f12'): print("[SCROLL] F12 iptal."); return False
        if scroll_present_at_pos(required): print(f"[SCROLL] Bulundu: {required}"); return True
        if time.time() - last_log > 1.0: print(f"[SCROLL] {required} yok, bekleniyor..."); last_log = time.time()
        time.sleep(0.15)


# ================== LOW/MID Scroll Alma Stage ==================
def _run_scroll_purchase_flow(w, adet, vendor_pos, *, prefix="[SCROLL]", npc_pos=(535, 520)):
    print(f"{prefix} alma stage, hedef adet={adet}")

    try:
        if w is not None:
            exit_game_fast(w)
    except Exception:
        pass

    w = relaunch_and_login_to_ingame()
    if not w:
        print(f"{prefix} Relaunch başarısız.")
        return False

    ensure_ui_closed()
    tries = 0
    while True:
        wait_if_paused()
        watchdog_enforce()
        send_town_command()
        time.sleep(0.2)
        x, _y = read_coordinates(w)
        if x == 812:
            print(f"{prefix} X=812 yakalandı.")
            break
        tries += 1
        if tries >= 100:
            print(f"{prefix} X=812 yakalanamadı (100 deneme). VALID_X hizasına geçiliyor.")
            town_until_valid_x(w)
            break

    go_w_to_y(w, 605, timeout=20.0)

    press_key(SC_B)
    release_key(SC_B)
    time.sleep(0.2)
    mouse_move(*npc_pos)
    mouse_click("right")
    time.sleep(0.3)
    wait_and_click_template(
        w,
        NPC_OPEN_TEXT_TEMPLATE_PATH,
        threshold=NPC_OPEN_MATCH_THRESHOLD,
        timeout=NPC_OPEN_FIND_TIMEOUT,
        scales=NPC_OPEN_SCALES,
    )
    mouse_move(*vendor_pos)
    mouse_click("right")
    time.sleep(0.2)
    for ch in str(adet):
        keyboard.write(ch)
        time.sleep(0.05)
    mouse_move(764, 381)
    mouse_click("left")
    time.sleep(0.2)
    mouse_move(905, 486)
    mouse_click("left")
    time.sleep(0.2)
    mouse_move(722, 582)
    mouse_click("left")
    time.sleep(0.3)

    print(f"{prefix} alındı → çıkış")
    exit_game_fast(w)
    return True


def scroll_alma_stage(w, adet=SCROLL_ALIM_ADET):
    return _run_scroll_purchase_flow(w, adet, (737, 183), prefix="[SCROLL] LOW")


def scroll_alma_stage_mid(w, adet=SCROLL_MID_ALIM_ADET):
    # YAMA: tek akış — önce exit, sonra relaunch, town ve NPC alış
    return _run_scroll_purchase_flow(w, adet, SCROLL_VENDOR_MID_POS, prefix="[SCROLL][MID]")


# ================== Görüntü/Template Yardımcıları ==================
def grab_window_gray(win):
    x1, y1, x2, y2 = win.left, win.top, win.right, win.bottom
    if mss is not None:
        try:
            import numpy as _np
            with mss.mss() as sct:
                mon = {"left": x1, "top": y1, "width": x2 - x1, "height": y2 - y1}
                im = _np.array(sct.grab(mon))[:, :, :3]
                return cv2.cvtColor(im, cv2.COLOR_BGR2GRAY)
        except Exception:
            pass
    img = ImageGrab.grab(bbox=(x1, y1, x2, y2))
    return cv2.cvtColor(np.array(img), cv2.COLOR_RGB2GRAY)


def match_template_multiscale(hay_gray, tmpl_gray, scales):
    if hay_gray is None or tmpl_gray is None: return (0.0, None, None)
    Hh, Wh = hay_gray.shape[:2];
    best = (0.0, None, None)
    try:
        hayE = cv2.Canny(hay_gray, 60, 140)
    except Exception:
        hayE = None
    for s in scales:
        try:
            t = cv2.resize(tmpl_gray, (0, 0), fx=s, fy=s, interpolation=cv2.INTER_AREA)
        except Exception:
            continue
        th, tw = t.shape[:2]
        if th < 8 or tw < 8 or th > Hh or tw > Wh: continue
        try:
            r1 = cv2.matchTemplate(hay_gray, t, cv2.TM_CCOEFF_NORMED);
            _, m1, _, l1 = cv2.minMaxLoc(r1)
        except Exception:
            m1, l1 = 0.0, (0, 0)
        m2 = -1.0;
        l2 = (0, 0)
        if hayE is not None:
            try:
                te = cv2.Canny(t, 60, 140);
                r2 = cv2.matchTemplate(hayE, te,
                                       cv2.TM_CCOEFF_NORMED);
                _, m2, _, l2 = cv2.minMaxLoc(
                    r2)
            except Exception:
                m2 = -1.0
        if m1 >= m2:
            tl = l1;
            score = m1
        else:
            tl = l2;
            score = m2
        center = (tl[0] + tw // 2, tl[1] + th // 2)
        if score > best[0]: best = (score, center, tl)
    return best


def wait_and_click_template(win, template_path, threshold=0.8, timeout=5.0, scales=(1.0,)):
    pp = resource_path(template_path) if os.path.exists(resource_path(template_path)) else template_path
    if not os.path.exists(pp): print(f"[Uyarı] Template yok: {template_path}"); return False
    tmpl = cv2.imread(pp, cv2.IMREAD_GRAYSCALE)
    if tmpl is None: print(f"[Uyarı] Template okunamadı: {template_path}"); return False
    t0 = time.time();
    last = 0.0
    while True:
        wait_if_paused();
        watchdog_enforce()
        if _kb_pressed('f12'): return False
        gray = grab_window_gray(win);
        score, center, _ = match_template_multiscale(gray, tmpl, scales)
        if time.time() - last > 0.4: print(
            f"[FIND] {os.path.basename(template_path)} score={score:.2f} center={center}"); last = time.time()
        if score >= threshold and center is not None:
            ax = win.left + center[0];
            ay = win.top + center[1]
            mouse_move(ax, ay);
            mouse_click("left");
            mouse_move(*TEMPLATE_EXTRA_CLICK_POS);
            mouse_click("left");
            time.sleep(0.1)
            print(f"[CLICK] {os.path.basename(template_path)} tıklandı. score={score:.2f} @ ({ax},{ay})");
            return True
        if (time.time() - t0) > timeout: print(f"[FIND] Zaman aşımı: {os.path.basename(template_path)}"); return False
        time.sleep(0.1)

        def _click_template_or_restart(w, template_path, *, threshold=0.8, timeout=5.0, scales=(1.0,)):
            """
            NE İŞE YARAR: wait_and_click_template() çağırır.
            - Başarılıysa (True, w) döner.
            - Zaman aşımıysa ve ON_TEMPLATE_TIMEOUT_RESTART True ise oyunu kapatır, relaunch edip (False, w2) döner.
            """
            ok = wait_and_click_template(w, template_path, threshold=threshold, timeout=timeout, scales=scales)
            if ok or not ON_TEMPLATE_TIMEOUT_RESTART:
                return ok, w

            print(f"[TIMEOUT] {template_path} bulunamadı → OYUN KAPAT/RELAUNCH tetiklendi.")
            try:
                exit_game_fast(w)
            except Exception as e:
                print(f"[TIMEOUT] exit_game_fast hata: {e}")
            w2 = relaunch_and_login_to_ingame()
            if not w2:
                print("[TIMEOUT] Relaunch başarısız.")
            return False, (w2 if w2 else w)


def pick_existing_template(paths):
    for p in paths:
        pp = resource_path(p) if os.path.exists(resource_path(p)) else p
        if os.path.exists(pp):
            img = cv2.imread(pp, cv2.IMREAD_GRAYSCALE)
            if img is not None: return pp
    return None


@with_retry("CLICK_START", attempts=5, delay=6)
def try_click_oyun_start_with_retries(w, attempts=5, wait_between=4.0):
    set_stage("START_RETRY")
    ok = wait_and_click_template(w, GAME_START_TEMPLATE_PATH, threshold=GAME_START_MATCH_THRESHOLD,
                                 timeout=GAME_START_FIND_TIMEOUT, scales=GAME_START_SCALES)
    return True if ok else None


# ================== +N (7/8) OCR/Şablon ==================
PLUS7_TEMPLATES = [];
PLUS8_TEMPLATES = []


def load_plus7_templates():
    global PLUS7_TEMPLATES;
    PLUS7_TEMPLATES = []
    for p in PLUS7_TEMPLATE_PATHS:
        pp = resource_path(p) if os.path.exists(resource_path(p)) else p
        if os.path.exists(pp):
            img = cv2.imread(pp, cv2.IMREAD_GRAYSCALE)
            if img is not None: PLUS7_TEMPLATES.append(img)
    print(f"[+7] {len(PLUS7_TEMPLATES)} şablon.")


def load_plus8_templates():
    global PLUS8_TEMPLATES;
    PLUS8_TEMPLATES = []
    for p in PLUS8_TEMPLATE_PATHS:
        pp = resource_path(p) if os.path.exists(resource_path(p)) else p
        if os.path.exists(pp):
            img = cv2.imread(pp, cv2.IMREAD_GRAYSCALE)
            if img is not None: PLUS8_TEMPLATES.append(img)
    print(f"[+8] {len(PLUS8_TEMPLATES)} şablon.")


def build_plus_regex(N: int): return re.compile(rf'(?<!\d)\+{N}(?!\d)')


def _preprocess_for_ocr(gray):
    clahe = cv2.createCLAHE(2.2, (8, 8));
    g = clahe.apply(gray);
    g = cv2.bilateralFilter(g, 5, 50, 50)
    sharp = cv2.addWeighted(g, 1.5, cv2.GaussianBlur(g, (0, 0), 1.0), -0.5, 0);
    _, th = cv2.threshold(sharp, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU);
    return th


def _match_plus7_templates_on(gray_slice, thr=0.78):
    if not PLUS7_TEMPLATES: return False
    try:
        hed = cv2.Canny(gray_slice, 60, 140)
        for t in PLUS7_TEMPLATES:
            for s in (0.60, 0.70, 0.80, 0.90, 1.0, 1.15, 1.30, 1.45, 1.60):
                tr = cv2.resize(t, (0, 0), fx=s, fy=s, interpolation=cv2.INTER_AREA);
                th, tw = tr.shape[:2]
                if th < 8 or tw < 8 or th > gray_slice.shape[0] or tw > gray_slice.shape[1]: continue
                te = cv2.Canny(tr, 60, 140);
                res = cv2.matchTemplate(hed, te, cv2.TM_CCOEFF_NORMED);
                _, mv, _, _ = cv2.minMaxLoc(res)
                if mv >= thr: return True
    except Exception:
        pass
    return False


def _match_plus8_templates_on(gray_slice, thr=0.78):
    if not PLUS8_TEMPLATES: return False
    try:
        hed = cv2.Canny(gray_slice, 60, 140)
        for t in PLUS8_TEMPLATES:
            for s in (0.60, 0.70, 0.80, 0.90, 1.0, 1.15, 1.30, 1.45, 1.60):
                tr = cv2.resize(t, (0, 0), fx=s, fy=s, interpolation=cv2.INTER_AREA);
                th, tw = tr.shape[:2]
                if th < 8 or tw < 8 or th > gray_slice.shape[0] or tw > gray_slice.shape[1]: continue
                te = cv2.Canny(tr, 60, 140);
                res = cv2.matchTemplate(hed, te, cv2.TM_CCOEFF_NORMED);
                _, mv, _, _ = cv2.minMaxLoc(res)
                if mv >= thr: return True
    except Exception:
        pass
    return False


def _roi_has_plusN(roi_gray, N: int):
    if roi_gray is None or roi_gray.size == 0: return False
    h, w = roi_gray.shape[:2];
    header_h = max(80, int(h * 0.28));
    header = roi_gray[0:header_h, :]
    if N == 7:
        if _match_plus7_templates_on(header, 0.78) or _match_plus7_templates_on(roi_gray, 0.80): return True
        try:
            proc = _preprocess_for_ocr(header);
            pil = Image.fromarray(proc)
            cfg = r'--oem 3 --psm 7 -c tessedit_char_whitelist=+0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz[]'
            data = pytesseract.image_to_data(pil, config=cfg, output_type=pytesseract.Output.DICT)
            rg = build_plus_regex(7)
            for i in range(len(data["text"])):
                txt = (data["text"][i] or "").strip()
                if not txt: continue
                conf = float(data["conf"][i]) if data["conf"][i] not in ("-1", "", None) else -1.0
                if conf >= 50 and rg.search(txt): return True
        except Exception:
            pass
        return False
    elif N == 8:
        if _match_plus8_templates_on(header, 0.76) or _match_plus8_templates_on(roi_gray, 0.78): return True
        try:
            proc = _preprocess_for_ocr(header);
            pil2 = Image.fromarray(proc)
            cfg2 = r'--oem 3 --psm 6 -c tessedit_char_whitelist=+0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz[]'
            txt2 = pytesseract.image_to_string(pil2, config=cfg2)
            if build_plus_regex(8).search(txt2 or ""): return True
        except Exception:
            pass
        return False
    else:
        try:
            proc = _preprocess_for_ocr(header);
            pil2 = Image.fromarray(proc)
            cfg2 = r'--oem 3 --psm 6 -c tessedit_char_whitelist=+0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz[]'
            txt2 = pytesseract.image_to_string(pil2, config=cfg2)
            if build_plus_regex(N).search(txt2 or ""): return True
        except Exception:
            pass
        return False


class POINT(ctypes.Structure): _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


def _get_mouse_pos():
    pt = POINT();
    ctypes.windll.user32.GetCursorPos(ctypes.byref(pt));
    return int(pt.x), int(pt.y)


def _grab_tooltip_roi_near_mouse(win, roi_w=TOOLTIP_ROI_W, roi_h=TOOLTIP_ROI_H):
    try:
        mx, my = _get_mouse_pos();
        Lw, Tw, Rw, Bw = win.left, win.top, win.right, win.bottom
        half = roi_w // 2;
        x1 = mx - half;
        y1 = my - (roi_h + TOOLTIP_OFFSET_Y);
        x2 = x1 + roi_w;
        y2 = y1 + roi_h
        x1 = max(Lw, x1);
        y1 = max(Tw, y1);
        x2 = min(Rw, x2);
        y2 = min(Bw, y2)
        if x2 - x1 < 40 or y2 - y1 < 40: raise ValueError("ROI small")
        img = ImageGrab.grab(bbox=(x1, y1, x2, y2));
        return cv2.cvtColor(np.array(img), cv2.COLOR_RGB2GRAY)
    except Exception:
        L, T, R, B = TOOLTIP_FALLBACK_BBOX;
        img = ImageGrab.grab(bbox=(L, T, R, B));
        return cv2.cvtColor(np.array(img), cv2.COLOR_RGB2GRAY)


def hover_has_plusN(win, region, col, row, N: int, hover_wait=None):
    # Hızlı +7/+8 tespiti: tek/az örnek, MSS ile hızlı grab, OCR opsiyonel
    if hover_wait is None:
        hover_wait = HOVER_WAIT_BANK if region == "BANK_PANEL" else HOVER_WAIT_INV
    x, y = slot_center(region, col, row)
    mouse_move(100, 100);
    time.sleep(0.02)
    mouse_move(x, y);
    time.sleep(hover_wait)

    if bool(globals().get('PLUSN_FAST_MODE', True)):
        samples = max(1, int(globals().get('PLUSN_HOVER_SAMPLES', 1)))
        use_ocr = bool(globals().get('PLUSN_USE_OCR_FALLBACK', False))
        wait_between = float(globals().get('PLUSN_WAIT_BETWEEN', 0.06))
        last_roi = None
        for i in range(samples):
            roi = _grab_tooltip_roi_near_mouse_fast(win) or _grab_tooltip_roi_near_mouse(win)
            last_roi = roi
            if N == 7:
                if _match_plus7_templates_on(roi, 0.78) or _match_plus7_templates_on(roi, 0.80): return True
            elif N == 8:
                if _match_plus8_templates_on(roi, 0.76) or _match_plus8_templates_on(roi, 0.78): return True
            if i < samples - 1: time.sleep(wait_between)
        if use_ocr and last_roi is not None:
            return _roi_has_plusN(last_roi, N)
        return False

    # Yavaş ama sağlam yol (orijinale yakın): 3 örnek + OCR
    roi1 = _grab_tooltip_roi_near_mouse(win)
    if _roi_has_plusN(roi1, N): return True
    time.sleep(0.12);
    roi2 = _grab_tooltip_roi_near_mouse(win)
    if _roi_has_plusN(roi2, N): return True
    time.sleep(0.10);
    roi3 = _grab_tooltip_roi_near_mouse(win)
    return _roi_has_plusN(roi3, N)


def is_slot_plus7(win, region, c, r):
    try:
        return hover_has_plusN(win, region, c, r, 7)
    except Exception:
        return False


def count_inventory_plusN(win, N: int, region="INV"):
    cols, rows = get_region_grid(region);
    count = 0;
    tmpl = _load_empty_template()
    for r in range(rows):
        for c in range(cols):
            gray = grab_gray_region(region)
            if slot_is_empty_in_gray(gray, c, r, region, tmpl): continue
            if hover_has_plusN(win, region, c, r, N): count += 1
    print(f"[+{N}] Toplam +{N} ({region}): {count}");
    return count


def deposit_inventory_plusN_to_bank(win, N: int):
    set_stage(f"STORAGE_DEPOSIT_PLUS{N}");
    deposited = 0
    cols, rows = get_region_grid("BANK");
    tmpl = _load_empty_template()
    for r in range(rows):
        for c in range(cols):
            wait_if_paused();
            watchdog_enforce()
            if _kb_pressed('f12'): print("[STORAGE] F12 kesildi."); return deposited
            gray = grab_gray_region("BANK")
            if slot_is_empty_in_gray(gray, c, r, "BANK", tmpl): continue
            try:
                if hover_has_plusN(win, "BANK", c, r, N):
                    x, y = slot_center("BANK", c, r);
                    mouse_move(x, y);
                    mouse_click("right");
                    deposited += 1;
                    time.sleep(0.09)
            except Exception as e:
                print(f"[STORAGE] Slot ({c},{r}) hata: {e}")
    print(f"[STORAGE] Bankaya atılan +{N}: {deposited}");
    return deposited


# ================== Scroll Takası (BANK/INV) ==================
def _cell_roi(gray, region, c, r): x1, y1, x2, y2 = cell_rect_in_img(c, r, gray.shape, region); return gray[y1:y2,
                                                                                                       x1:x2]


def deposit_low_scrolls_from_inventory_to_bank(max_stacks=SCROLL_SWAP_MAX_STACKS):
    if not SCROLL_LOW_TEMPLATES: print("[SCROLL] Low templates yok."); return 0
    set_stage("SCROLL_DEPOSIT_LOW");
    moved = 0;
    gray = grab_gray_region("BANK");
    cols, rows = get_region_grid("BANK")
    for r in range(rows):
        for c in range(cols):
            if moved >= max_stacks: print(f"[SCROLL] Low deposit limiti {max_stacks}."); return moved
            roi = _cell_roi(gray, "BANK", c, r);
            tmpl_empty = _load_empty_template()
            if slot_is_empty_in_gray(gray, c, r, "BANK", tmpl_empty): continue
            if _roi_matches_any_template(roi, SCROLL_LOW_TEMPLATES):
                x, y = slot_center("BANK", c, r);
                right_click_enter_at(x, y);
                moved += 1;
                time.sleep(0.2);
                gray = grab_gray_region("BANK")
    print(f"[SCROLL] Bankaya gönderilen LOW scroll: {moved}");
    return moved


def withdraw_mid_scrolls_from_bank_to_inventory(max_stacks=SCROLL_SWAP_MAX_STACKS):
    if not SCROLL_MID_TEMPLATES: print("[SCROLL] Mid templates yok."); return 0
    set_stage("SCROLL_WITHDRAW_MID");
    taken = 0;
    inv_empty = count_empty_slots("BANK")
    if inv_empty <= 0: print("[SCROLL] Envanterde boş yok."); return 0
    bank_go_to_first_page();
    tmpl_empty = _load_empty_template()
    for page in range(1, 9):
        grayp = grab_gray_region("BANK_PANEL");
        cols, rows = get_region_grid("BANK_PANEL")
        for r in range(rows):
            for c in range(cols):
                if taken >= max_stacks or inv_empty <= 0: print(
                    f"[SCROLL] MID çekim tamam: {taken}, boş={inv_empty}"); return taken
                if slot_is_empty_in_gray(grayp, c, r, "BANK_PANEL", tmpl_empty): continue
                roi = _cell_roi(grayp, "BANK_PANEL", c, r)
                if _roi_matches_any_template(roi, SCROLL_MID_TEMPLATES):
                    x, y = slot_center("BANK_PANEL", c, r);
                    right_click_enter_at(x, y);
                    taken += 1;
                    inv_empty -= 1;
                    time.sleep(0.2);
                    grayp = grab_gray_region("BANK_PANEL")
        if page < 8: bank_click_next(1, 0.15)
    print(f"[SCROLL] Bankadan MID: {taken}");
    return taken


def deposit_mid_scrolls_from_inventory_to_bank(max_stacks=SCROLL_SWAP_MAX_STACKS):
    if not SCROLL_MID_TEMPLATES: print("[SCROLL] Mid templates yok."); return 0
    set_stage("SCROLL_DEPOSIT_MID");
    moved = 0;
    gray = grab_gray_region("BANK");
    cols, rows = get_region_grid("BANK");
    tmpl_empty = _load_empty_template()
    for r in range(rows):
        for c in range(cols):
            if moved >= max_stacks: print(f"[SCROLL] Mid deposit limiti {max_stacks}."); return moved
            if slot_is_empty_in_gray(gray, c, r, "BANK", tmpl_empty): continue
            roi = _cell_roi(gray, "BANK", c, r)
            if _roi_matches_any_template(roi, SCROLL_MID_TEMPLATES):
                x, y = slot_center("BANK", c, r);
                right_click_enter_at(x, y);
                moved += 1;
                time.sleep(0.2);
                gray = grab_gray_region("BANK")
    print(f"[SCROLL] Bankaya MID: {moved}");
    return moved


def withdraw_low_scrolls_from_bank_to_inventory(max_stacks=SCROLL_SWAP_MAX_STACKS):
    if not SCROLL_LOW_TEMPLATES: print("[SCROLL] Low templates yok."); return 0
    set_stage("SCROLL_WITHDRAW_LOW");
    taken = 0;
    inv_empty = count_empty_slots("BANK")
    if inv_empty <= 0: print("[SCROLL] Envanterde boş yok."); return 0
    bank_go_to_first_page();
    tmpl_empty = _load_empty_template()
    for page in range(1, 9):
        print(f"[SCROLL] LOW arama sayfa {page}/8")
        grayp = grab_gray_region("BANK_PANEL");
        cols, rows = get_region_grid("BANK_PANEL")
        for r in range(rows):
            for c in range(cols):
                if taken >= max_stacks or inv_empty <= 0: print(
                    f"[SCROLL] LOW çekim tamam: {taken}, boş={inv_empty}"); return taken
                if slot_is_empty_in_gray(grayp, c, r, "BANK_PANEL", tmpl_empty): continue
                roi = _cell_roi(grayp, "BANK_PANEL", c, r)
                if _roi_matches_any_template(roi, SCROLL_LOW_TEMPLATES):
                    x, y = slot_center("BANK_PANEL", c, r);
                    right_click_enter_at(x, y);
                    taken += 1;
                    inv_empty -= 1;
                    time.sleep(0.2);
                    grayp = grab_gray_region("BANK_PANEL")
        if page < 8: bank_click_next(1, 0.15)
    print(f"[SCROLL] Bankadan LOW: {taken}");
    return taken


# ================== NPC SHOP ONAY ==================
def _grab_gray_bbox(bbox): img = ImageGrab.grab(bbox=bbox); return cv2.cvtColor(np.array(img), cv2.COLOR_RGB2GRAY)


def confirm_npc_shop_or_relogin(w):
    pp = resource_path(NPC_CONFIRM_TEMPLATE_PATH) if os.path.exists(
        resource_path(NPC_CONFIRM_TEMPLATE_PATH)) else NPC_CONFIRM_TEMPLATE_PATH
    if not os.path.exists(pp): print("[NPC_ONAY] npc_onay.png yok → atlandı."); return True, w
    try:
        roi = _grab_gray_bbox(NPC_CONFIRM_RECT);
        tmpl = cv2.imread(pp, cv2.IMREAD_GRAYSCALE)
        if tmpl is None: print("[NPC_ONAY] npc_onay.png okunamadı → atlandı."); return True, w
        score, _, _ = match_template_multiscale(roi, tmpl, NPC_CONFIRM_SCALES);
        print(f"[NPC_ONAY] skor={score:.3f} (eşik={NPC_CONFIRM_MATCH_THRESHOLD})")
        if score >= NPC_CONFIRM_MATCH_THRESHOLD:
            print("[NPC_ONAY] Onay başarılı.");
            return True, w
        else:
            print("[NPC_ONAY] Onay BAŞARISIZ → relogin.")
            try:
                exit_game_fast(w)
            except Exception:
                pass
            w2 = relaunch_and_login_to_ingame();
            return False, w2
    except Exception as e:
        print(f"[NPC_ONAY] Hata: {e} → relogin.")
        try:
            exit_game_fast(w)
        except Exception:
            pass
        w2 = relaunch_and_login_to_ingame();
        return False, w2


# ===================== WRAPPERS: KOORD OKUMA & KAPAT/RELAUNCH =====================
# Bu blok; mikro-düzeltme fonk.larında kullanılan eksik isimleri sağlar.
def read_coord_x():
    """X koordinatını döndürür (oyun penceresini öne alıp OCR okur)."""
    try:
        w = bring_game_window_to_front()
        x, _y = read_coordinates(w)
        return x
    except Exception:
        return None


def read_coord_y():
    """Y koordinatını döndürür (oyun penceresini öne alıp OCR okur)."""
    try:
        w = bring_game_window_to_front()
        _x, y = read_coordinates(w)
        return y
    except Exception:
        return None


def close_game():
    """Tüm KO ve Launcher süreçlerini kapatır (güvenli kapatma)."""
    try:
        close_all_game_instances()  # Merdiven.py'de tanımlı
    except Exception:
        pass


def relaunch():
    """Oyunu tekrar açıp oyuna giriş yapar, pencere nesnesini döndürür."""
    try:
        return relaunch_and_login_to_ingame()  # Merdiven.py'de tanımlı
    except Exception:
        return None


# ================================================================================

# ================== Hareket / Rota ==================
def ensure_ui_closed(): press_key(SC_ESC); release_key(SC_ESC); time.sleep(0.1); press_key(SC_ESC); release_key(
    SC_ESC); time.sleep(0.1)


def _read_axis(w, axis: str):
    try:
        x, y = read_coordinates(w)
    except Exception:
        x, y = None, None
    return x if axis == 'x' else y


# >>> OVERSHOOT FİX: A/D YOK, SADECE W – YÖN-PARAM ve TOLERANSLI KABUL <<<
def go_precise_x_no_nudge(w, target_x: int, dir: str, timeout: float = None):
    """
    NE İŞE YARAR: X hedefe sadece W ile ilerler; ±X_TOLERANCE bandına girince başarı kabul eder.
    dir='inc' → X artarak hedefe; dir='dec' → X azalarak hedefe. A/D BASMAZ.
    """
    import time
    if timeout is None: timeout = X_TOL_TIMEOUT
    t0 = time.time();
    in_band = 0
    press_key(SC_W)
    try:
        while True:
            wait_if_paused();
            watchdog_enforce()
            if keyboard.is_pressed('f12'): return False
            cur = _read_axis(w, 'x')
            if cur is None:
                time.sleep(X_TOL_READ_DELAY);
                continue
            if dir == 'inc':
                in_band = in_band + 1 if cur >= (target_x - X_TOLERANCE) else 0
            else:  # 'dec'
                in_band = in_band + 1 if cur <= (target_x + X_TOLERANCE) else 0
            if in_band >= X_BAND_CONSEC:
                log(f"[PREC] X hedef {target_x} yakalandı (cur={cur}, tol=±{X_TOLERANCE}).")
                return True
            if (time.time() - t0) > timeout:
                log(f"[PREC] tolerant timeout: cur={cur} target={target_x}")
                return True
            time.sleep(X_TOL_READ_DELAY)
    finally:
        release_key(SC_W)


def detect_w_direction(w, axis: str, pulses=4, dp=0.020, target=None) -> int:
    """W nabızlarıyla eksen yönünü ölç; ölçülemezse X/Y için +1 (artıyor) varsay, mümkünse hedef ipucunu kullan."""
    assert axis in ('x', 'y')
    base = _read_axis(w, axis)
    if base is None:
        # Ölçüm yoksa güvenli varsayım: ileri (artıyor)
        return +1
    for _ in range(pulses):
        with key_tempo(0.0):
            press_key(SC_W);
            time.sleep(dp);
            release_key(SC_W)
        time.sleep(MICRO_READ_DELAY);
        newv = _read_axis(w, axis)
        if newv is None: continue
        if newv > base: return +1
        if newv < base: return -1
    # Değişim okunamadı: hedef ipucuyla yönü seç
    if target is not None:
        try:
            return +1 if target > base else -1
        except Exception:
            pass
    # Son çare: artıyor
    return +1


def _select_micro_key(direction: int, cur: int, target: int) -> str:
    """Hedefe yaklaşmak için W/S tuşunu seç (yön ölçümüne göre)."""
    forward_if_higher = (target > cur and direction == +1) or (target < cur and direction == -1)
    return 'w' if forward_if_higher else 's'


def _micro_adjust_axis(read_current: Callable[[], Optional[int]], axis: str, target: int, direction: int,
                       pulse_seq: Sequence[float], settle_hits: int, max_duration: float = MICRO_ADJUST_MAX_DURATION,
                       deadline: Optional[float] = None) -> bool:
    """Çift yönlü mikro döngü: hedefin üstünde ise S, altında ise W ile toparlar."""
    start = time.time()
    stable = 0
    key_map = {'w': SC_W, 's': SC_S}

    def _deadline_reached():
        now = time.time()
        if (now - start) >= max_duration:
            return True
        if deadline is not None and now >= deadline:
            return True
        return False

    while not _deadline_reached():
        wait_if_paused();
        watchdog_enforce()
        if _kb_pressed('f12'):
            return False
        cur = read_current()
        if cur is None:
            time.sleep(MICRO_READ_DELAY)
            continue
        if cur == target:
            stable += 1
            if stable >= settle_hits:
                print(f"[PREC] {axis.upper()} hedef {target} yakalandı.")
                return True
            time.sleep(MICRO_READ_DELAY)
            continue
        stable = 0
        key_char = _select_micro_key(direction, cur, target)
        key_code = key_map[key_char]
        for dp in pulse_seq:
            with key_tempo(0.0):
                press_key(key_code)
                time.sleep(max(0.002, dp))
                release_key(key_code)
            time.sleep(MICRO_READ_DELAY)
            after = read_current()
            if after is not None and after != cur:
                break
    return False


def precise_move_w_to_axis(w, axis: str, target: int, timeout: float = 20.0, pre_brake_delta: int = PRE_BRAKE_DELTA,
                           pulse: float = MICRO_PULSE_DURATION, settle_hits: int = TARGET_STABLE_HITS,
                           force_exact: bool = True) -> bool:
    # [YAMA] PREC_MOVE_Y_598 başında kilit + çift tık (GUI ile yönetilir)
    try:
        if str(axis).lower() == 'y' and int(target) == 598:
            if bool(globals().get('PREC_Y598_TOWN_HARDLOCK', True)):
                globals()['TOWN_HARD_LOCK'] = True
                _town_log_once('[TOWN] HardLock AÇIK (PREC_MOVE_Y_598)')
            set_stage(f"PREC_MOVE_{axis.upper()}_{target}")
            if bool(globals().get('PREC_Y598_DBLCLICK', True)):
                try:
                    _pos = tuple(globals().get('PREC_Y598_CLICK_POS', (200, 107)))
                    _cnt = int(globals().get('PREC_Y598_CLICK_COUNT', 2))
                    _delay = float(globals().get('PREC_Y598_CLICK_DELAY', 0.1))
                    for _ in range(max(0, _cnt)):
                        mouse_move(int(_pos[0]), int(_pos[1]));
                        mouse_click('left');
                        time.sleep(_delay)
                except Exception as _e:
                    print('[PREC598] dblclick hata:', _e)
            ensure_ui_closed()
    except Exception as _e:
        print('[PREC598] init hata:', _e)
    assert axis in ('x', 'y');
    set_stage(f"PREC_MOVE_{axis.upper()}_{target}");
    ensure_ui_closed();
    t0 = time.time();
    press_key(SC_W)
    try:
        while True:
            wait_if_paused();
            watchdog_enforce()
            if _kb_pressed('f12'): return False
            cur = _read_axis(w, axis)
            if cur is None: time.sleep(MICRO_READ_DELAY); continue
            if abs(target - cur) <= pre_brake_delta: break
            if (time.time() - t0) > timeout: print(f"[PREC] timeout pre-brake cur={cur} target={target}"); return False
            time.sleep(0.03)
    finally:
        release_key(SC_W)
    direction = detect_w_direction(w, axis, target=target);
    print(f"[PREC] {axis.upper()} yön: {'artıyor' if direction == 1 else 'azalıyor'}")

    seq = [pulse * 0.5, pulse * 0.66, pulse * 0.8, pulse]
    remaining_timeout = max(0.0, float(timeout) - (time.time() - t0))
    deadline = time.time() + remaining_timeout
    matched = _micro_adjust_axis(lambda: _read_axis(w, axis), axis, target, direction, seq, settle_hits,
                                 max_duration=MICRO_ADJUST_MAX_DURATION, deadline=deadline)
    fc = _read_axis(w, axis);
    ok = matched or ((fc == target) if force_exact else abs((fc or target) - target) <= 1)
    print(f"[PREC] Son: axis={axis} cur≈{fc} target={target} ok={ok}");
    return ok


def go_w_to_x(w, target_x: int, timeout: float = NPC_SEEK_TIMEOUT) -> bool: return precise_move_w_to_axis(w, 'x',
                                                                                                          target_x,
                                                                                                          timeout=timeout,
                                                                                                          force_exact=True)


def go_w_to_y(w, target_y: int, timeout: float = Y_SEEK_TIMEOUT) -> bool:  return precise_move_w_to_axis(w, 'y',
                                                                                                         target_y,
                                                                                                         timeout=timeout,
                                                                                                         force_exact=True)


def town_until_valid_x(w):
    set_stage("TOWN_ALIGN_FOR_VALID_X");
    attempts = 0
    while True:
        wait_if_paused();
        watchdog_enforce()
        try:
            x, _ = read_coordinates(w)
        except Exception:
            x = None
        if x in VALID_X: print(f"[ALIGN] Geçerli X: {x} (deneme={attempts})"); return x
        print(f"[ALIGN] X={x} geçersiz → town.");
        ensure_ui_closed();
        send_town_command();
        attempts += 1;
        set_stage("TOWN_ALIGN_FOR_VALID_X");
        time.sleep(0.2)


# >>> SPEED_AWARE_BEGIN_v2
# === Hız-Profili Dinamik Fren Mesafesi (X ve Y) ===
# NE İŞE YARAR: FAST/BALANCED/SAFE → pre_brake_delta seçer ve precise_move_w_to_axis ile hedefe gider.
_SPEED_PRE_BRAKE = {"FAST": 2, "BALANCED": 3, "SAFE": 4}


def _get_speed_profile():
    gp = globals()
    p = gp.get("SPEED_PROFILE")
    if isinstance(p, str): return p.upper()
    for k in ("ACTIVE_SPEED", "CURRENT_SPEED", "SELECTED_SPEED", "GUI_SPEED_MODE"):
        v = gp.get(k)
        if isinstance(v, str): return v.upper()
    return "FAST"


def _get_delta(): return int(_SPEED_PRE_BRAKE.get(_get_speed_profile(), _SPEED_PRE_BRAKE["FAST"]))


# --- Yalnızca mevcut iki fonksiyonu override ediyoruz (imza KORUNUR) ---
def go_w_to_y(w, target_y: int, timeout: float = None) -> bool:
    # NE İŞE YARAR: Y hedefe yaklaşırken profilden gelen delta ile mikro fren uygular
    if timeout is None:
        timeout = globals().get("Y_SEEK_TIMEOUT", 20.0)
    d = _get_delta()
    return precise_move_w_to_axis(w, 'y', int(target_y), timeout=timeout, pre_brake_delta=d, force_exact=True)


def go_w_to_x(w, target_x: int, timeout: float = None) -> bool:
    # NE İŞE YARAR: X hedefe yaklaşırken profilden gelen delta ile mikro fren uygular
    if timeout is None:
        timeout = globals().get("NPC_SEEK_TIMEOUT", 20.0)
    d = _get_delta()
    return precise_move_w_to_axis(w, 'x', int(target_x), timeout=timeout, pre_brake_delta=d, force_exact=True)


# <<< SPEED_AWARE_END_v2

def ascend_stairs_to_top(w):
    global NEED_STAIRS_REALIGN
    set_stage("ASCEND_STAIRS");
    ensure_ui_closed()
    try:
        x, _ = read_coordinates(w)
    except Exception:
        x = None
    if x not in VALID_X: print("[STAIRS] X geçersiz → town hizala."); town_until_valid_x(w)
    target_y = int(globals().get('STAIRS_TOP_Y', STAIRS_TOP_Y))

    def _finalize_top(y_val=None):
        global NEED_STAIRS_REALIGN
        nonlocal target_y
        y_val = _read_y_now() if y_val is None else y_val
        _set_town_lock_by_y(y_val)
        if TOWN_LOCKED:
            _town_log_once('[TOWN] Kilit aktif (Y=598) — town artık kapalı')
        if y_val is not None and int(y_val) == target_y:
            print("[STAIRS] 598 tepe → S mikro geri 2x")
            for _ in range(STAIRS_TOP_S_BACKOFF_PULSES):
                micro_tap(SC_S, STAIRS_TOP_S_BACKOFF_DURATION)
                time.sleep(0.1)
            try:
                post_598_to_597()
            except Exception as e:
                print("[STAIRS] 598→597 mikro düzeltme hata:", e)
        NEED_STAIRS_REALIGN = False

    y_now = _read_y_now()
    if y_now is not None and target_y - 1 <= int(y_now) <= target_y:
        print(f"[STAIRS] Y≈{y_now} (597-598 bandı) → go_w_to_y atlandı, konum sabitleniyor.")
        _finalize_top(y_now)
        return

    ok = go_w_to_y(w, target_y, timeout=Y_SEEK_TIMEOUT)
    if not ok:
        print("[STAIRS] go_w_to_y başarısız → town & retry");
        send_town_command()
        return

    _finalize_top(_read_y_now())


def go_to_npc_from_top(w):
    set_stage("GO_TO_NPC");
    ensure_ui_closed()
    press_key(SC_A);
    time.sleep(TURN_LEFT_SEC);
    release_key(SC_A)
    press_key(SC_W);
    time.sleep(NPC_GIDIS_SURESI);
    release_key(SC_W)
    _ = go_w_to_x(w, TARGET_NPC_X, timeout=NPC_SEEK_TIMEOUT)  # başarısız olsa da akış devam etsin
    time.sleep(0.1)

    press_key(SC_B);
    release_key(SC_B);
    time.sleep(0.15)
    mouse_move(*NPC_CONTEXT_RIGHTCLICK_POS);
    mouse_click("right");
    time.sleep(0.2)

    # npc_acma.png tıklaması (ZAMAN AŞIMINDA RELAUNCH)
    ok = wait_and_click_template(
        w,
        NPC_OPEN_TEXT_TEMPLATE_PATH,
        threshold=NPC_OPEN_MATCH_THRESHOLD,
        timeout=NPC_OPEN_FIND_TIMEOUT,
        scales=NPC_OPEN_SCALES
    )
    if not ok:
        print("[TIMEOUT] npc_acma.png bulunamadı / zaman aşımı.")
        if globals().get("ON_TEMPLATE_TIMEOUT_RESTART", True):
            print("[TIMEOUT] ON_TEMPLATE_TIMEOUT_RESTART=True → oyunu kapatıp yeniden başlatıyorum.")
            try:
                exit_game_fast(w)
            except Exception as e:
                print(f"[TIMEOUT] exit_game_fast hata: {e}")
            w2 = relaunch_and_login_to_ingame()
            # Relaunch sonrası akış çağırana dönsün; üst akış yeni w ile devam eder
            return (False, w2 if w2 else w)
        else:
            print("[TIMEOUT] Bayrak False → relaunch yapmadan dönüyorum.")
            return (False, w)

    print("[Bilgi] NPC açma yazısı tıklandı.")
    mouse_move(*NPC_MENU_PAGE2_POS);
    mouse_click("left");
    time.sleep(0.15)

    onay_ok, w_after = confirm_npc_shop_or_relogin(w)
    if not onay_ok:
        return (False, w_after if w_after is not None else w)

    purchased = buy_items_from_npc()
    return (purchased, w)


def go_to_anvil_from_top(start_x):
    set_stage("GO_TO_ANVIL");
    ensure_ui_closed()
    if start_x in VALID_X_LEFT:
        press_key(SC_D);
        time.sleep(0.3);
        release_key(SC_D)
    elif start_x in VALID_X_RIGHT:
        press_key(SC_A);
        time.sleep(0.3);
        release_key(SC_A)
    press_key(SC_W);
    time.sleep(ANVIL_WALK_TIME);
    release_key(SC_W)


def move_to_769_and_turn_from_top(w):
    global BANK_OPEN
    set_stage("MOVE_TO_STORAGE_AREA");
    ensure_ui_closed();
    press_key(SC_A);
    time.sleep(TURN_LEFT_SEC);
    release_key(SC_A)
    ok = go_w_to_x(w, TARGET_NPC_X, timeout=NPC_SEEK_TIMEOUT)
    if not ok: print("[Uyarı] 768 x hedeflemesi zaman aşımı (storage).")
    press_key(SC_D);
    time.sleep(TURN_RIGHT_SEC);
    release_key(SC_D)
    ok = go_w_to_y(w, TARGET_Y_AFTER_TURN, timeout=Y_SEEK_TIMEOUT)
    if not ok: print("[Uyarı] 648 y hedeflemesi zaman aşımı (storage).")
    time.sleep(0.05);
    press_key(SC_B);
    release_key(SC_B);
    time.sleep(0.15);
    mouse_move(*NPC_CONTEXT_RIGHTCLICK_POS);
    mouse_click("right");
    time.sleep(0.2)
    tpl = pick_existing_template(USE_STORAGE_TEMPLATE_PATHS)
    if not tpl: print("[STORAGE] 'Use Storage' template yok."); return False
    ok = wait_and_click_template(w, tpl, threshold=USE_STORAGE_MATCH_THRESHOLD, timeout=USE_STORAGE_FIND_TIMEOUT,
                                 scales=USE_STORAGE_SCALES)
    if not ok: print("[STORAGE] 'Use Storage' bulunamadı."); return False
    print("[STORAGE] 'Use Storage' tıklandı → banka.");
    time.sleep(0.4);
    BANK_OPEN = True;
    return True


def send_town_command(*a, **kw):
    # Y==598 ise kilit aktif → town iptal; diğer tüm durumlarda serbest
    global TOWN_LOCKED, BANK_OPEN
    # [YAMA] HardLock aktifse town tamamen kapalı
    if globals().get('TOWN_HARD_LOCK', False):
        _town_log_once('[TOWN] HardLock aktif — komut iptal.')
        return False
    y_now = _read_y_now();
    _set_town_lock_by_y(y_now)
    if TOWN_LOCKED:
        _town_log_once('[TOWN] Kilit aktif (Y=598) — komut iptal edildi')
        return False
    mouse_move(*TOWN_CLICK_POS);
    mouse_click('left');
    time.sleep(TOWN_WAIT)
    BANK_OPEN = False


def buy_items_from_npc():
    set_stage("NPC_BUY_28")
    for _ in range(NPC_BUY_TURN_COUNT):
        for (x, y), clicks, btn in NPC_BUY_STEPS:
            for __ in range(clicks):
                wait_if_paused();
                watchdog_enforce()
                if _kb_pressed('f12'): return False
                mouse_move(x, y);
                mouse_click(btn);
                time.sleep(0.08)
    print("[NPC] 28 item alındı.");
    return True


# ================== Storage / Banka Sayfa ==================
def bank_click_next(times=1, delay=BANK_PAGE_CLICK_DELAY):
    for _ in range(times): mouse_move(*BANK_NEXT_PAGE_POS); mouse_click("left"); time.sleep(delay)


def bank_click_prev(times=1, delay=BANK_PAGE_CLICK_DELAY):
    for _ in range(times): mouse_move(*BANK_PREV_PAGE_POS); mouse_click("left"); time.sleep(delay)


def bank_go_to_last_page(): bank_click_next(7, BANK_PAGE_CLICK_DELAY)


def bank_go_to_first_page(): bank_click_prev(7, BANK_PAGE_CLICK_DELAY)


def count_empty_in_bank_panel_page(): return count_empty_slots("BANK_PANEL")


def after_deposit_check_and_decide_mode(w):
    global MODE, BANK_FULL_FLAG, BANK_OPEN
    set_stage("BANK_AFTER_DEPOSIT_CHECK")
    BANK_OPEN = True
    bank_go_to_last_page()
    empties = count_empty_in_bank_panel_page()

    if empties >= 1:
        print(f"[BANK] 8.sayfa {empties} boş → NORMAL.")
        _set_mode_normal("8.sayfa boş")
        BANK_FULL_FLAG = False
        _stop_plus8_wait_notifier()
        return "NORMAL"

    # 8. sayfa FULL
    print(f"[BANK] 8.sayfa full.")
    _set_mode_normal("8.sayfa full", reset_plus8_state=True)
    BANK_FULL_FLAG = True
    stage_detail("+8 bekleme: Banka full, F tuşu için Telegram bildirimi aktif")
    _start_plus8_wait_notifier()

    try:
        if AUTO_BANK_PLUS8:
            print(f"[BANK] {int(AUTO_BANK_PLUS8_DELAY)} sn içinde +8 döngüsü otomatik başlayacak "
                  f"(erken başlatmak için 'F', iptal için F12).")
            deadline = time.time() + float(AUTO_BANK_PLUS8_DELAY)
            res = _wait_for_f_with_countdown(deadline, label="BANK_PLUS8 F beklemesi (auto)")
            if res == "F":
                _set_mode_bank_plus8("F alındı")
                print("[BANK] 'F' alındı → BANK_PLUS8.")
                return "BANK_PLUS8"
            if res == "ABORT":
                print("[BANK] F12 alındı → ABORT.")
                return "ABORT"
            _set_mode_bank_plus8("Süre doldu")
            print("[BANK] Süre doldu → otomatik BANK_PLUS8.")
            return "BANK_PLUS8"
        else:
            # Eski davranış: 'F' bekle, süre dolarsa NORMAL
            print(f"[BANK] 'F' bekleniyor ({int(F_WAIT_TIMEOUT_SECONDS)} sn).")
            deadline = time.time() + float(F_WAIT_TIMEOUT_SECONDS)
            res = _wait_for_f_with_countdown(deadline, label="BANK_PLUS8 F beklemesi (manual)")
            if res == "F":
                _set_mode_bank_plus8("F alındı")
                print("[BANK] 'F' alındı → BANK_PLUS8.")
                return "BANK_PLUS8"
            if res == "ABORT":
                print("[BANK] F12 alındı → ABORT.")
                return "ABORT"
            print("[BANK] Süre doldu → NORMAL.")
            _set_mode_normal("F süresi doldu")
            return "NORMAL"
    finally:
        _stop_plus8_wait_notifier()


def withdraw_plusN_from_bank_pages(win, N: int, max_take=27):
    set_stage(f"BANK_WITHDRAW_PLUS{N}");
    taken = 0;
    tmpl = _load_empty_template();
    bank_go_to_first_page()
    for page in range(1, 9):
        wait_if_paused();
        watchdog_enforce();
        print(f"[BANK] Sayfa {page}/8 taranıyor...")
        cols, rows = get_region_grid("BANK_PANEL")
        for r in range(rows):
            for c in range(cols):
                if taken >= max_take: print(f"[BANK] İstenen adet: {taken}/{max_take}"); return taken
                gray = grab_gray_region("BANK_PANEL")
                if slot_is_empty_in_gray(gray, c, r, "BANK_PANEL", tmpl): continue
                if hover_has_plusN(win, "BANK_PANEL", c, r, N, hover_wait=HOVER_WAIT_BANK):
                    x, y = slot_center("BANK_PANEL", c, r);
                    mouse_move(x, y);
                    mouse_click("right");
                    taken += 1;
                    time.sleep(0.10)
        if page < 8: bank_click_next(1, 0.15)
    print(f"[BANK] Toplam çekilen +{N}: {taken}");
    return taken


def withdraw_plus_range_from_bank_pages(win, min_plus: int = 1, max_plus: int = 6, max_take: int = 27):
    set_stage("BANK_WITHDRAW_PLUS_RANGE");
    taken = 0
    tmpl = _load_empty_template()
    bank_go_to_first_page()
    for page in range(1, 9):
        wait_if_paused();
        watchdog_enforce();
        print(f"[BANK] Sayfa {page}/8 ( +{min_plus}…+{max_plus} ) taranıyor…")
        cols, rows = get_region_grid("BANK_PANEL")
        for r in range(rows):
            for c in range(cols):
                if taken >= max_take:
                    print(f"[BANK] İstenen adet: {taken}/{max_take}");
                    return taken
                gray = grab_gray_region("BANK_PANEL")
                if slot_is_empty_in_gray(gray, c, r, "BANK_PANEL", tmpl):
                    continue
                try:
                    if hover_has_plusN(win, "BANK_PANEL", c, r, 7, hover_wait=HOVER_WAIT_BANK) or \
                            hover_has_plusN(win, "BANK_PANEL", c, r, 8, hover_wait=HOVER_WAIT_BANK):
                        continue
                    roi = _grab_tooltip_roi_near_mouse_fast(win) or _grab_tooltip_roi_near_mouse(win)
                    if roi is not None and (_roi_has_plusN(roi, 7) or _roi_has_plusN(roi, 8)):
                        continue
                    x, y = slot_center("BANK_PANEL", c, r)
                    mouse_move(x, y)
                    mouse_click("right")
                    taken += 1
                    time.sleep(0.10)
                except Exception as e:
                    print(f"[BANK] +{min_plus}…+{max_plus} tarama hata: {e}")
        if page < 8:
            bank_click_next(1, 0.15)
    print(f"[BANK] Toplam çekilen +{min_plus}…+{max_plus}: {taken}")
    return taken


def withdraw_items_from_bank_for_sale(max_take: int = None):
    set_stage("ITEM_SATIS_BANK_WITHDRAW")
    try:
        max_take_val = int(max_take if max_take is not None else ITEM_SALE_BANK_WITHDRAW_COUNT)
    except Exception:
        max_take_val = ITEM_SALE_BANK_WITHDRAW_COUNT
    if max_take_val <= 0:
        max_take_val = ITEM_SALE_BANK_WITHDRAW_COUNT

    taken = 0
    tmpl = _load_empty_template()
    bank_go_to_first_page()
    for page in range(1, 9):
        wait_if_paused()
        watchdog_enforce()
        print(f"[ITEM_SATIS][BANK] Sayfa {page}/8 taranıyor...")
        stage_detail(f"Bankada sayfa {page}/8 taranıyor (çekilen: {taken}/{max_take_val})")
        cols, rows = get_region_grid("BANK_PANEL")
        for r in range(rows):
            for c in range(cols):
                if taken >= max_take_val:
                    print(f"[ITEM_SATIS][BANK] Çekilen: {taken}/{max_take_val}")
                    stage_detail(f"Bankadan alınan: {taken}/{max_take_val}")
                    return taken
                gray = grab_gray_region("BANK_PANEL")
                if slot_is_empty_in_gray(gray, c, r, "BANK_PANEL", tmpl):
                    continue
                x, y = slot_center("BANK_PANEL", c, r)
                mouse_move(x, y)
                mouse_click("right")
                taken += 1
                time.sleep(0.10)
        if page < 8:
            bank_click_next(1, 0.15)
    print(f"[ITEM_SATIS][BANK] Toplam çekilen: {taken}")
    stage_detail(f"Bankadan alınan toplam: {taken}")
    return taken


# ================== ITEM SATIŞ MODU ==================
def _item_sale_move_to_market(w):
    set_stage("ITEM_SATIS_HAZIRLIK")
    ensure_ui_closed()
    press_key(SC_A)
    time.sleep(TURN_LEFT_SEC)
    release_key(SC_A)
    target_primary = None
    try:
        target_primary = float(globals().get("PAZAR_PARK_X", PAZAR_PARK_X))
    except Exception:
        target_primary = float(PAZAR_PARK_X)
    candidates = []
    if target_primary is not None:
        candidates.append(int(round(target_primary)))
    for fallback in ITEM_SALE_VALID_X:
        if fallback not in candidates:
            candidates.append(int(fallback))
    reached = False
    for target in candidates:
        if go_w_to_x(w, int(target), timeout=Y_SEEK_TIMEOUT):
            print(f"[ITEM_SATIS] X hedefi yakalandı: {target}")
            reached = True
            break
    if not reached:
        print(f"[ITEM_SATIS] Hedef X bulunamadı (denenenler: {candidates}).")
    with key_tempo(0.0):
        press_key(SC_A)
        time.sleep(max(0.0, float(ITEM_SALE_FACE_A_DURATION)))
        release_key(SC_A)


def _item_sale_type_price_text(price_text: str, key_delay: float):
    text = str(price_text or "")
    if text:
        for ch in text:
            wait_if_paused()
            watchdog_enforce()
            keyboard.write(ch)
            time.sleep(0.02)
    time.sleep(key_delay)
    wait_if_paused()
    watchdog_enforce()
    press_key(SC_ENTER)
    release_key(SC_ENTER)
    time.sleep(key_delay)
    wait_if_paused()
    watchdog_enforce()
    press_key(SC_ENTER)
    release_key(SC_ENTER)
    time.sleep(key_delay)


def _item_sale_fill_market(price_text: str) -> int:
    set_stage("ITEM_SATIS_PAZAR_DOLDUR")
    filled = 0
    key_delay = 0.20
    for row_y in (375, 425, 475, 525):
        for i in range(7):
            wait_if_paused()
            watchdog_enforce()
            sx = 365 + 50 * i
            mouse_drag(sx, row_y, PAZAR_DROP_TARGET[0], PAZAR_DROP_TARGET[1], hold=0.12)
            time.sleep(0.1)
            _item_sale_type_price_text(price_text, key_delay)
            filled += 1
    for _ in range(2):
        mouse_move(656, 610)
        mouse_click("left")
        time.sleep(key_delay)
    for _ in range(50):
        press_vk(VK_BACKSPACE)
        release_vk(VK_BACKSPACE)
        time.sleep(0.2)
    mouse_move(476, 644)
    mouse_click("left")
    time.sleep(61.0)
    mouse_move(476, 644)
    mouse_click("left")
    time.sleep(2.0)
    mouse_move(806, 776)
    mouse_click("left")
    time.sleep(key_delay)
    return filled


def _item_sale_report_slot_count(empty_slots: int):
    print(f"[ITEM_SATIS] Boş slot sayısı: {empty_slots}")
    globals()["ITEM_SALE_LAST_SLOT_COUNT"] = int(empty_slots)
    stage_detail(f"Boş slot sayısı: {empty_slots}")
    try:
        cb = globals().get("_GUI_UPDATE_SALE_SLOT")
        if callable(cb):
            cb(int(empty_slots))
    except Exception:
        pass


def _item_sale_refresh_market(initial=False) -> int:
    global _AUTO_MARKET_LAST_REFRESH_TS
    set_stage("ITEM_SATIS_PAZAR_YENILE")
    if initial:
        if PAZAR_ILK_BEKELEME_SURESI > 0:
            wait_val = float(PAZAR_ILK_BEKELEME_SURESI)
            print(f"[ITEM_SATIS] İlk kurulum bekleniyor: {wait_val}s")
            _wait_with_stage_detail(wait_val, lambda rem: f"İlk kurulum bekleniyor, kalan: {rem} sn")
    else:
        refresh_min = globals().get("PAZAR_YENILEME_BEKELEME_MIN", PAZAR_YENILEME_BEKELEME_MIN)
        refresh_max = globals().get("PAZAR_YENILEME_BEKELEME_MAX", PAZAR_YENILEME_BEKELEME_MAX)
        wait_val = _random_between(refresh_min, refresh_max)
        if wait_val > 0:
            print(f"[ITEM_SATIS] Yenileme öncesi bekleme: {wait_val:.1f}s")
            _wait_with_stage_detail(wait_val, lambda rem: f"Pazar yenileme bekleniyor, kalan: {rem} sn")
        with key_tempo(0.0):
            press_key(SC_S)
            time.sleep(0.2)
            release_key(SC_S)
        mouse_move(*PAZAR_BREAK_CLICK_POS)
        mouse_click("left")
        time.sleep(0.1)
        if PAZAR_REOPEN_WAIT > 0:
            wait_val = float(PAZAR_REOPEN_WAIT)
            print(f"[ITEM_SATIS] Pazar bozuldu, bekleme: {wait_val}s")
            _wait_with_stage_detail(wait_val, lambda rem: f"Pazar yeniden açılacak, kalan: {rem} sn")

    with key_tempo(0.0):
        press_key(SC_H)
        time.sleep(0.1)
        release_key(SC_H)
    repeated_click(PAZAR_FIRST_CLICK_POS, CLICK_902_135_ADET, CLICK_902_135_HIZ)
    time.sleep(1.0)
    repeated_click(PAZAR_SECOND_CLICK_POS, CLICK_899_399_ADET, CLICK_899_399_HIZ)
    mouse_move(*PAZAR_CONFIRM_CLICK_POS)
    mouse_click("left")
    time.sleep(0.2)
    price_text = str(globals().get("ITEM_SALE_PRICE_TEXT", ITEM_SALE_PRICE_TEXT))
    stage_detail("Pazar slotları dolduruluyor")
    filled = _item_sale_fill_market(price_text)
    print(f"[ITEM_SATIS] Pazara yerleşen item: {filled}")
    stage_detail(f"Pazara yerleşen item: {filled}")
    _AUTO_MARKET_LAST_REFRESH_TS = time.time()
    globals()["_AUTO_MARKET_LAST_REFRESH_TS"] = _AUTO_MARKET_LAST_REFRESH_TS
    try:
        log(f"[AUTO_MARKET] Yenileme tamamlandı (initial={initial}, adet={filled}).")
    except Exception:
        pass
    return filled


def _item_sale_handle_bank(w):
    set_stage("ITEM_SATIS_BANKA")
    ensure_ui_closed()
    exit_game_fast(w)
    new_w = relaunch_and_login_to_ingame()
    if not new_w:
        print("[ITEM_SATIS] Yeniden giriş başarısız (banka).")
        return False
    town_until_valid_x(new_w)
    ascend_stairs_to_top(new_w)
    try:
        post_598_to_597()
    except Exception as e:
        print("[ITEM_SATIS] 598→597 hata:", e)
    if not move_to_769_and_turn_from_top(new_w):
        print("[ITEM_SATIS] Banka açılamadı.")
        return False
    try:
        take_count = int(globals().get("ITEM_SALE_BANK_WITHDRAW_COUNT", ITEM_SALE_BANK_WITHDRAW_COUNT))
    except Exception:
        take_count = ITEM_SALE_BANK_WITHDRAW_COUNT
    if take_count <= 0:
        take_count = ITEM_SALE_BANK_WITHDRAW_COUNT

    taken = withdraw_items_from_bank_for_sale(take_count)
    ensure_ui_closed()
    time.sleep(0.2)
    if taken <= 0:
        notify_enabled = bool(globals().get("ITEM_SALE_BANK_NOTIFY", ITEM_SALE_BANK_NOTIFY))
        if notify_enabled:
            message = str(globals().get("ITEM_SALE_BANK_EMPTY_MESSAGE", ITEM_SALE_BANK_EMPTY_MESSAGE))
            ok = send_telegram_message(message)
            status = "gönderildi" if ok else "gönderilemedi"
            print(f"[ITEM_SATIS][BANK] Telegram bildirimi {status}: {message}")
            stage_detail(f"Banka boş bildirimi {status}: {message}")
        set_stage("ITEM_SATIS_BANK_BOS")
        with key_tempo(0.0):
            press_key(SC_C)
            time.sleep(0.1)
            release_key(SC_C)
        stage_detail("Bankada item kalmadı, karakter beklemede")
        print("[ITEM_SATIS] Bankada item kalmadı. Makro beklemeye alındı.")
        return False

    exit_game_fast(new_w)
    print(f"[ITEM_SATIS] Bankadan alınan: {taken}")
    stage_detail(f"Bankadan alınan: {taken}")
    return True


def _item_sale_krallik_click(pos, hold):
    if not pos:
        return
    try:
        x, y = int(pos[0]), int(pos[1])
    except Exception:
        return
    if x == 0 and y == 0:
        return
    try:
        hold_s = max(0.0, float(hold))
    except Exception:
        hold_s = 0.0

    if not pause_point():
        return
    mouse_move(x, y)
    extra = ctypes.c_ulong(0)
    ii_ = Input_I()
    ii_.mi = MouseInput(0, 0, 0, MOUSEEVENTF_LEFTDOWN, 0, ctypes.pointer(extra))
    SendInput(1, ctypes.pointer(Input(ctypes.c_ulong(0), ii_)), ctypes.sizeof(Input))
    time.sleep(hold_s)
    if _abort_requested():
        return
    ii_.mi = MouseInput(0, 0, 0, MOUSEEVENTF_LEFTUP, 0, ctypes.pointer(extra))
    SendInput(1, ctypes.pointer(Input(ctypes.c_ulong(0), ii_)), ctypes.sizeof(Input))
    time.sleep(mouse_hizi / 2)
    try:
        stage_detail("Krallık yazısı tıklandı")
    except Exception:
        pass


def _item_sale_run_cycle(w):
    global _AUTO_MARKET_LAST_REFRESH_TS
    thresholds = [
        int(globals().get("PAZAR_ESIK_1", PAZAR_ESIK_1)),
        int(globals().get("PAZAR_ESIK_2", PAZAR_ESIK_2)),
        int(globals().get("PAZAR_ESIK_3", PAZAR_ESIK_3)),
    ]
    thresholds = [t for t in thresholds if t > 0]
    done = [False] * len(thresholds)
    bank_threshold = int(globals().get("BANKAYA_GIT_BOS_SLOT_ESIGI", BANKAYA_GIT_BOS_SLOT_ESIGI))
    try:
        interval = float(globals().get("ITEM_SALE_SLOT_SCAN_INTERVAL", ITEM_SALE_SLOT_SCAN_INTERVAL))
    except Exception:
        interval = ITEM_SALE_SLOT_SCAN_INTERVAL
    if interval < 1.0:
        interval = 1.0

    try:
        krallik_interval = max(0.0, float(globals().get("KRALLIK_TIKLAMA_ARALIGI", KRALLIK_TIKLAMA_ARALIGI)))
    except Exception:
        krallik_interval = max(0.0, float(KRALLIK_TIKLAMA_ARALIGI))
    try:
        krallik_pos = (
            int(globals().get("KRALLIK_CLICK_X", KRALLIK_CLICK_X)),
            int(globals().get("KRALLIK_CLICK_Y", KRALLIK_CLICK_Y)),
        )
    except Exception:
        krallik_pos = None
    try:
        krallik_hold = float(globals().get("KRALLIK_TIKLAMA_SURESI", KRALLIK_TIKLAMA_SURESI))
    except Exception:
        krallik_hold = KRALLIK_TIKLAMA_SURESI

    next_krallik_click = None
    if krallik_interval > 0 and krallik_pos is not None and not (krallik_pos[0] == 0 and krallik_pos[1] == 0):
        next_krallik_click = time.time() + krallik_interval

    set_stage("ITEM_SATIS_SLOT_TAKIP")
    next_scan = 0.0
    inv_open = True
    refresh_lock = globals().get("_AUTO_MARKET_REFRESH_LOCK")
    if refresh_lock is None:
        refresh_lock = threading.Lock()
        globals()["_AUTO_MARKET_REFRESH_LOCK"] = refresh_lock

    def open_inventory():
        nonlocal inv_open, next_scan
        if not inv_open:
            inv_open = True
            next_scan = 0.0

    def close_inventory():
        nonlocal inv_open
        if inv_open:
            inv_open = False

    def _maybe_krallik_click(now_ts):
        nonlocal next_krallik_click
        if next_krallik_click is None:
            return
        if now_ts < next_krallik_click:
            return
        try:
            _item_sale_krallik_click(krallik_pos, krallik_hold)
        except Exception as exc:
            print(f"[ITEM_SATIS] Krallık tıklama hata: {exc}")
        next_krallik_click = time.time() + krallik_interval

    def _try_auto_market_refresh() -> bool:
        nonlocal next_scan
        global _AUTO_MARKET_LAST_REFRESH_TS
        enabled = bool(globals().get("auto_market_refresh_enabled", AUTO_MARKET_REFRESH_ENABLED))
        if not enabled:
            return False
        try:
            interval_hours = float(globals().get("auto_market_refresh_interval_hours", AUTO_MARKET_REFRESH_INTERVAL_HOURS))
        except Exception:
            interval_hours = AUTO_MARKET_REFRESH_INTERVAL_HOURS
        interval_sec = max(60.0, interval_hours * 3600.0)
        last = float(globals().get("_AUTO_MARKET_LAST_REFRESH_TS", _AUTO_MARKET_LAST_REFRESH_TS) or 0.0)
        now = time.time()
        if now - last < interval_sec:
            return False
        if refresh_lock and not refresh_lock.acquire(False):
            return False
        globals()["_AUTO_MARKET_REFRESHING"] = True
        try:
            stage_detail("Otomatik pazar yenileme tetikleniyor")
            msg = f"[ITEM_SATIS] Otomatik pazar yenileme tetiklendi (aralık {interval_hours:g} saat)."
            print(msg)
            try:
                log(msg)
            except Exception:
                pass
            close_inventory()
            _item_sale_refresh_market(initial=False)
            _AUTO_MARKET_LAST_REFRESH_TS = time.time()
            globals()["_AUTO_MARKET_LAST_REFRESH_TS"] = _AUTO_MARKET_LAST_REFRESH_TS
            next_scan = 0.0
            return True
        except Exception as e:
            err = f"[ITEM_SATIS] Otomatik pazar yenileme hata: {e}"
            print(err)
            try:
                log(err, lvl="warning")
            except Exception:
                pass
            _AUTO_MARKET_LAST_REFRESH_TS = now
            globals()["_AUTO_MARKET_LAST_REFRESH_TS"] = _AUTO_MARKET_LAST_REFRESH_TS
            return False
        finally:
            globals()["_AUTO_MARKET_REFRESHING"] = False
            if refresh_lock:
                try:
                    refresh_lock.release()
                except Exception:
                    pass

    while True:
        wait_if_paused()
        watchdog_enforce()
        if _kb_pressed('f12'):
            print("[ITEM_SATIS] F12 alındı, döngü sonlandırılıyor.")
            close_inventory()
            return False

        open_inventory()
        now = time.time()
        _maybe_krallik_click(now)
        if now < next_scan:
            time.sleep(0.2)
            continue

        set_stage("ITEM_SATIS_SLOT_TAKIP")
        empty_slots = count_empty_slots("INV")
        _item_sale_report_slot_count(empty_slots)
        next_scan = time.time() + interval

        if empty_slots >= bank_threshold:
            print(f"[ITEM_SATIS] Banka eşiği ({bank_threshold}) yakalandı.")
            stage_detail(f"Banka eşiği ({bank_threshold}) yakalandı")
            close_inventory()
            exit_min = globals().get("ITEM_SALE_EXIT_DELAY_MIN", ITEM_SALE_EXIT_DELAY_MIN)
            exit_max = globals().get("ITEM_SALE_EXIT_DELAY_MAX", ITEM_SALE_EXIT_DELAY_MAX)
            delay = _random_between(exit_min, exit_max)
            if delay > 0:
                set_stage("ITEM_SATIS_BANK_DELAY")
                stage_detail(f"Boş slot sonrası çıkış gecikmesi: {delay:.1f}s")
                _wait_with_stage_detail(delay, lambda rem: f"Boş slot sonrası çıkış bekleniyor: {rem} sn kaldı")
            return _item_sale_handle_bank(w)

        if _try_auto_market_refresh():
            continue

        triggered = False
        for idx, thr in enumerate(thresholds):
            if idx < len(done) and empty_slots >= thr and not done[idx] and all(done[:idx]):
                print(f"[ITEM_SATIS] Eşik tetiklendi ({thr}).")
                stage_detail(f"Eşik tetiklendi ({thr})")
                close_inventory()
                _item_sale_refresh_market(initial=False)
                set_stage("ITEM_SATIS_SLOT_TAKIP")
                done[idx] = True
                next_scan = 0.0
                triggered = True
                break

        if triggered:
            continue

        time.sleep(0.2)


@crashguard("ITEM_SATIS_MAIN")
def run_item_sale_mode():
    while True:
        if _kb_pressed('f12'):
            print("[ITEM_SATIS] Kullanıcı durdurdu.")
            return
        w = relaunch_and_login_to_ingame()
        if not w:
            print("[ITEM_SATIS] Oyuna giriş başarısız.")
            return
        town_until_valid_x(w)
        ascend_stairs_to_top(w)
        try:
            post_598_to_597()
        except Exception as e:
            print("[ITEM_SATIS] 598→597 hata:", e)
        _item_sale_move_to_market(w)
        _item_sale_refresh_market(initial=True)
        set_stage("ITEM_SATIS_SLOT_TAKIP")
        cont = _item_sale_run_cycle(w)
        if not cont:
            break


# ================== Upgrade / Basma ==================
def _jdelay(base: float, spread: float = 0.02) -> float:
    # her koşulda float döndür
    try:
        b = float(base if base is not None else 0.0)
    except Exception:
        b = 0.0
    return max(0.0, b + random.uniform(-spread, spread))


# === Genel bölge kırpma yardımcıları ===
def _grab_gray_rect(rect):
    x1, y1, x2, y2 = rect
    if mss is not None:
        try:
            import numpy as _np
            with mss.mss() as sct:
                mon = {"left": x1, "top": y1, "width": x2 - x1, "height": y2 - y1}
                im = _np.array(sct.grab(mon))[:, :, :3]
                return cv2.cvtColor(im, cv2.COLOR_BGR2GRAY)
        except Exception:
            pass
    img = ImageGrab.grab(bbox=(x1, y1, x2, y2))
    return cv2.cvtColor(np.array(img), cv2.COLOR_RGB2GRAY)


def _find_best_template_location(hay_gray, tmpl_list, thr=SCROLL_MATCH_THRESHOLD, scales=SCROLL_SCALES):
    """
    hay_gray içinde (edges tabanlı) en iyi eşleşmenin MERKEZ koordinatını döndür.
    Dönüş: (score, (cx, cy)) veya (0.0, None)
    """
    if hay_gray is None or hay_gray.size == 0 or not tmpl_list:
        return (0.0, None)

    try:
        hayE = cv2.Canny(hay_gray, 60, 140)
    except Exception:
        hayE = None

    best_score = 0.0
    best_center = None

    for t in tmpl_list:
        for s in scales:
            try:
                tr = cv2.resize(t, (0, 0), fx=s, fy=s, interpolation=cv2.INTER_AREA)
            except Exception:
                continue
            th, tw = tr.shape[:2]
            if th < 8 or tw < 8 or th > hay_gray.shape[0] or tw > hay_gray.shape[1]:
                continue

            # Kenar temelli eşleştirme (daha sağlam)
            try:
                te = cv2.Canny(tr, 60, 140)
                res = cv2.matchTemplate(hayE, te, cv2.TM_CCOEFF_NORMED)
                _, mv, _, tl = cv2.minMaxLoc(res)
            except Exception:
                mv, tl = 0.0, (0, 0)

            if mv > best_score:
                best_score = float(mv)
                best_center = (int(tl[0] + tw // 2), int(tl[1] + th // 2))

    if best_score >= thr and best_center is not None:
        return (best_score, best_center)
    return (0.0, None)


def find_scroll_center_any(required: str, region="UPG", thr=None):
    """
    required: 'LOW' | 'MID'
    region:  'UPG' (upgrade envanter alanı)
    Dönüş: (abs_x, abs_y) veya None
    """
    if thr is None:
        # Biraz daha esnek eşik (0.05 gevşet)
        thr = max(0.50, SCROLL_MATCH_THRESHOLD - 0.05)

    if required == "LOW":
        tlist = SCROLL_LOW_TEMPLATES
    elif required == "MID":
        tlist = SCROLL_MID_TEMPLATES
    else:
        tlist = []

    L, T, R, B = get_region_bounds(region)
    hay = _grab_gray_rect((L, T, R, B))
    score, cen = _find_best_template_location(hay, tlist, thr=thr, scales=SCROLL_SCALES)
    if cen is None:
        return None

    cx, cy = cen
    abs_x = L + cx
    abs_y = T + cy
    print(f"[SCROLL] {required} bulundu (global): score={score:.2f} @ ({abs_x},{abs_y})")
    return (abs_x, abs_y)


def sleep_jitter(base: float, spread: float = 0.02):
    time.sleep(_jdelay(base, spread))


def perform_upgrade_on_slot(col, row, click_region, scroll_required=None, *, win=None):
    global REQUEST_RELAUNCH
    px, py = slot_center(click_region, col, row);
    tries = 0
    while True:
        wait_if_paused();
        watchdog_enforce()
        if _kb_pressed('f12'): return "ABORT"

        open_upgrade_screen_fast();
        mouse_move(px, py);
        mouse_click("right");
        time.sleep(UPG_STEP_DELAY)

        if scroll_required in ("LOW", "MID"):
            # 1) Upgrade bölgesi içinde scroll’u HER YERDE ara
            found_xy = find_scroll_center_any(scroll_required, region="UPG")

            if not found_xy:
                if scroll_required == "LOW":
                    # >>> LOW için global reopen bütçesi
                    can_continue, used, lim = _consume_scroll_reopen_low()
                    print(f"[SCROLL] LOW yok (global arama) → panel reopen ({used}/{lim})")
                    if can_continue:
                        time.sleep(0.10)
                        continue

                    # >>> BÜTÇE BİTTİ: BURAYA EKLE <<<
                    print("[SCROLL] LOW arama hakkı bitti → LOW satın alma stage’i tetikleniyor.")
                    scroll_alma_stage(win,
                                      adet=SCROLL_ALIM_ADET)  # önce çık, relogin, X=812, Y=605, vendor’dan al, sonra çık
                    REQUEST_RELAUNCH = True  # üst akış temiz relaunch etsin
                    return "EXIT_LOOP"
                else:
                    # MID veya diğerleri: eski, slot-özel deneme sayacı
                    tries += 1
                    print(
                        f"[SCROLL] {scroll_required} yok (global arama) → panel reopen ({tries}/{SCROLL_PANEL_REOPEN_MAX})")
                    if tries < SCROLL_PANEL_REOPEN_MAX:
                        time.sleep(0.10)
                        continue
                    if scroll_required == "MID":
                        # Orta scroll panelini yeniden açma denemeleri tükendi.
                        # Bu noktada NPC'ye gidip taze orta scroll stoklamak için
                        # "Orta Scroll Satın Alma" sahnesini çağırıyoruz.
                        print("[SCROLL] MID arama hakkı bitti → MID satın alma stage’i tetikleniyor.")
                        scroll_alma_stage_mid(win, adet=SCROLL_MID_ALIM_ADET)
                        REQUEST_RELAUNCH = True
                        return "EXIT_LOOP"
                    print(f"[SCROLL] {scroll_required} yok → FALLBACK sabit nokta deneniyor: {SCROLL_POS}")
                    found_xy = SCROLL_POS

            # 2) Bulunan konuma sağ tıkla (global ya da fallback)
            mouse_move(*found_xy);
            mouse_click("right")
        else:
            # scroll_required None ise eski sabit davranış
            mouse_move(*SCROLL_POS);
            mouse_click("right")

        time.sleep(_jdelay(UPG_STEP_DELAY))
        mouse_move(*UPGRADE_BTN_POS);
        mouse_click("left");
        time.sleep(UPG_STEP_DELAY)
        mouse_move(*CONFIRM_BTN_POS);
        mouse_click("left");
        time.sleep(UPG_STEP_DELAY)
        hover_guard()
        return "DONE"


@crashguard("UPGRADE_LOOP")
def basma_dongusu(attempts_limit=None, scroll_required=None, *, win=None, skip_plus8: bool = False):
    global ITEMS_DEPLETED_FLAG, REQUEST_RELAUNCH, MODE, FORCE_PLUS7_ONCE
    ITEMS_DEPLETED_FLAG = False;
    limit = attempts_limit if attempts_limit is not None else BASMA_HAKKI
    set_stage("UPGRADE_LOOP");
    used = set();
    attempts_done = 0;
    start_index = 0;
    total_slots = len(slot_order())
    ensure_ui_closed();
    press_key(SC_I);
    release_key(SC_I);
    time.sleep(0.6)
    skip_plus7 = (scroll_required == "LOW") and (win is not None)
    # >>> YENİ: LOW akışı için global reopen sayacı sıfırla
    if scroll_required == "LOW":
        _reset_scroll_reopen_budget("LOW")
    while attempts_done < limit and start_index < total_slots:
        wait_if_paused();
        watchdog_enforce()
        if _kb_pressed('f12'): break
        idx_found, slot = find_next_filled_slot_from_index(start_index, used, "UPG")
        if slot is None: break
        gray = grab_gray_region("UPG");
        tmpl = _load_empty_template();
        c, r = slot
        if slot_is_empty_in_gray(gray, c, r, "UPG", tmpl): start_index = idx_found + 1; continue
        if skip_plus7 and hover_has_plusN(win, "UPG", c, r, 7): print(
            f"[UPG] Slot ({c},{r}) +7 → atla."); start_index = idx_found + 1; continue
        if skip_plus8 and hover_has_plusN(win, "UPG", c, r, 8): print(
            f"[UPG] Slot ({c},{r}) +8 → atla."); start_index = idx_found + 1; continue
        res = perform_upgrade_on_slot(c, r, click_region="UPG", scroll_required=scroll_required, win=win)
        if res == "DONE":
            used.add(slot);
            attempts_done += 1
        elif res in ("EXIT_LOOP", "ABORT"):
            return attempts_done
        start_index = idx_found + 1
    wrap_cursor = 0
    while attempts_done < limit:
        wait_if_paused();
        watchdog_enforce()
        if _kb_pressed('f12'): break
        gray = grab_gray_region("UPG");
        tmpl = _load_empty_template()
        found_and_upgraded = False;
        seen_item = False;
        skipped_due_to_scroll = False;
        seen_only_plus7 = True if skip_plus7 else False
        for i in range(len(WRAP_SLOTS)):
            idx = (wrap_cursor + i) % len(WRAP_SLOTS);
            c, r = WRAP_SLOTS[idx]
            if slot_is_empty_in_gray(gray, c, r, "UPG", tmpl): continue
            seen_item = True
            if skip_plus7 and hover_has_plusN(win, "UPG", c, r, 7):
                print(f"[UPG] Slot ({c},{r}) +7 → atla.");
                continue
            if skip_plus8 and hover_has_plusN(win, "UPG", c, r, 8):
                print(f"[UPG] Slot ({c},{r}) +8 → atla.");
                continue
            else:
                if skip_plus7: seen_only_plus7 = False
            res = perform_upgrade_on_slot(c, r, click_region="UPG", scroll_required=scroll_required, win=win)
            if res == "DONE":
                attempts_done += 1;
                wrap_cursor = (idx + 1) % len(WRAP_SLOTS);
                found_and_upgraded = True;
                break
            elif res == "SKIP_SCROLL":
                skipped_due_to_scroll = True;
                continue
            elif res in ("EXIT_LOOP", "ABORT"):
                return attempts_done
        if not found_and_upgraded:
            if skipped_due_to_scroll: print("[UPG] Scroll görünmüyor → kısa bekle."); time.sleep(0.15); continue
            if not seen_item:
                print(f"[UPG] Wrap alanında item yok. Deneme: {attempts_done}/{limit}");
                ITEMS_DEPLETED_FLAG = True
                if MODE != "BANK_PLUS8": REQUEST_RELAUNCH = True
                break
            if skip_plus7 and seen_only_plus7:
                print("[UPG] Görünür tüm itemler +7 → relaunch.");
                REQUEST_RELAUNCH = True;
                FORCE_PLUS7_ONCE = True;
                return attempts_done
    print(f"[UPG] Basma bitti: {attempts_done}/{limit}");
    return attempts_done


# ================== NPC SONRASI ANVIL ROTASI ==================
def npc_post_purchase_route_to_anvil_and_upgrade(w):
    set_stage("NPC_POSTBUY_ROUTE");
    ensure_ui_closed()
    press_key(SC_A);
    time.sleep(NPC_POSTBUY_FIRST_A_DURATION);
    release_key(SC_A)
    set_stage("NPC_POSTBUY_W_TO_795");
    go_w_to_x(w, NPC_POSTBUY_TARGET_X1, timeout=NPC_POSTBUY_SEEK_TIMEOUT)
    set_stage("NPC_POSTBUY_D_WHILE_W");
    press_key(SC_W);
    press_key(SC_A);
    time.sleep(NPC_POSTBUY_A_WHILE_W_DURATION);
    release_key(SC_A);
    release_key(SC_W)
    set_stage("NPC_POSTBUY_W_TO_814");
    go_w_to_x(w, NPC_POSTBUY_TARGET_X2, timeout=NPC_POSTBUY_SEEK_TIMEOUT)
    set_stage("NPC_POSTBUY_A2");
    press_key(SC_A);
    time.sleep(NPC_POSTBUY_SECOND_A_DURATION);
    release_key(SC_A)
    set_stage("NPC_POSTBUY_W_FINAL");
    press_key(SC_W);
    time.sleep(NPC_POSTBUY_FINAL_W_DURATION);
    release_key(SC_W)
    attempts_done = basma_dongusu(scroll_required="LOW", win=w);
    return attempts_done


# ================== RE-LAUNCH & LOGIN ==================
def safe_press_enter_if_not_ingame(w):
    try:
        if _ingame_by_hpbar_once(w): print("[ENTER] Oyundayız."); return False
    except Exception:
        pass
    press_key(SC_ENTER);
    release_key(SC_ENTER);
    print("[ENTER] Enter basıldı.");
    return True


def _mean_rgb_around(win, rx, ry, size=7):
    x = win.left + rx;
    y = win.top + ry;
    k = size // 2;
    x1 = max(0, x - k);
    y1 = max(0, y - k);
    x2 = x + k + 1;
    y2 = y + k + 1
    img = ImageGrab.grab(bbox=(x1, y1, x2, y2));
    arr = np.array(img)[:, :, :3].reshape(-1, 3).astype(np.float32);
    m = arr.mean(axis=0);
    return float(m[0]), float(m[1]), float(m[2])


def _is_red(rgb, r_min=HP_RED_MIN, delta=HP_RED_DELTA):
    r, g, b = rgb;
    return (r >= r_min) and (r - max(g, b) >= delta)


def _ingame_by_hpbar_once(win):
    rgb1 = _mean_rgb_around(win, HP_POINTS[0][0], HP_POINTS[0][1], 7);
    rgb2 = _mean_rgb_around(win, HP_POINTS[1][0], HP_POINTS[1][1], 7)
    return _is_red(rgb1) and _is_red(rgb2)


def confirm_loading_until_ingame(w, timeout=90.0, poll=0.25, enter_period=3.0, allow_periodic_enter=False):
    set_stage("LOADING_TO_INGAME");
    print("[WAIT] HP bar bekleniyor.")
    t0 = time.time();
    last_enter = 0.0
    while time.time() - t0 < timeout:
        wait_if_paused();
        watchdog_enforce()
        if _kb_pressed('f12'): print("[WAIT] F12 iptal."); return False
        if _ingame_by_hpbar_once(w): print("[WAIT] HP bar görüldü."); ensure_ui_closed(); return True
        if allow_periodic_enter and (time.time() - last_enter >= enter_period): safe_press_enter_if_not_ingame(
            w); last_enter = time.time()
        time.sleep(poll)
    print("[WAIT] Zaman aşımı: HP bar yok.");
    return False


@with_retry("RELAUNCH_LOGIN", attempts=3, delay=2.0)
@crashguard("RELAUNCH_LOGIN")
def relaunch_and_login_to_ingame():
    global TOWN_LOCKED, NEED_STAIRS_REALIGN
    TOWN_LOCKED = False
    NEED_STAIRS_REALIGN = True
    globals()['TOWN_HARD_LOCK'] = False
    _town_log_once('[TOWN] HardLock KAPALI (relaunch başı).')
    _town_log_once("[TOWN] Kilit sıfırlandı (relaunch başı).")
    global BANK_OPEN
    while True:
        if _kb_pressed('f12'): print("[RELAUNCH] F12 iptal."); return None
        w = launch_via_launcher_and_wait()
        if not w: print("[RELAUNCH] KO gelmedi. Yeniden dene."); close_all_game_instances(); time.sleep(2.0); continue
        with key_tempo(0.5):
            set_stage("RELAUNCH_SPLASH_PASS");
            time.sleep(0.5)
            for _ in range(2): time.sleep(1.5); mouse_move(*SPLASH_CLICK_POS); mouse_click("left"); time.sleep(0.5)
            safe_press_enter_if_not_ingame(w);
            print("[RELAUNCH] Splash geçildi.")
            set_stage("RELAUNCH_LOGIN_INPUT");
            time.sleep(0.5);
            perform_login_inputs(w);
            print("[RELAUNCH] Giriş yazıldı.")
            set_stage("RELAUNCH_SERVER_LIST");
            time.sleep(0.8)
            for _ in range(2): mouse_move(*SERVER_OPEN_POS); mouse_click("left"); time.sleep(0.15)
            print("[RELAUNCH] Server listesi açıldı.")
            set_stage("RELAUNCH_SERVER_SELECT");
            time.sleep(1)
            server_xy = _choose_server_xy()
            for _ in range(2): mouse_move(*server_xy); mouse_click("left"); time.sleep(0.15)
            print(f"[RELAUNCH] Server seçildi: {server_xy}")
            set_stage("RELAUNCH_POST_SELECT");
            press_key(SC_ENTER);
            release_key(SC_ENTER);
            time.sleep(1.5)
            ok = try_click_oyun_start_with_retries(w, attempts=5, wait_between=4.0)
            if not ok:
                print("[RELAUNCH] oyun_start.png yok. Kapat→yeniden.")
                try:
                    exit_game_fast(w)
                except Exception:
                    close_all_game_instances()
                time.sleep(2.0);
                continue
            time.sleep(1);
            press_key(SC_ENTER);
            release_key(SC_ENTER);
            time.sleep(1)
            ok = confirm_loading_until_ingame(w, timeout=90.0, poll=0.25, enter_period=3.0, allow_periodic_enter=False)
            if not ok:
                print("[RELAUNCH] HP bar teyidi yok. Kapat→yeniden.")
                try:
                    exit_game_fast(w)
                except Exception:
                    close_all_game_instances()
                time.sleep(2.0);
                continue
        set_stage("RELAUNCH_TOWN_HIDE");
        ensure_ui_closed();
        send_town_command();
        press_key(SC_O);
        release_key(SC_O);
        time.sleep(0.1)
        print("[RELAUNCH] Town + 'O' tamam. Oyundayız.");
        BANK_OPEN = False;
        maybe_autotune(True);
        return w


# ================== BANK_PLUS8 ORKESTRASYONU ==================
@crashguard("BANK_PLUS8")
def run_bank_plus8_cycle(w, bank_is_open: bool = False):
    global MODE
    set_stage("BANK_PLUS8_CYCLE")
    if bank_is_open:
        print("[BANK_PLUS8] Banka açık → devam.")
    else:
        if not move_to_769_and_turn_from_top(w):
            print("[BANK_PLUS8] Banka açılamadı, town & tekrar.");
            send_town_command()
            if not move_to_769_and_turn_from_top(w): print(
                "[BANK_PLUS8] Banka yine açılamadı. Mod iptal."); _set_mode_normal("Banka açılamadı"); return

    # >>> 598'e başarıyla varıldıysa kilidi Y'ye göre AYARLA
    y_now = _read_y_now()
    _set_town_lock_by_y(y_now)
    if TOWN_LOCKED:
        _town_log_once('[TOWN] Kilit aktif (Y=598) — town artık kapalı')
    first = True
    while True:
        wait_if_paused();
        watchdog_enforce()
        if first:
            initial = withdraw_plusN_from_bank_pages(w, 7, max_take=2);
            print(f"[BANK_PLUS8] İlk +7: {initial}/2")
            low_moved = deposit_low_scrolls_from_inventory_to_bank(SCROLL_SWAP_MAX_STACKS)
            mid_taken = withdraw_mid_scrolls_from_bank_to_inventory(SCROLL_SWAP_MAX_STACKS)
            print(f"[BANK_PLUS8] Scroll takası: LOW→BANK={low_moved}, MID→ENV={mid_taken}")
            remaining = max(0, 27 - initial);
            extra = withdraw_plusN_from_bank_pages(w, 7, max_take=remaining) if remaining > 0 else 0
            taken = initial + extra;
            print(f"[BANK_PLUS8] Başlangıç toplam +7: {taken}/27 (ek={extra})");
            first = False
        else:
            low_moved = deposit_low_scrolls_from_inventory_to_bank(SCROLL_SWAP_MAX_STACKS)
            mid_taken = withdraw_mid_scrolls_from_bank_to_inventory(SCROLL_SWAP_MAX_STACKS)
            print(f"[BANK_PLUS8] Scroll takası(döngü): LOW→BANK={low_moved}, MID→ENV={mid_taken}")
            taken = withdraw_plusN_from_bank_pages(w, 7, max_take=27);
            print(f"[BANK_PLUS8] Döngü +7: {taken}/27")
        if taken <= 0:
            print("[BANK_PLUS8] Bankada +7 kalmadı → scroll dönüşümü ve çıkış.")
            mid_back = deposit_mid_scrolls_from_inventory_to_bank(SCROLL_SWAP_MAX_STACKS)
            low_back = withdraw_low_scrolls_from_bank_to_inventory(SCROLL_SWAP_MAX_STACKS)
            print(f"[BANK_PLUS8] Final takas: MID→BANK={mid_back}, LOW→ENV={low_back}");
            _set_mode_normal("Bankada +7 kalmadı")
            return
        ensure_ui_closed();
        exit_game_fast(w);
        w = relaunch_and_login_to_ingame()
        if not w: print("[BANK_PLUS8] Yeniden giriş başarısız (upgrade)."); _set_mode_normal("Relaunch upgrade başarısız"); return
        sx = town_until_valid_x(w);
        ascend_stairs_to_top(w);
        go_to_anvil_from_top(sx)
        attempts = basma_dongusu(attempts_limit=taken, scroll_required="MID", win=w);
        print(f"[BANK_PLUS8] +8 deneme: {attempts}/{taken}")
        exit_game_fast(w);
        w = relaunch_and_login_to_ingame()
        if not w: print("[BANK_PLUS8] Yeniden giriş başarısız (depozit)."); _set_mode_normal("Relaunch depozit başarısız"); return
        town_until_valid_x(w);
        ascend_stairs_to_top(w);
        press_key(SC_I);
        release_key(SC_I);
        time.sleep(0.5)
        plus8 = count_inventory_plusN(w, 8, "INV");
        press_key(SC_I);
        release_key(SC_I);
        time.sleep(0.2)
        if plus8 >= 1:
            if not move_to_769_and_turn_from_top(w):
                print("[BANK_PLUS8] Storage açılamadı; sonraki döngü.")
            else:
                deposit_inventory_plusN_to_bank(w, 8)
        else:
            print("[BANK_PLUS8] Üzerinde +8 yok.")
            if not move_to_769_and_turn_from_top(w): print(
                "[BANK_PLUS8] Banka açılamadı (döngü sonrası). Mod bitiyor."); _set_mode_normal("Depozit banka açılamadı"); return


# ================== BANK_PLUS7 ORKESTRASYONU ==================
@crashguard("BANK_PLUS7")
def run_bank_plus7_mode(w):
    global MODE
    _set_mode_bank_plus7("Başlat")
    while True:
        wait_if_paused();
        watchdog_enforce()
        if _kb_pressed('f12'):
            print("[BANK_PLUS7] F12 alındı, çıkılıyor.")
            _set_mode_normal("F12")
            return False
        town_until_valid_x(w)
        ascend_stairs_to_top(w)
        press_key(SC_I);
        release_key(SC_I);
        time.sleep(0.6)
        plus7_inv = count_inventory_plusN(w, 7, "INV")
        press_key(SC_I);
        release_key(SC_I);
        time.sleep(0.2)
        need_deposit = plus7_inv >= 3
        if not move_to_769_and_turn_from_top(w):
            print("[BANK_PLUS7] Banka açılamadı → town retry")
            send_town_command()
            continue
        if need_deposit:
            deposited = deposit_inventory_plusN_to_bank(w, 7)
            print(f"[BANK_PLUS7] Bankaya bırakılan +7: {deposited}")
        taken = withdraw_plus_range_from_bank_pages(w, 1, 6, max_take=27)
        if taken <= 0:
            print("[BANK_PLUS7] Bankada +1…+6 kalmadı → mod bitiyor.")
            _set_mode_normal("PLUS7 kaynak bitti")
            return True
        ensure_ui_closed();
        exit_game_fast(w);
        w = relaunch_and_login_to_ingame()
        if not w:
            print("[BANK_PLUS7] Yeniden giriş başarısız (upgrade).")
            _set_mode_normal("Relaunch upgrade başarısız")
            return False
        town_until_valid_x(w)
        ascend_stairs_to_top(w)
        try:
            start_x, _ = read_coordinates(w)
        except Exception:
            start_x = None
        go_to_anvil_from_top(start_x)
        attempts_limit = min(int(BASMA_HAKKI), int(taken))
        attempts_done = basma_dongusu(attempts_limit=attempts_limit, scroll_required="MID", win=w, skip_plus8=True)
        print(f"[BANK_PLUS7] +7 deneme: {attempts_done}/{attempts_limit}")
        exit_game_fast(w)
        w = relaunch_and_login_to_ingame()
        if not w:
            print("[BANK_PLUS7] Yeniden giriş başarısız (depozit).")
            _set_mode_normal("Relaunch depozit başarısız")
            return False


# ================== NORMAL ÇALIŞMA DÖNGÜSÜ ==================
@crashguard("WORKFLOW")
def run_stairs_and_workflow(w):
    # global satırı EN BAŞTA olmalı
    global GLOBAL_CYCLE, NEXT_PLUS7_CHECK_AT, MODE, REQUEST_RELAUNCH, FORCE_PLUS7_ONCE, BANK_OPEN, NEED_STAIRS_REALIGN, TOWN_LOCKED
    global PLUS8_RESUME

    set_stage("WORKFLOW_LOOP")
    print(f">>> Akış başlıyor (tur={GLOBAL_CYCLE}, +7_kontrol_turu>={NEXT_PLUS7_CHECK_AT})")

    try:
        while True:
            wait_if_paused();
            watchdog_enforce()
            if _kb_pressed('f12'):
                print("[LOOP] F12 iptal.")
                return (False, False)

            if NEED_STAIRS_REALIGN:
                set_stage("STAIRS_REALIGN_AFTER_RECONNECT")
                TOWN_LOCKED = False
                town_until_valid_x(w)
                ascend_stairs_to_top(w)
                continue

            if keyboard.is_pressed("f") or MODE == "BANK_PLUS8" or PLUS8_RESUME:
                _set_mode_bank_plus8("Klavye/Resume")
                print("[KAMPANYA] +8 modu (F/Resume).")
                if not BANK_OPEN:
                    if not move_to_769_and_turn_from_top(w):
                        print("[KAMPANYA] Banka yok; town & retry.")
                        send_town_command()
                        continue
                run_bank_plus8_cycle(w, bank_is_open=BANK_OPEN)
                print("[KAMPANYA] +8 modu tamam → NORMAL.")
                _set_mode_normal("BANK_PLUS8 döngü tamam")
                continue

            try:
                x, y = read_coordinates(w)
            except Exception:
                x, y = None, None
            if x is None or y is None:
                continue

            if x not in VALID_X:
                print(f"[CHECK] X={x} geçersiz → town.")
                send_town_command()
                continue

            start_x = x
            ascend_stairs_to_top(w)

            press_key(SC_I);
            release_key(SC_I);
            time.sleep(0.6)
            empty_slots = count_empty_slots("INV")

            do_plus7 = FORCE_PLUS7_ONCE or (GLOBAL_CYCLE >= NEXT_PLUS7_CHECK_AT)
            plus7_count = -1
            if do_plus7:
                if FORCE_PLUS7_ONCE:
                    print("[Karar] Bu tur +7 taraması **ZORUNLU**.")
                else:
                    print("[Karar] Bu tur +7 taraması AKTİF.")
                plus7_count = count_inventory_plusN(w, 7, "INV")
                FORCE_PLUS7_ONCE = False
            else:
                print("[Karar] Bu tur +7 taraması PASİF.")

            press_key(SC_I);
            release_key(SC_I);
            time.sleep(0.3)

            if do_plus7 and plus7_count >= 3:
                print("[Karar] Üzerinde ≥3 +7 → STORAGE akışı.")
                if move_to_769_and_turn_from_top(w):
                    deposit_inventory_plusN_to_bank(w, 7)
                    md = after_deposit_check_and_decide_mode(w)
                    if md == "BANK_PLUS8":
                        run_bank_plus8_cycle(w, bank_is_open=True)
                        ensure_ui_closed()
                        return (True, False)
                    elif md == "ABORT":
                        return (False, False)
                    else:
                        ensure_ui_closed()
                        return (True, False)
                else:
                    return (False, False)

            if empty_slots >= EMPTY_SLOT_THRESHOLD:
                print("[Karar] Boş slot ≥ eşik → NPC'den item al.")
                purchased, w = go_to_npc_from_top(w)
                if purchased:
                    NEXT_PLUS7_CHECK_AT = GLOBAL_CYCLE + PLUS7_START_FROM_TURN_AFTER_PURCHASE
                    print(f"[PLAN] NPC alış yapıldı. +7 taraması {NEXT_PLUS7_CHECK_AT}. turdan itibaren.")
                    attempts_done = npc_post_purchase_route_to_anvil_and_upgrade(w)
                    if REQUEST_RELAUNCH:
                        print("[RELAUNCH] Basarken relaunch tetiklendi.")
                        REQUEST_RELAUNCH = False
                        try:
                            exit_game_fast(w)
                        except Exception:
                            pass
                        w2 = relaunch_and_login_to_ingame()
                        if not w2: return (False, False)
                        w = w2
                        continue
                    if attempts_done >= BASMA_HAKKI:
                        print("[TUR] 31 item basıldı → tur tamam.")
                        return (True, False)
                    else:
                        print(f"[TUR] {attempts_done}/{BASMA_HAKKI} basıldı → devam.")
                        continue
                else:
                    continue
            else:
                print("[Karar] Boş slot < eşik → Anvil'e git.")
                go_to_anvil_from_top(start_x)
                attempts_done = basma_dongusu(scroll_required="LOW", win=w)
                if REQUEST_RELAUNCH:
                    print("[RELAUNCH] Basarken relaunch tetiklendi (LOW/+7-only).")
                    REQUEST_RELAUNCH = False
                    try:
                        exit_game_fast(w)
                    except Exception:
                        pass
                    w2 = relaunch_and_login_to_ingame()
                    if not w2: return (False, False)
                    w = w2
                    continue
                if attempts_done >= BASMA_HAKKI:
                    print("[TUR] 31 item basıldı → tur tamam.")
                    return (True, False)
                else:
                    continue
    finally:
        _stop_plus8_wait_notifier()


# =============== Ana ===============
@crashguard("MAIN")
def main():
    global GLOBAL_CYCLE, NEXT_PLUS7_CHECK_AT, MODE, BANK_FULL_FLAG  # <- GLOBAL EN BAŞTA!
    mode = str(globals().get("OPERATION_MODE", OPERATION_MODE)).upper()
    if mode == "ITEM_SATIS":
        run_item_sale_mode()
        return
    if mode == PLUS7_BANK_MODE:
        _set_mode_bank_plus7("Başlangıç")
    _set_dpi_aware();
    _wire_tesseract_portable()
    load_plus7_templates();
    load_plus8_templates();
    load_scroll_templates()
    print(f"[AYAR] +7 taraması NPC alışından {PLUS7_START_FROM_TURN_AFTER_PURCHASE}. tur sonra aktif.")
    print(f"[AYAR] Başlangıç: GLOBAL_CYCLE={GLOBAL_CYCLE}, NEXT_PLUS7_CHECK_AT={NEXT_PLUS7_CHECK_AT}")
    if AUTO_SPEED_PROFILE: _apply_profile("BALANCED"); maybe_autotune(True)
    try:
        while True:
            w = None
            set_stage("BOOT");
            try:
                print(">>> AŞAMA 1: Launcher ile başlat");
                w = launch_via_launcher_and_wait()
                if not w:
                    print("Başlatma başarısız. LAUNCHER_EXE/START koordinatı kontrol.")
                    raise WatchdogTimeout("Oyun penceresi yok.")
                with key_tempo(0.5):
                    set_stage("SPLASH_PASS");
                    time.sleep(0.5)
                    for _ in range(2): time.sleep(1.5); mouse_move(*SPLASH_CLICK_POS); mouse_click("left"); time.sleep(
                        0.5)
                    safe_press_enter_if_not_ingame(w);
                    print(">>> Splash geçildi. Login.")
                    set_stage("LOGIN_INPUT");
                    time.sleep(0.5);
                    perform_login_inputs(w);
                    print("[LOGIN] Kimlik bilgileri girildi.")
                    set_stage("SERVER_LIST");
                    time.sleep(0.8)
                    for _ in range(2): mouse_move(*SERVER_OPEN_POS); mouse_click("left"); time.sleep(0.15)
                    print("[SERVER] Server listesi açıldı.")
                    set_stage("SERVER_SELECT");
                    time.sleep(1)
                    server_xy = _choose_server_xy()
                    for _ in range(2): mouse_move(*server_xy); mouse_click("left"); time.sleep(0.15)
                    print(f"[SERVER] Seçilen server: {server_xy}")
                    set_stage("SERVER_POST_SELECT");
                    press_key(SC_ENTER);
                    release_key(SC_ENTER);
                    time.sleep(1.5)
                    ok = try_click_oyun_start_with_retries(w, attempts=5, wait_between=4.0)
                    if not ok: print("[START] oyun_start.png yok → restart."); raise WatchdogTimeout(
                        "oyun_start.png tıklanamadı.")
                    time.sleep(1);
                    press_key(SC_ENTER);
                    release_key(SC_ENTER);
                    time.sleep(1)
                    ok = confirm_loading_until_ingame(w, timeout=90.0, poll=0.25, enter_period=3.0,
                                                      allow_periodic_enter=False)
                    if not ok: print("[LOAD] Oyuna giriş teyidi yok."); raise WatchdogTimeout("HP bar görünmedi.")
                set_stage("INGAME_TOWN");
                ensure_ui_closed();
                send_town_command();
                _town_log_once("[TOWN] Bir kez town atıldı.")
                press_key(SC_O);
                release_key(SC_O);
                time.sleep(0.1);
                _town_log_once("[TOWN] 'O' basıldı; isimler gizlendi.");
                maybe_autotune(True)
                set_stage("RUN_WORKFLOW");
                if mode == PLUS7_BANK_MODE:
                    run_bank_plus7_mode(w)
                    return
                cycle_done, _purchased = run_stairs_and_workflow(w)
                if cycle_done:
                    set_stage("CYCLE_EXIT_RESTART");
                    print("[CYCLE] Tur tamamlandı → KO kapatılıp baştan.")
                    try:
                        exit_game_fast(w)
                    except Exception as e:
                        print(f"[CYCLE] Çıkış hata: {e}")
                    time.sleep(1.0);
                    GLOBAL_CYCLE += 1;
                    print(f"[CYCLE] Yeni tur: {GLOBAL_CYCLE}. Planlı +7 ≥ {NEXT_PLUS7_CHECK_AT}.");
                    continue
                else:
                    print("[CYCLE] Tamamlanmadan sonlandı (F12 veya hata).")
                    if _kb_pressed('f12'): print("[CYCLE] F12 tespit edildi, makro çıkıyor."); break
                    print("[RESTART] Hata sonrası temiz başlatma...")
                    try:
                        if w is not None:
                            exit_game_fast(w)
                        else:
                            close_all_game_instances()
                    except Exception as e:
                        print(f"[RESTART] Kapatma hata: {e}")
                    time.sleep(2.0);
                    continue
            except WatchdogTimeout as e:
                print(f"[WATCHDOG] {e} → Oyun yeniden başlatılıyor...")
                try:
                    if w is not None:
                        exit_game_fast(w)
                    else:
                        close_all_game_instances()
                except Exception as ee:
                    print(f"[WATCHDOG] Kapatma sırasında hata: {ee}")
                time.sleep(3.0);
                continue
    except GUIAbort:
        print("[MAIN] GUI durdurma isteği alındı; çıkılıyor.")


# ===================== MİKRO ADIM DÜZELTME FONKSİYONLARI (v2) =====================
import random, time, keyboard


def check_and_correct_y(target_y, read_func=None):
    """Y koordinatını 0 sapmayla düzeltir (maks 400 deneme)."""
    global relaunch
    if read_func is None:
        try:
            read_func = read_coord_y
        except NameError:
            print("[MİKRO] read_coord_y bulunamadı.");
            return
    print(f"[MİKRO] Düzeltme başlatıldı (hedef Y={target_y})")
    try:
        current_y = read_func();
        step = 0;
        last_change = time.time()
        while abs(current_y - target_y) != 0:
            if current_y > target_y:
                keyboard.press('s')
            elif current_y < target_y:
                keyboard.press('w')
            time.sleep(random.uniform(0.10, 0.15))
            keyboard.release('s');
            keyboard.release('w')
            time.sleep(0.05)
            new_y = read_func()
            if new_y != current_y: last_change = time.time()
            current_y = new_y;
            step += 1
            if step >= 400:
                print("[MİKRO] 400 deneme başarısız, oyun yeniden başlatılıyor...")
                try:
                    close_game();
                    time.sleep(2);
                    relaunch()
                except Exception as e:
                    print("[MİKRO] relaunch hata:", e)
                return
            if time.time() - last_change > 10:
                print("[MİKRO] 10 sn boyunca koordinat değişmedi, döngü sonlandırıldı.");
                break
        print(f"[MİKRO] Hedef bulundu: Y={current_y}")
    except Exception as e:
        print("[MİKRO] check_and_correct_y hata:", e)


def check_and_correct_x(target_x, read_func=None):
    """X koordinatını 0 sapmayla düzeltir (maks 400 deneme)."""
    global relaunch
    if read_func is None:
        try:
            read_func = read_coord_x
        except NameError:
            print("[MİKRO] read_coord_x bulunamadı.");
            return
    print(f"[MİKRO] Düzeltme başlatıldı (hedef X={target_x})")
    try:
        current_x = read_func();
        step = 0;
        last_change = time.time()
        while abs(current_x - target_x) != 0:
            if current_x > target_x:
                keyboard.press('a')
            elif current_x < target_x:
                keyboard.press('d')
            time.sleep(random.uniform(0.10, 0.15))
            keyboard.release('a');
            keyboard.release('d')
            time.sleep(0.05)
            new_x = read_func()
            if new_x != current_x: last_change = time.time()
            current_x = new_x;
            step += 1
            if step >= 400:
                print("[MİKRO] 400 deneme başarısız, oyun yeniden başlatılıyor...")
                try:
                    close_game();
                    time.sleep(2);
                    relaunch()
                except Exception as e:
                    print("[MİKRO] relaunch hata:", e)
                return
            if time.time() - last_change > 10:
                print("[MİKRO] 10 sn boyunca koordinat değişmedi, döngü sonlandırıldı.");
                break
        print(f"[MİKRO] Hedef bulundu: X={current_x}")
    except Exception as e:
        print("[MİKRO] check_and_correct_x hata:", e)


# ===================== 598→597 MİKRO DÜZELTME (main'den ÖNCE) =====================
import time, random, keyboard


def _read_y_safe():
    try:
        w = bring_game_window_to_front();
        _x, y = read_coordinates(w);
        return y
    except Exception:
        return None


def post_598_to_597():
    """598'e oturduktan sonra 597 bulunana dek S; altına inerse W ile 597'ye toparla."""
    try:
        target = 597;
        step = 0;
        last = time.time()
        y = _read_y_safe()
        if y is None:
            print("[598→597] Y okunamadı, işlem atlandı.");
            return
        print(f"[598→597] Başlatıldı. Şu an Y={y}, hedef={target}")
        while y != target:
            if y is None:
                y = _read_y_safe();
                continue
            if y > target:  # 598,599,... → S ile küçült
                keyboard.press('s');
                time.sleep(random.uniform(PRESS_MIN, PRESS_MAX));
                keyboard.release('s')
            else:  # 596,595,... (fazla iner ise) → W ile büyüt
                keyboard.press('w');
                time.sleep(random.uniform(PRESS_MIN, PRESS_MAX));
                keyboard.release('w')
            time.sleep(0.05)
            y_new = _read_y_safe()
            if y_new != y and y_new is not None: last = time.time()
            y = y_new;
            step += 1
            if step >= MAX_STEPS:
                print("[598→597] %d deneme başarısız, vazgeçildi." % MAX_STEPS);
                return
            if time.time() - last > STUCK_TIMEOUT:
                print("[598→597] %ds değişim yok, güvenlik gereği bırakıldı." % STUCK_TIMEOUT);
                return
        print("[598→597] Tamamlandı: Y=597")
    except Exception as e:
        print("[598→597] Hata:", e)


# ================================================================================

# === FABRIC/LINEN BUY MODE OVERRIDE ===
BUY_MODE = globals().get("BUY_MODE", "LINEN")  # F3=FABRIC, F4=LINEN (varsayılan: LINEN)
# === BUY_MODE PERSISTENCE (AUTO) ===
# NE İŞE YARAR: BUY_MODE'u json'a kaydeder, açılışta geri yükler.
try:
    import json, os, sys


    def _respath(name):
        try:
            base = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
        except Exception:
            base = os.path.dirname(os.path.abspath(__file__))
        return os.path.join(base, name)


    _BUY_CFG = _respath('config_buy_mode.json')
    if 'BUY_MODE' not in globals(): BUY_MODE = 'LINEN'  # emniyetli varsayılan


    def _load_buy_mode(default):
        try:
            with open(_BUY_CFG, 'r', encoding='utf-8') as f:
                d = json.load(f);
                m = d.get('BUY_MODE', default)
            if m in ('FABRIC', 'LINEN'): return m
        except Exception:
            pass
        return default


    def _save_buy_mode(m):
        try:
            with open(_BUY_CFG, 'w', encoding='utf-8') as f:
                json.dump({'BUY_MODE': m}, f, ensure_ascii=False)
        except Exception as e:
            print('[BUY_MODE] yazma uyarı:', e)


    BUY_MODE = _load_buy_mode(BUY_MODE)
    print(f"[BUY_MODE] başlangıç: {BUY_MODE}")
    _OLD__set_buy_mode = globals().get('_set_buy_mode')


    def _set_buy_mode(mode: str):
        global BUY_MODE
        if mode not in ('FABRIC', 'LINEN'): return
        if BUY_MODE != mode:
            BUY_MODE = mode;
            _save_buy_mode(BUY_MODE);
            print(f"[BUY_MODE] -> {BUY_MODE}")
except Exception as e:
    print('[BUY_MODE] persist init uyarı:', e)
FABRIC_STEPS = [((686, 290), 2, "right"), ((736, 290), 2, "right"), ((786, 290), 3, "right"), ((836, 290), 3, "right"),
                ((886, 290), 4, "right")]  # 1. sayfa
LINEN_STEPS = [((687, 237), 2, "right"), ((737, 237), 2, "right"), ((787, 237), 3, "right"), ((837, 237), 3, "right"),
               ((887, 237), 4, "right")]  # 2. sayfa
BUY_TURNS = 2  # döngü sayısı (2 tur = 28 adet)
if "NPC_MENU_PAGE2_POS" not in globals(): NPC_MENU_PAGE2_POS = (919, 540)  # güvenli varsayılan


def _set_buy_mode(mode: str):
    global BUY_MODE
    if mode in ("FABRIC", "LINEN") and BUY_MODE != mode:
        BUY_MODE = mode;
        print(f"[BUY_MODE] -> {BUY_MODE}")  # mod bildirimi


def _check_hotkeys_for_buy_mode():
    try:
        import keyboard
        if keyboard.is_pressed("f3"):
            _set_buy_mode("FABRIC")
        elif keyboard.is_pressed("f4"):
            _set_buy_mode("LINEN")
    except Exception:
        pass


def wait_if_paused():  # mevcut işleve override (aynı iş + F3/F4 dinleme)
    told = False
    abort_fn = globals().get("_abort_requested")
    AbortExc = globals().get("GUIAbort", GUIAbort)

    def _ensure_not_aborted():
        if abort_fn and abort_fn():
            raise AbortExc("GUI durdurma isteği")

    try:
        is_caps = globals().get("is_capslock_on")
        wdog = globals().get("watchdog_enforce")
        if not is_caps or not wdog:
            _ensure_not_aborted()
            return True
        while is_caps():
            _ensure_not_aborted()
            if not told:
                print("[PAUSE] CapsLock AÇIK. Devam için kapat.")
                told = True
            _check_hotkeys_for_buy_mode()
            time.sleep(0.1)
            wdog()
        _check_hotkeys_for_buy_mode()
        _ensure_not_aborted()
    except AbortExc:
        raise
    except Exception:
        _ensure_not_aborted()
    return True


def go_to_npc_from_top(w):  # moda göre sayfa seçimi
    set_stage("GO_TO_NPC");
    ensure_ui_closed()
    press_key(SC_A);
    time.sleep(TURN_LEFT_SEC);
    release_key(SC_A)
    press_key(SC_W);
    time.sleep(NPC_GIDIS_SURESI);
    release_key(SC_W)
    try:
        _ = go_w_to_x(w, TARGET_NPC_X, timeout=NPC_SEEK_TIMEOUT)
    except Exception:
        pass
    time.sleep(0.1)
    press_key(SC_B);
    release_key(SC_B);
    time.sleep(0.15)
    mouse_move(*NPC_CONTEXT_RIGHTCLICK_POS);
    mouse_click("right");
    time.sleep(0.2)
    ok = wait_and_click_template(w, NPC_OPEN_TEXT_TEMPLATE_PATH, threshold=NPC_OPEN_MATCH_THRESHOLD,
                                 timeout=NPC_OPEN_FIND_TIMEOUT, scales=NPC_OPEN_SCALES)
    if not ok:
        print("[TIMEOUT] npc_acma.png bulunamadı")
        if globals().get("ON_TEMPLATE_TIMEOUT_RESTART", True):
            try:
                exit_game_fast(w)
            except Exception as e:
                print(f"[TIMEOUT] exit_game_fast hata: {e}")
            w2 = relaunch_and_login_to_ingame();
            return (False, w2 if w2 else w)
        return (False, w)
    if BUY_MODE == "LINEN":
        mouse_move(*NPC_MENU_PAGE2_POS);
        mouse_click("left");
        time.sleep(0.15)  # LINEN → 2. sayfa
    else:
        time.sleep(0.10)  # FABRIC → 1. sayfa
    onay_ok, w_after = confirm_npc_shop_or_relogin(w)
    if not onay_ok: return (False, w_after if w_after is not None else w)
    purchased = buy_items_from_npc();
    return (purchased, w)


def buy_items_from_npc():  # 2 tur * (2,2,3,3,4) = 28 item
    set_stage("NPC_BUY_28")
    steps = FABRIC_STEPS if BUY_MODE == "FABRIC" else LINEN_STEPS
    for _ in range(BUY_TURNS):
        for (x, y), clicks, btn in steps:
            for __ in range(clicks):
                wait_if_paused();
                watchdog_enforce()
                try:
                    if _kb_pressed("f12"): return False
                except Exception:
                    pass
                mouse_move(x, y);
                mouse_click(btn);
                time.sleep(0.08)
    print(f"[NPC] Moda göre alım tamamlandı (mode={BUY_MODE}) → 28 item.")
    return True


def buy_items_from_npc():
    set_stage("NPC_BUY_28")
    steps = FABRIC_STEPS if BUY_MODE == "FABRIC" else LINEN_STEPS
    tail = [(912, 498), (729, 584)]
    for _ in range(BUY_TURNS):
        # 1) 5 ürün: 2,2,3,3,4 sağ tık
        for (x, y), clicks, btn in steps:
            for __ in range(clicks):
                wait_if_paused();
                watchdog_enforce()
                try:
                    if _kb_pressed("f12"): return False
                except Exception:
                    pass
                mouse_move(x, y);
                mouse_click(btn);
                time.sleep(0.08)
        # 2) TUR SONU: Satın Al + Onay (sol tıklar)
        for (tx, ty) in tail:
            wait_if_paused();
            watchdog_enforce()
            mouse_move(tx, ty);
            mouse_click("left");
            time.sleep(0.1)
    print(f"[NPC] Moda göre alım tamamlandı (mode={BUY_MODE}) → 28 item.")
    return True


# ====================== KALICI AYAR ŞEMASI / GUI DESTEK ======================
_NUMBER_RE = re.compile(r"-?\d+(?:\.\d+)?")


def _cfg_default(name: str, fallback: Any) -> Any:
    return copy.deepcopy(globals().get(name, fallback))


def _split_str_list(raw: Any) -> List[str]:
    return [p.strip() for p in re.split(r"[|,;\n]+", str(raw or "")) if p.strip()]


def _parse_number_list(raw: Any) -> List[float]:
    return [float(x) for x in _NUMBER_RE.findall(str(raw or ""))]


def _ensure_float_list(value: Any) -> List[float]:
    if isinstance(value, (list, tuple, set)):
        seq = sorted(value) if isinstance(value, set) else list(value)
    else:
        seq = _parse_number_list(value)
    return [float(x) for x in seq]


def _ensure_int_list(value: Any) -> List[int]:
    if isinstance(value, (list, tuple, set)):
        seq = sorted(value) if isinstance(value, set) else list(value)
    else:
        seq = _parse_number_list(value)
    return [int(round(float(x))) for x in seq]


def _ensure_str_list(value: Any) -> List[str]:
    if isinstance(value, (list, tuple, set)):
        seq = list(value)
    else:
        seq = _split_str_list(value)
    out = []
    for item in seq:
        s = str(item).strip()
        if s:
            out.append(s)
    return out


def _ensure_int_pair(value: Any) -> Tuple[int, int]:
    nums = _ensure_int_list(value)
    if len(nums) < 2:
        raise ValueError("En az iki sayı gerekir")
    return nums[0], nums[1]


def _ensure_int_quad(value: Any) -> Tuple[int, int, int, int]:
    nums = _ensure_int_list(value)
    if len(nums) < 4:
        raise ValueError("Dört sayı gerekir")
    return nums[0], nums[1], nums[2], nums[3]


def _ensure_pair_list(value: Any) -> List[Tuple[int, int]]:
    if isinstance(value, (list, tuple, set)):
        iterable: Iterable[Any] = list(value)
    else:
        iterable = _split_str_list(value)
    result: List[Tuple[int, int]] = []
    for item in iterable:
        result.append(_ensure_int_pair(item))
    return result


def _ensure_regions(value: Any) -> Tuple[str, ...]:
    return tuple(_ensure_str_list(value))


def _ensure_int_set(value: Any) -> set:
    return set(_ensure_int_list(value))


@dataclass
class ConfigField:
    key: str
    label: str
    category: str
    field_type: str = "str"
    default: Any = None
    description: str = ""
    choices: Optional[Sequence[str]] = None
    secret: bool = False
    runtime_only: bool = False
    width: int = 0
    apply: Optional[Callable[[Any], Any]] = None


CONFIG_FIELDS: List[ConfigField] = [
    ConfigField("tus_hizi", "Tuş hızı (sn)", "Hız & Tıklama", "float",
                _cfg_default("tus_hizi", 0.050), "Makro genel tuş basım süresi."),
    ConfigField("mouse_hizi", "Mouse hızı (sn)", "Hız & Tıklama", "float",
                _cfg_default("mouse_hizi", 0.100), "Mouse tıklama aralığı."),
    ConfigField("jitter_px", "Jitter (px)", "Hız & Tıklama", "int",
                _cfg_default("jitter_px", 0), "Mouse konumuna eklenen rastgele piksel sapması."),
    ConfigField("VALID_X_LEFT", "Geçerli X (sol)", "Koordinat Grupları", "list_int",
                _cfg_default("VALID_X_LEFT", {811, 812, 813}),
                "Merdiven sol X değerleri.", apply=_ensure_int_set),
    ConfigField("VALID_X_RIGHT", "Geçerli X (sağ)", "Koordinat Grupları", "list_int",
                _cfg_default("VALID_X_RIGHT", {819, 820, 821}),
                "Merdiven sağ X değerleri.", apply=_ensure_int_set),
    ConfigField("STOP_Y", "Y duruş noktaları", "Koordinat Grupları", "list_int",
                _cfg_default("STOP_Y", {598}), "Merdiven üstü Y değerleri.", apply=_ensure_int_set),
    ConfigField("SCROLL_POS", "Scroll pozisyonu (x,y)", "Koordinat Grupları", "int_pair",
                _cfg_default("SCROLL_POS", (671, 459)),
                "Scroll satın alma konumu.", apply=_ensure_int_pair),
    ConfigField("UPGRADE_BTN_POS", "Upgrade butonu (x,y)", "Koordinat Grupları", "int_pair",
                _cfg_default("UPGRADE_BTN_POS", (747, 358)),
                "Upgrade panelindeki buton koordinatı.", apply=_ensure_int_pair),
    ConfigField("CONFIRM_BTN_POS", "Onay butonu (x,y)", "Koordinat Grupları", "int_pair",
                _cfg_default("CONFIRM_BTN_POS", (737, 479)),
                "Anvil onay butonu koordinatı.", apply=_ensure_int_pair),
    ConfigField("SCROLL_VENDOR_MID_POS", "Scroll orta pos (x,y)", "Koordinat Grupları", "int_pair",
                _cfg_default("SCROLL_VENDOR_MID_POS", (747, 358)),
                "Scroll paneli orta noktası.", apply=_ensure_int_pair),
    ConfigField("NPC_CONTEXT_RIGHTCLICK_POS", "NPC sağ tık (x,y)", "Koordinat Grupları", "int_pair",
                _cfg_default("NPC_CONTEXT_RIGHTCLICK_POS", (535, 520)),
                "NPC menüsünü açan sağ tık noktası.", apply=_ensure_int_pair),
    ConfigField("NPC_MENU_PAGE2_POS", "NPC sayfa 2 (x,y)", "Koordinat Grupları", "int_pair",
                _cfg_default("NPC_MENU_PAGE2_POS", (968, 328)),
                "Keten için ikinci sayfa koordinatı.", apply=_ensure_int_pair),
    ConfigField("BANK_NEXT_PAGE_POS", "Banka ileri (x,y)", "Koordinat Grupları", "int_pair",
                _cfg_default("BANK_NEXT_PAGE_POS", (731, 389)),
                "Banka ileri sayfa butonu.", apply=_ensure_int_pair),
    ConfigField("BANK_PREV_PAGE_POS", "Banka geri (x,y)", "Koordinat Grupları", "int_pair",
                _cfg_default("BANK_PREV_PAGE_POS", (668, 389)),
                "Banka geri sayfa butonu.", apply=_ensure_int_pair),
    ConfigField("GAME_START_SCALES", "Launcher Start ölçekleri", "Ölçek Listeleri", "list_float",
                _cfg_default("GAME_START_SCALES", (0.85, 0.9, 1.0, 1.1, 1.2)),
                "Launcher Start butonu arama ölçekleri.", apply=lambda v: list(_ensure_float_list(v))),
    ConfigField("TEMPLATE_EXTRA_CLICK_POS", "Ek tık (x,y)", "Koordinat Grupları", "int_pair",
                _cfg_default("TEMPLATE_EXTRA_CLICK_POS", (931, 602)),
                "Template sonrası ekstra tıklama noktası.", apply=_ensure_int_pair),
    ConfigField("LAUNCHER_START_CLICK_POS", "Launcher Start (x,y)", "Koordinat Grupları", "int_pair",
                _cfg_default("LAUNCHER_START_CLICK_POS", (974, 726)),
                "Launcher üzerindeki Start butonu koordinatı.", apply=_ensure_int_pair),
    ConfigField("LOGIN_USERNAME_CLICK_POS", "Kullanıcı adı (x,y)", "Sunucu / Login", "int_pair",
                _cfg_default("LOGIN_USERNAME_CLICK_POS", (579, 326)),
                "Launcher kullanıcı adı alanı koordinatı.", apply=_ensure_int_pair),
    ConfigField("LOGIN_PASSWORD_CLICK_POS", "Şifre alanı (x,y)", "Sunucu / Login", "int_pair",
                _cfg_default("LOGIN_PASSWORD_CLICK_POS", (579, 378)),
                "Launcher şifre alanı koordinatı.", apply=_ensure_int_pair),
    ConfigField("SERVER_OPEN_POS", "Sunucu listesi (x,y)", "Sunucu / Login", "int_pair",
                _cfg_default("SERVER_OPEN_POS", (455, 231)),
                "Sunucu seçim açılır listesinin konumu.", apply=_ensure_int_pair),
    ConfigField("SERVER_CHOICES", "Sunucu seçimleri", "Sunucu / Login", "list_pairs",
                _cfg_default("SERVER_CHOICES", [(671, 254), (676, 281)]),
                "Sunucu listesindeki seçim koordinatları.", apply=_ensure_pair_list),
    ConfigField("HP_POINTS", "HP ölçüm noktaları", "HP & Town", "list_pairs",
                _cfg_default("HP_POINTS", [(185, 68), (218, 74)]),
                "HP barının kontrol edildiği koordinatlar.", apply=_ensure_pair_list),
    ConfigField("TOWN_CLICK_POS", "Town tık (x,y)", "HP & Town", "int_pair",
                _cfg_default("TOWN_CLICK_POS", (775, 775)),
                "Town komutunun tıklama noktası.", apply=_ensure_int_pair),
    ConfigField("SPLASH_CLICK_POS", "Splash tık (x,y)", "HP & Town", "int_pair",
                _cfg_default("SPLASH_CLICK_POS", (700, 550)),
                "Splash ekranını geçmek için tıklanan koordinat.", apply=_ensure_int_pair),
    ConfigField("TOOLTIP_FALLBACK_BBOX", "Tooltip bbox (x1,y1,x2,y2)", "HP & Town", "int_quad",
                _cfg_default("TOOLTIP_FALLBACK_BBOX", (290, 95, 1007, 662)),
                "Tooltip OCR fallback alanı.", apply=_ensure_int_quad),
    ConfigField("NPC_OPEN_SCALES", "NPC açma ölçekleri", "Ölçek Listeleri", "list_float",
                _cfg_default("NPC_OPEN_SCALES", (0.85, 0.9, 1.0, 1.1, 1.2)),
                "NPC açma şablonu ölçekleri.", apply=lambda v: list(_ensure_float_list(v))),
    ConfigField("USE_STORAGE_TEMPLATE_PATHS", "Storage şablonları", "Şablon Listeleri", "list_str",
                _cfg_default("USE_STORAGE_TEMPLATE_PATHS", ["use_storage.png", "use_stroge.png"]),
                "Depo açma şablon dosyaları.", apply=_ensure_str_list, width=28),
    ConfigField("USE_STORAGE_SCALES", "Storage ölçekleri", "Ölçek Listeleri", "list_float",
                _cfg_default("USE_STORAGE_SCALES", (0.85, 0.9, 1.0, 1.1, 1.2)),
                "Storage şablonu ölçekleri.", apply=lambda v: list(_ensure_float_list(v))),
    ConfigField("PLUS7_TEMPLATE_PATHS", "+7 şablonları", "Şablon Listeleri", "list_str",
                _cfg_default("PLUS7_TEMPLATE_PATHS", ["plus7.png", "plus7_var2.png"]),
                "+7 algılama şablon dosyaları.", apply=_ensure_str_list, width=28),
    ConfigField("PLUS8_TEMPLATE_PATHS", "+8 şablonları", "Şablon Listeleri", "list_str",
                _cfg_default("PLUS8_TEMPLATE_PATHS", ["plus8.png"]),
                "+8 algılama şablon dosyaları.", apply=_ensure_str_list, width=28),
    ConfigField("PLUS8_WAIT_MESSAGE", "+8 item basma mesajı", "Satın Alma", "str",
                _cfg_default("PLUS8_WAIT_MESSAGE", ""),
                "+8 bekleme modundayken Telegram'a gönderilecek mesaj."),
    ConfigField("PLUS8_WAIT_MESSAGE_INTERVAL_MIN", "+8 item basma mesaj gönderme süresi (dk)", "Satın Alma", "float",
                _cfg_default("PLUS8_WAIT_MESSAGE_INTERVAL_MIN", 10.0),
                "+8 bekleme modundayken kaç dakikada bir mesaj atılacağı."),
    ConfigField("SCROLL_LOW_TEMPLATE_PATHS", "Low scroll şablonları", "Şablon Listeleri", "list_str",
                _cfg_default("SCROLL_LOW_TEMPLATE_PATHS", ["scroll_low.png", "scroll_low2.png"]),
                "Low scroll şablon dosyaları.", apply=_ensure_str_list, width=28),
    ConfigField("SCROLL_MID_TEMPLATE_PATHS", "Mid scroll şablonları", "Şablon Listeleri", "list_str",
                _cfg_default("SCROLL_MID_TEMPLATE_PATHS", ["scroll_mid.png", "scroll_mid2.png"]),
                "Mid scroll şablon dosyaları.", apply=_ensure_str_list, width=28),
    ConfigField("SCROLL_SCALES", "Scroll ölçekleri", "Ölçek Listeleri", "list_float",
                _cfg_default("SCROLL_SCALES", (0.80, 0.90, 1.00, 1.10, 1.20)),
                "Scroll şablon tarama ölçekleri.", apply=lambda v: list(_ensure_float_list(v))),
    ConfigField("SCROLL_SEARCH_REGIONS", "Scroll bölgeleri", "Ölçek Listeleri", "list_str",
                _cfg_default("SCROLL_SEARCH_REGIONS", ("UPG", "INV")),
                "Scroll araması yapılacak bölgeler.", apply=_ensure_regions),
    ConfigField("PAZAR_YENILEME_BEKELEME_MIN", "Pazar yenileme bekleme min", "Item Satış", "float",
                _cfg_default("PAZAR_YENILEME_BEKELEME_MIN", 120.0),
                "Pazar yenileme öncesi minimum bekleme süresi."),
    ConfigField("PAZAR_YENILEME_BEKELEME_MAX", "Pazar yenileme bekleme maks", "Item Satış", "float",
                _cfg_default("PAZAR_YENILEME_BEKELEME_MAX", 120.0),
                "Pazar yenileme öncesi maksimum bekleme süresi."),
    ConfigField("auto_market_refresh_enabled", "Pazar yenileme aktif", "Item Satış", "bool",
                _cfg_default("auto_market_refresh_enabled", False),
                "Zamanlı otomatik pazar yenilemeyi aç/kapat."),
    ConfigField("auto_market_refresh_interval_hours", "Yenileme aralığı (saat)", "Item Satış", "float",
                _cfg_default("auto_market_refresh_interval_hours", 3.0),
                "Otomatik pazar yenileme sıklığı (saat cinsinden)."),
    ConfigField("ITEM_SALE_EXIT_DELAY_MIN", "Banka çıkış bekleme min", "Item Satış", "float",
                _cfg_default("ITEM_SALE_EXIT_DELAY_MIN", 0.0),
                "Banka eşiği yakalandığında çıkış öncesi minimum bekleme."),
    ConfigField("ITEM_SALE_EXIT_DELAY_MAX", "Banka çıkış bekleme maks", "Item Satış", "float",
                _cfg_default("ITEM_SALE_EXIT_DELAY_MAX", 0.0),
                "Banka eşiği yakalandığında çıkış öncesi maksimum bekleme."),
    ConfigField("ITEM_SALE_SLOT_SCAN_INTERVAL", "Slot tarama süresi", "Item Satış", "float",
                _cfg_default("ITEM_SALE_SLOT_SCAN_INTERVAL", 10.0),
                "Envanter boş slot tarama aralığı (sn)."),
    ConfigField("ITEM_SALE_BANK_NOTIFY", "Banka boşsa Telegram", "Item Satış", "int",
                _cfg_default("ITEM_SALE_BANK_NOTIFY", 1),
                "Banka boşaldığında Telegram bildirimi gönder.",
                apply=lambda v: bool(int(float(v)))),
    ConfigField("ITEM_SALE_BANK_EMPTY_MESSAGE", "Banka boş mesajı", "Item Satış", "str",
                _cfg_default("ITEM_SALE_BANK_EMPTY_MESSAGE", "Bankada item kalmadı"),
                "Banka boş kalınca gönderilecek Telegram metni."),
    ConfigField("TELEGRAM_TOKEN", "Telegram Token", "Item Satış", "str",
                _cfg_default("TELEGRAM_TOKEN", ""),
                "Telegram bot token değeri."),
    ConfigField("TELEGRAM_CHAT_ID", "Telegram Chat ID", "Item Satış", "str",
                _cfg_default("TELEGRAM_CHAT_ID", ""),
                "Telegram sohbet ID'si."),
    ConfigField("KRALLIK_CLICK_X", "Krallık tıklama X", "Item Satış", "int",
                _cfg_default("KRALLIK_CLICK_X", 0),
                "Krallık yazısı için tıklanacak X koordinatı."),
    ConfigField("KRALLIK_CLICK_Y", "Krallık tıklama Y", "Item Satış", "int",
                _cfg_default("KRALLIK_CLICK_Y", 0),
                "Krallık yazısı için tıklanacak Y koordinatı."),
    ConfigField("KRALLIK_TIKLAMA_ARALIGI", "Krallık tıklama aralığı", "Item Satış", "float",
                _cfg_default("KRALLIK_TIKLAMA_ARALIGI", 0.0),
                "Krallık yazısı tıklama periyodu (sn)."),
    ConfigField("KRALLIK_TIKLAMA_SURESI", "Krallık tıklama süresi", "Item Satış", "float",
                _cfg_default("KRALLIK_TIKLAMA_SURESI", 0.05),
                "Krallık tıklamasının basılı kalma süresi (sn)."),
]


def _iter_config_fields() -> Iterable[ConfigField]:
    """Yield only valid ConfigField objects, skipping stray patches."""
    for field in CONFIG_FIELDS:
        if isinstance(field, ConfigField):
            yield field


CONFIG_FIELD_MAP: Dict[str, ConfigField] = {f.key: f for f in _iter_config_fields()}
CONFIG_CATEGORY_ORDER: Tuple[str, ...] = tuple(
    dict.fromkeys(f.category for f in _iter_config_fields())
)


def _serialize_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _serialize_value(v) for k, v in value.items()}
    if isinstance(value, tuple):
        return [_serialize_value(v) for v in value]
    if isinstance(value, list):
        return [_serialize_value(v) for v in value]
    if isinstance(value, set):
        return [_serialize_value(v) for v in sorted(value)]
    return value


def _format_field_value(field: ConfigField, value: Any) -> str:
    if field.field_type == "int_pair":
        x, y = _ensure_int_pair(value)
        return f"{x}, {y}"
    if field.field_type == "int_quad":
        a, b, c, d = _ensure_int_quad(value)
        return f"{a}, {b}, {c}, {d}"
    if field.field_type == "list_pairs":
        pairs = _ensure_pair_list(value)
        return " | ".join(f"{px},{py}" for px, py in pairs)
    if field.field_type == "list_float":
        vals = _ensure_float_list(value)
        return ", ".join(f"{v:g}" for v in vals)
    if field.field_type == "list_int":
        vals = _ensure_int_list(value)
        return ", ".join(str(v) for v in vals)
    if field.field_type == "list_str":
        vals = _ensure_str_list(value)
        return ", ".join(vals)
    return str(value)


def _parse_field_value(field: ConfigField, raw: str) -> Any:
    txt = str(raw or "").strip()
    if field.field_type == "float":
        return float(txt)
    if field.field_type == "int":
        return int(float(txt))
    if field.field_type == "str":
        return txt
    if field.field_type == "int_pair":
        nums = _parse_number_list(txt)
        if len(nums) < 2:
            raise ValueError("En az iki sayı girin")
        return [int(round(nums[0])), int(round(nums[1]))]
    if field.field_type == "int_quad":
        nums = _parse_number_list(txt)
        if len(nums) < 4:
            raise ValueError("Dört sayı girin")
        return [int(round(nums[i])) for i in range(4)]
    if field.field_type == "list_float":
        nums = _parse_number_list(txt)
        if not nums:
            raise ValueError("Liste boş olamaz")
        return [float(x) for x in nums]
    if field.field_type == "list_int":
        nums = _parse_number_list(txt)
        if not nums:
            raise ValueError("Liste boş olamaz")
        return [int(round(x)) for x in nums]
    if field.field_type == "list_str":
        return _split_str_list(txt)
    if field.field_type == "list_pairs":
        if not txt:
            return []
        chunks = [c for c in re.split(r"[;|\n]+", txt) if c.strip()]
        pairs: List[List[int]] = []
        for chunk in chunks:
            nums = _parse_number_list(chunk)
            if len(nums) < 2:
                raise ValueError("Koordinat çifti için en az iki sayı girin")
            pairs.append([int(round(nums[0])), int(round(nums[1]))])
        return pairs
    raise ValueError(f"Desteklenmeyen alan tipi: {field.field_type}")


def _schema_defaults(base_defaults: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    defaults = copy.deepcopy(base_defaults or {})
    for field in _iter_config_fields():
        if field.key not in defaults:
            defaults[field.key] = _serialize_value(field.default)
    return defaults


def _serialize_config(cfg: Dict[str, Any]) -> Dict[str, Any]:
    return {k: _serialize_value(v) for k, v in cfg.items()}


def apply_config_values(cfg: Dict[str, Any]) -> None:
    g = globals()
    for field in _iter_config_fields():
        if field.runtime_only:
            continue
        if field.key not in cfg:
            continue
        value = cfg[field.key]
        try:
            applied = field.apply(value) if field.apply else value
        except Exception as exc:
            print(f"[CFG] {field.key} uygulanamadı: {exc}")
            continue
        g[field.key] = applied
    try:
        g['VALID_X'] = set(g.get('VALID_X_LEFT', set())) | set(g.get('VALID_X_RIGHT', set()))
    except Exception:
        pass
    try:
        if not isinstance(g.get('STOP_Y'), set):
            g['STOP_Y'] = set(g.get('STOP_Y', []))
    except Exception:
        pass
    try:
        if isinstance(g.get('SCROLL_SEARCH_REGIONS'), list):
            g['SCROLL_SEARCH_REGIONS'] = tuple(g['SCROLL_SEARCH_REGIONS'])
    except Exception:
        pass


# >>> MEGA_IMPROVE_BEGIN_V1
# === 2..8 İyileştirmeleri (config, OCR, state, rapor, scroll fix, buy wrapper) ===
import os, json, csv, time, traceback
from functools import wraps

_BASE_CONFIG_DEFAULTS = json.loads(
    r'''{"timeouts": {"move_timeout": 20.0, "ocr_timeout": 3.0, "npc_buy_timeout": 12.0}, "ocr": {"tess_config": "--psm7 -c tessedit_char_whitelist=0123456789", "rois": [[10, 10, 120, 40], [10, 40, 120, 70]]}, "logging": {"runs_csv": "runs.csv", "log_dir": "logs"}, "special_deltas": {}}''')


# --- Config yükle/kaydet ---
def load_config(path=None, defaults=None):
    if path is None:
        path = _MERDIVEN_CFG_PATH()
    if defaults is None:
        defaults = _schema_defaults(_BASE_CONFIG_DEFAULTS)
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        if not os.path.exists(path):
            with open(path, 'w', encoding='utf-8') as f: json.dump(defaults, f, indent=2, ensure_ascii=False)
            return defaults
        with open(path, 'r', encoding='utf-8') as f:
            cfg = json.load(f)

        def _merge(a, b):
            for k, v in b.items():
                if k not in a:
                    a[k] = v
                elif isinstance(v, dict) and isinstance(a.get(k), dict):
                    _merge(a[k], v)

        _merge(cfg, defaults)
        return cfg
    except Exception as e:
        print('[PATCH][config] load error:', e)
        return defaults


def save_config(cfg, path=None):
    if path is None:
        path = _MERDIVEN_CFG_PATH()
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(_serialize_config(cfg), f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        print('[PATCH][config] save error:', e)
        return False


# --- Retry yardımcı ---
def retry_on_exception(retries=2, delay=0.5, allowed_exceptions=(Exception,), backoff=1.5):
    def deco(fn):
        @wraps(fn)
        def wrapper(*a, **k):
            r = retries;
            d = delay
            while True:
                try:
                    return fn(*a, **k)
                except allowed_exceptions as e:
                    if isinstance(e, GUIAbort):
                        raise
                    if r <= 0: raise
                    time.sleep(d);
                    d *= backoff;
                    r -= 1

        return wrapper

    return deco


# --- Sağlam OCR ---
def robust_ocr(pil_image, rois=None, pytesseract=None, tess_conf=None):
    try:
        if pytesseract is None:
            try:
                import pytesseract as _pt
                pytesseract = _pt
            except Exception:
                return ('', {})
        if tess_conf is None:
            tess_conf = _GLOBAL_PATCH_CFG.get('ocr', {}).get('tess_config', '')
        if rois is None:
            rois = _GLOBAL_PATCH_CFG.get('ocr', {}).get('rois', [])
        votes = {};
        texts = []
        try:
            from PIL import Image
        except Exception:
            pass
        for r in rois:
            try:
                x, y, w, h = [int(v) for v in r]
                crop = pil_image.crop((x, y, x + w, y + h))
                txt = (pytesseract.image_to_string(crop, config=tess_conf) or '').strip()
                texts.append(txt);
                votes[txt] = votes.get(txt, 0) + 1
            except Exception:
                continue
        if not texts: return ('', {})
        best = max(votes.items(), key=lambda kv: (kv[1], 1 if kv[0] else 0))
        return (best[0], votes)
    except Exception:
        return ('', {})


# --- Basit durum makinesi ---
class MacroStateMachine:
    def __init__(self, initial='IDLE'):
        self.state = initial;
        self.history = []

    def transition(self, new_state, note=None):
        self.history.append((time.time(), self.state, new_state, note));
        self.state = new_state

    def get_state(self): return self.state

    def dump_history(self): return list(self.history)


# --- Rapor/CSV ---
def _ensure_dir(d):
    try:
        os.makedirs(d, exist_ok=True)
    except Exception:
        pass


def report_run(summary, csvpath=None):
    try:
        if csvpath is None:
            csvpath = _GLOBAL_PATCH_CFG.get('logging', {}).get('runs_csv', 'runs.csv')
        hdr = ['timestamp', 'duration_s', 'cycles', 'plus7', 'plus8', 'notes']
        exist = os.path.exists(csvpath)
        with open(csvpath, 'a', newline='', encoding='utf-8') as f:
            w = csv.DictWriter(f, fieldnames=hdr)
            if not exist: w.writeheader()
            w.writerow({k: summary.get(k, '') for k in hdr})
        return True
    except Exception as e:
        print('[PATCH][report] error:', e);
        return False


# --- SCROLL list düzeltme ---
def _fix_scroll_lists():
    try:
        g = globals()
        g['SCROLL_MID_TEMPLATE_PATHS'] = g.get('SCROLL_MID_TEMPLATE_PATHS', ['scroll_mid.png', 'scroll_mid2.png'])
        return True
    except Exception as e:
        print('[PATCH][scroll] fix error:', e);
        return False


# --- buy wrapper ---
def _wrap_buy_items():
    try:
        g = globals();
        orig = g.get('buy_items_from_npc', None)
        if orig is None:
            def _stub(*a, **k):
                print('[PATCH][buy] buy_items_from_npc bulunamadı (stub).');
                return False

            g['buy_items_from_npc'] = _stub;
            return True

        @retry_on_exception(retries=2, delay=0.5)
        def _wrapped(*a, **k):
            try:
                if 'set_stage' in globals(): globals()['set_stage']('NPC_BUY_WRAPPED')
            except Exception:
                pass
            return orig(*a, **k)

        g['buy_items_from_npc'] = _wrapped;
        return True
    except Exception as e:
        print('[PATCH][buy] wrap error:', e);
        return False


# --- Başlat: config/load, dir, fixes ---
try:
    _GLOBAL_PATCH_CFG = load_config()
except Exception:
    _GLOBAL_PATCH_CFG = {}
try:
    apply_config_values(_GLOBAL_PATCH_CFG)
except Exception:
    pass
try:
    _ld = _GLOBAL_PATCH_CFG.get('logging', {}).get('log_dir', 'logs');
    _ensure_dir(_ld)
except Exception:
    pass
try:
    _fix_scroll_lists()
except Exception:
    pass
try:
    if 'STATE_MACHINE' not in globals(): STATE_MACHINE = MacroStateMachine('IDLE')
except Exception:
    pass
try:
    _wrap_buy_items()
except Exception:
    pass

# --- main() sarmalama ---
if 'main' in globals() and callable(globals()['main']):
    _orig_main = globals()['main']


    def _patched_main(*a, **k):
        t0 = time.time()
        try:
            globals()['_GLOBAL_PATCH_CFG'] = load_config()
        except Exception:
            pass
        try:
            STATE_MACHINE.transition('RUNNING', 'main_enter')
        except Exception:
            pass
        try:
            res = _orig_main(*a, **k)
        except Exception as e:
            try:
                import traceback;
                traceback.print_exc()
            except Exception:
                pass
            try:
                STATE_MACHINE.transition('CRASH', 'exception')
            except Exception:
                pass
            raise
        finally:
            dur = time.time() - t0
            try:
                summary = {'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
                           'duration_s': round(dur, 1),
                           'cycles': globals().get('GLOBAL_CYCLE', ''),
                           'plus7': globals().get('PLUS7_COUNT', ''),
                           'plus8': globals().get('PLUS8_COUNT', ''),
                           'notes': ''}
                report_run(summary, csvpath=_GLOBAL_PATCH_CFG.get('logging', {}).get('runs_csv'))
            except Exception:
                pass
            try:
                STATE_MACHINE.transition('IDLE', 'main_exit')
            except Exception:
                pass
        return res


    globals()['main'] = _patched_main

# dışa aç
_GLOBAL_PATCH_UTILS = {'load_config': load_config, 'save_config': save_config, 'robust_ocr': robust_ocr,
                       'STATE_MACHINE': STATE_MACHINE, 'report_run': report_run,
                       'wrap_buy_items': _wrap_buy_items, 'fix_scroll_lists': _fix_scroll_lists}

# <<< MEGA_IMPROVE_END_V1
# ========================== [ENTEGRE GUI BLOĞU] ==========================
# Bu blok YAMAİCİN.PY ile otomatik eklendi. Kısa, stabil, tek dosya EXE uyumlu.
# Başlat/Durdur/Kaydet/Hepsini Kapat + "Gelişmiş" sekmesiyle TÜM büyük harfli değişkenleri düzenler.
_TR = {
    'ANVIL_CONFIRM_WAIT_MS': 'anvil onay bekleme (ms)',
    'ANVIL_HOVER_CLEAR_SEC': 'anvil hover temizleme (sn)',
    'ANVIL_HOVER_GUARD': 'anvil hover koruması',
    'ANVIL_WALK_TIME': 'anvil’e yürüme süresi',
    'AUTO_BANK_PLUS8': '+8 sonrası otomatik bankaya git',
    'AUTO_BANK_PLUS8_DELAY': '+8 sonrası bekleme (sn)',
    'BANK_FULL_FLAG': 'banka dolu işareti',
    'BANK_INV_LEFT': 'env sol',
    'BANK_INV_TOP': 'env üst',
    'BANK_INV_RIGHT': 'env sağ',
    'BANK_INV_BOTTOM': 'env alt',
    'BANK_OPEN': 'banka aç',
    'BANK_PAGE_CLICK_DELAY': 'banka sayfa tık bekleme (sn)',
    'BANK_PANEL_TOP': 'banka panel üst',
    'BANK_PANEL_RIGHT': 'banka panel sağ',
    'BANK_PANEL_BOTTOM': 'banka panel alt',
    'BANK_PANEL_LEFT': 'banka panel sol',
    'BANK_PANEL_ROWS': 'banka satır',
    'BANK_PANEL_COLS': 'banka sütun',
    'AUTO_SPEED_PROFILE': 'otomatik hız profili',
    'AUTO_TUNE_INTERVAL': 'otomatik ayar aralığı (sn)',
    'SPEED_PROFILE': 'hız profili',
    'PRESS_MIN': 'mikro adım min (sn)',
    'PRESS_MAX': 'mikro adım max (sn)',
    'PRE_BRAKE_DELTA': 'ön fren delta',
    'CRASH_DIR': 'çökme kayıt klasörü',
    'LOG_DIR': 'log klasörü',
    'GLOBAL_CYCLE': 'global tur sayacı',
    'MODE': 'mod',
    'MAX_STEPS': 'maks. adım sayısı',
    'WATCHDOG_TIMEOUT': 'watchdog zaman aşımı (sn)',
    'REQUEST_RELAUNCH': 'zaman aşımında relaunch',
    'ON_TEMPLATE_TIMEOUT_RESTART': 'şablon gecikirse yeniden başlat',
    'DEBUG_SAVE': 'debug görselleri kaydet',
    'GUI_AUTO_OPEN_SPEED': 'başlangıçta hız sekmesini aç',
    'TOOLTIP_GRAB_WITH_MSS': 'tooltip yakalamada mss kullan',
    'TOOLTIP_OFFSET_Y': 'tooltip Y ofseti',
    'TOOLTIP_ROI_W': 'tooltip ROI genişlik',
    'TOOLTIP_ROI_H': 'tooltip ROI yükseklik',
    'INV_LEFT': 'env sol',
    'INV_TOP': 'env üst',
    'INV_RIGHT': 'env sağ',
    'INV_BOTTOM': 'env alt',
    'SLOT_ROWS': 'slot satır',
    'SLOT_COLS': 'slot sütun',
    'UPG_INV_LEFT': 'upg sol',
    'UPG_INV_TOP': 'upg üst',
    'UPG_INV_RIGHT': 'upg sağ',
    'UPG_INV_BOTTOM': 'upg alt',
    'UPG_STEP_DELAY': 'upgrade adım bekleme (sn)',
    'UPG_TUS_HIZI': 'upgrade tuş hızı (sn)',
    'UPG_MOUSE_HIZI': 'upgrade mouse hızı (sn)',
    'UPG_ROI_STALE_MS': 'upgrade ROI bayat (ms)',
    'UPG_USE_FAST_MOUSE': 'upgrade hızlı mouse',
    'UPG_CONFIRM_WAIT_MS': 'upgrade onay bekleme (ms)',
    'EMPTY_SLOT_TEMPLATE_PATH': 'boş slot şablon dosyası',
    'EMPTY_SLOT_MATCH_THRESHOLD': 'boş slot şablon eşiği',
    'FALLBACK_MEAN_THRESHOLD': 'boş slot parlaklık eşiği',
    'FALLBACK_EDGE_DENSITY_THRESHOLD': 'boş slot kenar yoğunluğu eşiği',
    'EMPTY_SLOT_THRESHOLD': 'boş slot karar eşiği (adet)',
    'ENABLE_YAMA_SLOT_CACHE': 'slot önbellek etkin',
    'MAX_CACHE_SIZE_PER_SNAPSHOT': 'snapshot başına önbellek (px)',
    'ROI_STALE_MS': 'koordinat ROI bayat (ms)',
    'BUY_MODE': 'satın alma modu',
    'BUY_TURNS': 'alış tur sayısı',
    'NPC_BUY_TURN_COUNT': 'NPC alış tur sayısı',
    'NPC_OPEN_FIND_TIMEOUT': 'NPC açma yazısı arama süresi (sn)',
    'NPC_OPEN_MATCH_THRESHOLD': 'NPC açma yazısı eşik',
    'NPC_OPEN_TEXT_TEMPLATE_PATH': 'NPC açma yazısı şablonu',
    'NPC_CONFIRM_MATCH_THRESHOLD': 'NPC onay eşik',
    'NPC_CONFIRM_TEMPLATE_PATH': 'NPC onay şablonu',
    'NPC_SEEK_TIMEOUT': 'NPC arama zaman aşımı (sn)',
    'NPC_GIDIS_SURESI': 'NPC’ye yürüme süresi (sn)',
    'NPC_POSTBUY_FIRST_A_DURATION': 'alış sonrası 1. A basma (sn)',
    'NPC_POSTBUY_SECOND_A_DURATION': 'alış sonrası 2. A basma (sn)',
    'NPC_POSTBUY_A_WHILE_W_DURATION': 'alış sonrası A + W (sn)',
    'NPC_POSTBUY_FINAL_W_DURATION': 'alış sonrası düz W (sn)',
    'NPC_POSTBUY_TARGET_X1': 'alış sonrası hedef X1',
    'NPC_POSTBUY_TARGET_X2': 'alış sonrası hedef X2',
    'BASMA_HAKKI': '+8 deneme hakkı',
    'PLUS7_START_FROM_TURN_AFTER_PURCHASE': '+7 taraması kaçıncı turdan sonra',
    'PLUSN_FAST_MODE': '+N hızlı mod',
    'PLUSN_HOVER_SAMPLES': 'hover örnek sayısı',
    'PLUSN_USE_OCR_FALLBACK': '+N OCR yedeği',
    'PLUSN_WAIT_BETWEEN': '+N arası bekleme (sn)',
    'FORCE_PLUS7_ONCE': 'bir kez +7 zorla dene',
    'PREC_Y598_DBLCLICK': '598Y çift tık',
    'PREC_Y598_CLICK_COUNT': '598Y tık sayısı',
    'PREC_Y598_CLICK_DELAY': '598Y tık aralığı (sn)',
    'PREC_Y598_TOWN_HARDLOCK': '598Y town hardlock',
    'TARGET_NPC_X': 'hedef NPC X',
    'X_TOLERANCE': 'X tolerans (px)',
    'X_BAND_CONSEC': 'X bant arka arkaya isabet',
    'X_TOL_TIMEOUT': 'X tolerans zaman aşımı (sn)',
    'X_TOL_READ_DELAY': 'X okuma gecikmesi (sn)',
    'Y_SEEK_TIMEOUT': 'Y arama zaman aşımı (sn)',
    'TARGET_STABLE_HITS': 'hedef sabit okuma sayısı',
    'TARGET_Y_AFTER_TURN': 'dönüş sonrası hedef Y',
    'STAIRS_TOP_Y': 'merdiven tepe Y',
    'STAIRS_TOP_S_BACKOFF_PULSES': 'tepe geri S nabız',
    'STAIRS_TOP_S_BACKOFF_DURATION': 'tepe geri S süre (sn)',
    'TOWN_LOCKED': 'town kilidi',
    'TOWN_HARD_LOCK': 'town hard kilit',
    'TOWN_MIN_INTERVAL_SEC': 'town min aralık (sn)',
    'TOWN_WAIT': 'town bekleme (sn)',
    'WINDOW_TITLE_KEYWORD': 'pencere başlık anahtar',
    'WINDOW_APPEAR_TIMEOUT': 'pencere görünme zaman aşımı (sn)',
    'GAME_START_TEMPLATE_PATH': "launch 'Start' şablonu", 'GAME_START_MATCH_THRESHOLD': 'Start şablon eşiği',
    'GAME_START_FIND_TIMEOUT': 'Start arama zaman aşımı (sn)',
    'LAUNCHER_EXE': 'Launcher yolu',
    'SC_A': 'scan A',
    'SC_D': 'scan D',
    'SC_W': 'scan W',
    'SC_S': 'scan S',
    'SC_I': 'scan I',
    'SC_O': 'scan O',
    'SC_TAB': 'scan TAB',
    'SC_ESC': 'scan ESC',
    'SC_ENTER': 'scan ENTER',
    'KEYEVENTF_SCANCODE': 'DI scancode bayrak',
    'KEYEVENTF_KEYUP': 'DI keyup bayrak',
    'MOUSEEVENTF_LEFTDOWN': 'mouse left down',
    'MOUSEEVENTF_LEFTUP': 'mouse left up',
    'MOUSEEVENTF_RIGHTDOWN': 'mouse right down',
    'MOUSEEVENTF_RIGHTUP': 'mouse right up',
    'VK_CAPITAL': 'vk CapsLock',
    'VK_CONTROL': 'vk Ctrl',
    'VK_V': 'vk V',
    'TH32CS_SNAPPROCESS': 'proc snapshot bayrak',
    'GMEM_MOVEABLE': 'gmem moveable',
    'CF_UNICODETEXT': 'pano unicode formatı',
    'MICRO_PULSE_DURATION': 'mikro nabız süre (sn)',
    'MICRO_READ_DELAY': 'mikro okuma gecikmesi (sn)',
    'LOGIN_USERNAME': 'kullanıcı adı',
    'LOGIN_PASSWORD': 'şifre',
    'ITEMS_DEPLETED_FLAG': 'item bitti işareti',
    'HP_RED_MIN': 'HP kırmızı min',
    'HP_RED_DELTA': 'HP kırmızı delta',
    'PLUS7_TEMPLATE_TIMEOUT': '+7 şablon zaman aşımı',
    'PLUS8_TEMPLATE_TIMEOUT': '+8 şablon zaman aşımı',
    'PLUS8_WAIT_MESSAGE': '+8 bekleme mesajı',
    'PLUS8_WAIT_MESSAGE_INTERVAL_MIN': '+8 bekleme mesaj aralığı (dk)'
}

# === TR yardım sözlüğü ve Tooltip ===
# === TR yardım sözlüğü ve Tooltip ===
# Linter-dostu: önce (varsa) mevcutu al, sonra yeni Türkçe açıklamaları ekle/güncelle.
_TR_HELP = dict(globals().get('_TR_HELP', {}))
_TR_HELP.update({
    # ↓↓↓ Aşağıya sende zaten bulunan tüm maddeleri, olduğu gibi bırak ↓↓↓
    'ANVIL_CONFIRM_WAIT_MS': 'Anvil onay penceresini bekleme süresi (ms). Çok düşükse onay kaçabilir.',
    'ANVIL_HOVER_CLEAR_SEC': 'Anvil üstünde bekledikten sonra hover temizleme süresi.',
    'ANVIL_HOVER_GUARD': 'Yanlış hover birikmesini önleyen koruma.',
    "ANVIL_WALK_TIME": "Tepe noktasından anvil'e yürüme süresi.",
    'AUTO_BANK_PLUS8': '+8 sonrası otomatik bankaya gidilir.',
    'AUTO_BANK_PLUS8_DELAY': '+8 sonrası bekleme süresi (sn).',
    'BANK_OPEN': 'Banka penceresini otomatik aç.',
    'BANK_PAGE_CLICK_DELAY': 'Banka sayfa tıklamaları arası bekleme (sn).',
    'BANK_PANEL_ROWS': 'Banka paneli satır sayısı.',
    'BANK_PANEL_COLS': 'Banka paneli sütun sayısı.',
    'BANK_INV_LEFT': 'Envanter sol koordinatı (banka ekranında).',
    'BANK_INV_TOP': 'Envanter üst koordinatı (banka ekranında).',
    'BANK_INV_RIGHT': 'Envanter sağ koordinatı (banka ekranında).',
    'BANK_INV_BOTTOM': 'Envanter alt koordinatı (banka ekranında).',
    'SPEED_PROFILE': 'Hız profili (FAST/DENGELİ/SAFE).',
    'AUTO_SPEED_PROFILE': 'Profilin otomatik seçimi.',
    'AUTO_TUNE_INTERVAL': 'Oto-profilleme periyodu (sn).',
    'PRESS_MIN': 'A/D mikro adım basışının minimum süresi (sn).',
    'PRESS_MAX': 'A/D mikro adım basışının maksimum süresi (sn).',
    'PRE_BRAKE_DELTA': 'Hedefe yaklaşırken ön fren düzeltmesi (px).',
    'ROI_STALE_MS': 'Koordinat ROI tazeleme aralığı (ms).',
    'UPG_ROI_STALE_MS': 'Upgrade sırasında ROI tazeleme (ms).',
    'EMPTY_SLOT_TEMPLATE_PATH': 'Boş slot şablon dosyası.',
    'EMPTY_SLOT_MATCH_THRESHOLD': 'Boş slot şablon eşik değeri.',
    'FALLBACK_MEAN_THRESHOLD': 'Boş slot parlaklık eşiği.',
    'FALLBACK_EDGE_DENSITY_THRESHOLD': 'Boş slot kenar yoğunluğu eşiği.',
    "EMPTY_SLOT_THRESHOLD": "Boş slot sayısı ≥ bu değer ise 'çoğunlukla boş' kabul edilir.",
    'ENABLE_YAMA_SLOT_CACHE': 'Boş/dolu sonuçlarını önbelleğe al.',
    'MAX_CACHE_SIZE_PER_SNAPSHOT': 'Tek yakalamada izinli maksimum önbellek pikseli.',
    'TOOLTIP_GRAB_WITH_MSS': 'Tooltip için mss kullan (genelde daha stabil).',
    'TOOLTIP_OFFSET_Y': 'Tooltip kırpma ofseti (Y).',
    'TOOLTIP_ROI_W': 'Tooltip ROI genişliği.',
    'TOOLTIP_ROI_H': 'Tooltip ROI yüksekliği.',
    'PLUS8_WAIT_MESSAGE': '+8 bekleme modunda gönderilecek Telegram mesajı.',
    'PLUS8_WAIT_MESSAGE_INTERVAL_MIN': '+8 bekleme modunda mesaj tekrar aralığı (dakika).',
    # … sende olan diğer anahtarlar aynı şekilde devam edecek …
})

_ADV_CATEGORY_RULES = (
    ("Oyuna Giriş", dict(
        names=(
            'LOGIN_USERNAME',
            'LOGIN_PASSWORD',
            'LOGIN_USERNAME_CLICK_POS',
            'LOGIN_PASSWORD_CLICK_POS',
        ),
        prefixes=(
            'LOGIN_',
            'SERVER_',
            'SPLASH_',
        ),
    )),
    ("Launcher", dict(
        names=(
            'WINDOW_TITLE_KEYWORD',
            'WINDOW_APPEAR_TIMEOUT',
            'GAME_START_TEMPLATE_PATH',
            'GAME_START_MATCH_THRESHOLD',
            'GAME_START_FIND_TIMEOUT',
            'GAME_START_SCALES',
            'TEMPLATE_EXTRA_CLICK_POS',
            'REQUEST_RELAUNCH',
        ),
        prefixes=(
            'WINDOW_',
            'GAME_START_',
            'LAUNCHER_',
            'TEMPLATE_',
        ),
    )),
    ("Anvil", dict(
        prefixes=(
            'ANVIL_',
        ),
    )),
    ("NPC/598", dict(
        names=(
            'BUY_MODE',
            'BUY_TURNS',
            'FABRIC_STEPS',
            'LINEN_STEPS',
            'NPC_GIDIS_SURESI',
            'NPC_SEEK_TIMEOUT',
            'NPC_POSTBUY_FIRST_A_DURATION',
            'NPC_POSTBUY_SECOND_A_DURATION',
            'NPC_POSTBUY_A_WHILE_W_DURATION',
            'NPC_POSTBUY_FINAL_W_DURATION',
            'NPC_POSTBUY_TARGET_X1',
            'NPC_POSTBUY_TARGET_X2',
            'NPC_POSTBUY_SEEK_TIMEOUT',
            'NPC_MENU_PAGE2_POS',
        ),
        prefixes=(
            'NPC_',
            'BUY_',
            'USE_STORAGE',
            'FABRIC_',
            'LINEN_',
        ),
    )),
    ("Scroll", dict(
        names=(
            'SCROLL_ALIM_ADET',
            'SCROLL_MID_ALIM_ADET',
        ),
        prefixes=(
            'SCROLL_',
        ),
    )),
    ("Banka", dict(
        names=(
            'AUTO_BANK_PLUS8',
            'AUTO_BANK_PLUS8_DELAY',
            'BANK_OPEN',
            'BANK_PAGE_CLICK_DELAY',
            'BANK_PANEL_ROWS',
            'BANK_PANEL_COLS',
            'BANK_INV_LEFT',
            'BANK_INV_TOP',
            'BANK_INV_RIGHT',
            'BANK_INV_BOTTOM',
            'BANK_FULL_FLAG',
        ),
        prefixes=(
            'AUTO_BANK_',
            'BANK_',
            'INV_',
            'SLOT_',
        ),
    )),
    ("598 Takip", dict(
        names=(
            'TARGET_NPC_X',
            'TARGET_STABLE_HITS',
            'TARGET_Y_AFTER_TURN',
            'STAIRS_TOP_Y',
            'X_TOLERANCE',
            'X_BAND_CONSEC',
            'X_TOL_TIMEOUT',
            'X_TOL_READ_DELAY',
            'Y_SEEK_TIMEOUT',
        ),
        prefixes=(
            'TARGET_',
            'STAIRS_',
            'VALID_',
            'TURN_',
            'X_',
            'Y_',
            'PREC_',
        ),
    )),
    ("Town", dict(
        names=(
            'TOWN_CLICK_POS',
            'TOWN_WAIT',
            'TOWN_MIN_INTERVAL_SEC',
            'TOWN_LOCKED',
            'TOWN_HARD_LOCK',
        ),
        prefixes=(
            'TOWN_',
        ),
    )),
    ("Hız", dict(
        names=(
            'SPEED_PROFILE',
            'AUTO_SPEED_PROFILE',
            'AUTO_TUNE_INTERVAL',
            'PRESS_MIN',
            'PRESS_MAX',
            'PRE_BRAKE_DELTA',
            'MAX_STEPS',
            'STUCK_TIMEOUT',
        ),
        prefixes=(
            'AUTO_SPEED_',
            'AUTO_TUNE_',
            'SPEED_',
            'PRESS_',
            'MICRO_',
            'PRE_BRAKE_',
        ),
    )),
    ("Upgrade", dict(
        prefixes=(
            'UPGRADE_',
            'UPG_',
            'CONFIRM_',
            'YAMA_QC_',
        ),
    )),
    ("OCR/ROI", dict(
        names=(
            'ROI_STALE_MS',
            'UPG_ROI_STALE_MS',
            'EMPTY_SLOT_TEMPLATE_PATH',
            'EMPTY_SLOT_MATCH_THRESHOLD',
            'FALLBACK_MEAN_THRESHOLD',
            'FALLBACK_EDGE_DENSITY_THRESHOLD',
            'EMPTY_SLOT_THRESHOLD',
            'ENABLE_YAMA_SLOT_CACHE',
            'MAX_CACHE_SIZE_PER_SNAPSHOT',
            'TOOLTIP_GRAB_WITH_MSS',
            'TOOLTIP_OFFSET_Y',
            'TOOLTIP_ROI_W',
            'TOOLTIP_ROI_H',
        ),
        prefixes=(
            'HOVER_WAIT_',
            'TOOLTIP_',
            'ROI_',
            'EMPTY_',
            'FALLBACK_',
        ),
    )),
    ('+7/+8', dict(
        names=(
            'FORCE_PLUS7_ONCE',
            'BASMA_HAKKI',
            'WRAP_SLOTS',
        ),
        prefixes=(
            'PLUS7_',
            'PLUS8_',
            'PLUSN_',
            'WRAP_',
            'YAMA_QC_',
        ),
    )),
    ("Günlükleme", dict(
        prefixes=(
            'LOG_',
            'CRASH_',
        ),
    )),
    ("Genel İzleme", dict(
        names=(
            'HP_POTION_THRESHOLD',
            'HP_POTION_TARGET',
            'HP_LOW_SLEEP',
            'GLOBAL_CYCLE',
            'GLOBAL_LOOP_SLEEP',
            'NEXT_PLUS7_CHECK_AT',
            'MODE',
        ),
        prefixes=(
            'HP_',
            'GLOBAL_',
        ),
    )),
    ("Otomasyon", dict(
        names=(
            'AUTO_LOGIN',
            'AUTO_RELAUNCH',
            'AUTO_TOWN',
            'AUTO_EXIT_ON_EMPTY',
            'AUTO_SCROLL',
            'AUTO_BANK',
            'AUTO_SMART_TOWN',
            'AUTO_REPAIR',
            'WATCHDOG_TIMEOUT',
            'WATCHDOG_RELAUNCH_WAIT',
            'F_WAIT_AFTER_LOGIN',
            'F_WAIT_AFTER_FAIL',
            'GUI_AUTO_OPEN_SPEED',
            'DEBUG_SAVE',
            'ON_TEMPLATE_TIMEOUT_RESTART',
            'ITEMS_DEPLETED_FLAG',
        ),
        prefixes=(
            'AUTO_',
            'WATCHDOG_',
            'F_WAIT_',
            'GUI_',
            'DEBUG_',
        ),
    )),
    ("Girdi/WinAPI", dict(
        prefixes=(
            'SC_',
            'VK_',
            'KEYEVENTF_',
            'MOUSEEVENTF_',
            'TH32CS_',
            'CF_',
            'GMEM_',
        ),
    )),
)


def _build_adv_grouping():
    base = dict(globals().get('_ADV_GROUP', {}))
    prefix_rules = list(globals().get('_ADV_PREFIX_GROUPS', ()))
    order = list(globals().get('_ADV_GROUP_ORDER', ()))
    seen_prefixes = {p for p, _ in prefix_rules}

    for category, rule in _ADV_CATEGORY_RULES:
        if category not in order:
            order.append(category)
        for name in rule.get('names', ()):  # type: ignore[arg-type]
            base.setdefault(name, category)
        for prefix in rule.get('prefixes', ()):  # type: ignore[arg-type]
            if prefix not in seen_prefixes:
                prefix_rules.append((prefix, category))
                seen_prefixes.add(prefix)

    if 'Genel' not in order:
        order.append('Genel')

    return base, tuple(order), tuple(prefix_rules)


_ADV_GROUP, _ADV_GROUP_ORDER, _ADV_PREFIX_GROUPS = _build_adv_grouping()


def _norm_txt(s: str) -> str:
    try:
        return str(s).casefold()
    except:
        return str(s).lower()


def _adv_group_of(name: str) -> str:
    grp = _ADV_GROUP.get(name)
    if grp:
        return grp
    for prefix, fallback in _ADV_PREFIX_GROUPS:
        if name.startswith(prefix):
            return fallback
    return 'Genel'


class _Tooltip:
    # Basit hover tooltip (arka plan işlevsel; gerekirse messagebox fallback kullanılabilir)
    def __init__(self, widget, text):
        self.widget = widget;
        self.text = text;
        self.win = None
        widget.bind("<Enter>", self._show);
        widget.bind("<Leave>", self._hide)

    def _show(self, e=None):
        import tkinter as tk
        if self.win: return
        x = self.widget.winfo_rootx() + 20;
        y = self.widget.winfo_rooty() + 20
        self.win = tk.Toplevel(self.widget);
        self.win.wm_overrideredirect(True)
        try:
            self.win.attributes("-topmost", True)
        except:
            pass
        lbl = tk.Label(self.win, text=self.text, justify="left", relief="solid", borderwidth=1, padx=6, pady=4,
                       bg="#ffffe0")
        lbl.pack()
        self.win.wm_geometry(f"+{x}+{y}")

    def _hide(self, e=None):
        if self.win:
            try:
                self.win.destroy()
            except:
                pass
            self.win = None


# --- TR sözlük fallback'leri (lint uyarısı susturur, var olanı bozmaz) ---
try:
    _TR
except NameError:
    _TR = {}
try:
    _TR_HELP
except NameError:
    _TR_HELP = {}
try:
    _ADV_GROUP
except NameError:
    _ADV_GROUP = {}


# --- /fallback ---

def _tr_name(n):
    t = _TR.get(n);
    return f"{n} ({t})" if t else n


def _MERDIVEN_RUN_GUI():
    import sys, json, threading
    try:
        import tkinter as tk
        from tkinter import ttk
    except Exception as e:
        print("[GUI] Tkinter yok/başlatılamadı:", e)
        return False
    m = sys.modules[__name__]  # ayrı import yok; aynı dosya

    class _GUI:
        def __init__(self, root):
            self.root = root;
            root.title("Merdiven GUI");
            root.geometry("1020x680")
            self.stage = tk.StringVar(value="Hazır");
            self.stage_log = []
            # ---- GUI değişkenleri (üstte dursun, ayarlanabilir) ----
            self.v = {
                "username": tk.StringVar(value=getattr(m, "LOGIN_USERNAME", "")),
                "password": tk.StringVar(value=getattr(m, "LOGIN_PASSWORD", "")),
                "operation_mode": tk.StringVar(value=str(getattr(m, "OPERATION_MODE", "ITEM_BASMA"))),
                "item_basma_server": tk.StringVar(value=str(getattr(m, "ITEM_BASMA_SERVER", "Server1"))),
                "plus8_wait_message": tk.StringVar(value=str(getattr(m, "PLUS8_WAIT_MESSAGE", ""))),
                "plus8_wait_interval": tk.DoubleVar(value=float(getattr(m, "PLUS8_WAIT_MESSAGE_INTERVAL_MIN", 10.0))),
                "buy_mode": tk.StringVar(value=getattr(m, "BUY_MODE", "LINEN")),
                "buy_turns": tk.IntVar(value=int(getattr(m, "BUY_TURNS", 2))),
                "scroll_low": tk.IntVar(value=int(getattr(m, "SCROLL_ALIM_ADET", 0))),
                "scroll_mid": tk.IntVar(value=int(getattr(m, "SCROLL_MID_ALIM_ADET", 0))),
                "basma_hakki": tk.IntVar(value=int(getattr(m, "BASMA_HAKKI", 31))),
                "speed_profile": tk.StringVar(value=str(getattr(m, "SPEED_PROFILE", "BALANCED"))),
                "press_min": tk.DoubleVar(value=float(getattr(m, "PRESS_MIN", 0.02))),
                "press_max": tk.DoubleVar(value=float(getattr(m, "PRESS_MAX", 0.06))),
                "sale_price_text": tk.StringVar(value=str(getattr(m, "ITEM_SALE_PRICE_TEXT", ITEM_SALE_PRICE_TEXT))),
                "sale_threshold_1": tk.IntVar(value=int(getattr(m, "PAZAR_ESIK_1", PAZAR_ESIK_1))),
                "sale_threshold_2": tk.IntVar(value=int(getattr(m, "PAZAR_ESIK_2", PAZAR_ESIK_2))),
                "sale_threshold_3": tk.IntVar(value=int(getattr(m, "PAZAR_ESIK_3", PAZAR_ESIK_3))),
                "sale_refresh_min": tk.DoubleVar(
                    value=float(getattr(m, "PAZAR_YENILEME_BEKELEME_MIN", PAZAR_YENILEME_BEKELEME_MIN))),
                "sale_refresh_max": tk.DoubleVar(
                    value=float(getattr(m, "PAZAR_YENILEME_BEKELEME_MAX", PAZAR_YENILEME_BEKELEME_MAX))),
                "sale_initial_wait": tk.DoubleVar(
                    value=float(getattr(m, "PAZAR_ILK_BEKELEME_SURESI", PAZAR_ILK_BEKELEME_SURESI))),
                "sale_click_902_count": tk.IntVar(value=int(getattr(m, "CLICK_902_135_ADET", CLICK_902_135_ADET))),
                "sale_click_902_speed": tk.DoubleVar(value=float(getattr(m, "CLICK_902_135_HIZ", CLICK_902_135_HIZ))),
                "sale_click_899_count": tk.IntVar(value=int(getattr(m, "CLICK_899_399_ADET", CLICK_899_399_ADET))),
                "sale_click_899_speed": tk.DoubleVar(value=float(getattr(m, "CLICK_899_399_HIZ", CLICK_899_399_HIZ))),
                "auto_market_refresh_enabled": tk.BooleanVar(
                    value=bool(getattr(m, "auto_market_refresh_enabled", AUTO_MARKET_REFRESH_ENABLED))),
                "auto_market_refresh_interval_hours": tk.DoubleVar(
                    value=float(getattr(m, "auto_market_refresh_interval_hours",
                                        AUTO_MARKET_REFRESH_INTERVAL_HOURS))),
                "sale_bank_threshold": tk.IntVar(
                    value=int(getattr(m, "BANKAYA_GIT_BOS_SLOT_ESIGI", BANKAYA_GIT_BOS_SLOT_ESIGI))),
                "sale_bank_withdraw": tk.IntVar(
                    value=int(getattr(m, "ITEM_SALE_BANK_WITHDRAW_COUNT", ITEM_SALE_BANK_WITHDRAW_COUNT))),
                "sale_park_x": tk.IntVar(value=int(getattr(m, "PAZAR_PARK_X", PAZAR_PARK_X))),
                "sale_slot_interval": tk.DoubleVar(
                    value=float(getattr(m, "ITEM_SALE_SLOT_SCAN_INTERVAL", ITEM_SALE_SLOT_SCAN_INTERVAL))),
                "sale_exit_delay_min": tk.DoubleVar(
                    value=float(getattr(m, "ITEM_SALE_EXIT_DELAY_MIN", ITEM_SALE_EXIT_DELAY_MIN))),
                "sale_exit_delay_max": tk.DoubleVar(
                    value=float(getattr(m, "ITEM_SALE_EXIT_DELAY_MAX", ITEM_SALE_EXIT_DELAY_MAX))),
                "sale_bank_notify": tk.BooleanVar(
                    value=bool(getattr(m, "ITEM_SALE_BANK_NOTIFY", ITEM_SALE_BANK_NOTIFY))),
                "sale_bank_message": tk.StringVar(
                    value=str(getattr(m, "ITEM_SALE_BANK_EMPTY_MESSAGE", ITEM_SALE_BANK_EMPTY_MESSAGE))),
                "krallik_click_x": tk.IntVar(value=int(getattr(m, "KRALLIK_CLICK_X", KRALLIK_CLICK_X))),
                "krallik_click_y": tk.IntVar(value=int(getattr(m, "KRALLIK_CLICK_Y", KRALLIK_CLICK_Y))),
                "krallik_click_interval": tk.DoubleVar(
                    value=float(getattr(m, "KRALLIK_TIKLAMA_ARALIGI", KRALLIK_TIKLAMA_ARALIGI))),
                "krallik_click_hold": tk.DoubleVar(
                    value=float(getattr(m, "KRALLIK_TIKLAMA_SURESI", KRALLIK_TIKLAMA_SURESI))),
                "telegram_token": tk.StringVar(value=str(getattr(m, "TELEGRAM_TOKEN", ""))),
                "telegram_chat_id": tk.StringVar(value=str(getattr(m, "TELEGRAM_CHAT_ID", ""))),
            }
            dm = getattr(m, "_SPEED_PRE_BRAKE", {"FAST": 3, "BALANCED": 2, "SAFE": 1})
            self.v["brake_fast"] = tk.IntVar(value=int(dm.get("FAST", 3)))
            self.v["brake_bal"] = tk.IntVar(value=int(dm.get("BALANCED", 2)))
            self.v["brake_safe"] = tk.IntVar(value=int(dm.get("SAFE", 1)))
            self.sale_slot_var = tk.StringVar(value=str(getattr(m, "ITEM_SALE_LAST_SLOT_COUNT", "-")))
            self.adv_rows = []
            self._build();
            self._load_json();
            self._hook_stage();
            try:
                m._GUI_UPDATE_SALE_SLOT = self._update_sale_slot
            except Exception:
                pass
            self._tick()
            self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        # ---- basit olay/bildirim ----
        def _msg(self, s):
            print("[GUI]", s)

        def _open_krallik(self, *_):
            url = str(getattr(m, "KRALLIK_URL", KRALLIK_URL) or "")
            if not url:
                return
            try:
                webbrowser.open_new_tab(url)
                self._msg(f"[GUI] Krallık bağlantısı açıldı: {url}")
            except Exception as exc:
                self._msg(f"[GUI] Krallık bağlantısı açılamadı: {exc}")

        def _update_sale_slot(self, value):
            try:
                val = int(value)
            except Exception:
                val = value

            def _apply():
                try:
                    self.sale_slot_var.set(str(val))
                except Exception:
                    pass

            self.root.after(0, _apply)

        def _on_close(self):
            try:
                if getattr(m, "_GUI_UPDATE_SALE_SLOT", None) is self._update_sale_slot:
                    m._GUI_UPDATE_SALE_SLOT = None
            except Exception:
                pass
            try:
                queue_obj = getattr(self, "_stage_queue", None)
                if queue_obj is not None and getattr(m, "_GUI_STAGE_DETAIL", None) is queue_obj.append:
                    m._GUI_STAGE_DETAIL = None
            except Exception:
                m._GUI_STAGE_DETAIL = None
            self.root.destroy()

        # ---- set_stage hook'u GUI'ye bağla ----
        def _hook_stage(self):
            # Thread-safe: set_stage -> kuyruk, Tk güncellemesi ana thread
            import collections
            self._stage_queue = collections.deque(maxlen=200)
            try:
                _orig = m.set_stage

                def _wrap(st):
                    self._stage_queue.append(st);
                    try:
                        return _orig(st)
                    except Exception:
                        return None

                m.set_stage = _wrap  # type: ignore
            except Exception:
                def _basic(st):
                    self._stage_queue.append(st)

                m.set_stage = _basic  # type: ignore

            def _drain():
                try:
                    while self._stage_queue:
                        st = self._stage_queue.popleft()
                        self.stage.set(st)  # UI-thread
                        self.stage_log.append(st);
                        self.stage_log = self.stage_log[-200:]
                        self._refresh_log()
                finally:
                    self.root.after(150, _drain)

            _drain()
            try:
                m._GUI_STAGE_DETAIL = self._stage_queue.append
            except Exception:
                pass
            m.GUI_ABORT = False
            if hasattr(m, "_kb_pressed"):
                _kb0 = m._kb_pressed

                def _kb(k):
                    if k.lower() == "f12" and getattr(m, "GUI_ABORT", False): return True
                    try:
                        return _kb0(k)
                    except:
                        return False

                m._kb_pressed = _kb
            else:
                def _kb(k):
                    if k.lower() == "f12" and getattr(m, "GUI_ABORT", False): return True
                    return False

                m._kb_pressed = _kb

            if hasattr(keyboard, "is_pressed"):
                orig = getattr(m, "_GUI_ORIG_IS_PRESSED", None) or _KEYBOARD_IS_PRESSED_ORIG or keyboard.is_pressed

                def _gui_is_pressed(key):
                    try:
                        if str(key).lower() == "f12" and getattr(m, "GUI_ABORT", False):
                            return True
                    except Exception:
                        pass
                    try:
                        return orig(key)
                    except Exception:
                        return False

                m._GUI_ORIG_IS_PRESSED = orig
                keyboard.is_pressed = _gui_is_pressed

        # ---- UI kur ----
        def _build(self):
            nb = ttk.Notebook(self.root);
            nb.pack(fill="both", expand=True, padx=6, pady=6)
            # GENEL
            f1 = ttk.Frame(nb);
            nb.add(f1, text="Genel");
            r = 0
            ttk.Label(f1, text="Durum / Makro Aşaması:").grid(row=r, column=0, sticky="e");
            ttk.Label(f1, textvariable=self.stage, foreground="blue").grid(row=r, column=1, sticky="w");
            ttk.Label(f1, text="Boş Slot (Satış):").grid(row=r, column=2, sticky="e", padx=4);
            ttk.Label(f1, textvariable=self.sale_slot_var, foreground="blue").grid(row=r, column=3, sticky="w");
            r += 1
            ttk.Button(f1, text="Başlat", command=self.start).grid(row=r, column=0, sticky="we", padx=2, pady=2)
            ttk.Button(f1, text="Durdur", command=self.stop).grid(row=r, column=1, sticky="we", padx=2, pady=2)
            ttk.Button(f1, text="Ayarları Kaydet", command=self.save).grid(row=r, column=2, sticky="we", padx=2, pady=2)
            ttk.Button(f1, text="Hepsini Kapat", command=self.kill_all).grid(row=r, column=3, sticky="we", padx=2,
                                                                             pady=2);
            r += 1
            ttk.Label(f1, text="Kullanıcı Adı:").grid(row=r, column=0, sticky="e");
            ttk.Entry(f1, textvariable=self.v["username"], width=28).grid(row=r, column=1, sticky="w");
            r += 1
            ttk.Label(f1, text="Şifre:").grid(row=r, column=0, sticky="e");
            pw = ttk.Entry(f1, textvariable=self.v["password"], show="*", width=28);
            pw.grid(row=r, column=1, sticky="w")
            ttk.Button(f1, text="Göster/Gizle", command=lambda: pw.config(show=("" if pw.cget("show") == "*" else "*")),
                       width=14).grid(row=r, column=2, sticky="w");
            r += 1
            ttk.Button(f1, text="İzleme Penceresi Aç", command=self.open_monitor).grid(row=r, column=0, columnspan=2,
                                                                                       sticky="w", pady=4)
            r += 1
            lf_mode = ttk.LabelFrame(f1, text="Mod Seçimi")
            lf_mode.grid(row=r, column=0, columnspan=4, sticky="we", pady=6)
            ttk.Radiobutton(lf_mode, text="Item Basma", value="ITEM_BASMA", variable=self.v["operation_mode"]).grid(
                row=0, column=0, sticky="w", padx=4, pady=2)
            ttk.Radiobutton(lf_mode, text="Item Satış", value="ITEM_SATIS", variable=self.v["operation_mode"]).grid(
                row=0, column=1, sticky="w", padx=4, pady=2)
            ttk.Radiobutton(lf_mode, text="Artı 7’ye item basma", value=PLUS7_BANK_MODE,
                            variable=self.v["operation_mode"]).grid(row=0, column=2, sticky="w", padx=4, pady=2)
            ttk.Button(lf_mode, text="Kaydet", command=self.save_mode_selection).grid(row=0, column=3, padx=6, pady=2)

            # SATIN ALMA
            f2 = ttk.Frame(nb);
            nb.add(f2, text="Satın Alma")
            ttk.Label(f2, text="Mod:").grid(row=0, column=0, sticky="e")
            ttk.Radiobutton(f2, text="LINEN", value="LINEN", variable=self.v["buy_mode"]).grid(row=0, column=1,
                                                                                               sticky="w")
            ttk.Radiobutton(f2, text="FABRIC", value="FABRIC", variable=self.v["buy_mode"]).grid(row=0, column=2,
                                                                                                 sticky="w")
            ttk.Label(f2, text=_tr_name("BUY_TURNS")).grid(row=1, column=0, sticky="e");
            ttk.Entry(f2, textvariable=self.v["buy_turns"], width=8).grid(row=1, column=1, sticky="w")
            ttk.Label(f2, text=_tr_name("SCROLL_ALIM_ADET")).grid(row=2, column=0, sticky="e");
            ttk.Entry(f2, textvariable=self.v["scroll_low"], width=8).grid(row=2, column=1, sticky="w")
            ttk.Label(f2, text=_tr_name("SCROLL_MID_ALIM_ADET")).grid(row=3, column=0, sticky="e");
            ttk.Entry(f2, textvariable=self.v["scroll_mid"], width=8).grid(row=3, column=1, sticky="w")
            ttk.Label(f2, text=_tr_name("BASMA_HAKKI")).grid(row=4, column=0, sticky="e");
            ttk.Entry(f2, textvariable=self.v["basma_hakki"], width=8).grid(row=4, column=1, sticky="w")
            lf_server = ttk.LabelFrame(f2, text="Item Basma / Server Seçimi")
            lf_server.grid(row=5, column=0, columnspan=3, sticky="we", pady=6)
            ttk.Radiobutton(lf_server, text="Server1", value="Server1", variable=self.v["item_basma_server"]).grid(
                row=0, column=0, sticky="w", padx=4, pady=2)
            ttk.Radiobutton(lf_server, text="Server2", value="Server2", variable=self.v["item_basma_server"]).grid(
                row=0, column=1, sticky="w", padx=4, pady=2)

            lf_plus8_msg = ttk.LabelFrame(f2, text="+8 Bekleme Telegram")
            lf_plus8_msg.grid(row=6, column=0, columnspan=3, sticky="we", pady=6)
            ttk.Label(lf_plus8_msg, text="+8 item basma mesajı:").grid(row=0, column=0, sticky="e", padx=4, pady=2)
            ttk.Entry(lf_plus8_msg, textvariable=self.v["plus8_wait_message"], width=42).grid(row=0, column=1,
                                                                                                sticky="w", padx=4,
                                                                                                pady=2)
            ttk.Label(lf_plus8_msg, text="+8 item basma mesaj gönderme süresi (dk):").grid(row=1, column=0,
                                                                                            sticky="e", padx=4,
                                                                                            pady=2)
            ttk.Entry(lf_plus8_msg, textvariable=self.v["plus8_wait_interval"], width=10).grid(row=1, column=1,
                                                                                                sticky="w", padx=4,
                                                                                                pady=2)

            # ITEM SATIŞ
            f_sale = ttk.Frame(nb)
            nb.add(f_sale, text="Item Satış")
            f_sale.columnconfigure(1, weight=1)
            krallik_lbl = ttk.Label(f_sale, text="Krallık", foreground="blue", cursor="hand2")
            krallik_lbl.grid(row=0, column=0, columnspan=2, sticky="w", padx=6, pady=(4, 0))
            krallik_lbl.bind("<Button-1>", self._open_krallik)

            lf_sale = ttk.LabelFrame(f_sale, text="Pazar Ayarları")
            lf_sale.grid(row=1, column=0, columnspan=2, sticky="we", padx=6, pady=6)
            ttk.Label(lf_sale, text="Pazar Fiyat Metni:").grid(row=0, column=0, sticky="e", padx=4, pady=2)
            ttk.Entry(lf_sale, textvariable=self.v["sale_price_text"], width=32).grid(row=0, column=1, sticky="w",
                                                                                      padx=4,
                                                                                      pady=2)
            ttk.Label(lf_sale, text="Pazar Eşik 1:").grid(row=1, column=0, sticky="e", padx=4, pady=2)
            ttk.Entry(lf_sale, textvariable=self.v["sale_threshold_1"], width=8).grid(row=1, column=1, sticky="w",
                                                                                      padx=4,
                                                                                      pady=2)
            ttk.Label(lf_sale, text="Pazar Eşik 2:").grid(row=2, column=0, sticky="e", padx=4, pady=2)
            ttk.Entry(lf_sale, textvariable=self.v["sale_threshold_2"], width=8).grid(row=2, column=1, sticky="w",
                                                                                      padx=4,
                                                                                      pady=2)
            ttk.Label(lf_sale, text="Pazar Eşik 3:").grid(row=3, column=0, sticky="e", padx=4, pady=2)
            ttk.Entry(lf_sale, textvariable=self.v["sale_threshold_3"], width=8).grid(row=3, column=1, sticky="w",
                                                                                      padx=4,
                                                                                      pady=2)
            ttk.Label(lf_sale, text="Park X Koordinatı:").grid(row=4, column=0, sticky="e", padx=4, pady=2)
            ttk.Entry(lf_sale, textvariable=self.v["sale_park_x"], width=8).grid(row=4, column=1, sticky="w", padx=4,
                                                                                 pady=2)

            lf_timing = ttk.LabelFrame(f_sale, text="Bekleme / Tıklama")
            lf_timing.grid(row=2, column=0, columnspan=2, sticky="we", padx=6, pady=6)
            ttk.Label(lf_timing, text="Yenileme Bekleme Min (sn):").grid(row=0, column=0, sticky="e", padx=4, pady=2)
            ttk.Entry(lf_timing, textvariable=self.v["sale_refresh_min"], width=8).grid(row=0, column=1, sticky="w",
                                                                                        padx=4,
                                                                                        pady=2)
            ttk.Label(lf_timing, text="Maks (sn):").grid(row=0, column=2, sticky="e", padx=4, pady=2)
            ttk.Entry(lf_timing, textvariable=self.v["sale_refresh_max"], width=8).grid(row=0, column=3, sticky="w",
                                                                                        padx=4,
                                                                                        pady=2)
            ttk.Label(lf_timing, text="İlk Bekleme (sn):").grid(row=1, column=0, sticky="e", padx=4, pady=2)
            ttk.Entry(lf_timing, textvariable=self.v["sale_initial_wait"], width=8).grid(row=1, column=1, sticky="w",
                                                                                         padx=4,
                                                                                         pady=2)
            ttk.Label(lf_timing, text="902,135 Tıklama Adet:").grid(row=2, column=0, sticky="e", padx=4, pady=2)
            ttk.Entry(lf_timing, textvariable=self.v["sale_click_902_count"], width=8).grid(row=2, column=1, sticky="w",
                                                                                            padx=4, pady=2)
            ttk.Label(lf_timing, text="902,135 Hız (sn):").grid(row=2, column=2, sticky="e", padx=4, pady=2)
            ttk.Entry(lf_timing, textvariable=self.v["sale_click_902_speed"], width=8).grid(row=2, column=3, sticky="w",
                                                                                            padx=4, pady=2)
            ttk.Label(lf_timing, text="899,399 Tıklama Adet:").grid(row=3, column=0, sticky="e", padx=4, pady=2)
            ttk.Entry(lf_timing, textvariable=self.v["sale_click_899_count"], width=8).grid(row=3, column=1, sticky="w",
                                                                                            padx=4, pady=2)
            ttk.Label(lf_timing, text="899,399 Hız (sn):").grid(row=3, column=2, sticky="e", padx=4, pady=2)
            ttk.Entry(lf_timing, textvariable=self.v["sale_click_899_speed"], width=8).grid(row=3, column=3, sticky="w",
                                                                                            padx=4, pady=2)

            lf_bank = ttk.LabelFrame(f_sale, text="Banka")
            lf_bank.grid(row=3, column=0, columnspan=2, sticky="we", padx=6, pady=6)
            ttk.Label(lf_bank, text="Bankaya Git Boş Slot Eşiği:").grid(row=0, column=0, sticky="e", padx=4, pady=2)
            ttk.Entry(lf_bank, textvariable=self.v["sale_bank_threshold"], width=8).grid(row=0, column=1, sticky="w",
                                                                                         padx=4,
                                                                                         pady=2)
            ttk.Label(lf_bank, text="Bankadan Alınacak Adet:").grid(row=1, column=0, sticky="e", padx=4, pady=2)
            ttk.Entry(lf_bank, textvariable=self.v["sale_bank_withdraw"], width=8).grid(row=1, column=1, sticky="w",
                                                                                        padx=4,
                                                                                        pady=2)
            ttk.Label(lf_bank, text="Çıkış Süresi Min (sn):").grid(row=2, column=0, sticky="e", padx=4, pady=2)
            ttk.Entry(lf_bank, textvariable=self.v["sale_exit_delay_min"], width=8).grid(row=2, column=1, sticky="w",
                                                                                         padx=4,
                                                                                         pady=2)
            ttk.Label(lf_bank, text="Maks (sn):").grid(row=2, column=2, sticky="e", padx=4, pady=2)
            ttk.Entry(lf_bank, textvariable=self.v["sale_exit_delay_max"], width=8).grid(row=2, column=3, sticky="w",
                                                                                         padx=4,
                                                                                         pady=2)
            ttk.Checkbutton(lf_bank, text="Banka boşsa Telegram gönder", variable=self.v["sale_bank_notify"],
                            onvalue=True, offvalue=False).grid(row=3, column=0, columnspan=4, sticky="w", padx=4,
                                                               pady=2)
            ttk.Label(lf_bank, text="Telegram Mesajı:").grid(row=4, column=0, sticky="e", padx=4, pady=2)
            ttk.Entry(lf_bank, textvariable=self.v["sale_bank_message"], width=32).grid(row=4, column=1, columnspan=3,
                                                                                        sticky="w", padx=4, pady=2)
            ttk.Label(lf_bank, text="Telegram Token:").grid(row=5, column=0, sticky="e", padx=4, pady=2)
            ttk.Entry(lf_bank, textvariable=self.v["telegram_token"], width=32).grid(row=5, column=1, columnspan=3,
                                                                                     sticky="w", padx=4, pady=2)
            ttk.Label(lf_bank, text="Telegram Chat ID:").grid(row=6, column=0, sticky="e", padx=4, pady=2)
            ttk.Entry(lf_bank, textvariable=self.v["telegram_chat_id"], width=32).grid(row=6, column=1, columnspan=3,
                                                                                       sticky="w", padx=4, pady=2)

            lf_monitor = ttk.LabelFrame(f_sale, text="Envanter Takibi")
            lf_monitor.grid(row=4, column=0, columnspan=2, sticky="we", padx=6, pady=6)
            ttk.Label(lf_monitor, text="Boş Slot Sayısı:").grid(row=0, column=0, sticky="e", padx=4, pady=2)
            ttk.Label(lf_monitor, textvariable=self.sale_slot_var, width=6, foreground="blue").grid(row=0, column=1,
                                                                                                    sticky="w",
                                                                                                    padx=4, pady=2)
            ttk.Label(lf_monitor, text="Envanter Tarama Süresi (sn):").grid(row=1, column=0, sticky="e", padx=4,
                                                                            pady=2)
            ttk.Entry(lf_monitor, textvariable=self.v["sale_slot_interval"], width=8).grid(row=1, column=1, sticky="w",
                                                                                           padx=4, pady=2)
            lf_auto_refresh = ttk.LabelFrame(f_sale, text="Otomatik Pazar Yenileme")
            lf_auto_refresh.grid(row=5, column=0, columnspan=2, sticky="we", padx=6, pady=6)
            ttk.Checkbutton(lf_auto_refresh, text="Pazar yenileme aktif",
                            variable=self.v["auto_market_refresh_enabled"], onvalue=True,
                            offvalue=False).grid(row=0, column=0, columnspan=2, sticky="w", padx=4, pady=2)
            ttk.Label(lf_auto_refresh, text="Yenileme aralığı (saat):").grid(row=1, column=0, sticky="e", padx=4,
                                                                             pady=2)
            ttk.Entry(lf_auto_refresh, textvariable=self.v["auto_market_refresh_interval_hours"], width=8).grid(
                row=1, column=1, sticky="w", padx=4, pady=2)

            lf_krallik = ttk.LabelFrame(f_sale, text="Krallık Yazısı Tıklama")
            lf_krallik.grid(row=6, column=0, columnspan=2, sticky="we", padx=6, pady=6)
            ttk.Label(lf_krallik, text="X Koordinatı:").grid(row=0, column=0, sticky="e", padx=4, pady=2)
            ttk.Entry(lf_krallik, textvariable=self.v["krallik_click_x"], width=8).grid(row=0, column=1,
                                                                                        sticky="w", padx=4,
                                                                                        pady=2)
            ttk.Label(lf_krallik, text="Y Koordinatı:").grid(row=1, column=0, sticky="e", padx=4, pady=2)
            ttk.Entry(lf_krallik, textvariable=self.v["krallik_click_y"], width=8).grid(row=1, column=1,
                                                                                        sticky="w", padx=4,
                                                                                        pady=2)
            ttk.Label(lf_krallik, text="Tıklama Aralığı (sn):").grid(row=0, column=2, sticky="e", padx=4, pady=2)
            ttk.Entry(lf_krallik, textvariable=self.v["krallik_click_interval"], width=8).grid(row=0, column=3,
                                                                                               sticky="w", padx=4,
                                                                                               pady=2)
            ttk.Label(lf_krallik, text="Tıklama Süresi (sn):").grid(row=1, column=2, sticky="e", padx=4, pady=2)
            ttk.Entry(lf_krallik, textvariable=self.v["krallik_click_hold"], width=8).grid(row=1, column=3,
                                                                                           sticky="w", padx=4,
                                                                                           pady=2)

            ttk.Button(f_sale, text="Tüm Ayarları Kaydet", command=self.save).grid(row=7, column=0, columnspan=2,
                                                                                   sticky="we", padx=6, pady=6)

            # HIZ
            f3 = ttk.Frame(nb);
            nb.add(f3, text="Hız")
            ttk.Label(f3, text=_tr_name("SPEED_PROFILE")).grid(row=0, column=0, sticky="e")
            ttk.Combobox(f3, textvariable=self.v["speed_profile"], values=["FAST", "BALANCED", "SAFE"],
                         state="readonly", width=12).grid(row=0, column=1, sticky="w")
            ttk.Label(f3, text="Mikro Adım (PRESS_MIN/MAX):").grid(row=1, column=0, sticky="e")
            ttk.Entry(f3, textvariable=self.v["press_min"], width=8).grid(row=1, column=1, sticky="w")
            ttk.Entry(f3, textvariable=self.v["press_max"], width=8).grid(row=1, column=2, sticky="w")
            ttk.Label(f3, text="Fren Δ (FAST/BAL/SAFE):").grid(row=2, column=0, sticky="e")
            ttk.Entry(f3, textvariable=self.v["brake_fast"], width=6).grid(row=2, column=1, sticky="w")
            ttk.Entry(f3, textvariable=self.v["brake_bal"], width=6).grid(row=2, column=2, sticky="w")
            ttk.Entry(f3, textvariable=self.v["brake_safe"], width=6).grid(row=2, column=3, sticky="w")

            # GELİŞMİŞ (büyük harfli public değişkenler)
            f4 = ttk.Frame(nb);
            nb.add(f4, text="Gelişmiş")
            top = ttk.Frame(f4);
            top.pack(fill="x", padx=4, pady=4)
            ttk.Label(top, text="Filtre:").pack(side="left")
            self.filter = tk.StringVar();
            ttk.Entry(top, textvariable=self.filter, width=24).pack(side="left", padx=6)
            ttk.Button(top, text="Yenile", command=self._build_adv).pack(side="left")
            ttk.Button(top, text="Tümünü Uygula", command=self._apply_all_adv).pack(side="left", padx=6)
            c = tk.Canvas(f4, highlightthickness=0);
            vs = ttk.Scrollbar(f4, orient="vertical", command=c.yview);
            c.configure(yscrollcommand=vs.set)
            frm = ttk.Frame(c);
            self._frm_id = c.create_window((0, 0), window=frm, anchor="nw")
            c.bind("<Configure>", lambda e: c.itemconfigure(self._frm_id, width=e.width))
            c.pack(side="left", fill="both", expand=True);
            vs.pack(side="right", fill="y");
            self.adv_container = frm

            # DURUM
            f5 = ttk.Frame(nb);
            nb.add(f5, text="Durum")
            ttk.Label(f5, text="Anlık Aşama:").pack(anchor="w", padx=6, pady=4)
            ttk.Label(f5, textvariable=self.stage, foreground="blue", font=("Segoe UI", 11, "bold")).pack(anchor="w",
                                                                                                          padx=10)
            ttk.Label(f5, text="Son 30 Aşama:").pack(anchor="w", padx=6, pady=6)
            self.lb = tk.Listbox(f5, height=14);
            self.lb.pack(fill="both", expand=True, padx=8, pady=4)

            # --- Hız/Anvil/PREC 598 (sekme) ---
            try:
                f6 = ttk.Frame(nb);
                nb.add(f6, text="Hız/Anvil/PREC 598")
                c6 = tk.Canvas(f6, highlightthickness=0);
                vs6 = ttk.Scrollbar(f6, orient="vertical", command=c6.yview)
                c6.configure(yscrollcommand=vs6.set)
                frm6 = ttk.Frame(c6);
                _frm6_id = c6.create_window((0, 0), window=frm6, anchor="nw")
                c6.bind("<Configure>", lambda e: c6.itemconfigure(_frm6_id, width=e.width))
                c6.pack(side="left", fill="both", expand=True);
                vs6.pack(side="right", fill="y")
                _build_speed_prec598_tab(frm6, tk, ttk)
            except Exception as _e:
                print("[GUI] PREC 598 sekme hata:", _e)

        # ---- LOG kutusu ----
        def _refresh_log(self):
            if hasattr(self, "lb"):
                self.lb.delete(0, "end")
                for x in self.stage_log[-30:]: self.lb.insert("end", x)

        # ---- Gelişmiş alan listesi ----
        def _is_editable(self, name, val):
            if name.startswith("_"):
                return False
            if callable(val):
                return False
            import types
            if isinstance(val, types.ModuleType):
                return False
            if isinstance(val, (int, float, bool, str, list, tuple, dict, set, type(None))):
                return True
            return False

        def _adv_items(self):
            items = []
            for k in dir(m):
                try:
                    v = getattr(m, k)
                    if self._is_editable(k, v): items.append((k, v))
                except:
                    pass
            items.sort(key=lambda x: x[0]);
            return items

        def _build_adv(self):
            for w in self.adv_container.winfo_children(): w.destroy()
            self.adv_rows = []
            F = (self.filter.get().strip().upper() if hasattr(self, "filter") else "")
            grouped = {}
            for name, val in self._adv_items():
                if F and (F not in name.upper()) and (F not in (_TR.get(name, "").upper())):
                    continue
                grouped.setdefault(_adv_group_of(name), []).append((name, val))

            if not grouped:
                ttk.Label(self.adv_container, text="Sonuç bulunamadı.").pack(anchor="w", padx=8, pady=6)
                self.adv_container.update_idletasks()
                try:
                    self.adv_container.master.configure(scrollregion=self.adv_container.master.bbox("all"))
                except Exception:
                    pass
                return

            def _grp_key(grp_name: str):
                try:
                    return (_ADV_GROUP_ORDER.index(grp_name), grp_name)
                except ValueError:
                    return (len(_ADV_GROUP_ORDER), grp_name)

            for grp_name in sorted(grouped.keys(), key=_grp_key):
                entries = grouped[grp_name]
                entries.sort(key=lambda item: _tr_name(item[0]).upper())
                title = grp_name or 'Genel'
                frame = ttk.LabelFrame(self.adv_container, text=title)
                frame.pack(fill="x", padx=6, pady=4, anchor="n")
                frame.columnconfigure(1, weight=1)

                for row, (name, val) in enumerate(entries):
                    ttk.Label(frame, text=_tr_name(name)).grid(row=row, column=0, sticky="w", padx=2, pady=1)
                    if isinstance(val, bool):
                        var = tk.StringVar(value=str(val))
                        widget = ttk.Combobox(frame, values=["True", "False"], textvariable=var, width=8,
                                              state="readonly")
                    else:
                        var = tk.StringVar(value=str(val))
                        widget = ttk.Entry(frame, textvariable=var, width=28)
                    widget.grid(row=row, column=1, sticky="we", padx=3)
                    ttk.Button(frame, text="Uygula",
                               command=lambda n=name, vr=var: self._apply_one_adv(n, vr.get())
                               ).grid(row=row, column=2, sticky="w", padx=2)
                    try:
                        info_btn = ttk.Button(frame, width=2, text="i")
                        info_btn.grid(row=row, column=3, padx=2, pady=1, sticky="w")
                        _Tooltip(info_btn, _TR_HELP.get(name, "Açıklama yok"))
                    except Exception:
                        pass
                    self.adv_rows.append((name, var))

            self.adv_container.update_idletasks()
            try:
                self.adv_container.master.configure(scrollregion=self.adv_container.master.bbox("all"))
            except:
                pass

        def _apply_one_adv(self, name, val_raw):
            import ast
            try:
                try:
                    val = ast.literal_eval(val_raw)
                except:
                    val = val_raw
                setattr(m, name, val);
                self._msg(f"{name} = {val!r} uygulandı.")
                self.save()  # tek değişkeni de kalıcı yap
            except Exception as e:
                self._msg(f"{name} ayarlanamadı: {e}")

        def _apply_all_adv(self):
            import json, os
            path = self._cfg()
            # Şema garantisi
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                if not isinstance(data, dict): data = {}
            except Exception:
                data = {}
            if 'gui' not in data or not isinstance(data.get('gui'), dict): data['gui'] = {}
            if 'advanced' not in data or not isinstance(data.get('advanced'), dict): data['advanced'] = {}
            adv = data['advanced']
            # Değerleri topla
            for name, var in getattr(self, 'adv_rows', []):
                try:
                    adv[name] = var.get()
                except Exception:
                    pass
            # Atomik kaydet
            tmp = path + '.tmp'
            try:
                with open(tmp, 'w', encoding='utf-8') as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                os.replace(tmp, path)
                self._msg(f'Ayarlar kaydedildi: {path}')
            except Exception as e:
                self._msg(f'[GUI] Kaydetme hatası: {e}')
                try:
                    if os.path.exists(tmp): os.remove(tmp)
                except:
                    pass
            # Uygula
            try:
                self.apply_core()
                self._msg('Tüm gelişmiş ayarlar uygulandı.')
            except Exception as e:
                self._msg(f'[GUI] apply_core hatası: {e}')

        def start(self):
            if getattr(self, "thr", None) and self.thr.is_alive(): self._msg("Zaten çalışıyor."); return
            self.apply_core()
            m.GUI_ABORT = False
            self.thr = threading.Thread(target=self._run, daemon=True);
            self.thr.start()

        def _run(self):
            try:
                self.stage.set("Başlatılıyor...");
                try:
                    m.main()
                except getattr(m, "GUIAbort", GUIAbort):
                    self.stage.set("Kullanıcı tarafından durduruldu.")
                    self._msg("Makro kullanıcı isteğiyle durdu.")
                else:
                    if getattr(m, "GUI_ABORT", False):
                        self.stage.set("Kullanıcı tarafından durduruldu.")
                        self._msg("Makro kullanıcı isteğiyle durdu.")
                    else:
                        self.stage.set("Bitti/sonlandı.")
            except Exception as e:
                self.stage.set(f"Hata: {e}");
                self._msg(f"main() hata: {e}")
            finally:
                self.root.after(0, self._sync_thread_state)

        def stop(self):
            self._msg("Durdur (F12 sanalı)...");
            m.GUI_ABORT = True;
            self.stage.set("Durduruluyor (F12)...")

        def _sync_thread_state(self):
            thr = getattr(self, "thr", None)
            if thr and thr.is_alive():
                self.root.after(200, self._sync_thread_state)
            else:
                self.thr = None

        def kill_all(self):
            self.stop()
            try:
                if hasattr(m, "close_all_game_instances"): m.close_all_game_instances()
            except Exception as e:
                self._msg(f"close_all_game_instances hata: {e}")

        def open_monitor(self):
            win = tk.Toplevel(self.root);
            win.title("İzleme");
            win.resizable(False, False)
            ttk.Label(win, textvariable=self.stage, foreground="blue", font=("Segoe UI", 12, "bold")).pack(padx=10,
                                                                                                           pady=10)

        # ---- Ayar yükle/kaydet/uygula ----
        def _cfg(self):
            return _MERDIVEN_CFG_PATH()

        def _load_json(self):
            import json, os
            # JSON varsa GUI alanlarını ondan doldur; yoksa modül varsayılanları zaten set edildi.
            try:
                with open(self._cfg(), "r", encoding="utf-8") as f:
                    j = json.load(f)
            except:
                j = {}
            gui_data = (j.get("gui", {}) or {})
            for k, val in gui_data.items():
                if k in self.v:
                    try:
                        import tkinter as tk
                        if isinstance(self.v[k], tk.IntVar):
                            self.v[k].set(int(val))
                        elif isinstance(self.v[k], tk.DoubleVar):
                            self.v[k].set(float(val))
                        elif isinstance(self.v[k], tk.BooleanVar):
                            if isinstance(val, str):
                                self.v[k].set(val.lower() in ("1", "true", "yes", "on"))
                            else:
                                self.v[k].set(bool(val))
                        else:
                            self.v[k].set(str(val))
                    except:
                        pass
            if "sale_refresh_wait" in gui_data:
                try:
                    legacy = float(gui_data.get("sale_refresh_wait", 0))
                    if "sale_refresh_min" in self.v:
                        self.v["sale_refresh_min"].set(legacy)
                    if "sale_refresh_max" in self.v:
                        self.v["sale_refresh_max"].set(legacy)
                except Exception:
                    pass
            # advanced → modüle uygula
            for name, raw in (j.get("advanced", {}) or {}).items():
                try:
                    import ast
                    try:
                        val = ast.literal_eval(raw)
                    except:
                        val = raw
                    setattr(m, name, val)
                except:
                    pass
            self._build_adv()

        def save_mode_selection(self):
            self.save()

        def apply_core(self):
            # login
            if hasattr(m, "LOGIN_USERNAME"): m.LOGIN_USERNAME = self.v["username"].get()
            if hasattr(m, "LOGIN_PASSWORD"): m.LOGIN_PASSWORD = self.v["password"].get()
            setattr(m, "OPERATION_MODE", self.v["operation_mode"].get().upper())
            setattr(m, "ITEM_BASMA_SERVER", self.v["item_basma_server"].get())
            setattr(m, "ITEM_SALE_PRICE_TEXT", self.v["sale_price_text"].get())
            setattr(m, "PAZAR_ESIK_1", int(self.v["sale_threshold_1"].get()))
            setattr(m, "PAZAR_ESIK_2", int(self.v["sale_threshold_2"].get()))
            setattr(m, "PAZAR_ESIK_3", int(self.v["sale_threshold_3"].get()))
            setattr(m, "PAZAR_YENILEME_BEKELEME_MIN", float(self.v["sale_refresh_min"].get()))
            setattr(m, "PAZAR_YENILEME_BEKELEME_MAX", float(self.v["sale_refresh_max"].get()))
            setattr(m, "PAZAR_YENILEME_BEKELEME_SURESI", float(self.v["sale_refresh_max"].get()))
            setattr(m, "PAZAR_ILK_BEKELEME_SURESI", float(self.v["sale_initial_wait"].get()))
            setattr(m, "CLICK_902_135_ADET", int(self.v["sale_click_902_count"].get()))
            setattr(m, "CLICK_902_135_HIZ", float(self.v["sale_click_902_speed"].get()))
            setattr(m, "CLICK_899_399_ADET", int(self.v["sale_click_899_count"].get()))
            setattr(m, "CLICK_899_399_HIZ", float(self.v["sale_click_899_speed"].get()))
            setattr(m, "auto_market_refresh_enabled", bool(self.v["auto_market_refresh_enabled"].get()))
            setattr(m, "auto_market_refresh_interval_hours",
                    float(self.v["auto_market_refresh_interval_hours"].get()))
            setattr(m, "BANKAYA_GIT_BOS_SLOT_ESIGI", int(self.v["sale_bank_threshold"].get()))
            try:
                withdraw_val = int(self.v["sale_bank_withdraw"].get())
                if withdraw_val <= 0:
                    withdraw_val = ITEM_SALE_BANK_WITHDRAW_COUNT
            except Exception:
                withdraw_val = ITEM_SALE_BANK_WITHDRAW_COUNT
            setattr(m, "ITEM_SALE_BANK_WITHDRAW_COUNT", withdraw_val)
            setattr(m, "PAZAR_PARK_X", int(self.v["sale_park_x"].get()))
            setattr(m, "ITEM_SALE_SLOT_SCAN_INTERVAL", float(self.v["sale_slot_interval"].get()))
            setattr(m, "ITEM_SALE_EXIT_DELAY_MIN", float(self.v["sale_exit_delay_min"].get()))
            setattr(m, "ITEM_SALE_EXIT_DELAY_MAX", float(self.v["sale_exit_delay_max"].get()))
            setattr(m, "ITEM_SALE_BANK_NOTIFY", bool(self.v["sale_bank_notify"].get()))
            setattr(m, "ITEM_SALE_BANK_EMPTY_MESSAGE", self.v["sale_bank_message"].get())
            setattr(m, "KRALLIK_CLICK_X", int(self.v["krallik_click_x"].get()))
            setattr(m, "KRALLIK_CLICK_Y", int(self.v["krallik_click_y"].get()))
            setattr(m, "KRALLIK_TIKLAMA_ARALIGI", float(self.v["krallik_click_interval"].get()))
            setattr(m, "KRALLIK_TIKLAMA_SURESI", float(self.v["krallik_click_hold"].get()))
            setattr(m, "TELEGRAM_TOKEN", self.v["telegram_token"].get().strip())
            setattr(m, "TELEGRAM_CHAT_ID", self.v["telegram_chat_id"].get().strip())
            setattr(m, "PLUS8_WAIT_MESSAGE", self.v["plus8_wait_message"].get())
            try:
                setattr(m, "PLUS8_WAIT_MESSAGE_INTERVAL_MIN", float(self.v["plus8_wait_interval"].get()))
            except Exception:
                setattr(m, "PLUS8_WAIT_MESSAGE_INTERVAL_MIN", 0.0)
            # buy mode + adetler
            mode = self.v["buy_mode"].get().upper()
            try:
                if hasattr(m, "_set_buy_mode"):
                    m._set_buy_mode(mode)
                else:
                    setattr(m, "BUY_MODE", mode)
                # kalıcı dosya
                p = PERSIST_PATH('config_buy_mode.json')
                with open(p, "w", encoding="utf-8") as f:
                    json.dump({"BUY_MODE": mode}, f, ensure_ascii=False, indent=2)
            except Exception:
                pass
            for name, key in [("BUY_TURNS", "buy_turns"), ("SCROLL_ALIM_ADET", "scroll_low"),
                              ("SCROLL_MID_ALIM_ADET", "scroll_mid"), ("BASMA_HAKKI", "basma_hakki")]:
                try:
                    cur = getattr(m, name, 0)
                    val = self.v[key].get()
                    setattr(m, name, type(cur)(val) if not isinstance(cur, bool) else bool(val))
                except Exception:
                    setattr(m, name, self.v[key].get())
            # hız + fren
            if hasattr(m, "SPEED_PROFILE"): m.SPEED_PROFILE = self.v["speed_profile"].get().upper()
            if hasattr(m, "PRESS_MIN"): m.PRESS_MIN = float(self.v["press_min"].get())
            if hasattr(m, "PRESS_MAX"): m.PRESS_MAX = float(self.v["press_max"].get())
            try:
                d = getattr(m, "_SPEED_PRE_BRAKE", {"FAST": 3, "BALANCED": 2, "SAFE": 1})
                d.update({"FAST": int(self.v["brake_fast"].get()), "BALANCED": int(self.v["brake_bal"].get()),
                          "SAFE": int(self.v["brake_safe"].get())})
                setattr(m, "_SPEED_PRE_BRAKE", d)
            except Exception:
                pass

        def save(self):
            import json, os
            path = self._cfg()
            data = {"gui": {}, "advanced": {}}
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if not isinstance(data, dict): data = {"gui": {}, "advanced": {}}
                if "gui" not in data or not isinstance(data.get("gui"), dict): data["gui"] = {}
                if "advanced" not in data or not isinstance(data.get("advanced"), dict): data["advanced"] = {}
            except Exception:
                data = {"gui": {}, "advanced": {}}
            for k, var in self.v.items():
                try:
                    data["gui"][k] = var.get()
                except Exception:
                    pass
            adv = data.get("advanced")
            if not isinstance(adv, dict): adv = {}
            data["advanced"] = adv
            for name, var in self.adv_rows:
                try:
                    adv[name] = var.get()
                except Exception:
                    pass
            tmp = path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            os.replace(tmp, path)
            self._msg(f"Ayarlar kaydedildi: {path}")
            self.apply_core()

        def _tick(self):
            self.root.after(250, self._tick)  # ileride canlı metrik eklenebilir

    # Pencereyi başlat
    root = tk.Tk()
    try:
        s = ttk.Style()
        if "vista" in s.theme_names(): s.theme_use("vista")
    except Exception:
        pass
    _GUI(root)
    root.mainloop()
    return True


# --- Otomatik GUI başlatma / CLI fallback ---
def _MERDIVEN_GUI_ENTRY(auto_open=True):
    import sys
    if "--nogui" in sys.argv or not auto_open:
        try:
            main()
        except NameError:
            print("[GUI] main() bulunamadı.")
        return
    try:
        ok = _MERDIVEN_RUN_GUI()
        if not ok:
            main()
    except Exception as e:
        print("[GUI] açılmadı, terminal moduna düşülüyor:", e)
        try:
            main()
        except Exception as e2:
            print("[MAIN] hata:", e2)


# Eğer mevcut dosyanın sonunda standart __main__ bloğu varsa üzerine yazmak zahmetli olabilir.
# Bunun yerine: import edildiğinde hiçbir şey yapma; direkt çalıştırıldığında GUI'yi otomatik aç veya --nogui ile CLI çalıştır.
# (Yama ekledi) GUI ayar yolu belirleyici
def _cfg_path(*_):
    return PERSIST_PATH('merdiven_config.json')


# ==== [AUTO-INJECT] Town Guard Wrapper — town_wrapper_v2 ====
# linter-dostu sentinel
if '_TOWN_WRAPPED' not in globals():
    _TOWN_WRAPPED = False

# sentinel (_TOWN_WRAPPED tanımlı değilse False yap)
if '_TOWN_WRAPPED' not in globals():
    _TOWN_WRAPPED = False
if not _TOWN_WRAPPED:

    try:
        TOWN_MIN_INTERVAL_SEC
    except NameError:
        TOWN_MIN_INTERVAL_SEC = 8
    _TOWN_REQ_TS = 0.0
    _TOWN_REQ_COUNT = 0


    def _make_town_wrapper(_orig):
        def _wrapped(*args, **kwargs):
            global TOWN_LOCK, _TOWN_REQ_TS, _TOWN_REQ_COUNT, TOWN_MIN_INTERVAL_SEC
            now = time.time()
            # Debounce
            if now - float(_TOWN_REQ_TS) < float(TOWN_MIN_INTERVAL_SEC):
                _town_log_once('[TOWN] Debounce — son deneme çok yakın, skip.')
                return False
            # Kilit açıkken gelen istekleri izle
            if 'TOWN_LOCK' in globals() and TOWN_LOCK:
                # burst sayacı
                _TOWN_REQ_COUNT = (_TOWN_REQ_COUNT + 1) if (now - _TOWN_REQ_TS) < 3.0 else 1
                _TOWN_REQ_TS = now
                if _TOWN_REQ_COUNT >= 8:
                    try:
                        TOWN_LOCK = False
                        _town_log_once(
                            '[TOWN] Anti-Loop: ardışık istek eşiği aşıldı — kilit ZORLA kapatıldı (tek sefer).')
                    except Exception:
                        pass
                else:
                    _town_log_once('[TOWN] Kilit açık — town isteği skip.', 'count=', _TOWN_REQ_COUNT)
                    return False
            # çağrıya izin
            _TOWN_REQ_TS = now
            _TOWN_REQ_COUNT = 0
            try:
                return _orig(*args, **kwargs)
            except Exception as e:
                _town_log_once('[TOWN] Wrapper içi hata:', e)
                return False

        return _wrapped


    def _wrap_town_like():
        names = ('town', 'go_town', 'cast_town', 'send_town', 'do_town')
        wrapped_any = False
        for nm in names:
            orig = globals().get(nm, None)
            if callable(orig) and not getattr(orig, '_is_wrapped_by_town_guard', False):
                w = _make_town_wrapper(orig)
                setattr(w, '_is_wrapped_by_town_guard', True)
                globals()[nm] = w
                wrapped_any = True
        if wrapped_any:
            _town_log_once('[TOWN] Guard wrapper aktif.')
        else:
            _town_log_once('[TOWN] Uyarı: sarılacak town fonksiyonu bulunamadı — isimler farklı olabilir.')


    _wrap_town_like()
    _TOWN_WRAPPED = True
# ==== [/AUTO-INJECT] ====


# === [YAMA FAST ANVIL] start ===
# --- [YAMA] GUI görünürlüğü için alias'lar (SAFE) ---
# NE İŞE YARAR: IDE 'unresolved' uyarılarını keser, runtime'da da NameError vermez.
UPG_CONFIRM_WAIT_MS = int(globals().get('ANVIL_CONFIRM_WAIT_MS', 45))
ANVIL_CONFIRM_WAIT_MS = UPG_CONFIRM_WAIT_MS
UPG_ROI_STALE_MS = int(globals().get('ROI_STALE_MS', 120))
ROI_STALE_MS = UPG_ROI_STALE_MS

import time as _t

try:
    import pyautogui as _pya
except Exception as _e:
    print('[YAMA FAST] pyautogui import edilemedi:', _e)

# ---- Ayarlar (GUI ile değişebilir) ----
UPG_USE_FAST_MOUSE = True
UPG_MOUSE_HIZI = 0.05
UPG_TUS_HIZI = 0.05
ANVIL_CONFIRM_WAIT_MS = 50
ROI_STALE_MS = 250

try:
    _YAMA_FAST_ANVIL_OK
except NameError:
    _YAMA_FAST_ANVIL_OK = False


def _yama__get_upg_bounds():
    g = globals()
    if 'UPG' in g and isinstance(g['UPG'], (tuple, list)) and len(g['UPG']) == 4:
        x1, y1, x2, y2 = g['UPG']
        if x2 > x1 and y2 > y1:
            return int(x1), int(y1), int(x2 - x1), int(y2 - y1)
        return int(x1), int(y1), int(x2), int(y2)
    for a in ('UPG_INV_LEFT', 'UPG_INV_TOP', 'UPG_INV_RIGHT', 'UPG_INV_BOTTOM'):
        if a not in g: break
    else:
        x1, y1, x2, y2 = int(g['UPG_INV_LEFT']), int(g['UPG_INV_TOP']), int(g['UPG_INV_RIGHT']), int(
            g['UPG_INV_BOTTOM'])
        return x1, y1, int(x2 - x1), int(y2 - y1)
    return None


class _AnvilFastMode:
    def __enter__(self):
        self.g = globals();
        self._ok = False
        self._orig = {'PAUSE': getattr(_pya, 'PAUSE', 0.0),
                      'MINIMUM_SLEEP': getattr(_pya, 'MINIMUM_SLEEP', 0.0),
                      'MINIMUM_DURATION': getattr(_pya, 'MINIMUM_DURATION', 0.0),
                      'moveTo': getattr(_pya, 'moveTo', None),
                      'moveRel': getattr(_pya, 'moveRel', None),
                      'click': getattr(_pya, 'click', None),
                      'rightClick': getattr(_pya, 'rightClick', None),
                      'screenshot': getattr(_pya, 'screenshot', None)}
        try:
            _pya.PAUSE = 0.0;
            _pya.MINIMUM_SLEEP = 0.0;
            _pya.MINIMUM_DURATION = 0.0
        except Exception:
            pass
        self._save_mouse = self.g.get('mouse_hizi', None)
        self._save_tus = self.g.get('tus_hizi', None)
        if self.g.get('UPG_USE_FAST_MOUSE', True):
            if self._save_mouse is not None: self.g['mouse_hizi'] = float(self.g.get('UPG_MOUSE_HIZI', 0.015))
            if self._save_tus is not None: self.g['tus_hizi'] = float(self.g.get('UPG_TUS_HIZI', 0.020))

        self._upg = _yama__get_upg_bounds();
        self._upg_img = None;
        self._ts = 0.0
        import ctypes as _ct
        _L, _R = (0x0002, 0x0004), (0x0008, 0x0010)

        def _send(x, y, left=True):
            _ct.windll.user32.SetCursorPos(int(x), int(y))
            if left:
                _ct.windll.user32.mouse_event(_L[0], 0, 0, 0, 0);
                _ct.windll.user32.mouse_event(_L[1], 0, 0, 0, 0)
            else:
                _ct.windll.user32.mouse_event(_R[0], 0, 0, 0, 0);
                _ct.windll.user32.mouse_event(_R[1], 0, 0, 0, 0)

        def _mv(x, y, dur=None, *a, **k):
            return self._orig['moveTo'](x, y, 0, *a, **k) if self._orig['moveTo'] else None

        def _mvr(x, y, dur=None, *a, **k):
            return self._orig['moveRel'](x, y, 0, *a, **k) if self._orig['moveRel'] else None

        def _clk(x=None, y=None, clicks=1, interval=0.0, button='left', *a, **k):
            if x is not None and y is not None:
                for _ in range(int(clicks)): _send(x, y, left=(button != 'right'))
                return None
            return self._orig['click'](x=x, y=y, clicks=clicks, interval=interval, button=button, *a, **k) if \
                self._orig['click'] else None

        def _rclk(x=None, y=None, *a, **k):
            if x is not None and y is not None: _send(x, y, left=False); return None
            return self._orig['rightClick'](x=x, y=y, *a, **k) if self._orig['rightClick'] else None

        def _refresh():
            if not (self._upg and self._orig['screenshot']): return
            x, y, w, h = self._upg;
            self._upg_img = self._orig['screenshot'](region=(x, y, w, h));
            self._ts = _t.time() * 1000.0

        def _shot(*args, **kwargs):
            reg = kwargs.get('region', None)
            if not reg or not self._upg: return self._orig['screenshot'](*args, **kwargs)
            ux, uy, uw, uh = self._upg;
            rx, ry, rw, rh = [int(v) for v in reg]
            inside = (rx >= ux and ry >= uy and rx + rw <= ux + uw and ry + rh <= uy + uh)
            if not inside: return self._orig['screenshot'](*args, **kwargs)
            now = _t.time() * 1000.0
            if (self._upg_img is None) or (now - self._ts > float(self.g.get('ROI_STALE_MS', 120))):
                _refresh()
            try:
                return self._upg_img.crop((rx - ux, ry - uy, rx - ux + rw, ry - uy + rh))
            except Exception:
                return self._orig['screenshot'](*args, **kwargs)

        if self._orig['moveTo']: _pya.moveTo = _mv
        if self._orig['moveRel']: _pya.moveRel = _mvr
        if self._orig['click']: _pya.click = _clk
        if self._orig['rightClick']: _pya.rightClick = _rclk
        if self._orig['screenshot']: _pya.screenshot = _shot
        self._ok = True;
        return self

    def __exit__(self, et, ev, tb):
        try:
            _pya.PAUSE = self._orig['PAUSE'];
            _pya.MINIMUM_SLEEP = self._orig['MINIMUM_SLEEP'];
            _pya.MINIMUM_DURATION = self._orig['MINIMUM_DURATION']
            if self._orig['moveTo']: _pya.moveTo = self._orig['moveTo']
            if self._orig['moveRel']: _pya.moveRel = self._orig['moveRel']
            if self._orig['click']: _pya.click = self._orig['click']
            if self._orig['rightClick']: _pya.rightClick = self._orig['rightClick']
            if self._orig['screenshot']: _pya.screenshot = self._orig['screenshot']
        except Exception:
            pass
        if self._save_mouse is not None: globals()['mouse_hizi'] = self._save_mouse
        if self._save_tus is not None: globals()['tus_hizi'] = self._save_tus
        return False


def _yama__wrap(f):
    def _w(*a, **k):
        if not globals().get('UPG_USE_FAST_MOUSE', True): return f(*a, **k)
        with _AnvilFastMode():
            return f(*a, **k)

    return _w


def __yama_install_fast_anvil():
    global _YAMA_FAST_ANVIL_OK
    if _YAMA_FAST_ANVIL_OK: return True
    g = globals();
    changed = 0
    for name in ('perform_upgrade_on_slot', 'open_upgrade_screen_fast'):
        fn = g.get(name, None)
        if callable(fn):
            try:
                g[name] = _yama__wrap(fn);
                changed += 1
            except Exception as e:
                print('[YAMA FAST]', name, 'wrap hatası:', e)
    _YAMA_FAST_ANVIL_OK = True
    print('[YAMA FAST] aktif. Sarılan fonk=', changed, '| confirm(ms)=', globals().get('ANVIL_CONFIRM_WAIT_MS'))
    return True


__yama_install_fast_anvil()


# === [YAMA FAST ANVIL] end ===


# === [YAMA FAST GUI] start ===
# Hız / Anvil / PREC 598 / Cache / QC ayar penceresi (tek pencerede)
def _speed_cfg_path():
    try:
        return PERSIST_PATH('speed_config.json')  # Uygulama verileri altında
    except Exception:
        import os
        return os.path.join(os.path.expanduser('~'), 'speed_config.json')


def load_speed_config():
    try:
        import json, os
        p = _speed_cfg_path()
        if not os.path.exists(p): return False
        with open(p, 'r', encoding='utf-8') as f:
            conf = json.load(f)
        for k in ('UPG_USE_FAST_MOUSE', 'UPG_MOUSE_HIZI', 'UPG_TUS_HIZI',
                  'ANVIL_CONFIRM_WAIT_MS', 'ROI_STALE_MS',
                  'PREC_Y598_TOWN_HARDLOCK', 'PREC_Y598_DBLCLICK', 'PREC_Y598_CLICK_POS',
                  'PREC_Y598_CLICK_DELAY', 'PREC_Y598_CLICK_COUNT',
                  'ENABLE_YAMA_SLOT_CACHE', 'MAX_CACHE_SIZE_PER_SNAPSHOT',
                  'YAMA_QC_ENABLE', 'YAMA_QC_STD_MIN', 'YAMA_QC_EDGE_MIN', 'YAMA_QC_HEADER_RATIO',
                  'GUI_AUTO_OPEN_SPEED'):
            if k in conf: globals()[k] = conf[k]
        return True
    except Exception as e:
        print('[GUI] speed_config yüklenemedi:', e);
        return False


def save_speed_config():
    try:
        import json, os
        p = _speed_cfg_path()
        try:
            with open(p, 'r', encoding='utf-8') as f:
                conf = json.load(f)
        except Exception:
            conf = {}
        for k in ('UPG_USE_FAST_MOUSE', 'UPG_MOUSE_HIZI', 'UPG_TUS_HIZI',
                  'ANVIL_CONFIRM_WAIT_MS', 'ROI_STALE_MS',
                  'PREC_Y598_TOWN_HARDLOCK', 'PREC_Y598_DBLCLICK', 'PREC_Y598_CLICK_POS',
                  'PREC_Y598_CLICK_DELAY', 'PREC_Y598_CLICK_COUNT',
                  'ENABLE_YAMA_SLOT_CACHE', 'MAX_CACHE_SIZE_PER_SNAPSHOT',
                  'YAMA_QC_ENABLE', 'YAMA_QC_STD_MIN', 'YAMA_QC_EDGE_MIN', 'YAMA_QC_HEADER_RATIO',
                  'GUI_AUTO_OPEN_SPEED'):
            conf[k] = globals().get(k)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, 'w', encoding='utf-8') as f:
            import json;
            json.dump(conf, f, indent=2, ensure_ascii=False)
        print('[GUI] speed_config kaydedildi:', p);
        return True
    except Exception as e:
        print('[GUI] speed_config kaydetme hata:', e);
        return False


# Varsayılanları güvenle oluştur (globalde yoksa):
UPG_USE_FAST_MOUSE = bool(globals().get('UPG_USE_FAST_MOUSE', True))  # hızlı mouse/tuş
UPG_MOUSE_HIZI = float(globals().get('UPG_MOUSE_HIZI', 0.015))  # anvil mouse hızı
UPG_TUS_HIZI = float(globals().get('UPG_TUS_HIZI', 0.020))  # anvil tuş hızı
ANVIL_CONFIRM_WAIT_MS = int(globals().get('ANVIL_CONFIRM_WAIT_MS', 45))  # confirm bekleme (ms)
ROI_STALE_MS = int(globals().get('ROI_STALE_MS', 120))  # ROI bayatlama (ms)

# PREC_MOVE_Y_598 özel istek:
PREC_Y598_TOWN_HARDLOCK = bool(globals().get('PREC_Y598_TOWN_HARDLOCK', True))  # stage'de town kilit
PREC_Y598_DBLCLICK = bool(globals().get('PREC_Y598_DBLCLICK', True))  # çift sol tık
PREC_Y598_CLICK_POS = tuple(globals().get('PREC_Y598_CLICK_POS', (200, 107)))  # tık pozisyonu
PREC_Y598_CLICK_DELAY = float(globals().get('PREC_Y598_CLICK_DELAY', 0.1))  # tık arası
PREC_Y598_CLICK_COUNT = int(globals().get('PREC_Y598_CLICK_COUNT', 2))  # tık adedi

# Cache & QC:
ENABLE_YAMA_SLOT_CACHE = bool(globals().get('ENABLE_YAMA_SLOT_CACHE', True))
MAX_CACHE_SIZE_PER_SNAPSHOT = int(globals().get('MAX_CACHE_SIZE_PER_SNAPSHOT', 512))
YAMA_QC_ENABLE = bool(globals().get('YAMA_QC_ENABLE', True))
YAMA_QC_STD_MIN = float(globals().get('YAMA_QC_STD_MIN', 10.0))
YAMA_QC_EDGE_MIN = float(globals().get('YAMA_QC_EDGE_MIN', 0.002))
YAMA_QC_HEADER_RATIO = float(globals().get('YAMA_QC_HEADER_RATIO', 0.28))
GUI_AUTO_OPEN_SPEED = bool(globals().get('GUI_AUTO_OPEN_SPEED', False))


def run_speed_gui():
    try:
        import tkinter as tk
        from tkinter import ttk, messagebox
    except Exception as e:
        print('[GUI] tkinter yok:', e);
        return False

    load_speed_config()

    r = tk.Tk();
    r.title('Hız / Anvil / PREC 598 Ayarları')
    frm = ttk.Frame(r, padding=8);
    frm.pack(fill='both', expand=True)

    # yardımcı: label+entry
    def entry(label, value, width=10):
        ttk.Label(frm, text=label).pack(anchor='w')
        v = tk.StringVar(value=str(value))
        ttk.Entry(frm, textvariable=v, width=width).pack(anchor='w', pady=(0, 4))
        return v

    # --- Hız/Anvil ---
    ttk.Label(frm, text='Anvil Hız Ayarları', font=('Segoe UI', 10, 'bold')).pack(anchor='w', pady=(0, 4))
    var_fast = tk.BooleanVar(value=bool(globals().get('UPG_USE_FAST_MOUSE', True)))
    ttk.Checkbutton(frm, text='Anvil için hızlı Mouse/Tuş (UPG_USE_FAST_MOUSE)', variable=var_fast).pack(anchor='w')
    v_mouse = entry('UPG_MOUSE_HIZI', globals().get('UPG_MOUSE_HIZI', 0.015))
    v_key = entry('UPG_TUS_HIZI', globals().get('UPG_TUS_HIZI', 0.020))
    v_conf = entry('ANVIL_CONFIRM_WAIT_MS', globals().get('ANVIL_CONFIRM_WAIT_MS', 45))
    v_roi = entry('ROI_STALE_MS', globals().get('ROI_STALE_MS', 120))

    # --- PREC_MOVE_Y_598 ---
    ttk.Label(frm, text='PREC_MOVE_Y_598', font=('Segoe UI', 10, 'bold')).pack(anchor='w', pady=(8, 4))
    var_hlock = tk.BooleanVar(value=bool(globals().get('PREC_Y598_TOWN_HARDLOCK', True)))
    ttk.Checkbutton(frm, text='Stage başında TOWN HardLock (oyun kapanana kadar town kapalı)', variable=var_hlock).pack(
        anchor='w')
    var_dbl = tk.BooleanVar(value=bool(globals().get('PREC_Y598_DBLCLICK', True)))
    ttk.Checkbutton(frm, text='Stage başında çift sol tık', variable=var_dbl).pack(anchor='w')
    v_x = entry('PREC_Y598_CLICK_POS_X', globals().get('PREC_Y598_CLICK_POS', (200, 107))[0])
    v_y = entry('PREC_Y598_CLICK_POS_Y', globals().get('PREC_Y598_CLICK_POS', (200, 107))[1])
    v_dt = entry('PREC_Y598_CLICK_DELAY', globals().get('PREC_Y598_CLICK_DELAY', 0.1))
    v_ct = entry('PREC_Y598_CLICK_COUNT', globals().get('PREC_Y598_CLICK_COUNT', 2))

    # --- Cache & QC ---
    ttk.Label(frm, text='+7 Cache / QC', font=('Segoe UI', 10, 'bold')).pack(anchor='w', pady=(8, 4))
    var_cache = tk.BooleanVar(value=bool(globals().get('ENABLE_YAMA_SLOT_CACHE', True)))
    ttk.Checkbutton(frm, text='+7 Cache Aktif (ENABLE_YAMA_SLOT_CACHE)', variable=var_cache).pack(anchor='w')
    v_max = entry('MAX_CACHE_SIZE_PER_SNAPSHOT', globals().get('MAX_CACHE_SIZE_PER_SNAPSHOT', 512))
    var_qc = tk.BooleanVar(value=bool(globals().get('YAMA_QC_ENABLE', True)))
    ttk.Checkbutton(frm, text='Quick-Check Aktif (YAMA_QC_ENABLE)', variable=var_qc).pack(anchor='w')
    v_std = entry('YAMA_QC_STD_MIN', globals().get('YAMA_QC_STD_MIN', 10.0))
    v_edge = entry('YAMA_QC_EDGE_MIN', globals().get('YAMA_QC_EDGE_MIN', 0.002))
    v_hdr = entry('YAMA_QC_HEADER_RATIO', globals().get('YAMA_QC_HEADER_RATIO', 0.28))

    var_auto = tk.BooleanVar(value=bool(globals().get('GUI_AUTO_OPEN_SPEED', False)))
    ttk.Checkbutton(frm, text='Program açılışında bu pencereyi otomatik aç (GUI_AUTO_OPEN_SPEED)',
                    variable=var_auto).pack(anchor='w', pady=(4, 0))

    def do_save():
        try:
            globals()['UPG_USE_FAST_MOUSE'] = bool(var_fast.get())
            globals()['UPG_MOUSE_HIZI'] = float(v_mouse.get())
            globals()['UPG_TUS_HIZI'] = float(v_key.get())
            globals()['ANVIL_CONFIRM_WAIT_MS'] = int(float(v_conf.get()))
            globals()['ROI_STALE_MS'] = int(float(v_roi.get()))
            globals()['PREC_Y598_TOWN_HARDLOCK'] = bool(var_hlock.get())
            globals()['PREC_Y598_DBLCLICK'] = bool(var_dbl.get())
            globals()['PREC_Y598_CLICK_POS'] = (int(float(v_x.get())), int(float(v_y.get())))
            globals()['PREC_Y598_CLICK_DELAY'] = float(v_dt.get())
            globals()['PREC_Y598_CLICK_COUNT'] = int(float(v_ct.get()))
            globals()['ENABLE_YAMA_SLOT_CACHE'] = bool(var_cache.get())
            globals()['MAX_CACHE_SIZE_PER_SNAPSHOT'] = int(float(v_max.get()))
            globals()['YAMA_QC_ENABLE'] = bool(var_qc.get())
            globals()['YAMA_QC_STD_MIN'] = float(v_std.get())
            globals()['YAMA_QC_EDGE_MIN'] = float(v_edge.get())
            globals()['YAMA_QC_HEADER_RATIO'] = float(v_hdr.get())
            globals()['GUI_AUTO_OPEN_SPEED'] = bool(var_auto.get())
            save_speed_config()
            try:
                messagebox.showinfo('Kaydedildi', 'Ayarlar kaydedildi.')
            except Exception:
                pass
        except Exception as e:
            try:
                messagebox.showerror('Hata', str(e))
            except Exception:
                print('[GUI] save hata:', e)

    btnf = ttk.Frame(frm);
    btnf.pack(fill='x', pady=(8, 0))
    ttk.Button(btnf, text='Kaydet', command=do_save).pack(side='left')
    ttk.Button(btnf, text='Kapat', command=r.destroy).pack(side='left', padx=6)

    r.mainloop();
    return True


# Pencereyi açma tercihine göre otomatik aç
try:
    load_speed_config()
    if bool(globals().get('GUI_AUTO_OPEN_SPEED', False)):
        try:
            run_speed_gui()
        except Exception as _e:
            print('[GUI] hız penceresi açılamadı:', _e)
except Exception as _e:
    print('[GUI] speed_config otoload hata:', _e)


def _build_speed_prec598_tab(frm, tk, ttk):
    """Hız/Anvil/PREC 598 — Hover Guard + ROI; park X/Y alanları görünür."""

    def entry(lbl, val, w=10):
        ttk.Label(frm, text=lbl).pack(anchor='w')
        import tkinter as tkX;
        v = tkX.StringVar(value=str(val))
        ttk.Entry(frm, textvariable=v, width=w).pack(anchor='w', pady=(0, 4));
        return v

    ttk.Label(frm, text='Hover Guard', font=('Segoe UI', 10, 'bold')).pack(anchor='w', pady=(0, 4))
    var_hg = tk.BooleanVar(value=bool(globals().get('ANVIL_HOVER_GUARD', True)))
    ttk.Checkbutton(frm, text='Confirm sonrası fareyi park et (ANVIL_HOVER_GUARD)', variable=var_hg).pack(anchor='w')
    px, py = globals().get('ANVIL_MOUSE_PARK_POS', (5, 5))
    v_px = entry('ANVIL_MOUSE_PARK_POS_X', px);
    v_py = entry('ANVIL_MOUSE_PARK_POS_Y', py)
    v_ps = entry('ANVIL_HOVER_CLEAR_SEC (sn)', globals().get('ANVIL_HOVER_CLEAR_SEC', 0.035))

    ttk.Label(frm, text='ROI/Anvil Hız', font=('Segoe UI', 10, 'bold')).pack(anchor='w', pady=(8, 4))
    v_roi = entry('ROI_STALE_MS', globals().get('ROI_STALE_MS', 120))

    # Yardımcı: Pozisyon Yakala & Test Park
    btn = ttk.Frame(frm);
    btn.pack(fill='x', pady=(6, 0))

    def capture_pos():
        try:
            import time, pyautogui as pg;
            print('[GUI] Pozisyon yakalama 3 sn');
            time.sleep(3.0)
            pos = pg.position();
            v_px.set(str(int(pos.x)));
            v_py.set(str(int(pos.y)));
            print('[GUI] Poz:', pos.x, pos.y)
        except Exception as e:
            print('[GUI] capture hata:', e)

    def test_park():
        try:
            import time, pyautogui as pg
            pg.moveTo(int(float(v_px.get())), int(float(v_py.get())), duration=0);
            time.sleep(0.03);
            print('[GUI] Park OK')
        except Exception as e:
            print('[GUI] park hata:', e)

    ttk.Button(btn, text='Pozisyon Yakala (3 sn)', command=capture_pos).pack(side='left')
    ttk.Button(btn, text='Test Park', command=test_park).pack(side='left', padx=6)

    # Kaydet
    def do_save():
        try:
            globals()['ANVIL_HOVER_GUARD'] = bool(var_hg.get())
            globals()['ANVIL_MOUSE_PARK_POS'] = (int(float(v_px.get())), int(float(v_py.get())))
            globals()['ANVIL_HOVER_CLEAR_SEC'] = float(v_ps.get())
            globals()['ROI_STALE_MS'] = int(float(v_roi.get()))
            try:
                yama_save_extra_cfg()
            except Exception as _e:
                print('[GUI] save merge hata:', _e)
            print('[GUI] Kaydedildi.')
        except Exception as e:
            print('[GUI] save hata:', e)

    f = ttk.Frame(frm);
    f.pack(fill='x', pady=(8, 0));
    ttk.Button(f, text='Kaydet', command=do_save).pack(side='left')
    return True


def NPC_POSTBUY_D_WHILE_W():
    """NPC sonrası 795→814 rotasında W'ye basılıyken kısa bir SAĞ dönüş yap (yön hizası)."""
    try:
        prof = globals().get("SPEED_PROFILE", "BALANCED")
        dur = {"FAST": 0.18, "BALANCED": 0.23, "SAFE": 0.28}.get(prof, 0.23)
    except Exception:
        prof, dur = "BALANCED", 0.23
    print("[STAGE] NPC_POSTBUY_D_WHILE_W")
    try:
        import pyautogui as _pg, time as _t
        _pg.keyDown("w");
        _pg.keyDown("d");
        _t.sleep(dur);
        _pg.keyUp("d");
        _pg.keyUp("w")
    except Exception as _e:
        try:
            # Fallback: sadece D'ye kısa vur
            import pyautogui as _pg, time as _t
            _pg.keyDown("d");
            _t.sleep(max(0.12, dur - 0.08));
            _pg.keyUp("d")
        except Exception as _e2:
            print("[NPC_POSTBUY] D while W yapılamadı:", _e2)


# [YAMA] Hover Guard varsayılanları (Confirm sonrası fareyi park et)
ANVIL_HOVER_GUARD = bool(globals().get('ANVIL_HOVER_GUARD', True))  # Aç/Kapa
ANVIL_MOUSE_PARK_POS = tuple(globals().get('ANVIL_MOUSE_PARK_POS', (5, 5)))  # Park X,Y
ANVIL_HOVER_CLEAR_SEC = float(globals().get('ANVIL_HOVER_CLEAR_SEC', 0.035))  # Bekleme (sn)


# [YAMA] Confirm sonrası fareyi kısa süre park ederek tooltip/animasyonu kes
def hover_guard():
    if not bool(globals().get('ANVIL_HOVER_GUARD', True)): return
    try:
        x, y = globals().get('ANVIL_MOUSE_PARK_POS', (5, 5))
        try:
            mouse_move(int(x), int(y))  # varsa kendi mouse_move sarmalayıcın
        except Exception:
            import pyautogui as _pg
            _pg.moveTo(int(x), int(y), duration=0)
        import time as _t
        _t.sleep(float(globals().get('ANVIL_HOVER_CLEAR_SEC', 0.035)))
    except Exception as _e:
        try:
            print('[HOVER] guard hata:', _e)
        except:
            pass


# [YAMA] Hover Guard ayarlarını speed_config.json ile merge et
def _yama_speed_cfg_path():
    try:
        return _speed_cfg_path()  # projendeki fonksiyon varsa onu kullan
    except Exception:
        import os
        return os.path.join(os.path.expanduser('~'), 'speed_config.json')


def yama_load_extra_cfg():
    import json, os
    p = _yama_speed_cfg_path()
    if not os.path.exists(p): return False
    try:
        with open(p, 'r', encoding='utf-8') as f:
            cfg = json.load(f)
        if 'ANVIL_HOVER_GUARD' in cfg: globals()['ANVIL_HOVER_GUARD'] = bool(cfg['ANVIL_HOVER_GUARD'])
        if 'ANVIL_MOUSE_PARK_POS' in cfg:
            try:
                xx, yy = cfg['ANVIL_MOUSE_PARK_POS'][:2]
                globals()['ANVIL_MOUSE_PARK_POS'] = (int(xx), int(yy))
            except:
                pass
        if 'ANVIL_HOVER_CLEAR_SEC' in cfg: globals()['ANVIL_HOVER_CLEAR_SEC'] = float(cfg['ANVIL_HOVER_CLEAR_SEC'])
        if 'ROI_STALE_MS' in cfg: globals()['ROI_STALE_MS'] = int(cfg['ROI_STALE_MS'])
        return True
    except Exception as e:
        print('[YAMA CFG] load hata:', e);
        return False


def yama_save_extra_cfg():
    import json, os
    p = _yama_speed_cfg_path()
    try:
        try:
            with open(p, 'r', encoding='utf-8') as f:
                cfg = json.load(f)
        except Exception:
            cfg = {}
        cfg.update({
            'ANVIL_HOVER_GUARD': bool(globals().get('ANVIL_HOVER_GUARD', True)),
            'ANVIL_MOUSE_PARK_POS': list(globals().get('ANVIL_MOUSE_PARK_POS', (5, 5))),
            'ANVIL_HOVER_CLEAR_SEC': float(globals().get('ANVIL_HOVER_CLEAR_SEC', 0.035)),
            'ROI_STALE_MS': int(globals().get('ROI_STALE_MS', 120)),
        })
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, 'w', encoding='utf-8') as f:
            json.dump(_serialize_config(cfg), f, indent=2, ensure_ascii=False)
        print('[YAMA CFG] kaydedildi:', p);
        return True
    except Exception as e:
        print('[YAMA CFG] save hata:', e);
        return False


# [YAMA] +N hover hızlı mod ayarları
PLUSN_FAST_MODE = bool(globals().get('PLUSN_FAST_MODE', True))
PLUSN_HOVER_SAMPLES = int(globals().get('PLUSN_HOVER_SAMPLES', 1))
PLUSN_WAIT_BETWEEN = float(globals().get('PLUSN_WAIT_BETWEEN', 0.06))
PLUSN_USE_OCR_FALLBACK = bool(globals().get('PLUSN_USE_OCR_FALLBACK', False))
TOOLTIP_GRAB_WITH_MSS = bool(globals().get('TOOLTIP_GRAB_WITH_MSS', True))


# [YAMA] Tooltip ROI hızlı yakalama (MSS varsa onu kullan)
def _grab_tooltip_roi_near_mouse_fast(win, roi_w=TOOLTIP_ROI_W, roi_h=TOOLTIP_ROI_H):
    try:
        if not bool(globals().get('TOOLTIP_GRAB_WITH_MSS', True)):
            raise RuntimeError("MSS devre dışı")
        import mss, numpy as _np, cv2
        # Mevcut mouse pozisyonundan tepeye doğru roi
        class _PT:
            pass

        import ctypes
        pt = _PT();
        pt.x = ctypes.c_long();
        pt.y = ctypes.c_long()
        ctypes.windll.user32.GetCursorPos(ctypes.byref(pt))
        mx, my = int(pt.x.value), int(pt.y.value)
        Lw, Tw, Rw, Bw = win.left, win.top, win.right, win.bottom
        half = roi_w // 2;
        x1 = mx - half;
        y1 = my - (roi_h + TOOLTIP_OFFSET_Y);
        x2 = x1 + roi_w;
        y2 = y1 + roi_h
        x1 = max(Lw, x1);
        y1 = max(Tw, y1);
        x2 = min(Rw, x2);
        y2 = min(Bw, y2)
        if x2 - x1 < 40 or y2 - y1 < 40: return None
        with mss.mss() as sct:
            mon = {"left": x1, "top": y1, "width": x2 - x1, "height": y2 - y1}
            im = _np.array(sct.grab(mon))[:, :, :3]
            import cv2 as _cv2
            return _cv2.cvtColor(im, _cv2.COLOR_BGR2GRAY)
    except Exception:
        return None


# >>> [YAMA:GUI_DEFAULTS]

try:
    # ==== [YAMA GUI VARS] Eğer yoksa global varsayılanları tanımla ====
    _YAMA_GUI_DEFAULTS = {
        # --- NPC Alış (Fabric/Linen) ---
        "BUY_MODE": "FABRIC",  # FABRIC | LINEN
        "BUY_TURNS": 2,  # Kaç tur satın alma yapılacak (ör. 2 tur = 28 item)
        "NPC_MENU_PAGE2_POS": (968, 328),  # Sayfa 2 geçiş koordinatı
        "NPC_CONTEXT_RIGHTCLICK_POS": (526, 431),  # Satıcı panelini açtıran sağ tık noktası
        "NPC_OPEN_TEXT_TEMPLATE_PATH": "open_vendor.png",  # Açık yazısı/ikon şablonu
        "NPC_OPEN_MATCH_THRESHOLD": 0.70,
        "NPC_OPEN_FIND_TIMEOUT": 4.0,
        "NPC_OPEN_SCALES": [0.8, 1.0, 1.2],

        # Fabric steps (MAX_STEPS_PER_MODE kadar satır beklenir)
        "FABRIC_STEPS": [(671, 459, 1, "right")] * 5,
        # Linen steps (MAX_STEPS_PER_MODE kadar satır)
        "LINEN_STEPS": [(671, 459, 1, "right")] * 5,

        # Scroll/adet örnek alanlar (opsiyonel)
        "SCROLL_VENDOR_MID_POS": (747, 358),  # Scroll butonu / orta panel
        "SCROLL_ALIM_ADET": 2,  # Low scroll adet
        "SCROLL_MID_ALIM_ADET": 2,  # Mid scroll adet

        # --- Rota/Koordinat ---
        "TARGET_NPC_X": 766,  # NPC hedef X
        "NPC_SEEK_TIMEOUT": 6.0,
        "NPC_POSTBUY_TARGET_X1": 795,
        "NPC_POSTBUY_A_WHILE_W_DURATION": 0.35,
        "NPC_POSTBUY_TARGET_X2": 814,
        "NPC_POSTBUY_SECOND_A_DURATION": 0.20,
        "NPC_POSTBUY_FINAL_W_DURATION": 0.80,
        "TARGET_Y_AFTER_TURN": 597,
        "TURN_LEFT_SEC": 1.36,
        "NPC_GIDIS_SURESI": 5.0,

        # --- Anvil/Upgrade ---
        "BASMA_HAKKI": 31,
        "SCROLL_POS": (671, 459),
        "UPGRADE_BTN_POS": (747, 358),
        "CONFIRM_BTN_POS": (737, 479),
        "UPG_STEP_DELAY": 0.10,
        "SCROLL_PANEL_REOPEN_MAX": 10,
        "SCROLL_PANEL_REOPEN_DELAY": 0.10,

        # --- Boş slot tespiti ---
        "EMPTY_SLOT_TEMPLATE_PATH": "empty_slot.png",
        "EMPTY_SLOT_MATCH_THRESHOLD": 0.85,
        "FALLBACK_MEAN_THRESHOLD": 55.0,
        "FALLBACK_EDGE_DENSITY_THRESHOLD": 0.030,
        "EMPTY_SLOT_THRESHOLD": 24,

        # --- OCR/ROI & Önbellek ---
        "ROI_STALE_MS": 120,
        "UPG_ROI_STALE_MS": 120,
        "ENABLE_YAMA_SLOT_CACHE": True,
        "MAX_CACHE_SIZE_PER_SNAPSHOT": 512,

        # --- Hız Profili ---
        "AUTO_SPEED_PROFILE": "BALANCED",  # FAST | BALANCED | SAFE
        "AUTO_TUNE_INTERVAL": 30.0,
        "SPEED_PROFILE": "BALANCED",  # el ile zorla

        # --- +7 Tarama / Sayaç ---
        "PLUS7_START_FROM_TURN_AFTER_PURCHASE": 4,
        "GLOBAL_CYCLE": 1,
        "NEXT_PLUS7_CHECK_AT": 1,

        # --- Güvenlik/Town ---
        "TOWN_MIN_INTERVAL_SEC": 1.2,
    }
    # Çalışan kodda varsa mevcut FABRIC/LINEN_STEPS değerlerini al ve defaults'u güncelle
    if "FABRIC_STEPS" in globals() and isinstance(FABRIC_STEPS, list) and FABRIC_STEPS:
        _YAMA_GUI_DEFAULTS["FABRIC_STEPS"] = [(int(x), int(y), int(c), str(b)) for (x, y, c, b) in FABRIC_STEPS[:5]]
    if "LINEN_STEPS" in globals() and isinstance(LINEN_STEPS, list) and LINEN_STEPS:
        _YAMA_GUI_DEFAULTS["LINEN_STEPS"] = [(int(x), int(y), int(c), str(b)) for (x, y, c, b) in LINEN_STEPS[:5]]
except Exception as _e:
    print("[YAMA][GUI] Defaults init error:", _e)


# <<< [YAMA:GUI_DEFAULTS]


# >>> [YAMA:GUI_NPC_AND_OTHERS]

# ==== [YAMA GUI ENHANCER] NPC Alış + Tüm Değişkenler (Fabric/Linen/Anvil/OCR/Hız/vs.) ====
# Kısa: Tk GUI açıldığında "Gelişmiş" alana 4 yeni grup ekler, tooltip yazar, kaydet/uygula yapar.
# Not: Mevcut GUI yapınız ne olursa olsun; uygun bir kapsayıcı (LabelFrame/Notebook) aranır, yoksa basit frame eklenir.

def _y_safe_import_tk():
    try:
        import tkinter as tk
        from tkinter import ttk, messagebox
        return tk, ttk, messagebox
    except Exception as e:
        return None, None, None


def _y_coerce_tuple(val):
    # '(x,y)' veya 'x,y' veya [x,y] → (int,int)
    if isinstance(val, (list, tuple)) and len(val) == 2: return (int(val[0]), int(val[1]))
    s = str(val).strip().replace("(", "").replace(")", "").replace("[", "").replace("]", "")
    parts = [p.strip() for p in s.split(",") if p.strip()]
    if len(parts) >= 2:
        try:
            return (int(float(parts[0])), int(float(parts[1])))
        except:
            pass
    return (0, 0)


def _y_load_store():
    def _load():
        try:
            return load_config()
        except Exception as e:
            print('[GUI] config yüklenemedi:', e)
            return _schema_defaults(_BASE_CONFIG_DEFAULTS)

    def _save(data):
        try:
            cfg = data if isinstance(data, dict) else {}
            ok = save_config(cfg)
            if ok:
                print('[GUI] Ayarlar kaydedildi:', _MERDIVEN_CFG_PATH())
            else:
                print('[GUI] Kayıt hatası: save_config başarısız')
        except Exception as e:
            print('[GUI] Kayıt hatası:', e)

    return _load, _save


def _y_get_adv_container(root):
    # Gelişmiş alanı bulmaya çalış; bulamazsa root'a ekle
    # 1) isimli nitelikler
    for attr in ("adv_container", "advanced_container", "gelismis_kapsayici", "advanced_frame", "tum_ayarlar_frame"):
        if attr in globals():
            try:
                w = globals()[attr]
                if getattr(w, "winfo_exists", lambda: 0)(): return w
            except:
                pass
    # 2) LabelFrame text arama
    try:
        def _walk(w):
            if hasattr(w, "winfo_children"):
                for c in w.winfo_children():
                    yield c;
                    yield from _walk(c)

        for w in _walk(root):
            if w.winfo_class() in ("TLabelFrame", "Labelframe"):
                txt = getattr(w, "cget", lambda k: "")("text") or ""
                if any(s in str(txt).lower() for s in
                       ("gelişmiş", "gelismis", "tüm ayarlar", "tum ayarlar", "advanced")):
                    return w
    except:
        pass
    return root


class _YTooltip:
    def __init__(self, widget, text=""):
        self.widget = widget;
        self.text = text;
        self.tip = None
        widget.bind("<Enter>", self.show);
        widget.bind("<Leave>", self.hide)

    def show(self, e=None):
        if self.tip: return
        import tkinter as tk
        x, y, cx, cy = self.widget.bbox("insert") if hasattr(self.widget, "bbox") else (0, 0, 0, 0)
        x += self.widget.winfo_rootx() + 20;
        y += self.widget.winfo_rooty() + 20
        self.tip = tk.Toplevel(self.widget);
        self.tip.wm_overrideredirect(True);
        self.tip.wm_geometry("+%d+%d" % (x, y))
        label = tk.Label(self.tip, text=self.text, justify="left", relief="solid", borderwidth=1, background="#ffffe0")
        label.pack(ipadx=6, ipady=3)

    def hide(self, e=None):
        if self.tip: self.tip.destroy(); self.tip = None


def _y_make_entry(parent, label, init, width=8, tip=""):
    import tkinter as tk
    from tkinter import ttk
    frm = ttk.Frame(parent);
    frm.pack(fill="x", pady=1)
    ttk.Label(frm, text=label, width=26).pack(side="left")
    var = tk.StringVar(value=str(init));
    ent = ttk.Entry(frm, textvariable=var, width=width);
    ent.pack(side="left")
    if tip: _YTooltip(ent, tip)
    return var


def _y_make_combo(parent, label, values, init, tip=""):
    import tkinter as tk
    from tkinter import ttk
    frm = ttk.Frame(parent);
    frm.pack(fill="x", pady=1)
    ttk.Label(frm, text=label, width=26).pack(side="left")
    var = tk.StringVar(value=str(init));
    cb = ttk.Combobox(frm, values=values, textvariable=var, width=10, state="readonly");
    cb.pack(side="left")
    if tip: _YTooltip(cb, tip)
    return var


def _y_to_int(s, default=0):
    try:
        return int(float(str(s).strip()))
    except:
        return default


def _y_to_float(s, default=0.0):
    try:
        return float(str(s).strip())
    except:
        return default


def _y_build_and_attach_gui(root):
    tk, ttk, messagebox = _y_safe_import_tk()
    if not tk: return
    load, save = _y_load_store()
    data = load()

    # Varsayılanları getir
    gdef = globals().get("_YAMA_GUI_DEFAULTS", {}).copy()

    # --- Kapsayıcıyı bul
    adv = _y_get_adv_container(root)
    outer = ttk.LabelFrame(adv, text="Gelişmiş Ayarlar")
    outer.pack(fill="both", padx=6, pady=6, expand=True)

    nb = ttk.Notebook(outer)
    nb.pack(fill="both", expand=True)

    general_tab = ttk.Frame(nb)
    nb.add(general_tab, text="Genel Parametreler")
    npc_tab = ttk.Frame(nb)
    nb.add(npc_tab, text="NPC / Upgrade")

    general_vars: Dict[str, Any] = {}
    general_fields = list(_iter_config_fields())
    if general_fields:
        cgen = tk.Canvas(general_tab, highlightthickness=0)
        vs_gen = ttk.Scrollbar(general_tab, orient="vertical", command=cgen.yview)
        cgen.configure(yscrollcommand=vs_gen.set)
        general_frame = ttk.Frame(cgen)
        _general_window = cgen.create_window((0, 0), window=general_frame, anchor="nw")
        cgen.bind("<Configure>", lambda e: cgen.itemconfigure(_general_window, width=e.width))
        general_frame.bind("<Configure>", lambda e: cgen.configure(scrollregion=cgen.bbox("all")))
        cgen.pack(side="left", fill="both", expand=True)
        vs_gen.pack(side="right", fill="y")

        category_order = tuple(dict.fromkeys(f.category for f in general_fields))
        for category in category_order:
            fields = [f for f in general_fields if f.category == category]
            if not fields:
                continue
            grp = ttk.LabelFrame(general_frame, text=category)
            grp.pack(fill="x", padx=6, pady=4, anchor="n")
            grp.columnconfigure(1, weight=1)
            for row, field in enumerate(fields):
                val = data.get(field.key, field.default)
                if val is None:
                    val = field.default
                if field.field_type == "bool":
                    var = tk.BooleanVar(value=bool(val))
                    chk = ttk.Checkbutton(grp, text=field.label, variable=var)
                    chk.grid(row=row, column=0, sticky="w", padx=4, pady=2, columnspan=2)
                    if field.description:
                        _YTooltip(chk, field.description)
                    general_vars[field.key] = var
                    continue

                ttk.Label(grp, text=field.label).grid(row=row, column=0, sticky="w", padx=4, pady=2)
                display = _format_field_value(field, val)
                if field.choices:
                    var = tk.StringVar(value=str(display))
                    widget = ttk.Combobox(grp, textvariable=var, values=list(field.choices), state="readonly",
                                          width=field.width or 20)
                else:
                    var = tk.StringVar(value=str(display))
                    entry_kwargs = {"textvariable": var, "width": field.width or 24}
                    if field.secret:
                        entry_kwargs["show"] = "*"
                    widget = ttk.Entry(grp, **entry_kwargs)
                widget.grid(row=row, column=1, sticky="we", padx=4, pady=2)
                if field.description:
                    _YTooltip(widget, field.description)
                general_vars[field.key] = var

    lf = npc_tab

    # ========== 1) NPC Alış sekmesi ==========
    # BUY_MODE + BUY_TURNS + PAGE2_POS + CONTEXT + OPEN_* + SCROLL_* alanları
    buy_mode = _y_make_combo(lf, "Satın Alma Modu (BUY_MODE)", ["FABRIC", "LINEN"],
                             data.get("BUY_MODE", gdef.get("BUY_MODE")), "FABRIC=Kumaş; LINEN=Keten")
    buy_turns = _y_make_entry(lf, "Alış Tur Sayısı (BUY_TURNS)", data.get("BUY_TURNS", gdef.get("BUY_TURNS")),
                              tip="Her tur 14 adet; 2 tur ≈ 28 ürün")
    page2_pos = _y_make_entry(lf, "Sayfa 2 Pos (x,y)", data.get("NPC_MENU_PAGE2_POS", gdef.get("NPC_MENU_PAGE2_POS")),
                              tip="Örn: 968,328")

    ctx_pos = _y_make_entry(lf, "Sağ Tık Pos (x,y)",
                            data.get("NPC_CONTEXT_RIGHTCLICK_POS", gdef.get("NPC_CONTEXT_RIGHTCLICK_POS")),
                            tip="Satıcı panelini açtıran sağ tık noktası")
    tmpl_path = _y_make_entry(lf, "Açık Şablonu (PNG)",
                              data.get("NPC_OPEN_TEXT_TEMPLATE_PATH", gdef.get("NPC_OPEN_TEXT_TEMPLATE_PATH")),
                              tip="Aç/Konuş butonu yazısı/ikonu")
    match_thr = _y_make_entry(lf, "Eşik (MATCH_THRESHOLD)",
                              data.get("NPC_OPEN_MATCH_THRESHOLD", gdef.get("NPC_OPEN_MATCH_THRESHOLD")))
    find_to = _y_make_entry(lf, "Zaman Aşımı (FIND_TIMEOUT)",
                            data.get("NPC_OPEN_FIND_TIMEOUT", gdef.get("NPC_OPEN_FIND_TIMEOUT")))
    scales = _y_make_entry(lf, "Ölçekler (SCALES)",
                           ",".join([str(x) for x in data.get("NPC_OPEN_SCALES", gdef.get("NPC_OPEN_SCALES"))]))

    mid_pos = _y_make_entry(lf, "Scroll Orta Pos (x,y)",
                            data.get("SCROLL_VENDOR_MID_POS", gdef.get("SCROLL_VENDOR_MID_POS")))
    low_adet = _y_make_entry(lf, "Low Scroll Adet", data.get("SCROLL_ALIM_ADET", gdef.get("SCROLL_ALIM_ADET")))
    mid_adet = _y_make_entry(lf, "Mid Scroll Adet", data.get("SCROLL_MID_ALIM_ADET", gdef.get("SCROLL_MID_ALIM_ADET")))

    # Fabric/Linen Steps tabloları
    lf_f = ttk.LabelFrame(lf, text="Fabric Adımları (X, Y, Adet, Buton)")
    lf_f.pack(fill="x", padx=4, pady=4)
    lf_l = ttk.LabelFrame(lf, text="Linen Adımları (X, Y, Adet, Buton)")
    lf_l.pack(fill="x", padx=4, pady=4)

    f_vars = [];
    l_vars = []
    _fsteps = data.get("FABRIC_STEPS", gdef.get("FABRIC_STEPS"))
    _lsteps = data.get("LINEN_STEPS", gdef.get("LINEN_STEPS"))

    for i in range(1, 5 + 1):
        fx = _y_make_entry(lf_f, f"F{i} X", _fsteps[i - 1][0] if i - 1 < len(_fsteps) else 671);
        fy = _y_make_entry(lf_f, f"F{i} Y", _fsteps[i - 1][1] if i - 1 < len(_fsteps) else 459);
        fc = _y_make_entry(lf_f, f"F{i} Adet", _fsteps[i - 1][2] if i - 1 < len(_fsteps) else 1);
        fb = _y_make_combo(lf_f, f"F{i} Buton", ["left", "right"],
                           _fsteps[i - 1][3] if i - 1 < len(_fsteps) else "right")
        f_vars.append((fx, fy, fc, fb))

        lx = _y_make_entry(lf_l, f"L{i} X", _lsteps[i - 1][0] if i - 1 < len(_lsteps) else 671);
        ly = _y_make_entry(lf_l, f"L{i} Y", _lsteps[i - 1][1] if i - 1 < len(_lsteps) else 459);
        lc = _y_make_entry(lf_l, f"L{i} Adet", _lsteps[i - 1][2] if i - 1 < len(_lsteps) else 1);
        lb = _y_make_combo(lf_l, f"L{i} Buton", ["left", "right"],
                           _lsteps[i - 1][3] if i - 1 < len(_lsteps) else "right")
        l_vars.append((lx, ly, lc, lb))

    # ========== 2) Rota/Koordinat ==========
    lf_r = ttk.LabelFrame(lf, text="Rota / Koordinat")
    lf_r.pack(fill="x", padx=4, pady=4)
    target_x = _y_make_entry(lf_r, "TARGET_NPC_X", data.get("TARGET_NPC_X", gdef.get("TARGET_NPC_X")))
    seek_to = _y_make_entry(lf_r, "NPC_SEEK_TIMEOUT", data.get("NPC_SEEK_TIMEOUT", gdef.get("NPC_SEEK_TIMEOUT")))
    x1 = _y_make_entry(lf_r, "POSTBUY_TARGET_X1", data.get("NPC_POSTBUY_TARGET_X1", gdef.get("NPC_POSTBUY_TARGET_X1")))
    a1 = _y_make_entry(lf_r, "A_Bas_Sure1",
                       data.get("NPC_POSTBUY_A_WHILE_W_DURATION", gdef.get("NPC_POSTBUY_A_WHILE_W_DURATION")))
    x2 = _y_make_entry(lf_r, "POSTBUY_TARGET_X2", data.get("NPC_POSTBUY_TARGET_X2", gdef.get("NPC_POSTBUY_TARGET_X2")))
    a2 = _y_make_entry(lf_r, "A_Bas_Sure2",
                       data.get("NPC_POSTBUY_SECOND_A_DURATION", gdef.get("NPC_POSTBUY_SECOND_A_DURATION")))
    wf = _y_make_entry(lf_r, "Final_W_Sure",
                       data.get("NPC_POSTBUY_FINAL_W_DURATION", gdef.get("NPC_POSTBUY_FINAL_W_DURATION")))
    ty = _y_make_entry(lf_r, "TARGET_Y_AFTER_TURN", data.get("TARGET_Y_AFTER_TURN", gdef.get("TARGET_Y_AFTER_TURN")))
    tl = _y_make_entry(lf_r, "TURN_LEFT_SEC", data.get("TURN_LEFT_SEC", gdef.get("TURN_LEFT_SEC")))
    ngs = _y_make_entry(lf_r, "NPC_GIDIS_SURESI", data.get("NPC_GIDIS_SURESI", gdef.get("NPC_GIDIS_SURESI")))

    # ========== 3) Anvil/Upgrade ==========
    lf_u = ttk.LabelFrame(lf, text="Anvil / Upgrade")
    lf_u.pack(fill="x", padx=4, pady=4)
    basmahk = _y_make_entry(lf_u, "BASMA_HAKKI", data.get("BASMA_HAKKI", gdef.get("BASMA_HAKKI")))
    scpos = _y_make_entry(lf_u, "SCROLL_POS (x,y)", data.get("SCROLL_POS", gdef.get("SCROLL_POS")))
    upbtn = _y_make_entry(lf_u, "UPGRADE_BTN_POS (x,y)", data.get("UPGRADE_BTN_POS", gdef.get("UPGRADE_BTN_POS")))
    confbtn = _y_make_entry(lf_u, "CONFIRM_BTN_POS (x,y)", data.get("CONFIRM_BTN_POS", gdef.get("CONFIRM_BTN_POS")))
    stepd = _y_make_entry(lf_u, "UPG_STEP_DELAY", data.get("UPG_STEP_DELAY", gdef.get("UPG_STEP_DELAY")))
    scmax = _y_make_entry(lf_u, "SCROLL_PANEL_REOPEN_MAX",
                          data.get("SCROLL_PANEL_REOPEN_MAX", gdef.get("SCROLL_PANEL_REOPEN_MAX")))
    scdel = _y_make_entry(lf_u, "SCROLL_PANEL_REOPEN_DELAY",
                          data.get("SCROLL_PANEL_REOPEN_DELAY", gdef.get("SCROLL_PANEL_REOPEN_DELAY")))

    # Boş slot tespiti
    lf_b = ttk.LabelFrame(lf, text="Boş Slot Tespiti")
    lf_b.pack(fill="x", padx=4, pady=4)
    estpl = _y_make_entry(lf_b, "EMPTY_SLOT_TEMPLATE_PATH",
                          data.get("EMPTY_SLOT_TEMPLATE_PATH", gdef.get("EMPTY_SLOT_TEMPLATE_PATH")), width=24)
    esthr = _y_make_entry(lf_b, "EMPTY_SLOT_MATCH_THRESHOLD",
                          data.get("EMPTY_SLOT_MATCH_THRESHOLD", gdef.get("EMPTY_SLOT_MATCH_THRESHOLD")))
    fbmean = _y_make_entry(lf_b, "FALLBACK_MEAN_THRESHOLD",
                           data.get("FALLBACK_MEAN_THRESHOLD", gdef.get("FALLBACK_MEAN_THRESHOLD")))
    fbedge = _y_make_entry(lf_b, "FALLBACK_EDGE_DENSITY_THRESHOLD",
                           data.get("FALLBACK_EDGE_DENSITY_THRESHOLD", gdef.get("FALLBACK_EDGE_DENSITY_THRESHOLD")))
    estcnt = _y_make_entry(lf_b, "EMPTY_SLOT_THRESHOLD",
                           data.get("EMPTY_SLOT_THRESHOLD", gdef.get("EMPTY_SLOT_THRESHOLD")))

    # ========== 4) OCR/ROI & Önbellek ==========
    lf_o = ttk.LabelFrame(lf, text="OCR / ROI & Önbellek")
    lf_o.pack(fill="x", padx=4, pady=4)
    roi1 = _y_make_entry(lf_o, "ROI_STALE_MS", data.get("ROI_STALE_MS", gdef.get("ROI_STALE_MS")))
    roi2 = _y_make_entry(lf_o, "UPG_ROI_STALE_MS", data.get("UPG_ROI_STALE_MS", gdef.get("UPG_ROI_STALE_MS")))
    ycache = _y_make_combo(lf_o, "ENABLE_YAMA_SLOT_CACHE", ["True", "False"],
                           str(data.get("ENABLE_YAMA_SLOT_CACHE", gdef.get("ENABLE_YAMA_SLOT_CACHE"))))
    maxss = _y_make_entry(lf_o, "MAX_CACHE_SIZE_PER_SNAPSHOT",
                          data.get("MAX_CACHE_SIZE_PER_SNAPSHOT", gdef.get("MAX_CACHE_SIZE_PER_SNAPSHOT")))

    # ========== 5) Hız Profili ==========
    lf_h = ttk.LabelFrame(lf, text="Hız Profili")
    lf_h.pack(fill="x", padx=4, pady=4)
    auto = _y_make_combo(lf_h, "AUTO_SPEED_PROFILE", ["FAST", "BALANCED", "SAFE"],
                         data.get("AUTO_SPEED_PROFILE", gdef.get("AUTO_SPEED_PROFILE")))
    tune = _y_make_entry(lf_h, "AUTO_TUNE_INTERVAL", data.get("AUTO_TUNE_INTERVAL", gdef.get("AUTO_TUNE_INTERVAL")))
    forced = _y_make_combo(lf_h, "SPEED_PROFILE", ["FAST", "BALANCED", "SAFE"],
                           data.get("SPEED_PROFILE", gdef.get("SPEED_PROFILE")))

    # ========== 6) +7 Tarama ==========
    lf_p = ttk.LabelFrame(lf, text="+7 Tarama / Sayaçlar")
    lf_p.pack(fill="x", padx=4, pady=4)
    pstart = _y_make_entry(lf_p, "PLUS7_START_FROM_TURN_AFTER_PURCHASE",
                           data.get("PLUS7_START_FROM_TURN_AFTER_PURCHASE",
                                    gdef.get("PLUS7_START_FROM_TURN_AFTER_PURCHASE")))
    gcyc = _y_make_entry(lf_p, "GLOBAL_CYCLE", data.get("GLOBAL_CYCLE", gdef.get("GLOBAL_CYCLE")))
    n7at = _y_make_entry(lf_p, "NEXT_PLUS7_CHECK_AT", data.get("NEXT_PLUS7_CHECK_AT", gdef.get("NEXT_PLUS7_CHECK_AT")))

    # ========== 7) Güvenlik/Town ==========
    lf_t = ttk.LabelFrame(lf, text="Güvenlik / Town")
    lf_t.pack(fill="x", padx=4, pady=4)
    tmin = _y_make_entry(lf_t, "TOWN_MIN_INTERVAL_SEC",
                         data.get("TOWN_MIN_INTERVAL_SEC", gdef.get("TOWN_MIN_INTERVAL_SEC")))

    # --- Kaydet / Uygula butonları ---
    btns = ttk.Frame(outer);
    btns.pack(fill="x", pady=6)

    def _save_clicked():
        last_field = None
        try:
            general_updates = {}
            for field in _iter_config_fields():
                var = general_vars.get(field.key)
                if not var:
                    continue
                last_field = field
                if field.field_type == "bool":
                    value = bool(var.get())
                else:
                    raw = var.get()
                    text_val = str(raw).strip()
                    if text_val == "":
                        if field.field_type == "str":
                            value = ""
                        elif field.field_type in ("list_str", "list_pairs"):
                            value = []
                        else:
                            general_updates[field.key] = _serialize_value(field.default)
                            continue
                    else:
                        value = _parse_field_value(field, text_val)
                general_updates[field.key] = _serialize_value(value)

            last_field = None
            new = dict(general_updates)
            new.update({
                "BUY_MODE": buy_mode.get().strip(),
                "BUY_TURNS": _y_to_int(buy_turns.get(), 2),
                "NPC_MENU_PAGE2_POS": _y_coerce_tuple(page2_pos.get()),
                "NPC_CONTEXT_RIGHTCLICK_POS": _y_coerce_tuple(ctx_pos.get()),
                "NPC_OPEN_TEXT_TEMPLATE_PATH": tmpl_path.get().strip(),
                "NPC_OPEN_MATCH_THRESHOLD": _y_to_float(match_thr.get(), 0.7),
                "NPC_OPEN_FIND_TIMEOUT": _y_to_float(find_to.get(), 4.0),
                "NPC_OPEN_SCALES": [_y_to_float(s, 1.0) for s in str(scales.get()).split(",") if s.strip()],

                "SCROLL_VENDOR_MID_POS": _y_coerce_tuple(mid_pos.get()),
                "SCROLL_ALIM_ADET": _y_to_int(low_adet.get(), 2),
                "SCROLL_MID_ALIM_ADET": _y_to_int(mid_adet.get(), 2),

                "TARGET_NPC_X": _y_to_int(target_x.get(), 766),
                "NPC_SEEK_TIMEOUT": _y_to_float(seek_to.get(), 6.0),
                "NPC_POSTBUY_TARGET_X1": _y_to_int(x1.get(), 795),
                "NPC_POSTBUY_A_WHILE_W_DURATION": _y_to_float(a1.get(), 0.35),
                "NPC_POSTBUY_TARGET_X2": _y_to_int(x2.get(), 814),
                "NPC_POSTBUY_SECOND_A_DURATION": _y_to_float(a2.get(), 0.2),
                "NPC_POSTBUY_FINAL_W_DURATION": _y_to_float(wf.get(), 0.8),
                "TARGET_Y_AFTER_TURN": _y_to_int(ty.get(), 597),
                "TURN_LEFT_SEC": _y_to_float(tl.get(), 1.36),
                "NPC_GIDIS_SURESI": _y_to_float(ngs.get(), 5.0),

                "BASMA_HAKKI": _y_to_int(basmahk.get(), 31),
                "SCROLL_POS": _y_coerce_tuple(scpos.get()),
                "UPGRADE_BTN_POS": _y_coerce_tuple(upbtn.get()),
                "CONFIRM_BTN_POS": _y_coerce_tuple(confbtn.get()),
                "UPG_STEP_DELAY": _y_to_float(stepd.get(), 0.10),
                "SCROLL_PANEL_REOPEN_MAX": _y_to_int(scmax.get(), 10),
                "SCROLL_PANEL_REOPEN_DELAY": _y_to_float(scdel.get(), 0.10),

                "EMPTY_SLOT_TEMPLATE_PATH": estpl.get().strip(),
                "EMPTY_SLOT_MATCH_THRESHOLD": _y_to_float(esthr.get(), 0.85),
                "FALLBACK_MEAN_THRESHOLD": _y_to_float(fbmean.get(), 55.0),
                "FALLBACK_EDGE_DENSITY_THRESHOLD": _y_to_float(fbedge.get(), 0.030),
                "EMPTY_SLOT_THRESHOLD": _y_to_int(estcnt.get(), 24),

                "ROI_STALE_MS": _y_to_int(roi1.get(), 120),
                "UPG_ROI_STALE_MS": _y_to_int(roi2.get(), 120),
                "ENABLE_YAMA_SLOT_CACHE": str(ycache.get()) == "True",
                "MAX_CACHE_SIZE_PER_SNAPSHOT": _y_to_int(maxss.get(), 512),

                "AUTO_SPEED_PROFILE": auto.get().strip(),
                "AUTO_TUNE_INTERVAL": _y_to_float(tune.get(), 30.0),
                "SPEED_PROFILE": forced.get().strip(),

                "PLUS7_START_FROM_TURN_AFTER_PURCHASE": _y_to_int(pstart.get(), 4),
                "GLOBAL_CYCLE": _y_to_int(gcyc.get(), 1),
                "NEXT_PLUS7_CHECK_AT": _y_to_int(n7at.get(), 1),

                "TOWN_MIN_INTERVAL_SEC": _y_to_float(tmin.get(), 1.2),
            })

            fsteps = []
            lsteps = []
            for i, (fx, fy, fc, fb) in enumerate(f_vars, 1):
                fsteps.append((_y_to_int(fx.get(), 671), _y_to_int(fy.get(), 459), _y_to_int(fc.get(), 1), fb.get()))
            for i, (lx, ly, lc, lb) in enumerate(l_vars, 1):
                lsteps.append((_y_to_int(lx.get(), 671), _y_to_int(ly.get(), 459), _y_to_int(lc.get(), 1), lb.get()))
            new["FABRIC_STEPS"] = fsteps
            new["LINEN_STEPS"] = lsteps

            data.update(new)
            save(data)
            messagebox and messagebox.showinfo("Kaydedildi", "Ayarlar kaydedildi.")
        except Exception as e:
            if last_field is not None:
                label = getattr(last_field, 'label', last_field.key)
                err = f"{label}: {e}"
            else:
                err = str(e)
            print("[GUI] Kayıt hata:", err)
            messagebox and messagebox.showerror("Hata", err)

    def _apply_clicked():
        # Global değişkenlere uygula + listeleri rebuild et + wrapper'ları hazırla
        try:
            cfg = data  # kaydedilmiş (son)
            apply_config_values(cfg)
            g = globals()
            for k, v in cfg.items():
                if k in CONFIG_FIELD_MAP:
                    continue
                if k in ('ocr', 'timeouts', 'logging', 'special_deltas', 'gui', 'advanced'):
                    continue
                g[k] = v
            # Steps’i uygula
            g["FABRIC_STEPS"] = cfg.get("FABRIC_STEPS", g.get("FABRIC_STEPS", []))
            g["LINEN_STEPS"] = cfg.get("LINEN_STEPS", g.get("LINEN_STEPS", []))
            # Satın alma fonksiyonlarını sarmala (varsa)
            for name in ("buy_items_from_npc", "buy_items_from_npc_fabric", "buy_items_from_npc_linen"):
                if name in g and callable(g[name]) and not name.startswith("_Y_WRAP_"):
                    orig = g[name]

                    def _wrap(*a, __orig=orig, __cfg=cfg, **kw):
                        # Yola çıkmadan önce global'leri güncelle
                        gg = globals()
                        for k, v in __cfg.items(): gg[k] = v
                        gg["FABRIC_STEPS"] = __cfg.get("FABRIC_STEPS", gg.get("FABRIC_STEPS", []))
                        gg["LINEN_STEPS"] = __cfg.get("LINEN_STEPS", gg.get("LINEN_STEPS", []))
                        return __orig(*a, **kw)

                    g[name] = _wrap
            messagebox and messagebox.showinfo("Uygulandı", "Ayarlar global değişkenlere aktarıldı.")
        except Exception as e:
            print("[GUI] Apply hata:", e)
            messagebox and messagebox.showerror("Hata", str(e))

    ttk.Button(btns, text="Kaydet", command=_save_clicked).pack(side="left", padx=3)
    ttk.Button(btns, text="Uygula (Anında)", command=_apply_clicked).pack(side="left", padx=3)


def _y_install_gui_hook():
    tk, ttk, messagebox = _y_safe_import_tk()
    if not tk: return
    # Tk.__init__ wrap: Pencere kurulunca GUI eklentisini otomatik yerleştir
    if getattr(tk.Tk, "_yama_gui_wrapped", False): return
    _orig_init = tk.Tk.__init__

    def _init_wrap(self, *a, **k):
        _orig_init(self, *a, **k)
        try:
            self.after(200, lambda: _y_build_and_attach_gui(self))
        except Exception as e:
            print("[YAMA][GUI] attach hata:", e)

    tk.Tk.__init__ = _init_wrap
    tk.Tk._yama_gui_wrapped = True
    print("[GUI] YAMA GUI hook aktif.")


try:
    _y_install_gui_hook()
except Exception as _e:
    print("[YAMA][GUI] Hook hata:", _e)


# <<< [YAMA:GUI_NPC_AND_OTHERS]

def scroll_alma_stage_mid(w, adet=SCROLL_MID_ALIM_ADET):
    # YAMA: tek akış — önce exit, sonra relaunch, town ve NPC alış
    return _run_scroll_purchase_flow(w, adet, SCROLL_VENDOR_MID_POS, prefix="[SCROLL][MID]")


if __name__ == "__main__":
    _MERDIVEN_GUI_ENTRY(auto_open=True)
