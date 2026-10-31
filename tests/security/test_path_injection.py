"""CodeQL py/path-injection: evidence and checklist paths come only from server-made values
(integer case ids, random stored names, the country packs on disk) and must resolve inside
their base folder, symlinks included, before anything is read or deleted."""

import os
from pathlib import Path

import pytest
import yaml
from sqlalchemy.orm import Session

from escalate.agent.checklist import UnsafeChecklistPath, checklist_path, load_checklist
from escalate.config import Settings
from escalate.db.models import Case, Evidence
from escalate.evidence.store import (
    UnsafeEvidencePath,
    case_dir,
    delete_files,
    load_plain,
    save_upload,
)

TRAVERSAL = ["../victim", "..", "/etc", "%2e%2e%2fvictim", "..%2fvictim", "1/../../victim", "1"]


@pytest.fixture
def victim(tmp_path: Path) -> Path:
    """A folder next to EVIDENCE_DIR that must never be touched."""
    folder = tmp_path / "victim"
    folder.mkdir()
    (folder / "keep.txt").write_text("not evidence")
    return folder


@pytest.mark.parametrize("bad", [*TRAVERSAL, -1, True, 1.0, None])
def test_case_dir_takes_integer_ids_only(settings: Settings, bad: object) -> None:
    with pytest.raises(UnsafeEvidencePath):
        case_dir(bad, settings)  # type: ignore[arg-type]


@pytest.mark.parametrize("bad", TRAVERSAL)
def test_delete_files_rejects_traversal(settings: Settings, victim: Path, bad: str) -> None:
    with pytest.raises(UnsafeEvidencePath):
        delete_files(bad, settings)  # type: ignore[arg-type]
    assert (victim / "keep.txt").exists()


def test_delete_files_does_not_follow_a_symlinked_case_folder(
    settings: Settings, victim: Path
) -> None:
    settings.evidence_dir.mkdir(parents=True)
    (settings.evidence_dir / "7").symlink_to(victim, target_is_directory=True)
    with pytest.raises(UnsafeEvidencePath):
        delete_files(7, settings)
    assert (victim / "keep.txt").exists()


def test_delete_files_removes_links_inside_without_following(
    settings: Settings, victim: Path
) -> None:
    folder = settings.evidence_dir / "7"
    folder.mkdir(parents=True)
    (folder / "link.bin").symlink_to(victim / "keep.txt")
    delete_files(7, settings)
    assert not folder.exists()
    assert (victim / "keep.txt").exists()


@pytest.fixture
def stored(db: Session, settings: Settings) -> Evidence:
    case = Case(description="LED broke")
    db.add(case)
    db.flush()
    return save_upload(db, case.id, "r.txt", b"receipt", settings, extract=False)


@pytest.mark.parametrize(
    "file_path",
    [
        "../victim/keep.txt",
        "/etc/passwd",
        "%2e%2e%2fvictim%2fkeep.txt",
        "data/evidence/1/../../../victim/keep.txt",
        "data/evidence/1/" + "a" * 32 + ".bin/..",
        "r.txt",
    ],
)
def test_load_plain_rejects_tampered_paths(
    stored: Evidence, settings: Settings, file_path: str
) -> None:
    stored.file_path = file_path
    with pytest.raises(UnsafeEvidencePath):
        load_plain(stored, settings)


def test_load_plain_rejects_a_symlinked_stored_file(
    stored: Evidence, settings: Settings, victim: Path
) -> None:
    path = Path(stored.file_path)
    path.unlink()
    path.symlink_to(victim / "keep.txt")
    with pytest.raises(UnsafeEvidencePath):
        load_plain(stored, settings)


def test_load_plain_rejects_another_cases_folder(stored: Evidence, settings: Settings) -> None:
    stored.case_id = stored.case_id + 1  # the name exists only under the real case's folder
    with pytest.raises(FileNotFoundError):
        load_plain(stored, settings)


def test_stored_paths_keep_working(stored: Evidence, settings: Settings) -> None:
    assert Path(stored.file_path).parent == settings.evidence_dir / str(stored.case_id)
    assert load_plain(stored, settings) == b"receipt"
    delete_files(stored.case_id, settings)
    assert not (settings.evidence_dir / str(stored.case_id)).exists()


def _pack(folder: Path, title: str) -> None:
    folder.mkdir(parents=True)
    (folder / "scam_checklist.yaml").write_text(
        yaml.safe_dump({"country": title, "items": [{"id": "a", "title": title}]})
    )


@pytest.fixture
def playbooks(tmp_path: Path) -> Path:
    root = tmp_path / "playbooks"
    _pack(root / "intl" / "generic", "INTL")
    _pack(root / "xx", "XX")
    _pack(tmp_path / "outside", "OUTSIDE")
    return root


@pytest.mark.parametrize(
    "country", ["..", "../xx", "/etc", "%2e%2e", "x/", "xx/../..", "~", "", None, "intl", "zz"]
)
def test_checklist_country_is_looked_up_never_joined(playbooks: Path, country: str | None) -> None:
    generic = playbooks / "intl" / "generic" / "scam_checklist.yaml"
    assert checklist_path(country, playbooks) == generic


def test_checklist_country_code_picks_the_pack(playbooks: Path) -> None:
    assert load_checklist("XX", playbooks).country == "XX"
    assert load_checklist("xx", playbooks).country == "XX"


def test_checklist_symlinked_pack_out_of_playbooks_is_refused(
    playbooks: Path, tmp_path: Path
) -> None:
    (playbooks / "yy").symlink_to(tmp_path / "outside", target_is_directory=True)
    with pytest.raises(UnsafeChecklistPath):
        load_checklist("YY", playbooks)


def test_case_folder_linked_to_the_evidence_root_is_refused(settings: Settings) -> None:
    """Strictly inside: a case folder that resolves to EVIDENCE_DIR itself would let delete_files
    empty the root."""
    root = settings.evidence_dir
    root.mkdir(parents=True)
    (root / "keep.bin").write_bytes(b"x")
    (root / "7").symlink_to(root, target_is_directory=True)
    with pytest.raises(UnsafeEvidencePath):
        delete_files(7, settings)
    assert (root / "keep.bin").exists()


def test_case_folder_linked_to_a_sibling_with_the_same_prefix_is_refused(
    settings: Settings, tmp_path: Path
) -> None:
    sibling = tmp_path / "evidence-old" / "7"  # "…/evidence-old" starts with "…/evidence"
    sibling.mkdir(parents=True)
    (sibling / "keep.bin").write_bytes(b"x")
    settings.evidence_dir.mkdir(parents=True)
    (settings.evidence_dir / "7").symlink_to(sibling, target_is_directory=True)
    with pytest.raises(UnsafeEvidencePath):
        delete_files(7, settings)
    assert (sibling / "keep.bin").exists()


def test_stored_file_linked_to_another_cases_file_is_refused(
    db: Session, stored: Evidence, settings: Settings
) -> None:
    other = save_upload(db, stored.case_id, "o.txt", b"other", settings, extract=False)
    folder = settings.evidence_dir / "99"
    folder.mkdir()
    link = folder / os.path.basename(other.file_path)
    link.symlink_to(Path(other.file_path).resolve())
    other.case_id = 99
    with pytest.raises(UnsafeEvidencePath):
        load_plain(other, settings)


def test_paths_handed_out_are_already_resolved(stored: Evidence, settings: Settings) -> None:
    real = os.path.realpath(settings.evidence_dir)
    assert str(case_dir(stored.case_id, settings)) == os.path.join(real, str(stored.case_id))
