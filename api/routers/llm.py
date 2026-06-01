"""
llm.py — LLM 공급자 메타 엔드포인트.

프론트 토글이 초기 상태를 맞추고(기본 공급자), claude 키 미설정 시 claude 옵션을
비활성화할 수 있도록 가용 정보를 제공한다.

    GET /config/llm  → { default, claudeConfigured, providers: [...] }
"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(tags=["llm"])


class ProviderMeta(BaseModel):
    id: str
    label: str
    model: str
    available: bool


class LlmConfigResponse(BaseModel):
    default: str
    claudeConfigured: bool
    providers: list[ProviderMeta]


@router.get("/config/llm")
async def get_llm_config() -> LlmConfigResponse:
    # src/ 는 api.config import 시 sys.path 에 등록되어 있다.
    from config import resolve_provider, claude_configured, lm_config, claude_config

    local = lm_config()
    claude = claude_config()
    claude_ok = claude_configured()
    return LlmConfigResponse(
        default=resolve_provider(None),
        claudeConfigured=claude_ok,
        providers=[
            ProviderMeta(id="local", label="로컬 LLM", model=local["model"], available=True),
            ProviderMeta(id="claude", label="Claude Haiku", model=claude["model"],
                         available=claude_ok),
        ],
    )
