from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GLOSSARY = ROOT / "glossary"

EXCEPTIONS = {
    "北京市": "Beijing",
    "北京": "Beijing",
    "天津市": "Tianjin",
    "天津": "Tianjin",
    "上海市": "Shanghai",
    "上海": "Shanghai",
    "重庆市": "Chongqing",
    "重庆": "Chongqing",
    "内蒙古自治区": "Inner Mongolia Autonomous Region",
    "内蒙古": "Inner Mongolia",
    "广西壮族自治区": "Guangxi Zhuang Autonomous Region",
    "广西": "Guangxi",
    "西藏自治区": "Tibet Autonomous Region",
    "西藏": "Tibet",
    "宁夏回族自治区": "Ningxia Hui Autonomous Region",
    "宁夏": "Ningxia",
    "新疆维吾尔自治区": "Xinjiang Uygur Autonomous Region",
    "新疆": "Xinjiang",
    "香港特别行政区": "Hong Kong SAR",
    "香港": "Hong Kong",
    "澳门特别行政区": "Macao SAR",
    "澳门": "Macao",
    "陕西省": "Shaanxi Province",
    "陕西": "Shaanxi",
    "山西省": "Shanxi Province",
    "山西": "Shanxi",
    "西安市": "Xi'an City",
    "西安": "Xi'an",
    "呼和浩特市": "Hohhot City",
    "呼和浩特": "Hohhot",
    "乌鲁木齐市": "Urumqi City",
    "乌鲁木齐": "Urumqi",
    "拉萨市": "Lhasa City",
    "拉萨": "Lhasa",
}

SHORT_CORE = {
    "内蒙古自治区": "内蒙古",
    "广西壮族自治区": "广西",
    "西藏自治区": "西藏",
    "宁夏回族自治区": "宁夏",
    "新疆维吾尔自治区": "新疆",
    "香港特别行政区": "香港",
    "澳门特别行政区": "澳门",
}


def _pinyin_token(text: str) -> str:
    try:
        from pypinyin import Style, lazy_pinyin

        parts = lazy_pinyin(text, style=Style.NORMAL)
        if not parts:
            return text
        joined = "".join(parts)
        return joined[:1].upper() + joined[1:]
    except Exception:
        return text


def _english(name: str, kind: str) -> str:
    if name in EXCEPTIONS:
        return EXCEPTIONS[name]
    if kind == "province":
        if name.endswith("省"):
            return f"{_pinyin_token(name[:-1])} Province"
        return _pinyin_token(name)
    if kind == "city":
        if name.endswith("自治州"):
            return f"{_pinyin_token(name[:-3])} Autonomous Prefecture"
        if name.endswith("地区"):
            return f"{_pinyin_token(name[:-2])} Prefecture"
        if name.endswith("盟"):
            return f"{_pinyin_token(name[:-1])} League"
        if name.endswith("市"):
            return f"{_pinyin_token(name[:-1])} City"
        return f"{_pinyin_token(name)} City"
    if name.endswith("自治县"):
        return f"{_pinyin_token(name[:-3])} Autonomous County"
    if name.endswith("林区"):
        return f"{_pinyin_token(name[:-2])} Forestry District"
    if name.endswith("特区"):
        return f"{_pinyin_token(name[:-2])} Special District"
    if name.endswith("区"):
        return f"{_pinyin_token(name[:-1])} District"
    if name.endswith("县"):
        return f"{_pinyin_token(name[:-1])} County"
    if name.endswith("旗"):
        return f"{_pinyin_token(name[:-1])} Banner"
    if name.endswith("市"):
        return f"{_pinyin_token(name[:-1])} City"
    return _pinyin_token(name)


def _core_of(name: str) -> str | None:
    if name in SHORT_CORE:
        return SHORT_CORE[name]
    if name in EXCEPTIONS and name.endswith(("市", "省")):
        core = name[:-1]
        return core or None
    for suffix in ("自治州", "地区", "林区", "特区", "省", "市", "县", "区", "旗", "盟"):
        if name.endswith(suffix) and len(name) > len(suffix):
            core = name[: -len(suffix)]
            if len(core) >= 2:
                return core
    return None


def _load_raw(name: str) -> list[dict]:
    path = GLOSSARY / name
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def all_rows() -> list[dict]:
    rows: list[dict] = []
    seen: set[tuple[str, str]] = set()

    def add(zh: str, en: str, kind: str, code: str = "", parent: str = "") -> None:
        key = (zh, kind)
        if not zh or key in seen:
            return
        seen.add(key)
        rows.append({"zh": zh, "en": en, "kind": kind, "code": code, "parent": parent})

    for item in _load_raw("raw_province.json"):
        name, code = item["name"], item["code"]
        add(name, _english(name, "province"), "province", code, "")
        core = _core_of(name)
        if core:
            add(core, EXCEPTIONS.get(core, _english(name, "province").replace(" Province", "").replace(" Autonomous Region", "").replace(" SAR", "").strip()), "province_core", code, code)

    for item in _load_raw("raw_city.json"):
        name, code = item["name"], item["code"]
        if "行政区划" in name:
            continue
        parent = item["province"] + "0000"
        add(name, _english(name, "city"), "city", code, parent)
        core = _core_of(name)
        if core and core not in {row["zh"] for row in rows if row["kind"] == "province_core"}:
            en = _english(name, "city")
            for extra in (" City", " Autonomous Prefecture", " Prefecture", " League"):
                en = en.replace(extra, "")
            add(core, EXCEPTIONS.get(core, en.strip()), "city_core", code, parent)

    for item in _load_raw("raw_area.json"):
        name, code = item["name"], item["code"]
        parent = item["province"] + item["city"] + "00"
        add(name, _english(name, "area"), "area", code, parent)
        core = _core_of(name)
        if core and len(core) >= 2:
            en = _english(name, "area")
            for extra in (" District", " County", " Banner", " City", " Autonomous County", " Forestry District", " Special District"):
                en = en.replace(extra, "")
            add(core, EXCEPTIONS.get(core, en.strip()), "area_core", code, parent)
    return rows


@lru_cache(maxsize=1)
def zh_to_en() -> dict[str, str]:
    table: dict[str, str] = {}
    priority = {"province": 5, "city": 4, "area": 3, "province_core": 2, "city_core": 1, "area_core": 0}
    for row in sorted(all_rows(), key=lambda item: priority.get(item["kind"], 0)):
        table[row["zh"]] = row["en"]
    return table


@lru_cache(maxsize=1)
def names_by_length() -> list[str]:
    return sorted({row["zh"] for row in all_rows()}, key=len, reverse=True)


@lru_cache(maxsize=1)
def full_names() -> list[str]:
    return sorted(
        (row["zh"] for row in all_rows() if row["kind"] in {"province", "city", "area"}),
        key=len,
        reverse=True,
    )


@lru_cache(maxsize=1)
def _by_code() -> dict[str, dict]:
    out: dict[str, dict] = {}
    for row in all_rows():
        if row["code"] and row["kind"] in {"province", "city", "area"}:
            out.setdefault(row["code"], row)
    return out


@lru_cache(maxsize=1)
def _children() -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for row in all_rows():
        if row["kind"] in {"province", "city", "area"} and row["parent"]:
            out.setdefault(row["parent"], []).append(row["zh"])
    return out


@lru_cache(maxsize=1)
def _row_by_name() -> dict[str, dict]:
    out: dict[str, dict] = {}
    for row in all_rows():
        if row["kind"] in {"province", "city", "area"}:
            out[row["zh"]] = row
    return out


def places_from_usci(code: str) -> list[str]:
    code = (code or "").upper().replace(" ", "")
    if len(code) < 8 or not code[2:8].isdigit():
        return []
    region = code[2:8]
    names: list[str] = []
    by_code = _by_code()
    for key in (region, region[:4] + "00", region[:2] + "0000"):
        row = by_code.get(key)
        if row and row["zh"] not in names:
            names.append(row["zh"])
    return names


def levenshtein(a: str, b: str) -> int:
    if a == b:
        return 0
    if abs(len(a) - len(b)) > 1:
        return 99
    if len(a) < len(b):
        a, b = b, a
    if len(a) == len(b):
        return sum(x != y for x, y in zip(a, b))
    i = j = diffs = 0
    while i < len(a) and j < len(b):
        if a[i] == b[j]:
            i += 1
            j += 1
        else:
            diffs += 1
            i += 1
            if diffs > 1:
                return diffs
    return diffs + (len(a) - i)


def snap_place(token: str, candidates: list[str] | None = None, prefer: list[str] | None = None) -> str:
    token = (token or "").strip()
    table = zh_to_en()
    if not token:
        return token
    if token in table and (candidates is None or token in candidates):
        return token
    pool = candidates if candidates is not None else [name for name in names_by_length() if name.endswith(token[-1] if token[-1] in "省市县区旗盟州" else "")]
    hits = [name for name in pool if levenshtein(token, name) == 1]
    if prefer:
        preferred = [name for name in hits if name in prefer]
        if len(preferred) == 1:
            return preferred[0]
        if preferred:
            hits = preferred
    if len(hits) == 1:
        return hits[0]
    return token


def _candidates_for(parent: str | None, kind: str) -> list[str]:
    rows = [row for row in all_rows() if row["kind"] == kind]
    if not parent:
        return [row["zh"] for row in rows]
    parent_row = _row_by_name().get(parent)
    if not parent_row:
        return [row["zh"] for row in rows]
    children = _children().get(parent_row["code"], [])
    return children or [row["zh"] for row in rows]


def _match_level(text: str, kind: str, parent: str | None, prefer: list[str] | None) -> tuple[str, int] | None:
    names = sorted(_candidates_for(parent, kind), key=len, reverse=True)
    for name in names:
        if text.startswith(name):
            return name, len(name)
        core = _core_of(name)
        if core and len(core) >= 2 and text.startswith(core):
            return name, len(core)
    suffix = {"province": "省", "city": "市州盟", "area": "区县旗"}.get(kind, "")
    for width in range(min(12, len(text)), 1, -1):
        chunk = text[:width]
        if kind == "province" and not (chunk.endswith("省") or chunk.endswith("区") or chunk in SHORT_CORE.values()):
            if width != len(text) and chunk[-1] not in "省市自治区":
                continue
        if kind == "city" and chunk[-1] not in "市州盟":
            continue
        if kind == "area" and chunk[-1] not in "区县旗":
            continue
        fixed = snap_place(chunk, names, prefer)
        if fixed != chunk and fixed in names:
            return fixed, width
        if prefer:
            for name in prefer:
                if name in names and levenshtein(chunk, name) == 1:
                    return name, width
    return None


def consume_admin(text: str, prefer: list[str] | None = None) -> tuple[list[str], str]:
    admin: list[str] = []
    i = 0
    parent = None
    for kind in ("province", "city", "area"):
        hit = _match_level(text[i:], kind, parent, prefer)
        if not hit and kind != "province":
            hit = _match_level(text[i:], kind, None, prefer)
        if not hit:
            continue
        name, consumed = hit
        if kind == "city" and len(_match_ambiguous(text[i:], kind, parent, prefer)) > 1:
            ahead = _match_level(text[i + consumed :], "area", name, prefer)
            if not ahead:
                rivals = _match_ambiguous(text[i:], kind, parent, prefer)
                resolved = None
                for rival in rivals:
                    if _match_level(text[i + consumed :], "area", rival, prefer):
                        resolved = rival
                        break
                if resolved:
                    name = resolved
        admin.append(name)
        i += consumed
        parent = name
    return admin, text[i:]


def _match_ambiguous(text: str, kind: str, parent: str | None, prefer: list[str] | None) -> list[str]:
    names = _candidates_for(parent, kind)
    hits: list[str] = []
    for width in range(min(8, len(text)), 1, -1):
        chunk = text[:width]
        if chunk[-1] not in "省市州盟区县旗":
            continue
        for name in names:
            if levenshtein(chunk, name) == 1 or text.startswith(name):
                if name not in hits:
                    hits.append(name)
        if hits:
            return hits
    return hits


def snap_text(text: str, prefer: list[str] | None = None) -> str:
    if not text:
        return text
    admin, rest = consume_admin(text, prefer)
    if admin:
        return "".join(admin) + rest
    names = names_by_length()
    i = 0
    out: list[str] = []
    while i < len(text):
        hit = next((n for n in names if text.startswith(n, i)), None)
        if hit:
            out.append(hit)
            i += len(hit)
            continue
        snapped = None
        for width in range(min(8, len(text) - i), 1, -1):
            chunk = text[i : i + width]
            if chunk[-1] not in "省市县区旗盟州":
                continue
            fixed = snap_place(chunk, prefer=prefer)
            if fixed != chunk:
                snapped = fixed
                out.append(fixed)
                i += width
                break
        if snapped:
            continue
        out.append(text[i])
        i += 1
    return "".join(out)


def english(zh: str) -> str:
    return zh_to_en().get(zh) or zh
