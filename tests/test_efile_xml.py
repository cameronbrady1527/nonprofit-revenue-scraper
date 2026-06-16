"""IRS e-file XML parser tests (pure, offline).

Fixtures are minimal hand-written returns carrying the real IRS efile
namespace and the exact element names the parser matches, so a schema rename
on the IRS side surfaces here rather than silently producing empty rows.
"""

import pytest

from nonprofit_benchmark.efile_xml import EfileParseError, parse_990_xml

NS = 'xmlns="http://www.irs.gov/efile"'

FORM_990 = f"""<?xml version="1.0"?>
<Return {NS}><ReturnData><IRS990>
  <CYTotalRevenueAmt>500000</CYTotalRevenueAmt>
  <PYTotalRevenueAmt>410000</PYTotalRevenueAmt>
  <Form990PartVIISectionAGrp>
    <PersonNm>Ada Director</PersonNm><TitleTxt>EXECUTIVE DIRECTOR</TitleTxt>
    <ReportableCompFromOrgAmt>120000</ReportableCompFromOrgAmt>
    <ReportableCompFromRltdOrgAmt>5000</ReportableCompFromRltdOrgAmt>
    <OtherCompensationAmt>8000</OtherCompensationAmt>
  </Form990PartVIISectionAGrp>
  <Form990PartVIISectionAGrp>
    <PersonNm>Ben Board</PersonNm><TitleTxt>TREASURER</TitleTxt>
    <ReportableCompFromOrgAmt>0</ReportableCompFromOrgAmt>
    <ReportableCompFromRltdOrgAmt>0</ReportableCompFromRltdOrgAmt>
    <OtherCompensationAmt>0</OtherCompensationAmt>
  </Form990PartVIISectionAGrp>
</IRS990></ReturnData></Return>"""

FORM_990EZ = f"""<?xml version="1.0"?>
<Return {NS}><ReturnData><IRS990EZ>
  <TotalRevenueAmt>90000</TotalRevenueAmt>
  <OfficerDirectorTrusteeEmplGrp>
    <PersonNm>Cara President</PersonNm><TitleTxt>PRESIDENT</TitleTxt>
    <CompensationAmt>40000</CompensationAmt>
    <EmployeeBenefitProgramAmt>1000</EmployeeBenefitProgramAmt>
    <ExpenseAccountOtherAllwncAmt>500</ExpenseAccountOtherAllwncAmt>
  </OfficerDirectorTrusteeEmplGrp>
</IRS990EZ></ReturnData></Return>"""

FORM_990PF = f"""<?xml version="1.0"?>
<Return {NS}><ReturnData><IRS990PF>
  <TotalRevAndExpnssAmt>250000</TotalRevAndExpnssAmt>
  <OfficerDirTrstKeyEmplInfoGrp><OfficerDirTrstKeyEmplGrp>
    <PersonNm>Dee Trustee</PersonNm><TitleTxt>TRUSTEE</TitleTxt>
    <CompensationAmt>30000</CompensationAmt>
    <EmployeeBenefitProgramAmt>2000</EmployeeBenefitProgramAmt>
    <ExpenseAccountOtherAllwncAmt>0</ExpenseAccountOtherAllwncAmt>
  </OfficerDirTrstKeyEmplGrp></OfficerDirTrstKeyEmplInfoGrp>
</IRS990PF></ReturnData></Return>"""


def test_full_990_revenue_and_columns_kept_separate():
    result = parse_990_xml(FORM_990)
    assert result.total_revenue == 500000  # current-year, not prior-year
    assert len(result.executives) == 2
    top = result.executives[0]
    assert top.name == "Ada Director"
    assert top.title == "EXECUTIVE DIRECTOR"
    assert top.compensation_org == 120000  # column D — the benchmark figure
    assert top.compensation_related == 5000
    assert top.compensation_other == 8000


def test_990ez_maps_compensation_and_sums_other_columns():
    result = parse_990_xml(FORM_990EZ)
    assert result.total_revenue == 90000
    [officer] = result.executives
    assert officer.name == "Cara President"
    assert officer.compensation_org == 40000
    assert officer.compensation_related is None  # 990-EZ has no related-org column
    assert officer.compensation_other == 1500  # benefits 1000 + allowances 500


def test_990pf_nested_officer_group():
    result = parse_990_xml(FORM_990PF)
    assert result.total_revenue == 250000
    [trustee] = result.executives
    assert trustee.name == "Dee Trustee"
    assert trustee.compensation_org == 30000
    assert trustee.compensation_other == 2000


def test_business_name_falls_back_when_no_person_name():
    xml = f"""<Return {NS}><ReturnData><IRS990>
      <CYTotalRevenueAmt>100</CYTotalRevenueAmt>
      <Form990PartVIISectionAGrp>
        <BusinessNameLine1Txt>Management Co LLC</BusinessNameLine1Txt>
        <ReportableCompFromOrgAmt>10000</ReportableCompFromOrgAmt>
      </Form990PartVIISectionAGrp>
    </IRS990></ReturnData></Return>"""
    [entity] = parse_990_xml(xml).executives
    assert entity.name == "Management Co LLC"
    assert entity.compensation_org == 10000


def test_missing_revenue_and_no_people_is_empty_not_error():
    result = parse_990_xml(f"<Return {NS}><ReturnData><IRS990/></ReturnData></Return>")
    assert result.total_revenue is None
    assert result.executives == []


def test_malformed_xml_raises():
    with pytest.raises(EfileParseError):
        parse_990_xml(b"<Return><unclosed>")
