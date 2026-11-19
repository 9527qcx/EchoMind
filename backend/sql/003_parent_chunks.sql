-- 父块正文保存在 PostgreSQL，子块和向量保存在 Milvus。
-- 不设置外键，关联检查和删除由业务代码在事务中处理。
BEGIN;

CREATE TABLE IF NOT EXISTS public.parent_chunks (
    parent_id VARCHAR(128) NOT NULL,
    knowledge_base_id VARCHAR(128) NOT NULL,
    user_id INTEGER NOT NULL,
    text TEXT NOT NULL,
    file_name VARCHAR(255) NOT NULL,
    file_hash VARCHAR(64) NOT NULL,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (parent_id, knowledge_base_id, user_id)
);

CREATE INDEX IF NOT EXISTS idx_parent_file_scope
    ON public.parent_chunks(file_hash, knowledge_base_id, user_id);

CREATE INDEX IF NOT EXISTS idx_parent_kb_user
    ON public.parent_chunks(knowledge_base_id, user_id);

COMMIT;
