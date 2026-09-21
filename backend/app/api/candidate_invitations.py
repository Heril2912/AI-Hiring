import logging
import uuid
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.auth import AuthenticatedContext, require_recruiter
from app.config import Settings, get_settings
from app.database import get_db
from app.schemas.candidate_access import (
    CandidateInvitationSummary,
    CreateCandidateInvitationRequest,
    CreateCandidateInvitationResponse,
)
from app.services.candidate_access_service import (
    create_candidate_invitation,
    list_candidate_invitations_summary,
    revoke_candidate_invitation,
)

logger = logging.getLogger("ai_hiring.api.candidate_invitations")

router = APIRouter(
    prefix="/api/v1/recruiter/candidate-invitations",
    tags=["candidate_invitations"],
    dependencies=[Depends(require_recruiter)],
)


@router.post(
    "",
    response_model=CreateCandidateInvitationResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create Single-Use Candidate Invitation",
)
async def create_invitation(
    req: CreateCandidateInvitationRequest,
    auth_ctx: AuthenticatedContext = Depends(require_recruiter),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> CreateCandidateInvitationResponse:
    invitation, raw_token, activation_url = create_candidate_invitation(
        db=db,
        recruiter_user=auth_ctx.user,
        req=req,
        settings=settings,
    )
    return CreateCandidateInvitationResponse(
        invitation_id=invitation.invitation_id,
        candidate_id=invitation.candidate_id,
        organization_id=invitation.organization_id,
        raw_token=raw_token,
        activation_url=activation_url,
        expires_at=invitation.expires_at,
        created_at=invitation.created_at,
    )


@router.get(
    "/{candidate_id}",
    response_model=List[CandidateInvitationSummary],
    status_code=status.HTTP_200_OK,
    summary="List Safe Invitation History for Candidate",
)
async def get_candidate_invitations(
    candidate_id: uuid.UUID,
    auth_ctx: AuthenticatedContext = Depends(require_recruiter),
    db: Session = Depends(get_db),
) -> List[CandidateInvitationSummary]:
    return list_candidate_invitations_summary(db=db, candidate_id=candidate_id)


@router.post(
    "/{invitation_id}/revoke",
    response_model=CandidateInvitationSummary,
    status_code=status.HTTP_200_OK,
    summary="Revoke Unused Candidate Invitation",
)
async def revoke_invitation(
    invitation_id: uuid.UUID,
    auth_ctx: AuthenticatedContext = Depends(require_recruiter),
    db: Session = Depends(get_db),
) -> CandidateInvitationSummary:
    inv = revoke_candidate_invitation(
        db=db,
        recruiter_user=auth_ctx.user,
        invitation_id=invitation_id,
    )
    return CandidateInvitationSummary(
        invitation_id=inv.invitation_id,
        candidate_id=inv.candidate_id,
        organization_id=inv.organization_id,
        purpose=inv.purpose,
        status="REVOKED",
        expires_at=inv.expires_at,
        consumed_at=inv.consumed_at,
        revoked_at=inv.revoked_at,
        created_by_user_id=inv.created_by_user_id,
        created_at=inv.created_at,
    )
