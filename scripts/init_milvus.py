"""提前创建知识库子块集合及索引。"""

import os
from pathlib import Path

from dotenv import load_dotenv
from pymilvus import DataType, Function, FunctionType, MilvusClient


load_dotenv(Path(__file__).resolve().parents[1] / ".env")


def build_schema(dense_dim: int):
    """定义一条子块记录包含哪些字段。"""
    schema = MilvusClient.create_schema(
        enable_dynamic_field=True,
    )

    schema.add_field(
        "id",
        DataType.INT64,
        is_primary=True,
        auto_id=True,
    )
    schema.add_field(
        "user_id",
        DataType.INT64,
        is_partition_key=True,
    )
    schema.add_field(
        "file_hash", DataType.VARCHAR, max_length=64,
    )
    schema.add_field(
        "parent_id", DataType.VARCHAR, max_length=128,
    )
    schema.add_field(
        "knowledge_base_id", DataType.VARCHAR, max_length=128,
    )
    schema.add_field(
        "text",
        DataType.VARCHAR,
        max_length=65535,
        enable_analyzer=True,
        analyzer_params={"tokenizer": "jieba"},
    )
    schema.add_field("metadata", DataType.JSON)
    schema.add_field(
        "dense_vector",
        DataType.FLOAT_VECTOR,
        dim=dense_dim,
    )
    schema.add_field(
        "sparse_bm25",
        DataType.SPARSE_FLOAT_VECTOR,
    )

    schema.add_function(
        Function(
            name="bm25_func",
            function_type=FunctionType.BM25,
            input_field_names=["text"],
            output_field_names=["sparse_bm25"],
        )
    )

    return schema


def build_indexes():
    """定义向量检索和字段过滤使用的索引。"""
    indexes = MilvusClient.prepare_index_params()

    indexes.add_index(
        field_name="dense_vector",
        index_name="dense_index",
        index_type="HNSW",
        metric_type="COSINE",
        params={"M": 16, "efConstruction": 200},
    )

    indexes.add_index(
        field_name="sparse_bm25",
        index_name="sparse_bm25_index",
        index_type="SPARSE_INVERTED_INDEX",
        metric_type="BM25",
    )

    for field_name in (
        "user_id",
        "knowledge_base_id",
        "file_hash",
    ):
        indexes.add_index(
            field_name=field_name,
            index_name=f"{field_name}_idx",
            index_type="INVERTED",
        )

    return indexes


def main() -> None:
    uri = os.getenv("MILVUS_URI", "").strip()
    collection_name = os.getenv(
        "MILVUS_KNOWLEDGE_COLLECTION",
        "echomind_knowledge_base",
    ).strip()
    dense_dim = int(
        os.getenv("EMBEDDING_DIMENSION", "1024")
    )

    if not uri or not collection_name:
        raise ValueError("请配置 Milvus 地址和集合名称。")

    if dense_dim <= 0:
        raise ValueError("向量维度必须大于 0。")

    client = MilvusClient(uri=uri, timeout=30)

    try:
        if client.has_collection(collection_name):
            print("集合已存在，跳过创建：", collection_name)
        else:
            client.create_collection(
                collection_name=collection_name,
                schema=build_schema(dense_dim),
                index_params=build_indexes(),
            )
            print("集合创建成功：", collection_name)

        client.load_collection(collection_name)
        print("集合加载成功。")

        description = client.describe_collection(collection_name)
        for field in description["fields"]:
            print("字段：", field["name"])

    finally:
        client.close()


if __name__ == "__main__":
    main()