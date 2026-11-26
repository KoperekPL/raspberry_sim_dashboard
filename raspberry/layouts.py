"""
layouts.py - pełnoekranowe ekrany dashboardu (w stylu wyświetlaczy wyścigowych + abstrakcyjne).

Każdy ekran to funkcja draw(surf, d, now, dt), gdzie d to DashView z danymi.
Statyczne tło każdego ekranu jest renderowane raz (cached_bg), a co klatkę
rysowane są tylko elementy zmienne - dzięki temu działa płynnie na RPi.

Nowy ekran: napisz funkcję draw_xxx i dopisz ją do LAYOUTS na dole pliku.
"""
import math
import random
from collections import deque

import pygame

from themes import arc_poly, finalize, get_font, lerp


# ---------------------------------------------------------------------------
# Dane dla ekranów
# ---------------------------------------------------------------------------
class DashView:
    def __init__(self):
        self.rpm = 0.0
        self.redline = 8500.0
        self.rpm_max = 10000.0
        self.rpm_step = 1000.0
        self.speed = 0.0
        self.speed_max = 220.0
        self.speed_step = 20.0
        self.unit = "MPH"
        self.cur = 0.0
        self.last = 0.0
        self.best = 0.0
        self.lap = 1
        self.delta = None        # ostatnie okrążenie - najlepsze [s]
        self.vmax = 0.0
        self.session = 0.0
        self.throttle = None     # 0..1, jeśli PC wysyła
        self.position = None
        self.online = True
        self.hist_rpm = deque(maxlen=300)    # ułamki rpm/rpm_max (30 Hz -> 10 s)
        self.hist_speed = deque(maxlen=300)

    @property
    def rpm_frac(self):
        ref = self.redline if self.redline > 0 else self.rpm_max
        return max(0.0, self.rpm / ref) if ref > 0 else 0.0

    @property
    def speed_frac(self):
        return clamp(self.speed / self.speed_max, 0.0, 1.0) if self.speed_max > 0 else 0.0


def sample_view():
    """Przykładowe dane do miniatur w ekranie wyboru."""
    v = DashView()
    v.rpm, v.redline, v.rpm_max, v.rpm_step = 7400.0, 8500.0, 10000.0, 1000.0
    v.speed, v.unit = 104.0, "MPH"
    v.cur, v.last, v.best, v.lap, v.delta = 42.317, 61.204, 60.912, 7, 0.292
    v.vmax, v.session, v.throttle, v.position = 118.0, 754.0, 0.82, 3
    for i in range(300):
        t = i / 30.0
        v.hist_rpm.append(0.55 + 0.25 * math.sin(t * 0.9) + 0.08 * math.sin(t * 3.1))
        v.hist_speed.append(0.45 + 0.15 * math.sin(t * 0.5 + 1.0))
    return v


# ---------------------------------------------------------------------------
# Pomocnicze
# ---------------------------------------------------------------------------
def clamp(v, lo, hi):
    return lo if v < lo else hi if v > hi else v


def fmt_lap(sec):
    if sec is None or sec <= 0.0:
        return "--:--.---"
    ms = int(round(sec * 1000.0))
    m, rem = divmod(ms, 60000)
    s, ms = divmod(rem, 1000)
    return f"{m:02d}:{s:02d}.{ms:03d}"


def fmt_short(sec):
    if sec is None or sec <= 0.0:
        return "-:--.--"
    cs = int(round(sec * 100.0))
    m, rem = divmod(cs, 6000)
    s, cs = divmod(rem, 100)
    return f"{m}:{s:02d}.{cs:02d}"


def fmt_delta(d):
    return "--.---" if d is None else f"{d:+.3f}"


def delta_color(d, good=(40, 230, 90), bad=(255, 60, 50), neutral=(200, 200, 200)):
    if d is None:
        return neutral
    return good if d <= 0 else bad


def fmt_int(v):
    return f"{int(round(v)):,}".replace(",", " ")


def fmt_clock(sec):
    sec = int(max(0, sec))
    h, rem = divmod(sec, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


_text_cache = {}


def text(surf, s, family, size, color, pos, anchor="center", bold=True):
    """Tekst z małym cache gotowych napisów (te same napisy nie są renderowane co klatkę)."""
    font = get_font(family, size, bold)
    key = (id(font), s, color)
    img = _text_cache.get(key)
    if img is None:
        if len(_text_cache) > 1500:
            _text_cache.clear()
        img = font.render(s, True, color)
        _text_cache[key] = img
    r = img.get_rect(**{anchor: pos})
    surf.blit(img, r)
    return r


def glow_text(surf, s, family, size, color, glow, pos, anchor="center", spread=2):
    for dx, dy in ((-spread, 0), (spread, 0), (0, -spread), (0, spread)):
        text(surf, s, family, size, glow, (pos[0] + dx, pos[1] + dy), anchor)
    return text(surf, s, family, size, color, pos, anchor)


_bg_cache = {}


def cached_bg(key, size, builder):
    k = (key, size)
    surf = _bg_cache.get(k)
    if surf is None:
        if len(_bg_cache) > 60:
            _bg_cache.clear()
        surf = pygame.Surface(size)
        builder(surf, size[0], size[1])
        surf = finalize(surf, alpha=False)
        _bg_cache[k] = surf
    return surf


_state = {}


def state(name, size):
    return _state.setdefault((name, size), {})


def vgradient(surf, rect, top, bottom):
    rect = pygame.Rect(rect)
    for y in range(rect.h):
        pygame.draw.line(surf, lerp(top, bottom, y / max(1, rect.h - 1)),
                         (rect.x, rect.y + y), (rect.right - 1, rect.y + y))


def hgradient_surface(w, h, stops):
    """Poziomy gradient z listy (pozycja 0..1, kolor)."""
    surf = pygame.Surface((max(1, w), max(1, h)))
    for x in range(max(1, w)):
        f = x / max(1, w - 1)
        for i in range(len(stops) - 1):
            if stops[i][0] <= f <= stops[i + 1][0]:
                t = (f - stops[i][0]) / max(1e-6, stops[i + 1][0] - stops[i][0])
                col = lerp(stops[i][1], stops[i + 1][1], t)
                break
        else:
            col = stops[-1][1]
        pygame.draw.line(surf, col, (x, 0), (x, h))
    return finalize(surf, alpha=False)


def radial_fill(surf, c, r, inner, outer, step=2):
    for rr in range(int(r), 0, -step):
        pygame.draw.circle(surf, lerp(inner, outer, rr / r), c, rr)


def shift_colors(n, frac, scheme, now, start=0.55):
    """Kolory diod shift-light (None = zgaszona)."""
    if frac >= 0.98:
        on = int(now * 10) % 2 == 0
        return [(70, 120, 255) if on else None] * n
    lit = max(0.0, (frac - start) / (1.0 - start)) * n
    out = []
    for i in range(n):
        p = i / max(1, n - 1)
        if scheme == "f1":
            col = (40, 230, 70) if p < 0.34 else (255, 40, 40) if p < 0.67 else (60, 110, 255)
        elif scheme == "pro":
            col = (120, 110, 255) if p < 0.3 else (90, 240, 240) if p < 0.7 else (110, 245, 120)
        else:
            col = (40, 230, 70) if p < 0.5 else (255, 210, 0) if p < 0.8 else (255, 40, 40)
        out.append(col if i < lit else None)
    return out


def rpm_heat(frac):
    """Kolor od zimnego (niebieski) do gorącego (czerwony) zależnie od obrotów."""
    if frac < 0.8:
        return lerp((60, 110, 255), (255, 140, 0), frac / 0.8)
    return lerp((255, 140, 0), (255, 20, 40), (frac - 0.8) / 0.2)


# ---------------------------------------------------------------------------
# 1. PROLINE - wyświetlacz wyścigowy (inspiracja z dashy klubowych)
# ---------------------------------------------------------------------------
PRO_START, PRO_SWEEP = 160.0, 200.0


def draw_proline(s, d, now, dt):
    w, h = s.get_size()
    panel = pygame.Rect(int(w * 0.02), int(h * 0.15), int(w * 0.96), int(h * 0.80))
    info_h = int(h * 0.075)
    R = int(min(h * 0.40, w * 0.25))
    cx, cy = int(w * 0.29), int(panel.y + R * 1.05)
    col_x = int(w * 0.57)
    row_top = panel.y
    row_h = (panel.h - info_h) // 4

    def bg(b, w, h):
        b.fill((6, 8, 14))
        vgradient(b, panel, (24, 60, 112), (12, 32, 66))
        for i in range(4):
            r = pygame.Rect(col_x, row_top + i * row_h, panel.right - col_x, row_h)
            pygame.draw.rect(b, (26, 68, 124) if i % 2 == 0 else (18, 50, 96), r)
        b.set_clip(panel.x, panel.y, panel.w, panel.h - info_h)
        pygame.draw.circle(b, (8, 14, 26), (cx, cy), int(R * 1.02))
        # podziałka drobna
        for i in range(81):
            a = math.radians(PRO_START + i / 80 * PRO_SWEEP)
            r0 = R * (0.90 if i % 10 == 0 else 0.94)
            pygame.draw.line(b, (150, 160, 175) if i % 10 else (230, 235, 245),
                             (cx + math.cos(a) * r0, cy + math.sin(a) * r0),
                             (cx + math.cos(a) * R * 0.985, cy + math.sin(a) * R * 0.985), 2)
        radial_fill(b, (cx, cy), R * 0.64, (40, 110, 210), (14, 36, 74), 3)
        pygame.draw.circle(b, (90, 170, 255), (cx, cy), int(R * 0.64), max(2, int(R * 0.02)))
        pygame.draw.circle(b, (12, 30, 62), (cx, cy), int(R * 0.585))
        pygame.draw.line(b, (110, 140, 190), (cx - R * 0.42, cy + R * 0.02), (cx + R * 0.42, cy + R * 0.02), 2)
        nt = [(cx - R * 0.34, cy - R * 0.70), (cx + R * 0.34, cy - R * 0.70),
              (cx + R * 0.22, cy - R * 0.40), (cx - R * 0.22, cy - R * 0.40)]
        pygame.draw.polygon(b, (34, 80, 150), nt)
        b.set_clip(None)
        pygame.draw.rect(b, (196, 200, 208), (panel.x, panel.bottom - info_h, panel.w, info_h))
        for i, lbl in enumerate(("LAP TIME", "LAST", "BEST", "DELTA")):
            text(b, lbl, "sans", h * 0.035, (140, 190, 255),
                 (panel.right - w * 0.015, row_top + i * row_h + row_h * 0.80), "midright")
        text(b, "LAP", "sans", h * 0.032, (140, 190, 255), (panel.x + w * 0.012, panel.y + h * 0.10), "topleft")
        pygame.draw.rect(b, (40, 44, 52), (int(w * 0.22), int(h * 0.035), int(w * 0.56), int(h * 0.085)),
                         border_radius=int(h * 0.04))

    s.blit(cached_bg("proline", (w, h), bg), (0, 0))

    # diody
    leds = shift_colors(10, d.rpm_frac, "pro", now)
    lw = w * 0.56 / 10
    for i, col in enumerate(leds):
        r = pygame.Rect(int(w * 0.22 + i * lw + lw * 0.12), int(h * 0.05), int(lw * 0.76), int(h * 0.055))
        pygame.draw.rect(s, col or (58, 62, 74), r, border_radius=r.h // 2)

    # skala RPM: liczby (zależne od skali, rysowane z cache napisów)
    s.set_clip(panel.x, panel.y, panel.w, panel.h - info_h)
    n = max(1, int(round(d.rpm_max / d.rpm_step)))
    for i in range(n + 1):
        f = i / n
        a = math.radians(PRO_START + f * PRO_SWEEP)
        val = f * d.rpm_max
        col = (255, 90, 80) if val >= d.redline else (100, 175, 255)
        text(s, str(int(round(val / 1000))), "sans", h * 0.07, col,
             (cx + math.cos(a) * R * 0.78, cy + math.sin(a) * R * 0.78))
    frac = clamp(d.rpm / d.rpm_max, 0, 1)
    arc_poly(s, (90, 170, 255), (cx, cy), R * 0.655, R * 0.70, 0, frac, PRO_START, PRO_SWEEP)
    a = math.radians(PRO_START + frac * PRO_SWEEP)
    ca, sa = math.cos(a), math.sin(a)
    tip = (cx + ca * R * 0.88, cy + sa * R * 0.88)
    pygame.draw.polygon(s, (255, 255, 255), [
        tip, (cx + ca * R * 1.0 - sa * R * 0.05, cy + sa * R * 1.0 + ca * R * 0.05),
        (cx + ca * R * 1.0 + sa * R * 0.05, cy + sa * R * 1.0 - ca * R * 0.05)])
    s.set_clip(None)

    big = str(d.position) if d.position else str(d.lap)
    text(s, big, "sans", R * 0.26, (255, 255, 255), (cx, cy - R * 0.55))
    text(s, fmt_int(d.rpm), "sans", R * 0.28, (255, 255, 255), (cx, cy - R * 0.17))
    text(s, fmt_int(d.speed), "sans", R * 0.24, (255, 255, 255), (cx, cy + R * 0.20))
    text(s, d.unit.lower(), "sans", R * 0.07, (150, 190, 255), (cx, cy + R * 0.38))

    vals = [(fmt_lap(d.cur), (255, 255, 255)), (fmt_lap(d.last), (255, 255, 255)),
            (fmt_lap(d.best), (255, 255, 255)), (fmt_delta(d.delta), delta_color(d.delta))]
    for i, (v, col) in enumerate(vals):
        text(s, v, "sans", h * 0.085, col, (panel.right - w * 0.015, row_top + i * row_h + row_h * 0.40), "midright")
    text(s, str(d.lap), "sans", h * 0.075, (255, 255, 255), (panel.x + w * 0.012, panel.y + h * 0.01), "topleft")
    thr = f"   GAZ {int(d.throttle * 100)}%" if d.throttle is not None else ""
    text(s, f"TOP {int(d.vmax)} {d.unit}   SESJA {fmt_clock(d.session)}{thr}", "sans", h * 0.035,
         (20, 24, 32), (w // 2, panel.bottom - info_h // 2))


# ---------------------------------------------------------------------------
# 2. F1 - wyświetlacz z kierownicy
# ---------------------------------------------------------------------------
def draw_f1(s, d, now, dt):
    w, h = s.get_size()
    teal = (0, 215, 190)
    box = pygame.Rect(int(w * 0.33), int(h * 0.16), int(w * 0.34), int(h * 0.50))
    side_w = int(w * 0.29)
    lt = pygame.Rect(int(w * 0.02), box.y, side_w, int(h * 0.24))
    lb = pygame.Rect(int(w * 0.02), box.y + int(h * 0.26), side_w, int(h * 0.24))
    rt = pygame.Rect(w - int(w * 0.02) - side_w, box.y, side_w, int(h * 0.24))
    rb = pygame.Rect(w - int(w * 0.02) - side_w, box.y + int(h * 0.26), side_w, int(h * 0.24))
    bar = pygame.Rect(int(w * 0.04), int(h * 0.80), int(w * 0.80), int(h * 0.12))

    def bg(b, w, h):
        b.fill((4, 4, 6))
        pygame.draw.rect(b, (14, 16, 20), box, border_radius=int(h * 0.03))
        pygame.draw.rect(b, teal, box, max(2, int(h * 0.008)), border_radius=int(h * 0.03))
        for r, lbl in ((lt, "DELTA"), (lb, "LAST"), (rt, "BEST"), (rb, "LAP")):
            pygame.draw.rect(b, (20, 22, 28), r, border_radius=int(h * 0.02))
            pygame.draw.rect(b, teal, (r.x, r.y, max(3, int(w * 0.006)), r.h))
            text(b, lbl, "cond", h * 0.04, (150, 160, 170), (r.x + w * 0.02, r.y + h * 0.015), "topleft")
        pygame.draw.rect(b, (24, 26, 32), bar)
        for i in range(1, 20):
            x = bar.x + bar.w * i // 20
            pygame.draw.line(b, (4, 4, 6), (x, bar.y), (x, bar.bottom), 3)
        text(b, "RPM", "cond", h * 0.035, (150, 160, 170), (bar.right + w * 0.015, bar.y), "topleft")

    s.blit(cached_bg("f1", (w, h), bg), (0, 0))
    st = state("f1", (w, h))
    if "grad" not in st:
        st["grad"] = hgradient_surface(bar.w, bar.h, [(0, (0, 200, 90)), (0.7, (255, 210, 0)), (1, (255, 30, 40))])

    leds = shift_colors(15, d.rpm_frac, "f1", now)
    lw = w * 0.90 / 15
    for i, col in enumerate(leds):
        c = (int(w * 0.05 + lw * (i + 0.5)), int(h * 0.075))
        pygame.draw.circle(s, col or (30, 30, 36), c, int(min(lw * 0.36, h * 0.042)))

    text(s, fmt_int(d.speed), "cond", box.h * 0.52, (255, 255, 255), (box.centerx, box.y + box.h * 0.40))
    text(s, d.unit, "cond", h * 0.04, teal, (box.centerx, box.y + box.h * 0.73))
    text(s, fmt_lap(d.cur), "mono", h * 0.065, (255, 255, 255), (box.centerx, box.bottom + h * 0.065))
    text(s, fmt_delta(d.delta), "cond", h * 0.10, delta_color(d.delta), (lt.right - w * 0.02, lt.bottom - h * 0.02), "bottomright")
    text(s, fmt_short(d.last), "cond", h * 0.09, (255, 255, 255), (lb.right - w * 0.02, lb.bottom - h * 0.02), "bottomright")
    text(s, fmt_short(d.best), "cond", h * 0.09, (190, 120, 255), (rt.right - w * 0.02, rt.bottom - h * 0.02), "bottomright")
    lap_txt = f"{d.lap}" + (f"  P{d.position}" if d.position else "")
    text(s, lap_txt, "cond", h * 0.09, (255, 255, 255), (rb.right - w * 0.02, rb.bottom - h * 0.02), "bottomright")

    fw = int(bar.w * clamp(d.rpm / d.rpm_max, 0, 1))
    if fw > 0:
        s.blit(st["grad"], bar.topleft, (0, 0, fw, bar.h))
        for i in range(1, 20):
            x = bar.x + bar.w * i // 20
            if x < bar.x + fw:
                pygame.draw.line(s, (4, 4, 6), (x, bar.y), (x, bar.bottom), 3)
    rx = bar.x + int(bar.w * clamp(d.redline / d.rpm_max, 0, 1))
    pygame.draw.line(s, (255, 255, 255), (rx, bar.y - 4), (rx, bar.bottom + 4), 2)
    text(s, fmt_int(d.rpm), "cond", h * 0.06, (255, 255, 255), (bar.right + w * 0.015, bar.bottom), "bottomleft")


# ---------------------------------------------------------------------------
# 3. ENDURANCE - prototyp LMP
# ---------------------------------------------------------------------------
def draw_endurance(s, d, now, dt):
    w, h = s.get_size()
    orange = (255, 125, 0)
    bar = pygame.Rect(int(w * 0.04), int(h * 0.10), int(w * 0.92), int(h * 0.11))
    tiles_y = int(h * 0.66)
    tw = (w - int(w * 0.08) - 2 * int(w * 0.015)) // 3
    th = int(h * 0.145)

    def bg(b, w, h):
        vgradient(b, (0, 0, w, h), (30, 32, 38), (14, 15, 18))
        pygame.draw.rect(b, (8, 9, 11), bar)
        pygame.draw.rect(b, orange, (0, 0, w, int(h * 0.012)))
        for i in range(6):
            r = pygame.Rect(int(w * 0.04) + (i % 3) * (tw + int(w * 0.015)),
                            tiles_y + (i // 3) * (th + int(h * 0.02)), tw, th)
            pygame.draw.rect(b, (36, 38, 46), r, border_radius=6)
            pygame.draw.rect(b, orange, (r.x, r.bottom - 3, r.w, 3))
        text(b, "LAP", "cond", h * 0.035, (150, 150, 160), (w * 0.96, h * 0.26), "topright")
        pygame.draw.line(b, (60, 62, 70), (w * 0.62, h * 0.27), (w * 0.62, h * 0.60), 2)

    s.blit(cached_bg("endurance", (w, h), bg), (0, 0))
    st = state("endurance", (w, h))
    if "grad" not in st:
        st["grad"] = hgradient_surface(bar.w, bar.h, [(0, (40, 200, 255)), (0.6, (40, 255, 140)),
                                                      (0.85, (255, 220, 0)), (1, (255, 40, 40))])
    fw = int(bar.w * clamp(d.rpm / d.rpm_max, 0, 1))
    if fw > 0:
        s.blit(st["grad"], bar.topleft, (0, 0, fw, bar.h))
    n = max(1, int(round(d.rpm_max / d.rpm_step)))
    for i in range(n + 1):
        x = bar.x + bar.w * i // n
        pygame.draw.line(s, (14, 15, 18), (x, bar.y), (x, bar.bottom), 3)
        if i < n:
            text(s, str(int(round(i * d.rpm_step / 1000))), "cond", h * 0.032, (150, 150, 160),
                 (x + 4, bar.bottom + 2), "topleft")
    rx = bar.x + int(bar.w * clamp(d.redline / d.rpm_max, 0, 1))
    pygame.draw.rect(s, (255, 40, 40), (rx, bar.y - 6, 3, bar.h + 12))
    if d.rpm_frac >= 0.98 and int(now * 8) % 2 == 0:
        pygame.draw.rect(s, (255, 255, 255), bar, 4)

    text(s, fmt_int(d.speed), "cond", h * 0.34, (255, 255, 255), (w * 0.58, h * 0.44), "midright")
    text(s, d.unit, "cond", h * 0.05, orange, (w * 0.58, h * 0.60), "topright")
    text(s, fmt_int(d.rpm), "mono", h * 0.06, (180, 180, 190), (w * 0.04, h * 0.30), "topleft")
    text(s, str(d.lap), "cond", h * 0.16, (255, 255, 255), (w * 0.96, h * 0.30), "topright")
    text(s, fmt_lap(d.cur), "mono", h * 0.075, (255, 255, 255), (w * 0.96, h * 0.60), "bottomright")

    tiles = [("LAST", fmt_lap(d.last), (255, 255, 255)), ("BEST", fmt_lap(d.best), (190, 120, 255)),
             ("DELTA", fmt_delta(d.delta), delta_color(d.delta)),
             ("TOP SPEED", f"{int(d.vmax)}", (255, 255, 255)), ("SESJA", fmt_clock(d.session), (255, 255, 255)),
             ("GAZ" if d.throttle is not None else "POZYCJA",
              f"{int(d.throttle * 100)}%" if d.throttle is not None else (f"P{d.position}" if d.position else "--"),
              (255, 255, 255))]
    for i, (lbl, val, col) in enumerate(tiles):
        r = pygame.Rect(int(w * 0.04) + (i % 3) * (tw + int(w * 0.015)),
                        tiles_y + (i // 3) * (th + int(h * 0.02)), tw, th)
        text(s, lbl, "cond", h * 0.03, (150, 150, 160), (r.x + 8, r.y + 4), "topleft")
        text(s, val, "mono", h * 0.06, col, (r.right - 8, r.bottom - 6), "bottomright")


# ---------------------------------------------------------------------------
# 4. HUD - wyświetlacz przezierny (myśliwiec / sci-fi)
# ---------------------------------------------------------------------------
HUD = (60, 255, 150)
HUD_DIM = (20, 110, 60)


def _tape(s, rect, value, step, label_div, px_per_unit, side):
    s.set_clip(rect)
    cy = rect.centery
    first = int((value - rect.h / 2 / px_per_unit) // step) * step
    v = first
    end = value + rect.h / 2 / px_per_unit + step
    while v <= end:
        y = cy - (v - value) * px_per_unit
        x0, x1 = (rect.right - rect.w * 0.3, rect.right) if side == "left" else (rect.x, rect.x + rect.w * 0.3)
        pygame.draw.line(s, HUD, (x0, y), (x1, y), 2)
        if v >= 0 and int(round(v / step)) % 2 == 0:
            lbl = f"{v / label_div:g}"
            if side == "left":
                text(s, lbl, "mono", rect.h * 0.06, HUD, (x0 - 6, y), "midright")
            else:
                text(s, lbl, "mono", rect.h * 0.06, HUD, (x1 + 6, y), "midleft")
        v += step
    s.set_clip(None)


def draw_hud(s, d, now, dt):
    w, h = s.get_size()
    lt = pygame.Rect(int(w * 0.05), int(h * 0.16), int(w * 0.15), int(h * 0.62))
    rt = pygame.Rect(int(w * 0.80), int(h * 0.16), int(w * 0.15), int(h * 0.62))
    c = (w // 2, int(h * 0.47))
    R = int(h * 0.27)

    def bg(b, w, h):
        b.fill((0, 6, 3))
        for y in range(0, h, 3):
            pygame.draw.line(b, (0, 16, 8), (0, y), (w, y))
        L = int(h * 0.06)
        for (x, y, sx, sy) in ((8, 8, 1, 1), (w - 9, 8, -1, 1), (8, h - 9, 1, -1), (w - 9, h - 9, -1, -1)):
            pygame.draw.line(b, HUD, (x, y), (x + sx * L, y), 2)
            pygame.draw.line(b, HUD, (x, y), (x, y + sy * L), 2)
        pygame.draw.circle(b, HUD_DIM, c, R, 1)
        pygame.draw.circle(b, HUD_DIM, c, int(R * 0.15), 1)
        for a in range(0, 360, 30):
            ra = math.radians(a)
            pygame.draw.line(b, HUD_DIM, (c[0] + math.cos(ra) * R * 0.92, c[1] + math.sin(ra) * R * 0.92),
                             (c[0] + math.cos(ra) * R * 1.05, c[1] + math.sin(ra) * R * 1.05), 2)
        pygame.draw.rect(b, HUD_DIM, lt, 1)
        pygame.draw.rect(b, HUD_DIM, rt, 1)
        text(b, "SPD", "mono", h * 0.035, HUD_DIM, (lt.centerx, lt.y - 4), "midbottom")
        text(b, "RPM x1000", "mono", h * 0.035, HUD_DIM, (rt.centerx, rt.y - 4), "midbottom")

    s.blit(cached_bg("hud", (w, h), bg), (0, 0))
    _tape(s, lt, d.speed, 5, 1, lt.h / 60.0, "left")
    _tape(s, rt, d.rpm, 250, 1000, rt.h / 3000.0, "right")
    for rect, val in ((lt, fmt_int(d.speed)), (rt, f"{d.rpm / 1000:.1f}")):
        box = pygame.Rect(0, 0, rect.w + int(w * 0.02), int(h * 0.09))
        box.center = rect.center
        pygame.draw.rect(s, (0, 6, 3), box)
        pygame.draw.rect(s, HUD, box, 2)
        text(s, val, "mono", h * 0.065, HUD, box.center)

    frac = clamp(d.rpm / d.rpm_max, 0, 1)
    hot = d.rpm_frac >= 0.98
    col = (255, 70, 50) if hot else HUD
    arc_poly(s, col, c, R * 1.08, R * 1.14, 0, frac, 135, 270)
    text(s, fmt_int(d.speed), "mono", R * 0.42, col, (c[0], c[1] - R * 0.05))
    text(s, d.unit, "mono", R * 0.13, HUD_DIM, (c[0], c[1] + R * 0.35))
    if hot and int(now * 6) % 2 == 0:
        text(s, ">> SHIFT <<", "mono", h * 0.06, (255, 70, 50), (c[0], c[1] - R * 0.62))
    text(s, f"DELTA {fmt_delta(d.delta)}", "mono", h * 0.045, delta_color(d.delta, HUD, (255, 70, 50), HUD),
         (w // 2, int(h * 0.06)))
    if int(now * 2) % 2 == 0:
        pygame.draw.circle(s, (255, 60, 50), (int(w * 0.83), int(h * 0.065)), max(3, int(h * 0.012)))
    text(s, "REC", "mono", h * 0.035, HUD, (int(w * 0.85), int(h * 0.065)), "midleft")
    y = int(h * 0.87)
    line = f"LAP {d.lap:02d}   CUR {fmt_lap(d.cur)}   LST {fmt_lap(d.last)}   BST {fmt_lap(d.best)}"
    text(s, line, "mono", min(h * 0.045, w * 0.024), HUD, (w // 2, y))


# ---------------------------------------------------------------------------
# 5. SYNTHWAVE - neonowy zachód słońca, siatka pędzi z prędkością łodzi
# ---------------------------------------------------------------------------
def draw_synthwave(s, d, now, dt):
    w, h = s.get_size()
    hz = int(h * 0.58)
    sun_c = (w // 2, int(hz - h * 0.02))
    sun_r = int(h * 0.24)

    def bg(b, w, h):
        vgradient(b, (0, 0, w, hz), (14, 2, 38), (160, 30, 120))
        sun = pygame.Surface((sun_r * 2, sun_r * 2), pygame.SRCALPHA)
        for y in range(sun_r * 2):
            col = lerp((255, 235, 90), (255, 40, 150), y / (sun_r * 2))
            half = math.sqrt(max(0, sun_r ** 2 - (y - sun_r) ** 2))
            pygame.draw.line(sun, col, (sun_r - half, y), (sun_r + half, y))
        y = sun_r
        gap = 2
        while y < sun_r * 2:
            pygame.draw.rect(sun, (0, 0, 0, 0), (0, y, sun_r * 2, gap))
            y += gap + int(sun_r * 0.12)
            gap += 2
        b.blit(sun, (sun_c[0] - sun_r, sun_c[1] - sun_r))
        rnd = random.Random(7)
        for layer, col in ((0, (60, 12, 90)), (1, (34, 6, 56))):
            pts = [(0, hz)]
            x = 0
            while x < w:
                pts.append((x, hz - rnd.uniform(0.04, 0.16 if layer == 0 else 0.10) * h))
                x += rnd.randint(int(w * 0.04), int(w * 0.10))
            pts += [(w, hz - h * 0.05), (w, hz)]
            pygame.draw.polygon(b, col, pts)
        vgradient(b, (0, hz, w, h - hz), (24, 0, 40), (6, 0, 14))
        pygame.draw.line(b, (255, 120, 220), (0, hz), (w, hz), 2)

    s.blit(cached_bg("synthwave", (w, h), bg), (0, 0))
    st = state("synthwave", (w, h))
    st["phase"] = (st.get("phase", 0.0) + dt * (0.3 + d.speed_frac * 3.5)) % 1.0
    hot = d.rpm_frac >= 0.98
    grid = (0, 230, 255) if hot else (255, 50, 210)
    vp = (w // 2, hz)
    for i in range(-12, 13):
        x_bottom = w / 2 + i * w * 0.12
        pygame.draw.line(s, grid, vp, (x_bottom, h), 2 if abs(i) < 6 else 1)
    for k in range(14):
        z = k + 1 - st["phase"]
        y = hz + (h - hz) * (1.2 / z) ** 1.0 * 0.85
        if hz < y < h:
            pygame.draw.line(s, lerp((40, 0, 60), grid, min(1, (y - hz) / (h - hz) * 1.6)), (0, y), (w, y), 2)
    if d.rpm_frac > 0.6:
        rr = sun_r + int(h * 0.03 * min(1.0, (d.rpm_frac - 0.6) / 0.4))
        pygame.draw.circle(s, (255, 200, 120), sun_c, rr, 2)

    glow_text(s, fmt_int(d.rpm), "cond", h * 0.13, (255, 255, 255), (255, 0, 170), (w * 0.04, h * 0.04), "topleft")
    text(s, "RPM", "cond", h * 0.04, (255, 160, 230), (w * 0.045, h * 0.19), "topleft")
    glow_text(s, fmt_int(d.speed), "cond", h * 0.13, (255, 255, 255), (0, 200, 255), (w * 0.96, h * 0.04), "topright")
    text(s, d.unit, "cond", h * 0.04, (140, 230, 255), (w * 0.955, h * 0.19), "topright")
    box = pygame.Rect(int(w * 0.18), int(h * 0.80), int(w * 0.64), int(h * 0.13))
    pygame.draw.rect(s, (10, 0, 20), box, border_radius=8)
    pygame.draw.rect(s, (255, 50, 210), box, 2, border_radius=8)
    cols = [("LAP", str(d.lap)), ("CUR", fmt_short(d.cur)), ("LAST", fmt_short(d.last)), ("BEST", fmt_short(d.best))]
    for i, (lbl, val) in enumerate(cols):
        x = box.x + box.w * (i + 0.5) / 4
        text(s, lbl, "cond", h * 0.03, (255, 120, 220), (x, box.y + box.h * 0.27))
        text(s, val, "mono", h * 0.05, (255, 255, 255), (x, box.y + box.h * 0.68))


# ---------------------------------------------------------------------------
# 6. ORBITA - obroty i prędkość jako księżyce krążące wokół planety
# ---------------------------------------------------------------------------
def draw_orbit(s, d, now, dt):
    w, h = s.get_size()
    c = (w // 2, h // 2)
    r1, r2, r3 = h * 0.25, h * 0.34, h * 0.44

    def bg(b, w, h):
        b.fill((2, 2, 8))
        rnd = random.Random(3)
        for _ in range(int(w * h / 2500)):
            v = rnd.randint(40, 200)
            b.set_at((rnd.randrange(w), rnd.randrange(h)), (v, v, min(255, v + 30)))
        for r in (r1, r2, r3):
            pygame.draw.circle(b, (30, 34, 60), c, int(r), 1)
        text(b, "LAST", "sans", h * 0.03, (110, 120, 170), (w * 0.03, h * 0.05), "topleft", bold=False)
        text(b, "BEST", "sans", h * 0.03, (110, 120, 170), (w * 0.03, h * 0.20), "topleft", bold=False)
        text(b, "LAP", "sans", h * 0.03, (110, 120, 170), (w * 0.97, h * 0.05), "topright", bold=False)
        text(b, "DELTA", "sans", h * 0.03, (110, 120, 170), (w * 0.97, h * 0.20), "topright", bold=False)

    s.blit(cached_bg("orbit", (w, h), bg), (0, 0))
    st = state("orbit", (w, h))
    st["a1"] = st.get("a1", 0.3) + dt * (0.4 + 7.0 * clamp(d.rpm / d.rpm_max, 0, 1.2))
    st["a2"] = st.get("a2", 2.0) + dt * (0.2 + 4.0 * d.speed_frac)

    heat = rpm_heat(clamp(d.rpm_frac, 0, 1))
    pr = int(h * 0.15)
    for k, mult in ((0.12, 1.45), (0.25, 1.25), (0.5, 1.10)):
        pygame.draw.circle(s, lerp((2, 2, 8), heat, k), c, int(pr * mult))
    pygame.draw.circle(s, heat, c, pr)
    pygame.draw.circle(s, lerp(heat, (255, 255, 255), 0.4), (c[0] - pr // 3, c[1] - pr // 3), pr // 4)

    best = d.best if d.best > 0 else 60.0
    lap_f = clamp(d.cur / best, 0, 1)
    arc_poly(s, (40, 50, 90), c, r3 - 3, r3 + 3, 0, 1, -90, 360)
    arc_poly(s, (200, 210, 255) if lap_f < 1 else (255, 80, 80), c, r3 - 4, r3 + 4, 0, lap_f, -90, 360)

    for ang, r, col, label, size in ((st["a1"], r1, (255, 170, 60), fmt_int(d.rpm), 0.035),
                                     (st["a2"], r2, (90, 200, 255), fmt_int(d.speed), 0.028)):
        trail = 0.9
        f0 = ((math.degrees(ang - trail) + 90) % 360) / 360
        f1 = f0 + trail / (2 * math.pi)
        if f1 <= 1:
            arc_poly(s, lerp((2, 2, 8), col, 0.5), c, r - 2, r + 2, f0, f1, -90, 360)
        else:
            arc_poly(s, lerp((2, 2, 8), col, 0.5), c, r - 2, r + 2, f0, 1, -90, 360)
            arc_poly(s, lerp((2, 2, 8), col, 0.5), c, r - 2, r + 2, 0, f1 - 1, -90, 360)
        p = (c[0] + math.cos(ang) * r, c[1] + math.sin(ang) * r)
        pygame.draw.circle(s, lerp((2, 2, 8), col, 0.4), (int(p[0]), int(p[1])), int(h * size * 1.6))
        pygame.draw.circle(s, col, (int(p[0]), int(p[1])), int(h * size))
        text(s, label, "sans", h * 0.035, col, (p[0], p[1] - h * 0.06))

    text(s, fmt_int(d.speed), "sans", pr * 0.62, (255, 255, 255), (c[0], c[1] - pr * 0.08))
    text(s, d.unit, "sans", pr * 0.20, (255, 255, 255), (c[0], c[1] + pr * 0.42))
    text(s, fmt_lap(d.last), "mono", h * 0.05, (230, 230, 255), (w * 0.03, h * 0.09), "topleft")
    text(s, fmt_lap(d.best), "mono", h * 0.05, (190, 150, 255), (w * 0.03, h * 0.24), "topleft")
    text(s, str(d.lap), "sans", h * 0.08, (230, 230, 255), (w * 0.97, h * 0.085), "topright")
    text(s, fmt_delta(d.delta), "mono", h * 0.05, delta_color(d.delta), (w * 0.97, h * 0.24), "topright")
    text(s, fmt_lap(d.cur), "mono", h * 0.045, (200, 210, 255), (w * 0.97, h * 0.95), "bottomright")


# ---------------------------------------------------------------------------
# 7. LAWA - pulsujący blob, który rośnie i rozgrzewa się z obrotami
# ---------------------------------------------------------------------------
def _blob(c, R, amp, t, n=72, seed=0.0):
    pts = []
    for i in range(n):
        th = i / n * 2 * math.pi
        k = (math.sin(3 * th + t * 1.3 + seed) * 0.5 + math.sin(5 * th - t * 2.1 + seed) * 0.3
             + math.sin(7 * th + t * 3.7) * 0.2)
        r = R * (1 + amp * k)
        pts.append((c[0] + math.cos(th) * r, c[1] + math.sin(th) * r))
    return pts


def draw_lava(s, d, now, dt):
    w, h = s.get_size()
    c = (int(w * 0.40), int(h * 0.50))

    def bg(b, w, h):
        b.fill((6, 2, 8))
        radial_fill(b, c, int(max(w, h) * 0.8), (40, 10, 30), (6, 2, 8), 6)

    s.blit(cached_bg("lava", (w, h), bg), (0, 0))
    st = state("lava", (w, h))
    f = clamp(d.rpm_frac, 0, 1.1)
    st["t"] = st.get("t", 0.0) + dt * (0.6 + 3.5 * f)
    t = st["t"]
    heat = rpm_heat(min(1.0, f))
    R = h * (0.20 + 0.10 * min(1.0, f))
    amp = 0.05 + 0.16 * f
    for scale, k in ((1.30, 0.18), (1.15, 0.40), (1.0, 1.0)):
        pygame.draw.polygon(s, lerp((6, 2, 8), heat, k), _blob(c, R * scale, amp, t))
    pygame.draw.polygon(s, lerp(heat, (255, 255, 230), 0.45), _blob((c[0] - R * 0.15, c[1] - R * 0.2), R * 0.45, amp, t * 1.3, 48, 1.7))

    st["a"] = st.get("a", 0.0) + dt * (0.3 + 2.5 * d.speed_frac)
    sc = (c[0] + math.cos(st["a"]) * R * 1.85, c[1] + math.sin(st["a"]) * R * 1.5)
    sr = h * (0.035 + 0.05 * d.speed_frac)
    cool = lerp((40, 220, 255), (200, 120, 255), d.speed_frac)
    pygame.draw.polygon(s, lerp((6, 2, 8), cool, 0.35), _blob(sc, sr * 1.4, 0.15, t * 1.5, 36, 3.0))
    pygame.draw.polygon(s, cool, _blob(sc, sr, 0.15, t * 1.5, 36, 3.0))

    text(s, fmt_int(d.rpm), "cond", R * 0.55, (255, 255, 255), c)
    text(s, "RPM", "cond", R * 0.16, (255, 255, 255), (c[0], c[1] + R * 0.42))
    x = int(w * 0.97)
    text(s, fmt_int(d.speed), "cond", h * 0.20, cool, (x, h * 0.06), "topright")
    text(s, d.unit, "cond", h * 0.045, cool, (x, h * 0.29), "topright")
    for i, (lbl, val, col) in enumerate((("LAP", str(d.lap), (255, 230, 220)),
                                         ("CUR", fmt_lap(d.cur), (255, 230, 220)),
                                         ("LAST", fmt_lap(d.last), (255, 230, 220)),
                                         ("BEST", fmt_lap(d.best), (255, 200, 120)),
                                         ("DELTA", fmt_delta(d.delta), delta_color(d.delta)))):
        y = h * (0.44 + i * 0.095)
        text(s, lbl, "cond", h * 0.03, (170, 110, 120), (x, y), "bottomright")
        text(s, val, "mono", h * 0.05, col, (x, y + h * 0.005), "topright")


# ---------------------------------------------------------------------------
# 8. MATRIX - deszcz znaków, pada tym szybciej, im szybciej płyniesz
# ---------------------------------------------------------------------------
GLYPHS = "0123456789ABCDEFXZ#$%&*+=<>?@"


def _glyph_cache(cell, palette):
    font = get_font("mono", cell, True)
    return [[font.render(ch, True, col) for ch in GLYPHS] for col in palette]


def draw_matrix(s, d, now, dt):
    w, h = s.get_size()
    s.fill((0, 0, 0))
    st = state("matrix", (w, h))
    cell = max(8, int(h * 0.045))
    cols = w // cell
    rows = h // cell + 1
    if "cols" not in st:
        rnd = random.Random(11)
        st["cols"] = [[rnd.uniform(-rows, rows), rnd.uniform(0.6, 1.4), rnd.randint(6, 18), rnd.randrange(997)]
                      for _ in range(cols)]
        green = [(220, 255, 230), (60, 255, 120), (20, 180, 70), (10, 100, 40), (5, 55, 22)]
        red = [(255, 230, 220), (255, 70, 50), (190, 30, 20), (110, 15, 10), (60, 8, 5)]
        st["g"] = _glyph_cache(cell, green)
        st["r"] = _glyph_cache(cell, red)
    hot = d.rpm_frac >= 0.98
    glyphs = st["r"] if hot else st["g"]
    rate = 4 + d.speed_frac * 34
    ng = len(GLYPHS)
    for ci, col in enumerate(st["cols"]):
        col[0] += dt * rate * col[1]
        if col[0] - col[2] > rows:
            col[0] = -random.uniform(0, rows * 0.5)
            col[3] = random.randrange(997)
        head = int(col[0])
        x = ci * cell
        for k in range(col[2]):
            row = head - k
            if 0 <= row < rows:
                level = 0 if k == 0 else 1 if k < 3 else 2 if k < col[2] * 0.5 else 3 if k < col[2] * 0.8 else 4
                g = (row * 7 + col[3] + (int(now * 3) if k == 0 else 0)) % ng
                s.blit(glyphs[level][g], (x, row * cell))

    box = pygame.Rect(int(w * 0.18), int(h * 0.14), int(w * 0.64), int(h * 0.72))
    pygame.draw.rect(s, (0, 0, 0), box)
    acc = (255, 70, 50) if hot else (60, 255, 120)
    pygame.draw.rect(s, acc, box, 2)
    x = box.x + int(w * 0.03)
    text(s, "root@pi:~/dash$ telemetry --live", "mono", h * 0.032, (20, 180, 70), (x, box.y + h * 0.03), "topleft")
    text(s, f"RPM  {fmt_int(d.rpm):>7}", "mono", h * 0.10, acc, (x, box.y + h * 0.10), "topleft")
    text(s, f"SPD  {fmt_int(d.speed):>7} {d.unit}", "mono", h * 0.065, acc, (x, box.y + h * 0.25), "topleft")
    lines = [f"LAP   {d.lap:02d}    CUR  {fmt_lap(d.cur)}",
             f"LAST  {fmt_lap(d.last)}",
             f"BEST  {fmt_lap(d.best)}",
             f"DELTA {fmt_delta(d.delta)}    VMAX {int(d.vmax)}"]
    for i, ln in enumerate(lines):
        text(s, ln, "mono", h * 0.042, (150, 255, 180) if not hot else (255, 170, 150),
             (x, box.y + h * (0.39 + i * 0.07)), "topleft")
    if int(now * 2) % 2 == 0:
        pygame.draw.rect(s, acc, (x, box.bottom - h * 0.07, int(h * 0.025), int(h * 0.045)))


# ---------------------------------------------------------------------------
# 9. WARP - skok w nadprzestrzeń, gwiazdy rozciągają się z prędkością
# ---------------------------------------------------------------------------
def draw_warp(s, d, now, dt):
    w, h = s.get_size()
    s.fill((0, 0, 4))
    c = (w // 2, h // 2)
    st = state("warp", (w, h))
    if "stars" not in st:
        rnd = random.Random(5)
        st["stars"] = [[rnd.uniform(0, 2 * math.pi), rnd.uniform(0.02, 1.2), rnd.uniform(0.6, 1.4)]
                       for _ in range(220)]
    maxr = math.hypot(w, h) / 2
    v = d.speed_frac
    hot = d.rpm_frac >= 0.98
    streak = 0.02 + v * 0.30
    for star in st["stars"]:
        star[1] += dt * (0.04 + v * 1.8) * star[2] * (0.25 + star[1])
        if star[1] > 1.25:
            star[1] = random.uniform(0.02, 0.12)
            star[0] = random.uniform(0, 2 * math.pi)
        dist = star[1]
        ca, sa = math.cos(star[0]), math.sin(star[0])
        p1 = (c[0] + ca * dist * maxr, c[1] + sa * dist * maxr)
        p0 = (c[0] + ca * dist * (1 - streak) * maxr, c[1] + sa * dist * (1 - streak) * maxr)
        b = min(1.0, dist * 1.4)
        col = lerp((0, 0, 4), (255, 120, 100) if hot else lerp((160, 200, 255), (255, 255, 255), v), b)
        pygame.draw.line(s, col, p0, p1, 1 if dist < 0.5 else 2)

    R = int(h * 0.22)
    pygame.draw.circle(s, (0, 0, 6), c, int(R * 1.06))
    frac = clamp(d.rpm / d.rpm_max, 0, 1)
    arc_poly(s, (20, 30, 60), c, R, R * 1.06, 0, 1, 135, 270)
    arc_poly(s, rpm_heat(clamp(d.rpm_frac, 0, 1)), c, R, R * 1.06, 0, frac, 135, 270)
    text(s, fmt_int(d.speed), "cond", R * 0.62, (255, 255, 255), (c[0], c[1] - R * 0.10))
    text(s, d.unit, "cond", R * 0.15, (150, 190, 255), (c[0], c[1] + R * 0.32))
    text(s, f"{fmt_int(d.rpm)} RPM", "cond", R * 0.15, (150, 190, 255), (c[0], c[1] + R * 0.62))
    y = int(h * 0.93)
    text(s, f"LAP {d.lap}", "cond", h * 0.045, (200, 210, 255), (w * 0.04, y), "midleft")
    text(s, f"{fmt_lap(d.cur)}   BEST {fmt_lap(d.best)}", "mono", h * 0.04, (200, 210, 255), (w * 0.5, y))
    text(s, fmt_delta(d.delta), "mono", h * 0.045, delta_color(d.delta), (w * 0.96, y), "midright")


# ---------------------------------------------------------------------------
# 10. OSCYLOSKOP - obroty i prędkość jako przebiegi na ekranie CRT
# ---------------------------------------------------------------------------
def draw_scope(s, d, now, dt):
    w, h = s.get_size()
    scr = pygame.Rect(int(w * 0.03), int(h * 0.05), int(w * 0.66), int(h * 0.90))
    strip = int(h * 0.075)
    # wykres rysuje się tylko w "plot" - górny i dolny pasek z opisami są zawsze czytelne
    plot = pygame.Rect(scr.x, scr.y + strip, scr.w, scr.h - 2 * strip)
    green = (80, 255, 140)
    ch1, ch2 = (255, 220, 60), (60, 210, 255)
    px = int(w * 0.74)
    lbl_size = min(h * 0.03, w * 0.018)
    val_size = min(h * 0.055, w * 0.032)
    labels = ("CH1  RPM", "CH2  SPEED", "VMAX", "LAP", "LAST", "BEST", "DELTA")
    step_y = 0.13

    def bg(b, w, h):
        b.fill((26, 28, 30))
        pygame.draw.rect(b, (60, 64, 70), scr.inflate(14, 14), border_radius=14)
        pygame.draw.rect(b, (4, 16, 8), scr, border_radius=8)
        b.set_clip(plot)
        radial_fill(b, plot.center, plot.w * 0.6, (8, 30, 14), (4, 16, 8), 6)
        b.set_clip(None)
        for r in (pygame.Rect(scr.x, scr.y, scr.w, strip), pygame.Rect(scr.x, plot.bottom, scr.w, strip)):
            pygame.draw.rect(b, (2, 10, 5), r, border_radius=8)
        b.set_clip(plot)
        for i in range(1, 10):
            x = plot.x + plot.w * i // 10
            pygame.draw.line(b, (16, 60, 30), (x, plot.y), (x, plot.bottom), 1)
        for i in range(1, 8):
            y = plot.y + plot.h * i // 8
            pygame.draw.line(b, (16, 60, 30), (plot.x, y), (plot.right, y), 1)
        pygame.draw.line(b, (30, 100, 50), (plot.x, plot.centery), (plot.right, plot.centery), 1)
        pygame.draw.line(b, (30, 100, 50), (plot.centerx, plot.y), (plot.centerx, plot.bottom), 1)
        for i in range(50):
            x = plot.x + plot.w * i // 50
            pygame.draw.line(b, (30, 100, 50), (x, plot.centery - 4), (x, plot.centery + 4), 1)
        b.set_clip(None)
        pygame.draw.line(b, (30, 100, 50), (plot.x, plot.y), (plot.right, plot.y), 1)
        pygame.draw.line(b, (30, 100, 50), (plot.x, plot.bottom), (plot.right, plot.bottom), 1)
        ty = scr.y + strip // 2
        x = scr.x + 12
        for col, name in ((ch1, "CH1 RPM"), (ch2, "CH2 SPEED")):
            pygame.draw.line(b, col, (x, ty), (x + 22, ty), 3)
            r = text(b, name, "mono", lbl_size, col, (x + 30, ty), "midleft")
            x = r.right + 24
        text(b, "1 s/div   TRIG AUTO   RUN", "mono", lbl_size, green, (scr.x + 12, plot.bottom + strip // 2), "midleft")
        for i, lbl in enumerate(labels):
            text(b, lbl, "mono", lbl_size, (140, 150, 150), (px, int(h * (0.06 + i * step_y))), "topleft")
        pygame.draw.rect(b, ch1, (px - 12, int(h * 0.065), 6, int(lbl_size)))
        pygame.draw.rect(b, ch2, (px - 12, int(h * (0.065 + step_y)), 6, int(lbl_size)))

    s.blit(cached_bg("scope", (w, h), bg), (0, 0))

    def ypos(v):
        return plot.y + plot.h * (1 - clamp(v, 0, 1.0) * 0.92 - 0.04)

    s.set_clip(plot)
    ry = ypos(clamp(d.redline / d.rpm_max, 0, 1))
    for x in range(plot.x, plot.right, 14):
        pygame.draw.line(s, (130, 40, 30), (x, ry), (x + 7, ry), 1)
    for hist, col in ((d.hist_speed, ch2), (d.hist_rpm, ch1)):
        n = len(hist)
        if n > 2:
            step = plot.w / (hist.maxlen - 1)
            x0 = plot.right - 6 - (n - 1) * step
            pts = [(x0 + i * step, ypos(v)) for i, v in enumerate(hist)]
            pygame.draw.lines(s, lerp((4, 16, 8), col, 0.35), False, pts, 5)
            pygame.draw.lines(s, col, False, pts, 2)
            pygame.draw.circle(s, (255, 255, 255), (int(pts[-1][0]), int(pts[-1][1])), 4)
    s.set_clip(None)
    if d.rpm_frac >= 0.98 and int(now * 6) % 2 == 0:
        text(s, "REDLINE", "mono", lbl_size, (255, 80, 60), (scr.right - 12, plot.bottom + strip // 2), "midright")

    vals = [(fmt_int(d.rpm), ch1), (f"{fmt_int(d.speed)} {d.unit}", ch2),
            (f"{int(d.vmax)}", green), (str(d.lap), green), (fmt_lap(d.last), green),
            (fmt_lap(d.best), green), (fmt_delta(d.delta), delta_color(d.delta, green, (255, 80, 60), green))]
    for i, (v, col) in enumerate(vals):
        text(s, v, "mono", val_size, col, (px, int(h * (0.06 + i * step_y) + lbl_size * 1.15)), "topleft")


# ---------------------------------------------------------------------------
LAYOUTS = [
    dict(name="proline", label="PROLINE", draw=draw_proline),
    dict(name="f1", label="F1", draw=draw_f1),
    dict(name="endurance", label="ENDURANCE", draw=draw_endurance),
    dict(name="hud", label="HUD", draw=draw_hud),
    dict(name="synthwave", label="SYNTHWAVE", draw=draw_synthwave),
    dict(name="orbit", label="ORBITA", draw=draw_orbit),
    dict(name="lava", label="LAWA", draw=draw_lava),
    dict(name="matrix", label="MATRIX", draw=draw_matrix),
    dict(name="warp", label="WARP", draw=draw_warp),
    dict(name="scope", label="OSCYLOSKOP", draw=draw_scope),
]
LAYOUT_BY_NAME = {l["name"]: l for l in LAYOUTS}
