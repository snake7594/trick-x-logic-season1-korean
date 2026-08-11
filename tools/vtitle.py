"""챕터 타이틀(`*_bg_title`) 17장에 한글을 입힌다.

원본 글자를 밝기로 골라 지운 뒤(inpaint), 같은 자리·같은 색으로 세로쓰기.
"""
import paths
import os
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter
import inpaint

FONT = paths.TTF
BOTTOM = 252                      # 세로열이 내려갈 수 있는 한계 y

TITLE = {
    'BH': '망령 햄릿',
    'BJ': '폭주 줄리엣',
    'FW': '불 꺼진 방에서',
    'KM': '눈 내리는 여자 기숙사에서',
    'NF': '도둑맞은 피규어',
    'SI': '절단된 다섯 개의 목',
}
AUTHOR = {
    'BH': '구로다 겐지',
    'BJ': '구로다 겐지',
    'FW': '다케모토 겐지',
    'KM': '마야 유타카',
    'NF': '아비코 다케마루',
    'SI': '오야마 세이이치로',
}
TU_GAP = (98, 105)                # 練習問題 / 指さす死体 사이 여백
TU_TOP, TU_BOTTOM = '연습문제', '가리키는 시체'


def draw_column(px, box, text, color, bottom=BOTTOM):
    """box(x0,y0,x1,y1) 위쪽부터 세로쓰기. 공백은 반 칸."""
    x0, y0, x1, y1 = box
    cw = x1 - x0
    slots = [0.45 if c == ' ' else 1.0 for c in text]
    total = sum(slots)
    avail = max(y1 - y0, min(bottom, y0 + int(cw * total)) - y0)
    size = int(min(cw, avail / total))
    size = max(size, 9)
    f = ImageFont.truetype(FONT, size)
    h = size * total
    cx = (x0 + x1) / 2
    cy0 = y0 + max(0, ((y1 - y0) - h) / 2) if h < (y1 - y0) else y0

    lay = Image.new('RGBA', (px.shape[1], px.shape[0]), (0, 0, 0, 0))
    dr = ImageDraw.Draw(lay)
    y = cy0
    for c, s in zip(text, slots):
        if c != ' ':
            b = f.getbbox(c)
            gx = cx - (b[0] + b[2]) / 2
            gy = y + (size - (b[1] + b[3])) / 2
            dr.text((gx, gy), c, font=f, fill=color + (255,))
        y += size * s

    sh = lay.split()[3].filter(ImageFilter.GaussianBlur(1.2))
    sh = sh.point(lambda v: int(v * 0.72))
    out = Image.fromarray(px, 'RGBA')
    out.paste(Image.new('RGBA', out.size, (10, 6, 4, 255)),
              (1, 2), Image.frombytes('L', sh.size, sh.tobytes()))
    out.alpha_composite(lay)
    return np.asarray(out).copy()


def build(name, px):
    """이름으로 배치를 정해 한글판 픽셀을 만든다."""
    sc = name.split('_')[0]
    var = ('_foranswer' if name.endswith('_foranswer')
           else '_forend' if name.endswith('_forend') else '')
    box_mask = inpaint.text_mask(px, 165, 1)
    rs = inpaint.runs(box_mask, xgap=6, ygap=13, minpx=150, minh=20)
    if not rs:
        raise ValueError('글자 상자 없음')
    jobs = []
    tb = rs[0]
    if sc == 'TU':
        ga, gb = TU_GAP
        jobs.append(((tb[0], tb[1], tb[2], ga), TU_TOP, ga))
        jobs.append(((tb[0], gb, tb[2], tb[3]), TU_BOTTOM, BOTTOM))
    else:
        jobs.append((tb, TITLE[sc], BOTTOM))
        if var == '' and len(rs) > 1:
            jobs.append((rs[1], AUTHOR[sc], BOTTOM))
    if var and len(rs) > 1:
        jobs.append((rs[-1], '해결편' if var == '_foranswer' else '완', BOTTOM))

    erased, em = inpaint.erase(px, 120, 2)
    for box, txt, bot in jobs:
        erased = draw_column(erased, box, txt, inpaint.ink(px, em, box), bot)
    return erased
