from __future__ import annotations

import asyncio
import json
import logging
from datetime import date
from typing import Any

from javis_text2sql.llm.client import LLMClient
from javis_text2sql.llm.embeddings import EmbeddingClient, get_embedding_client

from .chunker import chunk_turns_into_passages, passage_content, split_turns
from .models import MeetingMeta, PassageEnrichmentSchema, Turn, empty_enrichment


logger = logging.getLogger(__name__)


def _jsonable(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)


async def enrich_passage(
    passage_text: str,
    passage_index: int,
    meeting_date: date,
    llm_client: LLMClient,
    semaphore: asyncio.Semaphore | None = None,
) -> tuple[dict[str, Any], str]:
    system_prompt = f"You are an expert NLP extractor. Reference date: {meeting_date.isoformat()}."
    gate = semaphore or asyncio.Semaphore(10)

    for attempt in range(3):
        try:
            async with gate:
                result_obj = await llm_client.structured_output(
                    system=system_prompt,
                    user=passage_text,
                    schema=PassageEnrichmentSchema,
                )
            return result_obj.model_dump(mode="json"), "success"
        except Exception as exc:
            if attempt == 2:
                logger.error("Passage %s enrichment failed: %s", passage_index, exc)
                return empty_enrichment().model_dump(mode="json"), "llm_failed"
            await asyncio.sleep(2**attempt)

    return empty_enrichment().model_dump(mode="json"), "llm_failed"


async def load_meeting(
    raw_transcript: str,
    meeting_meta: MeetingMeta,
    db_pool: Any,
    llm_client: LLMClient,
    turns: list[Turn] | None = None,
    max_turns: int = 10,
    embedding_client: EmbeddingClient | None = None,
) -> str:
    parsed_turns = turns or split_turns(raw_transcript, reference_date=meeting_meta.meeting_date)
    passage_groups = chunk_turns_into_passages(parsed_turns, max_turns=max_turns)
    
    # Generate embeddings for all turns
    embed_client = embedding_client or get_embedding_client()
    turn_contents = [t.content for t in parsed_turns]
    embeddings = await embed_client.embed_texts(turn_contents)
    
    turn_to_embedding = {}
    for turn, emb in zip(parsed_turns, embeddings):
        turn_to_embedding[turn] = emb

    semaphore = asyncio.Semaphore(10)
    enrichment_results = await asyncio.gather(
        *[
            enrich_passage(
                passage_text=passage_content(group),
                passage_index=index,
                meeting_date=meeting_meta.meeting_date,
                llm_client=llm_client,
                semaphore=semaphore,
            )
            for index, group in enumerate(passage_groups)
        ]
    )

    async with db_pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute("SELECT set_config('app.current_user_id', $1, true)", str(meeting_meta.user_id))
            meeting_id = await conn.fetchval(
                """
                INSERT INTO meetings
                    (user_id, title, meeting_date, speaker_count, duration_seconds, summary, topics, source_language)
                VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb, $8)
                RETURNING id
                """,
                meeting_meta.user_id,
                meeting_meta.title,
                meeting_meta.meeting_date,
                meeting_meta.speaker_count,
                meeting_meta.duration_seconds,
                meeting_meta.summary,
                _jsonable([]),
                meeting_meta.source_language,
            )

            for idx, (group, (schema_data, enrichment_status)) in enumerate(zip(passage_groups, enrichment_results)):
                passage_id = await conn.fetchval(
                    """
                    INSERT INTO passages
                        (meeting_id, passage_index, content, topics, entities, keywords,
                         turn_types, has_action_item, action_item_text, has_question, question_text,
                         amounts, dates_mentioned, sentiment, importance_score, enrichment_status)
                    VALUES
                        ($1, $2, $3, $4::jsonb, $5::jsonb, $6::jsonb,
                         $7, $8, $9, $10, $11, $12::jsonb, $13::jsonb, $14, $15, $16)
                    RETURNING id
                    """,
                    meeting_id,
                    idx,
                    passage_content(group),
                    _jsonable(schema_data["topics"]),
                    _jsonable(schema_data["entities"]),
                    _jsonable(schema_data["keywords"]),
                    schema_data["turn_types"],
                    schema_data["has_action_item"],
                    schema_data["action_item_text"],
                    schema_data["has_question"],
                    schema_data["question_text"],
                    _jsonable(schema_data["amounts"]),
                    _jsonable(schema_data["dates_mentioned"]),
                    schema_data["sentiment"],
                    schema_data["importance_score"],
                    enrichment_status,
                )

                commitments = schema_data.get("commitments") or []
                if commitments:
                    await conn.executemany(
                        """
                        INSERT INTO commitments
                            (passage_id, meeting_id, person, action, deadline, deadline_date, status)
                        VALUES ($1, $2, $3, $4, $5, $6, $7)
                        """,
                        [
                            (
                                passage_id,
                                meeting_id,
                                item["person"],
                                item["action"],
                                item.get("deadline"),
                                item.get("deadline_date"),
                                item.get("status", "pending"),
                            )
                            for item in commitments
                        ],
                    )

                await conn.executemany(
                    """
                    INSERT INTO turns
                        (passage_id, meeting_id, turn_index, speaker, content, timestamp, embedding)
                    VALUES ($1, $2, $3, $4, $5, $6, $7)
                    """,
                    [
                        (
                            passage_id,
                            meeting_id,
                            turn.turn_index,
                            turn.speaker,
                            turn.content,
                            turn.timestamp,
                            str(turn_to_embedding.get(turn)) if turn_to_embedding.get(turn) is not None else None,
                        )
                        for turn in group
                    ],
                )

    return str(meeting_id)
