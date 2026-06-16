"""Shared extraction schema (pure data, no I/O).

The single result type every parser produces — Gemini PDF parsing and IRS
e-file XML parsing alike — so the persistence layer (`db.record_parse_success`)
never depends on which source the numbers came from.

The three compensation columns are kept SEPARATE and are never summed across
people: org = Form 990 Part VII column D (the benchmark figure), related =
column E, other = column F.
"""

from pydantic import BaseModel, Field


class ExecutiveRecord(BaseModel):
    name: str
    title: str | None = None
    compensation_org: int | None = Field(None, description="Part VII column D")
    compensation_related: int | None = Field(None, description="Part VII column E")
    compensation_other: int | None = Field(None, description="Part VII column F")


class FilingExtraction(BaseModel):
    total_revenue: int | None = None
    executives: list[ExecutiveRecord] = []
