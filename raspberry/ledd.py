#!/usr/bin/env python3
"""
ledd.py - demon taśmy LED WS2812 / WS2812B na Raspberry Pi.

Działa jako usługa systemd, niezależnie od PC i od launchera.
Dane wysyłane przez SPI (MOSI = GPIO10, pin 19). Działa na Pi 3 / 4 / 5
bez uprawnień roota (użytkownik musi być w grupie "spi").

Sterowanie: komendy JSON po UDP na port 5006 (z launchera, z PC albo z LED.py):
  {"cmd": "set", "mode": "rainbow", "color": [255, 0, 0], "brightness": 0.5, "speed": 1.0}
  {"cmd": "rpm", "rpm": 7200, "redline": 9000}      # dla trybu "shift"
  {"cmd": "get"}                                    # odpowiedź: {"state": {...}}

Ostatnie ustawienia są zapisywane i przywracane po restarcie.
"""
import colorsys
import json
import math
import os
import random
import signal
import socket
import sys
import time

try:
    import spidev
except ImportError:
    spidev = None

# ===================== KONFIGURACJA =====================
NUM_LEDS = 60            # liczba diod w taśmie
COLOR_ORDER = "GRB"      # WS2812B = GRB; jeśli kolory są zamienione, spróbuj "RGB"
SPI_BUS = 0
SPI_DEVICE = 0
SPI_HZ = 2_400_000       # 3 bity SPI na 1 bit WS2812 -> 1.25 us na bit
MAX_BRIGHTNESS = 0.6     # twardy limit jasności (chroni zasilacz); 1.0 = pełna moc
GAMMA = 2.2              # korekcja gamma (ładniejsze kolory przy niskiej jasności)
FPS = 60
UDP_IP = "0.0.0.0"       # "127.0.0.1" = sterowanie tylko z samego RPi
UDP_PORT = 5006
STATE_FILE = os.path.expanduser("~/.config/ledd/state.json")
# ========================================================

MODES = ("off", "static", "breathe", "rainbow", "cycle",
         "comet", "sparkle", "fire", "police", "shift")

DEFAULT_STATE = {
    "mode": "rainbow",
    "color": [255, 80, 0],
    "brightness": 0.5,
    "speed": 1.0,
}

RESET_BYTES = 100        # ~330 us stanu niskiego = reset/latch taśmy


def log(*args):
    print("[ledd]", *args, flush=True)


# ---------------------------------------------------------------------------
# Wyjście SPI
# ---------------------------------------------------------------------------

def build_lut():
    """Bajt koloru -> 3 bajty SPI (bit 1 = 110, bit 0 = 100)."""
    lut = []
    for b in range(256):
        bits = 0
        for i in range(7, -1, -1):
            bits = (bits << 3) | (0b110 if (b >> i) & 1 else 0b100)
        lut.append(bits.to_bytes(3, "big"))
    return lut


class Strip:
    def __init__(self, n):
        self.n = n
        self.lut = build_lut()
        self.gamma = [int(round(((i / 255.0) ** GAMMA) * 255.0)) for i in range(256)]
        self.order = ["RGB".index(c) for c in COLOR_ORDER.upper()]
        self.spi = None
        if spidev is None:
            log("Brak modułu spidev (sudo apt install python3-spidev) - tryb symulacji.")
            return
        try:
            self.spi = spidev.SpiDev()
            self.spi.open(SPI_BUS, SPI_DEVICE)
            self.spi.max_speed_hz = SPI_HZ
            self.spi.mode = 0
        except Exception as e:
            log(f"Nie można otworzyć /dev/spidev{SPI_BUS}.{SPI_DEVICE}: {e}")
            log("Włącz SPI: sudo raspi-config nonint do_spi 0  (i reboot). Tryb symulacji.")
            self.spi = None

        frame_len = 1 + n * 9 + RESET_BYTES
        if frame_len > 4096:
            log(f"Ramka ma {frame_len} B - upewnij się, że w cmdline.txt jest spidev.bufsiz=65536")

    def show(self, pixels, brightness):
        lut, gam, order = self.lut, self.gamma, self.order
        buf = bytearray(b"\x00")
        for px in pixels:
            for idx in order:
                v = px[idx] * brightness
                if v <= 0:
                    v = 0
                elif v >= 255:
                    v = 255
                else:
                    v = int(v)
                buf += lut[gam[v]]
        buf += bytes(RESET_BYTES)
        if self.spi is not None:
            try:
                self.spi.writebytes2(buf)
            except AttributeError:
                self.spi.writebytes(list(buf))

    def close(self):
        if self.spi is not None:
            try:
                self.show([(0, 0, 0)] * self.n, 0.0)
                self.spi.close()
            except Exception:
                pass


# ---------------------------------------------------------------------------
# Animacje
# ---------------------------------------------------------------------------

def hsv255(h, s=1.0, v=1.0):
    r, g, b = colorsys.hsv_to_rgb(h % 1.0, s, v)
    return (r * 255.0, g * 255.0, b * 255.0)


def scale(c, k):
    return (c[0] * k, c[1] * k, c[2] * k)


def heat_color(h):
    t = max(0.0, min(255.0, h)) / 255.0 * 3.0
    if t < 1.0:
        return (t * 255.0, 0.0, 0.0)
    if t < 2.0:
        return (255.0, (t - 1.0) * 255.0, 0.0)
    return (255.0, 255.0, (t - 2.0) * 255.0)


class Animator:
    def __init__(self, n):
        self.n = n
        self.phase = 0.0
        self.heat = [0.0] * n
        self.spark = [0.0] * n

    def render(self, st, dt, now, rpm):
        n = self.n
        mode = st["mode"]
        speed = st["speed"]
        c = st["color"]
        self.phase += dt * speed
        p = self.phase

        if mode == "off":
            return [(0, 0, 0)] * n

        if mode == "static":
            return [tuple(c)] * n

        if mode == "breathe":
            k = 0.06 + 0.94 * (0.5 - 0.5 * math.cos(p * 2.0 * math.pi * 0.4))
            return [scale(c, k)] * n

        if mode == "rainbow":
            return [hsv255(i / n + p * 0.25) for i in range(n)]

        if mode == "cycle":
            return [hsv255(p * 0.1)] * n

        if mode == "comet":
            head = (p * n * 0.5) % n
            tail = max(3.0, n * 0.25)
            out = []
            for i in range(n):
                d = (head - i) % n
                k = (1.0 - d / tail) ** 2 if d < tail else 0.0
                out.append(scale(c, k))
            return out

        if mode == "sparkle":
            decay = math.exp(-dt * 3.0 * speed)
            sp = self.spark
            for i in range(n):
                sp[i] *= decay
            chance = dt * speed * n * 0.08
            while chance > 0.0:
                if random.random() < chance:
                    sp[random.randrange(n)] = 1.0
                chance -= 1.0
            return [scale(c, max(0.03, s)) for s in sp]

        if mode == "fire":
            self._fire(speed)
            return [heat_color(h) for h in self.heat]

        if mode == "police":
            side = int(p * 3.0) % 2
            on = int(p * 12.0) % 2 == 0
            half = n // 2
            out = []
            for i in range(n):
                if on and side == 0 and i < half:
                    out.append((255, 0, 0))
                elif on and side == 1 and i >= half:
                    out.append((0, 0, 255))
                else:
                    out.append((0, 0, 0))
            return out

        if mode == "shift":
            return self._shift(rpm, now, c, p)

        return [(0, 0, 0)] * n

    def _fire(self, speed):
        n = self.n
        h = self.heat
        cool = 55.0 * 10.0 / n + 2.0
        for i in range(n):
            h[i] = max(0.0, h[i] - random.uniform(0.0, cool) * speed)
        for k in range(n - 1, 1, -1):
            h[k] = (h[k - 1] + 2.0 * h[k - 2]) / 3.0
        if random.random() < 0.5 * min(1.0, speed):
            y = random.randrange(min(7, n))
            h[y] = min(255.0, h[y] + random.uniform(160.0, 255.0))

    def _shift(self, rpm, now, c, p):
        """Shift-light: pasek rośnie z obrotami, przy redline miga na niebiesko."""
        n = self.n
        if now - rpm["t"] > 1.5 or rpm["redline"] <= 0:
            # brak telemetrii -> delikatne "oddychanie" wybranym kolorem
            k = 0.05 + 0.07 * (0.5 - 0.5 * math.cos(p * 2.0 * math.pi * 0.3))
            return [scale(c, k)] * n

        frac = rpm["rpm"] / rpm["redline"]
        if frac >= 0.98:
            on = int(now * 12.0) % 2 == 0
            return [(0, 80, 255) if on else (0, 0, 0)] * n

        start = 0.55  # od jakiego % redline zaczynają się zapalać diody
        lit = max(0.0, (frac - start) / (1.0 - start)) * n
        out = []
        for i in range(n):
            pos = i / max(1, n - 1)
            if pos < 0.6:
                col = (0, 255, 0)
            elif pos < 0.85:
                col = (255, 200, 0)
            else:
                col = (255, 0, 0)
            k = max(0.0, min(1.0, lit - i))
            out.append(scale(col, k))
        return out


# ---------------------------------------------------------------------------
# Stan
# ---------------------------------------------------------------------------

def apply_set(state, msg):
    changed = False
    mode = msg.get("mode")
    if mode in MODES and mode != state["mode"]:
        state["mode"] = mode
        changed = True
    col = msg.get("color")
    if isinstance(col, (list, tuple)) and len(col) == 3:
        try:
            new = [max(0, min(255, int(v))) for v in col]
            if new != state["color"]:
                state["color"] = new
                changed = True
        except (TypeError, ValueError):
            pass
    for key, lo, hi in (("brightness", 0.0, 1.0), ("speed", 0.1, 5.0)):
        if key in msg:
            try:
                v = max(lo, min(hi, float(msg[key])))
                if v != state[key]:
                    state[key] = v
                    changed = True
            except (TypeError, ValueError):
                pass
    return changed


def load_state():
    state = json.loads(json.dumps(DEFAULT_STATE))
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            apply_set(state, json.load(f))
    except FileNotFoundError:
        pass
    except Exception as e:
        log(f"Nie można wczytać {STATE_FILE}: {e}")
    return state


def save_state(state):
    try:
        os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
        tmp = STATE_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(state, f)
        os.replace(tmp, STATE_FILE)
    except Exception as e:
        log(f"Nie można zapisać stanu: {e}")


# ---------------------------------------------------------------------------
# Pętla główna
# ---------------------------------------------------------------------------

def main():
    state = load_state()
    strip = Strip(NUM_LEDS)
    anim = Animator(NUM_LEDS)
    rpm_info = {"rpm": 0.0, "redline": 0.0, "t": 0.0}

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind((UDP_IP, UDP_PORT))
    sock.setblocking(False)
    log(f"Start: {NUM_LEDS} LED, UDP {UDP_IP}:{UDP_PORT}, tryb {state['mode']}")

    running = True

    def stop(*_):
        nonlocal running
        running = False

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)

    dirty = False
    last_save = 0.0
    last_static = None
    last_out = 0.0
    frame = 1.0 / FPS
    last = time.monotonic()

    while running:
        now = time.monotonic()
        dt = min(0.1, now - last)
        last = now

        while True:
            try:
                data, addr = sock.recvfrom(2048)
            except (BlockingIOError, InterruptedError):
                break
            except OSError:
                break
            try:
                msg = json.loads(data.decode("utf-8"))
                if not isinstance(msg, dict):
                    continue
            except Exception:
                continue
            cmd = msg.get("cmd", "set")
            if cmd == "set":
                if apply_set(state, msg):
                    dirty = True
                try:
                    sock.sendto(json.dumps({"state": state}).encode("utf-8"), addr)
                except OSError:
                    pass
            elif cmd == "rpm":
                try:
                    rpm_info["rpm"] = max(0.0, float(msg.get("rpm", 0.0)))
                    rpm_info["redline"] = max(0.0, float(msg.get("redline", 0.0)))
                    rpm_info["t"] = now
                except (TypeError, ValueError):
                    pass
            elif cmd == "get":
                try:
                    sock.sendto(json.dumps({"state": state}).encode("utf-8"), addr)
                except OSError:
                    pass

        if dirty and now - last_save > 2.0:
            save_state(state)
            dirty = False
            last_save = now

        # Tryby statyczne: odświeżaj taśmę tylko po zmianie (i raz na sekundę dla pewności)
        static_key = (state["mode"], tuple(state["color"]), state["brightness"])
        if state["mode"] in ("off", "static") and static_key == last_static and now - last_out < 1.0:
            time.sleep(0.03)
            continue
        last_static = static_key if state["mode"] in ("off", "static") else None
        last_out = now

        pixels = anim.render(state, dt, now, rpm_info)
        strip.show(pixels, state["brightness"] * MAX_BRIGHTNESS)

        sleep = frame - (time.monotonic() - now)
        if sleep > 0:
            time.sleep(sleep)

    if dirty:
        save_state(state)
    strip.close()
    sock.close()
    log("Stop.")


if __name__ == "__main__":
    sys.exit(main())
