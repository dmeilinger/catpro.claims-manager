"""API route handlers for /api/v1/claims and /api/v1/health."""

from fastapi import APIRouter

router = APIRouter()


@router.get("/claims")
def list_claims():
    """Paginated list + inline stats. Implemented in Phase 3."""
    return {"message": "stub"}


@router.get("/claims/{claim_id:int}")
def get_claim(claim_id: int):
    """Full claim detail with joined data. Implemented in Phase 3."""
    return {"message": "stub"}


@router.get("/health")
def health_check():
    """System health + poller status. Implemented in Phase 3."""
    return {"status": "ok"}
