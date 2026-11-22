#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
生日流光 · 3D Birthday
------------------------------------------------------------
· 开场：流光炫彩的「祝你快乐」
· 转场：文字碎成星屑，旋转着聚合成 3D 生日蛋糕（无白屏闪烁）
· 场景：三层全息流光蛋糕，透视旋转，环绕光带与 3D 星轨，暖色生日氛围
· 音乐：程序实时合成生日快乐歌，无外部素材

运行:  python 生日星空.py            (需要 pygame: pip install pygame)
出图:  python 生日星空.py --shot

鼠标:  移动撒星 / 点击爆星 / 按住拖动旋转视角 / 点蜡烛吹灭·点亮 / 靠近火苗变旺
键盘:  空格 重放音乐   M 静音   R 重来   Esc 退出
"""

import os
import sys
import math
import random
from array import array

os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

import pygame
from pygame import gfxdraw

# ------------------------------------------------------------------ 画面
W, H = 1200, 900
FS = 0.78   # 窗口显示缩放（画布 1200x900，窗口约 936x702）
CS = 0.72   # 蛋糕渲染分辨率（高清）
CX, CY = W // 2, 470
TAU = math.pi * 2

CAM = {"yaw": 0.62, "pitch": 0.36, "dist": 7.2, "focal": 1250, "ty": 0.80}

TIERS = [
    (1.18, 1.14, 0.00, 0.80, 84, 0.00),
    (0.99, 0.95, 0.80, 1.62, 72, 0.20),
]
NV = 4      # 侧壁纵向分段（越高越顺）
CANDLE_XZ = (0.14, 0.05)   # 蜡烛位置（偏离圆心，转动时能看到它在转）
CANDLE_Y0 = 1.64
CANDLE_H = 0.38


# ------------------------------------------------------------------ 颜色
def clamp(v, a, b):
    return a if v < a else (b if v > b else v)


def lerp(a, b, t):
    return a + (b - a) * t


def ease_out(x):
    x = clamp(x, 0.0, 1.0)
    return 1.0 - (1.0 - x) ** 3


def ease_in_out(x):
    x = clamp(x, 0.0, 1.0)
    return 3 * x * x - 2 * x * x * x


def cream(f):
    f = clamp(f, 0.0, 1.0)
    return (int(lerp(236, 255, f)), int(lerp(222, 253, f)), int(lerp(222, 252, f)), 255)


def rgba(c, a):
    return (int(c[0]), int(c[1]), int(c[2]), int(clamp(a, 0, 255)))


def mul(c, f):
    return (int(clamp(c[0] * f, 0, 255)), int(clamp(c[1] * f, 0, 255)),
            int(clamp(c[2] * f, 0, 255)))


_AURORA = [
    (0.00, (146, 148, 226)), (0.12, (172, 178, 244)), (0.24, (204, 188, 248)),
    (0.36, (240, 196, 244)), (0.48, (255, 204, 226)), (0.60, (255, 220, 198)),
    (0.72, (255, 198, 178)), (0.86, (226, 174, 220)), (1.00, (146, 148, 226)),
]
_RAINBOW_STOPS = _AURORA


def aurora(ph):
    """极光丝绸色带（低饱和粉彩）"""
    ph = ph % 1.0
    for i in range(len(_AURORA) - 1):
        a, ca = _AURORA[i]
        b, cb = _AURORA[i + 1]
        if a <= ph <= b:
            f = (ph - a) / (b - a)
            return (int(lerp(ca[0], cb[0], f)), int(lerp(ca[1], cb[1], f)),
                    int(lerp(ca[2], cb[2], f)))
    return _AURORA[-1][1]


def rainbow(ph):
    return aurora(ph)


def silk(u, v, t, scale=1.0, off=0.0):
    """丝绸材质：粉彩底 + 发光丝带芯 + 紫调阴影"""
    w = (v * 0.92 + u * 0.52 + 0.26 * math.sin((u * 0.8 - t * 0.20 + off) * TAU)
         + 0.14 * math.sin((u * 1.7 + v * 1.1 + t * 0.32) * TAU)
         + 0.05 * math.sin((u * 3.1 - v * 2.2 - t * 0.55) * TAU))
    c = aurora(w * 0.34 + t * 0.02 + off * 0.2)
    ph = (w * 0.62 + t * 0.03) % 1.0
    sn = math.sin(ph * TAU)
    if sn > 0:
        g = (sn ** 1.8) * 0.85
        c = (int(c[0] + (255 - c[0]) * g), int(c[1] + (250 - c[1]) * g),
             int(c[2] + (238 - c[2]) * g))
    else:
        d = ((-sn) ** 1.6) * 0.48
        c = (int(c[0] * (1 - d) + 74 * d), int(c[1] * (1 - d) + 62 * d),
             int(c[2] * (1 - d) + 148 * d))
    return c


def build_sheen(w, h, band=210):
    """供 BLEND_RGBA_ADD 使用的预乘亮度滑光带"""
    srf = pygame.Surface((w, h), pygame.SRCALPHA)
    for i in range(band):
        f = i / (band - 1)
        a = int(255 * (math.sin(math.pi * f) ** 2.2))
        pygame.draw.line(srf, (a, a, a, a), (i, 0), (i, h))
    return srf


def build_rainbow_strip(w=1024, h=48):
    s = pygame.Surface((w, h))
    for x in range(w):
        pygame.draw.line(s, rainbow(x / w), (x, 0), (x, h - 1))
    return s


# ------------------------------------------------------------------ 基础绘制
def new_layer():
    return pygame.Surface((W, H), pygame.SRCALPHA)


def star_points(cx, cy, r, rot=0.0, inner=0.44, n=5, squash=1.0):
    pts = []
    for i in range(n * 2):
        ang = rot + i * math.pi / n - math.pi / 2
        rad = r if i % 2 == 0 else r * inner
        pts.append((cx + math.cos(ang) * rad, cy + math.sin(ang) * rad * squash))
    return pts


def draw_poly(surf, pts, color, aa=True, grow=0.0):
    if len(color) == 4 and color[3] <= 0:
        return
    if grow > 0 and len(pts) >= 3:
        cx = sum(p[0] for p in pts) / len(pts)
        cy = sum(p[1] for p in pts) / len(pts)
        out = []
        for px, py in pts:
            dx, dy = px - cx, py - cy
            d = math.hypot(dx, dy) or 1.0
            out.append((px + dx / d * grow, py + dy / d * grow))
        pts = out
    ip = [(int(round(px)), int(round(py))) for px, py in pts]
    if len(ip) < 3:
        return
    try:
        gfxdraw.filled_polygon(surf, ip, color)
        if aa:
            gfxdraw.aapolygon(surf, ip, color)
    except (ValueError, TypeError):
        pass


def draw_star(surf, cx, cy, r, color, rot=0.0, squash=1.0):
    if r < 0.7:
        return
    draw_poly(surf, star_points(cx, cy, r, rot, squash=squash), color)


def draw_dot(surf, x, y, r, color):
    if r < 0.5:
        return
    x, y, r = int(round(x)), int(round(y)), max(1, int(round(r)))
    try:
        gfxdraw.filled_circle(surf, x, y, r, color)
        gfxdraw.aacircle(surf, x, y, r, color)
    except ValueError:
        pass


def draw_spark(surf, x, y, r, color, rot=0.0):
    if r < 0.7:
        return
    w = max(0.9, r * 0.16)
    pts = []
    for i in range(4):
        ang = rot + i * math.pi / 2
        pts.append((x + math.cos(ang) * r, y + math.sin(ang) * r))
        ang2 = ang + math.pi / 4
        pts.append((x + math.cos(ang2) * w, y + math.sin(ang2) * w))
    draw_poly(surf, pts, color)


def soft_blur(surf, k=8):
    w, h = surf.get_size()
    s = pygame.transform.smoothscale(surf, (max(1, w // k), max(1, h // k)))
    return pygame.transform.smoothscale(s, (w, h))


_grad_cache = {}


def radial_gradient(radius, color, power=2.0, mode="fall", res=128):
    key = (radius, color, power, mode)
    if key in _grad_cache:
        return _grad_cache[key]
    surf = pygame.Surface((res, res), pygame.SRCALPHA)
    for y in range(res):
        dy = (y + 0.5 - res / 2) / (res / 2)
        for x in range(res):
            dx = (x + 0.5 - res / 2) / (res / 2)
            d = math.hypot(dx, dy)
            if d >= 1.0:
                continue
            a = color[3] * ((1.0 - d) ** power if mode == "fall" else (d ** power))
            if a >= 0.6:
                surf.set_at((x, y), (color[0], color[1], color[2], int(a)))
    big = pygame.transform.smoothscale(surf, (radius * 2, radius * 2))
    _grad_cache[key] = big
    return big



_add_cache = {}


def radial_add(radius, color, power=2.0, res=112):
    """预乘亮度的加法光晕：配合 BLEND_RGBA_ADD 使用才有平滑渐变"""
    key = (radius, color, power)
    if key in _add_cache:
        return _add_cache[key]
    surf = pygame.Surface((res, res))
    surf.fill((0, 0, 0))
    c0, c1, c2 = color[0], color[1], color[2]
    for y in range(res):
        dy = (y + 0.5 - res / 2) / (res / 2)
        for x in range(res):
            dx = (x + 0.5 - res / 2) / (res / 2)
            d = math.hypot(dx, dy)
            if d >= 1.0:
                continue
            f = (1.0 - d) ** power
            surf.set_at((x, y), (int(c0 * f), int(c1 * f), int(c2 * f)))
    big = pygame.transform.smoothscale(surf, (radius * 2, radius * 2))
    _add_cache[key] = big
    return big


# ------------------------------------------------------------------ 字体
FONT_CJK = [
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
    "/usr/share/fonts/opentype/noto/NotoSerifCJK-Bold.ttc",
    "C:/Windows/Fonts/msyhbd.ttc",
    "C:/Windows/Fonts/msyh.ttc",
    "C:/Windows/Fonts/simhei.ttf",
    "/System/Library/Fonts/PingFang.ttc",
    "/System/Library/Fonts/STHeiti Medium.ttc",
]
FONT_KAI = [
    "/usr/share/fonts/truetype/arphic/ukai.ttc",
    "C:/Windows/Fonts/simkai.ttf",
    "C:/Windows/Fonts/STXINGKA.TTF",
    "C:/Windows/Fonts/STKAITI.TTF",
    "/usr/share/fonts/opentype/noto/NotoSerifCJK-Bold.ttc",
    "C:/Windows/Fonts/msyhbd.ttc",
    "/System/Library/Fonts/Supplemental/Kaiti.ttc",
]
FONT_SCRIPT = [
    "/usr/share/fonts/opentype/urw-base35/Z003-MediumItalic.otf",
    "C:/Windows/Fonts/Inkfree.ttf",
    "C:/Windows/Fonts/segoesc.ttf",
    "/System/Library/Fonts/Supplemental/SnellRoundhand.ttc",
]

_fonts = {}


def get_font(size, cjk=False, script=False, kai=False):
    key = (size, cjk, script, kai)
    if key in _fonts:
        return _fonts[key]
    f = None
    for p in (FONT_KAI if kai else FONT_SCRIPT if script else FONT_CJK):
        if os.path.exists(p):
            try:
                f = pygame.font.Font(p, size)
                break
            except Exception:
                f = None
    if f is None:
        name = "microsoftyahei,simhei,pingfangsc,notosanscjksc,arial" if cjk else "arial"
        f = pygame.font.SysFont(name, size)
    _fonts[key] = f
    return f


_text_cache = {}


def text_mask(text, size, cjk=False, script=False, pad=None, kai=False):
    key = ("mask", text, size, cjk, script, pad, kai)
    if key in _text_cache:
        return _text_cache[key]
    f = get_font(size, cjk, script, kai)
    pad = pad if pad is not None else int(size * 0.5)
    base = f.render(text, True, (255, 255, 255))
    surf = pygame.Surface((base.get_width() + pad * 2, base.get_height() + pad * 2),
                          pygame.SRCALPHA)
    surf.blit(base, (pad, pad))
    _text_cache[key] = surf
    return surf


def shadow_copy(surf, col=(58, 34, 78), blur=7, alpha=170):
    c = surf.copy()
    c.fill((*col, 255), special_flags=pygame.BLEND_RGBA_MULT)
    b = soft_blur(c, blur)
    b.set_alpha(alpha)
    return b


def glow_text(text, size, color, glow, cjk=False, script=False, glow_boost=1):
    key = ("glow", text, size, tuple(color), tuple(glow), cjk, script, glow_boost)
    if key in _text_cache:
        return _text_cache[key]
    f = get_font(size, cjk, script)
    base = f.render(text, True, color)
    bw, bh = base.get_size()
    pad = max(10, int(size * 0.62))
    surf = pygame.Surface((bw + pad * 2, bh + pad * 2), pygame.SRCALPHA)
    if glow:
        g = f.render(text, True, glow)
        padded = pygame.Surface((bw + pad * 2, bh + pad * 2), pygame.SRCALPHA)
        padded.blit(g, (pad, pad))
        wide = soft_blur(padded, 20)
        wide.set_alpha(120)
        surf.blit(wide, (0, 0))
        tight = soft_blur(padded, 8)
        tight.set_alpha(90)
        surf.blit(tight, (0, 0))
    surf.blit(base, (pad, pad))
    _text_cache[key] = surf
    return surf


def iridescent(mask, strip, phase, out=None):
    """把白字遮罩填成流动彩虹色"""
    w, h = mask.get_size()
    sw = strip.get_width()
    off = int(phase * sw) % sw
    seg = pygame.Surface((sw, strip.get_height()))
    seg.blit(strip, (-off, 0))
    seg.blit(strip, (sw - off, 0))
    grad = pygame.transform.smoothscale(seg, (w, h))
    if out is None:
        out = pygame.Surface((w, h), pygame.SRCALPHA)
    else:
        out.fill((0, 0, 0, 0))
    out.blit(mask, (0, 0))
    out.blit(grad, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
    return out


# ------------------------------------------------------------------ 音乐
def _midi_freq(m):
    return 440.0 * (2.0 ** ((m - 69) / 12.0))


MELODY = [
    67, .75, 69, .25, 67, .5, 72, .5, 71, 1.0, -1, .6,
    67, .75, 69, .25, 67, .5, 74, .5, 72, 1.0, -1, .6,
    67, .75, 79, .25, 76, .5, 72, .5, 71, .5, 69, 1.0, -1, .6,
    77, .75, 77, .25, 76, .5, 72, .5, 74, .5, 72, 1.0, -1, 1.4,
]


def synth_song(sr=44100, beat=0.58):
    beats = sum(MELODY[1::2])
    total = int(beat * beats * sr) + int(0.9 * sr)
    buf = array('f', bytes(4 * total))

    t = 0.0
    for i in range(0, len(MELODY), 2):
        midi, dur = MELODY[i], MELODY[i + 1]
        n = int(dur * beat * sr)
        off = int(t * sr)
        if midi > 0:
            f0 = _midi_freq(midi)
            att = max(1, int(0.012 * sr))
            rel = max(1, int(min(0.18 * sr, n * 0.4)))
            amp = 0.95 if dur <= 0.5 else 0.82
            for s in range(n):
                k = s / sr
                vib = 1.0 + 0.0032 * math.sin(TAU * 5.2 * k)
                x = math.sin(TAU * f0 * vib * k)
                x += 0.30 * math.sin(TAU * 2 * f0 * vib * k + 0.4)
                x += 0.10 * math.sin(TAU * 3 * f0 * k + 1.1)
                if s < att:
                    env = s / att
                else:
                    env = 0.55 + 0.45 * math.exp(-(s - att) / (0.24 * sr))
                if s > n - rel:
                    env *= (n - s) / rel
                if off + s < total:
                    buf[off + s] += x * env * amp
        t += dur * beat

    pad_len = min(total, int(t * sr) + int(0.7 * sr))
    for midi, g in ((48, 0.06), (55, 0.048), (64, 0.038)):
        f0 = _midi_freq(midi)
        for s in range(pad_len):
            buf[s] += g * math.sin(TAU * f0 * s / sr)

    for d, g in ((int(0.041 * sr), 0.22), (int(0.093 * sr), 0.14), (int(0.171 * sr), 0.08)):
        for s in range(d, total):
            buf[s] += buf[s - d] * g

    peak = max(1e-6, max(abs(v) for v in buf))
    scale = 0.88 * 32767.0 / peak
    out = array('h', bytes(4 * total))
    j = 0
    for s in range(total):
        v = buf[s] * scale
        iv = 32767 if v > 32767 else (-32767 if v < -32767 else int(v))
        out[j] = iv
        out[j + 1] = iv
        j += 2
    return out.tobytes()


# ------------------------------------------------------------------ 3D
VIEW = {"s": 1.0}


def project(x, y, z, cam=None):
    cam = cam or CAM
    y -= cam["ty"]
    cy_, sy_ = math.cos(cam["yaw"]), math.sin(cam["yaw"])
    x, z = x * cy_ + z * sy_, -x * sy_ + z * cy_
    cp, sp = math.cos(cam["pitch"]), math.sin(cam["pitch"])
    y, z = y * cp + z * sp, -y * sp + z * cp
    z += cam["dist"]
    if z < 0.35:
        z = 0.35
    k = cam["focal"] / z
    sc = VIEW["s"]
    return (CX * sc + x * k * sc, CY * sc - y * k * sc, z, k * sc)


def rot_yaw(x, z, cam=None):
    cam = cam or CAM
    c, s = math.cos(cam["yaw"]), math.sin(cam["yaw"])
    return (x * c + z * s, -x * s + z * c)


def cam_depth(x, y, z, cam=None):
    """相机空间深度：数值越大越远（用于正确的遮挡排序）"""
    cam = cam or CAM
    y -= cam["ty"]
    c, s = math.cos(cam["yaw"]), math.sin(cam["yaw"])
    x, z = x * c + z * s, -x * s + z * c
    cp, sp = math.cos(cam["pitch"]), math.sin(cam["pitch"])
    return -y * sp + z * cp + cam["dist"]


# ------------------------------------------------------------------ 背景

_SILK = [(96, 74, 146), (140, 112, 194), (196, 146, 208), (236, 160, 192),
         (252, 184, 178), (255, 208, 186), (240, 176, 204), (186, 146, 202),
         (124, 100, 160)]


def silk_ramp(f):
    f = clamp(f, 0, 0.999)
    i = int(f * (len(_SILK) - 1))
    u = f * (len(_SILK) - 1) - i
    a, b = _SILK[i], _SILK[min(i + 1, len(_SILK) - 1)]
    return (int(a[0] + (b[0] - a[0]) * u), int(a[1] + (b[1] - a[1]) * u),
            int(a[2] + (b[2] - a[2]) * u))


def build_silk_texture(w=1400, h=640):
    """预渲染丝绸布面：极光渐变 + 柔光云团 + 宽缎带 + 织纹 + 星屑"""
    s = pygame.Surface((w, h), pygame.SRCALPHA)
    for y in range(h):
        c = silk_ramp(y / h * 0.98)
        pygame.draw.line(s, (c[0], c[1], c[2], 255), (0, y), (w - 1, y))

    rnd = random.Random(13)

    # 大尺度柔光云团（打散规律性）
    for i in range(7):
        rad = rnd.randint(160, 420)
        col = rnd.choice([(255, 236, 246), (232, 214, 255), (255, 226, 200),
                          (205, 220, 255), (255, 208, 226)])
        blob = radial_gradient(rad, (col[0], col[1], col[2], 105), 2.2, res=80)
        s.blit(blob, (rnd.randint(-rad, w - rad // 2), rnd.randint(-rad, h - rad // 2)))

    # 宽缎面亮带（低频，跨度大）
    for i in range(3):
        amp = h * rnd.uniform(0.10, 0.20)
        ph = rnd.uniform(0, TAU)
        k = rnd.uniform(0.7, 1.5)
        cy = h * rnd.uniform(0.15, 0.85)
        th = h * rnd.uniform(0.06, 0.13)
        col = rnd.choice([(255, 252, 248), (255, 240, 220), (255, 246, 255)])
        lay = pygame.Surface((w, h), pygame.SRCALPHA)
        for x in range(w):
            yy = cy + math.sin(x / w * TAU * k + ph) * amp \
                 + math.sin(x / w * TAU * (k + 1.9) + ph * 2.1) * amp * 0.35
            thh = th * (1.0 + 0.30 * math.sin(x / w * TAU * 1.6 + ph))
            pygame.draw.line(lay, (col[0], col[1], col[2], 150),
                             (x, yy - thh), (x, yy + thh))
        lay = soft_blur(lay, 16)
        s.blit(lay, (0, 0))

    # 紫调暗带（体积）
    for i in range(2):
        amp = h * rnd.uniform(0.08, 0.16)
        ph = rnd.uniform(0, TAU)
        k = rnd.uniform(0.8, 1.6)
        cy = h * rnd.uniform(0.1, 0.9)
        th = h * rnd.uniform(0.05, 0.11)
        lay = pygame.Surface((w, h), pygame.SRCALPHA)
        for x in range(w):
            yy = cy + math.sin(x / w * TAU * k + ph + 1.7) * amp
            pygame.draw.line(lay, (96, 82, 172, 115), (x, yy - th), (x, yy + th))
        lay = soft_blur(lay, 14)
        s.blit(lay, (0, 0))

    # 细织纹
    grain = pygame.Surface((w, h), pygame.SRCALPHA)
    for i in range(70):
        x0 = rnd.uniform(-h, w)
        col = rnd.choice([(255, 255, 255, 22), (255, 240, 250, 18), (180, 170, 255, 18)])
        pygame.draw.line(grain, col, (x0, 0), (x0 + h * 0.25, h), 1)
    s.blit(grain, (0, 0))

    # 星屑
    for i in range(150):
        x, y = rnd.randint(0, w - 1), rnd.randint(0, h - 1)
        pygame.draw.circle(s, (255, 252, 250, rnd.randint(90, 200)),
                           (x, y), rnd.choice([1, 1, 2]))

    # 柔和高光带（斜向掠过，随纹理滚动形成"流动的釉光"）
    sheen = pygame.Surface((w, h), pygame.SRCALPHA)
    for k in range(2):
        cx = w * (0.34 + k * 0.42)
        ang = 0.55 + k * 0.2
        for i in range(0, w, 6):
            for j in (0,):
                pass
    # 用斜向渐变条带：沿一条斜线做宽高斯光
    # 上下环境色（顶部偏暖亮、底部偏冷暗）
    tint = pygame.Surface((w, h), pygame.SRCALPHA)
    for y in range(h):
        f = y / (h - 1)
        a = int(26 * f)
        pygame.draw.line(tint, (186, 156, 176, a), (0, y), (w - 1, y))
    s.blit(tint, (0, 0))
    band = pygame.Surface((w, h), pygame.SRCALPHA)
    for i in range(w):
        for k in range(2):
            x0 = w * (0.30 + k * 0.45)
            a = int(96 * math.exp(-((i - x0) ** 2) / (2 * (w * 0.055) ** 2)))
            if a > 3:
                pygame.draw.line(band, (255, 252, 250, a), (i, 0), (i + int(h * 0.42), h))
    band = soft_blur(band, 12)
    s.blit(band, (0, 0))

    return soft_blur(s, 2)


def build_ribbon(seed=1, hue=0.0, w=220, h=64, alpha=150):
    """柔光丝绸飘带（小尺寸生成后放大，自带柔边）"""
    rnd = random.Random(seed)
    srf = pygame.Surface((w, h), pygame.SRCALPHA)
    for x in range(w):
        col = aurora(x / w + hue)
        cy = h * 0.5 + math.sin(x / w * TAU * 1.25 + seed * 1.7) * h * 0.16
        th = h * 0.30 * (1.0 + 0.22 * math.sin(x / w * TAU * 2.6 + seed))
        feather = (math.sin(math.pi * (x / w)) ** 0.65)
        for y in range(h):
            f = (y - cy) / th
            if abs(f) >= 1.0:
                continue
            aa = int(alpha * feather * (math.cos(f * math.pi * 0.5) ** 1.5))
            if aa <= 0:
                continue
            srf.set_at((x, y), (col[0], col[1], col[2], aa))
    return srf



def build_rays():
    """斜向体积光（照片感的柔光柱）"""
    s = pygame.Surface((W, H), pygame.SRCALPHA)
    rnd = random.Random(77)
    for k in range(3):
        x0 = -60 + k * 260
        wdt = rnd.randint(120, 220)
        ang = 0.42 + k * 0.06
        for i in range(0, H + 40, 3):
            sway = math.sin(i * 0.012 + k) * 18
            a = int(max(0, 70 - abs(i - H * 0.25) // 8) * (0.35 + 0.3 * math.sin(i * 0.02 + k)))
            if a <= 2:
                continue
            x = x0 + i * ang / 2 + sway
            pygame.draw.line(s, (255, 246, 232, a), (x, i), (x + wdt, i), 2)
    s = soft_blur(s, 18)
    return s


def build_background():
    """深夜紫罗兰 + 霓虹星云：让奶白水果蛋糕更亮更清晰"""
    s = pygame.Surface((W, H))
    stops = [(0.0, (24, 20, 54)), (0.16, (38, 26, 78)), (0.34, (66, 34, 100)),
             (0.52, (104, 44, 116)), (0.70, (156, 66, 116)),
             (0.84, (204, 100, 104)), (1.0, (232, 146, 116))]
    for y in range(H):
        p_ = y / (H - 1)
        c = stops[-1][1]
        for i in range(len(stops) - 1):
            a, ca = stops[i]
            b, cb = stops[i + 1]
            if a <= p_ <= b:
                f = (p_ - a) / (b - a)
                c = (int(lerp(ca[0], cb[0], f)), int(lerp(ca[1], cb[1], f)),
                     int(lerp(ca[2], cb[2], f)))
                break
        pygame.draw.line(s, c, (0, y), (W, y))

    rnd0 = random.Random(97)
    # 星云
    neb = new_layer()
    for i in range(12):
        rad = rnd0.randint(160, 360)
        col = rnd0.choice([(150, 90, 240), (255, 96, 180), (255, 160, 110),
                           (90, 160, 250), (200, 90, 235), (90, 230, 220)])
        g = radial_gradient(rad, (col[0], col[1], col[2], 78), 2.2, res=96)
        neb.blit(g, (rnd0.randint(-180, W - 40), rnd0.randint(-140, H - 40)))
    neb = soft_blur(neb, 8)
    s.blit(neb, (0, 0))

    # 蛋糕背后的主光晕
    key = radial_gradient(430, (255, 170, 190, 120), 2.1, res=120)
    s.blit(key, (CX - 430, 300))
    hor = radial_gradient(360, (255, 196, 150, 130), 2.0, res=96)
    hor = pygame.transform.smoothscale(hor, (int(W * 1.4), 320))
    s.blit(hor, (-W // 5, H - 210))

    # 星点
    for i in range(190):
        x, y = rnd0.randint(0, W), rnd0.randint(0, H)
        r = rnd0.choice([1, 1, 1, 2, 2, 3])
        a = rnd0.randint(70, 200)
        pygame.draw.circle(s, (255, 250, 255, a), (x, y), r)

    # 彩色纸屑（远近两层）
    conf = new_layer()
    for i in range(150):
        x, y = rnd0.randint(-20, W + 20), rnd0.randint(-20, H + 20)
        col = rnd0.choice([(255, 130, 190), (140, 200, 255), (255, 210, 120),
                           (190, 150, 255), (130, 240, 220), (255, 110, 150)])
        sz = rnd0.randint(2, 5)
        al = rnd0.randint(50, 150)
        if i % 3 == 0:
            pygame.draw.circle(conf, (col[0], col[1], col[2], al), (x, y), sz)
        else:
            pygame.draw.line(conf, (col[0], col[1], col[2], al), (x, y), (x + sz, y + sz * 2), 2)
    s.blit(conf, (0, 0))

    # 极光飘带
    rnd = random.Random(23)
    for i in range(6):
        rib = build_ribbon(seed=i + 1, hue=i * 0.17, alpha=110 + 40 * (i % 2))
        rib = soft_blur(rib, 3)
        rw = rnd.randint(int(W * 0.9), int(W * 1.7))
        rh = int(rw * 0.26)
        rib = pygame.transform.smoothscale(rib, (rw, rh))
        ang = rnd.uniform(-16, 16)
        if ang:
            rib = pygame.transform.rotozoom(rib, ang, 1.0)
        rib.set_alpha(165)
        s.blit(rib, (rnd.randint(-rw // 3, W - rw // 2),
                     rnd.randint(-60, H - rh + 40)))

    bokeh = new_layer()
    for _ in range(48):
        r = rnd.randint(12, 74)
        x, y = rnd.randint(-40, W + 40), rnd.randint(-40, H + 40)
        col = rnd.choice([(255, 226, 200), (255, 176, 214), (190, 226, 255),
                          (255, 246, 236), (214, 196, 255)])
        k = rnd.randint(6, 15)
        g = radial_add(r, (col[0] * k // 255, col[1] * k // 255, col[2] * k // 255), 1.7, res=64)
        s.blit(g, (x - r, y - r), special_flags=pygame.BLEND_RGBA_ADD)
    return s


_VIVID = [(255, 138, 190), (150, 210, 255), (255, 200, 120), (200, 160, 255),
          (140, 245, 220), (255, 120, 160)]
_BALLOON_COLS = [(255, 190, 214), (206, 190, 252), (255, 214, 176),
                 (176, 226, 250), (246, 200, 246)]


def build_balloon_sprite(base, size=120):
    srf = pygame.Surface((size, size), pygame.SRCALPHA)
    h = size * 0.5
    for y in range(size):
        for x in range(size):
            dx = (x - h) / h
            dy = (y - h) / h * 1.06
            d2 = dx * dx + dy * dy
            if d2 > 1.0:
                continue
            d = math.sqrt(d2)
            sh = 1.18 - 0.40 * (d ** 1.7)
            hl = math.exp(-((dx + 0.34) ** 2 + (dy + 0.40) ** 2) * 5.5) * 0.55
            c = (int(min(255, base[0] * sh + 255 * hl)),
                 int(min(255, base[1] * sh + 255 * hl)),
                 int(min(255, base[2] * sh + 255 * hl)))
            a = int(255 * clamp((1.0 - d) / 0.12, 0.0, 1.0))
            if a <= 0:
                continue
            srf.set_at((x, y), (c[0], c[1], c[2], a))
    return srf


def make_aurora_layers():
    """缓慢飘动的第二层极光（每帧平移，营造流动）"""
    out = []
    rnd = random.Random(41)
    for i in range(2):
        rib = build_ribbon(seed=11 + i, hue=0.1 + i * 0.3, alpha=95)
        rib = soft_blur(rib, 2)
        rw = int(W * 1.5)
        rh = int(rw * 0.20)
        rib = pygame.transform.smoothscale(rib, (rw, rh))
        rib = pygame.transform.rotozoom(rib, -10 + i * 9, 1.0)
        rib.set_alpha(105 - i * 12)
        out.append([rib, rnd.uniform(0, rw), rnd.uniform(-40, H - rh),
                    rnd.uniform(2.5, 6.0), rh, rnd.uniform(0, 3)])
    return out


def make_bokeh_sprites():
    rnd = random.Random(31)
    out = []
    for _ in range(20):
        r = rnd.randint(10, 30)
        col = rnd.choice([(255, 216, 150), (255, 160, 200), (175, 235, 255), (255, 245, 220)])
        k = rnd.randint(10, 22)
        img = radial_add(r, (col[0] * k // 255, col[1] * k // 255, col[2] * k // 255), 1.5, res=64)
        out.append([img, rnd.uniform(0, W), rnd.uniform(0, H),
                    rnd.uniform(-10, 10), rnd.uniform(-24, -6), r])
    return out


# ------------------------------------------------------------------ 蛋糕
# ================================================================ 水果 & 奶油

_ICING = [(252, 248, 242), (250, 244, 240), (252, 246, 244), (250, 242, 244),
          (253, 248, 244), (251, 244, 246), (254, 250, 246)]

# 顶面同心渐变（蓝 → 紫 → 粉 → 奶白）
_TOP = [(170, 216, 238), (198, 214, 240), (232, 206, 232), (248, 212, 222),
        (253, 226, 230), (255, 246, 242), (255, 252, 248)]

_fruit_cache = {}


_LIGHT = (-0.42, -0.56, 0.72)


def _sphere(S, col, exp=26, amb=0.34, rim=(255, 255, 255), rim_amt=0.0,
            spec_amt=1.0, squash=1.0):
    """Lambert + Blinn-Phong 球体，返回 sprite（半径 S/2）"""
    srf = pygame.Surface((S, S), pygame.SRCALPHA)
    c = S / 2.0
    lx, ly, lz = _LIGHT
    n = math.sqrt(lx * lx + ly * ly + lz * lz)
    lx, ly, lz = lx / n, ly / n, lz / n
    hx, hy, hz = lx, ly, lz + 1.0
    hn = math.sqrt(hx * hx + hy * hy + hz * hz)
    hx, hy, hz = hx / hn, hy / hn, hz / hn
    for y in range(S):
        for x in range(S):
            dx = (x - c + 0.5) / c
            dy = (y - c + 0.5) / (c * squash)
            d2 = dx * dx + dy * dy
            if d2 >= 1.0:
                continue
            nz = math.sqrt(1.0 - d2)
            ndl = max(0.0, dx * lx + dy * ly + nz * lz)
            sp = max(0.0, dx * hx + dy * hy + nz * hz) ** exp
            sh = amb + (1.0 - amb) * ndl
            r = col[0] * sh + rim[0] * (rim_amt * (d2 ** 4)) + 255 * sp * spec_amt
            g = col[1] * sh + rim[1] * (rim_amt * (d2 ** 4)) + 255 * sp * spec_amt
            b = col[2] * sh + rim[2] * (rim_amt * (d2 ** 4)) + 255 * sp * spec_amt
            a = int(255 * clamp((1.0 - d2) / 0.045, 0.0, 1.0))
            srf.set_at((x, y), (int(min(255, r)), int(min(255, g)), int(min(255, b)), a))
    return srf


def build_fruit(kind, S=180):
    s = pygame.Surface((S, S), pygame.SRCALPHA)
    c = S / 2
    if kind == "straw":
        w, h = S * 0.31, S * 0.33
        # 轮廓遮罩
        mask = pygame.Surface((S, S), pygame.SRCALPHA)
        pygame.draw.ellipse(mask, (255, 255, 255, 255), (c - w, c - h * 1.20, w * 2, h * 2.0))
        pygame.draw.polygon(mask, (255, 255, 255, 255),
                            [(c - w * 0.90, c + h * 0.20), (c + w * 0.90, c + h * 0.20),
                             (c, c + h * 1.30)])
        # 球面光照
        bw, bh = int(w * 2.3), int(h * 2.9)
        ball = _sphere(bw, (222, 40, 62), exp=15, amb=0.30,
                       rim=(255, 130, 150), rim_amt=0.40, spec_amt=0.45)
        body = pygame.Surface((S, S), pygame.SRCALPHA)
        body.blit(ball, (int(c - bw / 2), int(c - h * 0.55 - bh / 2)))
        body.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
        # 籽
        for i in range(24):
            ang = i * 2.399
            rr = w * (0.28 + 0.58 * ((i % 5) / 4.0))
            x = c + math.cos(ang) * rr
            y = c + math.sin(ang * 1.15) * rr * 0.95 + h * 0.06
            if (x - c) ** 2 / (w * w * 1.02) + (y - c) ** 2 / (h * h * 1.5) > 0.9:
                continue
            pygame.draw.ellipse(body, (255, 228, 152), (x - 1.6, y - 2.4, 3.2, 4.8))
        s.blit(body, (0, 0))
        # 花萼
        for k in range(6):
            a = -math.pi / 2 + k * TAU / 6
            p0 = (c, c - h * 1.02)
            p1 = (c + math.cos(a) * w * 1.26, c - h * 1.02 + math.sin(a) * w * 0.72)
            p2 = (c + math.cos(a + 0.62) * w * 0.80, c - h * 1.02 + math.sin(a + 0.62) * w * 0.52)
            pygame.draw.polygon(s, (56, 142, 72), [p0, p1, p2])
            pygame.draw.line(s, (120, 194, 118), p0, p1, 1)
        pygame.draw.line(s, (86, 120, 56), (c, c - h * 1.0), (c + w * 0.14, c - h * 1.55), 3)
    elif kind == "blue":
        r = S * 0.26
        s = pygame.Surface((S, S), pygame.SRCALPHA)
        s.blit(_sphere(int(r * 2), (126, 140, 226), exp=30, amb=0.40,
                       rim=(196, 216, 255), rim_amt=0.70, spec_amt=1.0),
               (int(c - r), int(c - r)))
        pygame.draw.circle(s, (206, 220, 255), (int(c), int(c - r * 0.92)), 3)
        pygame.draw.circle(s, (74, 78, 146), (int(c), int(c - r * 0.62)), 3)
        draw_dot(s, c - r * 0.35, c - r * 0.42, r * 0.30, (255, 255, 255, 160))
    elif kind == "rasp":
        s = pygame.Surface((S, S), pygame.SRCALPHA)
        r = S * 0.085
        for i in range(26):
            ring = i // 9
            a = i * 2.399
            rr = S * (0.20 - ring * 0.055)
            x, y = c + math.cos(a) * rr, c + math.sin(a) * rr * 0.92
            d = _sphere(int(r * 2), (206, 40, 96), exp=20, amb=0.30,
                        rim=(255, 150, 190), rim_amt=0.35, spec_amt=0.5)
            s.blit(d, (int(x - r), int(y - r)))
    elif kind == "kiwi":
        r = S * 0.31
        pygame.draw.circle(s, (232, 226, 196), (int(c), int(c)), int(r))
        pygame.draw.circle(s, (156, 196, 92), (int(c), int(c)), int(r * 0.90))
        pygame.draw.circle(s, (206, 226, 152), (int(c), int(c)), int(r * 0.36))
        for i in range(14):
            a = i / 14 * TAU
            x, y = c + math.cos(a) * r * 0.58, c + math.sin(a) * r * 0.58
            pygame.draw.circle(s, (78, 84, 48), (int(x), int(y)), max(1, int(r * 0.075)))
        lay = new_layer()
        pygame.draw.circle(lay, (255, 255, 255, 70), (int(c), int(c)), int(r * 0.90))
        s.blit(lay, (0, 0))
    elif kind == "orange":
        r = S * 0.31
        pygame.draw.circle(s, (252, 236, 206), (int(c), int(c)), int(r))
        pygame.draw.circle(s, (248, 156, 54), (int(c), int(c)), int(r * 0.91))
        pygame.draw.circle(s, (255, 190, 96), (int(c), int(c)), int(r * 0.70))
        for i in range(8):
            a = i / 8 * TAU
            pygame.draw.line(s, (252, 236, 206), (int(c), int(c)),
                             (int(c + math.cos(a) * r * 0.88),
                              int(c + math.sin(a) * r * 0.88)), 3)
        pygame.draw.circle(s, (255, 250, 232), (int(c), int(c)), int(r * 0.11))
        draw_dot(s, c - r * 0.42, c - r * 0.44, r * 0.34, (255, 255, 240, 110))
    elif kind == "cherry":
        r = S * 0.23
        s.blit(_sphere(int(r * 2), (168, 18, 40), exp=34, amb=0.30,
                       rim=(255, 120, 130), rim_amt=0.35, spec_amt=0.9),
               (int(c - r), int(c - r + S * 0.10)))
        pygame.draw.line(s, (92, 132, 66), (c + r * 0.15, c - r * 0.55),
                         (c + r * 1.3, c - r * 2.4), 4)
        pygame.draw.line(s, (150, 196, 120), (c + r * 0.15, c - r * 0.55),
                         (c + r * 1.3, c - r * 2.4), 1)
    return _tighten(s, 0.90)


_FSIZE = {"straw": 1.0, "blue": 0.80, "rasp": 0.84, "cherry": 0.90,
          "kiwi": 1.02, "orange": 1.0}

_FRUIT_BASE = {}


def _tighten(spr, fill=0.96):
    bb = spr.get_bounding_rect()
    if bb.w < 2 or bb.h < 2:
        return spr
    crop = spr.subsurface(bb).copy()
    side = int(max(crop.get_width(), crop.get_height()) / fill)
    out = pygame.Surface((side, side), pygame.SRCALPHA)
    out.blit(pygame.transform.smoothscale(crop, (int(crop.get_width() / fill),
                                                int(crop.get_height() / fill)),
                                          ), ((side - int(crop.get_width() / fill)) // 2,
                                              (side - int(crop.get_height() / fill)) // 2))
    return out


def fruit_sprite(kind, size):
    size = max(6, int(size))
    key = (kind, size)
    hit = _fruit_cache.get(key)
    if hit is not None:
        return hit
    if kind not in _FRUIT_BASE:
        _FRUIT_BASE[kind] = build_fruit(kind)
    base = _FRUIT_BASE[kind]
    sc = pygame.transform.smoothscale(base, (size, size))
    _fruit_cache[key] = sc
    return sc


def _heart_pts(cx, cy, w, n=88):
    pts = []
    for i in range(n):
        t = i / n * TAU
        hx = 16 * math.sin(t) ** 3
        hy = -(13 * math.cos(t) - 5 * math.cos(2 * t)
               - 2 * math.cos(3 * t) - math.cos(4 * t))
        pts.append((cx + hx / 32.0 * w, cy + hy / 33.0 * w))
    return pts


def _sheen(dst, rect, color=(255, 255, 255), alpha=170, dx=-0.22, dy=-0.26,
           power=1.9, ell=True):
    """在椭圆/矩形内叠一层柔光（内部渐变，不产生分层环纹）"""
    w, h = max(3, int(rect.w * 1.24)), max(3, int(rect.h * 1.24))
    g = radial_gradient(int(max(w, h) * 1.15), rgba(color, alpha), power, res=64)
    g = pygame.transform.smoothscale(g, (w, h))
    mk = pygame.Surface((w, h), pygame.SRCALPHA)
    if ell:
        pygame.draw.ellipse(mk, (255, 255, 255, 255), (0, 0, w, h))
    else:
        mk.fill((255, 255, 255, 255))
    g.blit(mk, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
    dst.blit(g, (int(rect.x + dx * rect.w - (w - rect.w) * 0.5),
                 int(rect.y + dy * rect.h - (h - rect.h) * 0.5)))


def _heart_pts(cx, cy, w, n=88):
    pts = []
    for i in range(n):
        t = i / n * TAU
        hx = 16 * math.sin(t) ** 3
        hy = -(13 * math.cos(t) - 5 * math.cos(2 * t)
               - 2 * math.cos(3 * t) - math.cos(4 * t))
        pts.append((cx + hx / 32.0 * w, cy + hy / 33.0 * w))
    return pts


def build_heart(S=230, col=(255, 108, 150)):
    """亮面翻糖爱心（参考图那种粉色立体爱心）：粉渐变 + 银边 + 镜面高光"""
    s = pygame.Surface((S, S), pygame.SRCALPHA)
    cx, cy, w = S * 0.52, S * 0.50, S * 0.84
    pts = _heart_pts(cx, cy, w)
    draw_poly(s, [(x + S * 0.014, y + S * 0.055) for x, y in pts],
              (150, 52, 92, 90), grow=S * 0.016)
    draw_poly(s, pts, mul(col, 0.82))
    hm = pygame.Surface((S, S), pygame.SRCALPHA)
    draw_poly(hm, pts, (255, 255, 255, 255))
    g = radial_gradient(int(S * 1.05), (255, 228, 240, 205), 2.1, res=72)
    g = pygame.transform.smoothscale(g, (S, S))
    g.blit(hm, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
    s.blit(g, (int(-S * 0.10), int(-S * 0.14)))
    g2 = radial_gradient(int(S * 0.42), (255, 255, 255, 225), 2.0, res=56)
    g2 = pygame.transform.smoothscale(g2, (int(S * 0.42), int(S * 0.42)))
    g2.blit(hm, (int(-S * 0.29), int(-S * 0.29)),
            special_flags=pygame.BLEND_RGBA_MULT)
    s.blit(g2, (int(cx - w * 0.52), int(cy - w * 0.52)))
    try:
        pygame.draw.aalines(s, (255, 246, 251, 215), True,
                            [(int(x), int(y)) for x, y in pts])
        pygame.draw.aalines(s, (232, 92, 136, 120), True,
                            [(int(x + S * 0.010), int(y + S * 0.014)) for x, y in pts])
    except ValueError:
        pass
    return s


def _wing_pts(w, h, n=54, tip=0.34):
    """带外上尖角的翅形点列"""
    pts = []
    for i in range(n):
        t = i / n * TAU
        x = math.cos(t) * w
        y = math.sin(t) * h
        k = max(0.0, math.cos(t)) ** 2.4 * max(0.0, -math.sin(t)) ** 0.7
        x += w * tip * k * 1.25
        y -= h * tip * k * 2.0
        pts.append((x, y))
    return pts


def _wing_sprite(w, h, c_out, c_in, rim, ang, seed=1):
    """一片通透银闪翅膀：粉色翅面 + 内层珠光 + 银边 + 亮片"""
    pad = int(max(w, h) * 1.75)
    ws = pygame.Surface((int(pad * 2), int(pad * 2)), pygame.SRCALPHA)
    cx = cy = pad
    pts = [(cx + px, cy + py) for px, py in _wing_pts(w, h)]
    draw_poly(ws, [(x - w * 0.02, y + h * 0.06) for x, y in pts],
              rgba(mul(c_out, 0.86), 255), grow=2)
    draw_poly(ws, pts, rgba(c_out, 255))
    # 内层珠光（同形缩小）
    for f, col, al in ((0.70, c_in, 172), (0.30, (255, 255, 255), 92)):
        p2 = [(cx + (x - cx) * f - w * 0.05, cy + (y - cy) * f - h * 0.06) for x, y in pts]
        draw_poly(ws, p2, rgba(col, al), aa=False)
    # 翅脉
    for k in range(3):
        draw_poly(ws, [(cx + w * 0.06, cy + h * 0.55),
                       (cx + w * (0.86 - 0.04 * k), cy - h * (0.05 + 0.30 * k)),
                       (cx + w * 0.10, cy + h * 0.58)], (255, 255, 255, 80), aa=False)
    # 银色描边 + 亮片
    try:
        pygame.draw.aalines(ws, rgba(mul(c_out, 0.62), 190), True,
                            [(int(x), int(y)) for x, y in pts], 2)
        pygame.draw.aalines(ws, rgba(rim, 240), True,
                            [(int(x), int(y)) for x, y in pts])
        pygame.draw.aalines(ws, (255, 236, 248, 150), True,
                            [(int(cx + (x - cx) * 0.94), int(cy + (y - cy) * 0.94)) for x, y in pts])
    except ValueError:
        pass
    rnd = random.Random(seed)
    for k in range(9):
        a = rnd.uniform(0.0, TAU)
        rr = rnd.uniform(0.35, 0.88)
        bx = cx + math.cos(a) * w * rr
        by = cy + math.sin(a) * h * rr
        br = max(1.2, w * rnd.uniform(0.030, 0.072))
        pygame.draw.circle(ws, (255, 255, 255, 240), (int(bx), int(by)), int(br))
        pygame.draw.circle(ws, (255, 255, 255, 255),
                           (int(bx - br * 0.25), int(by - br * 0.25)), max(1, int(br * 0.45)))
    return pygame.transform.rotate(ws, ang)


def build_butterfly(S=320, tint=(255, 88, 152), tint2=(150, 128, 236),
                    silver=(244, 250, 255)):
    """银闪通透蝴蝶（参考图里的亮片蝴蝶）：四片半透翅膀 + 银边 + 珠光"""
    s = pygame.Surface((S, S), pygame.SRCALPHA)
    c = S * 0.5
    wings = ((S * 0.240, S * 0.162, 16, -0.200, -0.150, tint, (255, 196, 224), 4),
             (S * 0.240, S * 0.162, -16, 0.200, -0.150, tint, (255, 196, 224), 5),
             (S * 0.172, S * 0.112, 40, -0.158, 0.170, tint2, (206, 190, 246), 6),
             (S * 0.172, S * 0.112, -40, 0.158, 0.170, tint2, (206, 190, 246), 7))
    for (w, h, ang, dx, dy, co, ci, sd) in wings:
        sp = _wing_sprite(w, h, co, ci, silver, ang, sd)
        s.blit(sp, (int(c + S * dx - sp.get_width() / 2),
                    int(c + S * dy - sp.get_height() / 2)))
    bw, bh = S * 0.055, S * 0.20
    pygame.draw.ellipse(s, (188, 180, 224, 255),
                        (int(c - bw), int(c - bh * 0.55), int(bw * 2), int(bh * 1.75)))
    pygame.draw.ellipse(s, (252, 250, 255, 255),
                        (int(c - bw * 0.70), int(c - bh * 0.50), int(bw * 1.4), int(bh * 1.6)))
    pygame.draw.ellipse(s, (255, 255, 255, 200),
                        (int(c - bw * 0.30), int(c - bh * 0.60), int(bw * 0.56), int(bh * 1.4)))
    pygame.draw.circle(s, (252, 250, 255), (int(c), int(c - bh * 0.80)), max(2, int(S * 0.030)))
    for sgn in (-1, 1):
        pts = []
        for i in range(9):
            f = i / 8.0
            pts.append((c + sgn * S * (0.006 + 0.080 * f * f),
                        c - bh * 0.92 - S * 0.150 * f))
        pygame.draw.aalines(s, (236, 230, 250, 220), False, pts)
        pygame.draw.circle(s, (255, 253, 255, 240),
                           (int(pts[-1][0]), int(pts[-1][1])), max(1, int(S * 0.015)))
    return s


def build_bow(S=260, col=(255, 124, 176)):
    """缎面蝴蝶结：两翼 + 结心 + 两条飘带"""
    s = pygame.Surface((S, S), pygame.SRCALPHA)
    c = S * 0.5

    def loop(w, h, ang, tf, seed):
        tmp = pygame.Surface((int(w * 1.8), int(h * 2.0)), pygame.SRCALPHA)
        cx, cy = tmp.get_width() * 0.5, tmp.get_height() * 0.5
        rect = pygame.Rect(int(cx - w * 0.5), int(cy - h * 0.5), max(3, int(w)), max(3, int(h)))
        pygame.draw.ellipse(tmp, mul(col, 0.80), rect.inflate(int(w * 0.05), int(h * 0.07)))
        pygame.draw.ellipse(tmp, mul(col, 1.02), rect)
        _sheen(tmp, rect.inflate(-int(w * 0.06), -int(h * 0.08)), (255, 246, 252),
               190, -0.26, -0.34)
        pygame.draw.ellipse(tmp, mul(col, 0.88, ) if False else (mul(col, 0.88)),
                            rect.inflate(-int(w * 0.50), -int(h * 0.62)),
                            max(1, int(h * 0.07)))
        pygame.draw.ellipse(tmp, mul(col, 0.96),
                            rect.inflate(-int(w * 0.56), -int(h * 0.68)))
        pygame.draw.ellipse(tmp, (255, 242, 250, 210), rect, max(1, int(S * 0.006)))
        return pygame.transform.rotate(tmp, ang)

    for (w, h, ang, dx, dy, tf, sd) in (
            (S * 0.44, S * 0.30, 16, -0.210, -0.080, 1.0, 1),
            (S * 0.44, S * 0.30, -16, 0.210, -0.080, 1.0, 2)):
        sp = loop(w, h, ang, tf, sd)
        s.blit(sp, (int(c + S * dx - sp.get_width() / 2),
                    int(c + S * dy - sp.get_height() / 2)))
    for sgn in (-1, 1):
        pts = [(c + sgn * S * 0.03, c + S * 0.03),
               (c + sgn * S * 0.16, c + S * 0.30),
               (c + sgn * S * 0.11, c + S * 0.46),
               (c + sgn * S * 0.00, c + S * 0.34)]
        draw_poly(s, pts, mul(col, 0.98))
        g = radial_gradient(int(S * 0.30), (255, 246, 252, 150), 1.8, res=48)
        g = pygame.transform.smoothscale(g, (int(S * 0.30), int(S * 0.30)))
        s.blit(g, (int(c + sgn * S * 0.02 - S * 0.15), int(c + S * 0.10)))
    pygame.draw.ellipse(s, mul(col, 0.78),
                        (int(c - S * 0.070), int(c - S * 0.085), int(S * 0.14), int(S * 0.19)))
    pygame.draw.ellipse(s, mul(col, 1.04),
                        (int(c - S * 0.056), int(c - S * 0.074), int(S * 0.112), int(S * 0.17)))
    pygame.draw.ellipse(s, (255, 250, 253, 165),
                        (int(c - S * 0.034), int(c - S * 0.052), int(S * 0.036), int(S * 0.076)))
    return s


def build_rose(S=220, col=(255, 116, 168)):
    """裱花玫瑰（参考图那种粉色玫瑰）：三层花瓣 + 卷心"""
    s = pygame.Surface((S, S), pygame.SRCALPHA)
    c = S * 0.5
    for (n, rad, pr, ph) in ((7, S * 0.285, S * 0.190, 0.0),
                             (6, S * 0.195, S * 0.150, 0.5),
                             (5, S * 0.105, S * 0.105, 0.2)):
        for k in range(n):
            a = -math.pi / 2 + (k + ph) / n * TAU
            px = c + math.cos(a) * rad
            py = c + math.sin(a) * rad * 0.9
            light = 0.45 + 0.55 * max(0.0, math.cos(a + 2.5))
            tmp = pygame.Surface((int(pr * 2.7), int(pr * 2.7)), pygame.SRCALPHA)
            ww, hh = pr * 2.3, pr * 1.85
            rect = pygame.Rect(0, 0, max(2, int(ww)), max(2, int(hh)))
            pygame.draw.ellipse(tmp, mul(col, 0.86 + 0.10 * light), rect)
            _sheen(tmp, rect, (255, 236, 246), 170, -0.28, -0.36)
            pygame.draw.ellipse(tmp, mul(col, 0.72 + 0.10 * light), rect, max(1, int(pr * 0.10)))
            rot = pygame.transform.rotate(tmp, -math.degrees(a) + 90)
            s.blit(rot, (int(px - rot.get_width() / 2), int(py - rot.get_height() / 2)))
    for k in range(5):
        a = -math.pi / 2 + k * TAU / 5 + 0.35
        px, py = c + math.cos(a) * S * 0.030, c + math.sin(a) * S * 0.030 * 0.9
        pr = S * 0.062
        pygame.draw.circle(s, mul(col, 0.90), (int(px), int(py)), int(pr))
        pygame.draw.circle(s, mul(col, 1.08), (int(px - pr * 0.22), int(py - pr * 0.26)), int(pr * 0.62))
        pygame.draw.circle(s, (255, 244, 249), (int(px - pr * 0.34), int(py - pr * 0.40)),
                           max(1, int(pr * 0.26)))
    sp = []
    for i in range(24):
        f = i / 23.0
        ang = f * TAU * 1.30
        rr = S * 0.056 * (1.0 - f * 0.80)
        sp.append((c + math.cos(ang) * rr - S * 0.004,
                   c + math.sin(ang) * rr * 0.9 - S * 0.004))
    try:
        pygame.draw.aalines(s, rgba(mul(col, 0.74), 170), False, sp)
    except ValueError:
        pass
    pygame.draw.circle(s, (255, 250, 253), (int(c - S * 0.018), int(c - S * 0.020)),
                       max(2, int(S * 0.020)))
    return s


def build_blossom(S=120, tint=(247, 138, 178)):
    """粉色奶油小花（五瓣，小尺寸也清晰）"""
    s = pygame.Surface((S, S), pygame.SRCALPHA)
    c = S / 2
    R = S * 0.40

    def mix(col, f):
        return (max(0, min(255, int(col[0] * f))), max(0, min(255, int(col[1] * f))),
                max(0, min(255, int(col[2] * f))))

    for k in range(5):
        a = -math.pi / 2 + k * TAU / 5
        px, py = c + math.cos(a) * R * 0.44, c + math.sin(a) * R * 0.44
        pr = R * 0.56
        pygame.draw.circle(s, mix(tint, 0.80), (int(px), int(py + R * 0.12)), int(pr))
        pygame.draw.circle(s, tint, (int(px), int(py)), int(pr))
        pygame.draw.circle(s, mix(tint, 1.14), (int(px - pr * 0.20), int(py - pr * 0.24)), int(pr * 0.70))
    pygame.draw.circle(s, mix(tint, 0.94), (int(c), int(c)), int(R * 0.44))
    pygame.draw.circle(s, (255, 236, 244), (int(c - R * 0.10), int(c - R * 0.14)), int(R * 0.24))
    pygame.draw.circle(s, (255, 255, 255), (int(c - R * 0.16), int(c - R * 0.20)), max(1, int(R * 0.10)))
    return s


def build_ros_ette(S=120):
    """奶油裱花卷：厚奶油挤出的螺旋花，带柔和光影"""
    s = pygame.Surface((S, S), pygame.SRCALPHA)
    c = S / 2
    # 外圈花瓣（6 瓣，错落）
    for k in range(6):
        a = -math.pi / 2 + k * TAU / 6
        px = c + math.cos(a) * S * 0.19
        py = c + math.sin(a) * S * 0.15
        r = S * 0.155
        pygame.draw.circle(s, (206, 178, 190), (int(px), int(py + S * 0.045)), int(r))
        pygame.draw.circle(s, (244, 232, 232), (int(px), int(py)), int(r))
        pygame.draw.circle(s, (254, 246, 242), (int(px - r * 0.10), int(py - r * 0.12)), int(r * 0.86))
        pygame.draw.circle(s, (255, 252, 248), (int(px - r * 0.34), int(py - r * 0.40)), int(r * 0.30))
    # 中心螺旋
    pygame.draw.circle(s, (208, 180, 192), (int(c), int(c + S * 0.04)), int(S * 0.20))
    pygame.draw.circle(s, (250, 241, 236), (int(c), int(c)), int(S * 0.19))
    pygame.draw.circle(s, (255, 253, 250), (int(c - S * 0.03), int(c - S * 0.04)), int(S * 0.12))
    for k in range(24):
        f = k / 24.0
        ang = f * TAU * 1.6
        rr = S * 0.15 * (1.0 - f * 0.85)
        x, y = c + math.cos(ang) * rr, c + math.sin(ang) * rr
        pygame.draw.circle(s, (238, 224, 228), (int(x), int(y)), max(1, int(S * 0.012)))
    return s


def build_icing_texture(w=1400, h=620):
    """奶油布面：奶白底 + 天空蓝/樱粉/薄荷/奶黄柔光块 + 抹刀痕 + 糖霜"""
    s = pygame.Surface((w, h), pygame.SRCALPHA)
    for y in range(h):
        f = y / (h - 1)
        c = _ICING[int(f * (len(_ICING) - 1) * 0.999)]
        pygame.draw.line(s, (c[0], c[1], c[2], 255), (0, y), (w - 1, y))
    rnd = random.Random(17)
    for i in range(16):
        rad = rnd.randint(int(h * 0.55), int(h * 1.30))
        col = rnd.choice([(126, 196, 244), (250, 158, 196), (168, 226, 164),
                          (252, 224, 150), (196, 176, 250), (248, 190, 222),
                          (160, 208, 246), (255, 252, 248)])
        a = rnd.randint(210, 240) if col != (255, 252, 248) else rnd.randint(170, 220)
        g = radial_gradient(rad, (col[0], col[1], col[2], a), 1.9, res=72)
        s.blit(g, (rnd.randint(-rad // 2, w - rad // 2), rnd.randint(-rad // 2, h - rad // 2)))
    # 抹刀痕（极淡，只留一点手作感）
    lay = pygame.Surface((w, h), pygame.SRCALPHA)
    for i2 in range(7):
        y0 = h * (i2 / 7) + rnd.uniform(-6, 6)
        for x in range(0, w, 6):
            yy = y0 + math.sin(x / w * TAU * 1.4 + i2) * h * 0.020
            pygame.draw.line(lay, (255, 255, 252, 26), (x, yy), (x + 6, yy + 1), 2)
    s.blit(soft_blur(lay, 10), (0, 0))
    # 糖霜亮点
    for i in range(190):
        x, y = rnd.randint(0, w - 1), rnd.randint(0, h - 1)
        r = rnd.randint(1, 3)
        pygame.draw.circle(s, (255, 255, 255, rnd.randint(70, 150)), (x, y), r)
    # 顶部偏亮、底部偏冷暗
    tint = pygame.Surface((w, h), pygame.SRCALPHA)
    for y in range(h):
        f = y / (h - 1)
        pygame.draw.line(tint, (176, 148, 172, int(44 * f)), (0, y), (w - 1, y))
        pygame.draw.line(tint, (255, 255, 255, int(60 * (1 - f) ** 2)), (0, y), (w - 1, y))
    s.blit(tint, (0, 0))
    # 斜向柔光（用大圆光叠加，避免条纹）
    for k in range(3):
        rad = int(h * 1.15)
        g = radial_gradient(rad, (255, 253, 250, 120), 2.0, res=80)
        cx = int(w * (0.30 + 0.24 * k))
        s.blit(g, (cx - rad // 2, int(h * 0.5) - rad // 2))
    return s


def _top_col(f):
    f = clamp(f, 0, 0.999)
    i = int(f * (len(_TOP) - 1))
    u = f * (len(_TOP) - 1) - i
    a, b = _TOP[i], _TOP[min(i + 1, len(_TOP) - 1)]
    return (int(a[0] + (b[0] - a[0]) * u), int(a[1] + (b[1] - a[1]) * u),
            int(a[2] + (b[2] - a[2]) * u))


_FRONT_A = 5.58            # 正面朝向的绕轴角度
_FKIND = {0: ("bow", "rose", "heart", "rose", "bfly", "rose", "rose"),
          1: ("bfly", "rose", "heart", "rose", "bow", "rose", "rose")}
_FSZ = {0: {"bow": 0.52, "rose": 0.30, "heart": 0.17, "bfly": 0.48},
        1: {"bow": 0.42, "rose": 0.34, "heart": 0.16, "bfly": 0.60}}


def _gap(a, b):
    """两个角度的圆周最短距离"""
    return abs(((a - b + math.pi) % TAU) - math.pi)


def _mk_features(seed=7):
    """两层侧壁装饰：绕一圈随机分布；上下两层错开，不在同一条竖线上"""
    rnd = random.Random(seed)
    out = [[], []]
    n = 7
    slot = TAU / n

    def place(ti, lower, placed):
        base_fr = 0.46 if ti == 0 else 0.56
        kinds = list(_FKIND[ti])
        rest = kinds[1:]
        rnd.shuffle(rest)
        kinds = [kinds[0]] + rest
        off = 0.0 if ti == 0 else 0.5        # 上层整体错开半格
        res = []
        for k in range(n):
            base = _FRONT_A + (k + off) * slot
            ang = None
            for j in (0.0, 0.10, -0.10, 0.18, -0.18, 0.26, -0.26):
                cand = (base + j) % TAU
                if all(_gap(cand, p) >= 0.42 for p in placed) and \
                   all(_gap(cand, o[0]) >= 0.30 for o in lower):
                    ang = cand
                    break
            if ang is None:
                ang = base % TAU
            placed.append(ang)
            fr = min(0.86, max(0.32, base_fr + rnd.uniform(-0.12, 0.28)))
            sz = _FSZ[ti][kinds[k]] * rnd.uniform(0.86, 1.14)
            res.append((ang, fr, kinds[k], sz))
        return res

    out[0] = place(0, [], [])
    out[1] = place(1, out[0], [])
    return out


FEATURES = _mk_features(7)

# 顶面立体装饰（插在奶油里）：(x, z, 种类, 尺寸)，与水果/蜡烛一起做深度排序
TOP_FEATURES = [
    (-0.62, -0.52, "rose", 0.34),
    (0.58, -0.36, "heart", 0.26),
]


class Cake:
    """奶油水果蛋糕：奶白釉面 + 淋边奶油 + 草莓蓝莓柑橘猕猴桃"""

    def __init__(self):
        self.tex = build_icing_texture()
        self.wmask = pygame.Surface((int(W * CS), int(H * CS)), pygame.SRCALPHA)
        st = pygame.Surface((96, 96), pygame.SRCALPHA)
        for x in range(96):
            fx = x / 95
            f = 0.90 + 0.14 * math.exp(-((fx - 0.26) / 0.70) ** 2)
            for y in range(96):
                fy = y / 95
                g = max(0, min(255, int(255 * min(1.0, f * (1.06 - 0.12 * fy)))))
                st.set_at((x, y), (g, int(g * 0.94), int(g * 0.96), 255))
        self.shade_strip = st
        self.flame_xy = (CX, 0)
        self.flame_k = 100
        self.rosette = build_ros_ette()
        self.blossom = [build_blossom(120, (247, 138, 178)),
                        build_blossom(120, (255, 190, 128)),
                        build_blossom(120, (176, 196, 246))]
        self.pearl = _sphere(26, (250, 244, 240), exp=40, amb=0.55, spec_amt=0.7)
        self.heart = build_heart(230, (255, 118, 158))
        self._fsc = {}
        self.bfly_dark = None
        self.bfly = build_butterfly(320, (255, 104, 160), (168, 136, 240))
        self.bfly_dark = self.bfly.copy()
        self.bfly_dark.fill((158, 92, 138, 255), None, pygame.BLEND_RGBA_MULT)
        self.bow = build_bow(260, (255, 132, 180))
        self.rose = build_rose(220, (255, 126, 174))
        self._shc = {}
        rnd = random.Random(21)
        kinds = ["straw", "blue", "rasp", "kiwi", "orange", "cherry"]
        self.fruits = []
        # 每层顶面水果 + 盘面水果
        tiers = [(TIERS[1][1], TIERS[1][3], 5), (TIERS[0][1], TIERS[0][3], 9)]
        for ti, (rr, ytop, n) in enumerate(tiers):
            for i in range(n):
                a = (i / n) * TAU + 0.22 + ti * 0.5
                f = 0.80 if ti == 0 else 0.84
                kind = kinds[(i + ti * 2) % len(kinds)]
                size = (0.168 + 0.008 * ((i * 7) % 3)) * (1.0 if ti == 0 else 1.10)
                self.fruits.append((rr * f * math.cos(a), ytop + 0.055,
                                    rr * f * math.sin(a), kind, size, rnd.uniform(0, 1)))
            # 内圈点缀

        for i in range(6):
            a = i / 6 * TAU + 0.8
            r0 = TIERS[1][1] * 0.30
            self.fruits.append((r0 * math.cos(a), TIERS[1][3] + 0.05,
                                r0 * math.sin(a),
                                ["straw", "blue", "rasp"][i % 3], rnd.uniform(0.10, 0.12), 0))
        for i in range(7):
            a = i / 7 * TAU + 0.3
            self.fruits.append((TIERS[0][0] * 1.12 * math.cos(a), -0.01,
                                TIERS[0][0] * 1.12 * math.sin(a),
                                kinds[i % len(kinds)], 0.10, 0))
        self.spr = []

    # ------------------------------------------------ 侧壁遮罩 + 纹理
    def wall(self, surf, ti, rb, rt, y0, y1, cam, t, quads=None):
        n = 80
        quads = []
        for i in range(n):
            a0, a1 = i / n * TAU, (i + 1) / n * TAU
            am = (a0 + a1) * 0.5
            if rot_yaw(math.cos(am), math.sin(am))[1] > 0.03:
                continue
            ra = (rb + 0.008) * (1.0 + 0.006 * math.sin(a0 * 3 + t * 0.5))
            r2 = (rt + 0.034) * (1.0 + 0.006 * math.sin(a0 * 3 + t * 0.5))
            p0 = project(ra * math.cos(a0), y0 - 0.006, ra * math.sin(a0), cam)
            p1 = project(ra * math.cos(a1), y0 - 0.006, ra * math.sin(a1), cam)
            q1 = project(r2 * math.cos(a1), y1 + 0.004, r2 * math.sin(a1), cam)
            q0 = project(r2 * math.cos(a0), y1 + 0.004, r2 * math.sin(a0), cam)
            quads.append([(p0[0], p0[1]), (p1[0], p1[1]), (q1[0], q1[1]), (q0[0], q0[1])])
        if not quads:
            return
        xs = [pt[0] for quad in quads for pt in quad]
        ys = [pt[1] for quad in quads for pt in quad]
        bx0, bx1 = int(min(xs)) - 2, int(max(xs)) + 3
        by0, by1 = int(min(ys)) - 2, int(max(ys)) + 3
        bbw, bbh = max(8, bx1 - bx0), max(8, by1 - by0)

        mask = self.wmask
        mask.fill((0, 0, 0, 0))
        for quad in quads:
            pts = [(int(x) - bx0, int(y) - by0) for x, y in quad]
            pygame.draw.polygon(mask, (255, 255, 255, 255), pts)
            pygame.draw.polygon(mask, (255, 255, 255, 255),
                                [(x + 1, y) for x, y in pts])

        tw_, th_ = self.tex.get_size()
        sw, sh = int(tw_ * 0.94), int(th_ * 0.58)
        ox = int((0.42 + ti * 0.16) * (tw_ - sw))
        oy = int((0.36 + ti * 0.10) * (th_ - sh))
        shade = pygame.transform.smoothscale(self.shade_strip, (bbw, bbh))
        mask.blit(shade, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
        piece = self.tex.subsurface((ox, oy, sw, sh)).copy()
        piece = pygame.transform.smoothscale(piece, (bbw, bbh))
        piece.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
        surf.blit(piece, (bx0, by0))
        # 轮廓柔光（遮住侧壁直边，做出玻璃般的亮边）
        rw = max(10, int(bbw * 0.16))
        strip = pygame.Surface((rw, bbh), pygame.SRCALPHA)
        for xx in range(rw):
            a = int(96 * (1.0 - xx / rw) ** 2.0)
            strip.fill((255, 253, 250, a), (xx, 0, 1, bbh))
        pass
        try:
            line = [(int(x), int(y)) for x, y in
                    [quads[0][0]] + [quad[2] for quad in quads] + [quads[-1][1]]]
            pygame.draw.aalines(surf, (232, 210, 214, 150), False, line)
        except Exception:
            pass
        # 侧壁底部轻微暖光
        cxp = project(0, lerp(y0, y1, 0.35), 0, cam)
        gl = radial_add(int(140 * cxp[3] / 300), (70, 40, 34), 2.2, res=84)
        surf.blit(gl, (int(cxp[0]) - gl.get_width() // 2,
                       int(cxp[1]) - gl.get_height() // 2),
                  special_flags=pygame.BLEND_RGB_ADD)

    # ------------------------------------------------ 淋边奶油
    def drips(self, surf, rt, y1, cam, ti, t, seed=1):
        rnd = random.Random(100 + ti)
        n = 9
        for i in range(n):
            a = (i / n) * TAU + seed * 0.4
            if rot_yaw(math.cos(a), math.sin(a))[1] > 0.02:
                continue
            q = project(rt * math.cos(a), y1 + 0.006, rt * math.sin(a), cam)
            k = q[3]
            ln = rnd.uniform(0.040, 0.080) * k
            wpx = rnd.uniform(0.028, 0.042) * k
            x, y = q[0], q[1]
            col = (253, 244, 236, 255)
            poly = [(x - wpx, y - 2), (x - wpx * 0.75, y + ln * 0.72),
                    (x, y + ln), (x + wpx * 0.75, y + ln * 0.72), (x + wpx, y - 2)]
            try:
                pygame.draw.polygon(surf, col, poly)
                pygame.draw.circle(surf, col, (int(x), int(y + ln)), int(wpx * 0.95))
                sh_poly = [(px + wpx * 0.55, py) for px, py in poly]
                lay = pygame.Surface((int(wpx * 3) + 4, int(ln) + 8), pygame.SRCALPHA)
                for i in range(int(wpx), 0, -1):
                    pygame.draw.line(lay, (208, 178, 190, int(26 + i * 4)),
                                     (int(wpx * 1.5) - i, 0), (int(wpx * 1.5) - i, int(ln)))
                surf.blit(lay, (int(x + wpx * 0.15), int(y)))
                pygame.draw.aaline(surf, (255, 255, 250),
                                   (x - wpx * 0.85, y - 1), (x - wpx * 0.6, y + ln * 0.55))
            except Exception:
                pass

    def rosettes(self, surf, rt, y1, cam, t, n=9, scale=1.0):
        for i in range(n):
            a = (i / n) * TAU + 0.35
            if rot_yaw(math.cos(a), math.sin(a))[1] > 0.06:
                continue
            q = project(rt * 0.96 * math.cos(a), y1 + 0.03, rt * 0.96 * math.sin(a), cam)
            sz = int(0.062 * q[3] * scale)
            if sz < 6:
                continue
            sp = pygame.transform.smoothscale(self.rosette, (sz * 2, sz * 2))
            surf.blit(sp, (int(q[0] - sz), int(q[1] - sz * 0.8)))

    def draw_fruit(self, surf, x, y, z, kind, size, ph, cam, t):
        q = project(x, y, z, cam)
        sz = int(size * 2 * q[3] * 1.02)
        if sz < 7:
            return
        sz = int(sz * _FSIZE.get(kind, 1.0))
        if sz < 7:
            return
        sp = fruit_sprite(kind, sz)
        # 落在奶油上的软影
        sh = pygame.Surface((int(sz * 1.15), int(sz * 0.42)), pygame.SRCALPHA)
        pygame.draw.ellipse(sh, (128, 92, 118, 44), (0, 0, sh.get_width(), sh.get_height()))
        surf.blit(sh, (int(q[0] - sz * 0.575), int(q[1] + sz * 0.30)))
        # 果子背后的小奶油堆（让果子"坐"进奶油里，不遮挡果面）
        mw = int(sz * 0.80)
        mh = int(sz * 0.22)
        if mw > 6 and mh > 3:
            mound = pygame.Surface((mw, mh), pygame.SRCALPHA)
            for yy in range(mh):
                f = yy / max(1, mh - 1)
                wdt = int(mw * 0.5 * math.sqrt(max(0.0, 1.0 - ((f - 0.45) / 0.95) ** 2)))
                if wdt <= 0:
                    continue
                sh_ = 1.0 + 0.05 * (1 - f)
                col = (min(255, int(252 * sh_)), min(255, int(245 * sh_)),
                       min(255, int(238 * sh_)), 255)
                pygame.draw.line(mound, col, (mw // 2 - wdt, yy), (mw // 2 + wdt, yy))
            sh2 = mound.copy()
            sh2.fill((214, 190, 198, 255), special_flags=pygame.BLEND_RGBA_MULT)
            surf.blit(sh2, (int(q[0] - mw / 2), int(q[1] + sz * 0.13)))
            surf.blit(mound, (int(q[0] - mw / 2), int(q[1] + sz * 0.10)))
        surf.blit(sp, (int(q[0] - sz / 2), int(q[1] - sz / 2)))

    # ------------------------------------------------ 主体
    def draw(self, surf, t, cam):
        self.draw_plate(surf, cam, t)
        for ti, (rb, rt, y0, y1, segs, hoff) in enumerate(TIERS):
            # 顶面：奶白 + 天空蓝 / 樱粉 / 薄荷（春日油画风）
            yy = y1 + 0.012
            rim_r = rt + 0.022
            disc_all = []
            for i in range(60):
                a = i / 60 * TAU
                q = project(rim_r * math.cos(a), yy, rim_r * math.sin(a), cam)
                disc_all.append((q[0], q[1]))
            try:
                pygame.draw.polygon(surf, (255, 252, 246), disc_all)
            except Exception:
                pass
            N = 16
            for k in range(N):
                f = k / (N - 1)
                rr = (rt + 0.020) * (1.0 - 0.90 * f)
                col = _top_col(f)
                disc = []
                for i in range(48):
                    a = i / 48 * TAU
                    q = project(rr * math.cos(a), yy + 0.001 * k, rr * math.sin(a), cam)
                    disc.append((q[0], q[1]))
                try:
                    pygame.draw.polygon(surf, col, disc)
                except Exception:
                    pass
            # 顶面奶油小凸起（裱花挤花点）
            for i in range(9):
                a = i / 9 * TAU + 0.4
                if rot_yaw(math.cos(a), math.sin(a))[1] > 0.02:
                    continue
                q = project((rt + 0.020) * math.cos(a), yy + 0.006, (rt + 0.020) * math.sin(a), cam)
                sz = int(0.055 * q[3])
                if sz < 4:
                    continue
                pygame.draw.circle(surf, (252, 244, 236), (int(q[0]), int(q[1] + sz * 0.25)), sz)
                pygame.draw.circle(surf, (255, 252, 246), (int(q[0]), int(q[1])), sz)
                pygame.draw.circle(surf, (255, 255, 255), (int(q[0] - sz * 0.3), int(q[1] - sz * 0.35)), max(1, int(sz * 0.35)))
            # 蜡烛暖光落在奶油上
            cc = project(CANDLE_XZ[0], yy + 0.01, CANDLE_XZ[1], cam)
            gw = radial_add(int(0.32 * cc[3]), (34, 20, 10), 2.0, res=96)
            surf.blit(gw, (int(cc[0]) - gw.get_width() // 2,
                           int(cc[1]) - gw.get_height() // 2),
                      special_flags=pygame.BLEND_RGB_ADD)

            self.wall(surf, ti, rb, rt, y0, y1, cam, t)
            self.wall_decor(surf, ti, rt, y0, y1, cam, t)
            self.wall_features(surf, ti, rt, y0, y1, cam, t)
            self.drips(surf, rt, y1, cam, ti, t)
            self.bottom_border(surf, ti, rb, y0, y1, cam, t)
            self.draw_cream_curtain(surf, ti, rt, y1, cam, t)
            pass  # lace off

            self.decor(surf, ti, rt, y1, cam, t)

            # 顶面水果（按深度排序；最顶层把蜡烛与顶饰一起参与排序，旋转遮挡才正确）
            ring = [f for f in self.fruits if abs(f[1] - (y1 + 0.055)) < 0.02]
            ring.sort(key=lambda f: rot_yaw(f[0], f[2])[1])
            if ti == len(TIERS) - 1:
                items = [(cam_depth(f[0], f[1], f[2], cam), 0, f) for f in ring]
                items += [(cam_depth(o[0], y1 + 0.02, o[1], cam), 1, o) for o in TOP_FEATURES]
                items.append((cam_depth(CANDLE_XZ[0], CANDLE_Y0 + 0.02,
                                        CANDLE_XZ[1], cam), 2, None))
                items.sort(key=lambda it: -it[0])   # 远的先画
                for _dep, kd, obj in items:
                    if kd == 0:
                        self.draw_fruit(surf, obj[0], obj[1], obj[2], obj[3],
                                         obj[4], obj[5], cam, t)
                    elif kd == 1:
                        self.top_decor(surf, obj, y1 + 0.014, cam, t)
                    else:
                        self.draw_candle(surf, t, cam)
            else:
                for (fx, fy, fz, kind, size, ph) in ring:
                    self.draw_fruit(surf, fx, fy, fz, kind, size, ph, cam, t)

    def draw_plate(self, surf, cam, t):
        rb0 = TIERS[0][0]
        y = -0.02
        for b, (rr, col, dy) in enumerate((
                (rb0 * 1.15, (206, 200, 232, 255), -0.030),
                (rb0 * 1.11, (246, 242, 250, 255), -0.016),
                (rb0 * 0.95, (252, 249, 252, 255), 0.004))):
            disc = []
            for i in range(64):
                a = i / 64 * TAU
                q = project(rr * math.cos(a), y + dy - 0.05, rr * math.sin(a), cam)
                disc.append((q[0], q[1]))
            try:
                pygame.draw.polygon(surf, col, disc)
            except Exception:
                pass
        arc = []
        for i in range(58):
            a = math.pi * (0.03 + 0.94 * i / 57)
            q = project(rb0 * 1.15 * math.cos(a), y - 0.078, rb0 * 1.15 * math.sin(a), cam)
            arc.append((q[0], q[1]))
        try:
            pygame.draw.lines(surf, (255, 252, 248, 200), False, arc, 2)
        except ValueError:
            pass
        # 盘面水果
        plate = [f for f in self.fruits if f[1] < 0.01]
        plate.sort(key=lambda f: rot_yaw(f[0], f[2])[1])
        for (fx, fy, fz, kind, size, ph) in plate:
            self.draw_fruit(surf, fx, fy, fz, kind, size, ph, cam, t)

    def lace(self, surf, rt, y1, cam, ti, t):
        """奶油蕾丝：沿边缘挤出一圈小圆鼓"""
        n = 20
        for i in range(n):
            a = (i / n) * TAU + 0.15 + ti * 0.3
            if rot_yaw(math.cos(a), math.sin(a))[1] > 0.02:
                continue
            q = project((rt + 0.008) * math.cos(a), y1 + 0.002, (rt + 0.008) * math.sin(a), cam)
            r = int(0.026 * q[3])
            if r < 4:
                continue
            pygame.draw.circle(surf, (226, 202, 208), (int(q[0]), int(q[1] + r * 0.45)), r)
            pygame.draw.circle(surf, (253, 246, 238), (int(q[0]), int(q[1] + r * 0.20)), r)
            pygame.draw.circle(surf, (255, 253, 248), (int(q[0] - r * 0.22), int(q[1] - r * 0.05)), int(r * 0.62))

    # ------------------------------------------------ 侧壁装饰
    def wall_decor(self, surf, ti, rt, y0, y1, cam, t):
        """侧壁装饰：彩色糖屑星星 + 奶油裱花卷 + 小花（参考星空糖屑蛋糕）"""
        rnd = random.Random(77 + ti * 13)
        chips = [(255, 112, 172), (255, 198, 64), (104, 198, 250), (130, 238, 190),
                 (184, 148, 252), (255, 150, 118)]
        # 1) 彩色糖屑（星片 + 圆点）
        for i in range(72):
            a = rnd.uniform(0, TAU)
            fr = 0.05 + 0.90 * rnd.random()
            if rot_yaw(math.cos(a), math.sin(a))[1] > 0.02:
                continue
            q = project((rt + 0.010) * math.cos(a), lerp(y0, y1, fr),
                        (rt + 0.010) * math.sin(a), cam)
            r = (0.013 + 0.017 * rnd.random()) * q[3]
            if r < 1.6:
                continue
            col = chips[i % len(chips)]
            kind = i % 3
            rot = a * 2.0 + 0.6
            if kind == 0:
                pts = []
                for k in range(8):
                    rr = r * (1.35 if k % 2 == 0 else 0.55)
                    ang = rot + k * TAU / 8
                    pts.append((q[0] + math.cos(ang) * rr, q[1] + math.sin(ang) * rr))
                pygame.draw.polygon(surf, col, pts)
            elif kind == 1:
                pygame.draw.circle(surf, col, (int(q[0]), int(q[1])), max(1, int(r)))
                pygame.draw.circle(surf, (255, 255, 255), (int(q[0] - r * 0.3), int(q[1] - r * 0.34)),
                                   max(1, int(r * 0.34)))
            else:
                hh = int(r * 1.1) | 1
                pygame.draw.ellipse(surf, col, (int(q[0] - hh * 0.6), int(q[1] - hh * 0.6), hh, hh))

    # ------------------------------------------------ 立体装饰（蝴蝶结/玫瑰/爱心/蝴蝶）
    def _pad(self, surf, q, w, hf=0.55, tint=(253, 247, 242)):
        """一团柔光奶油托：装饰"坐"进奶油里"""
        mw, mh = max(6, int(w * 1.06)), max(4, int(w * hf))
        pad = pygame.Surface((mw, mh), pygame.SRCALPHA)
        g = radial_gradient(max(mw, mh), (tint[0], tint[1], tint[2], 255), 1.9, res=72)
        pad.blit(pygame.transform.smoothscale(g, (mw, int(mh * 0.86))), (0, 0))
        pygame.draw.ellipse(pad, (206, 178, 190, 70), (0, int(mh * 0.30), mw, int(mh * 0.62)))
        surf.blit(pad, (int(q[0] - mw / 2), int(q[1] - mh * 0.20)))

    def _sil(self, spr, w):
        """装饰的柔和轮廓影（先缩再放大当作模糊，按尺寸缓存）"""
        key = (id(spr), int(w))
        got = self._shc.get(key)
        if got is None:
            if len(self._shc) > 260:
                self._shc.clear()
            n = max(6, int(w * 0.30))
            sil = pygame.transform.smoothscale(spr, (n, n))
            sil.fill((132, 102, 138, 255), special_flags=pygame.BLEND_RGBA_MULT)
            got = pygame.transform.smoothscale(sil, (max(4, int(w)), max(4, int(w))))
            self._shc[key] = got
        return got

    def _shadow(self, surf, q, w, hf=0.34, a=40):
        sh = pygame.Surface((max(4, int(w)), max(3, int(w * hf))), pygame.SRCALPHA)
        pygame.draw.ellipse(sh, (148, 118, 150, a), (0, 0, sh.get_width(), sh.get_height()))
        surf.blit(sh, (int(q[0] - sh.get_width() / 2), int(q[1] + w * 0.14)))

    def _fs(self, spr, key, w, h):
        """缩放结果缓存（装饰按帧重算尺寸，避免每帧 smoothscale）"""
        c = self._fsc
        k = (key, w, h)
        v = c.get(k)
        if v is None:
            if len(c) > 260:
                c.clear()
            v = pygame.transform.smoothscale(spr, (max(4, w), max(4, h)))
            c[k] = v
        return v

    def wall_features(self, surf, ti, rt, y0, y1, cam, t):
        feats = FEATURES[ti] if ti < len(FEATURES) else []
        for (a0, fr, kind, sz) in feats:
            ca, sa = math.cos(a0), math.sin(a0)
            dep = rot_yaw(ca, sa)[1]
            if dep > -0.16:                      # 只看前半圈
                continue
            yy = lerp(y0, y1, fr)
            q = project((rt + 0.018) * ca, yy, (rt + 0.018) * sa, cam)
            hpx = int(sz * q[3])
            if hpx < 8:
                continue
            sq = 0.55 + 0.45 * min(1.0, -dep / 0.50)
            fa = min(1.0, (-dep - 0.16) / 0.24)   # 转到侧面淡出
            # 贴边时把贴片往蛋糕中轴挪回一点，别半截悬在轮廓外
            qcx = project(0.0, yy, 0.0, cam)[0]
            sgn = 1.0 if q[0] < qcx else -1.0
            qx = q[0] + sgn * hpx * 0.5 * (1.0 - sq) * 2.0
            wpx = int(hpx * sq)
            q2 = (qx, q[1], q[2], q[3])
            if kind == "bow":
                sk = self._sil(self.bow, hpx)
                sk.set_alpha(int(58 * fa))
                surf.blit(sk, (int(qx - wpx * 0.46), int(q[1] - hpx * 0.40)))
                sp = self._fs(self.bow, "bow", wpx, hpx)
                sp.set_alpha(int(255 * fa))
                surf.blit(sp, (int(qx - wpx * 0.5), int(q[1] - hpx * 0.46)))
            elif kind == "rose":
                ww, hh = int(wpx * 1.10), int(hpx * 1.10)
                self._pad(surf, q2, int(wpx * 0.94), 0.60)
                for sd in (-1, 1):
                    lx = qx + sd * ww * 0.50
                    ly = q[1] + hh * 0.10
                    lw, lh = max(3, int(ww * 0.30)), max(2, int(hh * 0.17))
                    ls = pygame.Surface((lw, lh), pygame.SRCALPHA)
                    pygame.draw.ellipse(ls, (236, 244, 232, 235), (0, 0, lw, lh))
                    pygame.draw.ellipse(ls, (252, 253, 250, 210),
                                        (int(lw * 0.18), int(lh * 0.14),
                                         int(lw * 0.62), int(lh * 0.52)))
                    ls.set_alpha(int(255 * fa))
                    surf.blit(pygame.transform.rotate(ls, -18 * sd),
                              (int(lx - lw * 0.5), int(ly - lh * 0.5)))
                sk = self._sil(self.rose, hh)
                sk.set_alpha(int(46 * fa))
                surf.blit(sk, (int(qx - ww * 0.44), int(q[1] - hh * 0.44)))
                sp = self._fs(self.rose, "rose", ww, hh)
                sp.set_alpha(int(255 * fa))
                surf.blit(sp, (int(qx - ww * 0.5), int(q[1] - hh * 0.50)))
            elif kind == "bfly":
                bw, bh = int(wpx * 1.06), int(hpx * 1.00)
                sh = pygame.Surface((max(4, int(bw * 0.46)), max(3, int(bh * 0.11)),
                                     ), pygame.SRCALPHA)
                pygame.draw.ellipse(sh, (120, 92, 132, 56),
                                    (0, 0, sh.get_width(), sh.get_height()))
                sh.set_alpha(int(255 * fa))
                surf.blit(sh, (int(qx - sh.get_width() * 0.5), int(q[1] + bh * 0.18)))
                ow, oh = int(bw * 1.06), int(bh * 0.99)
                ink = self._fs(self.bfly_dark, "ink", ow, oh)
                ink = pygame.transform.rotate(ink, -6 + 3 * math.sin(t * 0.8))
                ink.set_alpha(int(255 * fa))
                surf.blit(ink, (int(qx - ink.get_width() * 0.5),
                                int(q[1] - ink.get_height() * 0.52)))
                sp = self._fs(self.bfly, "bfly", bw, bh)
                sp = pygame.transform.rotate(sp, -6 + 3 * math.sin(t * 0.8))
                sp.set_alpha(int(255 * fa))
                surf.blit(sp, (int(qx - sp.get_width() * 0.5),
                               int(q[1] - sp.get_height() * 0.52)))
            else:
                self._pad(surf, q2, int(wpx * 0.92), 0.52)
                sk = self._sil(self.heart, hpx)
                sk.set_alpha(int(50 * fa))
                surf.blit(sk, (int(qx - wpx * 0.44), int(q[1] - hpx * 0.66)))
                sp = self._fs(self.heart, "heart", wpx, hpx)
                sp.set_alpha(int(255 * fa))
                surf.blit(sp, (int(qx - wpx * 0.5), int(q[1] - hpx * 0.72)))

    def top_decor(self, surf, o, ytop, cam, t):
        """顶面大件装饰：插在奶油上 / 从顶面探出来的蝴蝶"""
        x, z, kind, sz = o
        q = project(x, ytop, z, cam)
        wpx = int(sz * q[3])
        if wpx < 8:
            return
        if kind == "bfly":
            sw = int(wpx * 0.96)
            q0 = q
            sk = self._sil(self.bfly, sw)
            sk.set_alpha(64)
            surf.blit(sk, (int(q0[0] - sw * 0.34), int(q0[1] - sw * 0.42)))
            sh = pygame.Surface((int(sw * 0.30), int(sw * 0.12)), pygame.SRCALPHA)
            pygame.draw.ellipse(sh, (132, 100, 136, 52), (0, 0, sh.get_width(), sh.get_height()))
            surf.blit(sh, (int(q0[0] - sw * 0.14), int(q0[1] + sw * 0.02)))
            q = (q0[0], q0[1] - sw * 0.52)
            sp = pygame.transform.smoothscale(self.bfly, (sw, sw))
            sp = pygame.transform.rotate(sp, -8 + 4 * math.sin(t * 0.7))
            sh = pygame.Surface((int(sw * 0.34), int(sw * 0.13)), pygame.SRCALPHA)
            pygame.draw.ellipse(sh, (138, 108, 140, 46), (0, 0, sh.get_width(), sh.get_height()))
            surf.blit(sh, (int(q[0] - sw * 0.08), int(q[1] + sw * 0.02)))
            surf.blit(sp, (int(q[0] - sp.get_width() * 0.42),
                           int(q[1] - sp.get_height() * 0.74)))
        elif kind == "heart":
            self._pad(surf, q, int(wpx * 0.80), 0.46)
            sk = self._sil(self.heart, wpx)
            sk.set_alpha(52)
            surf.blit(sk, (int(q[0] - wpx * 0.44), int(q[1] - wpx * 0.72)))
            sp = pygame.transform.smoothscale(self.heart, (wpx, wpx))
            surf.blit(sp, (int(q[0] - wpx * 0.5), int(q[1] - wpx * 0.80)))
        else:
            self._pad(surf, q, int(wpx * 0.86), 0.52)
            ww = int(wpx * 1.06)
            sk = self._sil(self.rose, ww)
            sk.set_alpha(46)
            surf.blit(sk, (int(q[0] - ww * 0.44), int(q[1] - ww * 0.56)))
            sp = pygame.transform.smoothscale(self.rose, (ww, ww))
            surf.blit(sp, (int(q[0] - ww * 0.5), int(q[1] - ww * 0.62)))

    def bottom_border(self, surf, ti, rb, y0, y1, cam, t):
        """层底一圈奶油珍珠边"""
        for i in range(22):
            a = (i / 22) * TAU + 0.12 + ti * 0.4
            if rot_yaw(math.cos(a), math.sin(a))[1] > 0.02:
                continue
            q = project((rb + 0.010) * math.cos(a), y0 + 0.014, (rb + 0.010) * math.sin(a), cam)
            r = int(0.023 * q[3])
            if r < 3:
                continue
            pygame.draw.circle(surf, (214, 186, 196), (int(q[0]), int(q[1] + r * 0.42)), r)
            pygame.draw.circle(surf, (250, 241, 235), (int(q[0]), int(q[1] + r * 0.16)), r)
            pygame.draw.circle(surf, (255, 253, 250), (int(q[0] - r * 0.26), int(q[1] - r * 0.10)),
                               max(1, int(r * 0.60)))

    def decor(self, surf, ti, rt, y1, cam, t):
        """奶油挤花边 + 糖珠，围住顶面一圈"""
        for i in range(16):
            a = (i / 16) * TAU + 0.10 + ti * 0.35
            if rot_yaw(math.cos(a), math.sin(a))[1] > 0.02:
                continue
            q = project((rt + 0.030) * math.cos(a), y1 + 0.010, (rt + 0.030) * math.sin(a), cam)
            sz = int(0.058 * q[3])
            if sz < 5:
                continue
            sp = pygame.transform.smoothscale(self.rosette, (sz * 2, int(sz * 1.5)))
            surf.blit(sp, (int(q[0] - sz), int(q[1] - sz * 0.55)))
        for i in range(16):
            a = ((i + 0.5) / 16) * TAU + 0.2
            if rot_yaw(math.cos(a), math.sin(a))[1] > 0.02:
                continue
            q = project((rt + 0.058) * math.cos(a), y1 + 0.012, (rt + 0.058) * math.sin(a), cam)
            sz = int(0.020 * q[3])
            if sz < 3:
                continue
            pygame.draw.circle(surf, (250, 242, 238), (int(q[0]), int(q[1] + sz * 0.35)), sz)
            pygame.draw.circle(surf, (255, 253, 250), (int(q[0] - sz * 0.3), int(q[1] - sz * 0.3)),
                               max(1, int(sz * 0.62)))

    def draw_cream_curtain(self, surf, ti, rt, y1, cam, t, top_off=0.0):
        a0 = CAM["yaw"] - math.pi * 0.5
        n = 120
        top, bot = [], []
        for i in range(n + 1):
            a = a0 - math.pi * 0.5 + math.pi * 1.0 * (i / n)
            r = rt + 0.014
            q = project(r * math.cos(a), y1 + 0.006 + top_off, r * math.sin(a), cam)
            top.append((q[0], q[1]))
            p = (0.5 + 0.5 * math.sin(a * 26.0 + ti * 1.9)) ** 1.6
            d = 0.012 + 0.016 * p + 0.004 * (0.5 + 0.5 * math.sin(a * 7.0 + 0.9))
            e = project(r * math.cos(a), y1 - 0.002 - d, r * math.sin(a), cam)
            bot.append((e[0], e[1]))
        poly = top + bot[::-1]
        try:
            pygame.draw.polygon(surf, (250, 242, 234), poly)
            pygame.draw.aalines(surf, (255, 253, 248), True, poly)
            pygame.draw.aalines(surf, (234, 210, 216), False, bot)
        except ValueError:
            return

    def draw_candle(self, surf, t, cam):
        bx_, bz_ = CANDLE_XZ
        base = project(bx_, CANDLE_Y0, bz_, cam)
        sh = pygame.Surface((int(0.34 * base[3]) | 1, int(0.12 * base[3]) | 1), pygame.SRCALPHA)
        pygame.draw.ellipse(sh, (150, 118, 132, 52), (0, 0, sh.get_width(), sh.get_height()))
        surf.blit(sh, (int(base[0] - sh.get_width() / 2), int(base[1] - sh.get_height() * 0.42)))
        top = project(bx_, CANDLE_Y0 + CANDLE_H, bz_, cam)
        k = base[3]
        w = 0.070 * k
        draw_poly(surf, [(base[0] - w, base[1] + 2), (base[0] + w, base[1] + 2),
                         (top[0] + w * 0.92, top[1]), (top[0] - w * 0.92, top[1])],
                  (254, 244, 224, 255))
        draw_poly(surf, [(base[0] + w * 0.15, base[1] + 2), (base[0] + w, base[1] + 2),
                         (top[0] + w * 0.92, top[1]), (top[0] + w * 0.26, top[1])],
                  (214, 176, 150, 130), aa=False)
        ly = lambda f: base[1] + 2 + (top[1] - base[1]) * f
        for si in range(3):
            f0 = 0.20 + 0.24 * si
            f1 = f0 + 0.10
            col = [(255, 118, 156), (255, 150, 120), (255, 196, 96)][si]
            draw_poly(surf, [(base[0] - w, ly(f0)), (base[0] + w, ly(f0) - 3),
                             (base[0] + w * 0.94, ly(f1) - 3), (base[0] - w * 0.94, ly(f1))],
                      rgba(col, 210), aa=False)
        pygame.draw.line(surf, (255, 255, 246), (base[0] - w * 0.4, base[1] + 2),
                         (top[0] - w * 0.38, top[1]), 2)
        self.flame_xy = ((top[0] + w * 0.0) / VIEW["s"], top[1] / VIEW["s"] - 6)
        self.flame_k = k / VIEW["s"]





def flame_pts(x, ybase, h, w, sway, n=18):
    left, right = [], []
    for i in range(n + 1):
        f = i / n
        yy = ybase - h * f
        wid = w * (1.0 - f) ** 0.55 * (1.0 + 0.18 * math.sin(f * 3.4 + sway))
        sx = x + math.sin(f * 2.4 + sway) * w * 0.55 * f
        left.append((sx - wid, yy))
        right.append((sx + wid, yy))
    return left + right[::-1]


def draw_flame(surf, x, ybase, t, power=1.0, lit=True, alpha=255):
    if not lit:
        for i in range(4):
            yy = ybase - 10 - (i * 9 + (t * 24) % 10)
            draw_dot(surf, x + math.sin(t * 1.4 + i) * 6, yy, 5 + i * 1.4,
                     (210, 200, 210, int(28 * alpha / 255)))
        return
    h = 40 * power
    w = 9 * power
    sway = math.sin(t * 6) * 0.5
    gl = radial_add(int(52 * power), (120, 60, 24), 2.0, res=72)
    surf.blit(gl, (int(x) - gl.get_width() // 2, int(ybase) - gl.get_height() // 2 + 6),
              special_flags=pygame.BLEND_RGB_ADD)
    for (hh, ww, col) in ((1.0, 1.0, (255, 150, 60, 200)),
                          (0.74, 0.62, (255, 210, 110, 220)),
                          (0.42, 0.34, (255, 250, 230, 240))):
        poly = flame_pts(x, ybase, h * hh, w * ww, sway)
        try:
            pygame.draw.polygon(surf, rgba(col, col[3] * alpha // 255), poly)
        except Exception:
            pass
    draw_dot(surf, x, ybase - h * 0.30, w * 0.7, (255, 255, 240, int(200 * alpha / 255)))


class Particle:
    __slots__ = ("x", "y", "vx", "vy", "life", "max_life", "size", "color",
                 "rot", "spin", "kind", "grav", "drag")

    def __init__(self, x, y, vx=0, vy=0, life=1.0, size=6, color=(255, 255, 255),
                 kind="star", spin=0.0, grav=0.0, drag=1.2):
        self.x, self.y, self.vx, self.vy = x, y, vx, vy
        self.life = self.max_life = life
        self.size, self.color, self.kind = size, color, kind
        self.rot = random.uniform(0, TAU)
        self.spin, self.grav, self.drag = spin, grav, drag

    def update(self, dt):
        self.vy += self.grav * dt
        self.vx -= self.vx * self.drag * dt
        self.vy -= self.vy * self.drag * dt
        self.x += self.vx * dt
        self.y += self.vy * dt
        self.rot += self.spin * dt
        self.life -= dt
        if self.kind == "smoke":
            self.size += 24 * dt
        return self.life > 0

    def draw(self, surf):
        f = clamp(self.life / self.max_life, 0.0, 1.0)
        a = (f ** 0.8) * self.color[3]
        s = self.size * (0.5 + 0.5 * f)
        c = rgba(self.color, a)
        if self.kind == "star":
            draw_star(surf, self.x, self.y, s, c, rot=self.rot)
        elif self.kind == "dot":
            draw_dot(surf, self.x, self.y, s * 0.7, c)
        elif self.kind == "spark":
            draw_spark(surf, self.x, self.y, s, c, rot=self.rot)
        elif self.kind == "smoke":
            draw_dot(surf, self.x, self.y, s, rgba((190, 172, 200), a))


class MorphStar:
    __slots__ = ("sx", "sy", "ti", "a", "f", "size", "hue", "delay",
                 "dur", "ax", "bx")

    def __init__(self, sx, sy, ti, a, f, size, hue, delay, dur, ax, bx):
        self.sx, self.sy = sx, sy
        self.ti, self.a, self.f = ti, a, f
        self.size, self.hue, self.delay = size, hue, delay
        self.dur, self.ax, self.bx = dur, ax, bx


# ------------------------------------------------------------------ 主程序
class App:
    def __init__(self, shot=False):
        pygame.mixer.pre_init(44100, -16, 2, 512)
        pygame.init()
        if shot:
            self.canvas = pygame.Surface((W, H))
            self.win = self.canvas
        else:
            self.win = pygame.display.set_mode((int(W * FS), int(H * FS)))
            self.canvas = pygame.Surface((W, H)).convert()
        self.screen = self.canvas
        pygame.display.set_caption("祝你生日快乐 · 水果星空蛋糕")
        self.clock = pygame.time.Clock()

        self.bg = build_background()
        self.aurora = make_aurora_layers()
        self.balloon_sprites = [build_balloon_sprite(c) for c in _BALLOON_COLS]
        self.amb = self.make_ambient()
        rnd2 = random.Random(83)
        self.bigstars = [[rnd2.uniform(-2.7, 2.7), rnd2.uniform(0.2, 3.9), rnd2.uniform(-1.2, 2.2),
                          rnd2.uniform(0, 1), rnd2.uniform(0.03, 0.055),
                          rnd2.uniform(0, TAU), rnd2.uniform(0.3, 0.9)] for _ in range(9)]
        self.silk_tex = build_silk_texture()
        self.wmask = pygame.Surface((int(W * CS), int(H * CS)), pygame.SRCALPHA)
        st = pygame.Surface((96, 96), pygame.SRCALPHA)
        for x in range(96):
            fx = x / 95
            f = 0.52 + 0.48 * (math.sin(math.pi * fx) ** 0.55)
            for y in range(96):
                fy = y / 95
                g = max(0, min(255, int(255 * min(1.04, f * (1.04 - 0.16 * fy)))))
                st.set_at((x, y), (g, int(g * 0.94), int(g * 0.96), 255))
        self.shade_strip = st
        self._bscale = {}
        # 气球按屏幕四角锚定：(屏幕x比例, 屏幕y比例, 半径px, 配色, 相位, 速度)
        self.balloons = [
            (0.115, 0.150, 72, 0, 0.0, 0.7),
            (0.885, 0.135, 68, 1, 0.8, 0.9),
            (0.075, 0.700, 64, 2, 1.9, 0.6),
            (0.925, 0.715, 60, 3, 2.7, 0.8),
            (0.035, 0.430, 44, 4, 3.4, 0.7),
            (0.965, 0.430, 42, 0, 4.6, 0.5),
        ]
        self.bokeh = make_bokeh_sprites()
        self.strip = build_rainbow_strip()
        self.cake = Cake()

        self.title_mask = text_mask("祝你生日快乐", 112, cjk=True, pad=56, kai=True)
        self.title_img = pygame.Surface(self.title_mask.get_size(), pygame.SRCALPHA)
        self.title_rect = self.title_img.get_rect(center=(CX, 402))
        tm = self.title_mask.copy()
        tm.fill((150, 150, 150, 255), special_flags=pygame.BLEND_RGBA_MULT)
        self.title_sh = soft_blur(tm, 9)
        self.title_sh.set_alpha(150)
        self.sheen = build_sheen(self.title_img.get_width(), self.title_img.get_height())
        self.sheen_tmp = pygame.Surface(self.title_img.get_size(), pygame.SRCALPHA)
        self.sub = glow_text("点一下，星屑会把它拼成生日蛋糕", 24, (255, 246, 250),
                             (255, 150, 190), cjk=True, glow_boost=1)
        self.sub_sh = None
        self.hb = glow_text("Happy birthday!", 82, (255, 252, 255), (255, 190, 120),
                            script=True, glow_boost=2)
        self.hint = glow_text("拖动旋转视角 · 点击爆星 · 点蜡烛吹灭", 16, (255, 224, 232),
                              (120, 90, 130), cjk=True, glow_boost=0)
        self.hb_sh = shadow_copy(self.hb)
        self.hint_sh = shadow_copy(self.hint)

        self.stage = "intro"
        self.t = 0.0
        self.gt = 0.0
        self.yaw = CAM["yaw"]
        self.yaw_vel = 0.0
        self.dragging = False
        self.mouse = (W // 2, H // 2)
        self.prev_mouse = self.mouse
        self.particles = []
        self.morphs = []
        self.rings = []
        self.lit = True
        self.flame_power = 1.0
        self.cake_alpha = 0.0
        self.rise = 0.0
        self.music = None
        self.muted = False
        self.orbit = self._make_orbit()
        self.lay = new_layer()
        self.cake_surf = pygame.Surface((int(W * CS), int(H * CS)), pygame.SRCALPHA)
        self.ray_surf = build_rays()
        self.gl_surf = radial_gradient(430, (255, 170, 210, 60), 2.2)
        self.gather_surf = radial_gradient(420, (255, 206, 236, 130), 2.1)
        sh = radial_gradient(320, (30, 4, 26, 165), 2.4)
        self.sh_surf = pygame.transform.smoothscale(sh, (600, 210))
        self.start_yaw = CAM["yaw"]

        try:
            pygame.mixer.init(44100, -16, 2, 512)
            self.music = pygame.mixer.Sound(buffer=synth_song())
            self.music.set_volume(0.55)
        except Exception as e:
            print("音乐初始化失败（画面不受影响）:", e)

        pygame.mouse.set_visible(False)

    def _make_orbit(self):
        rnd = random.Random(19)
        out = []
        for _ in range(30):
            r = rnd.uniform(2.0, 3.1)
            a = rnd.uniform(0, TAU)
            y = rnd.uniform(-0.2, 2.2)
            out.append([r, a, y, rnd.uniform(0.08, 0.2) * rnd.choice([-1, 1]),
                        rnd.uniform(4, 10), rnd.uniform(0, 1), rnd.uniform(0, TAU)])
        return out

    # ------------------------------------------------------ 转场
    def start_morph(self):
        if self.stage != "intro":
            return
        self.stage = "morph"
        self.t = 0.0
        self.cake_alpha = 0.0
        self.rise = 0.0
        self.build_morph()
        if self.music and not self.muted:
            self.music.play(loops=-1)

    def build_morph(self):
        m = self.title_mask
        w, h = m.get_size()
        pts = []
        for y in range(0, h, 4):
            for x in range(0, w, 4):
                if m.get_at((x, y))[3] > 80:
                    pts.append((x, y))
        if len(pts) > 760:
            step = len(pts) // 760 + 1
            pts = pts[::step]

        rnd = random.Random(5)
        self.morphs = []
        for i, (px, py) in enumerate(pts):
            ti = rnd.choices([0, 1, 2], [0.52, 0.30, 0.18])[0]
            sx = px + self.title_rect.left
            sy = py + self.title_rect.top
            u = (sx - self.title_rect.left) / max(1.0, float(w))
            # 起飞时序：从左到右一波波被"抽走"，避免整块文字同时炸开
            delay = 0.07 + 0.74 * (u ** 1.05) + rnd.uniform(0.0, 0.16)
            self.morphs.append(MorphStar(
                sx, sy, ti, rnd.uniform(0, TAU), rnd.uniform(0.06, 0.94),
                rnd.uniform(3.0, 5.8), rnd.uniform(0, 1),
                delay, rnd.uniform(1.15, 1.55),
                rnd.uniform(0.55, 1.35), rnd.uniform(-2.6, 2.6)))

    def target_xy(self, m):
        if m.ti >= len(TIERS):
            p = project(CANDLE_XZ[0], CANDLE_Y0 + 0.16, CANDLE_XZ[1])
            return p[0], p[1]
        rb, rt, y0, y1, segs, hoff = TIERS[m.ti]
        r = lerp(rb, rt, m.f) * 1.01
        p = project(r * math.cos(m.a), y0 + (y1 - y0) * m.f, r * math.sin(m.a))
        return p[0], p[1]

    # ------------------------------------------------------ 事件
    def near_flame(self, pos):
        fx, fy = self.cake.flame_xy
        return math.dist(pos, (fx, fy - 18)) < 76

    def handle(self, e):
        if e.type in (pygame.MOUSEMOTION, pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP):
            d = dict(e.dict)
            d["pos"] = (e.pos[0] / FS, e.pos[1] / FS)
            if "rel" in d:
                d["rel"] = (d["rel"][0] / FS, d["rel"][1] / FS)
            e = pygame.event.Event(e.type, d)
        if e.type == pygame.QUIT:
            return False
        if e.type == pygame.KEYDOWN:
            if e.key == pygame.K_ESCAPE:
                return False
            if e.key == pygame.K_SPACE:
                if self.stage == "intro":
                    self.start_morph()
                elif self.music:
                    self.music.play(loops=-1)
                self.muted = False
            elif e.key == pygame.K_m:
                self.muted = not self.muted
                if self.music:
                    self.music.set_volume(0.0 if self.muted else 0.55)
            elif e.key == pygame.K_r:
                self.restart()
        elif e.type == pygame.MOUSEMOTION:
            dx = e.pos[0] - self.prev_mouse[0]
            self.mouse = e.pos
            if self.dragging:
                self.yaw_vel += dx * 0.010
        elif e.type == pygame.MOUSEBUTTONDOWN:
            if e.button == 1:
                if self.stage == "intro":
                    self.start_morph()
                    return True
                if self.stage == "cake" and self.near_flame(e.pos):
                    self.lit = not self.lit
                    if not self.lit:
                        self.smoke()
                else:
                    self.burst(*e.pos, n=38)
                    self.dragging = True
            elif e.button == 3:
                self.burst(*e.pos, n=60, power=520)
        elif e.type == pygame.MOUSEBUTTONUP:
            if e.button == 1:
                self.dragging = False
        elif e.type == pygame.MOUSEWHEEL:
            self.burst(self.mouse[0], self.mouse[1], n=16, power=240, ring=False)
        return True

    def restart(self):
        if self.music:
            self.music.stop()
        self.stage = "intro"
        self.t = 0.0
        self.particles.clear()
        self.morphs.clear()
        self.rings.clear()
        self.lit = True
        self.cake_alpha = 0.0
        self.rise = 0.0
        self.yaw_vel = 0.0

    def burst(self, x, y, n=36, power=380, ring=True):
        for _ in range(n):
            ang = random.uniform(0, TAU)
            v = random.uniform(0.2, 1.0) * power
            kind = random.choices(["star", "dot", "spark"], [0.55, 0.3, 0.15])[0]
            self.particles.append(Particle(
                x, y, math.cos(ang) * v, math.sin(ang) * v,
                1.3 * random.uniform(0.7, 1.2),
                random.uniform(6, 13) if kind != "dot" else random.uniform(3, 6),
                rgba(rainbow(random.random()), 250), kind,
                spin=random.uniform(-4, 4), grav=random.uniform(40, 130), drag=1.5))
        if ring:
            self.rings.append([x, y, 0.0, 1.0, rainbow(random.random())])

    def trail(self, x, y, vx, vy):
        for _ in range(2):
            self.particles.append(Particle(
                x + random.uniform(-6, 6), y + random.uniform(-6, 6),
                vx * 0.07 + random.uniform(-24, 24), vy * 0.07 - random.uniform(6, 40),
                random.uniform(0.4, 0.9), random.uniform(3, 7),
                rgba(rainbow(random.random()), 225),
                random.choice(["star", "spark", "dot"]),
                spin=random.uniform(-3, 3), grav=-4, drag=1.2))

    def smoke(self):
        fx, fy = self.cake.flame_xy
        for _ in range(12):
            self.particles.append(Particle(
                fx + random.uniform(-3, 3), fy - 22,
                random.uniform(-16, 16), random.uniform(-74, -30),
                random.uniform(1.0, 1.7), random.uniform(4, 8),
                (190, 172, 200, 110), "smoke", spin=random.uniform(-1, 1),
                grav=-16, drag=0.8))

    # ------------------------------------------------------ 更新
    def update(self, dt):
        self.t += dt
        self.gt += dt

        if self.stage == "intro" and self.t > 5.0:
            self.start_morph()

        if self.stage == "cake":
            self.yaw += 0.0020 + self.yaw_vel * dt
        elif self.stage == "morph":
            self.yaw += 0.0016 + self.yaw_vel * dt
        self.yaw_vel *= 0.94 ** (dt * 60)
        if abs(self.yaw_vel) < 0.0006:
            self.yaw_vel = 0.0
        CAM["yaw"] = self.yaw

        for o in self.orbit:
            o[1] += o[3] * dt

        if self.stage == "morph":
            self.cake_alpha = ease_in_out(clamp((self.t - 1.00) / 1.35, 0, 1))
            self.rise = ease_in_out(clamp((self.t - 0.90) / 1.40, 0, 1))
            if self.t > 3.10:
                gx, gy = project(0, 1.05, 0)[:2]
                self.rings.append([gx, gy, 6.0, 0.85, (255, 216, 238)])
                for _ in range(22):
                    ang = random.uniform(0, TAU)
                    v = random.uniform(40, 190)
                    self.particles.append(Particle(
                        gx, gy, math.cos(ang) * v, math.sin(ang) * v * 0.7,
                        random.uniform(0.9, 1.6), random.uniform(4, 9),
                        rgba(rainbow(random.random()), 235), "star",
                        spin=random.uniform(-3, 3), grav=60, drag=1.6))
                self.stage = "cake"
                self.t = 0.0
                self.cake_alpha = 1.0
                self.rise = 1.0
                self.morphs.clear()
        elif self.stage == "cake":
            self.cake_alpha = min(1.0, self.cake_alpha + dt * 2)
            self.rise = min(1.0, self.rise + dt * 2)
            fx, fy = self.cake.flame_xy
            target = 1.3 if math.dist(self.mouse, (fx, fy - 20)) < 150 else 1.0
            target *= 1.0 + 0.03 * math.sin(self.gt * 3.3)
            self.flame_power += (target - self.flame_power) * min(1.0, dt * 6)

        self.particles = [p for p in self.particles if p.update(dt)]
        for r in self.rings:
            r[2] += dt * 520
            r[3] -= dt * 1.6
        self.rings = [r for r in self.rings if r[3] > 0]

        if self.stage == "cake" and not self.dragging:
            mvx = self.mouse[0] - self.prev_mouse[0]
            mvy = self.mouse[1] - self.prev_mouse[1]
            if abs(mvx) + abs(mvy) > 2:
                self.trail(self.mouse[0], self.mouse[1], mvx, mvy)
        self.prev_mouse = self.mouse

    # ------------------------------------------------------ 绘制
    def draw_bg(self, scr):
        scr.blit(self.bg, (0, 0))
        for rib, x, y, vx, rh, ph in self.aurora:
            px = (x + vx * self.gt) % (rib.get_width() + W) - rib.get_width() // 2
            scr.blit(rib, (int(px), int(y + math.sin(self.gt * 0.2 + ph) * 16)))
        for img, x, y, vx, vy, r in self.bokeh:
            px = (x + vx * self.gt) % (W + 140) - 70
            py = (y + vy * self.gt) % (H + 140) - 70
            scr.blit(img, (px - r, py - r), special_flags=pygame.BLEND_RGBA_ADD)

    def make_ambient(self):
        rnd = random.Random(61)
        out = []
        for i in range(52):
            a = rnd.uniform(0, TAU)
            rr = rnd.uniform(1.7, 3.6)
            out.append([rr * math.cos(a), rnd.uniform(0.3, 4.2), rr * math.sin(a),
                        rnd.uniform(0, 1), rnd.choice(["star", "dot", "spark"]),
                        rnd.uniform(0.012, 0.032), rnd.uniform(0, TAU),
                        rnd.uniform(0.25, 0.85)])
        return out

    def draw_ambient(self, scr, off=0, front=False):
        cake_z = CAM["dist"]
        for x, y, z, hue, kind, size, ph, sp in self.amb:
            yy = y + self.gt * 0.09 * sp
            yy = 0.2 + (yy % 3.6)
            xx = x + math.sin(self.gt * 0.3 * sp + ph) * 0.10
            q = project(xx, yy, z)
            if (q[2] < cake_z) != front:
                continue
            tw = 0.45 + 0.55 * math.sin(self.gt * 1.6 + ph) ** 2
            c = aurora(hue + self.gt * 0.04)
            a = int(200 * tw * self.cake_alpha)
            s2 = size * q[3]
            if kind == "star":
                draw_star(scr, q[0], q[1] + off, s2, rgba(c, a), rot=ph + self.gt * 0.3)
            elif kind == "spark":
                draw_spark(scr, q[0], q[1] + off, s2 * 1.4, rgba((255, 255, 255), a),
                           rot=ph)
            else:
                draw_dot(scr, q[0], q[1] + off, s2 * 0.5, rgba(c, a))

    def draw_big_stars(self, scr, off=0, front=False):
        cake_z = CAM["dist"]
        for x, y, z, hue, size, ph, sp in self.bigstars:
            yy = 0.4 + (y + self.gt * 0.12 * sp) % 3.9
            q = project(x + math.sin(self.gt * 0.4 + ph) * 0.08, yy, z)
            if (q[2] < cake_z) != front:
                continue
            tw = 0.55 + 0.45 * math.sin(self.gt * 2.0 + ph) ** 2
            c = _VIVID[int(hue * 5.99) % len(_VIVID)]
            draw_star(scr, q[0], q[1] + off, size * q[3], rgba(c, int(210 * tw)),
                      rot=ph + self.gt * 0.6)
            draw_dot(scr, q[0], q[1] + off, size * q[3] * 0.55,
                     rgba(c, int(90 * tw)))
            draw_star(scr, q[0], q[1] + off, size * q[3] * 0.45,
                      (255, 255, 252, int(230 * tw)), rot=ph + self.gt * 0.6)

    def draw_balloons(self, scr, off=0, front=False):
        """四角气球：屏幕锚定，始终在四角漂着"""
        if front:
            return
        a = min(1.0, self.cake_alpha * 1.15)
        for (fx, fy, rr, ci, ph, sp) in self.balloons:
            px = fx * W + math.cos(self.gt * 0.4 * sp + ph) * 7
            py = fy * H + math.sin(self.gt * sp + ph) * 12
            rad = max(8, int(rr * (H / 900.0)))
            key = (ci, rad)
            img = self._bscale.get(key)
            if img is None:
                img = pygame.transform.smoothscale(self.balloon_sprites[ci], (rad * 2, rad * 2))
                if len(self._bscale) < 160:
                    self._bscale[key] = img
            img.set_alpha(int(255 * a))
            scr.blit(img, (int(px) - rad, int(py) + off - rad))
            pts = []
            for k in range(7):
                f = k / 6
                pts.append((px + math.sin(f * 3 + ph) * rad * 0.10,
                            py + off + rad * 0.92 + f * rad * 2.1))
            try:
                pygame.draw.lines(scr, (255, 244, 252, int(130 * a)), False,
                                  [(int(ax), int(ay)) for ax, ay in pts], 1)
            except ValueError:
                pass

    def draw_intro(self, scr):
        t = self.t
        a = ease_out((t - 0.1) / 0.9)

        if a > 0:
            lay = self.lay
            lay.fill((0, 0, 0, 0))
            for i in range(30):
                ph = i / 30
                ang = t * 0.5 + ph * TAU
                rr = 248 + 10 * math.sin(t * 2 + ph * 3)
                x = CX + math.cos(ang) * rr
                y = 456 + math.sin(ang) * rr * 0.7
                draw_star(lay, x, y, 3 + 3 * a, rgba(rainbow(ph + t * 0.2), 110 * a),
                          rot=ang)
            scr.blit(lay, (0, 0))

            dark = radial_gradient(330, (58, 40, 92, 150), 2.2)
            dark.set_alpha(int(150 * a))
            scr.blit(dark, (CX - 330, 452 - 300))
            img = iridescent(self.title_mask, self.strip, t * 0.12 + 0.12,
                             out=self.title_img)
            sc = 0.9 + 0.1 * a
            if abs(sc - 1) > 0.002:
                img2 = pygame.transform.smoothscale(
                    img, (int(img.get_width() * sc), int(img.get_height() * sc)))
                rect = img2.get_rect(center=(CX, 402))
                img2.set_alpha(int(a * 255))
                glow = soft_blur(img2, 16)
                glow.set_alpha(int(70 * a))
                scr.blit(glow, rect)
                scr.blit(img2, rect)
            else:
                img.set_alpha(int(a * 255))
                glow = soft_blur(img, 16)
                glow.set_alpha(int(70 * a))
                sh = self.title_sh
                sh.set_alpha(int(150 * a))
                scr.blit(sh, (self.title_rect.x, self.title_rect.y + 5))
                scr.blit(glow, self.title_rect)
                scr.blit(img, self.title_rect)
                tw = self.title_img.get_width()
                st = (t * 0.42) % 1.0
                sx = int(-self.sheen.get_width() + st * (tw + self.sheen.get_width()))
                tmp = self.sheen_tmp
                tmp.fill((0, 0, 0, 0))
                tmp.blit(self.sheen, (sx, 0))
                tmp.blit(self.title_mask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
                tmp.set_alpha(int(190 * a))
                scr.blit(tmp, self.title_rect)

        sa = ease_out((t - 1.2) / 1.0) * (0.6 + 0.4 * math.sin(t * 2.4))
        if sa > 0:
            s = self.sub
            s.set_alpha(int(sa * 235))
            r2 = s.get_rect(center=(CX, 566))
            scr.blit(s, r2)

        lay = self.lay
        lay.fill((0, 0, 0, 0))
        for i in range(24):
            y = H - ((t * 55 + i * 86) % (H + 180)) - 30
            x = CX + math.sin(t * 0.7 + i * 1.7) * (160 + 30 * (i % 4)) + (i - 12) * 18
            draw_star(lay, x, y, 2.4 + (i % 3) * 1.6,
                      rgba(rainbow(i * 0.07 + t * 0.1), 130 * ease_out(t / 2)),
                      rot=t * 1.2 + i)
        scr.blit(lay, (0, 0))

    def draw_floor(self, scr, base):
        g = radial_add(300, (110, 58, 42), 2.2)
        scr.blit(g, (base[0] - 300, base[1] - 300 * 0.36), special_flags=pygame.BLEND_RGBA_ADD)
        lay = self.lay
        lay.fill((0, 0, 0, 0))
        for rr, al in ((2.05, 42), (1.62, 30), (1.18, 24)):
            pts = []
            for i in range(64):
                a = i / 64 * TAU
                p = project(rr * math.cos(a), 0.0, rr * math.sin(a))
                pts.append((p[0], p[1]))
            try:
                gfxdraw.aapolygon(lay, [(int(x), int(y)) for x, y in pts], (255, 200, 170, al))
            except ValueError:
                pass
        ring = []
        for i in range(72):
            a = i / 72 * TAU
            p = project(1.70 * math.cos(a), 0.0, 1.70 * math.sin(a))
            ring.append((p[0], p[1]))
        pygame.draw.aalines(lay, (255, 226, 196, 120), True, ring)
        scr.blit(lay, (0, 0))

    def draw_beams(self, scr, base):
        lay = self.lay
        lay.fill((0, 0, 0, 0))
        for k in range(3):
            ang = self.gt * 0.25 + k * TAU / 3
            hgt = 2.9
            spread = 0.55
            col = rainbow(0.1 + k * 0.28 + self.gt * 0.05)
            for j in range(6):
                f0, f1 = j / 6, (j + 1) / 6
                r0 = 0.42 + 0.5 * f0
                r1 = 0.42 + 0.5 * f1
                y0, y1 = f0 * hgt, f1 * hgt
                p = []
                for a, r, y in ((ang - spread * 0.5, r0, y0), (ang + spread * 0.5, r0, y0),
                                (ang + spread * 0.9, r1, y1), (ang - spread * 0.9, r1, y1)):
                    q = project(r * math.cos(a), y, r * math.sin(a))
                    p.append((q[0], q[1]))
                a_ = int(46 * (1 - f0) ** 2)
                draw_poly(lay, p, rgba(col, a_), aa=False)
        scr.blit(lay, (0, 0))

    def draw_halo(self, scr, y, r, front, alpha=150):
        lay = self.lay
        lay.fill((0, 0, 0, 0))
        pts = []
        for i in range(90):
            a = i / 90 * TAU
            p = project(r * math.cos(a), y, r * math.sin(a))
            pts.append((p[0], p[1], p[2] < CAM["dist"], a))
        for i in range(90):
            x0, y0, f0, a0 = pts[i]
            x1, y1, f1, a1 = pts[(i + 1) % 90]
            if f0 != front or f1 != front:
                continue
            col = rainbow(a0 / TAU * 0.8 + self.gt * 0.08)
            al = alpha * (0.55 if front else 0.38)
            pygame.draw.line(lay, rgba(col, al), (x0, y0), (x1, y1), 2)
            draw_dot(lay, x0, y0, 1.4, rgba((255, 255, 255), al * 0.9))
        for k in range(3):
            a = self.gt * (0.9 + k * 0.3) + k * 2.1
            p = project(r * math.cos(a), y, r * math.sin(a))
            if (p[2] < CAM["dist"]) == front:
                draw_spark(lay, p[0], p[1], 9, rgba(rainbow(a / TAU + self.gt * 0.1), 220),
                           rot=self.gt * 2 + k)
        scr.blit(lay, (0, 0))

    def draw_orbit(self, scr, off):
        lay = scr
        for r, a, y, sp, size, hue, ph in self.orbit:
            x, yy, z, k = project(r * math.cos(a), y, r * math.sin(a))
            al = clamp(140 + (z - 6) * -20, 50, 210)
            col = rainbow(hue + self.gt * 0.07)
            draw_spark(lay, x, yy + off, size * 0.9, rgba(col, al), rot=ph + self.gt)
            draw_dot(lay, x, yy + off, 1.5, rgba((255, 255, 255), al))

    def draw_scene(self, scr):
        if self.cake_alpha <= 0:
            return
        base = project(0, 0, 0)
        self.draw_floor(scr, base)
        gl = self.gl_surf
        gl.set_alpha(int(60 * self.cake_alpha))
        scr.blit(gl, (base[0] - 430, base[1] - 470))
        if self.stage == "morph" and self.t > 0.60:
            k = clamp((self.t - 0.60) / 1.20, 0, 1)
            gs = self.gather_surf
            gs.set_alpha(int(150 * math.sin(k * math.pi * 0.92) ** 2))
            scr.blit(gs, (base[0] - 420, base[1] - 400))
        self.draw_beams(scr, base)


        # 接触阴影
        sh = self.sh_surf
        sh.set_alpha(int(140 * self.cake_alpha))
        scr.blit(sh, (base[0] - 300, base[1] - 86))

        rays = self.ray_surf
        rays.set_alpha(int(70 * self.cake_alpha))
        scr.blit(rays, (0, 0))
        self.draw_big_stars(scr, 0, front=False)
        self.draw_ambient(scr, 0, front=False)
        self.draw_balloons(scr, 0, front=False)

        cs = self.cake_surf
        cs.fill((0, 0, 0, 0))
        VIEW["s"] = CS
        self.cake.draw(cs, self.gt, CAM)
        VIEW["s"] = 1.0
        big = pygame.transform.smoothscale(cs, (W, H))
        big.set_alpha(int(255 * self.cake_alpha))
        off = int((1 - self.rise) * 56)
        if self.cake_alpha > 0.92:
            blo = pygame.transform.smoothscale(
                pygame.transform.smoothscale(big, (W // 10, H // 10)), (W, H))
            blo.set_alpha(int(52 * self.cake_alpha))
            scr.blit(blo, (0, off))
        scr.blit(big, (0, off))

        if self.cake_alpha > 0.35:
            fx, fy = self.cake.flame_xy
            draw_flame(scr, fx, fy + off, self.gt, power=self.flame_power,
                       lit=self.lit, alpha=int(255 * self.cake_alpha))

        self.draw_big_stars(scr, off, front=True)
        self.draw_ambient(scr, off, front=True)
        self.draw_balloons(scr, off, front=True)
        self.draw_halo(scr, 0.22, 1.78, True, 170)

        self.draw_orbit(scr, off)

        if self.morphs:
            lay = self.lay
            lay.fill((0, 0, 0, 0))
            rnd_l = rainbow

            def bez(m, u, tx, ty):
                c1x = m.sx + (m.sx - CX) * 0.34 * m.ax
                c1y = m.sy + (m.sy - 470.0) * 0.30 * m.ax - 34
                c2x = tx + (tx - CX) * 0.14 * m.bx
                c2y = ty - 74.0 - 28 * m.bx
                iv = 1.0 - u
                return (iv * iv * iv * m.sx + 3 * iv * iv * u * c1x
                        + 3 * iv * u * u * c2x + u * u * u * tx,
                        iv * iv * iv * m.sy + 3 * iv * iv * u * c1y
                        + 3 * iv * u * u * c2y + u * u * u * ty)

            for m in self.morphs:
                p = (self.t - m.delay) / m.dur
                if p <= 0 or p > 1.0:
                    continue
                u = ease_in_out(p)
                tx, ty = self.target_xy(m)
                x, y = bez(m, u, tx, ty)
                sw = math.sin(math.pi * u) * (58.0 + 74.0 * m.ax)
                ang = m.hue * TAU + self.gt * 0.8 + u * 2.4
                x += math.cos(ang) * sw
                y += math.sin(ang) * sw * 0.78
                col = rnd_l(m.hue + self.gt * 0.12)
                al = 238 * (1.0 - 0.18 * u)
                sz = m.size * (1.0 - 0.30 * u)
                # 流光拖尾
                if p > 0.075:
                    uu = ease_in_out(p - 0.075)
                    px_, py_ = bez(m, uu, tx, ty)
                    sw2 = math.sin(math.pi * uu) * (58.0 + 74.0 * m.ax)
                    an2 = m.hue * TAU + self.gt * 0.8 + uu * 2.4
                    px_ += math.cos(an2) * sw2
                    py_ += math.sin(an2) * sw2 * 0.78
                    pygame.draw.aaline(lay, rgba(col, 110), (px_, py_), (x, y))
                if m.size > 4.6:
                    draw_dot(lay, x, y, sz * 1.6, rgba(col, al * 0.18))
                draw_star(lay, x, y, sz, rgba(col, al),
                          rot=m.hue * 8 + self.t * 3.2)

            scr.blit(lay, (0, 0))

        lay = self.lay
        lay.fill((0, 0, 0, 0))
        for p in self.particles:
            p.draw(lay)
        for x, y, r, a, c in self.rings:
            try:
                gfxdraw.aacircle(lay, int(x), int(y), int(r), rgba(c, 130 * a))
            except ValueError:
                pass
        scr.blit(lay, (0, 0))

        if self.stage == "cake":
            ta = ease_out((self.t - 0.35) / 1.0)
            if ta > 0:
                dk2 = radial_gradient(270, (48, 24, 68, 190), 2.6)
                dk2 = pygame.transform.smoothscale(dk2, (560, 210))
                dk2.set_alpha(int(150 * ta))
                scr.blit(dk2, (CX - 280, 762))
                hb = self.hb
                hb.set_alpha(int(ta * 255))
                scr.blit(hb, hb.get_rect(center=(CX, 790)))
                h = self.hint
                h.set_alpha(int(ta * 190))
                scr.blit(h, h.get_rect(center=(CX, 848)))

    def draw(self, dt):
        scr = self.screen
        self.draw_bg(scr)
        if self.stage == "intro":
            self.draw_intro(scr)
        else:
            self.draw_scene(scr)
            if self.stage == "morph" and self.t < 1.16:
                img = iridescent(self.title_mask, self.strip, self.gt * 0.12,
                                 out=self.title_img)
                f = clamp((self.t - 0.46) / 0.70, 0, 1)
                img.set_alpha(int(255 * (1.0 - ease_in_out(f)) ** 1.15))
                scr.blit(img, self.title_rect)
        mx, my = self.mouse
        draw_spark(scr, mx, my, 12, (255, 255, 255, 200), rot=self.gt * 2)
        draw_spark(scr, mx, my, 6, (255, 226, 190, 220), rot=self.gt * 2 + 0.8)

    def run(self):
        running = True
        while running:
            dt = min(0.05, self.clock.tick(60) / 1000.0)
            for e in pygame.event.get():
                if not self.handle(e):
                    running = False
            self.update(dt)
            self.draw(dt)
            if self.win is not self.canvas:
                self.win.blit(pygame.transform.smoothscale(self.canvas, self.win.get_size()), (0, 0))
            pygame.display.flip()
        pygame.quit()


def shot(path="preview.png", stage="cake", t=6.0):
    app = App(shot=True)
    if stage == "intro":
        app.t = 3.2
        app.gt = 3.2
        app.draw(0.016)
        pygame.image.save(app.screen, path)
        print("已保存:", os.path.abspath(path))
        return
    app.stage = "cake"
    app.t = t
    app.gt = t
    app.cake_alpha = 1.0
    app.rise = 1.0
    VIEW["s"] = CS
    app.cake.draw(app.cake_surf, t, CAM)
    VIEW["s"] = 1.0
    app.draw(0.016)
    pygame.image.save(app.screen, path)
    print("已保存:", os.path.abspath(path))


if __name__ == "__main__":
    if "--shot" in sys.argv:
        if not os.environ.get("DISPLAY") and sys.platform.startswith("linux"):
            os.environ["SDL_VIDEODRIVER"] = "dummy"
            os.environ["SDL_AUDIODRIVER"] = "dummy"
        shot(os.path.join(os.path.dirname(os.path.abspath(__file__)), "preview.png"))
    else:
        App().run()
