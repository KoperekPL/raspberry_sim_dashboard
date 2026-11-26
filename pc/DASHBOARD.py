import ctypes
import json
import math
import socket
import subprocess
import threading
import time
from hydrosim_sdk import HydroSimSDK

RPI_IP = "192.168.0.112"
RPI_USER = "pi"             # użytkownik SSH na RPi (logowanie kluczem, bez hasła)
AUTO_START_LAUNCHER = True  # jeśli launcher na RPi nie działa - uruchom go przez SSH
RPI_PORT = 5005
SEND_HZ = 60

# Tarcza zegarów ustawiana przy starcie (puste = zostaw tę wybraną na RPi).
# Tarcze: modern, vintage, classic, sport, marine, neon, carbon, digital, minimal, night
# Ekrany: proline, f1, endurance, hud, synthwave, orbit, lava, matrix, warp, scope
THEME = ""

# Jeśli prędkość na zegarze będzie ok. 2.24x mniejsza niż na HUD w grze,
# zmień poniższą wartość na 2.23694 (przeliczenie z m/s na MPH).
SPEED_MULTIPLIER = 1.0

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sdk_instance = None
cleanup_lock = threading.Lock()
cleanup_done = False

last_log_time = 0.0
printed_driver_fields = False

CURRENT_LAP_KEYS = (
    "currentlaptime", "curlaptime", "laptime", "currentlap",
    "elapsedlaptime", "currenttime", "lapelapsed", "curtime"
)
LAST_LAP_KEYS = (
    "lastlaptime", "prevlaptime", "previouslaptime", "lasttime"
)
BEST_LAP_KEYS = (
    "bestlaptime", "fastestlaptime", "personalbestlaptime",
    "personalbest", "besttime"
)


# --- Sterowanie launcherem na Raspberry Pi (komendy UDP, bez SSH) ---

# Uruchomienie launchera w sesji pulpitu RPi (te same zmienne środowiska co dawniej przy SSH).
# run.sh pilnuje restartu po awarii; drugi launcher sam się wyłączy, jeśli jeden już działa.
REMOTE_START = (
    "if pgrep -f '[l]auncher.py' >/dev/null; then echo 'launcher: proces istnieje'; else "
    "WD=$(find /run/user/$(id -u) -maxdepth 1 -type s -name 'wayland-*' -printf '%f\\n' 2>/dev/null | head -n1); "
    "export XDG_RUNTIME_DIR=/run/user/$(id -u) WAYLAND_DISPLAY=${WD:-wayland-0} DISPLAY=:0; "
    "setsid -f bash \"$HOME/pi-launcher/run.sh\" >/dev/null 2>&1 </dev/null; "
    "echo 'launcher: uruchomiony'; fi"
)


def ping_launcher(timeout=1.0):
    """True, jeśli launcher na RPi odpowiada na UDP."""
    try:
        sock.settimeout(timeout)
        sock.sendto(b'{"cmd": "ping"}', (RPI_IP, RPI_PORT))
        end = time.time() + timeout
        while time.time() < end:
            data, _ = sock.recvfrom(2048)
            if b"pong" in data:
                return True
    except (socket.timeout, OSError):
        pass
    finally:
        sock.settimeout(None)
    return False


def ensure_launcher():
    """Sprawdź, czy launcher działa; jeśli nie - uruchom go przez SSH i poczekaj, aż się wczyta."""
    if ping_launcher(1.0):
        print("Launcher na Raspberry Pi działa.")
        return True
    if not AUTO_START_LAUNCHER:
        print("UWAGA: launcher na Raspberry Pi nie odpowiada.")
        return False

    print(f"Launcher nie odpowiada - uruchamiam go przez SSH ({RPI_USER}@{RPI_IP})...")
    try:
        r = subprocess.run(
            ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=5", f"{RPI_USER}@{RPI_IP}", REMOTE_START],
            capture_output=True, text=True, timeout=20,
        )
        msg = (r.stdout + r.stderr).strip()
        if msg:
            print("RPi:", msg)
    except FileNotFoundError:
        print("Brak programu ssh na tym komputerze.")
    except subprocess.TimeoutExpired:
        print("SSH nie odpowiada (RPi wyłączone albo inny adres?).")

    print("Czekam, aż launcher się wczyta...")
    end = time.time() + 90
    while time.time() < end:
        if ping_launcher(1.0):
            print("Launcher gotowy.")
            return True
        time.sleep(0.5)
    print("UWAGA: launcher nadal nie odpowiada - wysyłam dane mimo to.")
    return False


def send_cmd(obj, repeat=3):
    """Komenda JSON do launchera na RPi (UDP może zgubić pakiet, więc wysyłamy kilka razy)."""
    data = json.dumps(obj).encode("utf-8")
    for _ in range(repeat):
        try:
            sock.sendto(data, (RPI_IP, RPI_PORT))
        except OSError:
            pass
        time.sleep(0.02)


def cleanup():
    global cleanup_done
    with cleanup_lock:
        if cleanup_done:
            return
        cleanup_done = True

    print("\nPowrót Raspberry Pi do menu...")
    send_cmd({"cmd": "stop", "mode": "dashboard"})

    if sdk_instance is not None:
        for method_name in ("stop", "shutdown"):
            fn = getattr(sdk_instance, method_name, None)
            if callable(fn):
                try:
                    fn()
                except Exception:
                    pass
    try:
        sock.close()
    except Exception:
        pass


# Przechwycenie zamknięcia okna przyciskiem X w Windows
HANDLER_ROUTINE = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_uint)


def _win_ctrl_handler(ctrl_type):
    # 2 = CTRL_CLOSE_EVENT, 5 = LOGOFF, 6 = SHUTDOWN
    if ctrl_type in (2, 5, 6):
        cleanup()
        return False
    # 0 = CTRL_C_EVENT -> pozwól Pythonowi wywołać KeyboardInterrupt i finally
    return False


_console_handler = HANDLER_ROUTINE(_win_ctrl_handler)
ctypes.windll.kernel32.SetConsoleCtrlHandler(_console_handler, True)


# --- Odczyt telemetrii z HydroSim ---

def safe_float(val, default=0.0):
    try:
        f = float(val)
        return f if math.isfinite(f) else default
    except Exception:
        return default


def normalize_lap_seconds(val):
    sec = safe_float(val, 0.0)
    if sec <= 0.0 or sec >= 1e7:
        return 0.0
    if sec > 3600.0:
        sec /= 1000.0
    return sec


def unwrap(obj):
    if obj is None:
        return None
    if hasattr(obj, "data") and obj.data is not None:
        return obj.data
    return obj


def get_field_names(obj):
    if obj is None:
        return []
    names = []
    if hasattr(obj, "_fields_"):
        names.extend(name for name, _ in obj._fields_)
    for name in dir(obj):
        if not name.startswith("__") and name not in names:
            names.append(name)
    return names


def get_ci_attr(obj, candidate_keys):
    if obj is None:
        return None
    norm_map = {}
    for name in get_field_names(obj):
        norm = name.lstrip("_").lower()
        if norm not in norm_map:
            norm_map[norm] = name
    for key in candidate_keys:
        real_name = norm_map.get(key.lower())
        if real_name is not None:
            try:
                val = getattr(obj, real_name)
                if not callable(val):
                    return val
            except Exception:
                pass
    return None


def get_telemetry_obj(sdk):
    for attr in ("telemetry", "telemetry_file"):
        obj = getattr(sdk, attr, None)
        for cand in (obj, unwrap(obj)):
            if cand is not None and (hasattr(cand, "rpm") or hasattr(cand, "_rpm")):
                return cand
    return None


def get_local_driver(sdk):
    timing = unwrap(getattr(sdk, "timing", None)) or unwrap(getattr(sdk, "timing_file", None))
    if timing is None:
        return None
    drivers = get_ci_attr(timing, ("drivers",))
    if drivers is None:
        return None

    for drv in drivers:
        if bool(get_ci_attr(drv, ("islocalplayer", "isplayer", "localplayer"))):
            return drv

    count = int(safe_float(get_ci_attr(timing, ("driverscount",)), 0))
    if count > 0:
        return drivers[0]
    return None


def get_session_time(sdk):
    session = unwrap(getattr(sdk, "session", None)) or unwrap(getattr(sdk, "session_file", None))
    if session is None:
        return 0.0
    val = get_ci_attr(session, ("sessiontime", "elapsedtime", "time", "currenttime", "clock"))
    return normalize_lap_seconds(val)


def get_lap_times(sdk):
    global printed_driver_fields
    drv = get_local_driver(sdk)
    if drv is None:
        return 0.0, 0.0, 0.0

    cur_lap = normalize_lap_seconds(get_ci_attr(drv, CURRENT_LAP_KEYS))
    last_lap = normalize_lap_seconds(get_ci_attr(drv, LAST_LAP_KEYS))
    best_lap = normalize_lap_seconds(get_ci_attr(drv, BEST_LAP_KEYS))

    lap_times_arr = get_ci_attr(drv, ("laptimes",))
    completed = []
    if lap_times_arr is not None:
        for v in lap_times_arr:
            s = normalize_lap_seconds(v)
            if s > 0.0:
                completed.append(s)

    if last_lap <= 0.0 and completed:
        last_lap = completed[-1]
    if best_lap <= 0.0 and completed:
        best_lap = min(completed)

    if cur_lap <= 0.0:
        lap_start = normalize_lap_seconds(get_ci_attr(drv, ("lapstarttime", "currentlapstarttime", "starttime")))
        sess_time = get_session_time(sdk)
        if lap_start > 0.0 and sess_time >= lap_start:
            cur_lap = sess_time - lap_start
        else:
            total_t = normalize_lap_seconds(get_ci_attr(drv, ("totaltime", "racetime")))
            if total_t > sum(completed):
                cur_lap = total_t - sum(completed)

    return cur_lap, last_lap, best_lap


def get_extras(sdk, t):
    """Dodatkowe dane dla ekranów na RPi - wysyłane tylko, jeśli SDK je udostępnia."""
    extras = {}
    thr = get_ci_attr(t, ("throttle", "throttleinput", "throttlepos", "throttleposition"))
    if isinstance(thr, (int, float)):
        v = safe_float(thr, -1.0)
        if v > 1.5:
            v /= 100.0
        if 0.0 <= v <= 1.0:
            extras["throttle"] = round(v, 3)
    drv = get_local_driver(sdk)
    if drv is not None:
        pos = get_ci_attr(drv, ("position", "raceposition", "place"))
        if isinstance(pos, (int, float)) and 0 < pos < 100:
            extras["position"] = int(pos)
        lap = get_ci_attr(drv, ("lap", "lapnumber", "currentlapnumber"))
        if isinstance(lap, (int, float)) and 0 < lap < 10000:
            extras["lap"] = int(lap)
        else:
            done = get_ci_attr(drv, ("lapscompleted", "completedlaps", "lapcount"))
            if isinstance(done, (int, float)) and 0 <= done < 10000:
                extras["lap"] = int(done) + 1
    return extras


def fmt_time(sec):
    if sec <= 0.0:
        return "--:--.---"
    total_ms = int(round(sec * 1000.0))
    m, rem = divmod(total_ms, 60000)
    s, ms = divmod(rem, 1000)
    return f"{m:02d}:{s:02d}.{ms:03d}"


def send_telemetry(sdk):
    global last_log_time
    t = get_telemetry_obj(sdk)
    if t is None:
        return

    rpm = max(0.0, safe_float(get_ci_attr(t, ("rpm",)), 0.0))
    max_rpm = max(0.0, safe_float(get_ci_attr(t, ("maxrpm",)), 0.0))
    limiter_rpm = max(0.0, safe_float(get_ci_attr(t, ("limiterrpm",)), 0.0))
    max_n2_rpm = max(0.0, safe_float(get_ci_attr(t, ("maxn2rpm",)), 0.0))
    raw_speed = abs(safe_float(get_ci_attr(t, ("speed",)), 0.0))
    speed_mph = raw_speed * SPEED_MULTIPLIER

    effective_max_rpm = max(max_rpm, limiter_rpm)
    if max_n2_rpm > effective_max_rpm and rpm > effective_max_rpm * 1.1:
        effective_max_rpm = max_n2_rpm
    if effective_max_rpm <= 0.0 or rpm > effective_max_rpm * 1.15:
        effective_max_rpm = 0.0

    cur_lap, last_lap, best_lap = get_lap_times(sdk)

    data = {
        "rpm": rpm,
        "max_rpm": effective_max_rpm,
        "speed": speed_mph,
        "unit": "MPH",
        "current_lap": cur_lap,
        "last_lap": last_lap,
        "best_lap": best_lap,
    }
    try:
        data.update(get_extras(sdk, t))
    except Exception:
        pass
    payload = json.dumps(data).encode("utf-8")
    sock.sendto(payload, (RPI_IP, RPI_PORT))

    now = time.time()
    if now - last_log_time >= 1.0:
        print(
            f"RPM: {rpm:7.0f} | Speed: {speed_mph:5.1f} MPH | "
            f"CUR: {fmt_time(cur_lap)} | LAST: {fmt_time(last_lap)} | BEST: {fmt_time(best_lap)}"
        )
        last_log_time = now


def main():
    global sdk_instance
    try:
        ensure_launcher()
        print(f"Przełączanie Raspberry Pi ({RPI_IP}) na dashboard...")
        send_cmd({"cmd": "mode", "mode": "dashboard"})
        if THEME:
            send_cmd({"cmd": "theme", "name": THEME})
        sdk_instance = HydroSimSDK()
        print(f"Start HydroSim -> UDP {RPI_IP}:{RPI_PORT} (Ctrl+C lub X kończy i wraca RPi do menu)")
        sdk_instance.start()

        interval = 1.0 / SEND_HZ
        while True:
            send_telemetry(sdk_instance)
            time.sleep(interval)
    except KeyboardInterrupt:
        pass
    finally:
        cleanup()


if __name__ == "__main__":
    main()