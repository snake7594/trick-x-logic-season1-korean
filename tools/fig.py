"""도면 라벨 검출: 밝은 글자와 어두운 글자를 함께 잡는다."""
import sys
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from scipy import ndimage
import detect, atlas


def labels(px, join=(1, 7), minpx=45, minw=12, minh=8, maxh=30):
    lum = px[..., :3].astype(np.float32) @ [0.299, 0.587, 0.114]
    op = px[..., 3] > 100
    out = []
    for tag, m in (('d', op & (lum <= 110)), ('l', op & (lum >= 175))):
        lab, _ = ndimage.label(ndimage.binary_dilation(m, np.ones(join, bool)),
                               np.ones((3, 3), bool))
        for y, x in ndimage.find_objects(lab):
            blk = m[y, x]
            h, w = y.stop - y.start, x.stop - x.start
            if blk.sum() < minpx or w < minw or h < minh or h > maxh:
                continue
            xs = np.where(blk.any(0))[0]
            ys = np.where(blk.any(1))[0]
            out.append((tag, x.start + int(xs[0]), y.start + int(ys[0]),
                        x.start + int(xs[-1]) + 1, y.start + int(ys[-1]) + 1))
    out.sort(key=lambda b: (b[2], b[1]))
    return out


def main(names, sc=2):
    ims = []
    for n in names:
        px = detect.load(n)
        bs = labels(px)
        print("=====", n, px.shape[1], 'x', px.shape[0], len(bs))
        for i, b in enumerate(bs):
            print(f"{i:>2} {b[0]} x{b[1]:>3}..{b[3]:>3} y{b[2]:>3}..{b[4]:>3} "
                  f"{b[3]-b[1]:>3}x{b[4]-b[2]:>3}")
        im = Image.fromarray(px, 'RGBA')
        bg = Image.new('RGBA', im.size, (170, 170, 175, 255))
        im = Image.alpha_composite(bg, im).convert('RGB')
        im = im.resize((px.shape[1] * sc, px.shape[0] * sc), Image.LANCZOS)
        dr = ImageDraw.Draw(im)
        f = ImageFont.truetype(atlas.FONT, 13)
        for i, b in enumerate(bs):
            dr.rectangle([b[1]*sc, b[2]*sc, b[3]*sc-1, b[4]*sc-1],
                         outline=(230, 30, 30) if b[0] == 'd' else (30, 120, 255))
            dr.text((b[1]*sc+1, b[2]*sc-13), str(i), fill=(0, 110, 230), font=f)
        ims.append(im)
    W = sum(i.width for i in ims) + 8 * (len(ims) - 1)
    H = max(i.height for i in ims)
    out = Image.new('RGB', (W, H), (25, 25, 30))
    x = 0
    for i in ims:
        out.paste(i, (x, 0)); x += i.width + 8
    out.save('_fig.png')
    print('sheet', out.size)


if __name__ == '__main__':
    main(sys.argv[1:])
