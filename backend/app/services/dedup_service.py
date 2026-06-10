"""Medical record deduplication service.

Scans a member's records for potential duplicates using multiple criteria,
groups them, and supports merging duplicate groups into a single record.
"""
import json
import logging
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.models.base import HealthRecord
from app.models.medication import Medication
from app.models.lab_result import LabResult

logger = logging.getLogger(__name__)

# Maximum days between record_dates to consider as "adjacent"
DATE_PROXIMITY_DAYS = 3

# Minimum Jaccard similarity for "similar content" criterion
CONTENT_SIMILARITY_THRESHOLD = 0.5


def _extract_medicine_names(clinical_data: str | None) -> set[str]:
    """Extract lowercase medicine names from structured clinical_data JSON."""
    if not clinical_data:
        return set()
    try:
        parsed = json.loads(clinical_data)
        if not isinstance(parsed, dict):
            return set()
        # Structured format: {"_type": "structured", "prescriptions": [...]}
        prescriptions = parsed.get("prescriptions", [])
        if isinstance(prescriptions, list):
            return {
                rx.get("medicine", "").strip().lower()
                for rx in prescriptions
                if isinstance(rx, dict) and rx.get("medicine", "").strip()
            }
    except (json.JSONDecodeError, ValueError, TypeError):
        pass
    return set()


def _extract_lab_test_names(clinical_data: str | None) -> set[str]:
    """Extract lowercase lab test names from structured clinical_data JSON."""
    if not clinical_data:
        return set()
    try:
        parsed = json.loads(clinical_data)
        if not isinstance(parsed, dict):
            return set()
        lab_tests = parsed.get("lab_results", parsed.get("lab_tests", []))
        if isinstance(lab_tests, list):
            return {
                t.get("test_name", "").strip().lower()
                for t in lab_tests
                if isinstance(t, dict) and t.get("test_name", "").strip()
            }
    except (json.JSONDecodeError, ValueError, TypeError):
        pass
    return set()


def _jaccard(set_a: set, set_b: set) -> float:
    """Compute Jaccard similarity between two sets."""
    if not set_a and not set_b:
        return 0.0
    if not set_a or not set_b:
        return 0.0
    intersection = len(set_a & set_b)
    union = len(set_a | set_b)
    return intersection / union if union > 0 else 0.0


class UnionFind:
    """Simple union-find for grouping connected record pairs."""

    def __init__(self):
        self._parent: dict[str, str] = {}

    def find(self, x: str) -> str:
        if x not in self._parent:
            self._parent[x] = x
        if self._parent[x] != x:
            self._parent[x] = self.find(self._parent[x])
        return self._parent[x]

    def union(self, x: str, y: str):
        rx, ry = self.find(x), self.find(y)
        if rx != ry:
            self._parent[rx] = ry

    def groups(self) -> dict[str, list[str]]:
        """Return {root: [members]}."""
        result: dict[str, list[str]] = {}
        for key in self._parent:
            root = self.find(key)
            result.setdefault(root, []).append(key)
        return result


class DedupService:
    """Medical record deduplication service."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def find_duplicates(self, member_id: UUID) -> dict:
        """Scan all non-deleted records for a member, return grouped duplicates.

        Returns dict matching DedupResponse schema with proper types.
        """
        from app.schemas.health_record import DuplicateRecordItem, DuplicateGroup
        # Load all non-deleted records with attachments and provider eagerly loaded
        result = await self.db.execute(
            select(HealthRecord)
            .options(
                joinedload(HealthRecord.attachments),
                joinedload(HealthRecord.provider),
            )
            .where(
                HealthRecord.family_member_id == member_id,
                HealthRecord.is_deleted.is_(False),
            )
            .order_by(HealthRecord.record_date.desc())
        )
        records = list(result.scalars().unique().all())
        total_scanned = len(records)

        if len(records) < 2:
            return {"groups": [], "total_records_scanned": total_scanned}

        # Index: attachment content_hash -> set of record ids
        hash_to_records: dict[str, set[str]] = {}
        record_data: dict[str, dict] = {}

        for rec in records:
            rid = str(rec.id)
            rec_meds = _extract_medicine_names(rec.clinical_data)
            rec_labs = _extract_lab_test_names(rec.clinical_data)

            record_data[rid] = {
                "record": rec,
                "medicine_names": rec_meds,
                "lab_test_names": rec_labs,
            }

            for att in rec.attachments:
                if att.content_hash:
                    hash_to_records.setdefault(att.content_hash, set()).add(rid)

        # Build candidate pairs with scores and reasons
        pair_scores: dict[tuple[str, str], tuple[int, list[str]]] = {}
        uf = UnionFind()

        for i in range(len(records)):
            for j in range(i + 1, len(records)):
                a_id = str(records[i].id)
                b_id = str(records[j].id)
                ra = records[i]
                rb = records[j]
                rd_a = record_data[a_id]
                rd_b = record_data[b_id]

                score = 0
                reasons: list[str] = []

                # Criterion 1: Same type + adjacent date (±3 days)
                if ra.record_type == rb.record_type:
                    day_diff = abs((ra.record_date - rb.record_date).days)
                    if day_diff <= DATE_PROXIMITY_DAYS:
                        score += 1
                        reasons.append("same_type_adjacent_date")

                # Criterion 2: Same provider + same diagnosis
                if (
                    ra.provider_id
                    and rb.provider_id
                    and ra.provider_id == rb.provider_id
                    and ra.diagnosis
                    and rb.diagnosis
                    and ra.diagnosis.strip().lower() == rb.diagnosis.strip().lower()
                ):
                    score += 1
                    reasons.append("same_provider_diagnosis")

                # Criterion 3: Similar content (medicine names or lab tests)
                med_sim = _jaccard(rd_a["medicine_names"], rd_b["medicine_names"])
                lab_sim = _jaccard(rd_a["lab_test_names"], rd_b["lab_test_names"])
                if med_sim >= CONTENT_SIMILARITY_THRESHOLD or lab_sim >= CONTENT_SIMILARITY_THRESHOLD:
                    score += 1
                    reasons.append("similar_content")

                # Criterion 4: Same attachment file (content hash)
                shared_hashes = False
                for hash_val, rec_ids in hash_to_records.items():
                    if a_id in rec_ids and b_id in rec_ids:
                        shared_hashes = True
                        break
                if shared_hashes:
                    score += 1
                    reasons.append("same_attachment")

                if score >= 1:
                    pair_key = (a_id, b_id) if a_id < b_id else (b_id, a_id)
                    pair_scores[pair_key] = (score, reasons)
                    uf.union(a_id, b_id)

        if not pair_scores:
            return {"groups": [], "total_records_scanned": total_scanned}

        # Build groups from union-find
        uf_groups = uf.groups()

        # Only keep groups with >1 member and actual pair scores
        groups = []
        for root, members in uf_groups.items():
            if len(members) < 2:
                continue

            # Collect match reasons and max score for this group
            group_reasons: set[str] = set()
            group_max_score = 0
            for m_a in members:
                for m_b in members:
                    if m_a >= m_b:
                        continue
                    pair_key = tuple(sorted([m_a, m_b]))
                    if pair_key in pair_scores:
                        sc, rs = pair_scores[pair_key]
                        group_max_score = max(group_max_score, sc)
                        group_reasons.update(rs)

            # Build record items
            record_items = []
            for mid in members:
                rec = record_data[mid]["record"]
                record_items.append(DuplicateRecordItem(
                    id=rec.id,
                    record_type=rec.record_type,
                    record_date=rec.record_date,
                    diagnosis=rec.diagnosis,
                    provider_name=rec.provider.name if rec.provider else None,
                    provider_id=rec.provider_id,
                    prescription_text=rec.prescription_text,
                    has_attachments=len(rec.attachments) > 0,
                    attachment_count=len(rec.attachments),
                    created_at=rec.created_at,
                ))

            # Recommend keeper: most attachments, then longest clinical_data
            recommended = max(
                members,
                key=lambda mid: (
                    len(record_data[mid]["record"].attachments),
                    len(record_data[mid]["record"].clinical_data or ""),
                ),
            )

            groups.append(DuplicateGroup(
                records=record_items,
                recommended_keeper_id=UUID(recommended),
                match_reasons=sorted(group_reasons),
                score=group_max_score,
            ))

        # Sort groups by score desc, then by number of records desc
        groups.sort(key=lambda g: (g.score, len(g.records)), reverse=True)

        return {"groups": [g.model_dump(mode="json") for g in groups], "total_records_scanned": total_scanned}

    async def merge_records(self, member_id: UUID, keeper_id: UUID, loser_ids: list[UUID]) -> HealthRecord:
        """Merge loser records into keeper. Moves attachments, merges tags, soft-deletes losers."""
        # Load keeper with attachments
        result = await self.db.execute(
            select(HealthRecord)
            .options(joinedload(HealthRecord.attachments))
            .where(
                HealthRecord.id == keeper_id,
                HealthRecord.family_member_id == member_id,
                HealthRecord.is_deleted.is_(False),
            )
        )
        keeper = result.unique().scalar_one_or_none()
        if not keeper:
            raise ValueError("Keeper record not found")

        # Load losers
        losers_result = await self.db.execute(
            select(HealthRecord)
            .options(joinedload(HealthRecord.attachments))
            .where(
                HealthRecord.id.in_(loser_ids),
                HealthRecord.family_member_id == member_id,
                HealthRecord.is_deleted.is_(False),
            )
        )
        losers = list(losers_result.scalars().unique().all())
        if len(losers) != len(loser_ids):
            raise ValueError("One or more loser records not found")

        # Collect existing keeper attachment IDs to avoid duplicates
        keeper_attachment_ids = {att.id for att in keeper.attachments}

        for loser in losers:
            # Move attachments from loser to keeper (skip duplicates by id)
            for att in loser.attachments:
                if att.id not in keeper_attachment_ids:
                    att.health_record_id = keeper_id
                    keeper_attachment_ids.add(att.id)

            # Merge tags
            if loser.tags:
                try:
                    loser_tags = json.loads(loser.tags) if isinstance(loser.tags, str) else loser.tags
                    keeper_tags = json.loads(keeper.tags) if keeper.tags and isinstance(keeper.tags, str) else (json.loads(keeper.tags) if keeper.tags else [])
                    merged = list(set(keeper_tags + (loser_tags if isinstance(loser_tags, list) else [])))
                    keeper.tags = json.dumps(merged) if merged else keeper.tags
                except (json.JSONDecodeError, ValueError, TypeError):
                    pass

            # Fill in missing fields from loser
            if not keeper.diagnosis and loser.diagnosis:
                keeper.diagnosis = loser.diagnosis
            if not keeper.prescription_text and loser.prescription_text:
                keeper.prescription_text = loser.prescription_text
            if not keeper.next_review_date and loser.next_review_date:
                keeper.next_review_date = loser.next_review_date
            if not keeper.provider_id and loser.provider_id:
                keeper.provider_id = loser.provider_id

            # Reassign medications
            await self.db.execute(
                update(Medication)
                .where(Medication.health_record_id == loser.id)
                .values(health_record_id=keeper_id)
            )

            # Reassign lab results
            await self.db.execute(
                update(LabResult)
                .where(LabResult.health_record_id == loser.id)
                .values(health_record_id=keeper_id)
            )

            # Soft-delete loser
            loser.is_deleted = True

        await self.db.flush()
        await self.db.refresh(keeper, ["provider", "attachments"])
        return keeper
