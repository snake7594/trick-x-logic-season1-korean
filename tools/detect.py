"""이름표·지도 라벨처럼 어두운 판 위의 흰 글자를 찾아 좌표를 찍는다."""
import paths
import json, os, sys
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from scipy import ndimage
import atlas

IMG = paths.IMAGES
CL = json.load(open(os.path.join(IMG, '_classify.json'), encoding='utf-8'))


def load(n):
    p = [x for x in CL['ui_text'] if x.endswith('/' + n + '.png')][0]
    return np.asarray(Image.open(os.path.join(IMG, p)).convert('RGBA'))


def blobs(px, thr=170, join=(1, 7), minpx=40, minw=10, minh=8, maxh=36):
    lum = px[..., :3].astype(np.float32) @ [0.299, 0.587, 0.114]
    m = (px[..., 3] > 100) & (lum >= thr)
    lab, _ = ndimage.label(ndimage.binary_dilation(m, np.ones(join, bool)),
                           np.ones((3, 3), bool))
    out = []
    for y, x in ndimage.find_objects(lab):
        blk = m[y, x]
        h, w = y.stop - y.start, x.stop - x.start
        if blk.sum() < minpx or w < minw or h < minh or h > maxh:
            continue
        xs = np.where(blk.any(0))[0]
        ys = np.where(blk.any(1))[0]
        out.append((x.start + int(xs[0]), y.start + int(ys[0]),
                    x.start + int(xs[-1]) + 1, y.start + int(ys[-1]) + 1))
    out.sort(key=lambda b: (b[1], b[0]))
    return out


def run(names, sc=2, thr=170, join=(1, 7), tag='_d'):
    for n in names:
        px = load(n)
        bs = blobs(px, thr, join)
        print("=====", n, px.shape[1], 'x', px.shape[0], len(bs))
        for i, b in enumerate(bs):
            print(f"{i:>2} x{b[0]:>3}..{b[2]:>3} y{b[1]:>3}..{b[3]:>3} "
                  f"{b[2]-b[0]:>3}x{b[3]-b[1]:>3}")
        im = Image.fromarray(px, 'RGBA')
        bg = Image.new('RGBA', im.size, (190, 190, 195, 255))
        im = Image.alpha_composite(bg, im).convert('RGB')
        im = im.resize((px.shape[1] * sc, px.shape[0] * sc), Image.LANCZOS)
        dr = ImageDraw.Draw(im)
        f = ImageFont.truetype(atlas.FONT, 13)
        for i, b in enumerate(bs):
            dr.rectangle([b[0]*sc, b[1]*sc, b[2]*sc-1, b[3]*sc-1],
                         outline=(230, 30, 30))
            dr.text((b[0]*sc+1, b[1]*sc-13), str(i), fill=(0, 110, 230), font=f)
        im.save(f'{tag}_{n}.png')


if __name__ == '__main__':
    run(sys.argv[1:])
