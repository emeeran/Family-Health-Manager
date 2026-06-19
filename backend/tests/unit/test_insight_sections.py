"""Tests for the comprehensive-insight section parser."""

from app.schemas.insight_sections import parse_insight_sections


def test_parses_stars_wrap_number_format():
    """The model's actual output: '**1. Title**' (stars wrap the number)."""
    md = "**1. Health Overview**\n\nBody one.\n\n**2. Active Conditions**\n\nBody two."
    out = parse_insight_sections(md)
    assert [s["title"] for s in out] == ["Health Overview", "Active Conditions"]
    assert out[0]["body"] == "Body one."
    assert out[0]["key"] == "overview"
    assert out[1]["key"] == "conditions"


def test_parses_number_outside_stars_format():
    """The prompt's instructed format: '1. **Title**'."""
    md = "1. **Health Overview**\nBody A\n\n2. **Lab Trends**\nBody B"
    out = parse_insight_sections(md)
    assert [s["title"] for s in out] == ["Health Overview", "Lab Trends"]
    assert out[1]["key"] == "labs"


def test_parses_markdown_atx_headings():
    md = "### Health Overview\nBody A\n### Risk Assessment\nBody B"
    out = parse_insight_sections(md)
    assert [s["title"] for s in out] == ["Health Overview", "Risk Assessment"]
    assert out[1]["key"] == "risk"


def test_full_six_sections_keys():
    md = "\n\n".join(
        [
            "**1. Health Overview**",
            "overview body",
            "**2. Active Conditions**",
            "conditions body",
            "**3. Lab Trends**",
            "labs body",
            "**4. Risk Assessment**",
            "risk body",
            "**5. Recommendations**",
            "recs body",
            "**6. Follow-up Actions**",
            "followup body",
        ]
    )
    out = parse_insight_sections(md)
    assert [s["key"] for s in out] == [
        "overview",
        "conditions",
        "labs",
        "risk",
        "recommendations",
        "follow_up",
    ]
    assert all(s["body"] for s in out)


def test_no_false_split_on_bold_subitems():
    md = "**1. Active Conditions**\n\n**Parkinson's Disease**: stable.\n\n**T2DM**: worsening."
    out = parse_insight_sections(md)
    assert len(out) == 1
    assert out[0]["title"] == "Active Conditions"
    assert "Parkinson's Disease" in out[0]["body"]


def test_empty_returns_empty():
    assert parse_insight_sections("") == []
    assert parse_insight_sections("   \n\n  ") == []
