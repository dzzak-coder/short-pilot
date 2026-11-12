"""Local hand-landmark quality signal for candidate image selection.

This is a rejection signal, not a claim that every detected hand is perfect:
it rejects scenes where the local landmark model cannot find exactly the
expected number of hands.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import mediapipe as mp


def score(image_path: Path, model_path: Path, expected_hands: int) -> dict[str, object]:
    base_options = mp.tasks.BaseOptions(model_asset_path=str(model_path))
    options = mp.tasks.vision.HandLandmarkerOptions(
        base_options=base_options,
        running_mode=mp.tasks.vision.RunningMode.IMAGE,
        num_hands=expected_hands,
        min_hand_detection_confidence=0.60,
        min_hand_presence_confidence=0.60,
    )
    image = mp.Image.create_from_file(str(image_path))
    with mp.tasks.vision.HandLandmarker.create_from_options(options) as detector:
        result = detector.detect(image)
    count = len(result.hand_landmarks)
    return {
        "path": str(image_path),
        "hands_detected": count,
        "landmarks_per_hand": [len(hand) for hand in result.hand_landmarks],
        "passes_structural_gate": count == expected_hands
        and all(len(hand) == 21 for hand in result.hand_landmarks),
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("image", type=Path)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--hands", type=int, default=2)
    args = parser.parse_args()
    print(json.dumps(score(args.image, args.model, args.hands), ensure_ascii=False))
