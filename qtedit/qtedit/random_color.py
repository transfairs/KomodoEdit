"""Komodo's seeded randomColor (chrome/komodo/content/contrib/commonjs/
randomColor.js, David Merfield's randomColor "modified to take a seed and
only return a single color"), ported to Python with the JavaScript
semantics that decide the result: parseInt(seed, 36) stops at the first
non-base-36 character, % works on doubles, Math.round rounds .5 up.

Komodo seeds it with the language name to colour generated file icons, so
every language always gets the same colour.

>>> random_color("Batch", luminosity="light")  # same as Komodo (SpiderMonkey)
'#e6f9a2'
"""
import math

# loadColorBounds(): name -> (hue range, lower bounds), in definition order
# (getColorInfo returns the first match).
_COLORS = [
    ("monochrome", None, [[0, 0], [100, 0]]),
    ("red", [-26, 18], [[20, 100], [30, 92], [40, 89], [50, 85], [60, 78], [70, 70], [80, 60],
                        [90, 55], [100, 50]]),
    ("orange", [19, 46], [[20, 100], [30, 93], [40, 88], [50, 86], [60, 85], [70, 70], [100, 70]]),
    ("yellow", [47, 62], [[25, 100], [40, 94], [50, 89], [60, 86], [70, 84], [80, 82], [90, 80],
                          [100, 75]]),
    ("green", [63, 178], [[30, 100], [40, 90], [50, 85], [60, 81], [70, 74], [80, 64], [90, 50],
                          [100, 40]]),
    ("blue", [179, 257], [[20, 100], [30, 86], [40, 80], [50, 74], [60, 60], [70, 52], [80, 44],
                          [90, 39], [100, 35]]),
    ("purple", [258, 282], [[20, 100], [30, 87], [40, 79], [50, 70], [60, 65], [70, 59], [80, 52],
                            [90, 45], [100, 42]]),
    ("pink", [283, 334], [[20, 100], [30, 90], [40, 86], [60, 84], [80, 80], [90, 75], [100, 73]]),
]
_BASE36 = "0123456789abcdefghijklmnopqrstuvwxyz"


def _js_parse_int36(text):
    """parseInt(text, 36): leading whitespace skipped, then digits up to
    the first invalid one, accumulated in doubles; NaN -> None."""
    text = text.lstrip()
    sign = 1
    if text[:1] in ("+", "-"):
        sign = -1 if text[0] == "-" else 1
        text = text[1:]
    value = None
    for ch in text:
        digit = _BASE36.find(ch.lower())
        if digit < 0:
            break
        value = (value or 0.0) * 36 + digit
    return None if value is None else sign * value


def _js_round(x):
    return math.floor(x + 0.5)


def _random_within(seed, low, high):
    value = _js_parse_int36(seed)
    if value is None:
        value = 100
    value = value * (2 ** 13 + 1) + 1987
    return _js_round(low + math.fmod(value, 1000) / 1000 * (high - low))


def _color_info(hue):
    if 334 <= hue <= 360:
        hue -= 360
    for _name, hue_range, bounds in _COLORS:
        if hue_range and hue_range[0] <= hue <= hue_range[1]:
            return bounds
    raise ValueError(hue)


def _minimum_brightness(hue, saturation):
    bounds = _color_info(hue)
    for (s1, v1), (s2, v2) in zip(bounds, bounds[1:]):
        if s1 <= saturation <= s2:
            m = (v2 - v1) / (s2 - s1)
            return m * saturation + v1 - m * s1
    return 0


def _hsv_to_rgb(h, s, v):
    h = 1 if h == 0 else 359 if h == 360 else h  # randomColor's own fix
    h, s, v = h / 360, s / 100, v / 100
    h_i = math.floor(h * 6)
    f = h * 6 - h_i
    p, q, t = v * (1 - s), v * (1 - f * s), v * (1 - (1 - f) * s)
    r, g, b = [(v, t, p), (q, v, p), (p, v, t), (p, q, v), (t, p, v), (v, p, q)][h_i]
    return [math.floor(c * 255) for c in (r, g, b)]


def random_color(seed, luminosity=None):
    """randomColor({luminosity}, seed) -> '#rrggbb' (no hue option)."""
    hue = _random_within(seed, 0, 360)
    if hue < 0:
        hue += 360
    if luminosity == "random":
        saturation = _random_within(seed, 0, 100)
    else:
        bounds = _color_info(hue)
        s_min, s_max = bounds[0][0], bounds[-1][0]
        if luminosity == "bright":
            s_min = 55
        elif luminosity == "dark":
            s_min = s_max - 10
        elif luminosity == "light":
            s_max = 55
        saturation = _random_within(seed, s_min, s_max)
    b_min, b_max = _minimum_brightness(hue, saturation), 100
    if luminosity == "dark":
        b_max = b_min + 20
    elif luminosity == "light":
        b_min = (b_max + b_min) / 2
    elif luminosity == "random":
        b_min, b_max = 0, 100
    brightness = _random_within(seed, b_min, b_max)
    return "#" + "".join(f"{c:02x}" for c in _hsv_to_rgb(hue, saturation, brightness))
