"""Create deterministic OpenPose-style hand guides for isolated ComfyUI tests."""
from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image, ImageDraw


WIDTH, HEIGHT = 720, 1280
COLORS = [(255, 85, 0), (255, 170, 0), (170, 255, 0), (0, 255, 170), (0, 170, 255)]


def joint(draw: ImageDraw.ImageDraw, point: tuple[int, int], radius: int = 7, color=(255, 0, 0)) -> None:
    x, y = point
    draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=color)


def limb(draw: ImageDraw.ImageDraw, a: tuple[int, int], b: tuple[int, int], color=(0, 255, 255)) -> None:
    draw.line((a, b), fill=color, width=8)


def draw_hand(draw: ImageDraw.ImageDraw, wrist: tuple[int, int], direction: int, *, raised: bool = True) -> None:
    """Draw five deliberately separate OpenPose-style fingers from one wrist."""
    palm = (wrist[0] + direction * 22, wrist[1] - 12 if raised else wrist[1] + 10)
    joint(draw, palm)
    base_offsets = [18, 6, 0, 7, 21]
    tip_offsets = [-40, -62, -70, -62, -42] if raised else [42, 60, 68, 60, 42]
    for index, (base_offset, tip_offset, color) in enumerate(zip(base_offsets, tip_offsets, COLORS)):
        base = (palm[0] + direction * (15 + index * 8), palm[1] + base_offset)
        middle = (base[0] + direction * 16, (base[1] + palm[1] + tip_offset) // 2)
        tip = (middle[0] + direction * 9, palm[1] + tip_offset)
        for start, end in ((palm, base), (base, middle), (middle, tip)):
            limb(draw, start, end, color)
        for point in (base, middle, tip):
            joint(draw, point, 5, color)


def draw_torso(draw: ImageDraw.ImageDraw, shoulders: tuple[tuple[int, int], tuple[int, int]], elbows: tuple[tuple[int, int], tuple[int, int]], wrists: tuple[tuple[int, int], tuple[int, int]], neck=(360, 330), hip=(360, 775)) -> None:
    left_shoulder, right_shoulder = shoulders
    left_elbow, right_elbow = elbows
    left_wrist, right_wrist = wrists
    for start, end in ((neck, left_shoulder), (neck, right_shoulder), (left_shoulder, left_elbow),
                       (left_elbow, left_wrist), (right_shoulder, right_elbow),
                       (right_elbow, right_wrist), (neck, hip)):
        limb(draw, start, end)
    for point in (neck, left_shoulder, right_shoulder, left_elbow, right_elbow, left_wrist, right_wrist, hip):
        joint(draw, point)


def holding_object(draw: ImageDraw.ImageDraw) -> None:
    left_wrist, right_wrist = (307, 742), (413, 742)
    draw_torso(draw, ((255, 408), (465, 408)), ((268, 580), (452, 580)), (left_wrist, right_wrist))
    draw_hand(draw, left_wrist, 1)
    draw_hand(draw, right_wrist, -1)
    draw.rounded_rectangle((330, 650, 390, 750), radius=10, outline=(255, 255, 255), width=4)
    draw.ellipse((386, 675, 420, 725), outline=(255, 255, 255), width=4)


def holding_object_wide(draw: ImageDraw.ImageDraw) -> None:
    """Two separated hands around a wide object, avoiding crossed fingers."""
    left_wrist, right_wrist = (255, 760), (465, 760)
    draw_torso(draw, ((225, 408), (495, 408)), ((235, 585), (485, 585)), (left_wrist, right_wrist))
    draw_hand(draw, left_wrist, 1)
    draw_hand(draw, right_wrist, -1)
    draw.rounded_rectangle((300, 650, 420, 765), radius=12, outline=(255, 255, 255), width=4)
    draw.ellipse((415, 680, 458, 735), outline=(255, 255, 255), width=4)


def writing_at_table(draw: ImageDraw.ImageDraw) -> None:
    left_wrist, right_wrist = (270, 875), (435, 855)
    draw_torso(draw, ((245, 410), (475, 410)), ((250, 640), (480, 650)), (left_wrist, right_wrist), hip=(360, 820))
    draw_hand(draw, left_wrist, 1, raised=False)
    draw_hand(draw, right_wrist, -1, raised=False)
    draw.line((135, 930, 590, 930), fill=(255, 255, 255), width=5)
    draw.polygon(((295, 830), (445, 830), (485, 900), (255, 900)), outline=(255, 255, 255), width=4)
    draw.line((425, 846, 463, 892), fill=(255, 255, 255), width=4)


POSES = {
    "holding_object": holding_object,
    "holding_object_wide": holding_object_wide,
    "writing_at_table": writing_at_table,
}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("pose", choices=POSES)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    canvas = Image.new("RGB", (WIDTH, HEIGHT), "black")
    POSES[args.pose](ImageDraw.Draw(canvas))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(args.output)


if __name__ == "__main__":
    main()
