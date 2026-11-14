"""The written feed under the map (Dhavni — US-14): one plain sentence per change."""

from app.graph import narrator
from app.graph.narrator import Related


def test_an_added_requirement_names_the_actor_and_its_state() -> None:
    assert narrator.added("Arjun", "REQ-031") == "Arjun added REQ-031 (Proposed)."


def test_an_analysis_lists_what_it_found_with_severity() -> None:
    sentence = narrator.analysed(
        "REQ-031",
        [
            Related("conflict", "REQ-014", "high"),
            Related("conflict", "REQ-002", None),
            Related("duplicate", "REQ-040", None),
            Related("ambiguous", None),
        ],
    )

    assert sentence == (
        "Analysis of REQ-031: 2 conflicts with REQ-014 (high) and REQ-002, "
        "1 possible duplicate of REQ-040 and ambiguous wording."
    )


def test_a_clean_analysis_says_analysis_can_miss_conflicts() -> None:
    assert narrator.analysed("REQ-050", []) == (
        "Analysis of REQ-050: no issues detected (analysis can miss conflicts)."
    )


def test_a_document_analysis_counts_by_kind() -> None:
    sentence = narrator.document_analysed("srs.docx", ["conflict", "conflict", "ambiguous"])

    assert sentence == "Analysis of srs.docx finished: 1 ambiguity and 2 conflicts."


def test_reviews_name_the_requirements_involved() -> None:
    assert narrator.reviewed("Riya", "dismiss", "conflict", ["REQ-014", "REQ-031"]) == (
        "Riya dismissed the conflict between REQ-014 and REQ-031."
    )
    assert narrator.reviewed(
        "Riya", "reclassify", "conflict", ["REQ-014", "REQ-031"], new_kind="duplicate"
    ) == ("Riya reclassified the conflict between REQ-014 and REQ-031 as duplicate.")
    assert narrator.reviewed("Riya", "confirm", "ambiguous", ["REQ-050"]) == (
        "Riya confirmed the ambiguity on REQ-050."
    )


def test_state_changes_and_owner_changes() -> None:
    assert (
        narrator.moved("Riya", "REQ-031", "Under_Review") == "Riya moved REQ-031 to Under review."
    )
    assert narrator.moved("Riya", "REQ-031", "Approved") == "Riya approved REQ-031."
    assert narrator.moved(None, "REQ-031", "Implemented") == "Someone marked REQ-031 implemented."
    assert narrator.owner_changed("Riya", "REQ-031", "Arjun") == (
        "Riya made Arjun the owner of REQ-031."
    )
