import json

import pytest

from scripts import fetch_jd


def sample_job():
    return {
        "title": "Network Engineer (Firewall)",
        "company": "Example Co",
        "location": "Ho Chi Minh",
        "salary": "N/A",
        "matches": "NETWORK, Firewall",
        "posted": "2 days ago",
        "link": "https://example.com/job?a=1&b=2",
    }


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Minimum 3 years of experience with AWS", "requires 3+ years"),
        ("At least three years experience in Linux", "requires 3+ years"),
        ("Require 3-5 years of network experience", "requires 3-5 years"),
        ("Accept fresh graduates with basic Linux knowledge", ""),
        ("1-2 years experience is preferred", ""),
    ],
)
def test_too_much_experience_reason(text, expected):
    assert fetch_jd.too_much_experience_reason(text) == expected


def test_parse_claude_json_plain_json():
    payload = {"match_score": 72, "verdict": "Worth applying"}
    assert fetch_jd.parse_claude_json(json.dumps(payload)) == payload


def test_parse_claude_json_fenced_json():
    text = """```json
{"match_score": 65, "verdict": "Consider applying"}
```"""
    assert fetch_jd.parse_claude_json(text)["match_score"] == 65


def test_split_messages_splits_large_sections():
    header = "HEADER\n"
    footer = "FOOTER"
    sections = ["a" * 2000, "b" * 2000, "c" * 2000]

    messages = fetch_jd.split_messages(header, sections, footer)

    assert len(messages) > 1
    assert all(message.startswith(header) for message in messages)
    assert all(message.endswith(footer) for message in messages)


def test_format_rule_job_escapes_html():
    job = sample_job()
    job["title"] = "DevOps & Cloud <Junior>"

    text = fetch_jd.format_rule_job(job, 1)

    assert "DevOps &amp; Cloud &lt;Junior&gt;" in text
    assert "Company: Example Co" in text
    assert 'href="https://example.com/job?a=1&amp;b=2"' in text


def test_format_ai_job_contains_score_and_verdict():
    analysis = {
        "match_score": 72,
        "required_skills": ["Firewall", "Windows Server"],
        "strength": "Strong network project experience.",
        "gap": "No Windows Server experience shown.",
        "experience_level": "fresher-friendly",
        "verdict": "Worth applying",
    }

    text = fetch_jd.format_ai_job(sample_job(), analysis, 1)

    assert "Match: 72%" in text
    assert "Skills: Firewall, Windows Server" in text
    assert "fresher-friendly" in text
    assert "Worth applying" in text
