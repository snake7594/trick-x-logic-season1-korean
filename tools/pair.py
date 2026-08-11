"""두 장을 나란히 붙인 확인용 그림을 만든다."""
import sys
from PIL import Image
import detect

def main(names, sc=2):
    detect.run(names, sc=sc)
    ims = [Image.open(f'_d_{n}.png') for n in names]
    W = sum(i.width for i in ims) + 8 * (len(ims) - 1)
    H = max(i.height for i in ims)
    out = Image.new('RGB', (W, H), (25, 25, 30))
    x = 0
    for i in ims:
        out.paste(i, (x, 0)); x += i.width + 8
    out.save('_pair.png')
    print('sheet', out.size)

if __name__ == '__main__':
    main(sys.argv[1:])
