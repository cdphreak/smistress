import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from app.config import Settings
from app.db.enums import ProofRequirement, TaskStatus
from app.db.models.loop import Proof
from app.db.models.memory import MemoryEpisode
from app.economy import service as econ_svc
from app.llm.mock import MockLLMProvider
from app.llm.types import ChatResult
from app.loop import service as loop_svc
from app.backlog import service as backlog_svc
from app.schemas.onboarding import ProfileCreate
from app.services import profile as profile_svc


VISION_SETTINGS = Settings(vision_model="qwen2.5-vl")


async def _profile(session):
    p = await profile_svc.create_profile(
        session, ProfileCreate(is_adult=True, consent_acknowledged=True)
    )
    await session.flush()
    return p


async def _media_proof_pending_review(session, p, *, description="photo task"):
    task = await loop_svc.assign_task(
        session, p.id, description=description, proof_requirement=ProofRequirement.PHOTO,
        merit_reward=10,
    )
    await session.flush()
    await loop_svc.start_task(session, task.id)
    await session.flush()
    await loop_svc.submit_proof(
        session, task.id, media_uri="data:image/png;base64,AAA", settings=VISION_SETTINGS,
    )
    await session.flush()
    return task


async def test_settle_judges_pass_and_applies_merit(session):
    p = await _profile(session)
    task = await _media_proof_pending_review(session, p)
    await session.commit()

    provider = MockLLMProvider(supports_vision=True, scripted=[ChatResult(
        content='{"verdict": "pass", "confidence": 90, "reasoning": "visible", "issues": []}'
    )])
    summary = await backlog_svc.settle_backlog(
        session, p.id, provider=provider, settings=VISION_SETTINGS,
    )
    await session.commit()

    assert summary.passed == 1 and summary.judged == 1
    assert (await econ_svc.get_economy(session, p.id)).merit == 10
    refreshed = await session.get(type(task), task.id)
    assert refreshed.status is TaskStatus.VERIFIED_PASS


async def test_settle_judges_fail_issues_discipline(session):
    p = await _profile(session)
    task = await _media_proof_pending_review(session, p)
    await session.commit()

    provider = MockLLMProvider(supports_vision=True, scripted=[ChatResult(
        content='{"verdict": "fail", "confidence": 20, '
                '"reasoning": "absent", "issues": ["no subject"]}'
    )])
    summary = await backlog_svc.settle_backlog(
        session, p.id, provider=provider, settings=VISION_SETTINGS,
    )
    await session.commit()

    assert summary.failed == 1
    refreshed = await session.get(type(task), task.id)
    assert refreshed.status is TaskStatus.VERIFIED_FAIL
    assert (await econ_svc.get_economy(session, p.id)).debt > 0  # discipline issued


async def test_settle_reproof_leaves_task_proof_submitted(session):
    p = await _profile(session)
    task = await _media_proof_pending_review(session, p)
    await session.commit()

    provider = MockLLMProvider(supports_vision=True, scripted=[ChatResult(
        content='{"verdict": "re_proof", "confidence": 40, '
                '"reasoning": "unclear", "issues": ["dark"]}'
    )])
    summary = await backlog_svc.settle_backlog(
        session, p.id, provider=provider, settings=VISION_SETTINGS,
    )
    await session.commit()

    assert summary.re_proven == 1
    refreshed = await session.get(type(task), task.id)
    assert refreshed.status is TaskStatus.PROOF_SUBMITTED


async def test_settle_dedups_duplicate_pending_review_proofs_per_task(session):
    p = await _profile(session)
    task = await _media_proof_pending_review(session, p)  # first pending_review proof (AAA)
    aaa = (await session.execute(
        select(Proof).where(Proof.task_id == task.id)
    )).scalars().one()
    # second, newer pending_review proof for the SAME task (BBB)
    bbb = await loop_svc.submit_proof(
        session, task.id, media_uri="data:image/png;base64,BBB", settings=VISION_SETTINGS,
    )
    # Pin explicit created_at values: AAA earlier, BBB later. They would otherwise
    # tie on the transaction timestamp, leaving latest-wins ordering untestable.
    base = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    aaa.created_at = base
    bbb.created_at = base + timedelta(seconds=10)  # BBB is strictly later
    await session.commit()

    provider = MockLLMProvider(
        supports_vision=True,
        scripted=[ChatResult(
            content='{"verdict": "pass", "confidence": 90, "reasoning": "ok", "issues": []}'
        )],
    )
    summary = await backlog_svc.settle_backlog(
        session, p.id, provider=provider, settings=VISION_SETTINGS,
    )
    await session.commit()

    assert summary.judged == 1  # only the latest judged
    assert summary.passed == 1
    proofs = (
        await session.execute(select(Proof).where(Proof.task_id == task.id))
    ).scalars().all()
    verdicts = sorted(pr.verdict for pr in proofs)
    assert verdicts == ["pass", "superseded"]  # older one superseded, not double-judged
    # Latest-wins pin: BBB (the newer) is the one judged (pass); AAA is superseded.
    judged = next(pr for pr in proofs if pr.verdict == "pass")
    superseded = next(pr for pr in proofs if pr.verdict == "superseded")
    assert judged.media_uri == "data:image/png;base64,BBB"
    assert superseded.verdict == "superseded"
    assert (await econ_svc.get_economy(session, p.id)).merit == 10  # not 20


async def test_settle_excludes_media_less_pending_review_from_dedup_and_supersedes_it(session):
    p = await _profile(session)
    task = await _media_proof_pending_review(session, p)  # real media proof, pending_review
    media_proof = (await session.execute(
        select(Proof).where(Proof.task_id == task.id)
    )).scalars().one()
    # Pin both timestamps explicitly so dedup ordering is deterministic (clock-drift free).
    base = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    media_proof.created_at = base
    await session.flush()
    # A NEWER media-less proof, queued for review, that would WIN dedup (latest wins)
    # if media-less rows weren't excluded from the dedup SELECT.
    session.add(Proof(
        task_id=task.id,
        profile_id=p.id,
        content="text-only note, no media attached",
        media_uri=None,
        verdict="pending_review",
        created_at=base + timedelta(seconds=10),  # strictly newer than the media proof
    ))
    await session.commit()

    provider = MockLLMProvider(supports_vision=True, scripted=[ChatResult(
        content='{"verdict": "pass", "confidence": 90, "reasoning": "visible", "issues": []}'
    )])
    summary = await backlog_svc.settle_backlog(
        session, p.id, provider=provider, settings=VISION_SETTINGS,
    )
    await session.commit()

    assert summary.judged == 1
    rows = (await session.execute(select(Proof).where(Proof.task_id == task.id))).scalars().all()
    by_media = {pr.media_uri: pr for pr in rows}
    media_pr = by_media["data:image/png;base64,AAA"]
    none_pr = by_media[None]
    # The MEDIA proof is judged (pass); the media-less row is CLOSED (superseded),
    # never left to clog the queue forever.
    assert media_pr.verdict == "pass"
    assert none_pr.verdict == "superseded"


async def test_settle_skips_and_logs_when_provider_lacks_vision(caplog, session):
    p = await _profile(session)
    await _media_proof_pending_review(session, p)
    await session.commit()

    provider = MockLLMProvider(supports_vision=False)  # permanent misconfig
    with caplog.at_level(logging.WARNING, logger="app.backlog"):
        summary = await backlog_svc.settle_backlog(
            session, p.id, provider=provider, settings=VISION_SETTINGS,
        )
    await session.commit()

    assert summary.skipped == 1 and summary.judged == 0
    assert any("vision" in r.message.lower() for r in caplog.records)


async def test_settle_counts_errored_on_transient_provider_exception_and_leaves_pending(session):
    class _BoomProvider:
        supports_vision = True
        async def chat(self, messages, *, model=None, tools=None):
            raise RuntimeError("vision endpoint down")

    p = await _profile(session)
    task = await _media_proof_pending_review(session, p)
    await session.commit()

    summary = await backlog_svc.settle_backlog(
        session, p.id, provider=_BoomProvider(), settings=VISION_SETTINGS,
    )
    await session.commit()

    assert summary.errored == 1 and summary.judged == 0
    refreshed = await session.get(type(task), task.id)
    assert refreshed.status is TaskStatus.PROOF_SUBMITTED  # untouched, retriable
    proof = (
        await session.execute(
            select(Proof).where(Proof.task_id == task.id).order_by(Proof.created_at.desc())
        )
    ).scalars().first()
    assert proof.verdict == "pending_review"


async def test_settle_drains_memory_for_this_profile_only(session):
    from app.memory import service as mem_svc

    p = await _profile(session)
    other = await _profile(session)
    # queue one episode for p and one for `other`
    await mem_svc.enqueue_episode(
        session, p.id, name="p-ep", body="x", source="text",
        source_description="t", reference_time=datetime.now(timezone.utc),
    )
    await mem_svc.enqueue_episode(
        session, other.id, name="other-ep", body="x", source="text",
        source_description="t", reference_time=datetime.now(timezone.utc),
    )
    await session.commit()

    provider = MockLLMProvider(supports_vision=True)
    summary = await backlog_svc.settle_backlog(
        session, p.id, provider=provider, settings=VISION_SETTINGS,
    )
    await session.commit()

    assert summary.memory_drained == 1  # only p's episode
    other_rows = (
        await session.execute(
            select(MemoryEpisode).where(MemoryEpisode.profile_id == other.id)
        )
    ).scalars().all()
    assert len(other_rows) == 1 and other_rows[0].status == "pending"
