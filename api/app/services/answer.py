"""Turns a question into an AskResponse. This is where the query pipeline lives.

The version below is the bare minimum that works with the stubs: retrieve,
generate, return. Section 3.2 lists eight steps; this file does two of them.
"""

from __future__ import annotations

import logging

from ..config import Settings
from ..logjson import request_id_var
from ..providers.llm.base import LLMProvider
from ..retrieval.base import Retriever
from ..schemas import AskResponse, RetrievedRef

log = logging.getLogger("rahbar.answer")


from .semantic_cache import get_semantic_cache


def answer_question(
    question: str, retriever: Retriever, provider: LLMProvider, settings: Settings
) -> AskResponse:
    cache = get_semantic_cache(settings)

    # 1. Check semantic cache
    cached_response = cache.lookup(question)
    if cached_response is not None:
        return cached_response

    # 2. Retrieve passages
    raw_passages = retriever.retrieve(question, k=settings.top_k)

    # 3. Apply relevance floor filter
    passages = [p for p in raw_passages if p.score >= settings.relevance_floor]

    # 4. Generate answer from context
    answer = provider.generate(question, passages)

    # 5. Citation verification: ensure cited sources match retrieved passages
    valid_retrieved_pairs = {(p.source, p.section) for p in passages}
    verified_citations = [
        c for c in answer.citations if (c.source, c.section) in valid_retrieved_pairs
    ]

    log.info(
        "answered",
        extra={
            "retriever": retriever.name,
            "provider": provider.name,
            "top_k": settings.top_k,
            "chunk_ids": [p.chunk_id for p in raw_passages],
            "scores": [round(p.score, 4) for p in raw_passages],
            "answered_from_context": answer.answered_from_context,
            "relevance_floor": settings.relevance_floor,
        },
    )

    response = AskResponse(
        request_id=request_id_var.get(),
        answer=answer.answer,
        citations=verified_citations,
        answered_from_context=answer.answered_from_context,
        confidence=answer.confidence,
        retrieved=[
            RetrievedRef(
                chunk_id=p.chunk_id, source=p.source, section=p.section, page=p.page, score=p.score
            )
            for p in raw_passages
        ],
        provider=provider.name,
    )

    # 6. Store in cache if eligible
    cache.store(question, response)

    return response
