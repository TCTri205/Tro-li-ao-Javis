from __future__ import annotations

import asyncio
import sys
from datetime import date
from typing import Any

from javis_text2sql.config import Settings
from javis_text2sql.db.admin import create_pool
from javis_text2sql.llm import get_llm_client
from javis_text2sql.query.pipeline import text2sql_pipeline, map_entities, retrieve_few_shots
from javis_text2sql.routing.router import route_question

# Beautiful ANSI Colors
C_GREEN = "\033[92m"
C_YELLOW = "\033[93m"
C_RED = "\033[91m"
C_CYAN = "\033[96m"
C_MAGENTA = "\033[95m"
C_BOLD = "\033[1m"
C_RESET = "\033[0m"

def print_header(title: str):
    print(f"\n{C_BOLD}{C_CYAN}{'=' * 60}{C_RESET}")
    print(f"{C_BOLD}{C_CYAN}  {title}{C_RESET}")
    print(f"{C_BOLD}{C_CYAN}{'=' * 60}{C_RESET}")

def print_sub_header(title: str):
    print(f"\n{C_BOLD}{C_MAGENTA}--- {title} ---{C_RESET}")

def format_table(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "No data returned."
    
    headers = list(rows[0].keys())
    # Determine max width for each column
    col_widths = {h: len(str(h)) for h in headers}
    for row in rows:
        for h in headers:
            col_widths[h] = max(col_widths[h], len(str(row.get(h, ""))))
            
    # Build the header line
    header_line = " | ".join(f"{h:<{col_widths[h]}}" for h in headers)
    separator = "-+-".join("-" * col_widths[h] for h in headers)
    
    lines = [header_line, separator]
    for row in rows:
        lines.append(" | ".join(f"{str(row.get(h, '')):<{col_widths[h]}}" for h in headers))
        
    return "\n".join(lines)

import logging
# Suppress diagnostic warnings/logs from library outputs to keep client console pristine
logging.basicConfig(level=logging.ERROR)
logger = logging.getLogger("javis_text2sql")
logger.setLevel(logging.ERROR)

async def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        
    settings = Settings.from_env()
    
    print_header("JAVIS TEXT-TO-SQL INTERACTIVE CLIENT")
    print(f"{C_BOLD}Settings Loaded:{C_RESET}")
    print(f" - DB URL:      {settings.database_url}")
    print(f" - LLM Provider:{C_GREEN} {settings.llm_provider.upper()} {C_RESET}")
    print(f" - LLM Model:   {C_GREEN} {settings.groq_model} {C_RESET}")
    print(f" - Redis Cache: {C_YELLOW} {settings.redis_url or 'Disabled'} {C_RESET}")
    
    try:
        llm_client = get_llm_client(settings)
    except Exception as e:
        print(f"\n{C_RED}{C_BOLD}[ERROR] Failed to initialize LLM Client: {e}{C_RESET}")
        print("Please check your GROQ_API_KEYS inside the .env file.")
        return

    try:
        pool = await create_pool(settings.database_url)
    except Exception as e:
        print(f"\n{C_RED}{C_BOLD}[ERROR] Failed to connect to database: {e}{C_RESET}")
        print("Please make sure your Postgres Docker container is running by typing: docker compose up -d")
        return

    # Check connection
    try:
        async with pool.acquire() as conn:
            meetings_count = await conn.fetchval("SELECT COUNT(*) FROM meetings")
            turns_count = await conn.fetchval("SELECT COUNT(*) FROM turns")
            print(f" - Status:      {C_GREEN}Connected successfully! ({meetings_count} meetings, {turns_count} turns in DB){C_RESET}")
    except Exception as e:
        print(f"\n{C_RED}{C_BOLD}[ERROR] Database connection failed check: {e}{C_RESET}")
        await pool.close()
        return

    reference_date = date(2026, 5, 26)  # Standard project evaluation reference date
    print(f" - Reference Date: {C_CYAN}{reference_date.isoformat()}{C_RESET}")
    
    print(f"\n{C_BOLD}Ready for your questions! Type 'exit' or 'quit' to stop.{C_RESET}")
    
    while True:
        try:
            print(f"\n{C_BOLD}{C_YELLOW}Question > {C_RESET}", end="")
            question = input().strip()
            if not question:
                continue
            if question.lower() in ("exit", "quit", "q"):
                print(f"\n{C_CYAN}Goodbye!{C_RESET}")
                break
                
            # 1. Routing Heuristic Decision
            decision = route_question(question)
            print_sub_header("1. ROUTING DECISION")
            route_color = C_GREEN if decision.route == "sql" else (C_YELLOW if decision.route == "hybrid" else C_RED)
            print(f"Selected Route: {route_color}{decision.route.upper()}{C_RESET} (Confidence: {decision.confidence:.2f})")
            print(f"SQL Intent:     {C_CYAN}{decision.sql_intent or 'None'}{C_RESET}")
            print(f"Needs Numeric:  {C_CYAN}{decision.requires_numeric}{C_RESET}")
            
            if decision.route != "sql":
                print(f"{C_YELLOW}[Note] This query is classified as {decision.route.upper()}. Running Text-to-SQL anyway for demo purposes!{C_RESET}")

            # 2. Entity Mapping & Few shot retrieval details
            async with pool.acquire() as conn:
                entities = await map_entities(question, conn)
                few_shots = await retrieve_few_shots(question, conn, limit=3)
                
            print_sub_header("2. KNOWLEDGE GRAPH & FEW-SHOTS ENRICHMENT")
            if entities:
                print(f"{C_BOLD}Fuzzy Entity Matches (Trigram + RapidFuzz):{C_RESET}")
                for k, v in entities.items():
                    print(f"  - '{k}' mapped to canonical name {C_GREEN}'{v}'{C_RESET}")
            else:
                print("No entity mappings detected.")
                
            print(f"\n{C_BOLD}Dynamic Few-Shots Retrieved (pgvector Cosine Similarity):{C_RESET}")
            for idx, (q_shot, sql_shot) in enumerate(few_shots, 1):
                print(f"  {idx}. Q: '{q_shot}'")
                print(f"     SQL: {C_GREEN}{sql_shot}{C_RESET}")

            # 3. Pipeline Run
            print_sub_header("3. LLM GENERATION & EXECUTION PIPELINE")
            print(f"Generating SQL and querying...")
            
            result = await text2sql_pipeline(
                question=question,
                db_pool=pool,
                llm_client=llm_client,
                reference_date=reference_date,
                redis_url=settings.redis_url
            )
            
            if result.success:
                print(f"\n{C_GREEN}{C_BOLD}[✓] Success!{C_RESET}")
                if result.retry_used:
                    print(f"{C_YELLOW}[Info] 1-Turn Refiner executed! The first attempt failed, but the refiner successfully auto-corrected the SQL syntax.{C_RESET}")
                
                print(f"\n{C_BOLD}Generated SQL Query:{C_RESET}")
                print(f"{C_CYAN}{result.sql}{C_RESET}")
                
                print(f"\n{C_BOLD}Execution Results:{C_RESET}")
                if result.data:
                    print(format_table(result.data))
                else:
                    print("Empty result set.")
            else:
                print(f"\n{C_RED}{C_BOLD}[✗] Failed!{C_RESET}")
                print(f"{C_BOLD}Generated SQL (Failed):{C_RESET}")
                print(f"{C_RED}{result.sql}{C_RESET}")
                print(f"\n{C_BOLD}Error Message:{C_RESET}")
                print(f"{C_RED}{result.error}{C_RESET}")

        except (KeyboardInterrupt, EOFError):
            print(f"\n\n{C_CYAN}Session interrupted. Goodbye!{C_RESET}")
            break
        except Exception as e:
            print(f"\n{C_RED}[ERROR] An unexpected error occurred: {e}{C_RESET}")
            
    await pool.close()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
