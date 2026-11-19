"""知识库子块的向量化与存储。"""
import json
import logging
from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings
from pymilvus import AnnSearchRequest, AsyncMilvusClient, RRFRanker

logger = logging.getLogger(__name__)

class KnowledgeBaseManager:
    def __init__(
        self,
        client: AsyncMilvusClient,
        embeddings: Embeddings,
        collection_name: str,
        dense_dim: int,
    ):
        self.client = client
        self.embeddings = embeddings
        self.collection_name = collection_name
        self.dense_dim = dense_dim

    async def add_chunks_batch(
        self,
        knowledge_base_id: str,
        chunks: list[Document],
        user_id: int,
    ) -> dict:
        """校验子块，生成向量，然后批量写入 Milvus。"""
        if not chunks:
            return {"insert_count": 0, "ids": []}

        texts = []
        records = []
        column_fields = {
            "parent_id",
            "file_hash",
            "knowledge_base_id",
            "user_id",
        }

        for chunk in chunks:
            metadata = chunk.metadata

            if metadata.get("user_id") != user_id:
                raise ValueError("子块所属用户不一致。")

            if metadata.get("knowledge_base_id") != knowledge_base_id:
                raise ValueError("子块所属知识库不一致。")

            if not metadata.get("parent_id") or not metadata.get("file_hash"):
                raise ValueError("子块缺少父块 ID 或文件哈希。")

            if not chunk.page_content.strip():
                raise ValueError("子块正文不能为空。")

            texts.append(chunk.page_content)
            records.append({
                "user_id": user_id,
                "knowledge_base_id": knowledge_base_id,
                "file_hash": metadata["file_hash"],
                "parent_id": metadata["parent_id"],
                "text": chunk.page_content,
                "metadata": {
                    key: value
                    for key, value in metadata.items()
                    if key not in column_fields
                },
            })

        vectors = await self.embeddings.aembed_documents(texts)

        if len(vectors) != len(records):
            raise ValueError("向量数量与子块数量不一致。")

        for record, vector in zip(records, vectors):
            if len(vector) != self.dense_dim:
                raise ValueError(
                    f"向量维度错误：预期 {self.dense_dim}，"
                    f"实际 {len(vector)}。"
                )

            record["dense_vector"] = vector

        return await self.client.insert(
            collection_name=self.collection_name,
            data=records,
            timeout=30,
        )

    async def hybrid_retrieval_knowledge_base(
        self,
        query: str,
        knowledge_base_id: str,
        user_id: int,
        top_k: int = 5,
    ) -> list[str]:
        """混合检索子块，按排名返回去重后的父块 ID。"""
        query = query.strip()

        if not query or not knowledge_base_id.strip():
            raise ValueError("问题和知识库名称不能为空。")

        if user_id < 1 or not 1 <= top_k <= 20:
            raise ValueError(
                "用户 ID 必须为正数，top_k 必须在 1 到 20 之间。"
            )

        vector = await self.embeddings.aembed_query(query)

        if len(vector) != self.dense_dim:
            raise ValueError("查询向量维度与集合不一致。")

        filter_expr = f"user_id == {user_id}"

        if knowledge_base_id != "默认知识库":
            filter_expr += (
                " and knowledge_base_id == "
                + json.dumps(knowledge_base_id, ensure_ascii=False)
            )

        dense_request = AnnSearchRequest(
            data=[vector],
            anns_field="dense_vector",
            param={
                "metric_type": "COSINE",
                "params": {"ef": 64},
            },
            limit=top_k * 7,
            expr=filter_expr,
        )

        sparse_request = AnnSearchRequest(
            data=[query],
            anns_field="sparse_bm25",
            param={"metric_type": "BM25"},
            limit=top_k * 3,
            expr=filter_expr,
        )

        try:
            results = await self.client.hybrid_search(
                collection_name=self.collection_name,
                reqs=[dense_request, sparse_request],
                ranker=RRFRanker(),
                limit=top_k * 3,
                output_fields=["parent_id"],
                timeout=30,
            )

        except Exception as exc:
            logger.warning(
                "混合检索失败，降级为向量检索：%s",
                exc,
            )

            results = await self.client.search(
                collection_name=self.collection_name,
                data=[vector],
                anns_field="dense_vector",
                search_params={
                    "metric_type": "COSINE",
                    "params": {"ef": 64},
                },
                filter=filter_expr,
                limit=top_k,
                output_fields=["parent_id"],
                timeout=30,
            )

        if not results:
            return []

        parent_ids = []
        seen = set()

        for hit in results[0]:
            parent_id = hit["entity"]["parent_id"]

            if parent_id not in seen:
                seen.add(parent_id)
                parent_ids.append(parent_id)

        return parent_ids
