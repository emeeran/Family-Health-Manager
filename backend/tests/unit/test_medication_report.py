"""Unit tests for the Medication Report router.

Covers the context builder (active meds + DDI + recalls), the prompt prefix used
for persistence/retrieval, and the section formatters. ``MedicationService`` and
``DrugInfoService`` are mocked — no DB, no network, no LLM.
"""

from unittest.mock import AsyncMock, patch
from uuid import uuid4

from app.routers import member_medication_report as mmr


async def test_context_empty_when_no_meds():
    member_id = uuid4()
    with (
        patch.object(mmr, "MedicationService") as MS,
        patch.object(mmr, "DrugInfoService") as DI,
    ):
        MS.return_value.get_active_medications = AsyncMock(return_value=[])
        ctx = await mmr._build_medication_context(member_id, db=None)
    assert "none recorded" in ctx.lower()
    # No meds -> drug-info lookups must not even run.
    DI.return_value.ddi.assert_not_called()


async def test_context_includes_meds_interactions_and_recalls():
    member_id = uuid4()
    meds = [
        {
            "medicine": "Syndopa 110",
            "type": "Tab",
            "dosage": "1-1-1",
            "timing": "before_food",
            "duration": "30 days",
            "provider_name": "Dr. Rao",
        }
    ]
    interactions = [
        {
            "description": "May increase BP-lowering effect",
            "severity": "moderate",
            "pair": "Syndopa + Amlodipine",
        }
    ]
    recalls = [
        {
            "reason_for_recall": "Contamination",
            "product_description": "Syndopa 110 lot X",
            "matched_medications": ["levodopa"],
        }
    ]
    with (
        patch.object(mmr, "MedicationService") as MS,
        patch.object(mmr, "DrugInfoService") as DI,
    ):
        MS.return_value.get_active_medications = AsyncMock(return_value=meds)
        DI.return_value.ddi = AsyncMock(return_value=interactions)
        DI.return_value.recalls = AsyncMock(return_value=recalls)
        ctx = await mmr._build_medication_context(member_id, db=None)

    assert "Syndopa 110" in ctx
    assert "1-1-1" in ctx
    assert "May increase BP-lowering effect" in ctx
    assert "Contamination" in ctx


async def test_prompt_carries_member_prefix():
    member_id = uuid4()
    meds = [{"medicine": "Metformin", "type": "Tab"}]
    with (
        patch.object(mmr, "MedicationService") as MS,
        patch.object(mmr, "DrugInfoService") as DI,
    ):
        MS.return_value.get_active_medications = AsyncMock(return_value=meds)
        DI.return_value.ddi = AsyncMock(return_value=[])
        DI.return_value.recalls = AsyncMock(return_value=[])
        prompt = await mmr._build_prompt(member_id, db=None)

    assert prompt.startswith(f"__medreport__{member_id}__")
    assert "Metformin" in prompt
    # The instruction prompt is embedded after the prefix.
    assert "COMPREHENSIVE MEDICATION REPORT" in prompt


def test_fmt_interactions_handles_empty():
    text = mmr._fmt_interactions([])
    assert "none" in text.lower()


def test_fmt_interactions_renders_pair_and_severity():
    out = mmr._fmt_interactions(
        [{"pair": "A + B", "severity": "major", "description": "risk of X"}]
    )
    assert "A + B" in out
    assert "major" in out
    assert "risk of X" in out


def test_fmt_recalls_handles_empty():
    assert "no active recalls" in mmr._fmt_recalls([]).lower()


def test_fmt_recalls_caps_to_twenty():
    recalls = [
        {"reason_for_recall": f"r{i}", "product_description": "p", "matched_medications": ["m"]}
        for i in range(30)
    ]
    assert len(mmr._fmt_recalls(recalls).strip().splitlines()) == 20


def test_fmt_meds_includes_schedule_and_provider():
    out = mmr._fmt_meds(
        [
            {
                "medicine": "Aspirin",
                "type": "Tab",
                "dosage": "0-0-1",
                "timing": "after_food",
                "duration": "ongoing",
                "provider_name": "Dr. Smith",
            }
        ]
    )
    assert "Aspirin" in out
    assert "0-0-1" in out
    assert "Dr. Smith" in out
