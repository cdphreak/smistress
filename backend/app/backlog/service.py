from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.db.enums import TaskStatus
from app.db.models.loop import Proof
from app.db.models.task import Task
from app.economy import service as econ_svc
from app.llm.provider import LLMProvider
from app.loop import service as loop_svc
from app.loop import verification
from app.memory import service as mem_svc
from app.memory.store import build_memory_store

_log = logging.getLogger("app.backlog")


@dataclass
class SettlementSummary:
    judged: int = 0
    passed: int = 0
    failed: int = 0
    re_proven: int = 0
    skipped: int = 0
    errored: int = 0
    memory_drained: int = 0


async def settle_backlog(
    session: AsyncSession,
    profile_id: uuid.UUID,
    *,
    provider: LLMProvider,
    settings: Settings,
    now: datetime | None = None,
) -> SettlementSummary:
    """Drain this profile's memory outbox, then settle its queued media proofs.

    Offline-6's settle beat: media proofs queue as ``pending_review`` while she is
    away; this drains the outbox, dedups queued proofs per task (latest wins;
    older duplicates are stamped ``superseded`` — the single-outcome-per-task
    invariant), invokes the vision judge, and applies merit/debt via the existing
    economy + discipline units. Services flush; the caller commits.

    A settle drains up to ``drain_outbox``'s limit (50) pending memory episodes
    per call; repeated settles continue draining the remainder.
    """
    summary = SettlementSummary()
    now = now or datetime.now(timezone.utc)

    # 1. Drain this profile's memory outbox FIRST (spec §4).
    store = build_memory_store(settings)
    summary.memory_drained = await mem_svc.drain_outbox(
        session, store, profile_id=profile_id
    )

    # 2. Per-task dedup: latest pending_review proof per task wins (DISTINCT ON).
    # Belt-and-braces: a media-less row can never be picked for judging (a text-
    # only note has nothing to show her). The supersede step below intentionally
    # keeps its FULL pending_review-of-profile scope so a stray media-less row is
    # CLOSED (superseded) rather than clogging the queue forever.
    dedup_stmt = (
        select(Proof)
        .distinct(Proof.task_id)
        .where(
            Proof.verdict == "pending_review",
            Proof.profile_id == profile_id,
            Proof.media_uri.is_not(None),
        )
        .order_by(Proof.task_id, Proof.created_at.desc())
    )
    judged_proofs = (await session.execute(dedup_stmt)).scalars().all()
    judged_ids = [p.id for p in judged_proofs]

    # Stamp every OTHER pending_review proof for this profile as superseded
    # (single-outcome-per-task invariant). Skip when nothing was judged.
    if judged_ids:
        others = (
            await session.execute(
                select(Proof).where(
                    Proof.verdict == "pending_review",
                    Proof.profile_id == profile_id,
                    Proof.id.not_in(judged_ids),
                )
            )
        ).scalars().all()
        for oth in others:
            oth.verdict = "superseded"
        await session.flush()

    # 3. Judge each latest proof.
    for proof in judged_proofs:
        task = await session.get(Task, proof.task_id)
        # Transient provider errors are swallowed; the proof stays pending_review
        # for the next settle. Outcome application is deliberately OUTSIDE this
        # try/except — a DB/economy error must surface, not silently become errored.
        try:
            result = await verification.verify_media(
                task, media_uri=proof.media_uri, provider=provider, settings=settings
            )
        except Exception:  # noqa: BLE001 - transient provider error; retry next settle
            summary.errored += 1
            continue

        # Misconfig branch: vision configured but provider lacks vision -> skip.
        # Proof stays pending_review (untouched).
        if result.verdict == verification.PENDING_REVIEW:
            summary.skipped += 1
            continue

        # Judged outcome (pass/fail/re_proof): persist the full verdict block,
        # mirroring verify_task's persistence (ruling #3: all four fields).
        proof.verdict = result.verdict
        proof.confidence = result.confidence
        proof.reasoning = result.reasoning
        proof.issues = result.issues
        summary.judged += 1

        if result.verdict == verification.PASS:
            task.status = TaskStatus.VERIFIED_PASS
            await econ_svc.apply_task_outcome(session, task)
            await loop_svc.apply_terminal_discipline(session, task)
            summary.passed += 1
        elif result.verdict == verification.FAIL:
            task.status = TaskStatus.VERIFIED_FAIL
            await econ_svc.apply_task_outcome(session, task)
            await loop_svc.apply_terminal_discipline(session, task)
            summary.failed += 1
        else:  # re_proof — task stays proof_submitted (already is)
            summary.re_proven += 1

        # Enqueue a memory episode for judged outcomes only (pass/fail/re_proof).
        await mem_svc.enqueue_episode(
            session,
            profile_id,
            name="proof judged",
            body=f"Proof for '{task.description}' judged: {result.verdict}.",
            source="text",
            source_description="backlog",
            reference_time=now,
        )

    # One warning per settle when proofs were skipped due to vision misconfig.
    if summary.skipped > 0:
        _log.warning(
            "profile %s: %d media proof(s) skipped — vision provider lacks "
            "vision support",
            profile_id,
            summary.skipped,
        )

    await session.flush()
    return summary
