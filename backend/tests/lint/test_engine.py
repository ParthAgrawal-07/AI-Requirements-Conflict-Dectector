"""The lint engine (Keval — US-51, NFR-34): issues with offsets, the quality score, speed."""

import time

from app.lint.engine import catalogue, lint, score_of


def test_issues_point_at_the_words_in_reading_order() -> None:
    text = "The app shall be user-friendly and respond quickly, etc."
    result = lint(text)

    ids = [issue.rule_id for issue in result.issues]
    assert ids.index("vague.usability") < ids.index("vague.speed") < ids.index("unbounded.etc")
    for issue in result.issues:
        assert text[issue.start : issue.end] == issue.match
        assert issue.hint and issue.message


def test_the_score_and_quality_follow_the_published_weights() -> None:
    clean = lint("When the user is inactive for 10 minutes, the system shall end the session.")
    assert (clean.score, clean.quality) == (100, "good")

    poor = lint("It shall be fast, easy, robust and TBD.")
    expected = 100 - sum({"error": 25, "warning": 10, "info": 3}[i.severity] for i in poor.issues)
    assert poor.score == max(0, expected)
    assert poor.quality == "poor"


def test_score_bands() -> None:
    assert score_of([]) == (100, "good")
    fair = lint("The page shall load quickly, be user-friendly and robust.")
    assert (fair.score, fair.quality) == (70, "fair")


def test_lint_never_blocks_and_is_fast() -> None:
    text = "The system shall respond quickly. " * 200
    started = time.perf_counter()
    result = lint(text)
    assert time.perf_counter() - started < 0.3  # NFR-34, on the server too
    assert len(result.issues) <= 50


def test_the_catalogue_is_what_the_browser_gets() -> None:
    data = catalogue()
    assert data["version"] == 2
    assert {"measure.missing", "compound.multiple_shall", "weak.modal"} <= {
        entry["id"] for entry in data["entries"]
    }
