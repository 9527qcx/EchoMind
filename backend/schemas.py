"""与原项目对应：集中定义接口的请求和响应。"""

from dataclasses import dataclass
from uuid import UUID, uuid4
from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field


class ChatRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    message: str = Field(min_length=1, max_length=4000)
    knowledge_base: str = Field(min_length=1, max_length=50)
    user_id: int = Field(default=1, ge=1, description="当前为演示用户，尚未接入登录。")
    session_id: UUID = Field(
        default_factory=uuid4,
        description="同一会话重复使用同一个 UUID；省略时创建新会话。",
    )


class ChatResponse(BaseModel):
    answer: str
    session_id: UUID


@dataclass
class ContextSchema:
    """沿用原项目的运行上下文，后续供知识库与记忆工具使用。"""

    user_id: int
    knowledge_base_id: str
    top_k: int = 5

class CreateKnowledgeBaseRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    knowledge_base_id: str = Field(min_length=1, max_length=50)
    user_id: int = Field(ge=1)


class CreateKnowledgeBaseResponse(BaseModel):
    knowledge_base_id: str
    status: str = "success"
    message: str

class GetKnowledgeBaseResponse(BaseModel):
    status: str = "success"
    message: str
    count: int
    knowledge_bases: list[str]

class DocumentUploadResponse(BaseModel):
    filename: str
    message: str
    file_hash: str
    knowledge_base_id: str
    is_duplicate: bool

class FileItem(BaseModel):
    file_hash: str
    file_name: str
    uploaded_at: datetime


class GetKnowledgeBaseFilesResponse(BaseModel):
    status: str = "success"
    message: str
    count: int
    files: list[FileItem]

class DocumentDeleteResponse(BaseModel):
    status: str = "success"
    message: str
    knowledge_base_id: str
    file_hash: str
