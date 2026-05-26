from __future__ import annotations

import csv
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_migration_defines_required_tables_views_and_indexes() -> None:
    sql = (ROOT / "migrations" / "001_init.sql").read_text(encoding="utf-8")
    for table in ["meetings", "passages", "turns", "entity_aliases", "commitments"]:
        assert f"CREATE TABLE IF NOT EXISTS {table}" in sql
    for view in [
        "v_topics",
        "v_commitments",
        "v_amounts",
        "v_action_items",
        "v_open_questions",
        "v_statements",
        "v_dates",
        "v_speaker_turns",
    ]:
        assert f"CREATE OR REPLACE VIEW {view}" in sql
    for index in [
        "idx_passages_topics",
        "idx_passages_entities",
        "idx_passages_amounts",
        "idx_passages_turn_types",
        "idx_entity_aliases_trgm",
    ]:
        assert index in sql


def test_seed_aliases_cover_companies_people_and_products_without_duplicate_key() -> None:
    rows = list(csv.DictReader((ROOT / "seeds" / "entity_aliases.csv").read_text(encoding="utf-8").splitlines()))
    keys = {(row["alias"], row["language"]) for row in rows}
    assert len(keys) == len(rows)
    canonical_names = {row["canonical_name"] for row in rows}
    for expected in ["VJ Technologies", "AJ Technologies", "ONE Financial Service", "Yoshio Yamashita"]:
        assert expected in canonical_names
    entity_types = {row["entity_type"] for row in rows}
    assert {"organization", "person", "product"}.issubset(entity_types)
