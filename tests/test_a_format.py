from license_trans.classify import NotFormatA, classify_format_a
from license_trans.divisions import consume_admin, places_from_usci, snap_text
from license_trans.ocr import OcrLine
from license_trans.parse import LicenseFields, parse_license
from license_trans.translate import (
    translate_address,
    translate_authority,
    translate_capital,
    translate_company,
    translate_fields,
    translate_term,
    translate_type,
)
from license_trans.usci import checksum_ok, repair_usci


def test_usci_and_region():
    code = "91341600MA2U049814"
    assert checksum_ok(code)
    assert "亳州市" in places_from_usci(code)
    assert repair_usci("91341600MA2U04981A") in {code, "91341600MA2U04981A"}


def test_snap_ocr_places():
    prefer = places_from_usci("91341600MA2U049814")
    assert snap_text("老州市青美酒业有限公司", prefer) == "亳州市青美酒业有限公司"
    assert snap_text("安徽省老州市焦城区桐乡路", prefer).startswith("安徽省亳州市谯城区")
    admin, rest = consume_admin("安徽省老州市焦城区桐乡路万达珑悦湾2-112铺", prefer)
    assert admin == ["安徽省", "亳州市", "谯城区"]
    assert rest.startswith("桐乡路")


def test_address_and_company():
    prefer = places_from_usci("91341600MA2U049814")
    addr = translate_address("安徽省亳州市谯城区桐乡路万达珑悦湾2-112铺", prefer)
    assert addr == "Shop 2-112, Wanda Longyuewan, Tongxiang Road, Qiaocheng District, Bozhou City, Anhui Province"
    garbled = translate_address("安徽省老州市焦城区桐乡路万达珑悦湾2-112铺", prefer)
    assert garbled == addr
    assert translate_company("亳州市青美酒业有限公司") == "Bozhou Qingmei Wine Industry Co., Ltd."
    assert translate_authority("", "安徽省亳州市谯城区桐乡路", "亳州市青美酒业有限公司") == (
        "Bozhou Municipal Market Supervision and Administration Bureau (Sealed)"
    )


def test_closed_a_fields():
    assert translate_type("有限责任公司（自然人独资）") == "Limited Liability Company (Sole Proprietorship of Natural Person)"
    assert translate_type("股份有限公司(上市)") == "Company Limited by Shares (Listed)"
    assert translate_type("有限责任公司(中外合资)") == "Limited Liability Company (Sino-Foreign Equity Joint Venture)"
    assert translate_capital("壹仟万圆整") == "CNY Ten Million Only"
    assert translate_capital("美元100万") == "USD One Million Only"
    assert translate_term("2019年08月05日至长期") == "August 5, 2019 to Long term"
    assert translate_term("长期") == "Long term"


def test_reject_non_a():
    try:
        classify_format_a(LicenseFields(credit_code="92341600MA2U049814", type="个体工商户"))
        assert False
    except NotFormatA:
        pass
    try:
        classify_format_a(LicenseFields(name="某某有限公司北京分公司", type="有限责任公司分公司"))
        assert False
    except NotFormatA:
        pass


def test_parse_snaps_garbled_ocr():
    def line(text: str, x0: float, y0: float) -> OcrLine:
        return OcrLine(text=text, score=0.9, x0=x0, y0=y0, x1=x0 + 200, y1=y0 + 18)

    fields = parse_license(
        [
            line("统一社会信用代码 91341600MA2U049814 (1-1)", 40, 40),
            line("名称", 40, 80),
            line("老州市青美酒业有限公司", 90, 80),
            line("类型", 40, 110),
            line("有限责任公司（自然人独资）", 90, 110),
            line("法定代表人", 40, 140),
            line("孟瑞青", 140, 140),
            line("经营范围", 40, 170),
            line("许可项目：食品生产", 90, 170),
            line("注册资本", 500, 80),
            line("壹仟万圆整", 580, 80),
            line("成立日期", 500, 110),
            line("2019年08月05日", 580, 110),
            line("住所", 500, 140),
            line("安徽省老州市焦城区桐乡路万达珑悦湾2-112销", 560, 140),
            line("副本", 400, 20),
        ]
    )
    assert fields.name == "亳州市青美酒业有限公司"
    assert fields.address.startswith("安徽省亳州市谯城区")
    assert fields.address.endswith("2-112铺")
    assert fields.duplicate is True


def test_translate_fields_sample():
    fields = LicenseFields(
        credit_code="91341600MA2U049814",
        copy_no="1-1",
        name="亳州市青美酒业有限公司",
        type="有限责任公司（自然人独资）",
        legal_person="孟瑞青",
        scope="许可项目：食品生产、食品销售（依法须经批准的项目，经相关部门批准后方可开展经营活动）一般项目：农副产品销售、初级农产品收购：日用百货销售、家居用品销售（除许可业务外，可自主依法经营法律法规非禁止或限制的项目）",
        capital="壹仟万圆整",
        established="2019年08月05日",
        address="安徽省亳州市谯城区桐乡路万达珑悦湾2-112铺",
        issue_date="2022年12月09日",
        duplicate=True,
    )
    en = translate_fields(fields)
    assert en["name"] == "Bozhou Qingmei Wine Industry Co., Ltd."
    assert en["type"].startswith("Limited Liability Company")
    assert en["legal_person"] == "Meng Ruiqing"
    assert en["capital"] == "CNY Ten Million Only"
    assert en["established"] == "August 5, 2019"
    assert en["issue_date"] == "December 9, 2022"
    assert "Qiaocheng District" in en["address"]
    assert "Bozhou" in en["authority"]


if __name__ == "__main__":
    test_usci_and_region()
    test_snap_ocr_places()
    test_address_and_company()
    test_closed_a_fields()
    test_reject_non_a()
    test_parse_snaps_garbled_ocr()
    test_translate_fields_sample()
    print("ok")
