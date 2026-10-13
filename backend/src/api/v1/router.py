"""
API v1 — Router aggregator. All v1 endpoints are registered here.
"""

from fastapi import APIRouter, Depends
from src.api.deps import get_current_user_id
from src.api.v1 import search, threads, spaces, collections, discover, auth, users, report, pharma, interpolation, personal
from src.api.v1 import attachments, personalization

api_router = APIRouter()

api_router.include_router(search.router, prefix="/search", tags=["Search"])
api_router.include_router(report.router, prefix="/report", tags=["Report"])
api_router.include_router(threads.router, prefix="/threads", tags=["Threads"], dependencies=[Depends(get_current_user_id)])
api_router.include_router(spaces.router, prefix="/spaces", tags=["Spaces"])
api_router.include_router(collections.router, prefix="/collections", tags=["Collections"])
api_router.include_router(discover.router, prefix="/discover", tags=["Discover"], dependencies=[Depends(get_current_user_id)])
api_router.include_router(pharma.router, prefix="/pharma", tags=["Pharma updates"], dependencies=[Depends(get_current_user_id)])
api_router.include_router(interpolation.router, prefix="/interpolation", tags=["Yearly-to-monthly interpolation"], dependencies=[Depends(get_current_user_id)])
api_router.include_router(auth.router, prefix="/auth", tags=["Auth"])
api_router.include_router(users.router, prefix="/users", tags=["Users"])
api_router.include_router(personal.router, prefix="/personal", tags=["Personal cloud storage"])
api_router.include_router(attachments.router, prefix="/attachments", tags=["Chat attachments"])
api_router.include_router(personalization.router, prefix="/me", tags=["Personalization and memory"])
