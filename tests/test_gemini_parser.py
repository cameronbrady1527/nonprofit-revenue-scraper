"""Gemini 990 parsing: response processing, validation, and retry behavior."""

import pytest

from nonprofit_benchmark.gemini_parser import (
    GeminiParseError,
    GeminiParser,
    process_response,
)

VALID_RESPONSE = """Here is the extracted data:
```json
{
    "total_revenue": 480000,
    "executives": [
        {"name": "JANE DOE", "title": "EXECUTIVE DIRECTOR",
         "compensation_org": 95000, "compensation_related": 0, "compensation_other": 8200},
        {"name": "JOHN ROE", "title": "CFO",
         "compensation_org": 78000, "compensation_related": 12000, "compensation_other": 0}
    ]
}
```"""


def test_valid_response_yields_per_executive_compensation_columns():
    extraction = process_response(VALID_RESPONSE)

    assert extraction.total_revenue == 480000
    assert len(extraction.executives) == 2

    jane = extraction.executives[0]
    assert jane.name == "JANE DOE"
    assert jane.title == "EXECUTIVE DIRECTOR"
    assert jane.compensation_org == 95000
    assert jane.compensation_related == 0
    assert jane.compensation_other == 8200


def test_partial_fields_are_tolerated_as_none():
    extraction = process_response(
        '{"total_revenue": null, "executives": [{"name": "JANE DOE"}]}'
    )

    assert extraction.total_revenue is None
    jane = extraction.executives[0]
    assert jane.title is None
    assert jane.compensation_org is None


@pytest.mark.parametrize(
    "bad_response",
    [
        '{"total_revenue": 480000, "executives": [',  # truncated JSON
        "I cannot extract data from this document.",  # refusal, no JSON
        '{"executives": [{"title": "CEO"}]}',  # executive missing required name
        '{"executives": "none found"}',  # wrong shape
    ],
)
def test_unusable_responses_raise_parse_error(bad_response):
    with pytest.raises(GeminiParseError):
        process_response(bad_response)


class FlakyGenerate:
    """Injectable transport that fails N times before answering."""

    def __init__(self, failures, response=VALID_RESPONSE):
        self.failures = failures
        self.response = response
        self.calls = 0

    def __call__(self, pdf_bytes, prompt):
        self.calls += 1
        if self.calls <= self.failures:
            raise RuntimeError("429 Resource has been exhausted")
        return self.response


def test_transient_api_errors_are_retried_with_backoff():
    generate = FlakyGenerate(failures=2)
    sleeps = []
    parser = GeminiParser(generate=generate, sleep=sleeps.append)

    extraction = parser.parse(b"%PDF-fake")

    assert extraction.total_revenue == 480000
    assert generate.calls == 3
    assert len(sleeps) == 2
    assert sleeps[1] > sleeps[0]


def test_persistent_api_errors_raise_parse_error():
    parser = GeminiParser(generate=FlakyGenerate(failures=99), sleep=lambda _: None)

    with pytest.raises(GeminiParseError):
        parser.parse(b"%PDF-fake")
