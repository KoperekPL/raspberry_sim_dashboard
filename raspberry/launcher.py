#!/usr/bin/env python3
"""
launcher.py - menu startowe na Raspberry Pi (ekran dotykowy / mysz).

Uruchamia się automatycznie po starcie pulpitu i pozwala wybrać:
  DASHBOARD - zegary RPM / prędkość / czasy okrążeń (dane UDP z PC, port 5005)
  FILM      - odtwarzanie filmów z ~/filmy przez mpv (bez PC)
  LEDY      - kolory i animacje taśmy WS2812 (przez demona ledd.py, bez PC)

PC może też zdalnie przełączać tryb komendami JSON na port 5005:
  {"cmd": "mode", "mode": "dashboard" | "film" | "menu", "file": "opcjonalnie.mp4"}
  {"cmd": "stop", "mode": "dashboard" | "film"}   # wróć do menu, jeśli ten tryb jest aktywny

Test na zwykłym komputerze w oknie:  LAUNCHER_WINDOW=800x480 python3 launcher.py
"""
import colorsys
import fcntl
import json
import math
import os
import socket
import subprocess
import sys
import time

os.environ.setdefault("SDL_VIDEO_MINIMIZE_ON_FOCUS_LOSS", "0")  # nie chowaj okna, gdy mpv zabierze fokus
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
import pygame

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
FPS = 60
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
pygame.init()
_win = os.environ.get("LAUNCHER_WINDOW")
if _win:
    _w, _h = (int(v) for v in _win.lower().split("x"))
    screen = pygame.display.set_mode((_w, _h))
else:
    screen = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
    pygame.mouse.set_visible(False)
pygame.display.set_caption("Pi Launcher")
W, H = screen.get_size()
clock = pygame.time.Clock()


def make_font(name, size, bold=True):
    return pygame.font.SysFont(name, max(8, int(size)), bold=bold)


font_title = make_font("dejavusans", H * 0.075)
font_btn = make_font("dejavusans", H * 0.060)
font_small = make_font("dejavusans", H * 0.036)
font_tiny = make_font("dejavusans", H * 0.028, bold=False)


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


def get_ip():
    try:
        out = subprocess.run(["hostname", "-I"], capture_output=True, text=True, timeout=1).stdout.split()
        out = [a for a in out if ":" not in a]  # tylko IPv4
        return ", ".join(out) if out else "brak sieci"
    except Exception:
        return "?"


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

    def reset_rpm_scale(self):
        self.rpm_scale, self.rpm_step = float(DEFAULT_RPM_SCALE[0]), float(DEFAULT_RPM_SCALE[1])
        self.rpm_redline = self.rpm_scale * 0.85

    def process(self, pkt):
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
        self.theme = T.get_theme(self.settings.get("theme", T.DEFAULT_THEME))
        self.themes_return = "menu"
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
        self.ip = get_ip()
        self.ip_time = time.time()

        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind(("0.0.0.0", UDP_PORT))
        self.sock.setblocking(False)

        self.led_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.led_sock.setblocking(False)
        self.led_raw({"cmd": "get"})

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
                self.dash.process(pkt)
            except (TypeError, ValueError):
                pass

    def handle_command(self, pkt):
        cmd = pkt.get("cmd")
        target = pkt.get("mode")
        print(f"Komenda z PC: {pkt}")
        if cmd == "mode":
            if target == "dashboard":
                self.go_dash()
            elif target == "film":
                name = pkt.get("file")
                if name:
                    path = os.path.join(VIDEO_DIR, os.path.basename(str(name)))
                    if os.path.isfile(path):
                        self.play_film(path)
                    else:
                        self.toast(f"Brak pliku: {path}")
                else:
                    self.open_films()
            elif target == "menu":
                self.go_menu()
        elif cmd == "theme":
            name = str(pkt.get("name", ""))
            if name in ("next", "prev"):
                self.cycle_theme(1 if name == "next" else -1)
            elif name in T.THEME_BY_NAME:
                self.set_theme(name)
        elif cmd == "stop":
            if (target == "dashboard" and self.mode == "dash") or \
               (target == "film" and self.mode == "film_play"):
                self.go_menu()

    # ----- nawigacja -----
    def go_menu(self):
        self.stop_film()
        self.mode = "menu"
        self.active_slider = None
        if time.time() - self.ip_time > 5:
            self.ip = get_ip()
            self.ip_time = time.time()

    def go_dash(self):
        self.stop_film()
        self.mode = "dash"

    def go_led(self):
        self.mode = "led"
        self.led_raw({"cmd": "get"})

    def open_themes(self, back):
        self.themes_return = back
        self.mode = "themes"

    def set_theme(self, name, close=False):
        self.theme = T.get_theme(name)
        self.settings["theme"] = self.theme["name"]
        save_settings(self.settings)
        print(f"Tarcza: {self.theme['name']}")
        if close:
            self.mode = self.themes_return

    def cycle_theme(self, step):
        names = [t["name"] for t in T.THEMES]
        i = names.index(self.theme["name"]) if self.theme["name"] in names else 0
        self.set_theme(names[(i + step) % len(names)])

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

    def play_film(self, path):
        self.stop_film()
        args = ["mpv", "--fs", "--no-osc", "--no-osd-bar", "--osd-level=0",
                "--cursor-autohide=always", "--hwdec=auto", "--no-terminal",
                f"--input-conf={MPV_INPUT_CONF}"]
        if FILM_LOOP:
            args.append("--loop=inf")
        if FILM_MUTE:
            args.append("--no-audio")
        args.append(path)
        try:
            self.film_proc = subprocess.Popen(args)
        except FileNotFoundError:
            self.go_menu()
            self.toast("Nie znaleziono mpv (sudo apt install mpv)")
            return
        self.film_name = os.path.basename(path)
        self.mode = "film_play"
        print(f"Film: {path}")

    def stop_film(self):
        proc = self.film_proc
        self.film_proc = None
        if proc is None:
            return
        try:
            proc.terminate()
            proc.wait(timeout=2)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass

    def check_film(self):
        if self.film_proc is not None and self.film_proc.poll() is not None:
            self.film_proc = None
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
                    fn()
                    return
            if x < 80 and y < 80:
                self.go_menu()
            elif x < W // 2:
                self.dash.reset_rpm_scale()
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
                    color=ACCENT_BLUE, font=font_small, sub=self.theme["label"].lower())
        confirm = now < self.confirm_off_until
        self.button((W - x0 - bw, by, bw, bh), "NA PEWNO?" if confirm else "WYŁĄCZ",
                    self.power_off, color=REDLINE_COLOR, font=font_small, active=confirm)

        pc_ok = now - self.last_data < DATA_TIMEOUT
        status = (f"IP: {self.ip}   |   PC: {'dane OK' if pc_ok else 'brak danych'}   |   "
                  f"LED: {self.led_state['mode'] if self.led_online else 'ledd nie odpowiada'}")
        s = render_fit(font_tiny, status, SUBTEXT_COLOR, W - 20)
        screen.blit(s, s.get_rect(center=(W // 2, int(H * 0.94))))

    def draw_dash(self, now):
        th = self.theme
        screen.fill(th["bg"])
        d = self.dash
        T.draw_timing_bar(screen, th, d.current_lap, d.last_lap, d.best_lap, format_lap_time)
        radius = int(min(W * 0.21, H * 0.38))
        center_y = int(H * 0.56)
        T.draw_gauge(screen, th, int(W * 0.26), center_y, radius, d.disp_rpm, d.rpm_scale,
                     "RPM", d.rpm_step, redline=d.rpm_redline, kind="rpm", divide=1000)
        T.draw_gauge(screen, th, int(W * 0.74), center_y, radius, d.disp_speed, d.speed_scale,
                     d.speed_unit, d.speed_step, redline=None, kind="speed", divide=1)

        bw, bh = int(W * 0.12), int(H * 0.09)
        self.button((int(W * 0.01), int(H * 0.89), bw, bh), "< MENU", self.go_menu, font=font_tiny)
        self.button((W - bw - int(W * 0.01), int(H * 0.89), bw, bh), "TARCZA",
                    lambda: self.open_themes("dash"), font=font_tiny)

        if now - self.last_data > DATA_TIMEOUT:
            s = font_small.render(f"Czekam na dane z PC (UDP :{UDP_PORT})...", True, ACCENT_ORANGE)
            screen.blit(s, s.get_rect(center=(W // 2, int(H * 0.17))))

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
        screen.fill(BG_COLOR)
        s = render_fit(font_btn, f"Odtwarzanie: {self.film_name}", TEXT_COLOR, int(W * 0.9))
        screen.blit(s, s.get_rect(center=(W // 2, int(H * 0.35))))
        s = font_small.render("Podwójne dotknięcie filmu lub ESC zamyka film", True, SUBTEXT_COLOR)
        screen.blit(s, s.get_rect(center=(W // 2, int(H * 0.48))))
        self.button((W // 2 - int(W * 0.15), int(H * 0.60), int(W * 0.30), int(H * 0.14)),
                    "ZATRZYMAJ", self.go_menu, color=REDLINE_COLOR)

    def draw_themes(self, now):
        screen.fill(BG_COLOR)
        m = int(W * 0.03)
        self.button((m, int(H * 0.02), int(W * 0.15), int(H * 0.095)), "< WSTECZ",
                    lambda: setattr(self, "mode", self.themes_return), font=font_small)
        title = font_title.render("TARCZE ZEGARÓW", True, TEXT_COLOR)
        screen.blit(title, title.get_rect(center=(W // 2, int(H * 0.07))))

        cols = 5
        rows = math.ceil(len(T.THEMES) / cols)
        gap = int(W * 0.015)
        y0 = int(H * 0.15)
        tw = (W - 2 * m - gap * (cols - 1)) // cols
        th_h = (H - y0 - m - gap * (rows - 1)) // rows
        # wskazówka "pracuje" w podglądzie
        demo = 5200 + 2600 * (0.5 - 0.5 * math.cos(now * 1.3))
        for i, theme in enumerate(T.THEMES):
            col, row = i % cols, i // cols
            rect = pygame.Rect(m + col * (tw + gap), y0 + row * (th_h + gap), tw, th_h)
            pygame.draw.rect(screen, theme["bg"], rect, border_radius=10)
            label_h = font_tiny.get_height() + 8
            r = int(min(tw * 0.40, (th_h - label_h) * 0.42))
            T.draw_gauge(screen, theme, rect.centerx, rect.y + 6 + int(r * 1.12), r, demo, 10000,
                         "RPM", 2000, redline=8500, kind="rpm", divide=1000)
            selected = theme["name"] == self.theme["name"]
            lbl = render_fit(font_tiny, theme["label"], ACCENT_BLUE if selected else TEXT_COLOR, rect.w - 8)
            screen.blit(lbl, lbl.get_rect(midbottom=(rect.centerx, rect.bottom - 4)))
            pygame.draw.rect(screen, ACCENT_BLUE if selected else RING_COLOR, rect,
                             4 if selected else 1, border_radius=10)
            self.hits.append((rect, lambda n=theme["name"]: self.set_theme(n, close=True)))

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
            self.handle_events()
            self.poll_udp(now)
            self.poll_led(now)
            self.check_film()
            self.dash.update(now)
            self.led_flush(now)

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
            draw(now)
            self.draw_toast(now)
            pygame.display.flip()
            clock.tick(15 if self.mode == "film_play" else FPS)  # mniej CPU podczas filmu

        self.stop_film()
        self.led_flush(time.time(), force=True)
        pygame.quit()
        print("=== launcher stop ===")


if __name__ == "__main__":
    App().run()
