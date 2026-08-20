"""Run and database reporting helpers."""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config.loaders import SubjectsConfig
from app.database.models import Classification, CollectedFile
from app.database.statuses import FileStatus


@dataclass(frozen=True)
class Report:
    new: int
    duplicates: int
    classified: int
    unclassified: int
    failed: int
    unsupported: int
    by_subject: dict[str, int] = field(default_factory=dict)
    by_content_type: dict[str, int] = field(default_factory=dict)
    empty_subjects: list[str] = field(default_factory=list)

    def to_text(self) -> str:
        lines = [
            "Run Report",
            f"New: {self.new}",
            f"Duplicates: {self.duplicates}",
            f"Classified: {self.classified}",
            f"Unclassified: {self.unclassified}",
            f"Failed: {self.failed}",
            f"Unsupported: {self.unsupported}",
            "",
            "Subjects:",
        ]
        lines.extend(f"{subject}: {count}" for subject, count in sorted(self.by_subject.items()))
        lines.append("")
        lines.append("Content Types:")
        lines.extend(
            f"{content_type}: {count}"
            for content_type, count in sorted(self.by_content_type.items())
        )
        if self.empty_subjects:
            lines.append("")
            lines.append("Subjects With Zero Content:")
            lines.extend(sorted(self.empty_subjects))
        return "\n".join(lines)


class Reporter:
    def __init__(self, session: Session, subjects_config: SubjectsConfig) -> None:
        self.session = session
        self.subjects_config = subjects_config

    def generate(self) -> Report:
        by_status = dict(
            self.session.execute(
                select(CollectedFile.status, func.count(CollectedFile.id)).group_by(
                    CollectedFile.status
                )
            ).all()
        )
        by_subject = dict(
            self.session.execute(
                select(Classification.subject_code, func.count(Classification.id))
                .where(Classification.subject_code.is_not(None))
                .group_by(Classification.subject_code)
            ).all()
        )
        by_content_type = dict(
            self.session.execute(
                select(Classification.content_type, func.count(Classification.id))
                .where(Classification.content_type.is_not(None))
                .group_by(Classification.content_type)
            ).all()
        )
        empty_subjects = [
            subject.code
            for subject in self.subjects_config.subjects
            if by_subject.get(subject.code, 0) == 0
        ]

        return Report(
            new=sum(by_status.values()),
            duplicates=by_status.get(FileStatus.DUPLICATE.value, 0),
            classified=by_status.get(FileStatus.CLASSIFIED.value, 0),
            unclassified=by_status.get(FileStatus.UNCLASSIFIED.value, 0),
            failed=by_status.get(FileStatus.FAILED.value, 0),
            unsupported=by_status.get(FileStatus.UNSUPPORTED.value, 0),
            by_subject=by_subject,
            by_content_type=by_content_type,
            empty_subjects=empty_subjects,
        )
