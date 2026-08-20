from app.processing.classifier import (
    ClassificationStatus,
    RawClassificationOutput,
    decision_from_raw_data,
    validate_raw_classification,
)


def test_valid_classification_is_accepted() -> None:
    decision = validate_raw_classification(
        RawClassificationOutput(
            subject_code="db101",
            content_type="lecture",
            confidence=0.91,
            evidence=["normalization"],
        ),
        allowed_subject_codes={"DB101"},
        allowed_types={"lecture"},
        min_confidence=0.8,
        min_evidence_items=1,
        classifier_version="test",
    )

    assert decision.status == ClassificationStatus.CLASSIFIED
    assert decision.subject_code == "DB101"


def test_unknown_subject_becomes_unclassified() -> None:
    decision = validate_raw_classification(
        RawClassificationOutput(
            subject_code="AI999",
            content_type="lecture",
            confidence=0.99,
            evidence=["clear evidence"],
        ),
        allowed_subject_codes={"DB101"},
        allowed_types={"lecture"},
        min_confidence=0.8,
        min_evidence_items=1,
        classifier_version="test",
    )

    assert decision.status == ClassificationStatus.UNCLASSIFIED
    assert decision.reason == "Unknown or missing subject code"


def test_low_confidence_becomes_unclassified() -> None:
    decision = validate_raw_classification(
        RawClassificationOutput(
            subject_code="DB101",
            content_type="lecture",
            confidence=0.2,
            evidence=["normalization"],
        ),
        allowed_subject_codes={"DB101"},
        allowed_types={"lecture"},
        min_confidence=0.8,
        min_evidence_items=1,
        classifier_version="test",
    )

    assert decision.status == ClassificationStatus.UNCLASSIFIED


def test_invalid_ai_output_becomes_unclassified() -> None:
    decision = decision_from_raw_data(
        {"subject_code": "DB101", "content_type": "lecture", "confidence": "high"},
        allowed_subject_codes={"DB101"},
        allowed_types={"lecture"},
        min_confidence=0.8,
        min_evidence_items=1,
        classifier_version="test",
    )

    assert decision.status == ClassificationStatus.UNCLASSIFIED
    assert decision.reason == "Invalid classifier output"

