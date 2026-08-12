"""프로젝트 경로를 한곳에서 정한다.

기본값은 **이 파일의 상위 폴더**(저장소 루트)를 기준으로 잡는다. 저장소를 어디에
받아 놓든 그대로 돌아간다. 다른 자리에 두고 싶으면 환경 변수로 덮어쓴다.

    TXL_ROOT     저장소 루트          (기본: tools/ 의 상위 폴더)
    TXL_ISO      원본 ISO 경로        (기본: <ROOT>/Trick x Logic Season 1.iso)
    TXL_ISO_KR   만들어질 한글판 ISO  (기본: <ROOT>/Trick x Logic Season 1 (KR).iso)
    TXL_TTF      이미지용 한글 폰트   (기본: <ROOT>/fonts/SeoulHangangEB.ttf)
    TXL_TTF_GAME 게임 폰트용 TTF      (기본: <ROOT>/fonts/SeoulHangangB.ttf)

중간 산출물(common.bin, out/, font_out/, *.pkl)은 **현재 작업 폴더**에 쌓인다.
그래서 빈 폴더를 하나 만들어 거기서 돌리면 저장소가 더러워지지 않는다.

    mkdir build && cd build
    python ../tools/bootstrap.py
"""
import os

ROOT = os.environ.get('TXL_ROOT') or os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))

ISO = os.environ.get('TXL_ISO') or os.path.join(
    ROOT, 'Trick x Logic Season 1.iso')
ISO_KR = os.environ.get('TXL_ISO_KR') or os.path.join(
    ROOT, 'Trick x Logic Season 1 (KR).iso')

TEXT = os.path.join(ROOT, 'text')
IMAGES = os.path.join(ROOT, 'images')
FONTS = os.path.join(ROOT, 'fonts')

# 이미지(GIM) 안의 글자용. 큼직하게 그리므로 굵은 쪽이 잘 보인다.
TTF = os.environ.get('TXL_TTF') or os.path.join(FONTS, 'SeoulHangangEB.ttf')

# 게임 폰트(17x17·20x20) 글리프용. 굵기와 감마는 **원본 한자의 값 분포에
# 맞춰서** 정했다(`build_font.GAMMA` 설명 참고). ExtraBold 는 너무 굵고
# Medium 은 너무 가늘다.
TTF_GAME = os.environ.get('TXL_TTF_GAME') or os.path.join(
    FONTS, 'SeoulHangangB.ttf')
