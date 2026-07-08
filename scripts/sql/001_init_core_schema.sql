-- Core Auralys schema
-- Covers:
-- - domain ingestion tables
-- - reusable conversation/message/memory persistence
-- - legacy discussion history and review queue compatibility

CREATE TABLE IF NOT EXISTS fiches (
    fiche_id TEXT PRIMARY KEY,
    source_file TEXT NOT NULL,
    page_key TEXT NOT NULL,
    client TEXT,
    maintenance_number TEXT,
    service_date DATE,
    service_time TIME,
    service_types JSONB NOT NULL DEFAULT '[]'::jsonb,
    searchable_text TEXT NOT NULL,
    payload JSONB NOT NULL
);

CREATE TABLE IF NOT EXISTS chunks (
    chunk_id TEXT PRIMARY KEY,
    fiche_id TEXT NOT NULL REFERENCES fiches(fiche_id) ON DELETE CASCADE,
    source_file TEXT NOT NULL,
    page_key TEXT NOT NULL,
    chunk_type TEXT NOT NULL,
    ordinal INTEGER NOT NULL DEFAULT 0,
    content TEXT NOT NULL,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_fiches_client ON fiches (client);
CREATE INDEX IF NOT EXISTS idx_fiches_maintenance_number ON fiches (maintenance_number);
CREATE INDEX IF NOT EXISTS idx_chunks_fiche_id ON chunks (fiche_id);
CREATE INDEX IF NOT EXISTS idx_chunks_chunk_type ON chunks (chunk_type);

CREATE TABLE IF NOT EXISTS conversations (
    id BIGSERIAL PRIMARY KEY,
    conversation_key TEXT NOT NULL UNIQUE,
    user_id BIGINT,
    role TEXT,
    channel TEXT NOT NULL DEFAULT 'chat',
    status TEXT NOT NULL DEFAULT 'active',
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_message_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_conversations_user_id ON conversations (user_id);
CREATE INDEX IF NOT EXISTS idx_conversations_role ON conversations (role);
CREATE INDEX IF NOT EXISTS idx_conversations_last_message_at
    ON conversations (last_message_at DESC);

CREATE TABLE IF NOT EXISTS messages (
    id BIGSERIAL PRIMARY KEY,
    conversation_id BIGINT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    sender TEXT NOT NULL,
    message_type TEXT NOT NULL DEFAULT 'text',
    content TEXT NOT NULL,
    transcript TEXT,
    audio_path TEXT,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_messages_conversation_id_created_at
    ON messages (conversation_id, created_at ASC, id ASC);
CREATE INDEX IF NOT EXISTS idx_messages_sender ON messages (sender);

CREATE TABLE IF NOT EXISTS memories (
    id BIGSERIAL PRIMARY KEY,
    scope TEXT NOT NULL DEFAULT 'global',
    memory_type TEXT NOT NULL,
    content TEXT NOT NULL,
    source_conversation_id BIGINT REFERENCES conversations(id) ON DELETE SET NULL,
    source_message_id BIGINT REFERENCES messages(id) ON DELETE SET NULL,
    status TEXT NOT NULL DEFAULT 'PENDING',
    confidence DOUBLE PRECISION NOT NULL DEFAULT 0.5,
    tags JSONB NOT NULL DEFAULT '[]'::jsonb,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_memories_status_created_at
    ON memories (status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_memories_scope_type
    ON memories (scope, memory_type);

CREATE TABLE IF NOT EXISTS discussion_history (
    history_id BIGSERIAL PRIMARY KEY,
    conversation_id TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    input_type TEXT NOT NULL,
    original_query TEXT NOT NULL,
    transcript TEXT,
    normalized_query TEXT,
    route TEXT,
    intent TEXT,
    filters JSONB NOT NULL DEFAULT '{}'::jsonb,
    answer TEXT NOT NULL,
    response_source TEXT,
    model_output TEXT,
    llm_error TEXT,
    token_usage JSONB NOT NULL DEFAULT '{}'::jsonb,
    timings JSONB NOT NULL DEFAULT '{}'::jsonb,
    spoken_text TEXT,
    hits JSONB NOT NULL DEFAULT '[]'::jsonb,
    reasoning_signals JSONB NOT NULL DEFAULT '{}'::jsonb,
    reasoning_summary TEXT,
    sav_admin_analysis JSONB NOT NULL DEFAULT '{}'::jsonb,
    admin_alert JSONB,
    admin_alert_log_path TEXT,
    output_audio_path TEXT
);

CREATE INDEX IF NOT EXISTS idx_discussion_history_conversation_id
    ON discussion_history (conversation_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_discussion_history_created_at
    ON discussion_history (created_at DESC);

CREATE TABLE IF NOT EXISTS review_cases (
    history_id BIGINT PRIMARY KEY REFERENCES discussion_history(history_id) ON DELETE CASCADE,
    review_status TEXT NOT NULL DEFAULT 'pending',
    decision TEXT,
    review_notes TEXT,
    corrected_answer TEXT,
    knowledge_action TEXT,
    reviewed_by TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    reviewed_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_review_cases_status_updated_at
    ON review_cases (review_status, updated_at DESC);

CREATE TABLE IF NOT EXISTS agent_feedback (
    id BIGSERIAL PRIMARY KEY,
    conversation_id BIGINT REFERENCES conversations(id) ON DELETE CASCADE,
    user_id BIGINT,
    rating VARCHAR(50),
    correction TEXT,
    should_remember BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS agent_actions (
    id BIGSERIAL PRIMARY KEY,
    conversation_id BIGINT REFERENCES conversations(id) ON DELETE CASCADE,
    action_type VARCHAR(100),
    status VARCHAR(50),
    input_json JSONB,
    output_json JSONB,
    requires_approval BOOLEAN DEFAULT FALSE,
    approved_by BIGINT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS agent_tool_logs (
    id BIGSERIAL PRIMARY KEY,
    tool_name VARCHAR(100),
    input_json JSONB,
    output_json JSONB,
    success BOOLEAN,
    error_message TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
