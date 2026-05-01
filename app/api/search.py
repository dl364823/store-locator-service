import logging

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.db.base import get_db
from app.middleware.rate_limit import limiter
from app.schemas.search import SearchRequest, SearchResponse
from app.services.search import execute_search

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Search"])


@router.post(
    "/stores/search",
    response_model=SearchResponse,
    summary="Search for stores",
    description=(
        "Search stores by coordinates, address, or postal code. "
        "Returns active stores within the specified radius, sorted by distance."
    ),
)
@limiter.limit("100/hour")
@limiter.limit("10/minute")
def search_stores(
    request: Request,  # required first arg for slowapi rate limiting
    body: SearchRequest,
    db: Session = Depends(get_db),
) -> SearchResponse:
    logger.info(
        "Search request from %s: mode=%s radius=%.1f",
        request.client.host if request.client else "unknown",
        "coords" if body.latitude is not None else ("address" if body.address else "postal"),
        body.radius_miles,
    )
    return execute_search(db, body)
