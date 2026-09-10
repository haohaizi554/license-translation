from __future__ import annotations

import re
from dataclasses import dataclass, field, asdict

from .ocr import OcrLine
from .divisions import places_from_usci, snap_text
from .usci import checksum_ok, repair_usci

OCR_FIXES = (
    ("衣副产品", "农副产品"),
    ("农副产品销售：", "农副产品销售、"),
    ("日用百货销售：", "日用百货销售、"),
    ("食品生产：", "食品生产、"),
    ("食品销售：", "食品销售、"),
)

NOISE_RE = re.compile(
    r"(SCJDGL|SIDGL|SODGL|SOJDGL|SUJDGL|SCJDGI|SCJDG|JDGL|OGL|DGL|SJD)",
    re.I,
)

CREDIT_RE = re.compile(
    r"([0-9A-HJ-NPQRTUWXY]{2}\d{6}[0-9A-HJ-NPQRTUWXY]{10})(?:\s*[\(（]\s*(\d+\s*-\s*\d+)\s*[\)）])?"
)
DATE_RE = re.compile(r"(20\d{2})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日")
COPY_RE = re.compile(r"[\(（]\s*(\d+\s*-\s*\d+)\s*[\)）]")

KEYS = [
    ("credit_label", ("统一社会信用代码", "社会信用代码", "信用代码")),
    ("name", ("名称", "名 称")),
    ("type", ("类型", "类 型")),
    ("legal_person", ("法定代表人",)),
    ("scope", ("经营范围", "经 营 范 围")),
    ("capital", ("注册资本", "注册资金")),
    ("established", ("成立日期", "注册日期")),
    ("address", ("住所",)),
    ("term", ("营业期限", "经营期限")),
    ("authority", ("登记机关",)),
]


def _fix_ocr_text(text: str) -> str:
    for src, dst in OCR_FIXES:
        text = text.replace(src, dst)
    text = re.sub(r"(\d+[A-Za-z]?(?:-\d+[A-Za-z]?)?)销", r"\1铺", text)
    return text


def _is_noise(line: OcrLine) -> bool:
    compact = _norm(line.text)
    if NOISE_RE.fullmatch(compact) or NOISE_RE.fullmatch(line.text.strip()):
        return True
    if compact in {"市场监督", "市场监督管理"} and (line.x1 - line.x0) > 150:
        return True
    if "监制" in compact:
        return True
    if compact.startswith("http") or "gsxt" in compact.lower():
        return True
    if compact in {"营业执照", "电子营业执照", "国家市场监督管理总局监制"}:
        return True
    return False


def _norm(text: str) -> str:
    return (
        text.replace(" ", "")
        .replace("　", "")
        .replace("：", ":")
        .replace("（", "(")
        .replace("）", ")")
        .strip()
    )


def _clean_value(text: str) -> str:
    text = text.strip(" :：;；|-_")
    text = re.sub(r"^(名称|类型|法定代表人|经营范围|注册资本|注册资金|成立日期|住所|营业期限|经营期限|登记机关)[:：]?", "", text)
    return text.strip()


def _find_key_line(lines: list[OcrLine], labels: tuple[str, ...]) -> OcrLine | None:
    for line in lines:
        compact = _norm(line.text)
        for label in labels:
            if compact.startswith(_norm(label)) or _norm(label) == compact:
                return line
    for line in lines:
        compact = _norm(line.text)
        for label in labels:
            if _norm(label) in compact[:12]:
                return line
    return None


def _value_after_key(line: OcrLine, labels: tuple[str, ...]) -> str:
    text = line.text
    for label in sorted(labels, key=len, reverse=True):
        idx = _norm(text).find(_norm(label))
        if idx >= 0:
            # map back approximately by stripping label from original
            raw = re.sub(r"\s+", "", text)
            lab = _norm(label)
            if raw.startswith(lab) or lab in raw:
                leftover = raw[raw.find(lab) + len(lab) :]
                leftover = leftover.lstrip(":：")
                if leftover:
                    return leftover
    parts = re.split(r"[:：]", text, maxsplit=1)
    if len(parts) == 2 and parts[1].strip():
        return parts[1].strip()
    return ""


def _lines_right_or_below(lines: list[OcrLine], key: OcrLine, stop: list[OcrLine], max_dy: float = 80) -> list[OcrLine]:
    stop_y = min((s.y0 for s in stop if s.y0 > key.y0 + 8), default=key.y0 + 400)
    height = max(12.0, key.y1 - key.y0)
    chosen: list[OcrLine] = []
    for line in lines:
        if line is key:
            continue
        if line.y0 >= stop_y - 4:
            continue
        same_row = abs(line.cy - key.cy) < height * 1.2 and line.x0 >= key.x1 - 8
        below = key.y0 - 4 < line.y0 < stop_y and line.x0 >= key.x0 - 20 and line.cx > key.cx
        if same_row or below:
            if line.y0 <= key.y0 + max_dy or same_row:
                chosen.append(line)
    chosen.sort(key=lambda item: (round(item.y0 / 12), item.x0))
    return chosen


def _join(parts: list[str]) -> str:
    out: list[str] = []
    for part in parts:
        part = _clean_value(part)
        if not part:
            continue
        if out and out[-1].endswith(("，", ",", "、", ";", "；")):
            out.append(part)
        elif out and part.startswith(("，", ",", "、")):
            out[-1] += part
        else:
            out.append(part)
    return "".join(out) if any("许可" in p or "一般" in p or "项目" in p for p in out) else " ".join(out) if False else "".join(out)


@dataclass
class LicenseFields:
    credit_code: str = ""
    copy_no: str = "1-1"
    name: str = ""
    type: str = ""
    legal_person: str = ""
    scope: str = ""
    capital: str = ""
    established: str = ""
    address: str = ""
    term: str = ""
    authority: str = ""
    issue_date: str = ""
    duplicate: bool = False
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def parse_license(lines: list[OcrLine]) -> LicenseFields:
    fields = LicenseFields()
    for line in lines:
        line.text = _fix_ocr_text(line.text)
    raw_blob = "".join(line.text for line in lines)
    if "副本" in raw_blob:
        fields.duplicate = True
    elif "正本" in raw_blob:
        fields.duplicate = False
    lines = [line for line in lines if not _is_noise(line)]
    blob = "".join(line.text for line in lines)

    credit = CREDIT_RE.search(blob.replace(" ", ""))
    if credit:
        fields.credit_code = repair_usci(credit.group(1))
        if not checksum_ok(fields.credit_code):
            fields.warnings.append("credit_code_checksum")
        if credit.group(2):
            fields.copy_no = re.sub(r"\s+", "", credit.group(2))
    else:
        fields.warnings.append("credit_code")

    copy = COPY_RE.search(blob)
    if copy:
        fields.copy_no = re.sub(r"\s+", "", copy.group(1))

    parsed = [(int(y), int(m), int(d)) for y, m, d in DATE_RE.findall(blob)]
    if parsed:
        parsed.sort()
        fields.established = f"{parsed[0][0]:04d}年{parsed[0][1]:02d}月{parsed[0][2]:02d}日"
        later = [item for item in parsed if item != parsed[0]]
        if later:
            fields.issue_date = f"{later[-1][0]:04d}年{later[-1][1]:02d}月{later[-1][2]:02d}日"

    key_lines: dict[str, OcrLine] = {}
    for name, labels in KEYS:
        found = _find_key_line(lines, labels)
        if found:
            key_lines[name] = found

    ordered_keys = [key_lines[name] for name, _ in KEYS if name in key_lines]

    def grab(name: str, labels: tuple[str, ...], extra_stop: tuple[str, ...] = ()) -> str:
        key = key_lines.get(name)
        if not key:
            fields.warnings.append(name)
            return ""
        inline = _value_after_key(key, labels)
        stops = [key_lines[other] for other in extra_stop if other in key_lines]
        stops += [k for k in ordered_keys if k is not key and k.y0 > key.y0]
        nearby = _lines_right_or_below(lines, key, stops, max_dy=220 if name == "scope" else 90)
        parts = [inline] + [item.text for item in nearby]
        filtered: list[str] = []
        for part in parts:
            part = part.strip()
            if not part:
                continue
            compact = _norm(part)
            if any(_norm(lab) == compact for _, labs in KEYS for lab in labs):
                continue
            if NOISE_RE.fullmatch(compact):
                continue
            filtered.append(part)
        value = _clean_value("".join(filtered) if name in {"scope", "address"} else (filtered[0] if filtered else ""))
        if name in {"scope", "address"}:
            value = _clean_value("".join(_clean_value(p) for p in filtered))
        return value

    prefer = places_from_usci(fields.credit_code)
    fields.name = grab("name", ("名称", "名 称"), ("type", "legal_person"))
    fields.type = grab("type", ("类型", "类 型"), ("legal_person", "scope"))
    fields.legal_person = grab("legal_person", ("法定代表人",), ("scope", "capital"))
    fields.scope = grab("scope", ("经营范围",), ("capital", "authority", "term"))
    fields.capital = grab("capital", ("注册资本", "注册资金"), ("established", "address"))
    established = grab("established", ("成立日期", "注册日期"), ("address", "authority"))
    if DATE_RE.search(established or ""):
        fields.established = established
    fields.address = snap_text(grab("address", ("住所",), ("authority",)), prefer)
    fields.term = grab("term", ("营业期限", "经营期限"), ("authority",))
    if "term" in fields.warnings:
        fields.warnings.remove("term")
    fields.name = snap_text(fields.name, prefer)
    authority = grab("authority", ("登记机关",))
    if authority and "局" in authority and "监制" not in authority:
        fields.authority = authority
    else:
        fields.authority = ""
        fields.warnings.append("authority")

    # Fallbacks when a label was seen but the value box was empty / noisy.
    if not fields.name:
        for line in lines:
            compact = _norm(line.text)
            if re.search(r"(有限公司|股份有限公司|合伙企业)$", compact) and "责任公司（" not in compact and "责任公司(" not in compact:
                fields.name = snap_text(_clean_value(line.text), places_from_usci(fields.credit_code))
                if "name" in fields.warnings:
                    fields.warnings.remove("name")
                break
    if not fields.address:
        for line in lines:
            if re.search(r"省.+市.+", _norm(line.text)) and "公示" not in line.text:
                fields.address = snap_text(_clean_value(re.sub(r"^住所[:：]?", "", line.text)), places_from_usci(fields.credit_code))
                if "address" in fields.warnings:
                    fields.warnings.remove("address")
                break
    if fields.scope:
        fields.scope = re.sub(r"[A-Za-z]{2,}$", "", fields.scope)
        if not fields.scope.endswith("）") and "限制的项目" in fields.scope:
            fields.scope += "）"

    for attr in ("name", "type", "legal_person", "scope", "capital", "address"):
        if not getattr(fields, attr):
            if attr not in fields.warnings:
                fields.warnings.append(attr)

    if not fields.issue_date:
        fields.warnings.append("issue_date")

    return fields


def refine_issue_date(fields: LicenseFields, extra_text: str) -> LicenseFields:
    blob = extra_text.replace(" ", "")
    match = DATE_RE.search(blob)
    if not match:
        year = re.search(r"(20\d{2})\s*年", extra_text)
        month_day = re.search(r"(\d{1,2})\s*月\s*(\d{1,2})", extra_text)
        if year and month_day:
            match = year
            fields.issue_date = (
                f"{int(year.group(1)):04d}年{int(month_day.group(1)):02d}月{int(month_day.group(2)):02d}日"
            )
            if "issue_date" in fields.warnings:
                fields.warnings.remove("issue_date")
            return fields
        return fields
    fields.issue_date = f"{int(match.group(1)):04d}年{int(match.group(2)):02d}月{int(match.group(3)):02d}日"
    if "issue_date" in fields.warnings:
        fields.warnings.remove("issue_date")
    return fields
