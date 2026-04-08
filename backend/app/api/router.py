from fastapi import APIRouter

from app.api import admin, analyze, articles, export, notes, sources, topics

router = APIRouter()

router.include_router(sources.router,   prefix="/sources",  tags=["sources"])
router.include_router(articles.router,  prefix="/articles", tags=["articles"])
router.include_router(topics.router,    prefix="/topics",   tags=["topics"])
router.include_router(analyze.router,                       tags=["analyze"])
router.include_router(notes.router,     prefix="/notes",    tags=["notes"])
router.include_router(admin.router,     prefix="/admin",    tags=["admin"])
router.include_router(export.router,    prefix="/export",   tags=["export"])
