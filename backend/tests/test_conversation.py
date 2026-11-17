"""用真实本地 Redis 与确定性模型验证会话行为，无需付费模型请求。"""

import asyncio
import json
import os
import unittest
from unittest.mock import patch
from uuid import uuid4

from fastapi.testclient import TestClient
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langgraph.checkpoint.redis.aio import AsyncRedisSaver
from streamlit.testing.v1 import AppTest

from backend.agent import get_thread_id
from backend.main import app
from backend.llm import get_model


class HistoryModel(BaseChatModel):
    @property
    def _llm_type(self) -> str:
        return "conversation-history-test"

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        content = json.dumps(
            {
                "users": [m.content for m in messages if isinstance(m, HumanMessage)],
                "assistant_count": sum(isinstance(m, AIMessage) for m in messages),
            }
        )
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content=content))])


class ConversationTests(unittest.TestCase):
    def setUp(self):
        self.threads = set()
        self.model_patch = patch("backend.agent.get_model", return_value=HistoryModel())
        self.model_patch.start()
        self.addCleanup(self.model_patch.stop)

    def post(self, client, payload):
        response = client.post("/chat", json=payload)
        self.assertEqual(response.status_code, 200, response.text)
        data = response.json()
        self.threads.add(
            get_thread_id(payload.get("user_id", 1), data["session_id"])
        )
        return data

    def tearDown(self):
        async def cleanup():
            async with AsyncRedisSaver.from_conn_string(os.environ["REDIS_URL"]) as saver:
                await saver.asetup()
                for thread_id in self.threads:
                    await saver.adelete_thread(thread_id)

        asyncio.run(cleanup())

    def test_switch_knowledge_base_keeps_history(self):
        payload = {
            "user_id": 1,
            "session_id": str(uuid4()),
            "knowledge_base": "Research",
        }

        with TestClient(app) as client:
            self.post(client, {
                **payload,
                "message": "remember-alpha",
            })

            result = self.post(client, {
                **payload,
                "knowledge_base": "Other",
                "message": "follow-up",
            })

            history = json.loads(result["answer"])["users"]

            self.assertEqual(history, [
                "remember-alpha",
                "follow-up",
            ])
    def test_history_isolation_and_backend_restart(self):
        session = str(uuid4())
        payload = {"knowledge_base": "Research", "session_id": session, "user_id": 1}
        with TestClient(app) as client:
            first = self.post(client, {**payload, "message": "remember-alpha"})
            self.assertEqual(json.loads(first["answer"])["users"], ["remember-alpha"])
            second = self.post(client, {**payload, "message": "follow-up"})
            self.assertEqual(json.loads(second["answer"]), {
                "users": ["remember-alpha", "follow-up"], "assistant_count": 1
            })
            for changes in [
                {"session_id": str(uuid4())},
                {"user_id": 2},
            ]:
                isolated = self.post(client, {**payload, **changes, "message": "isolated"})
                self.assertEqual(json.loads(isolated["answer"])["users"], ["isolated"])

        # 重新运行应用生命周期，Agent 和 Redis 连接都会重新创建。
        with TestClient(app) as client:
            restored = self.post(client, {**payload, "message": "after-restart"})
            self.assertEqual(json.loads(restored["answer"]), {
                "users": ["remember-alpha", "follow-up", "after-restart"], "assistant_count": 2
            })
            self.assertEqual(client.post("/chat", json={**payload, "message": " "}).status_code, 422)
            self.assertEqual(client.post("/chat", json={**payload, "session_id": "bad", "message": "hello"}).status_code, 422)

    def test_model_clients_are_closed_and_recreated(self):
        with TestClient(app):
            first = get_model()
            self.assertFalse(first.http_async_client.is_closed)
        self.assertTrue(first.http_async_client.is_closed)
        self.assertTrue(first.http_client.is_closed)
        with TestClient(app):
            second = get_model()
            self.assertIsNot(first.http_async_client, second.http_async_client)
            self.assertFalse(second.http_async_client.is_closed)
        self.assertTrue(second.http_async_client.is_closed)

    def test_page_preserves_session_and_clear_starts_new_one(self):
        with TestClient(app) as client:
            from requests import Response

            # 知识库接口使用内存列表，避免页面测试写入业务数据库。
            knowledge_bases = []

            def make_response(status_code, content):
                response = Response()
                response.status_code = status_code
                response._content = content
                response._content_consumed = True
                response.encoding = "utf-8"
                return response

            def get_from_api(url, **kwargs):
                if url.endswith("/get_knowledge_base_files"):
                    return make_response(
                        200,
                        b'{"files": [], "count": 0}',
                    )
                self.assertTrue(url.endswith("/get_knowledge_bases"))
                self.assertEqual(kwargs["params"]["user_id"], 1)
                data = {"knowledge_bases": knowledge_bases, "count": len(knowledge_bases)}
                return make_response(200, json.dumps(data).encode())

            def send_to_api(url, **kwargs):
                payload = kwargs["json"]
                if url.endswith("/create_knowledge_base"):
                    knowledge_bases.append(payload["knowledge_base_id"])
                    return make_response(201, b"{}")
                self.assertTrue(url.endswith("/stream_chat"))
                self.threads.add(get_thread_id(payload["user_id"], payload["session_id"]))
                response = client.post("/stream_chat", json=payload)
                self.assertEqual(response.status_code, 200, response.text)
                return make_response(response.status_code, response.content)

            with patch("requests.post", side_effect=send_to_api), patch("requests.get", side_effect=get_from_api):
                page = AppTest.from_file("frontend/app.py").run(timeout=15)
                self.assertFalse(page.exception)
                original_kb = page.selectbox[0].value
                session = page.session_state["conversation"]["session_id"]
                page.chat_input[0].set_value("page-first").run(timeout=15)
                page.chat_input[0].set_value("page-follow-up").run(timeout=15)
                self.assertFalse(page.exception)
                self.assertEqual(json.loads(page.chat_message[-1].markdown[0].value)["users"], ["page-first", "page-follow-up"])
                page.text_input[0].set_value("Another KB")
                next(b for b in page.button if b.key and b.key.startswith("FormSubmitter:")).click().run(timeout=15)
                self.assertEqual(page.session_state["conversation"]["session_id"], session)
                page.chat_input[0].set_value("other-kb").run(timeout=15)
                self.assertEqual(json.loads(page.chat_message[-1].markdown[0].value)["users"], ["page-first", "page-follow-up", "other-kb"])
                page.selectbox[0].select(original_kb).run()
                self.assertEqual(page.session_state["conversation"]["session_id"], session)
                next(b for b in page.button if b.label == "清空对话").click().run()
                self.assertFalse(page.exception)
                self.assertNotEqual(page.session_state["conversation"]["session_id"], session)
                page.chat_input[0].set_value("after-clear").run(timeout=15)
                self.assertFalse(page.exception)
                self.assertEqual(json.loads(page.chat_message[-1].markdown[0].value)["users"], ["after-clear"])


if __name__ == "__main__":
    unittest.main()
