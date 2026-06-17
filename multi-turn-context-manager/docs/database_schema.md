# データベース・スキーマ設計 (Database Schema)

## 1. 永続ストレージ (Persistent Cold Storage)

### `transcripts` テーブル
通話ログやドキュメントのメタデータを保存します（既存スキーマ）。

| カラム名 | 型 | 制約 |
| :--- | :--- | :--- |
| `id` | `UUID` | PRIMARY KEY |
| `session_id` | `VARCHAR(64)` | INDEX |
| `meeting_date` | `DATE` | |
| `participants` | `JSONB` | |

## 2. 動的コンテキスト・キャッシュ (Dynamic Context Cache)

### `session_context_cache` (Hot Table)
高速な検索とルーティングのためのメタデータを保持します。

| カラム名 | 型 | 制約 |
| :--- | :--- | :--- |
| `id` | `BIGSERIAL` | PRIMARY KEY |
| `session_id` | `VARCHAR(64)` | NOT NULL, INDEX |
| `topic_key` | `TEXT` | NOT NULL |
| `last_pipeline` | `VARCHAR(50)` | SQL, RAG, WEB, MODEL |
| `query_embedding` | `vector(384)` | pgvector |
| `last_accessed_at` | `TIMESTAMP` | LRU 用タイムスタンプ |
| `refreshed_at` | `TIMESTAMP` | TTL 用タイムスタンプ |

### `session_context_payload` (Cold Table)
大きな JSON データを保存し、必要な時だけ読み込まれます。

| カラム名 | 型 | 制約 |
| :--- | :--- | :--- |
| `cache_id` | `BIGINT` | REFERENCES Hot Table (CASCADE) |
| `cached_payload` | `JSONB` | SQL rows, RAG chunks, Web snippets |
| `summary_context` | `JSONB` | ルーティング補助用要約 |

## 3. 実体インデックス (Entity Index)

### `session_entity_index`
代名詞や実体名を高速にマッピングします。

| カラム名 | 型 | 制約 |
| :--- | :--- | :--- |
| `session_id` | `VARCHAR(64)` | NOT NULL, INDEX |
| `entity_id` | `TEXT` | 実体の一意識別子 |
| `entity_type` | `VARCHAR(50)` | person, document, etc. |
| `display_names` | `TEXT[]` | 指示代名詞の配列 (GIN INDEX) |
| `cache_slot_id` | `BIGINT` | 対象のキャッシュスロット |

## 4. 最適化のポイント (Key Optimizations)

*   **Hot/Cold 分離:** メタデータ (Hot) と巨大ペイロード (Cold) を分離することで、PostgreSQL のメモリ効率を最大化し、Seq Scan を回避します。
*   **GIN インデックス:** `display_names` (TEXT配列) に GIN インデックスを貼ることで、代名詞の照合を定数時間で実行可能にします。
*   **Advisory Locks:** 同一セッションに対するリクエストの同時実行を DB レベルで制御し、キャッシュの整合性を保証します。
