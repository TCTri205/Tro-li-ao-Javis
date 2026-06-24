import asyncio
import os
import sys
import asyncpg
from dotenv import load_dotenv

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from hcacis.llm_client import LLMClient
from hcacis.orchestrator import HCACIS

async def main():
    env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "numeric_sql_tool_v2", ".env")
    if os.path.exists(env_path):
        load_dotenv(env_path)
    else:
        load_dotenv()

    # Database
    db_url = os.environ.get("NUMERIC_SQL_DATABASE_URL", "postgresql://app_user:app_password@localhost:54331/app_db")
    print(f"Connecting to database at: {db_url}")
    
    try:
        db_pool = await asyncpg.create_pool(db_url)
    except Exception as e:
        print(f"Failed to connect to DB: {e}")
        return

    # LLM Initialization based on .env
    det_provider = os.environ.get("DETECTOR_PROVIDER", "gemini")
    det_model = os.environ.get("DETECTOR_MODEL", "gemini-2.5-flash")
    
    gen_provider = os.environ.get("GENERATOR_PROVIDER", "ollama")
    gen_model = os.environ.get("GENERATOR_MODEL", "qwen2.5:7b")
    ollama_url = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")

    print(f"Initializing HCACIS System...")
    print(f" -> Detector LLM : {det_provider.upper()} ({det_model})")
    print(f" -> Generator LLM: {gen_provider.upper()} ({gen_model})")
    
    detector_llm = LLMClient(provider=det_provider, model_name=det_model)
    generator_llm = LLMClient(provider=gen_provider, model_name=gen_model, base_url=ollama_url)
    
    hcacis = HCACIS(detector_llm, generator_llm, db_pool)
    
    session_id = "test_multi_llm_001"
    
    print("\n================ HCACIS MULTI-ENGINE & MULTI-LLM TEST ================")
    
    import argparse
    parser = argparse.ArgumentParser(description="Run HCACIS tests with a scenario file.")
    parser.add_argument("--scenario", "-s", type=str, default=None, help="Path to the scenario text file")
    args = parser.parse_args()

    queries = []
    if args.scenario and os.path.exists(args.scenario):
        print(f"\nLoading scenario from: {args.scenario}")
        with open(args.scenario, 'r', encoding='utf-8') as f:
            queries = [line.strip() for line in f if line.strip() and not line.strip().startswith("#")]
    else:
        print("\nNo valid scenario file provided. Running default Scenario 1...")
        default_scenario = os.path.join(os.path.dirname(os.path.abspath(__file__)), "scenarios", "scenario_1.txt")
        if os.path.exists(default_scenario):
            with open(default_scenario, 'r', encoding='utf-8') as f:
                queries = [line.strip() for line in f if line.strip() and not line.strip().startswith("#")]
        else:
            # Fallback to hardcoded queries
            queries = [
                "2026年5月15日の会議では、主にどんな内容が話し合われましたか？",
                "その会議の中で、「山田さん」は何回発言しましたか？",
                "山田さんの発言の平均時間はどれくらいですか？",
                "彼が話した内容を箇条書きで3つのポイントに要約してください。",
                "ところで、日本の「トヨタ自動車」の最新のニュースをインターネットで調べて。",
                "その会社の社長は誰ですか？",
                "2026年5月のすべての会議の合計時間は何秒ですか？",
                "その中で一番長かった会議のIDは何ですか？",
                "その一番長かった会議で、新エネルギーについて言及されましたか？"
            ]
    
    for query in queries:
        display_query = query.replace("ユーザー (User): ", "").strip()
        print(f"\nユーザー (User): {display_query}")
        print("思考中 (Thinking)...")
        answer = await hcacis.process_query(session_id, query)
        
        state = hcacis.memory_manager.get_state(session_id)
        det = state.detector_output
        is_followup = det.is_followup if det else 'None'
        intent_cat = det.intent_category if det else 'None'
        rewritten = det.rewritten_standalone_query if det else 'None'
        
        print(f"-> [内部状態] Detector: is_followup={is_followup}, intent_category={intent_cat}")
        print(f"-> [内部状態] Detector: Rewritten Query='{rewritten}'")
        print(f"-> [内部状態] Planner : Plan executed={state.retrieval_plan}")
        
        print(f"\nアシスタント (Assistant):\n{answer}\n")
        print("=" * 80)

    await db_pool.close()

if __name__ == "__main__":
    asyncio.run(main())
