"""Classifier abstraction and strict no-guessing validation."""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from enum import StrEnum

from openai import AsyncOpenAI
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.config.loaders import SubjectConfig, allowed_content_type_values
from app.config.settings import Settings
from app.processing.text_cleaner import truncate_for_classification


class ClassificationStatus(StrEnum):
    CLASSIFIED = "classified"
    UNCLASSIFIED = "unclassified"


class ClassificationInput(BaseModel):
    filename: str
    caption: str | None = None
    channel_name: str
    extracted_text: str
    allowed_subjects: list[SubjectConfig]
    allowed_content_types: set[str]


class RawClassificationOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    subject_code: str | None = None
    content_type: str | None = None
    confidence: float | None = Field(default=None, ge=0, le=1)
    evidence: list[str] = Field(default_factory=list)


class ClassificationDecision(BaseModel):
    status: ClassificationStatus
    subject_code: str | None = None
    content_type: str | None = None
    confidence: float | None = None
    evidence: list[str] = Field(default_factory=list)
    reason: str | None = None
    classifier_version: str


class BaseClassifier(ABC):
    classifier_version = "base"

    @abstractmethod
    async def classify(self, request: ClassificationInput) -> ClassificationDecision:
        raise NotImplementedError


class NoopClassifier(BaseClassifier):
    classifier_version = "none"

    async def classify(self, request: ClassificationInput) -> ClassificationDecision:
        return ClassificationDecision(
            status=ClassificationStatus.UNCLASSIFIED,
            reason="AI provider is disabled",
            classifier_version=self.classifier_version,
        )


def validate_raw_classification(
    raw: RawClassificationOutput,
    *,
    allowed_subject_codes: set[str],
    allowed_types: set[str],
    min_confidence: float,
    min_evidence_items: int,
    classifier_version: str,
) -> ClassificationDecision:
    """Apply deterministic no-guessing rules to a structured classifier output."""

    subject_code = raw.subject_code.strip().upper() if raw.subject_code else None
    content_type = raw.content_type.strip() if raw.content_type else None

    if subject_code not in allowed_subject_codes:
        return ClassificationDecision(
            status=ClassificationStatus.UNCLASSIFIED,
            reason="Unknown or missing subject code",
            classifier_version=classifier_version,
        )
    if content_type not in allowed_types:
        return ClassificationDecision(
            status=ClassificationStatus.UNCLASSIFIED,
            reason="Unknown or missing content type",
            classifier_version=classifier_version,
        )
    if raw.confidence is None or raw.confidence < min_confidence:
        return ClassificationDecision(
            status=ClassificationStatus.UNCLASSIFIED,
            reason="Confidence is below threshold",
            confidence=raw.confidence,
            classifier_version=classifier_version,
        )
    evidence = [item.strip() for item in raw.evidence if item.strip()]
    if len(evidence) < min_evidence_items:
        return ClassificationDecision(
            status=ClassificationStatus.UNCLASSIFIED,
            reason="Insufficient evidence",
            confidence=raw.confidence,
            classifier_version=classifier_version,
        )

    return ClassificationDecision(
        status=ClassificationStatus.CLASSIFIED,
        subject_code=subject_code,
        content_type=content_type,
        confidence=raw.confidence,
        evidence=evidence,
        classifier_version=classifier_version,
    )


def decision_from_raw_data(
    data: object,
    *,
    allowed_subject_codes: set[str],
    allowed_types: set[str],
    min_confidence: float,
    min_evidence_items: int,
    classifier_version: str,
) -> ClassificationDecision:
    """Parse untrusted provider output and convert invalid payloads to unclassified."""

    try:
        raw = RawClassificationOutput.model_validate(data)
    except ValidationError:
        return ClassificationDecision(
            status=ClassificationStatus.UNCLASSIFIED,
            reason="Invalid classifier output",
            classifier_version=classifier_version,
        )

    return validate_raw_classification(
        raw,
        allowed_subject_codes=allowed_subject_codes,
        allowed_types=allowed_types,
        min_confidence=min_confidence,
        min_evidence_items=min_evidence_items,
        classifier_version=classifier_version,
    )


class OpenAIClassifier(BaseClassifier):
    classifier_version = "openai-responses-v1"

    def __init__(self, settings: Settings) -> None:
        if settings.openai_api_key is None:
            raise ValueError("TUC_OPENAI_API_KEY is required when TUC_AI_PROVIDER=openai")
        self.settings = settings
        self.client = AsyncOpenAI(api_key=settings.openai_api_key.get_secret_value())

    async def classify(self, request: ClassificationInput) -> ClassificationDecision:
        allowed_subject_codes = {subject.code for subject in request.allowed_subjects}
        input_payload = {
            "filename": request.filename,
            "caption": request.caption,
            "channel_name": request.channel_name,
            "extracted_text": truncate_for_classification(
                request.extracted_text,
                self.settings.max_classification_chars,
            ),
            "allowed_subjects": [subject.model_dump() for subject in request.allowed_subjects],
            "allowed_content_types": sorted(request.allowed_content_types),
        }

        response = await self.client.responses.create(
            model=self.settings.openai_model,
            instructions=(
                "Classify university educational content. Return only the configured subject_code "
                "and content_type. If uncertain, use null values. Do not invent categories."
            ),
            input=json.dumps(input_payload, ensure_ascii=False),
            text={
                "format": {
                    "type": "json_schema",
                    "name": "telegram_content_classification",
                    "strict": True,
                    "schema": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "subject_code": {"type": ["string", "null"]},
                            "content_type": {"type": ["string", "null"]},
                            "confidence": {"type": ["number", "null"], "minimum": 0, "maximum": 1},
                            "evidence": {
                                "type": "array",
                                "items": {"type": "string"},
                                "maxItems": 5,
                            },
                        },
                        "required": ["subject_code", "content_type", "confidence", "evidence"],
                    },
                }
            },
        )

        try:
            data = json.loads(response.output_text)
        except ValueError:
            return ClassificationDecision(
                status=ClassificationStatus.UNCLASSIFIED,
                reason="Invalid classifier output",
                classifier_version=self.classifier_version,
            )

        return decision_from_raw_data(
            data,
            allowed_subject_codes=allowed_subject_codes,
            allowed_types=request.allowed_content_types,
            min_confidence=self.settings.classification_min_confidence,
            min_evidence_items=self.settings.classification_min_evidence_items,
            classifier_version=self.classifier_version,
        )


def build_classifier(settings: Settings) -> BaseClassifier:
    if settings.ai_provider == "openai":
        return OpenAIClassifier(settings)
    return NoopClassifier()


def default_allowed_content_types() -> set[str]:
    return allowed_content_type_values()
