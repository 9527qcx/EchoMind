-- 文件信息与原文件内容分开存储；本表只保存元数据。
BEGIN;

CREATE TABLE IF NOT EXISTS public.file_metadata (
    file_hash VARCHAR(64) NOT NULL,
    file_name VARCHAR(255) NOT NULL,
    knowledge_base_id VARCHAR(128) NOT NULL,
    user_id INTEGER NOT NULL,
    uploaded_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (file_hash, knowledge_base_id, user_id)
);

CREATE INDEX IF NOT EXISTS idx_file_kb_user_time
    ON public.file_metadata(knowledge_base_id, user_id, uploaded_at DESC);

COMMIT;
