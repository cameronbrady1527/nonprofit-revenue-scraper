"""Parse IRS Form 990 / 990-EZ / 990-PF e-file XML (pure, no I/O).

The IRS publishes machine-readable XML for every electronically filed return.
This module turns one return's XML into the same `FilingExtraction` the Gemini
path produced — total revenue plus every Part VII / officer entry with the
three compensation columns kept separate — so the rest of the pipeline is
unchanged. There is no network, no AI, and no nondeterminism here.

Element paths validated against real 2023 TEOS returns:

    form     revenue                  person group                    org / related / other
    ----     -------                  ------------                    ---------------------
    990      CYTotalRevenueAmt        Form990PartVIISectionAGrp       ReportableCompFromOrgAmt /
                                                                      ReportableCompFromRltdOrgAmt /
                                                                      OtherCompensationAmt
    990-EZ   TotalRevenueAmt          OfficerDirectorTrusteeEmplGrp   CompensationAmt / — /
                                                                      EmployeeBenefitProgramAmt +
                                                                      ExpenseAccountOtherAllwncAmt
    990-PF   TotalRevAndExpnssAmt     OfficerDirTrstKeyEmplGrp        CompensationAmt / — /
                                                                      EmployeeBenefitProgramAmt +
                                                                      ExpenseAccountOtherAllwncAmt

Tags are matched by local name, so the IRS efile namespace is irrelevant.
"""

import xml.etree.ElementTree as ET

from nonprofit_benchmark.extraction import ExecutiveRecord, FilingExtraction

# Revenue tags in priority order: a 990 carries CYTotalRevenueAmt, a 990-EZ
# carries TotalRevenueAmt, a 990-PF carries TotalRevAndExpnssAmt. The first one
# present wins, so a single ordered tuple covers all three forms.
REVENUE_TAGS = ("CYTotalRevenueAmt", "TotalRevenueAmt", "TotalRevAndExpnssAmt")

# (group tag, org-comp tags, related-comp tags, other-comp tags). A return
# contains exactly one of these group types; persons are collected from
# whichever appears. Multiple "other" tags are summed (benefits + allowances).
_PERSON_GROUPS = (
    (
        "Form990PartVIISectionAGrp",
        ("ReportableCompFromOrgAmt",),
        ("ReportableCompFromRltdOrgAmt",),
        ("OtherCompensationAmt",),
    ),
    (
        "OfficerDirectorTrusteeEmplGrp",  # 990-EZ
        ("CompensationAmt",),
        (),
        ("EmployeeBenefitProgramAmt", "ExpenseAccountOtherAllwncAmt"),
    ),
    (
        "OfficerDirTrstKeyEmplGrp",  # 990-PF
        ("CompensationAmt",),
        (),
        ("EmployeeBenefitProgramAmt", "ExpenseAccountOtherAllwncAmt"),
    ),
)


class EfileParseError(Exception):
    """The XML could not be parsed; record the filing as failed."""


def _local(tag: str) -> str:
    """Strip any `{namespace}` prefix, leaving the bare element name."""
    return tag.rsplit("}", 1)[-1]


def _first_text(element: ET.Element, *names: str) -> str | None:
    """First non-empty text of any descendant whose local name is in `names`,
    searching the names in order."""
    for name in names:
        for el in element.iter():
            if _local(el.tag) == name and el.text and el.text.strip():
                return el.text.strip()
    return None


def _amount(element: ET.Element, *names: str) -> int | None:
    """Sum the integer amounts found for `names` (None when none present)."""
    total = None
    for name in names:
        for el in element.iter():
            if _local(el.tag) != name or not el.text:
                continue
            value = _to_int(el.text)
            if value is not None:
                total = value if total is None else total + value
    return total


def _to_int(text: str) -> int | None:
    cleaned = text.replace(",", "").replace("$", "").strip()
    if not cleaned:
        return None
    try:
        return int(round(float(cleaned)))
    except ValueError:
        return None


def _groups(root: ET.Element, name: str) -> list[ET.Element]:
    return [el for el in root.iter() if _local(el.tag) == name]


def _person_name(group: ET.Element) -> str | None:
    return _first_text(group, "PersonNm", "BusinessNameLine1Txt", "BusinessNameLine1")


def parse_990_xml(xml_bytes: bytes | str) -> FilingExtraction:
    """Parse one IRS 990/990-EZ/990-PF e-file return into a FilingExtraction."""
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError as exc:
        raise EfileParseError(f"Malformed 990 XML: {exc}") from exc

    revenue = _amount(root, *REVENUE_TAGS)

    executives: list[ExecutiveRecord] = []
    for group_tag, org_tags, related_tags, other_tags in _PERSON_GROUPS:
        for group in _groups(root, group_tag):
            name = _person_name(group)
            if not name:
                continue
            executives.append(
                ExecutiveRecord(
                    name=name,
                    title=_first_text(group, "TitleTxt"),
                    compensation_org=_amount(group, *org_tags),
                    compensation_related=_amount(group, *related_tags) if related_tags else None,
                    compensation_other=_amount(group, *other_tags),
                )
            )

    return FilingExtraction(total_revenue=revenue, executives=executives)
