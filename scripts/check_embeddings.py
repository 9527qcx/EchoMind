"""验证文档和查询的向量化结果。"""

import asyncio
import os

from backend.embeddings import get_embeddings


async def main() -> None:
    embeddings = get_embeddings()
    expected_dimension = int(
        os.getenv("EMBEDDING_DIMENSION", "1024")
    )

    texts = [
        "RAG 通过检索外部知识，辅助模型生成回答。",
        "Streamlit 可以用 Python 快速创建交互页面。",
    ]

    document_vectors = await embeddings.aembed_documents(texts)

    query_vector = await embeddings.aembed_query(
        "什么是检索增强生成？"
    )

    if len(document_vectors) != len(texts):
        raise RuntimeError("返回的文档向量数量与输入文本数量不一致。")

    dimensions = [
        len(vector)
        for vector in document_vectors
    ]
    dimensions.append(len(query_vector))

    if any(
        dimension != expected_dimension
        for dimension in dimensions
    ):
        raise RuntimeError(
            f"向量维度不符合配置："
            f"预期 {expected_dimension}，实际 {dimensions}"
        )

    print("Embedding 调用成功。")
    print("文档向量数量：", len(document_vectors))
    print("文档向量维度：", dimensions[:-1])
    print("查询向量维度：", len(query_vector))
    print("查询向量前 5 项：", query_vector[:5])


if __name__ == "__main__":
    asyncio.run(main())
