-- 在 echomind_db 中手动执行；应用启动只建立连接池，不负责建表。
-- 本学习版由业务代码维护关联关系，不设置外键。
BEGIN;

CREATE TABLE IF NOT EXISTS public.users (
    user_id SERIAL PRIMARY KEY,
    user_profile TEXT,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS public.knowledge_bases (
    knowledge_base_id VARCHAR(128) NOT NULL,
    user_id INTEGER NOT NULL,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (knowledge_base_id, user_id)
);

CREATE INDEX IF NOT EXISTS idx_kb_user
    ON public.knowledge_bases(user_id);

COMMIT;
