#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""gen-cover-art-assets.py —— 原型演示素材（封面 / 头像）生成器。

为《ai-novel-c端-封面与角色头像-原型》生成自包含 SVG 示意画面：
  assets/cover-*.svg   3:4 书封（两案一组，供「候选」切换）
  assets/ava-*.svg     1:1 角色头像（陈屿四案，其余两案）

这些是**原型示意素材**，不是真实图像模型输出，也不代表最终画风；只用于
评审版式、状态与交互。全部由本脚本参数化生成，无外部字体/图片引用。

用法：python3 docs/design-c/drafts/gen-cover-art-assets.py
"""
import io
import os

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cover-art-captures", "assets")

SERIF = "Noto Serif SC, Songti SC, STSong, Iowan Old Style, Georgia, serif"


def svg(w, h, body, defs="", viewbox=None):
    vb = viewbox or f"0 0 {w} {h}"
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="{vb}">
<defs>
  <filter id="grain" x="0" y="0" width="100%" height="100%">
    <feTurbulence type="fractalNoise" baseFrequency="0.9" numOctaves="3" seed="7" result="n"/>
    <feColorMatrix in="n" type="saturate" values="0" result="m"/>
    <feComponentTransfer in="m" result="t"><feFuncA type="linear" slope="0.10"/></feComponentTransfer>
    <feBlend in="SourceGraphic" in2="t" mode="multiply"/>
  </filter>
  <filter id="soft" x="-30%" y="-30%" width="160%" height="160%"><feGaussianBlur stdDeviation="18"/></filter>
  <filter id="soft2" x="-40%" y="-40%" width="180%" height="180%"><feGaussianBlur stdDeviation="34"/></filter>
  <filter id="ink"><feTurbulence type="fractalNoise" baseFrequency="0.012" numOctaves="4" seed="3" result="n"/><feDisplacementMap in="SourceGraphic" in2="n" scale="14" xChannelSelector="R" yChannelSelector="G"/></filter>
{defs}
</defs>
{body}
</svg>
'''


def cover(path, W, H, pal, kind, title, sub, seal, with_text=True):
    bg1, bg2, accent, ink, paper = pal
    b = []
    b.append(f'<rect width="{W}" height="{H}" fill="url(#bg)"/>')
    # atmosphere
    b.append(f'<ellipse cx="{W*0.72:.0f}" cy="{H*0.22:.0f}" rx="{W*0.30:.0f}" ry="{H*0.20:.0f}" fill="{accent}" opacity="0.16" filter="url(#soft2)"/>')
    if kind == "lantern":
        # roofline
        b.append(f'<path d="M0 {H*0.74:.0f} L{W*0.10:.0f} {H*0.70:.0f} L{W*0.18:.0f} {H*0.73:.0f} L{W*0.30:.0f} {H*0.66:.0f} L{W*0.44:.0f} {H*0.72:.0f} L{W*0.56:.0f} {H*0.67:.0f} L{W*0.70:.0f} {H*0.73:.0f} L{W*0.84:.0f} {H*0.69:.0f} L{W:.0f} {H*0.74:.0f} L{W:.0f} {H:.0f} L0 {H:.0f} Z" fill="{ink}" opacity="0.92" filter="url(#ink)"/>')
        # figure
        b.append(f'<g opacity="0.95"><ellipse cx="{W*0.36:.0f}" cy="{H*0.66:.0f}" rx="{W*0.052:.0f}" ry="{H*0.038:.0f}" fill="{ink}"/><path d="M{W*0.28:.0f} {H*0.86:.0f} Q{W*0.30:.0f} {H*0.71:.0f} {W*0.36:.0f} {H*0.705:.0f} Q{W*0.43:.0f} {H*0.71:.0f} {W*0.45:.0f} {H*0.86:.0f} Z" fill="{ink}"/></g>')
        # lantern
        b.append(f'<circle cx="{W*0.55:.0f}" cy="{H*0.62:.0f}" r="{W*0.13:.0f}" fill="{accent}" opacity="0.30" filter="url(#soft2)"/>')
        b.append(f'<line x1="{W*0.55:.0f}" y1="{H*0.50:.0f}" x2="{W*0.55:.0f}" y2="{H*0.545:.0f}" stroke="{ink}" stroke-width="4" opacity="0.8"/>')
        b.append(f'<rect x="{W*0.515:.0f}" y="{H*0.545:.0f}" width="{W*0.07:.0f}" height="{H*0.075:.0f}" rx="{W*0.014:.0f}" fill="{accent}" opacity="0.95"/>')
        b.append(f'<rect x="{W*0.515:.0f}" y="{H*0.545:.0f}" width="{W*0.07:.0f}" height="{H*0.075:.0f}" rx="{W*0.014:.0f}" fill="none" stroke="{paper}" stroke-width="2" opacity="0.5"/>')
        b.append(f'<line x1="{W*0.55:.0f}" y1="{H*0.62:.0f}" x2="{W*0.55:.0f}" y2="{H*0.635:.0f}" stroke="{ink}" stroke-width="3" opacity="0.7"/>')
        # mist bands
        for i, y in enumerate((0.70, 0.78, 0.86)):
            b.append(f'<ellipse cx="{W*(0.2+0.3*i):.0f}" cy="{H*y:.0f}" rx="{W*0.42:.0f}" ry="{H*0.035:.0f}" fill="{paper}" opacity="{0.10+0.03*i}" filter="url(#soft)"/>')
    elif kind == "city":
        # window frame + city
        b.append(f'<rect x="0" y="0" width="{W}" height="{H}" fill="url(#bg)"/>')
        b.append(f'<rect x="{W*0.08:.0f}" y="{H*0.10:.0f}" width="{W*0.84:.0f}" height="{H*0.58:.0f}" rx="6" fill="none" stroke="{ink}" stroke-width="10" opacity="0.55"/>')
        b.append(f'<line x1="{W*0.50:.0f}" y1="{H*0.10:.0f}" x2="{W*0.50:.0f}" y2="{H*0.68:.0f}" stroke="{ink}" stroke-width="8" opacity="0.5"/>')
        b.append(f'<line x1="{W*0.08:.0f}" y1="{H*0.38:.0f}" x2="{W*0.92:.0f}" y2="{H*0.38:.0f}" stroke="{ink}" stroke-width="6" opacity="0.4"/>')
        for i, (x, hh) in enumerate(((0.12, 0.18), (0.22, 0.28), (0.32, 0.12), (0.58, 0.22), (0.69, 0.15), (0.80, 0.25))):
            b.append(f'<rect x="{W*x:.0f}" y="{H*(0.68-hh):.0f}" width="{W*0.075:.0f}" height="{H*hh:.0f}" fill="{ink}" opacity="0.28"/>')
            b.append(f'<circle cx="{W*(x+0.035):.0f}" cy="{H*(0.68-hh*0.6):.0f}" r="2.4" fill="{accent}" opacity="0.8"/>')
        # table, cups, plant
        b.append(f'<rect x="0" y="{H*0.78:.0f}" width="{W}" height="{H*0.22:.0f}" fill="{ink}" opacity="0.16"/>')
        b.append(f'<ellipse cx="{W*0.36:.0f}" cy="{H*0.80:.0f}" rx="{W*0.10:.0f}" ry="{H*0.018:.0f}" fill="{paper}" opacity="0.55"/>')
        b.append(f'<path d="M{W*0.30:.0f} {H*0.72:.0f} h{W*0.07:.0f} v{H*0.06:.0f} h-{W*0.07:.0f} Z" fill="{paper}" opacity="0.85"/>')
        b.append(f'<path d="M{W*0.45:.0f} {H*0.73:.0f} h{W*0.06:.0f} v{H*0.05:.0f} h-{W*0.06:.0f} Z" fill="{paper}" opacity="0.7"/>')
        b.append(f'<path d="M{W*0.70:.0f} {H*0.66:.0f} q{W*0.06:.0f} -{H*0.14:.0f} {W*0.12:.0f} -{H*0.02:.0f}" stroke="{ink}" stroke-width="6" fill="none" opacity="0.55"/>')
        b.append(f'<ellipse cx="{W*0.84:.0f}" cy="{H*0.62:.0f}" rx="{W*0.06:.0f}" ry="{H*0.09:.0f}" fill="{ink}" opacity="0.28" transform="rotate(24 {W*0.84:.0f} {H*0.62:.0f})"/>')
        b.append(f'<ellipse cx="{W*0.75:.0f}" cy="{H*0.57:.0f}" rx="{W*0.05:.0f}" ry="{H*0.08:.0f}" fill="{ink}" opacity="0.22" transform="rotate(-18 {W*0.75:.0f} {H*0.57:.0f})"/>')
    elif kind == "steppe":
        b.append(f'<path d="M0 {H*0.66:.0f} L{W*0.16:.0f} {H*0.52:.0f} L{W*0.32:.0f} {H*0.62:.0f} L{W*0.50:.0f} {H*0.45:.0f} L{W*0.70:.0f} {H*0.60:.0f} L{W*0.86:.0f} {H*0.48:.0f} L{W:.0f} {H*0.60:.0f} L{W} {H} L0 {H} Z" fill="{ink}" opacity="0.9" filter="url(#ink)"/>')
        # sun
        b.append(f'<circle cx="{W*0.68:.0f}" cy="{H*0.28:.0f}" r="{W*0.09:.0f}" fill="{accent}" opacity="0.9"/>')
        # rider silhouette
        b.append(f'<g fill="{ink}" transform="translate({W*0.36:.0f},{H*0.62:.0f})" opacity="0.92">')
        b.append(f'<ellipse cx="0" cy="0" rx="{W*0.11:.0f}" ry="{H*0.035:.0f}"/>')
        b.append(f'<path d="M-{W*0.10:.0f} 0 l-{W*0.03:.0f} {H*0.09:.0f} M{W*0.08:.0f} 0 l{W*0.02:.0f} {H*0.09:.0f} M-{W*0.05:.0f} 0 l-{W*0.02:.0f} {H*0.09:.0f} M{W*0.04:.0f} 0 l{W*0.03:.0f} {H*0.09:.0f}" stroke="{ink}" stroke-width="9" stroke-linecap="round"/>')
        b.append(f'<circle cx="{W*0.01:.0f}" cy="-{H*0.10:.0f}" r="{W*0.028:.0f}"/><path d="M-{W*0.005:.0f} -{H*0.085:.0f} q{W*0.04:.0f} -{H*0.02:.0f} {W*0.05:.0f} {H*0.02:.0f} l-{W*0.01:.0f} {H*0.05:.0f} l-{W*0.04:.0f} 0 Z"/>')
        b.append(f'<path d="M{W*0.045:.0f} -{H*0.075:.0f} l{W*0.16:.0f} -{H*0.01:.0f}" stroke="{ink}" stroke-width="5" stroke-linecap="round"/>')
        b.append('</g>')
        for i, y in enumerate((0.72, 0.80)):
            b.append(f'<ellipse cx="{W*0.5:.0f}" cy="{H*y:.0f}" rx="{W*0.60:.0f}" ry="{H*0.025:.0f}" fill="{paper}" opacity="0.12" filter="url(#soft)"/>')
    # vignette + grain
    b.append(f'<rect width="{W}" height="{H}" fill="url(#vig)"/>')
    b.append(f'<rect width="{W}" height="{H}" filter="url(#grain)" opacity="0.55" fill="none"/>')
    if with_text:
        # title block
        b.append(f'<g font-family="{SERIF}" fill="{paper}">')
        b.append(f'<text x="{W*0.10:.0f}" y="{H*0.115:.0f}" font-size="{W*0.030:.0f}" letter-spacing="{W*0.006:.0f}" opacity="0.72">{sub}</text>')
        ty = H * 0.19
        for i, ch in enumerate(title):
            b.append(f'<text x="{W*0.105:.0f}" y="{ty + i*W*0.085:.0f}" font-size="{W*0.085:.0f}" font-weight="600">{ch}</text>')
        b.append(f'</g>')
        # seal
        sx, sy, ss = W * 0.86, H * 0.875, W * 0.075
        b.append(f'<rect x="{sx:.0f}" y="{sy:.0f}" width="{ss:.0f}" height="{ss*1.28:.0f}" rx="3" fill="{accent}" opacity="0.92"/>')
        b.append(f'<text x="{sx+ss/2:.0f}" y="{sy+ss*0.52:.0f}" text-anchor="middle" font-family="{SERIF}" font-size="{ss*0.42:.0f}" fill="{paper}">{seal[0]}</text>')
        b.append(f'<text x="{sx+ss/2:.0f}" y="{sy+ss*0.98:.0f}" text-anchor="middle" font-family="{SERIF}" font-size="{ss*0.42:.0f}" fill="{paper}">{seal[1]}</text>')

    defs = f'''  <linearGradient id="bg" x1="0" y1="0" x2="0.4" y2="1">
    <stop offset="0" stop-color="{bg1}"/><stop offset="1" stop-color="{bg2}"/>
  </linearGradient>
  <radialGradient id="vig" cx="0.5" cy="0.45" r="0.78">
    <stop offset="0.55" stop-color="#000" stop-opacity="0"/><stop offset="1" stop-color="#000" stop-opacity="0.38"/>
  </radialGradient>'''
    write(path, svg(W, H, "\n".join(b), defs))


def avatar(path, S, pal, variant, hair, extra="", glasses=False, scar=False, older=False, viewbox=None):
    bg1, bg2, skin, ink, cloth, accent = pal
    b = []
    b.append(f'<rect width="{S}" height="{S}" fill="url(#bg)"/>')
    b.append(f'<circle cx="{S*0.5:.0f}" cy="{S*0.46:.0f}" r="{S*0.40:.0f}" fill="{accent}" opacity="0.10" filter="url(#soft2)"/>')
    # shoulders
    b.append(f'<path d="M{S*0.08:.0f} {S:.0f} Q{S*0.12:.0f} {S*0.68:.0f} {S*0.34:.0f} {S*0.63:.0f} L{S*0.66:.0f} {S*0.63:.0f} Q{S*0.88:.0f} {S*0.68:.0f} {S*0.92:.0f} {S:.0f} Z" fill="{cloth}"/>')
    # neck
    b.append(f'<path d="M{S*0.42:.0f} {S*0.55:.0f} h{S*0.16:.0f} v{S*0.13:.0f} h-{S*0.16:.0f} Z" fill="{skin}" opacity="0.92"/>')
    # head
    b.append(f'<ellipse cx="{S*0.50:.0f}" cy="{S*0.39:.0f}" rx="{S*0.145:.0f}" ry="{S*0.175:.0f}" fill="{skin}"/>')
    # hair
    if hair == "short":
        b.append(f'<path d="M{S*0.355:.0f} {S*0.36:.0f} Q{S*0.35:.0f} {S*0.19:.0f} {S*0.50:.0f} {S*0.185:.0f} Q{S*0.65:.0f} {S*0.19:.0f} {S*0.645:.0f} {S*0.36:.0f} Q{S*0.61:.0f} {S*0.27:.0f} {S*0.50:.0f} {S*0.275:.0f} Q{S*0.39:.0f} {S*0.27:.0f} {S*0.355:.0f} {S*0.36:.0f} Z" fill="{ink}"/>')
    elif hair == "bob":
        b.append(f'<path d="M{S*0.345:.0f} {S*0.44:.0f} Q{S*0.33:.0f} {S*0.18:.0f} {S*0.50:.0f} {S*0.175:.0f} Q{S*0.67:.0f} {S*0.18:.0f} {S*0.655:.0f} {S*0.44:.0f} L{S*0.62:.0f} {S*0.41:.0f} Q{S*0.60:.0f} {S*0.26:.0f} {S*0.50:.0f} {S*0.26:.0f} Q{S*0.40:.0f} {S*0.26:.0f} {S*0.38:.0f} {S*0.41:.0f} Z" fill="{ink}"/>')
    elif hair == "cap":
        b.append(f'<path d="M{S*0.34:.0f} {S*0.33:.0f} Q{S*0.36:.0f} {S*0.17:.0f} {S*0.52:.0f} {S*0.17:.0f} Q{S*0.66:.0f} {S*0.18:.0f} {S*0.66:.0f} {S*0.31:.0f} L{S*0.72:.0f} {S*0.325:.0f} Q{S*0.66:.0f} {S*0.36:.0f} {S*0.58:.0f} {S*0.34:.0f} Z" fill="{ink}"/>')
    else:  # grey
        b.append(f'<path d="M{S*0.355:.0f} {S*0.36:.0f} Q{S*0.35:.0f} {S*0.19:.0f} {S*0.50:.0f} {S*0.185:.0f} Q{S*0.65:.0f} {S*0.19:.0f} {S*0.645:.0f} {S*0.36:.0f} Q{S*0.61:.0f} {S*0.28:.0f} {S*0.50:.0f} {S*0.285:.0f} Q{S*0.39:.0f} {S*0.28:.0f} {S*0.355:.0f} {S*0.36:.0f} Z" fill="{ink}" opacity="0.55"/>')
    # brows/eyes/nose (minimal ink)
    b.append(f'<path d="M{S*0.435:.0f} {S*0.385:.0f} q{S*0.028:.0f} -{S*0.014:.0f} {S*0.052:.0f} 0 M{S*0.515:.0f} {S*0.385:.0f} q{S*0.028:.0f} -{S*0.014:.0f} {S*0.052:.0f} 0" stroke="{ink}" stroke-width="{S*0.010:.0f}" fill="none" stroke-linecap="round" opacity="0.85"/>')
    b.append(f'<path d="M{S*0.50:.0f} {S*0.405:.0f} l-{S*0.008:.0f} {S*0.045:.0f} l{S*0.016:.0f} 0" stroke="{ink}" stroke-width="{S*0.006:.0f}" fill="none" opacity="0.35"/>')
    b.append(f'<path d="M{S*0.465:.0f} {S*0.495:.0f} q{S*0.035:.0f} {S*0.014:.0f} {S*0.070:.0f} 0" stroke="{ink}" stroke-width="{S*0.007:.0f}" fill="none" stroke-linecap="round" opacity="0.55"/>')
    # cloth fold
    b.append(f'<path d="M{S*0.34:.0f} {S*0.63:.0f} L{S*0.50:.0f} {S*0.78:.0f} L{S*0.66:.0f} {S*0.63:.0f}" fill="none" stroke="{ink}" stroke-width="{S*0.008:.0f}" opacity="0.25"/>')
    if glasses:
        b.append(f'<g fill="none" stroke="{ink}" stroke-width="{S*0.008:.0f}" opacity="0.8"><circle cx="{S*0.455:.0f}" cy="{S*0.39:.0f}" r="{S*0.038:.0f}"/><circle cx="{S*0.555:.0f}" cy="{S*0.39:.0f}" r="{S*0.038:.0f}"/><path d="M{S*0.493:.0f} {S*0.39:.0f} h{S*0.024:.0f}"/></g>')
    if scar:
        b.append(f'<path d="M{S*0.60:.0f} {S*0.40:.0f} l{S*0.02:.0f} {S*0.05:.0f}" stroke="{ink}" stroke-width="{S*0.006:.0f}" opacity="0.5"/>')
    if older:
        b.append(f'<path d="M{S*0.43:.0f} {S*0.46:.0f} q{S*0.03:.0f} {S*0.01:.0f} {S*0.05:.0f} 0 M{S*0.52:.0f} {S*0.46:.0f} q{S*0.03:.0f} {S*0.01:.0f} {S*0.05:.0f} 0" stroke="{ink}" stroke-width="{S*0.004:.0f}" opacity="0.3"/>')
    b.append(extra)
    b.append(f'<rect width="{S}" height="{S}" fill="url(#vig)"/>')
    b.append(f'<rect width="{S}" height="{S}" filter="url(#grain)" opacity="0.55" fill="none"/>')
    defs = f'''  <linearGradient id="bg" x1="0" y1="0" x2="0.7" y2="1"><stop offset="0" stop-color="{bg1}"/><stop offset="1" stop-color="{bg2}"/></linearGradient>
  <radialGradient id="vig" cx="0.5" cy="0.45" r="0.75"><stop offset="0.55" stop-color="#000" stop-opacity="0"/><stop offset="1" stop-color="#000" stop-opacity="0.34"/></radialGradient>'''
    write(path, svg(S, S, "\n".join(b), defs, viewbox))


def write(name, text):
    os.makedirs(OUT, exist_ok=True)
    p = os.path.join(OUT, name)
    with io.open(p, "w", encoding="utf-8") as f:
        f.write(text)
    print("wrote", p, len(text.encode("utf-8")), "bytes")


def main():
    W, H = 600, 800
    pal_night = ("#0d1c1b", "#16302c", "#d99344", "#060e0e", "#f1e7d2")
    pal_night2 = ("#101d24", "#22323a", "#c9783f", "#050b0e", "#e9e2d4")
    pal_warm = ("#f3dfc9", "#d9a88e", "#b5533f", "#3a2622", "#fff8ef")
    pal_warm2 = ("#e9cfbf", "#c98e7a", "#8c4a3c", "#33221f", "#fff6ec")
    pal_cold = ("#16202e", "#2a3a4a", "#b64a3f", "#080d14", "#e8e4d8")
    pal_cold2 = ("#1b2433", "#33455c", "#c56a4a", "#070b12", "#efeadd")

    cover("cover-changyedeng-a.svg", W, H, pal_night, "lantern", "长夜灯", "悬疑 · 民俗", "长夜")
    cover("cover-changyedeng-b.svg", W, H, pal_night2, "lantern", "长夜灯", "悬疑 · 民俗", "长夜")
    cover("cover-chunri-a.svg", W, H, pal_warm, "city", "春日迟迟", "都市 · 情感", "春日")
    cover("cover-chunri-b.svg", W, H, pal_warm2, "city", "春日迟迟", "都市 · 情感", "春日")
    cover("cover-tiema-a.svg", W, H, pal_cold, "steppe", "铁马冰河", "历史 · 战争", "铁马")
    cover("cover-tiema-b.svg", W, H, pal_cold2, "steppe", "铁马冰河", "历史 · 战争", "铁马")
    cover("test-lantern-tall.svg", 600, 800, pal_night, "lantern", "", "", "", with_text=False)
    cover("test-lantern-square.svg", 600, 600, pal_night, "lantern", "", "", "", with_text=False)

    S = 400
    p_chen = ("#1a2b2b", "#2f4441", "#d8b191", "#111a1a", "#2b3a38", "#d99344")
    p_zhou = ("#1b2832", "#2f4655", "#dcb69c", "#101a20", "#2b4a5c", "#7fa6b8")
    p_qin = ("#2a2620", "#433b30", "#d3ad8d", "#17130f", "#4a4034", "#c99552")
    p_fu = ("#20262a", "#374249", "#cfae93", "#0f1416", "#3a444a", "#c69a5c")
    avatar("ava-chenyu-a.svg", S, p_chen, "a", "short", extra=f'<path d="M{S*0.72:.0f} {S*0.58:.0f} q{S*0.06:.0f} -{S*0.10:.0f} {S*0.12:.0f} -{S*0.02:.0f} l-{S*0.03:.0f} {S*0.10:.0f} Z" fill="#d99344" opacity="0.55" filter="url(#soft)"/>')
    avatar("ava-chenyu-b.svg", S, p_chen, "b", "short", viewbox="26 14 348 348", extra=f'<rect x="{S*0.70:.0f}" y="{S*0.52:.0f}" width="{S*0.08:.0f}" height="{S*0.11:.0f}" rx="{S*0.012:.0f}" fill="#e0a054" opacity="0.7"/>')
    avatar("ava-chenyu-c.svg", S, p_fu, "c", "short", viewbox="0 18 400 382", extra=f'<circle cx="{S*0.74:.0f}" cy="{S*0.58:.0f}" r="{S*0.07:.0f}" fill="#eab06a" opacity="0.28" filter="url(#soft)"/>')
    avatar("ava-chenyu-d.svg", S, p_qin, "d", "short", viewbox="12 0 376 376", extra=f'<path d="M0 {S*0.66:.0f} h{S:.0f} v{S*0.34:.0f} h-{S:.0f} Z" fill="#0f1414" opacity="0.22"/>')
    avatar("ava-zhou-a.svg", S, p_zhou, "a", "bob", scar=True, extra=f'<path d="M0 {S*0.62:.0f} q{S*0.18:.0f} -{S*0.05:.0f} {S*0.36:.0f} 0 t{S*0.36:.0f} 0" fill="none" stroke="#9fc3d2" stroke-width="{S*0.012:.0f}" opacity="0.45"/>')
    avatar("ava-zhou-b.svg", S, p_zhou, "b", "bob", scar=True)
    avatar("ava-laoqin-a.svg", S, p_qin, "a", "cap", glasses=True, extra=f'<circle cx="{S*0.66:.0f}" cy="{S*0.70:.0f}" r="{S*0.035:.0f}" fill="none" stroke="{p_qin[3]}" stroke-width="{S*0.008:.0f}" opacity="0.6"/><circle cx="{S*0.72:.0f}" cy="{S*0.72:.0f}" r="{S*0.035:.0f}" fill="none" stroke="{p_qin[3]}" stroke-width="{S*0.008:.0f}" opacity="0.6"/>')
    avatar("ava-laoqin-b.svg", S, p_qin, "b", "cap", glasses=True)
    avatar("ava-chenfu-a.svg", S, p_fu, "a", "grey", older=True, extra=f'<rect x="{S*0.16:.0f}" y="{S*0.66:.0f}" width="{S*0.10:.0f}" height="{S*0.12:.0f}" rx="{S*0.014:.0f}" fill="#d9a45a" opacity="0.55"/><line x1="{S*0.21:.0f}" y1="{S*0.66:.0f}" x2="{S*0.21:.0f}" y2="{S*0.63:.0f}" stroke="{p_fu[3]}" stroke-width="{S*0.008:.0f}"/>')
    avatar("ava-chenfu-b.svg", S, p_fu, "b", "grey", older=True)


if __name__ == "__main__":
    main()
