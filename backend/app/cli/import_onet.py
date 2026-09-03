import argparse
import csv
import hashlib
import json
import logging
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models.taxonomy import (
    OccupationAlias,
    OccupationConcept,
    OccupationSkillLink,
    SkillAlias,
    SkillConcept,
    TaxonomySnapshot,
    TaxonomySnapshotState,
)
from app.services.skill_catalog import SKILL_DEFINITIONS
from app.services.taxonomy_normalization import normalize_search_query

logger = logging.getLogger("ai_hiring.cli.import_onet")

REQUIRED_FILES = {
    "occupation_data": "occupation_data.csv",
    "job_titles": "job_titles.csv",
    "software_skills": "software_skills.csv",
}

EXPECTED_HEADERS = {
    "occupation_data.csv": ["O*NET-SOC Code", "Title", "Description"],
    "job_titles.csv": ["O*NET-SOC Code", "Title", "Job Title", "Short Title", "Source(s)"],
    "software_skills.csv": ["O*NET-SOC Code", "Title", "Workplace Example", "Element ID", "Element Name", "Hot Technology", "In Demand"],
}

BATCH_SIZE = 2000


class ImporterError(Exception):
    pass


def _compute_sha256(filepath: Path) -> str:
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest().lower()


def _compute_combined_hash(hashes: Dict[str, str]) -> str:
    combined_str = f"{hashes['occupation_data.csv']}:{hashes['job_titles.csv']}:{hashes['software_skills.csv']}"
    return hashlib.sha256(combined_str.encode("utf-8")).hexdigest().lower()


def _validate_headers(filepath: Path, expected: List[str]) -> None:
    with open(filepath, "r", encoding="utf-8-sig", errors="replace") as f:
        reader = csv.reader(f)
        header = next(reader, None)
        if header is None or [h.strip() for h in header] != expected:
            raise ImporterError(
                f"Header mismatch in '{filepath.name}'. Expected {expected}, got {header}"
            )


def import_onet_taxonomy(
    source_dir: Path,
    version: str = "31.0",
    session: Optional[Session] = None,
) -> int:
    """
    Imports O*NET taxonomy CSV files offline and atomically into PostgreSQL.
    """
    close_session = False
    if session is None:
        session = SessionLocal()
        close_session = True

    try:
        # 1. Validate source files exist
        if not source_dir.exists() or not source_dir.is_dir():
            logger.error("Source directory does not exist", extra={"source_dir": str(source_dir)})
            return 1

        file_paths: Dict[str, Path] = {}
        for key, fname in REQUIRED_FILES.items():
            fpath = (source_dir / fname).resolve()
            if not fpath.exists():
                logger.error(f"Missing required file: {fname}", extra={"expected_path": str(fpath)})
                return 1
            file_paths[fname] = fpath

        # 2. Validate CSV headers
        for fname, fpath in file_paths.items():
            try:
                _validate_headers(fpath, EXPECTED_HEADERS[fname])
            except ImporterError as e:
                logger.error(f"Header validation failed: {str(e)}")
                return 1

        # 3. Compute hashes
        file_hashes = {fname: _compute_sha256(fpath) for fname, fpath in file_paths.items()}
        combined_hash = _compute_combined_hash(file_hashes)

        now = datetime.now(timezone.utc)

        # 4. Check for existing snapshot with same version
        stmt = select(TaxonomySnapshot).where(
            TaxonomySnapshot.source == "ONET",
            TaxonomySnapshot.source_version == version,
        )
        existing_snapshot = session.execute(stmt).scalar_one_or_none()

        if existing_snapshot is not None:
            if existing_snapshot.combined_sha256_hash == combined_hash:
                if existing_snapshot.state == TaxonomySnapshotState.ACTIVE:
                    logger.info(
                        "Identical active snapshot already exists. Skipping re-import.",
                        extra={"snapshot_id": str(existing_snapshot.snapshot_id), "version": version},
                    )
                    return 0
                else:
                    # Reactivate
                    session.execute(
                        update(TaxonomySnapshot)
                        .where(TaxonomySnapshot.state == TaxonomySnapshotState.ACTIVE)
                        .values(state=TaxonomySnapshotState.SUPERSEDED, updated_at=now)
                    )
                    existing_snapshot.state = TaxonomySnapshotState.ACTIVE
                    existing_snapshot.activated_at = now
                    existing_snapshot.updated_at = now
                    session.commit()
                    logger.info("Reactivated existing snapshot.", extra={"snapshot_id": str(existing_snapshot.snapshot_id)})
                    return 0
            else:
                logger.error(
                    "Snapshot for version exists with different SHA-256 hash. Rejecting inconsistent import.",
                    extra={"version": version, "existing_hash": existing_snapshot.combined_sha256_hash, "new_hash": combined_hash},
                )
                return 1

        # 5. Create new snapshot in IMPORTING state
        snapshot_id = uuid.uuid4()
        snapshot = TaxonomySnapshot(
            snapshot_id=snapshot_id,
            source="ONET",
            source_version=version,
            combined_sha256_hash=combined_hash,
            state=TaxonomySnapshotState.IMPORTING,
            source_filenames={k: str(p.name) for k, p in file_paths.items()},
            record_counts={},
            imported_at=now,
            created_at=now,
            updated_at=now,
        )
        session.add(snapshot)
        session.flush()

        # 6. Stream and import occupation_data.csv
        occupation_id_by_soc: Dict[str, uuid.UUID] = {}
        occupation_count = 0

        with open(file_paths["occupation_data.csv"], "r", encoding="utf-8-sig", errors="replace") as f:
            reader = csv.reader(f)
            next(reader, None)  # header
            batch = []
            for row in reader:
                if not row or len(row) < 3:
                    continue
                soc_code = row[0].strip()
                title = row[1].strip()
                description = row[2].strip() if row[2].strip() else None

                if not soc_code or not title:
                    continue

                norm_title = normalize_search_query(title)
                concept_id = uuid.uuid4()
                occupation_id_by_soc[soc_code] = concept_id

                occ = OccupationConcept(
                    concept_id=concept_id,
                    snapshot_id=snapshot_id,
                    onet_soc_code=soc_code,
                    canonical_title=title,
                    normalized_title=norm_title,
                    description=description,
                    source_provenance=f"ONET_{version}",
                    created_at=now,
                )
                batch.append(occ)
                occupation_count += 1
                if len(batch) >= BATCH_SIZE:
                    session.add_all(batch)
                    session.flush()
                    batch = []
            if batch:
                session.add_all(batch)
                session.flush()

        # 7. Stream and import job_titles.csv (Aliases)
        alias_count = 0
        seen_aliases: Set[Tuple[uuid.UUID, str]] = set()

        with open(file_paths["job_titles.csv"], "r", encoding="utf-8-sig", errors="replace") as f:
            reader = csv.reader(f)
            next(reader, None)  # header
            batch = []
            for row in reader:
                if not row or len(row) < 3:
                    continue
                soc_code = row[0].strip()
                alias_title = row[2].strip()

                if not soc_code or not alias_title:
                    continue

                occ_id = occupation_id_by_soc.get(soc_code)
                if not occ_id:
                    continue

                norm_alias = normalize_search_query(alias_title)
                if (occ_id, norm_alias) in seen_aliases:
                    continue
                seen_aliases.add((occ_id, norm_alias))

                alias = OccupationAlias(
                    alias_id=uuid.uuid4(),
                    occupation_concept_id=occ_id,
                    job_title_alias=alias_title,
                    normalized_alias=norm_alias,
                    source_provenance=f"ONET_{version}_JOB_TITLES",
                    created_at=now,
                )
                batch.append(alias)
                alias_count += 1
                if len(batch) >= BATCH_SIZE:
                    session.add_all(batch)
                    session.flush()
                    batch = []
            if batch:
                session.add_all(batch)
                session.flush()

        # 8. Seed Controlled Skill Concepts & Aliases from Phase-1 SkillCatalog
        # This ensures existing canonical names take precedence
        skill_concept_by_norm_label: Dict[str, uuid.UUID] = {}
        skill_concept_count = 0
        skill_alias_count = 0

        for skill_def in SKILL_DEFINITIONS:
            norm_label = normalize_search_query(skill_def.canonical_name)
            if norm_label in skill_concept_by_norm_label:
                continue

            concept_id = uuid.uuid4()
            skill_concept_by_norm_label[norm_label] = concept_id

            sk = SkillConcept(
                concept_id=concept_id,
                snapshot_id=snapshot_id,
                canonical_label=skill_def.canonical_name,
                normalized_label=norm_label,
                category=skill_def.category.value if hasattr(skill_def.category, "value") else str(skill_def.category),
                source="INTERNAL_CONTROLLED",
                created_at=now,
            )
            session.add(sk)
            skill_concept_count += 1

            # Seed aliases
            for al in skill_def.aliases:
                norm_al = normalize_search_query(al)
                if norm_al and norm_al != norm_label:
                    sk_alias = SkillAlias(
                        alias_id=uuid.uuid4(),
                        skill_concept_id=concept_id,
                        alias_text=al,
                        normalized_alias=norm_al,
                        alias_source="INTERNAL_CONTROLLED",
                        created_at=now,
                    )
                    session.add(sk_alias)
                    skill_alias_count += 1

        session.flush()

        # 9. Stream software_skills.csv (Skills & Links)
        link_count = 0
        seen_links: Set[Tuple[uuid.UUID, uuid.UUID]] = set()

        with open(file_paths["software_skills.csv"], "r", encoding="utf-8-sig", errors="replace") as f:
            reader = csv.reader(f)
            next(reader, None)  # header
            batch_links = []
            for row in reader:
                if not row or len(row) < 3:
                    continue
                soc_code = row[0].strip()
                skill_name = row[2].strip()
                element_id = row[3].strip() if len(row) > 3 and row[3].strip() else None
                element_name = row[4].strip() if len(row) > 4 and row[4].strip() else None
                hot_tech = (row[5].strip().upper() == "Y") if len(row) > 5 else False
                in_demand = (row[6].strip().upper() == "Y") if len(row) > 6 else False

                if not soc_code or not skill_name:
                    continue

                occ_id = occupation_id_by_soc.get(soc_code)
                if not occ_id:
                    continue

                norm_skill = normalize_search_query(skill_name)
                skill_id = skill_concept_by_norm_label.get(norm_skill)

                if not skill_id:
                    skill_id = uuid.uuid4()
                    skill_concept_by_norm_label[norm_skill] = skill_id

                    sk = SkillConcept(
                        concept_id=skill_id,
                        snapshot_id=snapshot_id,
                        canonical_label=skill_name,
                        normalized_label=norm_skill,
                        category=element_name,
                        source=f"ONET_{version}",
                        external_id=element_id,
                        created_at=now,
                    )
                    session.add(sk)
                    session.flush()
                    skill_concept_count += 1

                if (occ_id, skill_id) in seen_links:
                    continue
                seen_links.add((occ_id, skill_id))

                link = OccupationSkillLink(
                    link_id=uuid.uuid4(),
                    occupation_concept_id=occ_id,
                    skill_concept_id=skill_id,
                    hot_technology=hot_tech,
                    in_demand=in_demand,
                    element_id=element_id,
                    element_name=element_name,
                    created_at=now,
                )
                batch_links.append(link)
                link_count += 1
                if len(batch_links) >= BATCH_SIZE:
                    session.add_all(batch_links)
                    session.flush()
                    batch_links = []

            if batch_links:
                session.add_all(batch_links)
                session.flush()

        # 10. Update record counts and activate snapshot atomically
        counts = {
            "occupations": occupation_count,
            "occupation_aliases": alias_count,
            "skills": skill_concept_count,
            "skill_aliases": skill_alias_count,
            "occupation_skill_links": link_count,
        }
        snapshot.record_counts = counts

        # Supersede any previous ACTIVE snapshots
        session.execute(
            update(TaxonomySnapshot)
            .where(TaxonomySnapshot.state == TaxonomySnapshotState.ACTIVE)
            .values(state=TaxonomySnapshotState.SUPERSEDED, updated_at=now)
        )

        snapshot.state = TaxonomySnapshotState.ACTIVE
        snapshot.activated_at = now
        snapshot.updated_at = now

        session.commit()
        logger.info(
            f"Successfully imported O*NET {version} snapshot.",
            extra={"snapshot_id": str(snapshot_id), "record_counts": counts},
        )
        print(f"Successfully imported O*NET {version} snapshot {snapshot_id}: {counts}")
        return 0

    except Exception as e:
        session.rollback()
        logger.error(
            "Failed O*NET import transaction. Rolled back.",
            extra={"error_type": type(e).__name__},
        )
        print(f"Error during import: {e}", file=sys.stderr)
        return 1
    finally:
        if close_session:
            session.close()


def main():
    parser = argparse.ArgumentParser(description="Offline O*NET 31.0 Taxonomy Importer")
    parser.add_argument("--source-dir", required=True, type=str, help="Directory containing O*NET CSV files")
    parser.add_argument("--version", default="31.0", type=str, help="O*NET version (default: 31.0)")
    args = parser.parse_args()

    source_path = Path(args.source_dir).resolve()
    exit_code = import_onet_taxonomy(source_dir=source_path, version=args.version)
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
