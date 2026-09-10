from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

import cn2an

from .divisions import consume_admin, snap_text, zh_to_en

ROOT = Path(__file__).resolve().parent.parent
GLOSSARY = ROOT / "glossary"

MONTHS = [
    "",
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
]

ONES = ["", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine"]
TEENS = [
    "Ten",
    "Eleven",
    "Twelve",
    "Thirteen",
    "Fourteen",
    "Fifteen",
    "Sixteen",
    "Seventeen",
    "Eighteen",
    "Nineteen",
]
TENS = ["", "", "Twenty", "Thirty", "Forty", "Fifty", "Sixty", "Seventy", "Eighty", "Ninety"]

DATE_RE = re.compile(r"(20\d{2})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日")
NUM_DATE_RE = re.compile(r"(20\d{2})[./-](\d{1,2})[./-](\d{1,2})")


@lru_cache(maxsize=None)
def _load(name: str) -> dict[str, str]:
    path = GLOSSARY / name
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _try_pinyin(text: str, heteronym: bool = False) -> str:
    try:
        from pypinyin import Style, lazy_pinyin

        parts = lazy_pinyin(text, style=Style.NORMAL)
        return "".join(p.capitalize() if i == 0 else p for i, p in enumerate(parts)) if len(text) > 1 and " " not in text else " ".join(p.capitalize() for p in parts)
    except Exception:
        return text


def person_pinyin(name: str) -> str:
    name = name.strip()
    if not name:
        return ""
    try:
        from pypinyin import Style, lazy_pinyin

        if len(name) == 1:
            return lazy_pinyin(name, style=Style.NORMAL)[0].capitalize()
        # 复姓 (common)
        doubles = ("欧阳", "司马", "上官", "诸葛", "东方", "皇甫", "尉迟", "公孙", "慕容", "司徒")
        if name.startswith(doubles):
            family, given = name[:2], name[2:]
        else:
            family, given = name[0], name[1:]
        fam = "".join(lazy_pinyin(family, style=Style.NORMAL)).capitalize()
        giv = "".join(lazy_pinyin(given, style=Style.NORMAL)).capitalize()
        return f"{fam} {giv}".strip()
    except Exception:
        return name


def _replace_longest(text: str, table: dict[str, str]) -> str:
    if not text:
        return text
    keys = sorted(table, key=len, reverse=True)
    i = 0
    out: list[str] = []
    while i < len(text):
        matched = False
        for key in keys:
            if text.startswith(key, i):
                out.append(table[key])
                i += len(key)
                matched = True
                break
        if not matched:
            out.append(text[i])
            i += 1
    return "".join(out)


def translate_date(text: str) -> str:
    if not text:
        return ""
    match = DATE_RE.search(text) or NUM_DATE_RE.search(text)
    if not match:
        return text
    year, month, day = (int(match.group(1)), int(match.group(2)), int(match.group(3)))
    return f"{MONTHS[month]} {day}, {year}"


def _under_thousand(n: int) -> str:
    hundred, rest = divmod(n, 100)
    pieces: list[str] = []
    if hundred:
        pieces.append(f"{ONES[hundred]} Hundred")
    if rest >= 20:
        ten, one = divmod(rest, 10)
        pieces.append(TENS[ten] + (f"-{ONES[one]}" if one else ""))
    elif rest >= 10:
        pieces.append(TEENS[rest - 10])
    elif rest:
        pieces.append(ONES[rest])
    return " ".join(pieces)


def integer_to_words(n: int) -> str:
    if n == 0:
        return "Zero"
    scales = [
        (1_000_000_000, "Billion"),
        (1_000_000, "Million"),
        (1_000, "Thousand"),
    ]
    parts: list[str] = []
    for value, name in scales:
        qty, n = divmod(n, value)
        if qty:
            parts.append(f"{_under_thousand(qty)} {name}".strip())
    if n:
        parts.append(_under_thousand(n))
    return " ".join(parts)


def translate_capital(text: str) -> str:
    raw = (text or "").strip()
    if not raw:
        return ""
    compact = raw.replace(" ", "").replace("圆", "元").replace("人民幣", "人民币")
    currency = "CNY"
    currency_map = [
        (("美元", "USD"), "USD"),
        (("港币", "港元", "HKD"), "HKD"),
        (("欧元", "EUR"), "EUR"),
        (("日元", "JPY"), "JPY"),
        (("英镑", "GBP"), "GBP"),
        (("澳门元", "澳元", "MOP"), "MOP"),
        (("人民币", "CNY", "RMB"), "CNY"),
    ]
    for keys, code in currency_map:
        if any(k in compact for k in keys):
            currency = code
            break
    number_part = compact
    for token in ("人民币", "CNY", "RMB", "美元", "USD", "港币", "港元", "HKD", "欧元", "EUR", "日元", "JPY", "英镑", "GBP", "整", "元", "正", "认缴"):
        number_part = number_part.replace(token, "")
    number_part = number_part.replace("万元", "万")
    amount = None
    try:
        if re.fullmatch(r"[\d.,]+万?", number_part):
            if number_part.endswith("万"):
                amount = int(float(number_part[:-1]) * 10000)
            else:
                amount = int(float(number_part.replace(",", "")))
        else:
            amount = int(cn2an.cn2an(number_part, "smart"))
    except Exception:
        try:
            amount = int(cn2an.transform(number_part + "元", "cn2an").replace("元", "") or 0)
        except Exception:
            amount = None
    if amount is None:
        return f"{currency} {raw}"
    return f"{currency} {integer_to_words(amount)} Only"


def translate_type(text: str) -> str:
    compact = (text or "").replace(" ", "").replace("（", "(").replace("）", ")")
    table = _load("types.json")
    if compact in table:
        return table[compact]
    atoms = _load("type_atoms.json")
    match = re.match(r"(一人有限责任公司|有限责任公司|股份有限公司)(?:\((.+)\))?$", compact)
    if match:
        head = atoms.get(match.group(1), table.get(match.group(1), match.group(1)))
        if not match.group(2):
            return head
        mods = [part.strip() for part in re.split(r"[、,;；]", match.group(2)) if part.strip()]
        en_mods = []
        for part in mods:
            if part in atoms:
                en_mods.append(atoms[part])
            else:
                en_mods.append(_replace_longest(part, atoms))
        return f"{head} ({'; '.join(en_mods)})"
    merged = {**atoms, **table}
    return _replace_longest(compact, merged) or text


def translate_person(text: str) -> str:
    name = (text or "").strip()
    people = _load("people.json")
    if name in people:
        return people[name]
    return person_pinyin(name)


def translate_company(text: str) -> str:
    name = snap_text((text or "").strip())
    companies = _load("companies.json")
    if name in companies:
        return companies[name]
    places = zh_to_en()
    words = _load("words.json")
    work = name
    out: list[str] = []
    keys = sorted({**places, **words}, key=len, reverse=True)
    i = 0
    unknown: list[str] = []

    def flush_unknown() -> None:
        chunk = "".join(unknown)
        unknown.clear()
        if not chunk:
            return
        if chunk.endswith("市") and chunk in places:
            out.append(places[chunk].replace(" City", ""))
            return
        if chunk in places:
            token = places[chunk]
            for extra in (" Province", " City", " District", " County"):
                token = token.replace(extra, "")
            out.append(token)
            return
        py = person_pinyin(chunk).replace(" ", "")
        out.append(py)

    while i < len(work):
        matched = None
        for key in keys:
            if work.startswith(key, i):
                matched = key
                break
        if matched:
            flush_unknown()
            table = words if matched in words else places
            token = table[matched]
            if matched in places:
                token = token.replace(" Province", "").replace(" City", "").replace(" District", "")
            out.append(token)
            i += len(matched)
        else:
            unknown.append(work[i])
            i += 1
    flush_unknown()
    # ensure Co., Ltd. if original had 公司 and we missed it
    joined = " ".join(part for part in out if part)
    if "公司" in name and "Co." not in joined:
        joined = f"{joined} Co., Ltd."
    return re.sub(r"\s+", " ", joined).strip(" ,")


def translate_scope(text: str) -> str:
    compact = (text or "").replace(" ", "")
    compact = compact.replace("：", ":")
    compact = re.sub(r"(许可经营项目|一般经营项目|许可项目|一般项目)[:：]", r"\1:", compact)
    compact = compact.replace("：", "、").replace(":", "、")
    compact = compact.replace("许可经营项目、", "许可经营项目：").replace("一般经营项目、", "一般经营项目：")
    compact = compact.replace("许可项目、", "许可项目：").replace("一般项目、", "一般项目：")
    translated = _replace_longest(compact, _load("phrases.json"))
    translated = translated.replace("、", "; ").replace("，", "; ")
    translated = translated.replace("：", ": ")
    translated = translated.replace(":", ": ")
    translated = re.sub(r"\s+", " ", translated)
    translated = translated.replace(" ;", ";").replace("; ", "; ")
    # add spaces after Chinese leftovers turned into latin glued punctuation
    translated = re.sub(r"([a-z])([A-Z])", r"\1 \2", translated)
    translated = translated.replace("items:", "items:").replace("Licensed items:", "Licensed items:")
    translated = translated.replace("General items:", "General items:")
    translated = re.sub(r"([a-z])\(", r"\1 (", translated)
    translated = re.sub(r"\)([A-Za-z])", r") \1", translated)
    return translated.strip()



STREET_SUFFIXES = (
    ("高新技术产业开发区", "High-tech Industrial Development Zone"),
    ("经济技术开发区", "Economic and Technological Development Zone"),
    ("经济开发区", "Economic Development Zone"),
    ("高新技术产业园", "High-tech Industrial Park"),
    ("工业园区", "Industrial Park"),
    ("科技园区", "Science Park"),
    ("高新区", "High-tech Zone"),
    ("开发区", "Development Zone"),
    ("工业园", "Industrial Park"),
    ("科技园", "Science Park"),
    ("大学城", "University Town"),
    ("商务区", "Business District"),
    ("保税区", "Bonded Zone"),
    ("度假区", "Resort Area"),
    ("风景区", "Scenic Area"),
    ("步行街", "Pedestrian Street"),
    ("街道", "Subdistrict"),
    ("大街", "Street"),
    ("大道", "Avenue"),
    ("南路", "South Road"),
    ("北路", "North Road"),
    ("东路", "East Road"),
    ("西路", "West Road"),
    ("中路", "Middle Road"),
    ("路", "Road"),
    ("街", "Street"),
    ("巷", "Alley"),
    ("道", "Road"),
    ("弄", "Lane"),
    ("里", "Li"),
    ("胡同", "Hutong"),
    ("社区", "Community"),
    ("镇", "Town"),
    ("乡", "Township"),
    ("村", "Village"),
    ("庄", "Village"),
)

UNIT_SUFFIXES = {
    "铺": "Shop {num}",
    "号铺": "Shop {num}",
    "号": "No. {num}",
    "号楼": "Building {num}",
    "号院": "Yard {num}",
    "室": "Room {num}",
    "层": "{num}F",
    "幢": "Building {num}",
    "栋": "Building {num}",
    "座": "Block {num}",
    "单元": "Unit {num}",
    "F": "{num}F",
    "楼": "{num}F",
}


def place_pinyin(text: str) -> str:
    compact = (text or "").strip()
    if not compact:
        return ""
    try:
        from pypinyin import Style, lazy_pinyin

        joined = "".join(lazy_pinyin(compact, style=Style.NORMAL))
        return joined[:1].upper() + joined[1:] if joined else compact
    except Exception:
        return compact


def _street_glossary() -> dict[str, str]:
    extra = _load("places.json")
    admin = zh_to_en()
    return {key: value for key, value in extra.items() if key not in admin}


def translate_address(text: str, prefer: list[str] | None = None) -> str:
    raw = snap_text((text or "").replace(" ", ""), prefer)
    if not raw:
        return ""
    places = zh_to_en()
    admin, rest = consume_admin(raw, prefer)
    admin_en = [places.get(token, token) for token in admin]
    units = re.findall(
        r"(\d+[A-Za-z]?(?:-\d+[A-Za-z]?)?)(号铺|号楼|号院|号|铺|室|层|幢|栋|座|单元|楼)",
        rest,
    )
    unit_en = []
    for num, kind in units:
        unit_en.append(UNIT_SUFFIXES.get(kind, "{num}").format(num=num))
        rest = rest.replace(f"{num}{kind}", "", 1)
    overlay = {**places, **_street_glossary()}
    keys = sorted(overlay, key=len, reverse=True)
    rest_bits: list[str] = []
    i = 0
    buf = ""

    def flush() -> None:
        nonlocal buf
        if buf:
            rest_bits.append(place_pinyin(buf))
            buf = ""

    while i < len(rest):
        hit = next((key for key in keys if rest.startswith(key, i) and len(key) >= 2), None)
        suffix = next((pair for pair in STREET_SUFFIXES if rest.startswith(pair[0], i)), None)
        if suffix and (not hit or len(suffix[0]) >= len(hit)):
            prefix = buf
            buf = ""
            token = f"{place_pinyin(prefix)} {suffix[1]}".strip() if prefix else suffix[1]
            rest_bits.append(token)
            i += len(suffix[0])
            continue
        if hit:
            flush()
            rest_bits.append(overlay[hit])
            i += len(hit)
        elif "\u4e00" <= rest[i] <= "\u9fff":
            buf += rest[i]
            i += 1
        else:
            flush()
            if rest[i] not in " ,，、":
                rest_bits.append(rest[i])
            i += 1
    flush()
    rest_bits = [bit.strip(" ,") for bit in reversed(rest_bits) if bit.strip(" ,")]
    ordered = unit_en + rest_bits + list(reversed(admin_en))
    return ", ".join(part for part in ordered if part)


def translate_term(text: str) -> str:
    raw = (text or '').replace(' ', '')
    if not raw:
        return ''
    if raw in {'长期', '永久', '无固定期限'}:
        return 'Long term'
    if '至长期' in raw or '到长期' in raw:
        start = re.search(r'(20\d{2}年\d{1,2}月\d{1,2}日)', raw)
        if start:
            return f'{translate_date(start.group(1))} to Long term'
        return 'Long term'
    span = re.findall(r'20\d{2}年\d{1,2}月\d{1,2}日', raw)
    if len(span) >= 2:
        return f'{translate_date(span[0])} to {translate_date(span[1])}'
    return translate_date(raw) or raw


def translate_authority(text: str, address: str = '', name: str = '') -> str:
    raw = snap_text((text or '').replace(' ', ''))
    places = zh_to_en()
    m = re.search(r'(.+?)(市场监督管理局|市场监督管理分局|工商行政管理局)', raw)
    if m and '监制' not in raw:
        place = m.group(1)
        bureau = 'Municipal Market Supervision and Administration Bureau'
        if '分局' in m.group(2):
            bureau = 'Market Supervision and Administration Branch'
        elif '工商' in m.group(2):
            bureau = 'Administration for Industry and Commerce'
        en = places.get(place) or places.get(place + '市') or places.get(place[:-1] if place.endswith('市') else place)
        if not en:
            en = person_pinyin(place.replace('市', '')).replace(' ', '')
        en = str(en).replace(' City', '').replace(' Province', '').replace(' District', '').strip()
        return f'{en} {bureau} (Sealed)'
    hint = snap_text((address or "") + (name or ""))
    for city in sorted((key for key in places if key.endswith("市") and len(key) >= 3), key=len, reverse=True):
        if city in hint:
            return translate_authority(city + "市场监督管理局")
    return ""


def translate_fields(fields) -> dict:
    data = fields.to_dict() if hasattr(fields, 'to_dict') else dict(fields)
    from .divisions import places_from_usci

    prefer = places_from_usci(data.get("credit_code") or "")
    address_en = translate_address(data.get("address") or "", prefer)
    scope = translate_scope(data.get('scope') or '')
    leftover = re.findall(r"[\u4e00-\u9fff]+", scope)
    warnings = list(data.get("warnings") or [])
    if leftover:
        warnings.append("scope_untranslated")
    authority = translate_authority(data.get("authority") or "", data.get("address") or "", data.get("name") or "")
    if authority and "authority" in warnings:
        warnings.remove("authority")
    return {
        "credit_code": data.get("credit_code") or "",
        "copy_no": data.get("copy_no") or "1-1",
        "duplicate": bool(data.get("duplicate", False)),
        "name": translate_company(data.get("name") or ""),
        "type": translate_type(data.get("type") or ""),
        "legal_person": translate_person(data.get("legal_person") or ""),
        "scope": scope,
        "capital": translate_capital(data.get("capital") or ""),
        "established": translate_date(data.get("established") or ""),
        "address": address_en,
        "term": translate_term(data.get("term") or ""),
        "authority": authority,
        "issue_date": translate_date(data.get("issue_date") or ""),
        "warnings": warnings,
        "source": {k: data.get(k) for k in ("credit_code", "name", "type", "legal_person", "scope", "capital", "established", "address", "authority", "issue_date", "term")},
    }
