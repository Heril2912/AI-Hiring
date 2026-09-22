"""Domain service orchestrating Candidate Practice session state machine, snapshotting, and executions."""
from datetime import datetime, timedelta, timezone
import hashlib
import json
import logging
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID, uuid4

from fastapi import HTTPException, status
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session, selectinload

from app.models.auth import UserRecord
from app.models.candidate_access import (
    CandidateAccountBindingRecord,
    CandidateBindingStatus,
    CandidatePracticeMcqAnswerRecord,
    CandidatePracticeMessageRecord,
    CandidatePracticeReleaseRecord,
    CandidatePracticeSessionRecord,
)
from app.models.interview import AiInterviewQuestionSetRecord
from app.models.job import JobRequisition, JobVersion
from app.schemas.mcq_contract import McqOptionDto
from app.schemas.phase3_enums import (
    PracticeMessageKind,
    PracticeMessageRole,
    PracticeReleaseStatus,
    PracticeSection,
    PracticeSessionLifecycle,
    QuestionFormat,
)
from app.schemas.practice_follow_up_contract import (
    BoundedPracticeFollowUpRequest,
    BoundedPracticeFollowUpResponse,
)
from app.schemas.practice_session_contract import (
    PracticeActiveQuestionDto,
    PracticeConversationAnswerRequest,
    PracticeMcqAnswerRequest,
    PracticeMessageDto,
    PracticeSessionAbandonResponse,
    PracticeSessionDetailResponse,
    PracticeSessionStartRequest,
)
from app.services.practice_follow_up_service import (
    request_practice_conversation_follow_up,
)

logger = logging.getLogger("ai_hiring.services.practice_session")


def _get_active_binding(candidate_user: UserRecord, db: Session) -> CandidateAccountBindingRecord:
    stmt = select(CandidateAccountBindingRecord).where(
        CandidateAccountBindingRecord.user_id == candidate_user.user_id,
        CandidateAccountBindingRecord.status == CandidateBindingStatus.ACTIVE.value,
    )
    binding = db.execute(stmt).scalar_one_or_none()
    if not binding:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "CANDIDATE_ACCESS_SUSPENDED", "message": "Active candidate binding not found."},
        )
    return binding


def _compute_snapshot_hash(snapshot: List[Dict[str, Any]]) -> str:
    canonical = json.dumps(snapshot, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _map_session_to_dto(session: CandidatePracticeSessionRecord) -> PracticeSessionDetailResponse:
    now = datetime.now(timezone.utc)
    
    # Auto-expire if in progress but past expiry
    if session.lifecycle_status == PracticeSessionLifecycle.IN_PROGRESS.value and session.expires_at:
        exp = session.expires_at if session.expires_at.tzinfo else session.expires_at.replace(tzinfo=timezone.utc)
        if now > exp:
            session.lifecycle_status = PracticeSessionLifecycle.EXPIRED.value
            session.expired_at = now

    # Derive active question
    active_q: Optional[PracticeActiveQuestionDto] = None
    snapshot = session.questions_snapshot or []
    conv_questions = [q for q in snapshot if q.get("question_format") == QuestionFormat.CONVERSATION.value]
    mcq_questions = [q for q in snapshot if q.get("question_format") == QuestionFormat.MCQ_SINGLE_ANSWER.value]

    if session.lifecycle_status == PracticeSessionLifecycle.IN_PROGRESS.value:
        if session.current_section == PracticeSection.CONVERSATION.value:
            if 0 <= session.current_conv_index < len(conv_questions):
                raw_q = conv_questions[session.current_conv_index]
                active_q = PracticeActiveQuestionDto(
                    question_id=UUID(raw_q["question_id"]),
                    question_format=QuestionFormat.CONVERSATION.value,
                    wording=raw_q["wording"],
                    competency_name=raw_q["competency_name"],
                    options=None,
                    difficulty=raw_q.get("difficulty"),
                    estimated_time_minutes=raw_q.get("estimated_time_minutes", 3),
                    current_position=session.current_conv_index + 1,
                    total_in_section=len(conv_questions),
                )
        elif session.current_section == PracticeSection.MCQ.value:
            if 0 <= session.current_mcq_index < len(mcq_questions):
                raw_q = mcq_questions[session.current_mcq_index]
                safe_options = [
                    McqOptionDto(option_id=opt["option_id"], text=opt["text"])
                    for opt in raw_q.get("options", [])
                ]
                active_q = PracticeActiveQuestionDto(
                    question_id=UUID(raw_q["question_id"]),
                    question_format=QuestionFormat.MCQ_SINGLE_ANSWER.value,
                    wording=raw_q["wording"],
                    competency_name=raw_q["competency_name"],
                    options=safe_options,
                    difficulty=raw_q.get("difficulty"),
                    estimated_time_minutes=raw_q.get("estimated_time_minutes", 2),
                    current_position=session.current_mcq_index + 1,
                    total_in_section=len(mcq_questions),
                )

    # Format safe message transcript
    messages_dto: List[PracticeMessageDto] = []
    for msg in session.messages or []:
        messages_dto.append(
            PracticeMessageDto(
                message_id=msg.message_id,
                sequence_number=msg.sequence_number,
                role=msg.role,
                message_kind=msg.message_kind,
                source_question_id=msg.source_question_id,
                text=msg.text,
                created_at=msg.created_at,
            )
        )

    job_title = session.job_version.title if session.job_version else (session.job.title if session.job else "Practice Job")

    return PracticeSessionDetailResponse(
        session_id=session.session_id,
        release_id=session.release_id,
        job_id=session.job_id,
        job_title=job_title,
        job_revision=session.job_revision,
        lifecycle_status=session.lifecycle_status,
        current_section=session.current_section,
        current_conv_index=session.current_conv_index,
        total_conv_count=session.total_conv_count,
        current_mcq_index=session.current_mcq_index,
        total_mcq_count=session.total_mcq_count,
        total_response_count=session.total_response_count,
        active_question=active_q,
        messages=messages_dto,
        fallback_active=session.fallback_active,
        fallback_notice=(
            "Adaptive follow-ups are unavailable. Core practice is continuing."
            if session.fallback_active
            else None
        ),
        started_at=session.started_at,
        completed_at=session.completed_at,
        expires_at=session.expires_at,
    )


def start_or_resume_practice_session(
    candidate_user: UserRecord,
    release_id: UUID,
    db: Session,
) -> PracticeSessionDetailResponse:
    """Starts a new practice session or resumes an existing active IN_PROGRESS session."""
    binding = _get_active_binding(candidate_user, db)
    now = datetime.now(timezone.utc)

    # 1. Load release
    stmt_rel = (
        select(CandidatePracticeReleaseRecord)
        .options(
            selectinload(CandidatePracticeReleaseRecord.job),
            selectinload(CandidatePracticeReleaseRecord.job_version),
            selectinload(CandidatePracticeReleaseRecord.ai_set),
        )
        .where(
            CandidatePracticeReleaseRecord.release_id == release_id,
            CandidatePracticeReleaseRecord.candidate_id == binding.candidate_id,
            CandidatePracticeReleaseRecord.organization_id == binding.organization_id,
        )
    )
    release = db.execute(stmt_rel).scalar_one_or_none()
    if not release:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "RELEASE_NOT_FOUND", "message": "Practice assignment not found for candidate."},
        )

    if release.status != PracticeReleaseStatus.RELEASED.value:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "RELEASE_REVOKED", "message": "This practice assignment has been revoked."},
        )

    # 2. Check for existing active session for this release
    stmt_existing = (
        select(CandidatePracticeSessionRecord)
        .options(
            selectinload(CandidatePracticeSessionRecord.messages),
            selectinload(CandidatePracticeSessionRecord.job),
            selectinload(CandidatePracticeSessionRecord.job_version),
        )
        .where(
            CandidatePracticeSessionRecord.release_id == release.release_id,
            CandidatePracticeSessionRecord.candidate_id == binding.candidate_id,
            CandidatePracticeSessionRecord.lifecycle_status == PracticeSessionLifecycle.IN_PROGRESS.value,
        )
        .order_by(desc(CandidatePracticeSessionRecord.started_at))
    )
    existing_session = db.execute(stmt_existing).scalars().first()
    if existing_session:
        exp = existing_session.expires_at if existing_session.expires_at.tzinfo else existing_session.expires_at.replace(tzinfo=timezone.utc)
        if now <= exp:
            return _map_session_to_dto(existing_session)
        else:
            existing_session.lifecycle_status = PracticeSessionLifecycle.EXPIRED.value
            existing_session.expired_at = now
            db.commit()

    # 3. Check 24h attempt rate limit (max 3 attempts per 24 hours per job)
    window_start = now - timedelta(hours=24)
    stmt_attempts = (
        select(func.count(CandidatePracticeSessionRecord.session_id))
        .where(
            CandidatePracticeSessionRecord.candidate_id == binding.candidate_id,
            CandidatePracticeSessionRecord.job_id == release.job_id,
            CandidatePracticeSessionRecord.started_at >= window_start,
        )
    )
    attempt_count = db.execute(stmt_attempts).scalar() or 0
    if attempt_count >= 3:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "code": "ATTEMPT_LIMIT_REACHED",
                "message": "Maximum 3 practice attempts permitted within a 24-hour window for this job.",
            },
        )

    # 4. Extract approved question snapshot from AI Question Set
    ai_set = release.ai_set
    raw_items = ai_set.items if ai_set and ai_set.items else []
    
    conv_items = [
        it for it in raw_items
        if (it.get("question_format") or it.get("format") or "CONVERSATION") == QuestionFormat.CONVERSATION.value
    ]
    mcq_items = [
        it for it in raw_items
        if (it.get("question_format") or it.get("format")) == QuestionFormat.MCQ_SINGLE_ANSWER.value
    ]

    # Bound checks: max 5 conversation, max 10 MCQ
    if len(conv_items) > 5 or len(mcq_items) > 10:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "INVALID_QUESTION_SET_BOUNDS", "message": "Practice question set exceeds allowable bounds."},
        )

    if not conv_items and not mcq_items:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "NO_QUESTIONS_IN_RELEASE", "message": "No practice questions found in released interview set."},
        )

    # Build snapshot list
    snapshot: List[Dict[str, Any]] = []
    
    for i, it in enumerate(conv_items):
        q_id = str(it.get("slot_id") or it.get("question_id") or uuid4())
        snapshot.append({
            "question_id": q_id,
            "display_order": i,
            "question_format": QuestionFormat.CONVERSATION.value,
            "wording": it.get("ai_wording") or it.get("question_text") or it.get("text") or "Describe your experience.",
            "competency_name": it.get("competency_name") or it.get("competency") or "Core Competency",
            "options": None,
            "correct_option_id": None,
            "difficulty": it.get("difficulty"),
            "estimated_time_minutes": it.get("estimated_time_minutes", 3),
        })

    for j, it in enumerate(mcq_items):
        q_id = str(it.get("slot_id") or it.get("question_id") or uuid4())
        snapshot.append({
            "question_id": q_id,
            "display_order": len(conv_items) + j,
            "question_format": QuestionFormat.MCQ_SINGLE_ANSWER.value,
            "wording": it.get("ai_wording") or it.get("question_text") or it.get("text") or "",
            "competency_name": it.get("competency_name") or it.get("competency") or "Knowledge Area",
            "options": it.get("options", []),
            "correct_option_id": it.get("correct_option_id", "A"),
            "explanation": it.get("explanation") or it.get("answer_explanation"),
            "difficulty": it.get("difficulty", "INTERMEDIATE"),
            "estimated_time_minutes": it.get("estimated_time_minutes", 2),
        })

    snapshot_hash = _compute_snapshot_hash(snapshot)
    initial_section = PracticeSection.CONVERSATION.value if conv_items else PracticeSection.MCQ.value

    job_title = release.job_version.title if release.job_version else (release.job.title if release.job else "Role")

    new_session = CandidatePracticeSessionRecord(
        session_id=uuid4(),
        organization_id=binding.organization_id,
        binding_id=binding.binding_id,
        candidate_id=binding.candidate_id,
        release_id=release.release_id,
        application_id=release.application_id,
        job_id=release.job_id,
        job_version_id=release.job_version_id,
        job_revision=release.job_revision,
        ai_set_id=release.ai_set_id,
        set_version=release.set_version,
        snapshot_hash=snapshot_hash,
        questions_snapshot=snapshot,
        lifecycle_status=PracticeSessionLifecycle.IN_PROGRESS.value,
        current_section=initial_section,
        current_conv_index=0,
        current_conv_turn_count=0,
        current_mcq_index=0,
        total_conv_count=len(conv_items),
        total_mcq_count=len(mcq_items),
        total_response_count=0,
        model_call_count=0,
        concurrency_version=1,
        started_at=now,
        expires_at=now + timedelta(hours=24),
        retention_class="SIMULATION_CONTENT",
        fallback_active=False,
    )
    db.add(new_session)
    db.flush()

    # 5. Populate initial greeting and first primary question if starting in CONVERSATION
    if initial_section == PracticeSection.CONVERSATION.value and conv_items:
        first_q = conv_items[0]
        first_q_id = UUID(snapshot[0]["question_id"])
        
        greeting_msg = CandidatePracticeMessageRecord(
            message_id=uuid4(),
            session_id=new_session.session_id,
            sequence_number=1,
            role=PracticeMessageRole.INTERVIEWER.value,
            message_kind=PracticeMessageKind.GREETING.value,
            source_question_id=None,
            text=f"Welcome to your practice interview session for the {job_title} role. We will begin with conversational scenario questions followed by practical knowledge checks. Please answer thoroughly in your own words when you are ready.",
            created_at=now,
        )
        db.add(greeting_msg)

        primary_q_msg = CandidatePracticeMessageRecord(
            message_id=uuid4(),
            session_id=new_session.session_id,
            sequence_number=2,
            role=PracticeMessageRole.INTERVIEWER.value,
            message_kind=PracticeMessageKind.PRIMARY_QUESTION.value,
            source_question_id=first_q_id,
            text=snapshot[0]["wording"],
            created_at=now,
        )
        db.add(primary_q_msg)

    db.commit()
    db.refresh(new_session)

    # Re-fetch session with relationships
    stmt_full = (
        select(CandidatePracticeSessionRecord)
        .options(
            selectinload(CandidatePracticeSessionRecord.messages),
            selectinload(CandidatePracticeSessionRecord.job),
            selectinload(CandidatePracticeSessionRecord.job_version),
        )
        .where(CandidatePracticeSessionRecord.session_id == new_session.session_id)
    )
    full_session = db.execute(stmt_full).scalar_one()
    return _map_session_to_dto(full_session)


def get_practice_session_state(
    candidate_user: UserRecord,
    session_id: UUID,
    db: Session,
) -> PracticeSessionDetailResponse:
    """Fetches candidate practice session state."""
    binding = _get_active_binding(candidate_user, db)

    stmt = (
        select(CandidatePracticeSessionRecord)
        .options(
            selectinload(CandidatePracticeSessionRecord.messages),
            selectinload(CandidatePracticeSessionRecord.job),
            selectinload(CandidatePracticeSessionRecord.job_version),
        )
        .where(
            CandidatePracticeSessionRecord.session_id == session_id,
            CandidatePracticeSessionRecord.candidate_id == binding.candidate_id,
        )
    )
    session = db.execute(stmt).scalar_one_or_none()
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "SESSION_NOT_FOUND", "message": "Practice session not found."},
        )

    return _map_session_to_dto(session)


async def submit_conversational_answer(
    candidate_user: UserRecord,
    session_id: UUID,
    payload: PracticeConversationAnswerRequest,
    db: Session,
    custom_endpoint_url: Optional[str] = None,
) -> PracticeSessionDetailResponse:
    """Submits a candidate answer for the active conversational question, evaluating follow-up availability."""
    binding = _get_active_binding(candidate_user, db)
    now = datetime.now(timezone.utc)

    stmt = (
        select(CandidatePracticeSessionRecord)
        .options(
            selectinload(CandidatePracticeSessionRecord.messages),
            selectinload(CandidatePracticeSessionRecord.job),
            selectinload(CandidatePracticeSessionRecord.job_version),
        )
        .where(
            CandidatePracticeSessionRecord.session_id == session_id,
            CandidatePracticeSessionRecord.candidate_id == binding.candidate_id,
        )
        .with_for_update()
    )
    session = db.execute(stmt).scalar_one_or_none()
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "SESSION_NOT_FOUND", "message": "Practice session not found."},
        )

    if session.lifecycle_status != PracticeSessionLifecycle.IN_PROGRESS.value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "SESSION_NOT_ACTIVE", "message": f"Session is already {session.lifecycle_status}."},
        )

    if session.current_section != PracticeSection.CONVERSATION.value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "INVALID_SECTION", "message": "Current section is not conversational."},
        )

    # Validate active conversational question
    snapshot = session.questions_snapshot or []
    conv_questions = [q for q in snapshot if q.get("question_format") == QuestionFormat.CONVERSATION.value]
    if session.current_conv_index >= len(conv_questions):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "CONVERSATION_COMPLETE", "message": "All conversational questions are already completed."},
        )

    active_q = conv_questions[session.current_conv_index]
    if str(payload.question_id) != active_q["question_id"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "QUESTION_MISMATCH", "message": "Answer submitted does not match active question."},
        )

    answer_clean = payload.answer_text.strip()
    if not answer_clean:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "EMPTY_ANSWER", "message": "Answer text cannot be empty or whitespace only."},
        )

    seq_num = len(session.messages) + 1

    # 1. Save candidate answer
    cand_msg = CandidatePracticeMessageRecord(
        message_id=uuid4(),
        session_id=session.session_id,
        sequence_number=seq_num,
        role=PracticeMessageRole.CANDIDATE.value,
        message_kind=PracticeMessageKind.ANSWER.value,
        source_question_id=payload.question_id,
        text=answer_clean,
        created_at=now,
    )
    db.add(cand_msg)
    session.total_response_count += 1

    # 2. State Machine Turn Evaluation
    # Turn 0: Primary question was asked -> Candidate gave primary answer -> Evaluate if follow-up can be asked
    if session.current_conv_turn_count == 0:
        follow_up_available = (session.model_call_count < 5)
        
        fu_req = BoundedPracticeFollowUpRequest(
            source_question_id=active_q["question_id"],
            competency_name=active_q["competency_name"],
            question_wording=active_q["wording"],
            candidate_answer=answer_clean,
            follow_up_available=follow_up_available,
        )

        fu_resp = await request_practice_conversation_follow_up(
            request=fu_req,
            db=db,
            custom_endpoint_url=custom_endpoint_url,
        )

        if fu_resp.safe_fallback_used:
            session.fallback_active = True
            session.fallback_reason = "ADAPTIVE_FOLLOW_UPS_UNAVAILABLE"

        if fu_resp.action == "FOLLOW_UP" and fu_resp.follow_up_question and not fu_resp.safe_fallback_used:
            # Post follow-up question
            session.model_call_count += 1
            session.current_conv_turn_count = 2  # State: waiting for follow-up answer
            interviewer_fu_msg = CandidatePracticeMessageRecord(
                message_id=uuid4(),
                session_id=session.session_id,
                sequence_number=seq_num + 1,
                role=PracticeMessageRole.INTERVIEWER.value,
                message_kind=PracticeMessageKind.FOLLOW_UP.value,
                source_question_id=payload.question_id,
                text=fu_resp.follow_up_question,
                created_at=now,
            )
            db.add(interviewer_fu_msg)
        else:
            # Acknowledge and advance to next conversational question (or MCQ section)
            ack_text = fu_resp.acknowledgement or "Thank you for explaining that."
            interviewer_ack_msg = CandidatePracticeMessageRecord(
                message_id=uuid4(),
                session_id=session.session_id,
                sequence_number=seq_num + 1,
                role=PracticeMessageRole.INTERVIEWER.value,
                message_kind=PracticeMessageKind.ACKNOWLEDGEMENT.value,
                source_question_id=payload.question_id,
                text=ack_text,
                created_at=now,
            )
            db.add(interviewer_ack_msg)

            # Advance
            session.current_conv_index += 1
            session.current_conv_turn_count = 0

            if session.current_conv_index < len(conv_questions):
                next_q = conv_questions[session.current_conv_index]
                next_q_msg = CandidatePracticeMessageRecord(
                    message_id=uuid4(),
                    session_id=session.session_id,
                    sequence_number=seq_num + 2,
                    role=PracticeMessageRole.INTERVIEWER.value,
                    message_kind=PracticeMessageKind.PRIMARY_QUESTION.value,
                    source_question_id=UUID(next_q["question_id"]),
                    text=next_q["wording"],
                    created_at=now,
                )
                db.add(next_q_msg)
            else:
                # All conversational questions finished -> Transition
                mcq_questions = [q for q in snapshot if q.get("question_format") == QuestionFormat.MCQ_SINGLE_ANSWER.value]
                if mcq_questions:
                    session.current_section = PracticeSection.MCQ.value
                    session.current_mcq_index = 0
                    trans_msg = CandidatePracticeMessageRecord(
                        message_id=uuid4(),
                        session_id=session.session_id,
                        sequence_number=seq_num + 2,
                        role=PracticeMessageRole.INTERVIEWER.value,
                        message_kind=PracticeMessageKind.ACKNOWLEDGEMENT.value,
                        source_question_id=None,
                        text="Conversational practice complete. Let's proceed to the multiple-choice questions.",
                        created_at=now,
                    )
                    db.add(trans_msg)
                else:
                    session.current_section = PracticeSection.COMPLETE.value
                    session.lifecycle_status = PracticeSessionLifecycle.COMPLETED.value
                    session.completed_at = now

    elif session.current_conv_turn_count == 2:
        # Candidate just submitted answer to follow-up -> Post static ACK and advance to next question
        ack_msg = CandidatePracticeMessageRecord(
            message_id=uuid4(),
            session_id=session.session_id,
            sequence_number=seq_num + 1,
            role=PracticeMessageRole.INTERVIEWER.value,
            message_kind=PracticeMessageKind.ACKNOWLEDGEMENT.value,
            source_question_id=payload.question_id,
            text="Thank you for providing that additional context.",
            created_at=now,
        )
        db.add(ack_msg)

        session.current_conv_index += 1
        session.current_conv_turn_count = 0

        if session.current_conv_index < len(conv_questions):
            next_q = conv_questions[session.current_conv_index]
            next_q_msg = CandidatePracticeMessageRecord(
                message_id=uuid4(),
                session_id=session.session_id,
                sequence_number=seq_num + 2,
                role=PracticeMessageRole.INTERVIEWER.value,
                message_kind=PracticeMessageKind.PRIMARY_QUESTION.value,
                source_question_id=UUID(next_q["question_id"]),
                text=next_q["wording"],
                created_at=now,
            )
            db.add(next_q_msg)
        else:
            mcq_questions = [q for q in snapshot if q.get("question_format") == QuestionFormat.MCQ_SINGLE_ANSWER.value]
            if mcq_questions:
                session.current_section = PracticeSection.MCQ.value
                session.current_mcq_index = 0
                trans_msg = CandidatePracticeMessageRecord(
                    message_id=uuid4(),
                    session_id=session.session_id,
                    sequence_number=seq_num + 2,
                    role=PracticeMessageRole.INTERVIEWER.value,
                    message_kind=PracticeMessageKind.ACKNOWLEDGEMENT.value,
                    source_question_id=None,
                    text="Conversational practice complete. Let's proceed to the multiple-choice questions.",
                    created_at=now,
                )
                db.add(trans_msg)
            else:
                session.current_section = PracticeSection.COMPLETE.value
                session.lifecycle_status = PracticeSessionLifecycle.COMPLETED.value
                session.completed_at = now

    session.concurrency_version += 1
    session.updated_at = now
    db.commit()

    return _map_session_to_dto(session)


def submit_mcq_answer(
    candidate_user: UserRecord,
    session_id: UUID,
    payload: PracticeMcqAnswerRequest,
    db: Session,
) -> PracticeSessionDetailResponse:
    """Submits a candidate answer for the active MCQ question, evaluating correctness deterministically."""
    binding = _get_active_binding(candidate_user, db)
    now = datetime.now(timezone.utc)

    stmt = (
        select(CandidatePracticeSessionRecord)
        .options(
            selectinload(CandidatePracticeSessionRecord.messages),
            selectinload(CandidatePracticeSessionRecord.job),
            selectinload(CandidatePracticeSessionRecord.job_version),
        )
        .where(
            CandidatePracticeSessionRecord.session_id == session_id,
            CandidatePracticeSessionRecord.candidate_id == binding.candidate_id,
        )
        .with_for_update()
    )
    session = db.execute(stmt).scalar_one_or_none()
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "SESSION_NOT_FOUND", "message": "Practice session not found."},
        )

    if session.lifecycle_status != PracticeSessionLifecycle.IN_PROGRESS.value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "SESSION_NOT_ACTIVE", "message": f"Session is already {session.lifecycle_status}."},
        )

    if session.current_section != PracticeSection.MCQ.value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "INVALID_SECTION", "message": "Current section is not MCQ."},
        )

    snapshot = session.questions_snapshot or []
    mcq_questions = [q for q in snapshot if q.get("question_format") == QuestionFormat.MCQ_SINGLE_ANSWER.value]
    if session.current_mcq_index >= len(mcq_questions):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "MCQ_COMPLETE", "message": "All MCQ questions are already completed."},
        )

    active_mcq = mcq_questions[session.current_mcq_index]
    if str(payload.question_id) != active_mcq["question_id"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "QUESTION_MISMATCH", "message": "Submitted answer does not match active MCQ question."},
        )

    # Validate option exists
    options = active_mcq.get("options", [])
    valid_option_ids = [opt["option_id"] for opt in options]
    if payload.selected_option_id not in valid_option_ids:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "INVALID_OPTION_ID", "message": f"Selected option '{payload.selected_option_id}' is not among valid options {valid_option_ids}."},
        )

    # Check for duplicate answer
    stmt_ans = select(CandidatePracticeMcqAnswerRecord).where(
        CandidatePracticeMcqAnswerRecord.session_id == session.session_id,
        CandidatePracticeMcqAnswerRecord.question_id == payload.question_id,
    )
    existing_ans = db.execute(stmt_ans).scalar_one_or_none()
    if existing_ans:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "ANSWER_ALREADY_SUBMITTED", "message": "An answer has already been submitted for this MCQ."},
        )

    # Deterministic correctness check against server snapshot (NEVER use LLM)
    correct_option_id = active_mcq.get("correct_option_id", "A")
    is_correct = (payload.selected_option_id.strip().upper() == correct_option_id.strip().upper())

    mcq_ans_rec = CandidatePracticeMcqAnswerRecord(
        answer_id=uuid4(),
        session_id=session.session_id,
        question_id=payload.question_id,
        selected_option_id=payload.selected_option_id,
        is_correct=is_correct,
        submitted_at=now,
    )
    db.add(mcq_ans_rec)

    # Advance MCQ position
    session.current_mcq_index += 1
    session.total_response_count += 1

    if session.current_mcq_index >= len(mcq_questions):
        session.current_section = PracticeSection.COMPLETE.value
        session.lifecycle_status = PracticeSessionLifecycle.COMPLETED.value
        session.completed_at = now

    session.concurrency_version += 1
    session.updated_at = now
    db.commit()

    return _map_session_to_dto(session)


def abandon_practice_session(
    candidate_user: UserRecord,
    session_id: UUID,
    db: Session,
) -> PracticeSessionAbandonResponse:
    """Abandons an active practice session."""
    binding = _get_active_binding(candidate_user, db)
    now = datetime.now(timezone.utc)

    stmt = select(CandidatePracticeSessionRecord).where(
        CandidatePracticeSessionRecord.session_id == session_id,
        CandidatePracticeSessionRecord.candidate_id == binding.candidate_id,
    )
    session = db.execute(stmt).scalar_one_or_none()
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "SESSION_NOT_FOUND", "message": "Practice session not found."},
        )

    if session.lifecycle_status != PracticeSessionLifecycle.IN_PROGRESS.value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "SESSION_NOT_ACTIVE", "message": f"Session is already {session.lifecycle_status}."},
        )

    session.lifecycle_status = PracticeSessionLifecycle.ABANDONED.value
    session.abandoned_at = now
    session.updated_at = now
    db.commit()

    return PracticeSessionAbandonResponse(
        session_id=session.session_id,
        lifecycle_status=PracticeSessionLifecycle.ABANDONED.value,
        safe_message="Practice interview session ended.",
    )
