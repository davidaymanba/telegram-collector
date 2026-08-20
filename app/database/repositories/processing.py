"""Repositories for processing logs and classifications."""

from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.database.models import Classification, CollectedFile, ProcessingLog, ProcessingRun
from app.database.statuses import ProcessingLogStatus
from app.processing.classifier import ClassificationDecision, ClassificationStatus


class ProcessingRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def log(
        self,
        *,
        file_record: CollectedFile | None,
        stage: str,
        status: ProcessingLogStatus,
        error_message: str | None = None,
    ) -> ProcessingLog:
        entry = ProcessingLog(
            file_id=file_record.id if file_record is not None else None,
            stage=stage,
            status=status.value,
            error_message=error_message,
        )
        self.session.add(entry)
        self.session.flush()
        return entry

    def upsert_classification(
        self,
        file_record: CollectedFile,
        decision: ClassificationDecision,
    ) -> Classification:
        classification = file_record.classification
        if classification is None:
            classification = Classification(
                file_id=file_record.id,
                status=decision.status.value,
                classifier_version=decision.classifier_version,
            )
            self.session.add(classification)

        classification.subject_code = decision.subject_code
        classification.content_type = decision.content_type
        classification.confidence = decision.confidence
        classification.evidence = decision.evidence
        classification.status = decision.status.value
        classification.reason = decision.reason
        classification.classifier_version = decision.classifier_version
        self.session.flush()
        return classification


class ProcessingRunRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def start(self, metadata: dict[str, object] | None = None) -> ProcessingRun:
        run = ProcessingRun(metadata_json=metadata or {})
        self.session.add(run)
        self.session.flush()
        return run

    def finish(
        self,
        run: ProcessingRun,
        *,
        new_count: int = 0,
        duplicate_count: int = 0,
        classified_count: int = 0,
        unclassified_count: int = 0,
        failed_count: int = 0,
        unsupported_count: int = 0,
    ) -> None:
        run.finished_at = datetime.now(tz=UTC)
        run.new_count = new_count
        run.duplicate_count = duplicate_count
        run.classified_count = classified_count
        run.unclassified_count = unclassified_count
        run.failed_count = failed_count
        run.unsupported_count = unsupported_count


def file_status_from_decision(decision: ClassificationDecision) -> str:
    return "classified" if decision.status == ClassificationStatus.CLASSIFIED else "unclassified"
