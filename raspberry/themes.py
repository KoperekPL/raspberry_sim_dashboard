"""
themes.py - wymienne tarcze zegarów dla launcher.py.

Każda tarcza to słownik parametrów nadpisujących BASE. Statyczna część zegara
(tarcza, obręcz, podziałka, liczby) jest renderowana raz i trzymana w cache,
więc nawet "ciężkie" tarcze (chrom, carbon, gradienty) nie obciążają RPi.

Własną tarczę dodajesz, dopisując słownik do listy THEMES (patrz przykłady niżej).
"""
import math
import os

import pygame

START_DEG = 135.0
SWEEP_DEG = 270.0

# Rodziny czcionek: najpierw konkretne pliki (szybko, bez szukania), potem nazwy systemowe.
_DJ = "/usr/share/fonts/truetype/dejavu/"
FONT_FILES = {
    ("sans", True): [_DJ + "DejaVuSans-Bold.ttf"], ("sans", False): [_DJ + "DejaVuSans.ttf"],
    ("serif", True): [_DJ + "DejaVuSerif-Bold.ttf"], ("serif", False): [_DJ + "DejaVuSerif.ttf"],
    ("mono", True): [_DJ + "DejaVuSansMono-Bold.ttf"], ("mono", False): [_DJ + "DejaVuSansMono.ttf"],
    ("cond", True): [_DJ + "DejaVuSansCondensed-Bold.ttf", _DJ + "DejaVuSans-Bold.ttf"],
    ("cond", False): [_DJ + "DejaVuSansCondensed.ttf", _DJ + "DejaVuSans.ttf"],
    ("seg", True): ["/usr/share/fonts/truetype/dseg/DSEG7Classic-Bold.ttf", _DJ + "DejaVuSansMono-Bold.ttf"],
    ("seg", False): ["/usr/share/fonts/truetype/dseg/DSEG7Classic-Regular.ttf", _DJ + "DejaVuSansMono.ttf"],
}
FONT_FAMILIES = {"sans": "dejavusans", "serif": "dejavuserif", "mono": "dejavusansmono",
                 "cond": "dejavusanscondensed", "seg": "dseg7classic"}

# --------------------------------------------------------------------------
# Parametry domyślne (= tarcza "NOWOCZESNA")
# --------------------------------------------------------------------------
BASE = dict(
    name="modern", label="NOWOCZESNA",
    bg=(12, 15, 20),
    # pasek czasów okrążeń
    bar_label=(135, 150, 170), bar_text=(235, 240, 248), bar_best=(80, 225, 120),
    bar_divider=(38, 46, 60), bar_font="mono",
    # tarcza: flat | radial | carbon | none
    face_style="flat", face=(22, 27, 36), face2=None,
    # obręcz: none | ring | chrome | brass | glow
    bezel="ring", bezel_color=(70, 82, 100), bezel_width=0.025,
    # podziałka: line | dot | none
    ticks="line", tick_color=(235, 240, 248), tick_minor_color=None,
    tick_major=(0.76, 0.90), tick_minor=(0.83, 0.90), tick_width=(3, 2), sub_divs=2,
    # liczby: all | ends | none
    num_mode="all", num_font="sans", num_color=None, num_radius=0.62, num_size=0.09, num_bold=True,
    # czerwone pole: band | line | glow | none
    redzone="band", red_color=(225, 45, 45), red_radius=(0.80, 0.90),
    # wskazówka: line | taper | thin | glow | none
    needle="line", needle_rpm=(255, 65, 54), needle_speed=(45, 175, 255),
    needle_len=0.82, needle_tail=0.16, needle_width=0.032,
    # środek wskazówki: flat | chrome | brass | none
    hub="flat", hub_color=(200, 210, 225), hub_inner=(12, 15, 20),
    # łuk zamiast wskazówki: None | progress | segments
    arc=None, arc_bg=(40, 44, 52), arc_radius=(0.80, 0.92), arc_segments=36,
    seg_low=(0, 230, 120), seg_mid=(255, 200, 0), seg_high=(255, 40, 40),
    # odczyt cyfrowy
    value_font="sans", value_color=(235, 240, 248), value_size=0.205, value_pos=0.47, value_bold=True,
    value_box=None, value_box_border=None,
    # jednostka (unit_pos=None -> nie rysuj) i dodatkowy napis
    unit_font="sans", unit_color=(135, 150, 170), unit_size=0.085, unit_pos=0.68,
    caption=None, caption_color=None, caption_font="sans", caption_size=0.07, caption_pos=-0.30,
    glow=False,
)

THEMES_OVERRIDES = [
    dict(name="modern", label="NOWOCZESNA"),

    dict(name="vintage", label="VINTAGE",
         bg=(30, 24, 18),
         bar_label=(170, 150, 115), bar_text=(240, 228, 200), bar_best=(220, 180, 90),
         bar_divider=(70, 58, 42), bar_font="serif",
         face_style="radial", face=(250, 243, 222), face2=(205, 188, 148),
         bezel="chrome", bezel_width=0.07,
         tick_color=(35, 28, 22), tick_major=(0.79, 0.90), tick_minor=(0.85, 0.90),
         tick_width=(3, 1), sub_divs=5,
         num_font="serif", num_radius=0.66, num_size=0.10,
         redzone="line", red_color=(175, 30, 25), red_radius=(0.91, 0.95),
         needle="thin", needle_rpm=(190, 35, 20), needle_speed=(190, 35, 20),
         needle_len=0.86, needle_tail=0.22, needle_width=0.03,
         hub="chrome",
         value_font="mono", value_color=(245, 235, 205), value_size=0.12, value_pos=0.47,
         value_box=(28, 24, 20), value_box_border=(120, 105, 80),
         unit_pos=None,
         caption={"rpm": "x1000 r/min", "speed": "{unit}"}, caption_color=(70, 55, 40),
         caption_font="serif", caption_size=0.075, caption_pos=-0.32),

    dict(name="classic", label="KLASYCZNA",
         bg=(10, 10, 12),
         bar_label=(150, 150, 150), bar_text=(240, 240, 240), bar_best=(255, 140, 30),
         bar_divider=(45, 45, 48), bar_font="sans",
         face=(14, 14, 16),
         bezel="chrome", bezel_width=0.06,
         tick_color=(245, 245, 245), tick_minor_color=(160, 160, 160), sub_divs=4,
         tick_major=(0.77, 0.91), tick_minor=(0.85, 0.91), tick_width=(4, 2),
         num_radius=0.63, num_size=0.10,
         red_color=(220, 30, 30), red_radius=(0.84, 0.91),
         needle="taper", needle_rpm=(255, 110, 0), needle_speed=(255, 110, 0),
         needle_len=0.86, needle_tail=0.20, needle_width=0.035,
         hub="chrome",
         value_color=(240, 240, 240), value_size=0.15, value_pos=0.50,
         unit_color=(150, 150, 150), unit_pos=0.70,
         caption={"rpm": "x1000 1/min", "speed": ""}, caption_color=(150, 150, 150)),

    dict(name="sport", label="SPORT",
         bg=(18, 18, 20),
         bar_label=(150, 150, 155), bar_text=(245, 245, 245), bar_best=(255, 210, 0),
         bar_divider=(50, 50, 55), bar_font="sans",
         face_style="radial", face=(252, 252, 252), face2=(200, 200, 206),
         bezel="ring", bezel_color=(25, 25, 28), bezel_width=0.065,
         tick_color=(15, 15, 15), tick_major=(0.74, 0.90), tick_minor=(0.83, 0.90),
         tick_width=(6, 2),
         num_radius=0.59, num_size=0.105,
         red_color=(225, 25, 25), red_radius=(0.84, 0.92),
         needle="taper", needle_rpm=(225, 20, 20), needle_speed=(225, 20, 20),
         needle_len=0.88, needle_width=0.04,
         hub="flat", hub_color=(20, 20, 22), hub_inner=(225, 20, 20),
         value_color=(15, 15, 15), value_size=0.18, value_pos=0.48,
         unit_color=(90, 90, 95)),

    dict(name="marine", label="MARINE",
         bg=(8, 14, 28),
         bar_label=(150, 170, 200), bar_text=(240, 242, 248), bar_best=(225, 185, 90),
         bar_divider=(35, 55, 90), bar_font="serif",
         face_style="radial", face=(36, 68, 120), face2=(10, 22, 50),
         bezel="brass", bezel_width=0.08,
         tick_color=(242, 242, 248), tick_minor_color=(165, 185, 215), sub_divs=5,
         tick_major=(0.78, 0.91), tick_minor=(0.85, 0.91), tick_width=(3, 1),
         num_font="serif", num_radius=0.65, num_size=0.10,
         red_color=(215, 55, 50), red_radius=(0.86, 0.91),
         needle="taper", needle_rpm=(250, 250, 250), needle_speed=(250, 250, 250),
         needle_len=0.86, needle_width=0.03,
         hub="brass",
         value_font="mono", value_color=(242, 242, 248), value_size=0.12, value_pos=0.47,
         value_box=(6, 12, 26), value_box_border=(190, 150, 70),
         unit_pos=None,
         caption={"rpm": "RPM x1000", "speed": "{unit}"}, caption_color=(200, 170, 100),
         caption_font="serif", caption_pos=-0.32),

    dict(name="neon", label="RETRO NEON",
         bg=(8, 3, 16), glow=True,
         bar_label=(0, 170, 200), bar_text=(255, 120, 240), bar_best=(0, 240, 255),
         bar_divider=(70, 20, 90), bar_font="mono",
         face=(16, 6, 28),
         bezel="glow", bezel_color=(255, 40, 210), bezel_width=0.02,
         tick_color=(0, 230, 255), tick_minor_color=(0, 110, 150),
         tick_width=(3, 2),
         num_font="mono", num_size=0.085,
         redzone="glow", red_color=(255, 40, 120), red_radius=(0.84, 0.88),
         needle="glow", needle_rpm=(255, 60, 220), needle_speed=(0, 240, 255),
         needle_width=0.03,
         hub="flat", hub_color=(255, 60, 220), hub_inner=(16, 6, 28),
         value_font="mono", value_color=(255, 255, 255), value_size=0.19,
         unit_font="mono", unit_color=(0, 230, 255)),

    dict(name="carbon", label="CARBON",
         bg=(8, 8, 9),
         bar_label=(160, 160, 165), bar_text=(245, 245, 245), bar_best=(230, 30, 30),
         bar_divider=(60, 20, 20), bar_font="sans",
         face_style="carbon",
         bezel="ring", bezel_color=(205, 25, 25), bezel_width=0.022,
         tick_color=(245, 245, 245), tick_minor_color=(150, 150, 155), tick_width=(4, 2),
         red_color=(225, 25, 25),
         needle="line", needle_rpm=(235, 30, 30), needle_speed=(235, 30, 30),
         hub="flat", hub_color=(30, 30, 33), hub_inner=(225, 25, 25),
         unit_color=(170, 170, 175)),

    dict(name="digital", label="CYFROWA",
         bg=(4, 6, 8),
         bar_label=(70, 110, 100), bar_text=(0, 255, 140), bar_best=(0, 200, 255),
         bar_divider=(20, 40, 35), bar_font="mono",
         face=(10, 13, 16),
         bezel="ring", bezel_color=(30, 38, 46), bezel_width=0.015,
         ticks="none",
         num_font="mono", num_color=(90, 115, 125), num_radius=0.66, num_size=0.075,
         redzone="none",
         needle="none", needle_rpm=(0, 255, 140), needle_speed=(0, 200, 255),
         hub="none",
         arc="segments", arc_bg=(24, 32, 38), arc_radius=(0.79, 0.95), arc_segments=40,
         value_font="mono", value_color=None, value_size=0.24, value_pos=0.02,
         unit_font="mono", unit_color=(90, 115, 125), unit_pos=0.26),

    dict(name="minimal", label="MINIMAL",
         bg=(5, 5, 7),
         bar_label=(110, 110, 115), bar_text=(250, 250, 250), bar_best=(120, 200, 255),
         bar_divider=(30, 30, 34), bar_font="sans",
         face_style="none", bezel="none", ticks="none",
         num_mode="ends", num_color=(110, 110, 115), num_radius=0.70, num_size=0.075, num_bold=False,
         redzone="none", red_color=(255, 60, 50),
         needle="none", needle_rpm=(250, 250, 250), needle_speed=(120, 200, 255),
         hub="none",
         arc="progress", arc_bg=(32, 32, 36), arc_radius=(0.86, 0.94),
         value_size=0.30, value_pos=0.02, value_bold=False,
         unit_color=(110, 110, 115), unit_pos=0.30),

    dict(name="night", label="NOCNA",
         bg=(0, 0, 0), glow=True,
         bar_label=(140, 30, 20), bar_text=(255, 60, 35), bar_best=(255, 150, 90),
         bar_divider=(50, 8, 5), bar_font="mono",
         face=(10, 2, 2),
         bezel="ring", bezel_color=(70, 12, 8), bezel_width=0.02,
         tick_color=(255, 55, 30), tick_minor_color=(140, 25, 15),
         num_color=(255, 60, 35),
         redzone="line", red_color=(255, 170, 120), red_radius=(0.91, 0.94),
         needle="glow", needle_rpm=(255, 45, 20), needle_speed=(255, 45, 20), needle_width=0.028,
         hub="flat", hub_color=(120, 20, 10), hub_inner=(10, 2, 2),
         value_color=(255, 60, 35), unit_color=(140, 30, 20)),
]

THEMES = [dict(BASE, **o) for o in THEMES_OVERRIDES]
THEME_BY_NAME = {t["name"]: t for t in THEMES}
DEFAULT_THEME = "modern"


def get_theme(name):
    return THEME_BY_NAME.get(name, THEME_BY_NAME[DEFAULT_THEME])


# --------------------------------------------------------------------------
# Pomocnicze
# --------------------------------------------------------------------------
_font_cache = {}
_font_path_cache = {}


def _font_path(family, bold):
    key = (family, bold)
    if key not in _font_path_cache:
        path = None
        for cand in FONT_FILES.get(key, []):
            if os.path.isfile(cand):
                path = cand
                break
        if path is None:
            try:
                path = pygame.font.match_font(FONT_FAMILIES.get(family, family), bold=bold)
            except Exception:
                path = None
        _font_path_cache[key] = path
    return _font_path_cache[key]


def get_font(family, size, bold=True):
    """Czcionka z cache. Rozmiary są zaokrąglane, żeby nie ładować pliku dla każdego piksela."""
    size = max(8, int(size))
    if size > 20:
        size -= size % 2
    if size > 60:
        size -= size % 4
    key = (family, size, bold)
    f = _font_cache.get(key)
    if f is None:
        f = pygame.font.Font(_font_path(family, bold), size)
        _font_cache[key] = f
    return f


def finalize(surf, alpha=True):
    """Konwersja do formatu ekranu - wielokrotnie szybsze blitowanie (ważne na RPi)."""
    if pygame.display.get_init() and pygame.display.get_surface() is not None:
        try:
            return surf.convert_alpha() if alpha else surf.convert()
        except pygame.error:
            pass
    return surf


def lerp(a, b, t):
    t = 0.0 if t < 0 else 1.0 if t > 1 else t
    return (int(a[0] + (b[0] - a[0]) * t), int(a[1] + (b[1] - a[1]) * t), int(a[2] + (b[2] - a[2]) * t))


def _px(v, radius, minimum=1):
    """Grubość w pikselach przeskalowana do rozmiaru zegara (wartości w stylu podane dla r=190)."""
    return max(minimum, int(round(v * radius / 190.0)))


def _ang(frac):
    return math.radians(START_DEG + frac * SWEEP_DEG)


def arc_poly(surf, color, c, r_in, r_out, f0, f1, start=START_DEG, sweep=SWEEP_DEG):
    """Wycinek pierścienia od ułamka f0 do f1 łuku (start/sweep w stopniach, oś Y w dół)."""
    if f1 <= f0:
        return
    steps = max(2, int(48 * (f1 - f0) * abs(sweep) / 270.0) + 2)

    def _ang(f):
        return math.radians(start + f * sweep)

    pts = []
    for i in range(steps + 1):
        a = _ang(f0 + (f1 - f0) * i / steps)
        pts.append((c[0] + math.cos(a) * r_out, c[1] + math.sin(a) * r_out))
    for i in range(steps, -1, -1):
        a = _ang(f0 + (f1 - f0) * i / steps)
        pts.append((c[0] + math.cos(a) * r_in, c[1] + math.sin(a) * r_in))
    pygame.draw.polygon(surf, color, pts)


def glow_line(surf, color, bg, p1, p2, width):
    for mult, k in ((4.0, 0.12), (2.6, 0.30), (1.7, 0.60)):
        pygame.draw.line(surf, lerp(bg, color, k), p1, p2, max(1, int(width * mult)))
    pygame.draw.line(surf, lerp(color, (255, 255, 255), 0.35), p1, p2, max(1, int(width)))


def _masked(surf, pattern, c, r_out, r_in=0):
    mask = pygame.Surface(pattern.get_size(), pygame.SRCALPHA)
    pygame.draw.circle(mask, (255, 255, 255, 255), c, int(r_out))
    if r_in > 0:
        pygame.draw.circle(mask, (0, 0, 0, 0), c, int(r_in))
    pattern.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
    surf.blit(pattern, (0, 0))


def _metal_ring(surf, c, r_out, r_in, light, dark):
    size = surf.get_size()

    def gradient(top_col, bot_col):
        g = pygame.Surface(size, pygame.SRCALPHA)
        top = c[1] - r_out
        h = max(1, 2 * r_out)
        for y in range(size[1]):
            t = (y - top) / h
            # jasny refleks u góry, ciemno na dole, lekkie odbicie na samym dole
            k = t * 1.25 if t < 0.8 else 1.0 - (t - 0.8) * 1.5
            pygame.draw.line(g, (*lerp(top_col, bot_col, k), 255), (0, y), (size[0], y))
        return g

    _masked(surf, gradient(light, dark), c, r_out, r_in)
    w = r_out - r_in
    _masked(surf, gradient(dark, light), c, r_in + w * 0.30, r_in)   # wewnętrzna faza
    pygame.draw.circle(surf, lerp(dark, (0, 0, 0), 0.5), c, int(r_in), max(1, int(w * 0.08)))


METALS = {
    "chrome": ((250, 250, 255), (85, 90, 100)),
    "brass": ((250, 220, 140), (110, 75, 25)),
}


def _carbon(surf, c, r):
    size = surf.get_size()
    pat = pygame.Surface(size, pygame.SRCALPHA)
    cell = max(3, int(r * 0.045))
    for gy in range(0, size[1], cell):
        for gx in range(0, size[0], cell):
            odd = ((gx // cell) + (gy // cell)) % 2
            if odd:
                pygame.draw.rect(pat, (27, 27, 31, 255), (gx, gy, cell, cell))
                pygame.draw.rect(pat, (44, 44, 50, 255), (gx, gy, cell, max(1, cell // 3)))
            else:
                pygame.draw.rect(pat, (17, 17, 20, 255), (gx, gy, cell, cell))
                pygame.draw.rect(pat, (34, 34, 39, 255), (gx, gy, max(1, cell // 3), cell))
    _masked(surf, pat, c, r)
    # przyciemnienie przy krawędzi
    for i in range(max(2, int(r * 0.08))):
        pygame.draw.circle(surf, (0, 0, 0, 90 - i * 90 // max(2, int(r * 0.08))), c, int(r - i), 1)


# --------------------------------------------------------------------------
# Statyczna warstwa zegara (cache)
# --------------------------------------------------------------------------
_static_cache = {}


def _static_layer(th, radius, max_val, step, redline, unit, divide, kind):
    key = (th["name"], radius, round(max_val), round(step), round(redline or 0), unit, divide, kind)
    surf = _static_cache.get(key)
    if surf is not None:
        return surf
    if len(_static_cache) > 80:
        _static_cache.clear()

    pad = int(radius * 0.14) + 6
    size = 2 * (radius + pad)
    surf = pygame.Surface((size, size), pygame.SRCALPHA)
    c = (size // 2, size // 2)
    r = radius
    bg_for_glow = th["face"] if th["face_style"] == "flat" else th["bg"]

    # --- tarcza ---
    fs = th["face_style"]
    if fs == "flat":
        pygame.draw.circle(surf, th["face"], c, r)
    elif fs == "radial":
        for rr in range(r, 0, -2):
            pygame.draw.circle(surf, lerp(th["face"], th["face2"], (rr / r) ** 1.6), c, rr)
    elif fs == "carbon":
        _carbon(surf, c, r)

    # --- obręcz ---
    bz = th["bezel"]
    if bz == "ring":
        pygame.draw.circle(surf, th["bezel_color"], c, r, max(2, int(r * th["bezel_width"])))
    elif bz in METALS:
        light, dark = METALS[bz]
        _metal_ring(surf, c, r * (1.0 + th["bezel_width"]), r * 0.985, light, dark)
    elif bz == "glow":
        col = th["bezel_color"]
        gw = max(3, int(r * 0.07))
        for k in range(gw, 0, -1):
            a = int(160 * (1 - k / gw) ** 2)
            pygame.draw.circle(surf, (*col, a), c, r + k, 1)
        for k in range(1, gw):
            pygame.draw.circle(surf, lerp(th["face"], col, 0.5 * (1 - k / gw) ** 2), c, r - k, 1)
        pygame.draw.circle(surf, lerp(col, (255, 255, 255), 0.3), c, r, max(2, int(r * th["bezel_width"])))

    if max_val <= 0:
        max_val = 1.0

    # --- łuk / segmenty (tło) ---
    ri, ro = th["arc_radius"]
    if th["arc"] == "progress":
        arc_poly(surf, th["arc_bg"], c, r * ri, r * ro, 0.0, 1.0)
    elif th["arc"] == "segments":
        n = th["arc_segments"]
        gap = 0.22 / n
        for k in range(n):
            arc_poly(surf, th["arc_bg"], c, r * ri, r * ro, k / n + gap, (k + 1) / n - gap)

    # --- czerwone pole ---
    rz = th["redzone"]
    if redline and 0 < redline < max_val and rz != "none":
        f0 = redline / max_val
        r0, r1 = th["red_radius"]
        if rz == "glow":
            arc_poly(surf, lerp(bg_for_glow, th["red_color"], 0.35), c, r * (r0 - 0.03), r * (r1 + 0.03), f0, 1.0)
        arc_poly(surf, th["red_color"], c, r * r0, r * r1, f0, 1.0)

    # --- podziałka i liczby ---
    num_major = max(1, int(round(max_val / step)))
    sd = max(1, th["sub_divs"])
    total = num_major * sd
    num_font = get_font(th["num_font"], r * th["num_size"], th["num_bold"])
    for i in range(total + 1):
        frac = i / total
        a = _ang(frac)
        ca, sa = math.cos(a), math.sin(a)
        major = (i % sd == 0)
        val = frac * max_val
        in_red = bool(redline) and val >= redline - 1e-6 and th["redzone"] != "none"
        if in_red:
            col = th["red_color"]
        elif major or th["tick_minor_color"] is None:
            col = th["tick_color"]
        else:
            col = th["tick_minor_color"]

        if th["ticks"] == "line":
            r_in, r_out = th["tick_major"] if major else th["tick_minor"]
            w = _px(th["tick_width"][0 if major else 1], r)
            p1 = (c[0] + ca * r * r_in, c[1] + sa * r * r_in)
            p2 = (c[0] + ca * r * r_out, c[1] + sa * r * r_out)
            if th["glow"]:
                glow_line(surf, col, bg_for_glow, p1, p2, w)
            else:
                pygame.draw.line(surf, col, p1, p2, w)
        elif th["ticks"] == "dot":
            r_in, r_out = th["tick_major"] if major else th["tick_minor"]
            rm = r * (r_in + r_out) / 2
            pygame.draw.circle(surf, col, (int(c[0] + ca * rm), int(c[1] + sa * rm)),
                               max(1, int(r * (0.022 if major else 0.011))))

        show_num = major and (th["num_mode"] == "all" or (th["num_mode"] == "ends" and i in (0, total)))
        if show_num:
            ncol = th["red_color"] if in_red else (th["num_color"] or th["tick_color"])
            txt = num_font.render(str(int(round(val / divide))), True, ncol)
            rt = r * th["num_radius"]
            surf.blit(txt, txt.get_rect(center=(c[0] + ca * rt, c[1] + sa * rt)))

    # --- jednostka i napis ---
    if th["unit_pos"] is not None and unit:
        uf = get_font(th["unit_font"], r * th["unit_size"])
        us = uf.render(unit, True, th["unit_color"])
        surf.blit(us, us.get_rect(center=(c[0], c[1] + r * th["unit_pos"])))
    cap = th["caption"]
    if cap:
        text = cap.get(kind, "").format(unit=unit)
        if text:
            cf = get_font(th["caption_font"], r * th["caption_size"])
            cs = cf.render(text, True, th["caption_color"] or th["unit_color"])
            surf.blit(cs, cs.get_rect(center=(c[0], c[1] + r * th["caption_pos"])))

    surf = finalize(surf)
    _static_cache[key] = surf
    return surf


# --------------------------------------------------------------------------
# Rysowanie zegara
# --------------------------------------------------------------------------
def draw_gauge(target, th, cx, cy, radius, value, max_val, unit, step,
               redline=None, kind="rpm", divide=1):
    radius = int(radius)
    layer = _static_layer(th, radius, max_val, step, redline, unit, divide, kind)
    target.blit(layer, layer.get_rect(center=(cx, cy)))

    if max_val <= 0:
        max_val = 1.0
    r = radius
    c = (cx, cy)
    frac = max(0.0, min(1.0, value / max_val))
    accent = th["needle_rpm"] if kind == "rpm" else th["needle_speed"]
    face_bg = th["face"] if th["face_style"] == "flat" else th["bg"]

    # --- łuk / segmenty (wartość) ---
    ri, ro = th["arc_radius"]
    if th["arc"] == "segments":
        n = th["arc_segments"]
        gap = 0.22 / n
        lit = int(frac * n + 1e-6)
        for k in range(lit):
            mid = (k + 0.5) / n * max_val
            if kind == "rpm" and redline:
                col = th["seg_high"] if mid >= redline else th["seg_mid"] if mid >= redline * 0.8 else th["seg_low"]
            else:
                col = accent
            arc_poly(target, col, c, r * ri, r * ro, k / n + gap, (k + 1) / n - gap)
    elif th["arc"] == "progress" and frac > 0.002:
        col = th["red_color"] if (redline and value >= redline) else accent
        arc_poly(target, col, c, r * ri, r * ro, 0.0, frac)
        a = _ang(frac)
        rm = r * (ri + ro) / 2
        pygame.draw.circle(target, col, (int(cx + math.cos(a) * rm), int(cy + math.sin(a) * rm)),
                           max(2, int(r * (ro - ri) * 0.75)))

    # --- odczyt cyfrowy ---
    vf = get_font(th["value_font"], r * th["value_size"], th["value_bold"])
    vcol = th["value_color"] or accent
    vs = vf.render(f"{int(round(value)):,}".replace(",", " "), True, vcol)
    vrect = vs.get_rect(center=(cx, cy + r * th["value_pos"]))
    if th["value_box"]:
        box = vrect.inflate(int(r * 0.14), int(r * 0.05))
        pygame.draw.rect(target, th["value_box"], box, border_radius=max(2, int(r * 0.02)))
        if th["value_box_border"]:
            pygame.draw.rect(target, th["value_box_border"], box, max(1, int(r * 0.012)),
                             border_radius=max(2, int(r * 0.02)))
    target.blit(vs, vrect)

    # --- wskazówka ---
    nd = th["needle"]
    if nd != "none":
        a = _ang(frac)
        dx, dy = math.cos(a), math.sin(a)
        px, py = -dy, dx
        tip = (cx + dx * r * th["needle_len"], cy + dy * r * th["needle_len"])
        tail = (cx - dx * r * th["needle_tail"], cy - dy * r * th["needle_tail"])
        w = max(2.0, r * th["needle_width"])
        if nd == "line":
            pygame.draw.line(target, accent, tail, tip, max(3, int(w)))
        elif nd == "taper":
            hw = w * 0.85
            pts = [tip,
                   (cx + px * hw, cy + py * hw),
                   (tail[0] + px * hw * 0.55, tail[1] + py * hw * 0.55),
                   (tail[0] - px * hw * 0.55, tail[1] - py * hw * 0.55),
                   (cx - px * hw, cy - py * hw)]
            pygame.draw.polygon(target, accent, pts)
            pygame.draw.aalines(target, accent, True, pts)
        elif nd == "thin":
            pygame.draw.line(target, accent, tail, tip, max(2, int(w * 0.5)))
            pygame.draw.circle(target, accent, (int(tail[0]), int(tail[1])), max(2, int(w * 1.3)))
        elif nd == "glow":
            glow_line(target, accent, face_bg, tail, tip, max(2, int(w * 0.6)))

    # --- środek ---
    hb = th["hub"]
    if hb == "flat":
        pygame.draw.circle(target, th["hub_color"], c, max(4, int(r * 0.07)))
        pygame.draw.circle(target, th["hub_inner"], c, max(2, int(r * 0.035)))
    elif hb in METALS:
        light, dark = METALS[hb]
        pygame.draw.circle(target, dark, c, max(4, int(r * 0.085)))
        pygame.draw.circle(target, lerp(light, dark, 0.35), c, max(3, int(r * 0.065)))
        pygame.draw.circle(target, light, (cx - int(r * 0.02), cy - int(r * 0.02)), max(1, int(r * 0.022)))


def draw_timing_bar(target, th, cur_s, last_s, best_s, fmt):
    W, H = target.get_size()
    bar_y = int(H * 0.070)
    line_y = int(H * 0.130)
    font = get_font(th["bar_font"], min(W * 0.023, H * 0.050))
    items = [
        (int(W * 0.18), "CURRENT: ", fmt(cur_s), th["bar_text"]),
        (int(W * 0.52), "LAST: ", fmt(last_s), th["bar_text"]),
        (int(W * 0.83), "BEST: ", fmt(best_s), th["bar_best"] if best_s > 0 else th["bar_label"]),
    ]
    for cx, label, val_str, val_color in items:
        ls = font.render(label, True, th["bar_label"])
        vs = font.render(val_str, True, val_color)
        x = cx - (ls.get_width() + vs.get_width()) // 2
        y = bar_y - ls.get_height() // 2
        target.blit(ls, (x, y))
        target.blit(vs, (x + ls.get_width(), y))
    pygame.draw.line(target, th["bar_divider"], (int(W * 0.04), line_y), (int(W * 0.96), line_y), 2)
