#!/usr/bin/env python3
"""
launcher.py - menu startowe na Raspberry Pi (ekran dotykowy / mysz).

Uruchamia się automatycznie po starcie pulpitu i pozwala wybrać:
  DASHBOARD - zegary RPM / prędkość / czasy okrążeń (dane UDP z PC, port 5005)
  FILM      - odtwarzanie filmów z ~/filmy przez mpv (bez PC)
  LEDY      - kolory i animacje taśmy WS2812 (przez demona ledd.py, bez PC)

Film uruchamia się tylko z ekranu dotykowego. PC może przełączać dashboard komendami JSON (port 5005):
  {"cmd": "mode", "mode": "dashboard" | "menu"}
  {"cmd": "stop", "mode": "dashboard"}            # wróć do menu, jeśli dashboard jest aktywny
  {"cmd": "theme", "name": "warp" | "next" | "prev"}

Test na zwykłym komputerze w oknie:  LAUNCHER_WINDOW=800x480 python3 launcher.py
"""
import colorsys
import fcntl
import glob
import json
import math
import os
import shutil
import socket
import subprocess
import sys
import threading
import time

os.environ.setdefault("SDL_VIDEO_MINIMIZE_ON_FOCUS_LOSS", "0")  # nie chowaj okna, gdy odtwarzacz zabierze fokus
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
import pygame

try:
    import evdev                      # odczyt dotyku podczas filmu (python3-evdev)
    from evdev import ecodes
except ImportError:
    evdev = None

import layouts as Lay
import themes as T

# ===================== KONFIGURACJA =====================
UDP_PORT = 5005                       # telemetria + komendy z PC
LED_ADDR = ("127.0.0.1", 5006)        # demon ledd.py
VIDEO_DIR = os.path.expanduser("~/filmy")
VIDEO_EXT = (".mp4", ".mkv", ".mov", ".avi", ".webm", ".m4v")
FILM_LOOP = True                      # True = film w pętli
FILM_MUTE = False                     # True = bez dźwięku
AUTO_DASHBOARD = False                # True = w menu automatycznie przejdź do dashboardu, gdy przyjdą dane z PC
DATA_TIMEOUT = 3.0                    # po tylu sekundach bez danych dashboard pokazuje "czekam na dane"
FPS = 60                              # dashboard; menu i ustawienia odświeżają się rzadziej
MENU_FPS = 30
FILM_PLAYER = "vlc"                   # "vlc" (zalecane na RPi - sprzętowe dekodowanie), "mpv" albo "auto"
FILM_HANDOFF_DELAY = 2.0              # po ilu s od startu odtwarzacza launcher oddaje mu ekran
VLC_EXTRA_ARGS = []
MPV_EXTRA_ARGS = []
LOG_FILE = os.path.expanduser("~/.cache/pi-launcher.log")
SETTINGS_FILE = os.path.expanduser("~/.config/pi-launcher/settings.json")  # m.in. wybrana tarcza
# ========================================================

# Przy autostarcie nie ma terminala - zapisuj komunikaty do pliku
if sys.stdout is None or not sys.stdout.isatty():
    try:
        os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
        _log = open(LOG_FILE, "a", buffering=1, encoding="utf-8")
        sys.stdout = sys.stderr = _log
    except Exception:
        pass

# Tylko jedna kopia launchera naraz
_lock_file = open("/tmp/pi-launcher.lock", "w")
try:
    fcntl.flock(_lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
except OSError:
    print("Launcher już działa - wychodzę.")
    sys.exit(0)

print(f"=== launcher start {time.strftime('%Y-%m-%d %H:%M:%S')} ===")

# Progi skali obrotomierza: (maksymalne_RPM, krok_duzej_podzialki)
RPM_SCALES = [
    (8000, 1000), (10000, 1000), (12000, 2000), (16000, 2000), (20000, 2000),
    (25000, 5000), (30000, 5000), (40000, 5000), (50000, 5000),
    (60000, 10000), (80000, 10000), (100000, 10000),
]
# Progi skali prędkościomierza w MPH
SPEED_SCALES = [(220, 20), (260, 20), (300, 30), (360, 30)]
DEFAULT_RPM_SCALE = RPM_SCALES[0]
DEFAULT_SPEED_SCALE = SPEED_SCALES[0]
AUTO_RESET_SECONDS = 4.0

# Kolory
BG_COLOR = (12, 15, 20)
DIAL_BG = (22, 27, 36)
RING_COLOR = (70, 82, 100)
TEXT_COLOR = (235, 240, 248)
SUBTEXT_COLOR = (135, 150, 170)
NEEDLE_COLOR = (255, 65, 54)
ACCENT_BLUE = (45, 175, 255)
ACCENT_ORANGE = (255, 150, 40)
ACCENT_PURPLE = (170, 100, 255)
REDLINE_COLOR = (225, 45, 45)
BEST_COLOR = (80, 225, 120)
DIVIDER_COLOR = (38, 46, 60)

LED_MODES = [
    ("off", "WYŁĄCZ"), ("static", "STAŁY"),
    ("breathe", "ODDECH"), ("rainbow", "TĘCZA"),
    ("cycle", "CYKL KOLORÓW"), ("comet", "KOMETA"),
    ("sparkle", "ISKRY"), ("fire", "OGIEŃ"),
    ("police", "POLICJA"), ("shift", "OBROTY (RPM)"),
]
LED_MODES_WITHOUT_COLOR = ("off", "rainbow", "cycle", "fire", "police")
PRESET_COLORS = [
    (255, 0, 0), (255, 90, 0), (255, 200, 0), (0, 255, 0), (0, 255, 200),
    (0, 120, 255), (0, 0, 255), (150, 0, 255), (255, 0, 140), (255, 255, 255),
]

MPV_INPUT_CONF = "/tmp/pi-launcher-mpv-input.conf"
with open(MPV_INPUT_CONF, "w") as _f:
    _f.write("MBTN_LEFT_DBL quit\nESC quit\nq quit\n")

# ---------------------------------------------------------------------------
# Ekran
# ---------------------------------------------------------------------------
# Tylko grafika i czcionki - bez pygame.init(), który otwiera też dźwięk (wolny start, blokuje audio dla mpv)
pygame.display.init()
pygame.font.init()


def open_display():
    win = os.environ.get("LAUNCHER_WINDOW")
    if win:
        w, h = (int(v) for v in win.lower().split("x"))
        surf = pygame.display.set_mode((w, h))
    else:
        surf = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
        pygame.mouse.set_visible(False)
    pygame.display.set_caption("Pi Launcher")
    return surf


screen = open_display()
W, H = screen.get_size()


def refresh_screen():
    """Po błędzie rysowania pobierz powierzchnię okna od nowa (SDL mógł ją podmienić)."""
    global screen
    surf = pygame.display.get_surface()
    if surf is not None:
        screen = surf
clock = pygame.time.Clock()

font_title = T.get_font("sans", H * 0.075)
font_btn = T.get_font("sans", H * 0.060)
font_small = T.get_font("sans", H * 0.036)
font_tiny = T.get_font("sans", H * 0.028, bold=False)

SKINS = [(t["name"], t["label"], "gauge") for t in T.THEMES] + \
        [(l["name"], l["label"], "layout") for l in Lay.LAYOUTS]
SKIN_NAMES = [n for n, _, _ in SKINS]
SKIN_LABEL = {n: lbl for n, lbl, _ in SKINS}


def render_skin(surf, name, view, now, dt):
    """Rysuje cały ekran dashboardu (tarcza lub pełny ekran) na dowolnej powierzchni."""
    if name in Lay.LAYOUT_BY_NAME:
        Lay.LAYOUT_BY_NAME[name]["draw"](surf, view, now, dt)
        return
    th = T.get_theme(name)
    w, h = surf.get_size()
    surf.fill(th["bg"])
    T.draw_timing_bar(surf, th, view.cur, view.last, view.best, format_lap_time)
    radius = int(min(w * 0.21, h * 0.38))
    cy = int(h * 0.56)
    T.draw_gauge(surf, th, int(w * 0.26), cy, radius, view.rpm, view.rpm_max, "RPM",
                 view.rpm_step, redline=view.redline, kind="rpm", divide=1000)
    T.draw_gauge(surf, th, int(w * 0.74), cy, radius, view.speed, view.speed_max, view.unit,
                 view.speed_step, redline=None, kind="speed", divide=1)


def clamp(v, lo, hi):
    return lo if v < lo else hi if v > hi else v


def render_fit(font, text, color, max_w):
    surf = font.render(text, True, color)
    if max_w > 0 and surf.get_width() > max_w:
        k = max_w / surf.get_width()
        surf = pygame.transform.smoothscale(
            surf, (max(1, int(surf.get_width() * k)), max(1, int(surf.get_height() * k))))
    return surf


def pick_scale(value, scales):
    for max_v, step in scales:
        if value <= max_v:
            return float(max_v), float(step)
    top_max = math.ceil(value / 20000.0) * 20000.0
    return float(top_max), float(top_max / 10.0)


def format_lap_time(sec):
    if sec is None or sec <= 0.0:
        return "--:--.---"
    total_ms = int(round(sec * 1000.0))
    minutes, rem_ms = divmod(total_ms, 60000)
    seconds, ms = divmod(rem_ms, 1000)
    return f"{minutes:02d}:{seconds:02d}.{ms:03d}"


# ---------------------------------------------------------------------------
# Dashboard - stan i rysowanie (logika z dotychczasowego skryptu RPi)
# ---------------------------------------------------------------------------
class DashState:
    def __init__(self):
        self.target_rpm = 0.0
        self.target_speed = 0.0
        self.speed_unit = "MPH"
        self.current_lap = 0.0
        self.last_lap = 0.0
        self.best_lap = 0.0
        self.reset_rpm_scale()
        self.speed_scale, self.speed_step = float(DEFAULT_SPEED_SCALE[0]), float(DEFAULT_SPEED_SCALE[1])
        self.rpm_auto_mode = True
        self.zero_rpm_since = None
        self.disp_rpm = 0.0
        self.disp_speed = 0.0
        self.laps_done = 0
        self.lap_from_pc = None
        self.vmax = 0.0
        self.session_start = None
        self.last_pkt = 0.0
        self.throttle = None
        self.position = None
        self.last_hist = 0.0
        self.view = Lay.DashView()

    def reset_rpm_scale(self):
        self.rpm_scale, self.rpm_step = float(DEFAULT_RPM_SCALE[0]), float(DEFAULT_RPM_SCALE[1])
        self.rpm_redline = self.rpm_scale * 0.85

    def process(self, pkt, now=None):
        now = time.time() if now is None else now
        if self.session_start is None or now - self.last_pkt > 30.0:
            self.session_start = now
        self.last_pkt = now
        prev_last = self.last_lap
        self.target_rpm = max(0.0, float(pkt.get("rpm", self.target_rpm)))
        self.target_speed = max(0.0, float(pkt.get("speed", self.target_speed)))
        if "unit" in pkt:
            self.speed_unit = str(pkt["unit"])
        if "current_lap" in pkt:
            self.current_lap = max(0.0, float(pkt["current_lap"] or 0.0))
        if "last_lap" in pkt:
            self.last_lap = max(0.0, float(pkt["last_lap"] or 0.0))
        if "best_lap" in pkt:
            self.best_lap = max(0.0, float(pkt["best_lap"] or 0.0))
        if self.last_lap > 0 and abs(self.last_lap - prev_last) > 1e-3:
            self.laps_done += 1
        self.lap_from_pc = int(pkt["lap"]) if pkt.get("lap") else None
        self.throttle = float(pkt["throttle"]) if pkt.get("throttle") is not None else None
        self.position = int(pkt["position"]) if pkt.get("position") else None
        self.vmax = max(self.vmax, self.target_speed)

        pkt_max_rpm = float(pkt.get("max_rpm", 0) or 0)
        if pkt_max_rpm > 0:
            self.rpm_auto_mode = False
            needed = max(pkt_max_rpm, self.target_rpm * 1.05)
            self.rpm_scale, self.rpm_step = pick_scale(needed, RPM_SCALES)
            self.rpm_redline = pkt_max_rpm * 0.90
        else:
            self.rpm_auto_mode = True
            if self.target_rpm > self.rpm_scale * 0.92:
                self.rpm_scale, self.rpm_step = pick_scale(self.target_rpm / 0.85, RPM_SCALES)
                self.rpm_redline = self.rpm_scale * 0.85

        pkt_max_speed = float(pkt.get("max_speed", 0) or 0)
        needed_speed = max(DEFAULT_SPEED_SCALE[0], pkt_max_speed, self.target_speed * 1.05)
        self.speed_scale, self.speed_step = pick_scale(needed_speed, SPEED_SCALES)

    def update(self, now):
        if self.rpm_auto_mode:
            if self.target_rpm < 150.0:
                if self.zero_rpm_since is None:
                    self.zero_rpm_since = now
                elif now - self.zero_rpm_since >= AUTO_RESET_SECONDS:
                    self.reset_rpm_scale()
            else:
                self.zero_rpm_since = None
        self.disp_rpm += (self.target_rpm - self.disp_rpm) * 0.28
        self.disp_speed += (self.target_speed - self.disp_speed) * 0.28

        v = self.view
        v.rpm, v.redline, v.rpm_max, v.rpm_step = self.disp_rpm, self.rpm_redline, self.rpm_scale, self.rpm_step
        v.speed, v.speed_max, v.speed_step, v.unit = self.disp_speed, self.speed_scale, self.speed_step, self.speed_unit
        v.cur, v.last, v.best = self.current_lap, self.last_lap, self.best_lap
        v.lap = self.lap_from_pc or (self.laps_done + 1)
        v.delta = (self.last_lap - self.best_lap) if (self.last_lap > 0 and self.best_lap > 0) else None
        v.vmax = self.vmax
        v.session = (now - self.session_start) if self.session_start else 0.0
        v.throttle, v.position = self.throttle, self.position
        if now - self.last_hist >= 1.0 / 30:
            self.last_hist = now
            v.hist_rpm.append(self.disp_rpm / self.rpm_scale if self.rpm_scale else 0.0)
            v.hist_speed.append(self.disp_speed / self.speed_scale if self.speed_scale else 0.0)


class TouchWatcher:
    """Podwójne dotknięcie / ESC podczas filmu, czytane prosto z /dev/input (działa z każdym odtwarzaczem)."""

    def __init__(self):
        self.devs = []
        self.last_tap = 0.0
        if evdev is None:
            print("Brak python3-evdev - film zamkniesz tylko z PC lub klawiszem w odtwarzaczu")
            return
        for path in evdev.list_devices():
            try:
                dev = evdev.InputDevice(path)
                keys = dev.capabilities().get(ecodes.EV_KEY, [])
                if any(k in keys for k in (ecodes.BTN_TOUCH, ecodes.BTN_LEFT, ecodes.KEY_ESC)):
                    self.devs.append(dev)
                else:
                    dev.close()
            except Exception:
                pass
        # wyrzuć zaległe zdarzenia (np. dotknięcie, którym wybrano film)
        self.exit_requested()
        self.last_tap = 0.0

    def exit_requested(self):
        hit = False
        for dev in self.devs:
            try:
                while True:
                    ev = dev.read_one()
                    if ev is None:
                        break
                    if ev.type != ecodes.EV_KEY or ev.value != 1:
                        continue
                    if ev.code in (ecodes.KEY_ESC, ecodes.KEY_Q):
                        hit = True
                    elif ev.code in (ecodes.BTN_TOUCH, ecodes.BTN_LEFT):
                        now = time.time()
                        if now - self.last_tap < 0.45:
                            hit = True
                        self.last_tap = now
            except (BlockingIOError, OSError):
                continue
        return hit

    def close(self):
        for dev in self.devs:
            try:
                dev.close()
            except Exception:
                pass
        self.devs = []


def load_settings():
    try:
        with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except FileNotFoundError:
        return {}
    except Exception as e:
        print(f"Nie można wczytać {SETTINGS_FILE}: {e}")
        return {}


def save_settings(data):
    try:
        os.makedirs(os.path.dirname(SETTINGS_FILE), exist_ok=True)
        tmp = SETTINGS_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f)
        os.replace(tmp, SETTINGS_FILE)
    except Exception as e:
        print(f"Nie można zapisać ustawień: {e}")


# ---------------------------------------------------------------------------
# Aplikacja
# ---------------------------------------------------------------------------
class App:
    def __init__(self):
        self.mode = "menu"            # menu | dash | film_list | film_play | led | themes
        self.settings = load_settings()
        skin = self.settings.get("theme", T.DEFAULT_THEME)
        self.skin = skin if skin in SKIN_NAMES else T.DEFAULT_THEME
        self.themes_return = "menu"
        self.themes_tab = "layout" if self.skin in Lay.LAYOUT_BY_NAME else "gauge"
        self.thumbs = {}
        self.sample = Lay.sample_view()
        self.display_released = False
        self.touch = None
        self.film_started = 0.0
        self.film_proc_started = 0.0
        self.film_path = None
        self.film_fails = 0
        self.dash_ui_until = 0.0          # przyciski na dashboardzie pokazują się po dotknięciu
        self.last_frame = time.time()
        self.warm_tasks = None
        self.running = True
        self.dash = DashState()
        self.last_data = 0.0

        self.hits = []                # [(rect, callback)] z ostatniej klatki
        self.slider_rects = {}
        self.active_slider = None

        self.film_proc = None
        self.film_name = ""
        self.videos = []
        self.film_page = 0

        self.led_state = {"mode": "rainbow", "color": [255, 80, 0], "brightness": 0.5, "speed": 1.0}
        self.led_pending = {}
        self.led_last_flush = 0.0
        self.led_last_change = 0.0
        self.led_last_reply = 0.0
        self.led_last_ping = 0.0
        self.last_rpm_fwd = 0.0
        self.hue_surface = None

        self.confirm_off_until = 0.0
        self.message = ""
        self.message_until = 0.0

        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind(("0.0.0.0", UDP_PORT))
        self.sock.setblocking(False)

        self.led_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.led_sock.setblocking(False)
        self.led_raw({"cmd": "get"})
        self.preload_pending = True   # wczytanie grafiki + filmu rusza po pierwszej klatce (w run)

    # ----- komunikaty -----
    def toast(self, text, seconds=3.0):
        print(text)
        self.message = text
        self.message_until = time.time() + seconds

    # ----- LED -----
    def led_raw(self, obj):
        try:
            self.led_sock.sendto(json.dumps(obj).encode("utf-8"), LED_ADDR)
        except OSError:
            pass

    def led_send(self, **kw):
        self.led_pending.update(kw)
        self.led_state.update(kw)
        self.led_last_change = time.time()

    def led_flush(self, now, force=False):
        if self.led_pending and (force or now - self.led_last_flush > 0.033):
            self.led_raw(dict(cmd="set", **self.led_pending))
            self.led_pending = {}
            self.led_last_flush = now

    def led_set_mode(self, key):
        self.led_send(mode=key)

    def led_set_color(self, col):
        self.led_send(color=[int(c) for c in col])
        if self.led_state["mode"] in LED_MODES_WITHOUT_COLOR:
            self.led_send(mode="static")

    def poll_led(self, now):
        while True:
            try:
                data, _ = self.led_sock.recvfrom(2048)
            except (BlockingIOError, InterruptedError):
                break
            except OSError:
                break
            try:
                msg = json.loads(data.decode("utf-8"))
            except Exception:
                continue
            if isinstance(msg, dict) and isinstance(msg.get("state"), dict):
                self.led_last_reply = now
                if not self.led_pending and now - self.led_last_change > 0.6:
                    self.led_state.update(msg["state"])
        if now - self.led_last_ping > 3.0:
            self.led_last_ping = now
            self.led_raw({"cmd": "get"})

    @property
    def led_online(self):
        return time.time() - self.led_last_reply < 7.0

    # ----- UDP z PC -----
    def poll_udp(self, now):
        while True:
            try:
                data, _ = self.sock.recvfrom(2048)
            except (BlockingIOError, InterruptedError):
                break
            except OSError:
                break
            try:
                pkt = json.loads(data.decode("utf-8"))
                if not isinstance(pkt, dict):
                    continue
            except Exception:
                continue

            if "cmd" in pkt:
                self.handle_command(pkt)
                continue

            self.last_data = now
            if self.mode == "menu" and AUTO_DASHBOARD:
                self.go_dash()
            try:
                self.dash.process(pkt, now)
            except (TypeError, ValueError):
                pass

    def handle_command(self, pkt):
        cmd = pkt.get("cmd")
        target = pkt.get("mode")
        print(f"Komenda z PC: {pkt}")
        if cmd == "mode":
            if target == "dashboard":
                self.go_dash()
            elif target == "menu":
                self.go_menu()
        elif cmd == "theme":
            name = str(pkt.get("name", ""))
            if name in ("next", "prev"):
                self.cycle_theme(1 if name == "next" else -1)
            elif name in SKIN_NAMES:
                self.set_theme(name)
        elif cmd == "stop":
            if target == "dashboard" and self.mode == "dash":
                self.go_menu()

    # ----- nawigacja -----
    def go_menu(self):
        self.stop_film()
        self.mode = "menu"
        self.active_slider = None

    def go_dash(self):
        self.stop_film()
        self.mode = "dash"

    def go_led(self):
        self.mode = "led"
        self.led_raw({"cmd": "get"})

    def open_themes(self, back):
        self.themes_return = back
        self.themes_tab = "layout" if self.skin in Lay.LAYOUT_BY_NAME else "gauge"
        self.mode = "themes"

    def set_theme(self, name, close=False):
        if name not in SKIN_NAMES:
            return
        self.skin = name
        self.settings["theme"] = name
        save_settings(self.settings)
        print(f"Ekran dashboardu: {name}")
        if close:
            self.mode = self.themes_return

    def cycle_theme(self, step):
        i = SKIN_NAMES.index(self.skin) if self.skin in SKIN_NAMES else 0
        self.set_theme(SKIN_NAMES[(i + step) % len(SKIN_NAMES)])

    # ----- rozgrzewanie cache (żeby dashboard i wybór ekranów otwierały się od razu) -----
    def make_warm_tasks(self):
        """Wszystko, co rysowanie potrzebuje policzyć raz: tarcze, tła ekranów, czcionki, miniatury."""
        self.dash.update(time.time())          # domyślne skale - te same, które dashboard pokaże na start
        view = self.dash.view
        off = pygame.Surface((W, H))
        tasks = []
        for name in [self.skin] + [n for n in SKIN_NAMES if n != self.skin]:
            tasks.append(lambda n=name: render_skin(off, n, view, time.time(), 0.0))
        tw, th = self.thumb_size()
        for name in SKIN_NAMES:
            tasks.append(lambda n=name: self.get_thumb(n, tw, th))
        return iter(tasks)

    def preload_ui(self):
        """Ekran startowy z paskiem postępu - po nim dashboard i wybór ekranów otwierają się od razu."""
        tasks = list(self.make_warm_tasks())
        t_start = time.perf_counter()
        last_draw = 0.0
        splash_ok = True
        for i, task in enumerate(tasks):
            try:
                task()
            except Exception as e:
                print(f"Błąd przy wczytywaniu: {e}")
            now = time.perf_counter()
            if splash_ok and (now - last_draw > 0.05 or i == len(tasks) - 1):
                last_draw = now
                try:
                    self.draw_splash((i + 1) / len(tasks))
                except pygame.error as e:
                    print(f"Ekran wczytywania pominięty: {e}")
                    splash_ok = False
                    refresh_screen()
        print(f"Grafika wczytana w {time.perf_counter() - t_start:.1f} s")

    def draw_splash(self, frac):
        pygame.event.pump()
        refresh_screen()
        frame = pygame.Surface((W, H))          # najpierw poza ekranem, potem jeden blit
        frame.fill(BG_COLOR)
        t = font_title.render("WCZYTYWANIE", True, TEXT_COLOR)
        frame.blit(t, t.get_rect(center=(W // 2, int(H * 0.42))))
        bar = pygame.Rect(int(W * 0.2), int(H * 0.55), int(W * 0.6), int(H * 0.035))
        pygame.draw.rect(frame, DIAL_BG, bar, border_radius=bar.h // 2)
        fill = bar.copy()
        fill.w = max(bar.h, int(bar.w * frac))
        pygame.draw.rect(frame, ACCENT_BLUE, fill, border_radius=bar.h // 2)
        screen.blit(frame, (0, 0))
        pygame.display.flip()

    # ----- wstępne wczytanie filmu i VLC do RAM (pierwsze uruchomienie filmu bez czekania) -----
    def preload_media(self):
        self.warm_player = None

        def fadvise(path):
            try:
                fd = os.open(path, os.O_RDONLY)
                try:
                    os.posix_fadvise(fd, 0, 0, os.POSIX_FADV_WILLNEED)   # jądro czyta plik do RAM w tle
                finally:
                    os.close(fd)
            except OSError:
                pass

        def work():
            t0 = time.time()
            videos = [os.path.join(VIDEO_DIR, f) for f in self.scan_videos()]
            for v in videos:
                fadvise(v)
            libs = []
            for pattern in ("/usr/lib/*/vlc/**", "/usr/lib/vlc/**", "/usr/lib/*/libvlc*.so*",
                            "/usr/lib/*/libav*.so*", "/usr/lib/*/libsw*.so*", "/usr/lib/*/libplacebo*.so*",
                            "/usr/bin/vlc", "/usr/bin/cvlc"):
                libs += glob.glob(pattern, recursive=True)
            for f in libs:
                if os.path.isfile(f):
                    fadvise(f)
            # Raz uruchom VLC bez obrazu i dźwięku - ładuje wtyczki i dekoder, potem start filmu jest natychmiastowy
            vlc = shutil.which("cvlc")
            if vlc and videos and FILM_PLAYER != "mpv" and self.film_proc is None:
                try:
                    self.warm_player = subprocess.Popen(
                        [vlc, "-I", "dummy", "--vout", "dummy", "--aout", "dummy", "--no-video-title-show",
                         "--run-time=2", "--play-and-exit", videos[0]],
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                        preexec_fn=lambda: os.nice(10))
                    self.warm_player.wait(timeout=20)
                except Exception:
                    self.kill_warm_player()
            print(f"Film/VLC wczytane do RAM w {time.time() - t0:.1f} s ({len(videos)} filmów, {len(libs)} plików VLC)")

        threading.Thread(target=work, daemon=True).start()

    def kill_warm_player(self):
        proc = getattr(self, "warm_player", None)
        if proc is not None and proc.poll() is None:
            try:
                proc.kill()
                proc.wait(timeout=1)
            except Exception:
                pass

    def warm_step(self, budget=0.012):
        if self.warm_tasks is None:
            return
        t0 = time.perf_counter()
        while time.perf_counter() - t0 < budget:
            try:
                next(self.warm_tasks)()
            except StopIteration:
                self.warm_tasks = None
                print(f"Cache gotowy ({time.strftime('%H:%M:%S')})")
                return

    def thumb_size(self):
        cols, m, gap = 5, int(W * 0.03), int(W * 0.015)
        tw = (W - 2 * m - gap * (cols - 1)) // cols
        th = int(tw * H / W)
        return tw, th

    def get_thumb(self, name, tw, th):
        key = (name, tw, th)
        surf = self.thumbs.get(key)
        if surf is None:
            # render w połowie rozdzielczości ekranu i pomniejszenie -> miniatura wygląda jak prawdziwy ekran
            big = pygame.Surface((max(tw, W // 2), max(th, H // 2)))
            render_skin(big, name, self.sample, 12.3, 0.0)
            surf = pygame.transform.smoothscale(big, (tw, th)).convert()
            self.thumbs[key] = surf
        return surf

    def scan_videos(self):
        try:
            files = [f for f in os.listdir(VIDEO_DIR)
                     if f.lower().endswith(VIDEO_EXT) and os.path.isfile(os.path.join(VIDEO_DIR, f))]
        except FileNotFoundError:
            files = []
        return sorted(files, key=str.lower)

    def open_films(self):
        self.videos = self.scan_videos()
        if not self.videos:
            self.go_menu()
            self.toast(f"Brak filmów w {VIDEO_DIR}")
        elif len(self.videos) == 1:
            self.play_film(os.path.join(VIDEO_DIR, self.videos[0]))
        else:
            self.film_page = 0
            self.mode = "film_list"

    def player_command(self, path):
        """Te same parametry co we wcześniejszym skrypcie filmu (tam działało płynnie)."""
        vlc, mpv = shutil.which("cvlc"), shutil.which("mpv")
        use_vlc = vlc and (FILM_PLAYER in ("vlc", "auto") or not mpv)
        if use_vlc:
            args = [vlc, "--fullscreen", "--no-video-title-show", "--no-osd", "--mouse-hide-timeout=0"]
            if FILM_LOOP:
                # --input-repeat: ten sam plik od nowa w tym samym oknie (bez zamykania obrazu)
                args += ["--loop", "--input-repeat=65535"]
            else:
                args.append("--play-and-exit")
            if FILM_MUTE:
                args.append("--no-audio")
            return args + VLC_EXTRA_ARGS + [path]
        if mpv:
            args = [mpv, "--fs", "--no-osc", "--no-osd-bar", "--cursor-autohide=always",
                    f"--input-conf={MPV_INPUT_CONF}"]
            if FILM_LOOP:
                args.append("--loop-file=inf")
            if FILM_MUTE:
                args.append("--no-audio")
            return args + MPV_EXTRA_ARGS + [path]
        return None

    def play_film(self, path):
        self.stop_film()
        self.kill_warm_player()
        args = self.player_command(path)
        if args is None:
            self.go_menu()
            self.toast("Brak odtwarzacza (sudo apt install vlc)")
            return
        if not self.spawn_player(args):
            self.go_menu()
            return
        self.film_path = path
        self.film_fails = 0
        # Launcher na razie zostaje (czarny ekran "Ładowanie"), żeby nie było widać pulpitu.
        # Po FILM_HANDOFF_DELAY zamyka swoje okno, a odtwarzacz ma cały ekran dla siebie.
        self.film_started = time.time()
        self.film_name = os.path.basename(path)
        self.mode = "film_play"
        self.touch = TouchWatcher()
        print(f"Film: {' '.join(args)}")

    def spawn_player(self, args):
        try:
            self.film_proc = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            self.film_proc_started = time.time()
            return True
        except OSError as e:
            self.toast(f"Nie można uruchomić filmu: {e}")
            return False

    def release_display(self):
        if not self.display_released:
            pygame.display.quit()
            self.display_released = True

    def restore_display(self):
        global screen
        if self.display_released:
            pygame.display.init()
            screen = open_display()
            self.display_released = False
            self.active_slider = None

    def stop_film(self):
        proc = self.film_proc
        self.film_proc = None
        if proc is not None:
            try:
                proc.terminate()
                proc.wait(timeout=2)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass
        if getattr(self, "touch", None) is not None:
            self.touch.close()
            self.touch = None
        self.restore_display()

    def check_film(self):
        if self.film_proc is not None and self.film_proc.poll() is not None:
            ran = time.time() - self.film_proc_started
            self.film_proc = None
            # Pętla pilnowana przez launcher: jeśli odtwarzacz sam się zamknął (a nie zatrzymał go
            # użytkownik), od razu startujemy film od nowa - bez wracania do menu.
            if FILM_LOOP and self.mode == "film_play" and self.film_path:
                self.film_fails = self.film_fails + 1 if ran < 3.0 else 0
                if self.film_fails < 3:
                    args = self.player_command(self.film_path)
                    if args and self.spawn_player(args):
                        print(f"Film zapętlony (odtwarzacz zamknął się po {ran:.0f} s)")
                        return
                self.toast("Nie można odtworzyć filmu - sprawdź plik")
            self.stop_film()                  # zamyka czytnik dotyku i przywraca okno launchera
            if self.mode == "film_play":
                self.mode = "menu"

    def power_off(self):
        now = time.time()
        if now < self.confirm_off_until:
            self.toast("Wyłączanie...")
            self.stop_film()
            subprocess.Popen(["sudo", "poweroff"])
            self.running = False
        else:
            self.confirm_off_until = now + 3.0

    def quit_to_desktop(self):
        self.running = False

    # ----- wejście -----
    def on_press(self, pos):
        x, y = pos
        if self.mode == "dash":
            for rect, fn in self.hits:
                if rect.collidepoint(pos):
                    self.dash_ui_until = time.time() + 4.0
                    fn()
                    return
            # pierwsze dotknięcie pokazuje przyciski MENU / EKRAN (chowają się po 4 s)
            self.dash_ui_until = time.time() + 4.0
            return

        if self.mode == "film_play":
            return
        for key, rect in self.slider_rects.items():
            if rect.inflate(0, int(H * 0.05)).collidepoint(pos):
                self.active_slider = key
                self.update_slider(pos)
                return
        for rect, fn in self.hits:
            if rect.collidepoint(pos):
                fn()
                return

    def update_slider(self, pos):
        rect = self.slider_rects.get(self.active_slider)
        if rect is None:
            return
        f = clamp((pos[0] - rect.x) / max(1, rect.w), 0.0, 1.0)
        if self.active_slider == "hue":
            r, g, b = colorsys.hsv_to_rgb(min(f, 0.999), 1.0, 1.0)
            self.led_set_color((r * 255, g * 255, b * 255))
        elif self.active_slider == "bri":
            self.led_send(brightness=round(f, 3))
        elif self.active_slider == "spd":
            self.led_send(speed=round(0.2 + f * 2.8, 2))

    def handle_events(self):
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                self.running = False
            elif ev.type == pygame.KEYDOWN:
                if ev.key == pygame.K_ESCAPE:
                    if self.mode == "menu":
                        self.running = False
                    else:
                        self.go_menu()
            elif ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
                self.on_press(ev.pos)
            elif ev.type == pygame.MOUSEMOTION and self.active_slider:
                self.update_slider(ev.pos)
            elif ev.type == pygame.MOUSEBUTTONUP and ev.button == 1:
                if self.active_slider:
                    self.active_slider = None
                    self.led_flush(time.time(), force=True)

    # ----- elementy UI -----
    def button(self, rect, label, fn, color=RING_COLOR, font=None, active=False, sub=None):
        rect = pygame.Rect(rect)
        rad = int(min(rect.w, rect.h) * 0.16)
        pygame.draw.rect(screen, color if active else DIAL_BG, rect, border_radius=rad)
        pygame.draw.rect(screen, color, rect, width=3, border_radius=rad)
        txt_color = BG_COLOR if active else TEXT_COLOR
        surf = render_fit(font or font_btn, label, txt_color, rect.w - 16)
        if sub:
            sub_surf = render_fit(font_tiny, sub, BG_COLOR if active else SUBTEXT_COLOR, rect.w - 16)
            total = surf.get_height() + sub_surf.get_height() + 4
            top = rect.centery - total // 2
            screen.blit(surf, surf.get_rect(midtop=(rect.centerx, top)))
            screen.blit(sub_surf, sub_surf.get_rect(midtop=(rect.centerx, top + surf.get_height() + 4)))
        else:
            screen.blit(surf, surf.get_rect(center=rect.center))
        self.hits.append((rect, fn))
        return rect

    def slider(self, key, rect, frac, label, gradient=None, color=ACCENT_PURPLE):
        rect = pygame.Rect(rect)
        lbl = font_small.render(label, True, SUBTEXT_COLOR)
        screen.blit(lbl, (rect.x, rect.y - lbl.get_height() - 4))
        if gradient is not None:
            screen.blit(gradient, rect)
        else:
            pygame.draw.rect(screen, DIAL_BG, rect, border_radius=6)
            fill = rect.copy()
            fill.w = int(rect.w * frac)
            if fill.w > 0:
                pygame.draw.rect(screen, color, fill, border_radius=6)
        pygame.draw.rect(screen, RING_COLOR, rect, 2, border_radius=6)
        kx = rect.x + int(frac * rect.w)
        knob = pygame.Rect(kx - 6, rect.y - 5, 12, rect.h + 10)
        pygame.draw.rect(screen, TEXT_COLOR, knob, border_radius=4)
        pygame.draw.rect(screen, BG_COLOR, knob, 2, border_radius=4)
        self.slider_rects[key] = rect

    def get_hue_surface(self, w, h):
        if self.hue_surface is None or self.hue_surface.get_size() != (w, h):
            surf = pygame.Surface((w, h))
            for x in range(w):
                r, g, b = colorsys.hsv_to_rgb(x / max(1, w - 1), 1.0, 1.0)
                pygame.draw.line(surf, (int(r * 255), int(g * 255), int(b * 255)), (x, 0), (x, h))
            self.hue_surface = surf
        return self.hue_surface

    def draw_toast(self, now):
        if self.message and now < self.message_until:
            surf = render_fit(font_small, self.message, TEXT_COLOR, int(W * 0.8))
            box = surf.get_rect(center=(W // 2, int(H * 0.5))).inflate(40, 24)
            pygame.draw.rect(screen, DIAL_BG, box, border_radius=12)
            pygame.draw.rect(screen, ACCENT_ORANGE, box, 3, border_radius=12)
            screen.blit(surf, surf.get_rect(center=box.center))

    # ----- ekrany -----
    def draw_menu(self, now):
        screen.fill(BG_COLOR)
        title = font_title.render("WYBIERZ TRYB", True, TEXT_COLOR)
        screen.blit(title, title.get_rect(center=(W // 2, int(H * 0.11))))

        tile_w = int(W * 0.28)
        tile_h = int(H * 0.46)
        gap = int(W * 0.04)
        x0 = (W - (3 * tile_w + 2 * gap)) // 2
        y0 = int(H * 0.22)
        tiles = [
            ("DASHBOARD", "zegary z PC", ACCENT_BLUE, self.go_dash),
            ("FILM", "pliki z ~/filmy", ACCENT_ORANGE, self.open_films),
            ("LEDY", "kolory i animacje", ACCENT_PURPLE, self.go_led),
        ]
        for i, (label, sub, col, fn) in enumerate(tiles):
            rect = pygame.Rect(x0 + i * (tile_w + gap), y0, tile_w, tile_h)
            self.button(rect, label, fn, color=col, sub=sub)

        bw, bh = int(W * 0.20), int(H * 0.10)
        by = int(H * 0.74)
        self.button((x0, by, bw, bh), "PULPIT", self.quit_to_desktop, font=font_small)
        self.button(((W - bw) // 2, by, bw, bh), "TARCZE", lambda: self.open_themes("menu"),
                    color=ACCENT_BLUE, font=font_small, sub=SKIN_LABEL.get(self.skin, "").lower())
        confirm = now < self.confirm_off_until
        self.button((W - x0 - bw, by, bw, bh), "NA PEWNO?" if confirm else "WYŁĄCZ",
                    self.power_off, color=REDLINE_COLOR, font=font_small, active=confirm)

        pc_ok = now - self.last_data < DATA_TIMEOUT
        status = (f"PC: {'dane OK' if pc_ok else 'brak danych'}   |   "
                  f"LED: {self.led_state['mode'] if self.led_online else 'ledd nie odpowiada'}")
        s = render_fit(font_tiny, status, SUBTEXT_COLOR, W - 20)
        screen.blit(s, s.get_rect(center=(W // 2, int(H * 0.94))))

    def draw_dash(self, now):
        dt = min(0.1, now - self.last_frame)
        render_skin(screen, self.skin, self.dash.view, now, dt)
        if now < self.dash_ui_until:
            bw, bh = int(W * 0.16), int(H * 0.11)
            y = H - bh - int(H * 0.02)
            self.button((int(W * 0.02), y, bw, bh), "< MENU", self.go_menu, font=font_small)
            self.button((W - bw - int(W * 0.02), y, bw, bh), "EKRAN",
                        lambda: self.open_themes("dash"), font=font_small)
            self.button(((W - bw) // 2, y, bw, bh), "NASTĘPNY", lambda: self.cycle_theme(1), font=font_small)
        if now - self.last_data > DATA_TIMEOUT:
            s = font_small.render(f"Czekam na dane z PC (UDP :{UDP_PORT})...", True, ACCENT_ORANGE)
            box = s.get_rect(center=(W // 2, int(H * 0.5))).inflate(30, 16)
            pygame.draw.rect(screen, (0, 0, 0), box, border_radius=10)
            screen.blit(s, s.get_rect(center=box.center))

    def draw_film_list(self, now):
        screen.fill(BG_COLOR)
        self.button((int(W * 0.03), int(H * 0.03), int(W * 0.16), int(H * 0.10)),
                    "< MENU", self.go_menu, font=font_small)
        title = font_title.render("FILMY", True, TEXT_COLOR)
        screen.blit(title, title.get_rect(center=(W // 2, int(H * 0.08))))

        per_page = 5
        pages = max(1, math.ceil(len(self.videos) / per_page))
        self.film_page = clamp(self.film_page, 0, pages - 1)
        items = self.videos[self.film_page * per_page:(self.film_page + 1) * per_page]
        x = int(W * 0.08)
        w = int(W * 0.84)
        y = int(H * 0.17)
        h = int(H * 0.115)
        gap = int(H * 0.02)
        for name in items:
            path = os.path.join(VIDEO_DIR, name)
            self.button((x, y, w, h), name, lambda p=path: self.play_film(p),
                        color=ACCENT_ORANGE, font=font_small)
            y += h + gap

        if pages > 1:
            by = int(H * 0.86)
            bw = int(W * 0.18)
            bh = int(H * 0.10)
            self.button((x, by, bw, bh), "< POPRZ.",
                        lambda: setattr(self, "film_page", self.film_page - 1), font=font_small)
            self.button((x + w - bw, by, bw, bh), "NAST. >",
                        lambda: setattr(self, "film_page", self.film_page + 1), font=font_small)
            s = font_small.render(f"{self.film_page + 1} / {pages}", True, SUBTEXT_COLOR)
            screen.blit(s, s.get_rect(center=(W // 2, by + bh // 2)))

    def draw_film_play(self, now):
        screen.fill((0, 0, 0))
        dots = "." * (1 + int(now * 3) % 3)
        s = font_small.render(f"Ładowanie filmu{dots}", True, (90, 90, 100))
        screen.blit(s, s.get_rect(center=(W // 2, H // 2)))

    def draw_themes(self, now):
        screen.fill(BG_COLOR)
        m = int(W * 0.03)
        self.button((m, int(H * 0.02), int(W * 0.15), int(H * 0.095)), "< WSTECZ",
                    lambda: setattr(self, "mode", self.themes_return), font=font_small)
        tabw = int(W * 0.24)
        for i, (tab, label) in enumerate((("gauge", "TARCZE"), ("layout", "EKRANY"))):
            self.button((W // 2 - tabw + i * (tabw + 8), int(H * 0.02), tabw, int(H * 0.095)), label,
                        lambda t=tab: setattr(self, "themes_tab", t), color=ACCENT_BLUE,
                        active=(self.themes_tab == tab), font=font_small)

        items = [(n, lbl) for n, lbl, kind in SKINS if kind == self.themes_tab]
        cols, gap = 5, int(W * 0.015)
        tw, th = self.thumb_size()
        label_h = font_tiny.get_height() + 6
        rows = math.ceil(len(items) / cols)
        y0 = int(H * 0.15) + max(0, (H - int(H * 0.15) - rows * (th + label_h + gap)) // 2)
        budget_end = time.perf_counter() + 0.03     # ile czasu na dorobienie miniatur w tej klatce
        for i, (name, label) in enumerate(items):
            c, r = i % cols, i // cols
            rect = pygame.Rect(m + c * (tw + gap), y0 + r * (th + label_h + gap), tw, th)
            key = (name, tw, th)
            if key in self.thumbs or time.perf_counter() < budget_end:
                screen.blit(self.get_thumb(name, tw, th), rect)
            else:
                pygame.draw.rect(screen, DIAL_BG, rect)
                s = font_tiny.render("...", True, SUBTEXT_COLOR)
                screen.blit(s, s.get_rect(center=rect.center))
            selected = name == self.skin
            pygame.draw.rect(screen, ACCENT_BLUE if selected else RING_COLOR, rect.inflate(6, 6),
                             4 if selected else 1, border_radius=6)
            lbl = render_fit(font_tiny, label, ACCENT_BLUE if selected else TEXT_COLOR, tw)
            screen.blit(lbl, lbl.get_rect(midtop=(rect.centerx, rect.bottom + 4)))
            self.hits.append((rect.inflate(0, label_h), lambda n=name: self.set_theme(n, close=True)))

    def draw_led(self, now):
        screen.fill(BG_COLOR)
        st = self.led_state
        m = int(W * 0.03)
        self.button((m, int(H * 0.02), int(W * 0.15), int(H * 0.095)), "< MENU", self.go_menu, font=font_small)
        title = font_title.render("LEDY", True, TEXT_COLOR)
        screen.blit(title, title.get_rect(center=(W // 2, int(H * 0.07))))
        if not self.led_online:
            s = font_tiny.render("ledd nie odpowiada - sprawdź: systemctl status ledd", True, REDLINE_COLOR)
            screen.blit(s, s.get_rect(midright=(W - m, int(H * 0.07))))
        else:
            prev = pygame.Rect(0, 0, int(H * 0.08), int(H * 0.08))
            prev.midright = (W - m, int(H * 0.07))
            pygame.draw.rect(screen, tuple(st["color"]), prev, border_radius=8)
            pygame.draw.rect(screen, RING_COLOR, prev, 2, border_radius=8)

        # Tryby (lewa kolumna)
        y0 = int(H * 0.15)
        left_w = int(W * 0.46) - m
        gap = int(H * 0.015)
        rows = math.ceil(len(LED_MODES) / 2)
        bw = (left_w - gap) // 2
        bh = (H - y0 - m - gap * (rows - 1)) // rows
        for i, (key, label) in enumerate(LED_MODES):
            c, r = i % 2, i // 2
            rect = (m + c * (bw + gap), y0 + r * (bh + gap), bw, bh)
            self.button(rect, label, lambda k=key: self.led_set_mode(k), color=ACCENT_PURPLE,
                        active=(st["mode"] == key), font=font_small)

        # Kolory i suwaki (prawa kolumna)
        rx = int(W * 0.50)
        rw = W - rx - m
        sw_w = (rw - gap * 4) // 5
        sw_h = int(H * 0.10)
        for i, col in enumerate(PRESET_COLORS):
            c, r = i % 5, i // 5
            rect = pygame.Rect(rx + c * (sw_w + gap), y0 + r * (sw_h + gap), sw_w, sw_h)
            pygame.draw.rect(screen, col, rect, border_radius=8)
            selected = list(col) == list(st["color"])
            pygame.draw.rect(screen, TEXT_COLOR if selected else RING_COLOR, rect,
                             4 if selected else 2, border_radius=8)
            self.hits.append((rect, lambda col=col: self.led_set_color(col)))

        bar_h = int(H * 0.075)
        label_h = font_small.get_height() + 6
        step = label_h + bar_h + int(H * 0.04)
        y = y0 + 2 * sw_h + gap + int(H * 0.04) + label_h

        hue, sat, _ = colorsys.rgb_to_hsv(*(v / 255.0 for v in st["color"]))
        self.slider("hue", (rx, y, rw, bar_h), hue, "KOLOR",
                    gradient=self.get_hue_surface(rw, bar_h))
        y += step
        self.slider("bri", (rx, y, rw, bar_h), clamp(st["brightness"], 0, 1),
                    f"JASNOŚĆ  {int(round(st['brightness'] * 100))}%")
        y += step
        spd = clamp((st["speed"] - 0.2) / 2.8, 0, 1)
        self.slider("spd", (rx, y, rw, bar_h), spd, f"PRĘDKOŚĆ ANIMACJI  x{st['speed']:.1f}")

    # ----- pętla -----
    def run(self):
        while self.running:
            now = time.time()
            self.poll_udp(now)
            self.poll_led(now)
            self.check_film()
            self.led_flush(now)

            if self.mode == "film_play" and self.film_proc is not None:
                if self.touch is not None and self.touch.exit_requested():
                    print("Film zatrzymany dotknięciem")
                    self.go_menu()
                    continue
                if not self.display_released and now - self.film_started >= FILM_HANDOFF_DELAY:
                    self.release_display()

            if self.display_released:
                # film gra na całym ekranie - launcher tylko nasłuchuje komend i dotyku, nic nie rysuje
                self.last_frame = now
                time.sleep(0.05)
                continue

            self.handle_events()
            self.dash.update(now)
            if self.mode == "dash" and now - self.last_rpm_fwd > 0.033:
                self.last_rpm_fwd = now
                self.led_raw({"cmd": "rpm", "rpm": self.dash.target_rpm, "redline": self.dash.rpm_redline})

            self.hits = []
            self.slider_rects = {}
            draw = {
                "menu": self.draw_menu,
                "dash": self.draw_dash,
                "film_list": self.draw_film_list,
                "film_play": self.draw_film_play,
                "led": self.draw_led,
                "themes": self.draw_themes,
            }[self.mode]
            try:
                draw(now)
                self.draw_toast(now)
                pygame.display.flip()
            except pygame.error as e:
                # pojedyncza nieudana klatka nie może wyłączyć aplikacji
                print(f"Błąd rysowania ({self.mode}): {e}")
                refresh_screen()
                time.sleep(0.05)
            self.last_frame = now

            if self.preload_pending:
                # najpierw grafika (pasek postępu), dopiero potem w tle film/VLC - nie równocześnie
                self.preload_pending = False
                self.preload_ui()
                self.preload_media()

            if self.mode in ("menu", "led", "film_list"):
                self.warm_step()           # w wolnych chwilach przygotuj dashboard i miniatury
            clock.tick(FPS if self.mode == "dash" else MENU_FPS)

        self.stop_film()
        self.led_flush(time.time(), force=True)
        pygame.quit()
        print("=== launcher stop ===")


if __name__ == "__main__":
    App().run()
