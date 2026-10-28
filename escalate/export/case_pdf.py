"""Case-file PDF export (implemented in task 3.5)."""

from sqlalchemy.orm import Session

from escalate.db.models import Case


def build_case_pdf(session: Session, case: Case) -> bytes:
    raise NotImplementedError("case PDF export arrives in task 3.5")
