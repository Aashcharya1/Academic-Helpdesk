from typing import Literal, Any
from pydantic import BaseModel, Field

class Context(BaseModel):
    dataset: Literal['real', 'demo'] = 'real'
    term: str = 'AY 2026-27, Semester-I'
    program: str = ''
    cohort: str = '2023'
    course: str = ''
    section: str = ''

class Evidence(BaseModel):
    id: str
    doc_id: str
    title: str
    locator: str
    text: str
    version: str
    source_url: str = ''
    source_path: str = ''
    retrieval_score: float | None = None

class ToolResult(BaseModel):
    status: Literal['ok','not_found','ambiguous','incomplete','error']
    data: Any = None
    evidence: list[Evidence] = Field(default_factory=list)
    error_code: str = ''

class Response(BaseModel):
    request_id: str
    status: Literal['answered','draft','needs_clarification','out_of_scope','insufficient_evidence','error']
    answer: str
    citations: list[Evidence] = Field(default_factory=list)
    draft: dict | None = None
    clarification_fields: list[str] = Field(default_factory=list)
    trace_id: str
    metrics: dict = Field(default_factory=dict)
