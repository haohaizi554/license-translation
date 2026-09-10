from __future__ import annotations

from dataclasses import dataclass, asdict
from pathlib import Path

import cv2
import numpy as np

KEYWORDS = [
    "营业执照",
    "统一社会",
    "信用代码",
    "法定代表人",
    "经营范围",
    "注册资本",
    "成立日期",
    "登记机关",
]


@dataclass
class OcrLine:
    text: str
    score: float
    x0: float
    y0: float
    x1: float
    y1: float

    @property
    def cx(self) -> float:
        return (self.x0 + self.x1) / 2

    @property
    def cy(self) -> float:
        return (self.y0 + self.y1) / 2

    def to_dict(self) -> dict:
        return asdict(self)


def _read_image(path: str | Path) -> np.ndarray:
    data = np.fromfile(str(path), dtype=np.uint8)
    img = cv2.imdecode(data, cv2.IMREAD_COLOR)
    if img is None:
        raise FileNotFoundError(f"Cannot read image: {path}")
    return img


def _run_ocr(ocr, image: np.ndarray) -> list[OcrLine]:
    result, _elapse = ocr(image)
    lines: list[OcrLine] = []
    for box, text, score in result or []:
        text = (text or "").strip()
        if not text:
            continue
        xs = [p[0] for p in box]
        ys = [p[1] for p in box]
        lines.append(
            OcrLine(
                text=text,
                score=float(score),
                x0=float(min(xs)),
                y0=float(min(ys)),
                x1=float(max(xs)),
                y1=float(max(ys)),
            )
        )
    return lines


def _keyword_hits(lines: list[OcrLine]) -> int:
    blob = "".join(line.text for line in lines)
    return sum(1 for key in KEYWORDS if key in blob)


class LicenseOCR:
    def __init__(self) -> None:
        from rapidocr_onnxruntime import RapidOCR

        self._ocr = RapidOCR()

    def recognize(self, path: str | Path) -> tuple[np.ndarray, list[OcrLine]]:
        image = _read_image(path)
        best_img = image
        best_lines: list[OcrLine] = []
        best_score = (-1, -1, -1)
        for k in range(4):
            rotated = np.ascontiguousarray(np.rot90(image, k))
            lines = _run_ocr(self._ocr, rotated)
            hits = _keyword_hits(lines)
            horiz = sum(1 for line in lines if (line.x1 - line.x0) > (line.y1 - line.y0) * 1.2)
            score = (hits, horiz, len(lines))
            if score > best_score:
                best_score = score
                best_img = rotated
                best_lines = lines
        best_lines.sort(key=lambda line: (round(line.y0 / 18), line.x0))
        return best_img, best_lines
