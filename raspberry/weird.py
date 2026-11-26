"""
weird.py - kompletnie pojechane ekrany dashboardu (zakładka DZIWNE).

Ten sam interfejs co layouts.py: draw(surf, d, now, dt), d = DashView.
"""
import math
import random

import pygame

from layouts import (cached_bg, clamp, delta_color, fmt_delta, fmt_int, fmt_lap, fmt_short,
                     radial_fill, rpm_heat, state, text, vgradient)
from themes import get_font, lerp


# ---------------------------------------------------------------------------
# 1. OKO - źrenica rozszerza się z obrotami, oko rozgląda się z prędkością
# ---------------------------------------------------------------------------
def _lid_curve(cx, cy, ew, eh, n, top, close):
    """Krzywa powieki (górna/dolna); close 0..1 domyka oko."""
    pts = []
    for i in range(n + 1):
        x = -1 + 2 * i / n
        y = (1 - x * x) ** 0.85 * eh / 2
        y *= (1 - close)
        pts.append((cx + x * ew / 2, cy - y if top else cy + y))
    return pts


def draw_eye(s, d, now, dt):
    w, h = s.get_size()
    cx, cy = w // 2, int(h * 0.50)
    ew, eh = int(w * 0.74), int(h * 0.66)
    skin = (58, 22, 26)

    def bg(b, w, h):
        radial_fill(b, (cx, cy), max(w, h) * 0.75, (95, 40, 42), (18, 6, 8), 6)
        radial_fill(b, (cx, cy), max(ew, eh) * 0.55, (255, 250, 240), (205, 190, 180), 3)

    st = state("eye", (w, h))
    if "veins" not in st:
        rnd = random.Random(42)
        veins = []
        for _ in range(22):
            a = rnd.uniform(0, 2 * math.pi)
            r = 1.0
            pts = []
            ang = a
            while r > 0.35:
                pts.append((cx + math.cos(ang) * ew * 0.5 * r, cy + math.sin(ang) * eh * 0.5 * r))
                r -= rnd.uniform(0.05, 0.09)
                ang += rnd.uniform(-0.18, 0.18)
            veins.append(pts)
        st["veins"] = veins
        st["next_blink"] = now + 2.0
        st["blink_t"] = -1.0
        st["gaze"] = [0.0, 0.0]
        st["phase"] = 0.0

    s.blit(cached_bg("eye", (w, h), bg), (0, 0))
    f = clamp(d.rpm_frac, 0, 1.2)

    # żyłki - im wyższe obroty, tym więcej
    n_veins = int(len(st["veins"]) * clamp((f - 0.3) / 0.7, 0, 1))
    for pts in st["veins"][:n_veins]:
        if len(pts) > 1:
            pygame.draw.lines(s, (200, 40, 40), False, pts, 2)

    # spojrzenie: nerwowe rozglądanie się, szybsze przy większej prędkości
    st["phase"] += dt * (0.4 + 3.5 * d.speed_frac)
    p = st["phase"]
    tx = math.sin(p * 1.3) * 0.6 + math.sin(p * 3.1) * 0.25
    ty = math.sin(p * 0.9 + 1.0) * 0.35
    g = st["gaze"]
    g[0] += (tx - g[0]) * min(1, dt * 6)
    g[1] += (ty - g[1]) * min(1, dt * 6)
    jit = (random.uniform(-1, 1) * h * 0.012, random.uniform(-1, 1) * h * 0.012) if f >= 0.98 else (0, 0)
    ir = int(h * 0.19)
    ic = (int(cx + g[0] * ew * 0.22 + jit[0]), int(cy + g[1] * eh * 0.20 + jit[1]))

    iris = lerp(lerp((40, 120, 220), (60, 190, 90), min(1, f / 0.5)), (220, 120, 20), clamp((f - 0.5) / 0.5, 0, 1))
    pygame.draw.circle(s, lerp(iris, (0, 0, 0), 0.5), ic, ir + 3)
    pygame.draw.circle(s, iris, ic, ir)
    for i in range(36):
        a = i / 36 * 2 * math.pi + 0.1 * math.sin(i * 7)
        c2 = lerp(iris, (255, 255, 220) if i % 2 else (0, 0, 0), 0.35)
        pygame.draw.line(s, c2, (ic[0] + math.cos(a) * ir * 0.3, ic[1] + math.sin(a) * ir * 0.3),
                         (ic[0] + math.cos(a) * ir * 0.95, ic[1] + math.sin(a) * ir * 0.95), 2)
    pupil = int(ir * (0.22 + 0.62 * clamp(f, 0, 1)))
    pygame.draw.circle(s, (5, 5, 8), ic, pupil)
    pygame.draw.circle(s, (255, 255, 255), (ic[0] - ir // 3, ic[1] - ir // 3), max(3, ir // 7))

    # mruganie (przy redline - nerwowe, ciągłe)
    if now >= st["next_blink"]:
        st["blink_t"] = now
        st["next_blink"] = now + (random.uniform(0.4, 0.9) if f >= 0.98 else random.uniform(3.0, 7.0))
    close = 0.0
    if st["blink_t"] >= 0:
        bt = now - st["blink_t"]
        if bt < 0.22:
            close = 1 - abs(bt - 0.11) / 0.11
    top = _lid_curve(cx, cy, ew, eh, 32, True, close)
    bot = _lid_curve(cx, cy, ew, eh, 32, False, close)
    pygame.draw.polygon(s, skin, [(0, 0), (w, 0), (w, cy)] + top[::-1] + [(0, cy)])
    pygame.draw.polygon(s, skin, [(0, h), (w, h), (w, cy)] + bot[::-1] + [(0, cy)])
    pygame.draw.lines(s, (25, 8, 10), False, top, 6)
    pygame.draw.lines(s, (25, 8, 10), False, bot, 4)
    for i in range(1, 32, 3):   # rzęsy
        x0, y0 = top[i]
        pygame.draw.line(s, (15, 5, 6), (x0, y0), (x0 + (x0 - cx) * 0.04, y0 - h * 0.05 * (1 - close)), 3)

    text(s, f"{fmt_int(d.rpm)} OBR/MIN", "cond", h * 0.06, (255, 200, 190), (w // 2, int(h * 0.92)))
    text(s, f"{fmt_int(d.speed)} {d.unit}", "cond", h * 0.06, (255, 200, 190), (w // 2, int(h * 0.07)))
    text(s, f"LAP {d.lap}", "cond", h * 0.04, (220, 150, 140), (w * 0.03, h * 0.05), "topleft")
    text(s, fmt_lap(d.cur), "mono", h * 0.04, (220, 150, 140), (w * 0.97, h * 0.05), "topright")
    if f >= 0.98:
        text(s, "WIDZĘ CIĘ", "cond", h * 0.05, (255, 60, 50), (w * 0.97, h * 0.95), "bottomright")


# ---------------------------------------------------------------------------
# 2. WĄŻ - długość = prędkość, wicie się = obroty, cyfry RPM na ciele
# ---------------------------------------------------------------------------
def draw_snake(s, d, now, dt):
    w, h = s.get_size()

    def bg(b, w, h):
        vgradient(b, (0, 0, w, h), (16, 40, 18), (6, 18, 8))
        rnd = random.Random(9)
        for _ in range(int(w * h / 900)):
            x, y = rnd.randrange(w), rnd.randrange(h)
            pygame.draw.line(b, (22 + rnd.randint(0, 25), 60 + rnd.randint(0, 40), 24), (x, y), (x + rnd.randint(-3, 3), y - rnd.randint(4, 10)), 1)

    s.blit(cached_bg("snake", (w, h), bg), (0, 0))
    st = state("snake", (w, h))
    st["t"] = st.get("t", 0.0) + dt * (0.25 + 1.1 * d.speed_frac)
    st["wig"] = st.get("wig", 0.0) + dt * (2 + 14 * clamp(d.rpm / d.rpm_max, 0, 1))
    t, wig = st["t"], st["wig"]
    f = clamp(d.rpm_frac, 0, 1.2)

    def path(tt):
        return (w * 0.5 + w * 0.40 * math.sin(tt * 1.0), h * 0.52 + h * 0.36 * math.sin(tt * 1.7 + 0.6))

    # wielka prędkość w tle
    text(s, fmt_int(d.speed), "cond", h * 0.42, (30, 70, 32), (w // 2, h // 2))
    n = int(18 + 70 * d.speed_frac)
    step = 0.022
    pts = []
    for k in range(n):
        tt = t - k * step
        x, y = path(tt)
        x2, y2 = path(tt - 0.001)
        dx, dy = x - x2, y - y2
        ln = math.hypot(dx, dy) or 1
        nx, ny = -dy / ln, dx / ln
        amp = h * (0.015 + 0.03 * f) * min(1, k / 6)
        off = math.sin(k * 0.55 - wig) * amp
        pts.append((x + nx * off, y + ny * off, dx / ln, dy / ln))

    body = (210, 40, 30) if f >= 0.98 else lerp((60, 200, 70), (230, 200, 40), clamp(f, 0, 1))
    body2 = lerp(body, (0, 0, 0), 0.45)
    digits = fmt_int(d.rpm).replace(" ", "")
    for k in range(n - 1, -1, -1):
        x, y, _, _ = pts[k]
        r = h * 0.045 * (1 - 0.75 * k / n)
        pygame.draw.circle(s, body2, (int(x), int(y)), int(r + 2))
        pygame.draw.circle(s, body if (k // 3) % 2 == 0 else lerp(body, (255, 255, 200), 0.25), (int(x), int(y)), int(r))
    hx, hy, fx, fy = pts[0]
    hr = h * 0.06
    pygame.draw.ellipse(s, body2, (hx - hr - 2, hy - hr - 2, 2 * hr + 4, 2 * hr + 4))
    pygame.draw.ellipse(s, body, (hx - hr, hy - hr, 2 * hr, 2 * hr))
    px, py = -fy, fx
    for side in (-1, 1):
        ex, ey = hx + fx * hr * 0.35 + px * side * hr * 0.45, hy + fy * hr * 0.35 + py * side * hr * 0.45
        pygame.draw.circle(s, (255, 240, 120), (int(ex), int(ey)), int(hr * 0.28))
        pygame.draw.ellipse(s, (0, 0, 0), (ex - hr * 0.06, ey - hr * 0.2, hr * 0.12, hr * 0.4))
    if f >= 0.98 or int(now * 1.5) % 4 == 0:
        tl = hr * (1.3 + 0.3 * math.sin(now * 30))
        tip = (hx + fx * (hr + tl), hy + fy * (hr + tl))
        base = (hx + fx * hr, hy + fy * hr)
        pygame.draw.line(s, (220, 30, 60), base, tip, 3)
        for side in (-1, 1):
            pygame.draw.line(s, (220, 30, 60), tip,
                             (tip[0] + fx * hr * 0.3 + px * side * hr * 0.25, tip[1] + fy * hr * 0.3 + py * side * hr * 0.25), 3)

    # cyfry RPM wytatuowane na ciele: czytane od ogona do głowy, rysowane na wierzchu
    spacing = max(3, (n - 6) // (len(digits) + 1))
    for i, ch in enumerate(digits[::-1]):
        k = 6 + i * spacing
        if k < n:
            x, y, _, _ = pts[k]
            r = h * 0.045 * (1 - 0.75 * k / n)
            text(s, ch, "cond", max(10, r * 1.5), (15, 15, 5), (x, y))

    text(s, f"DŁUGOŚĆ WĘŻA = {fmt_int(d.speed)} {d.unit}", "cond", h * 0.04, (170, 230, 150), (w * 0.03, h * 0.04), "topleft")
    text(s, f"WICIE SIĘ = {fmt_int(d.rpm)} RPM", "cond", h * 0.04, (170, 230, 150), (w * 0.03, h * 0.10), "topleft")
    text(s, f"LAP {d.lap}  {fmt_short(d.cur)}", "mono", h * 0.04, (170, 230, 150), (w * 0.97, h * 0.04), "topright")
    text(s, fmt_delta(d.delta), "mono", h * 0.04, delta_color(d.delta), (w * 0.97, h * 0.10), "topright")


# ---------------------------------------------------------------------------
# 3. SERCE - tętno = RPM / 50, EKG, "ciśnienie" z prędkości
# ---------------------------------------------------------------------------
def _heart_pts(cx, cy, size, n=60):
    pts = []
    for i in range(n):
        t = i / n * 2 * math.pi
        x = 16 * math.sin(t) ** 3
        y = 13 * math.cos(t) - 5 * math.cos(2 * t) - 2 * math.cos(3 * t) - math.cos(4 * t)
        pts.append((cx + x * size / 17, cy - y * size / 17))
    return pts


def _ecg(ph):
    """Kształt jednego uderzenia EKG dla fazy 0..1."""
    v = 0.0
    v += 0.12 * math.exp(-((ph - 0.12) / 0.03) ** 2)        # P
    v -= 0.15 * math.exp(-((ph - 0.24) / 0.008) ** 2)       # Q
    v += 1.00 * math.exp(-((ph - 0.27) / 0.012) ** 2)       # R
    v -= 0.30 * math.exp(-((ph - 0.30) / 0.012) ** 2)       # S
    v += 0.25 * math.exp(-((ph - 0.50) / 0.05) ** 2)        # T
    return v


def draw_heart(s, d, now, dt):
    w, h = s.get_size()
    ecg = pygame.Rect(int(w * 0.03), int(h * 0.74), int(w * 0.94), int(h * 0.22))

    def bg(b, w, h):
        radial_fill(b, (w // 2, int(h * 0.38)), max(w, h) * 0.7, (60, 6, 14), (8, 0, 3), 6)
        pygame.draw.rect(b, (4, 14, 8), ecg, border_radius=6)
        for x in range(ecg.x, ecg.right, max(6, ecg.h // 8)):
            pygame.draw.line(b, (12, 40, 20), (x, ecg.y), (x, ecg.bottom))
        for y in range(ecg.y, ecg.bottom, max(6, ecg.h // 8)):
            pygame.draw.line(b, (12, 40, 20), (ecg.x, y), (ecg.right, y))

    s.blit(cached_bg("heart", (w, h), bg), (0, 0))
    st = state("heart", (w, h))
    bpm = max(30.0, d.rpm / 50.0)
    st["ph"] = st.get("ph", 0.0) + dt * bpm / 60.0
    ph = st["ph"] % 1.0
    if "ecg" not in st:
        st["ecg"] = [0.0] * 240
        st["acc"] = 0.0
    st["acc"] += dt
    while st["acc"] >= 1 / 60:
        st["acc"] -= 1 / 60
        st["ecg"].pop(0)
        st["ecg"].append(_ecg(ph) + random.uniform(-0.02, 0.02))

    f = clamp(d.rpm_frac, 0, 1.2)
    beat = math.exp(-((ph - 0.27) / 0.06) ** 2) + 0.4 * math.exp(-((ph - 0.42) / 0.06) ** 2)
    size = h * 0.25 * (1 + 0.13 * beat)
    hot = f >= 0.98
    col = (255, 30, 60) if hot and int(now * 8) % 2 == 0 else lerp((150, 10, 30), (240, 20, 40), clamp(f, 0, 1))
    c = (w // 2, int(h * 0.38))
    for k, mult in ((0.18, 1.25), (0.4, 1.12)):
        pygame.draw.polygon(s, lerp((8, 0, 3), col, k), _heart_pts(c[0], c[1], size * mult))
    pygame.draw.polygon(s, col, _heart_pts(c[0], c[1], size))
    pygame.draw.polygon(s, lerp(col, (255, 220, 220), 0.35), _heart_pts(c[0] - size * 0.35, c[1] - size * 0.3, size * 0.22, 30))

    text(s, f"{int(bpm)}", "cond", size * 0.55, (255, 240, 240), (c[0], c[1] - size * 0.08))
    text(s, "BPM", "cond", size * 0.16, (255, 210, 210), (c[0], c[1] + size * 0.32))

    pts = [(ecg.x + ecg.w * i / (len(st["ecg"]) - 1), ecg.centery + ecg.h * 0.15 - v * ecg.h * 0.62)
           for i, v in enumerate(st["ecg"])]
    trace = (255, 80, 80) if hot else (60, 255, 120)
    pygame.draw.lines(s, lerp((4, 14, 8), trace, 0.35), False, pts, 5)
    pygame.draw.lines(s, trace, False, pts, 2)

    sysp = int(d.speed)
    text(s, f"CIŚNIENIE {sysp}/{int(sysp * 0.64)}", "cond", h * 0.05, (255, 200, 200), (w * 0.03, h * 0.04), "topleft")
    text(s, f"= {fmt_int(d.rpm)} RPM", "cond", h * 0.04, (220, 150, 150), (w * 0.03, h * 0.11), "topleft")
    text(s, f"OKRĄŻENIE {d.lap}", "cond", h * 0.045, (255, 200, 200), (w * 0.97, h * 0.04), "topright")
    text(s, fmt_lap(d.cur), "mono", h * 0.045, (255, 200, 200), (w * 0.97, h * 0.11), "topright")
    text(s, f"OSTATNIE {fmt_short(d.last)}   NAJLEPSZE {fmt_short(d.best)}", "cond", h * 0.035,
         (220, 150, 150), (w * 0.03, h * 0.705), "midleft")
    if hot:
        text(s, "TACHYKARDIA!", "cond", h * 0.06, (255, 255, 255), (w * 0.97, h * 0.705), "midright")


# ---------------------------------------------------------------------------
# 4. ZEGAR DALEGO - tarcza topnieje tym bardziej, im wyższe obroty
# ---------------------------------------------------------------------------
_rot_cache = {}


def _rotated_text(s, txt, family, size, color, angle):
    from themes import get_font
    a = int(round(angle / 3.0)) * 3
    key = (txt, family, int(size), color, a)
    img = _rot_cache.get(key)
    if img is None:
        if len(_rot_cache) > 800:
            _rot_cache.clear()
        img = pygame.transform.rotate(get_font(family, size).render(txt, True, color), a)
        _rot_cache[key] = img
    return img


def draw_dali(s, d, now, dt):
    w, h = s.get_size()
    hz = int(h * 0.62)

    def bg(b, w, h):
        vgradient(b, (0, 0, w, hz), (70, 110, 160), (235, 190, 120))
        vgradient(b, (0, hz, w, h - hz), (190, 140, 80), (110, 70, 40))
        pygame.draw.circle(b, (255, 235, 180), (int(w * 0.90), int(h * 0.52)), int(h * 0.07))
        # martwe drzewo
        tx = int(w * 0.10)
        pygame.draw.line(b, (50, 35, 25), (tx, h), (tx, int(h * 0.30)), max(4, w // 120))
        pygame.draw.line(b, (50, 35, 25), (tx, int(h * 0.34)), (int(w * 0.30), int(h * 0.22)), max(3, w // 160))
        pygame.draw.line(b, (50, 35, 25), (tx, int(h * 0.45)), (int(w * 0.02), int(h * 0.36)), max(2, w // 200))
        # półka / blok, na którym topnieje zegar
        pygame.draw.polygon(b, (90, 60, 40), [(w * 0.30, h * 0.80), (w * 0.86, h * 0.80), (w * 0.92, h * 0.90), (w * 0.24, h * 0.90)])
        pygame.draw.rect(b, (70, 45, 30), (w * 0.24, h * 0.90, w * 0.68, h * 0.06))

    s.blit(cached_bg("dali", (w, h), bg), (0, 0))
    f = clamp(d.rpm_frac, 0, 1.2)
    melt = 0.06 + 0.75 * clamp(f, 0, 1.1) + 0.04 * math.sin(now * 0.8)
    cx, cy, R = int(w * 0.56), int(h * 0.42), int(h * 0.30)

    def drip(x_rel):
        """Ile punkt (wzgl. środka) spływa w dół."""
        return melt * R * (0.55 + 0.35 * math.sin(x_rel * 3.1 + 0.7) + 0.25 * math.sin(x_rel * 7.3 + now * 0.5))

    def warp(px, py):
        xr = (px - cx) / R
        yr = (py - cy) / R
        down = drip(xr) * max(0.0, yr + 0.3) ** 1.6
        return (px + xr * melt * R * 0.08, py + down)

    pts = []
    for i in range(72):
        a = i / 72 * 2 * math.pi
        pts.append(warp(cx + math.cos(a) * R, cy + math.sin(a) * R))
    pygame.draw.polygon(s, (60, 45, 30), [(x + 6, y + 8) for x, y in pts])
    pygame.draw.polygon(s, (200, 170, 70), pts)
    inner = [warp(cx + math.cos(i / 72 * 2 * math.pi) * R * 0.9, cy + math.sin(i / 72 * 2 * math.pi) * R * 0.9) for i in range(72)]
    pygame.draw.polygon(s, (245, 235, 205), inner)
    # krople
    for k, xr in enumerate((-0.55, 0.05, 0.6)):
        x, y = warp(cx + xr * R, cy + R * 0.9)
        L = melt * R * (0.35 + 0.2 * k) * (0.8 + 0.2 * math.sin(now * 1.3 + k))
        pygame.draw.ellipse(s, (245, 235, 205), (x - R * 0.06, y - R * 0.05, R * 0.12, L))

    n = max(1, int(round(d.rpm_max / d.rpm_step)))
    for i in range(n + 1):
        a = math.radians(135 + i / n * 270)
        x, y = warp(cx + math.cos(a) * R * 0.74, cy + math.sin(a) * R * 0.74)
        tilt = -((x - cx) / R) * melt * 40
        img = _rotated_text(s, str(int(round(i * d.rpm_step / 1000))), "serif", R * 0.15, (40, 30, 20), tilt)
        s.blit(img, img.get_rect(center=(x, y)))

    def hand(frac, length, width, col):
        a = math.radians(135 + clamp(frac, 0, 1) * 270)
        seg = []
        for k in range(9):
            r = length * k / 8
            seg.append(warp(cx + math.cos(a) * r, cy + math.sin(a) * r))
        pygame.draw.lines(s, col, False, seg, width)

    hand(d.speed / d.speed_max if d.speed_max else 0, R * 0.55, max(4, R // 18), (60, 40, 30))
    hand(d.rpm / d.rpm_max if d.rpm_max else 0, R * 0.80, max(2, R // 40), (150, 30, 20))
    pygame.draw.circle(s, (60, 40, 30), (cx, cy), max(4, R // 18))

    text(s, "CZAS JEST PŁYNNY", "serif", h * 0.045, (60, 40, 30), (w * 0.03, h * 0.04), "topleft")
    text(s, f"{fmt_int(d.rpm)} obr.   {fmt_int(d.speed)} {d.unit}", "serif", h * 0.04, (60, 40, 30), (w * 0.03, h * 0.11), "topleft")
    img = _rotated_text(s, fmt_lap(d.cur), "serif", h * 0.05, (40, 30, 20), -melt * 12)
    s.blit(img, img.get_rect(topright=(int(w * 0.97), int(h * 0.04 + melt * h * 0.04))))
    text(s, f"najlepsze {fmt_lap(d.best)}", "serif", h * 0.035, (60, 40, 30), (w * 0.97, h * 0.16), "topright")


# ---------------------------------------------------------------------------
# 5. GLITCH - uszkodzony wyświetlacz, im wyższe obroty, tym gorzej
# ---------------------------------------------------------------------------
def draw_glitch(s, d, now, dt):
    w, h = s.get_size()
    st = state("glitch", (w, h))
    if "frame" not in st:
        st["frame"] = pygame.Surface((w, h))
        st["hex"] = random.Random(5)
    frame = st["frame"]
    f = clamp(d.rpm_frac, 0, 1.2)
    hot = f >= 0.98
    level = clamp((f - 0.3) / 0.7, 0, 1) ** 1.5
    if hot:
        level = 1.0

    # śmieci w tle - nowe 2 razy na sekundę (renderowane raz, potem tylko kopiowane)
    jkey = int(now * 2)
    if st.get("jkey") != jkey:
        st["jkey"] = jkey
        junk = pygame.Surface((w, h))
        junk.fill((8, 4, 14))
        jr = random.Random(jkey)
        for i in range(int(1 / 0.045) + 1):
            line = " ".join(f"{jr.randrange(65536):04X}" for _ in range(10))
            junk.blit(get_font("mono", h * 0.03).render(line, True, (40, 30, 70)), (w * 0.02, i * h * 0.045))
        st["junk"] = junk
    if hot and int(now * 10) % 3 == 0:
        frame.fill((230, 230, 240))
    else:
        frame.blit(st["junk"], (0, 0))
    rnd = random.Random(int(now * 12))

    sh = int(h * 0.012 + level * h * 0.02)
    for txt, size, y in ((fmt_int(d.rpm), 0.30, 0.30), (f"{fmt_int(d.speed)} {d.unit}", 0.13, 0.60)):
        for col, dx in (((255, 0, 80), -sh), ((0, 230, 255), sh)):
            text(frame, txt, "cond", h * size, col, (w // 2 + dx, h * y))
        text(frame, txt, "cond", h * size, (255, 255, 255), (w // 2, h * y))
    text(frame, f"LAP {d.lap:02d}  {fmt_lap(d.cur)}   BEST {fmt_lap(d.best)}", "mono", h * 0.045,
         (0, 255, 160), (w // 2, h * 0.80))
    text(frame, f"DELTA {fmt_delta(d.delta)}", "mono", h * 0.04, delta_color(d.delta), (w // 2, h * 0.88))
    if hot:
        text(frame, "FATAL ERROR 0xDEADBEEF", "mono", h * 0.06, (255, 30, 60), (w // 2, h * 0.08))
        text(frame, "REDLINE_EXCEPTION: engine.exe przestał odpowiadać", "mono", h * 0.03, (255, 120, 140), (w // 2, h * 0.15))
    else:
        text(frame, "SYS OK" if level < 0.3 else "SIGNAL UNSTABLE", "mono", h * 0.04,
             (0, 255, 160) if level < 0.3 else (255, 200, 0), (w // 2, h * 0.08))

    # porwane paski: kopiowanie klatki na ekran z przesunięciami
    s.fill((0, 0, 0))
    strips = 18
    sh_h = h // strips + 1
    for i in range(strips):
        off = 0
        if rnd.random() < 0.15 + 0.6 * level:
            off = int(rnd.uniform(-1, 1) * w * (0.01 + 0.12 * level))
        s.blit(frame, (off, i * sh_h), (0, i * sh_h, w, sh_h))
    # bloki zakłóceń
    for _ in range(int(3 + 25 * level)):
        bw, bh = rnd.randint(8, int(w * 0.15)), rnd.randint(2, int(h * 0.04))
        col = rnd.choice([(255, 0, 80), (0, 230, 255), (255, 255, 255), (0, 0, 0), (255, 220, 0)])
        pygame.draw.rect(s, col, (rnd.randrange(w), rnd.randrange(h), bw, bh))
    for y in range(0, h, 3):
        pygame.draw.line(s, (0, 0, 0), (0, y), (w, y))


WEIRD = [
    dict(name="eye", label="OKO", draw=draw_eye),
    dict(name="snake", label="WĄŻ", draw=draw_snake),
    dict(name="heart", label="SERCE", draw=draw_heart),
    dict(name="dali", label="ZEGAR DALEGO", draw=draw_dali),
    dict(name="glitch", label="GLITCH", draw=draw_glitch),
]
WEIRD_BY_NAME = {x["name"]: x for x in WEIRD}
