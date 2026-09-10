from __future__ import annotations

import json
import logging
from datetime import date
from pathlib import Path

import cv2

from .classify import NotFormatA, classify_format_a
from .ocr import LicenseOCR, OcrLine, _run_ocr
from .parse import parse_license
from .render import render_pdf
from .translate import translate_fields

ROOT = Path(__file__).resolve().parent.parent
LOG = logging.getLogger("license_trans")


def load_config(path: str | Path | None = None) -> dict:
    cfg = Path(path) if path else ROOT / "config.json"
    return json.loads(cfg.read_text(encoding="utf-8"))


def _crop_qr(image_bgr, lines: list[OcrLine]) -> bytes | None:
    h, w = image_bgr.shape[:2]
    detector = cv2.QRCodeDetector()
    _data, points, _ = detector.detectAndDecode(image_bgr)
    if points is None:
        return None
    pts = points.reshape(-1, 2)
    x0, y0 = int(max(0, pts[:, 0].min() - 8)), int(max(0, pts[:, 1].min() - 8))
    x1, y1 = int(min(w, pts[:, 0].max() + 8)), int(min(h, pts[:, 1].max() + 8))
    if (x1 - x0) > 280 or (y1 - y0) > 280 or (x1 - x0) < 40:
        return None
    crop = image_bgr[y0:y1, x0:x1]
    ok, buf = cv2.imencode(".png", crop)
    return buf.tobytes() if ok else None


def _recover_issue_date(image, lines, engine) -> str:
    import re

    year_ln = next((ln for ln in lines if re.fullmatch(r"20\d{2}年", ln.text.replace(" ", ""))), None)
    day_ln = next((ln for ln in lines if re.match(r"月\s*\d{1,2}", ln.text.replace(" ", ""))), None)
    if year_ln is None or day_ln is None:
        blob = "".join(ln.text for ln in lines)
        from .parse import DATE_RE
        match = DATE_RE.search(blob)
        return match.group(0) if match else ""
    year = re.search(r"20\d{2}", year_ln.text).group(0)
    day = re.search(r"(\d{1,2})", day_ln.text).group(1)
    month = ""
    h, w = image.shape[:2]
    x0 = int(max(0, year_ln.x1 - 6))
    x1 = int(min(w, day_ln.x0 + 8))
    y0 = int(max(0, min(year_ln.y0, day_ln.y0) - 8))
    y1 = int(min(h, max(year_ln.y1, day_ln.y1) + 8))
    if x1 > x0 + 4:
        gap = image[y0:y1, x0:x1]
        if gap.size:
            gap = cv2.resize(gap, None, fx=5.0, fy=5.0, interpolation=cv2.INTER_CUBIC)
            gray = cv2.cvtColor(gap, cv2.COLOR_BGR2GRAY)
            _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
            gap_bgr = cv2.cvtColor(binary, cv2.COLOR_GRAY2BGR)
            for item in _run_ocr(engine._ocr, gap_bgr) + _run_ocr(engine._ocr, gap):
                found = re.search(r"\b(1[0-2]|0?[1-9])\b", item.text)
                if found:
                    month = found.group(1)
                    break
    if not month:
        for ln in lines:
            if ln is year_ln or ln is day_ln:
                continue
            if abs(ln.cy - year_ln.cy) < 24 and year_ln.x1 - 8 <= ln.cx <= day_ln.x0 + 8:
                found = re.search(r"(1[0-2]|0?[1-9])", ln.text)
                if found:
                    month = found.group(1)
                    break
    if not month:
        return ""
    return f"{int(year):04d}年{int(month):02d}月{int(day):02d}日"


def _normalize_issue_date(text: str) -> str:
    import re

    text = text.strip()
    match = re.fullmatch(r"(20\d{2})[-/.](\d{1,2})[-/.](\d{1,2})", text)
    if match:
        return f"{int(match.group(1)):04d}年{int(match.group(2)):02d}月{int(match.group(3)):02d}日"
    match = re.search(r"(20\d{2})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日?", text)
    if match:
        return f"{int(match.group(1)):04d}年{int(match.group(2)):02d}月{int(match.group(3)):02d}日"
    return text


def convert_image(
    image_path: str | Path,
    output_path: str | Path,
    *,
    config_path: str | Path | None = None,
    work_dir: str | Path | None = None,
    ocr: LicenseOCR | None = None,
    translation_date: date | None = None,
    issue_date: str | None = None,
) -> dict:
    image_path = Path(image_path)
    output_path = Path(output_path)
    config = load_config(config_path)
    LOG.info("读取 %s", image_path.name)
    engine = ocr or LicenseOCR()
    LOG.info("OCR 四向纠偏…")
    oriented, lines = engine.recognize(image_path)
    LOG.info("识别 %d 行文字", len(lines))
    fields = parse_license(lines)
    blob = "".join(line.text for line in lines)
    classify_format_a(fields, blob)
    issue = _recover_issue_date(oriented, lines, engine)
    if issue_date:
        fields.issue_date = _normalize_issue_date(issue_date)
        if "issue_date" in fields.warnings:
            fields.warnings.remove("issue_date")
        LOG.info("发证日期（指定）%s", fields.issue_date)
    elif issue:
        fields.issue_date = issue
        if "issue_date" in fields.warnings:
            fields.warnings.remove("issue_date")
        LOG.info("发证日期（识别）%s", fields.issue_date)
    elif not fields.issue_date:
        LOG.warning("发证日期未识别，可在面板里指定")
    english = translate_fields(fields)
    LOG.info("译文  %s", english.get("name") or "（无名称）")
    qr_bytes = _crop_qr(oriented, lines)
    LOG.info("渲染英文模板 PDF")
    render_pdf(
        english,
        config,
        output_path,
        original_image=image_path,
        oriented_bgr=oriented,
        qr_bytes=qr_bytes,
        translation_date=translation_date,
    )
    result = {
        "input": str(image_path),
        "output": str(output_path),
        "fields": fields.to_dict(),
        "english": english,
        "ocr": [line.to_dict() for line in lines],
    }
    if work_dir:
        work_dir = Path(work_dir)
        work_dir.mkdir(parents=True, exist_ok=True)
        sidecar = work_dir / (output_path.stem + ".json")
        sidecar.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        # preview of oriented source
        preview = work_dir / (output_path.stem + "-oriented.jpg")
        cv2.imencode(".jpg", oriented)[1].tofile(str(preview))
    LOG.info("完成  %s", output_path)
    return result
