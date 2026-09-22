"""API endpoints for Recruiter Practice Releases and Candidate Practice Discovery in Phase 3F.2."""
import uuid
from typing import Any, Dict, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.auth import (
    AuthenticatedContext,
    CandidateAuthenticatedContext,
    require_candidate,
    require_recruiter,
    verify_candidate_csrf_and_origin,
)
from app.database import get_db
from app.schemas.mcq_contract import (
    CandidatePracticeDiscoveryResponse,
    StrictSchema,
)
from app.schemas.practice_session_contract import (
    PracticeConversationAnswerRequest,
    PracticeMcqAnswerRequest,
    PracticeSessionAbandonResponse,
    PracticeSessionDetailResponse,
    PracticeSessionStartRequest,
)
from app.services.candidate_practice_service import (
    get_candidate_practice_discovery,
    list_candidate_practice_releases_for_recruiter,
    release_practice_to_candidate,
    revoke_candidate_practice_release,
)
from app.services.practice_session_service import (
    abandon_practice_session,
    get_practice_session_state,
    start_or_resume_practice_session,
    submit_conversational_answer,
    submit_mcq_answer,
)

router = APIRouter(
    prefix="/api/v1",
    tags=["candidate-practice"],
)


class CreatePracticeReleaseRequest(StrictSchema):
    candidate_id: UUID
    job_id: UUID
    ai_set_id: Optional[UUID] = None


@router.post(
    "/recruiter/practice-releases",
    status_code=status.HTTP_200_OK,
    summary="Release Practice Interview to Candidate",
)
async def create_practice_release_endpoint(
    payload: CreatePracticeReleaseRequest,
    auth_ctx: AuthenticatedContext = Depends(require_recruiter),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    return release_practice_to_candidate(
        actor=auth_ctx.user,
        candidate_id=payload.candidate_id,
        job_id=payload.job_id,
        ai_set_id=payload.ai_set_id,
        db=db,
    )


@router.get(
    "/recruiter/practice-releases/{candidate_id}",
    status_code=status.HTTP_200_OK,
    summary="List Practice Releases for Candidate (Recruiter)",
)
async def list_practice_releases_endpoint(
    candidate_id: UUID,
    auth_ctx: AuthenticatedContext = Depends(require_recruiter),
    db: Session = Depends(get_db),
) -> List[Dict[str, Any]]:
    return list_candidate_practice_releases_for_recruiter(
        actor=auth_ctx.user,
        candidate_id=candidate_id,
        db=db,
    )


@router.post(
    "/recruiter/practice-releases/{release_id}/revoke",
    status_code=status.HTTP_200_OK,
    summary="Revoke Practice Release",
)
async def revoke_practice_release_endpoint(
    release_id: UUID,
    auth_ctx: AuthenticatedContext = Depends(require_recruiter),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    return revoke_candidate_practice_release(
        actor=auth_ctx.user,
        release_id=release_id,
        db=db,
    )


@router.get(
    "/candidate/practice/jobs",
    response_model=CandidatePracticeDiscoveryResponse,
    status_code=status.HTTP_200_OK,
    summary="Candidate Practice Discovery",
    description="Returns active practice interview jobs released to the authenticated candidate.",
)
async def get_candidate_practice_jobs_endpoint(
    auth_ctx: CandidateAuthenticatedContext = Depends(require_candidate),
    db: Session = Depends(get_db),
) -> CandidatePracticeDiscoveryResponse:
    return get_candidate_practice_discovery(
        candidate_user=auth_ctx.user,
        db=db,
    )


# --- Phase 3F.3: Candidate Practice Execution Endpoints ---


@router.post(
    "/candidate/practice-sessions/start",
    response_model=PracticeSessionDetailResponse,
    status_code=status.HTTP_200_OK,
    summary="Start or Resume Practice Session",
    description="Initializes or resumes an active practice session with immutable question snapshots.",
)
async def start_practice_session_endpoint(
    payload: PracticeSessionStartRequest,
    cand_ctx: CandidateAuthenticatedContext = Depends(verify_candidate_csrf_and_origin),
    db: Session = Depends(get_db),
) -> PracticeSessionDetailResponse:
    return start_or_resume_practice_session(
        candidate_user=cand_ctx.user,
        release_id=payload.release_id,
        db=db,
    )


@router.get(
    "/candidate/practice-sessions/{session_id}",
    response_model=PracticeSessionDetailResponse,
    status_code=status.HTTP_200_OK,
    summary="Get Practice Session State",
    description="Retrieves current session state, messages, and active question.",
)
async def get_practice_session_endpoint(
    session_id: UUID,
    cand_ctx: CandidateAuthenticatedContext = Depends(require_candidate),
    db: Session = Depends(get_db),
) -> PracticeSessionDetailResponse:
    return get_practice_session_state(
        candidate_user=cand_ctx.user,
        session_id=session_id,
        db=db,
    )


@router.post(
    "/candidate/practice-sessions/{session_id}/answer-conversation",
    response_model=PracticeSessionDetailResponse,
    status_code=status.HTTP_200_OK,
    summary="Submit Conversational Answer",
    description="Submits a candidate conversational answer and triggers bounded AI follow-up or advances to next question.",
)
async def answer_conversation_endpoint(
    session_id: UUID,
    payload: PracticeConversationAnswerRequest,
    cand_ctx: CandidateAuthenticatedContext = Depends(verify_candidate_csrf_and_origin),
    db: Session = Depends(get_db),
) -> PracticeSessionDetailResponse:
    return await submit_conversational_answer(
        candidate_user=cand_ctx.user,
        session_id=session_id,
        payload=payload,
        db=db,
    )


@router.post(
    "/candidate/practice-sessions/{session_id}/answer-mcq",
    response_model=PracticeSessionDetailResponse,
    status_code=status.HTTP_200_OK,
    summary="Submit MCQ Answer",
    description="Records deterministic candidate MCQ answer and advances to next MCQ or completes practice.",
)
async def answer_mcq_endpoint(
    session_id: UUID,
    payload: PracticeMcqAnswerRequest,
    cand_ctx: CandidateAuthenticatedContext = Depends(verify_candidate_csrf_and_origin),
    db: Session = Depends(get_db),
) -> PracticeSessionDetailResponse:
    return submit_mcq_answer(
        candidate_user=cand_ctx.user,
        session_id=session_id,
        payload=payload,
        db=db,
    )


@router.post(
    "/candidate/practice-sessions/{session_id}/abandon",
    response_model=PracticeSessionAbandonResponse,
    status_code=status.HTTP_200_OK,
    summary="Abandon Practice Session",
    description="Marks an in-progress practice session as abandoned.",
)
async def abandon_practice_session_endpoint(
    session_id: UUID,
    cand_ctx: CandidateAuthenticatedContext = Depends(verify_candidate_csrf_and_origin),
    db: Session = Depends(get_db),
) -> PracticeSessionAbandonResponse:
    return abandon_practice_session(
        candidate_user=cand_ctx.user,
        session_id=session_id,
        db=db,
    )
