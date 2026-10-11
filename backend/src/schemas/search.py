"""Pydantic schemas for search requests and responses."""
from pydantic import BaseModel
from typing import List, Optional


class SearchRequest(BaseModel):
    query: str
    focus_mode: str = "all"
    model: str = "gpt-4o"


class SourceResponse(BaseModel):
    url: str
    title: str
    domain: str
    favicon_url: Optional[str] = None
    snippet: Optional[str] = None
    citation_index: int


class SearchResponse(BaseModel):
    answer: str
    sources: List[SourceResponse]
    related_questions: List[str]
    model: str
