"""Draw a role diagram of D405 RGB/depth generation, using verified public specs."""

import argparse
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, default=Path(__file__).with_name('d405_rgb_path.png'))
    parser.add_argument('--font', type=Path, default=Path('C:/Windows/Fonts/malgun.ttf'))
    parser.add_argument('--bold-font', type=Path, default=Path('C:/Windows/Fonts/malgunbd.ttf'))
    args = parser.parse_args()
    canvas = Image.new('RGB', (1680, 800), '#ffffff')
    draw = ImageDraw.Draw(canvas)
    ink, muted, blue, gray = '#182d42', '#52677b', '#126fba', '#607991'

    def font(size, bold=False):
        return ImageFont.truetype(str(args.bold_font if bold else args.font), size)

    def center(text, x, y, size=28, color=ink, bold=False):
        draw.text((x, y), text, font=font(size, bold), fill=color, anchor='mm')

    def panel(box, color='#f5f8fb', border='#c8d5e2', width=2):
        draw.rounded_rectangle(box, radius=18, fill=color, outline=border, width=width)

    def arrow(points, color=gray, width=5):
        draw.line(points, fill=color, width=width, joint='curve')
        x, y = points[-1]
        px, py = points[-2]
        dx, dy = x - px, y - py
        length = (dx * dx + dy * dy) ** 0.5
        ux, uy = dx / length, dy / length
        draw.polygon([(x, y), (x - 17 * ux + 8 * uy, y - 17 * uy - 8 * ux),
                      (x - 17 * ux - 8 * uy, y - 17 * uy + 8 * ux)], fill=color)

    def lens(x, y, accent):
        draw.ellipse((x - 53, y - 53, x + 53, y + 53), fill='#24384a')
        draw.ellipse((x - 42, y - 42, x + 42, y + 42), fill='#101f2c', outline='#7a94ad', width=3)
        draw.ellipse((x - 29, y - 29, x + 29, y + 29), fill=accent)
        draw.ellipse((x - 13, y - 24, x + 3, y - 8), fill='#b2dbf4')

    draw.text((48, 28), 'D405: 왼쪽 센서에서 RGB가 만들어지는 경로',
              font=font(40, True), fill=ink)
    draw.text((50, 91), '센서 명칭과 영상 처리 역할을 기준으로 배치한 개념도',
              font=font(24), fill=muted)

    panel((50, 235, 315, 530))
    center('실제 장면', 182, 275, 31, bold=True)
    # An object icon represents reflected light, not a captured camera image.
    draw.polygon([(112, 365), (182, 330), (252, 365), (182, 402)], fill='#e85953')
    draw.polygon([(112, 365), (182, 402), (182, 477), (112, 439)], fill='#c63d39')
    draw.polygon([(182, 402), (252, 365), (252, 439), (182, 477)], fill='#ed8077')
    center('물체가 반사한 빛', 182, 505, 23, color=muted)

    panel((390, 132, 770, 650), color='#f6f9fc')
    center('스테레오 센서', 580, 155, 25, bold=True)
    panel((420, 183, 738, 353), color='#eaf5ff', border=blue, width=3)
    lens(487, 266, '#2a739e')
    center('왼쪽 센서', 637, 229, 30, bold=True, color=blue)
    center('Left imager', 637, 274, 24, color=muted)
    center('컬러 신호', 637, 314, 25, color=blue)

    panel((420, 420, 738, 590), color='#f0f4f8')
    lens(487, 505, '#405e76')
    center('오른쪽 센서', 637, 466, 28, bold=True)
    center('Right imager', 637, 514, 24, color=muted)
    center('같은 장면 · 서로 다른 시점', 580, 623, 23, color=muted)

    arrow([(315, 328), (363, 328), (420, 266)], width=4)
    arrow([(315, 440), (361, 440), (420, 505)], width=4)

    panel((900, 183, 1200, 353), color='#eaf5ff', border=blue, width=3)
    center('ISP', 1050, 223, 34, bold=True, color=blue)
    center('영상 신호 처리부', 1050, 269, 26)
    center('컬러 신호 → RGB', 1050, 315, 23, color=muted)
    arrow([(738, 253), (900, 253)], color=blue, width=6)
    center('RGB 경로', 820, 222, 22, color=blue, bold=True)

    panel((1320, 183, 1630, 353), color='#f2f9ff', border=blue, width=3)
    center('RGB 영상', 1475, 227, 31, bold=True, color=blue)
    for x, label, color, text_color in [(1380, 'R', '#d84442', '#ffffff'),
                                       (1445, 'G', '#49a871', '#102a20'),
                                       (1510, 'B', '#3b77ca', '#ffffff')]:
        draw.rounded_rectangle((x, 263, x + 56, 312), radius=7, fill=color)
        center(label, x + 28, 287, 25, color=text_color, bold=True)
    arrow([(1200, 253), (1320, 253)], color=blue, width=6)

    panel((900, 420, 1200, 590), color='#f0f4f8')
    center('Vision Processor D4', 1050, 456, 25, bold=True)
    center('두 영상으로', 1050, 509, 26)
    center('깊이 계산', 1050, 553, 28, bold=True)
    # Left also supplies an image to stereo depth processing.
    arrow([(738, 311), (814, 311), (814, 476), (900, 476)])
    arrow([(738, 532), (900, 532)])

    panel((1320, 420, 1630, 590), color='#f4f7fa')
    center('깊이 영상', 1475, 459, 30, bold=True)
    for index in range(8):
        value = 45 + 25 * index
        draw.rectangle((1370 + 26 * index, 499, 1395 + 26 * index, 532), fill=(value,) * 3)
    center('픽셀마다 거리값', 1475, 562, 23, color=muted)
    arrow([(1200, 506), (1320, 506)])

    draw.rounded_rectangle((50, 689, 1630, 744), radius=12, fill='#edf5fc')
    center('RGB는 왼쪽 센서의 컬러 신호로, 깊이는 두 센서의 영상으로 생성된다.',
           840, 716, 28, color=ink, bold=True)
    draw.text((50, 765), '처리 역할을 단순화한 그림이며 실제 부품 위치와 배선을 나타내지 않는다.',
              font=font(20), fill=muted)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(args.out)
    print(args.out.resolve())


if __name__ == '__main__':
    main()
