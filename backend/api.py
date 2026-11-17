"""与原项目 api.py 对应：声明接口，处理 HTTP 层错误。"""

import logging
import asyncpg
from fastapi import APIRouter, HTTPException, Request
from openai import APIError, APITimeoutError
from redis.exceptions import RedisError

from backend.documents_process import (
    TempDocumentProcessor,
    UploadTooLargeError,
)
from backend.agent import get_agent_response, stream_agent_response
from backend.llm import ModelConfigError
from backend.schemas import (ChatRequest,
                             ChatResponse,
                             CreateKnowledgeBaseRequest,
                             DocumentUploadResponse,
                             CreateKnowledgeBaseResponse,
                             GetKnowledgeBaseResponse,
                             GetKnowledgeBaseFilesResponse,
                             DocumentDeleteResponse,)



from backend.postgresql_client import PostgreSQLParentClient
import json
from uuid import UUID
from pathlib import Path

from fastapi import Depends, Query, File, UploadFile, Form
from fastapi.responses import StreamingResponse


router = APIRouter()
logger = logging.getLogger(__name__)

async def get_postgresql_client(
    request: Request,
) -> PostgreSQLParentClient:
    return request.app.state.postgresql_client

@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.post("/chat", response_model=ChatResponse, summary="发送聊天消息", tags=["聊天"])
async def chat(request: ChatRequest, http_request: Request) -> ChatResponse:
    try:
        answer = await get_agent_response(
            agent=http_request.app.state.agent,
            user_message=request.message,
            knowledge_base_id=request.knowledge_base,
            user_id=request.user_id,
            session_id=str(request.session_id),
        )
    except ModelConfigError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from None
    except APITimeoutError:
        raise HTTPException(status_code=504, detail="模型服务响应超时，请稍后重试。") from None
    except APIError as exc:
        # 只记录状态码，不输出第三方错误中的密钥或请求正文。
        status = getattr(exc, "status_code", None)
        logger.warning("模型服务调用失败，HTTP 状态码：%s", status)
        detail = "模型服务调用失败，请检查 API 地址、模型名称及网络连接。"
        if status in (401, 403):
            detail = "模型服务鉴权失败，请检查 API Key 和模型访问权限。"
        elif status == 429:
            detail = "模型服务限流或额度不足，请检查服务商控制台。"
        raise HTTPException(status_code=502, detail=detail) from None
    except RedisError:
        raise HTTPException(status_code=503, detail="会话存储暂时不可用，请检查本地 Redis 服务。") from None
    except ValueError:
        raise HTTPException(status_code=502, detail="模型未返回有效文本，请检查模型是否支持文本问答。") from None

    return ChatResponse(answer=answer, session_id=request.session_id)


@router.post("/stream_chat", response_class=StreamingResponse, summary="流式聊天消息", tags=["聊天"])
async def stream_chat(
    http_request: Request,
    request: ChatRequest,
) -> StreamingResponse:
    async def events():
        try:
            async for event in stream_agent_response(
                agent=http_request.app.state.agent,
                user_message=request.message.strip(),
                knowledge_base_id=request.knowledge_base.strip(),
                user_id=request.user_id,
                session_id=str(request.session_id),
            ):
                yield event

        except (APIError, RedisError, ValueError) as exc:
            logger.warning(
                "流式回答失败，异常类型：%s",
                type(exc).__name__,
            )

            yield json.dumps(
                {
                    "type": "error",
                    "content": "生成回复失败，请检查模型或 Redis 服务后重试。",
                },
                ensure_ascii=False,
            ) + "\n"

    return StreamingResponse(
        events(),
        media_type="text/plain; charset=utf-8",
    )

@router.post(
    "/create_knowledge_base",
    response_model=CreateKnowledgeBaseResponse,
    status_code=201,
    summary="创建知识库",
    tags=["知识库"],
)
async def create_knowledge_base(
    payload: CreateKnowledgeBaseRequest,
    client: PostgreSQLParentClient = Depends(get_postgresql_client),
) -> CreateKnowledgeBaseResponse:
    try:
        result = await client.create_knowledge_base(
            knowledge_base_id=payload.knowledge_base_id,
            user_id=payload.user_id,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from None
    except (asyncpg.PostgresError, OSError, TimeoutError) as exc:
        logger.warning(
            "创建知识库失败，异常类型：%s",
            type(exc).__name__,
        )
        raise HTTPException(
            status_code=503,
            detail="数据库操作失败，请检查数据库服务及后端日志。",
        ) from None

    if not result["success"]:
        raise HTTPException(
            status_code=409,
            detail=result["message"],
        )

    return CreateKnowledgeBaseResponse(
        knowledge_base_id=result["knowledge_base_id"],
        message=result["message"],
    )

@router.get(
    "/get_knowledge_bases",
    response_model=GetKnowledgeBaseResponse,
    summary="查询用户的知识库列表",
    tags=["知识库"],
)
async def get_user_knowledge_bases(
    user_id: int = Query(..., ge=1),
    client: PostgreSQLParentClient = Depends(get_postgresql_client),
) -> GetKnowledgeBaseResponse:
    try:
        result = await client.get_user_knowledge_bases(user_id)
    except (asyncpg.PostgresError, OSError, TimeoutError) as exc:
        logger.warning(
            "查询知识库失败，异常类型：%s",
            type(exc).__name__,
        )
        raise HTTPException(
            status_code=503,
            detail="数据库查询失败，请检查数据库服务及后端日志。",
        ) from None

    return GetKnowledgeBaseResponse(
        message=result["message"],
        count=result["count"],
        knowledge_bases=result["knowledge_bases"],
    )

@router.post(
    "/document_upload",
    response_model=DocumentUploadResponse,
    summary="上传文档",
    tags=["文档"],
)
async def document_upload(
    file: UploadFile = File(...),
    knowledge_base_id: str = Form(..., min_length=1, max_length=50),
    user_id: int = Form(..., ge=1),
    postgresql_client: PostgreSQLParentClient = Depends(get_postgresql_client),
) -> DocumentUploadResponse:
    temp_path: Path | None = None

    try:
        knowledge_base_id = knowledge_base_id.strip()

        if not knowledge_base_id:
            raise HTTPException(400, detail="知识库名称不能为空。")

        filename = Path(
            (file.filename or "").replace("\\", "/")
        ).name

        if not filename or len(filename) > 255:
            raise HTTPException(400, detail="文件名为空或超过 255 个字符。")

        if Path(filename).suffix.lower() not in {
            ".pdf", ".docx", ".txt", ".md"
        }:
            raise HTTPException(400, detail="仅支持 PDF、DOCX、TXT、MD 文件。")

        # 普通知识库需要先创建；默认知识库保留为特殊入口。
        if knowledge_base_id != "默认知识库":
            result = await postgresql_client.get_user_knowledge_bases(user_id)

            if knowledge_base_id not in result["knowledge_bases"]:
                raise HTTPException(404, detail="该用户的知识库不存在。")

        processor = TempDocumentProcessor()

        temp_path, file_hash = await processor.save_upload(file)

        # 原文件保存成功后，再登记数据库。
        await processor.persist_upload(temp_path, file_hash)

        created = await postgresql_client.add_file_metadata(
            file_hash=file_hash,
            file_name=filename,
            knowledge_base_id=knowledge_base_id,
            user_id=user_id,
        )

        return DocumentUploadResponse(
            filename=filename,
            message=(
                "文件已上传，尚未解析。"
                if created
                else "文件已存在，无需重复登记。"
            ),
            file_hash=file_hash,
            knowledge_base_id=knowledge_base_id,
            is_duplicate=not created,
        )

    except UploadTooLargeError as exc:
        raise HTTPException(413, detail=str(exc)) from None

    except ValueError as exc:
        raise HTTPException(400, detail=str(exc)) from None

    except (asyncpg.PostgresError, OSError, TimeoutError) as exc:
        logger.warning(
            "文件上传失败，异常类型：%s",
            type(exc).__name__,
        )
        raise HTTPException(
            503,
            detail="文件保存或登记失败，请检查磁盘、数据库及后端日志。",
        ) from None

    finally:
        try:
            if temp_path is not None:
                temp_path.unlink(missing_ok=True)
        finally:
            await file.close()

@router.get(
    "/get_knowledge_base_files",
    response_model=GetKnowledgeBaseFilesResponse,
    summary="查询知识库文件列表",
    tags=["文档"],
)
async def get_knowledge_base_files(
    knowledge_base_id: str = Query(..., min_length=1, max_length=50),
    user_id: int = Query(..., ge=1),
    postgresql_client: PostgreSQLParentClient = Depends(get_postgresql_client),
) -> GetKnowledgeBaseFilesResponse:
    knowledge_base_id = knowledge_base_id.strip()

    if not knowledge_base_id:
        raise HTTPException(400, detail="知识库名称不能为空。")

    try:
        result = await postgresql_client.get_knowledge_base_files(
            knowledge_base_id=knowledge_base_id,
            user_id=user_id,
        )
    except (asyncpg.PostgresError, OSError, TimeoutError) as exc:
        logger.warning(
            "查询文件列表失败，异常类型：%s",
            type(exc).__name__,
        )
        raise HTTPException(
            503,
            detail="文件列表查询失败，请检查数据库及后端日志。",
        ) from None

    return GetKnowledgeBaseFilesResponse(
        message=result["message"],
        count=result["count"],
        files=result["files"],
    )

@router.delete(
    "/document_delete",
    response_model=DocumentDeleteResponse,
    summary="从知识库移除文档",
    tags=["文档"],
)
async def document_delete(
    file_hash: str = Query(..., pattern="^[0-9a-f]{64}$"),
    knowledge_base_id: str = Query(..., min_length=1, max_length=50),
    user_id: int = Query(..., ge=1),
    postgresql_client: PostgreSQLParentClient = Depends(get_postgresql_client),
) -> DocumentDeleteResponse:
    knowledge_base_id = knowledge_base_id.strip()

    if not knowledge_base_id:
        raise HTTPException(400, detail="知识库名称不能为空。")

    try:
        deleted = await postgresql_client.delete_file(
            file_hash=file_hash,
            knowledge_base_id=knowledge_base_id,
            user_id=user_id,
        )
    except (asyncpg.PostgresError, OSError, TimeoutError) as exc:
        logger.warning(
            "移除文档失败，异常类型：%s",
            type(exc).__name__,
        )
        raise HTTPException(
            503,
            detail="移除文档失败，请检查数据库及后端日志。",
        ) from None

    if not deleted:
        raise HTTPException(
            404,
            detail="该知识库中不存在此文件记录。",
        )

    return DocumentDeleteResponse(
        message="文档已从当前知识库移除。",
        knowledge_base_id=knowledge_base_id,
        file_hash=file_hash,
    )
