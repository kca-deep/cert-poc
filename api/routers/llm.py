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
    # local(Ollama) 전용: 모델이 메모리에 로딩(=실행중)됐는지. None=무관(claude/clovax/llama.cpp).
    loaded: bool | None = None
    # 탐지된 백엔드 종류: "ollama" | "openai" | None.
    backend: str | None = None


class LlmConfigResponse(BaseModel):
    default: str
    claudeConfigured: bool
    clovaxConfigured: bool
    providers: list[ProviderMeta]


@router.get("/config/llm")
async def get_llm_config() -> LlmConfigResponse:
    # src/ 는 api.config import 시 sys.path 에 등록되어 있다.
    from config import (resolve_provider, claude_configured, clovax_configured,
                        lm_config, claude_config, clovax_config, probe_local_backends)

    local = lm_config()
    claude = claude_config()
    clovax = clovax_config()
    claude_ok = claude_configured()
    clovax_ok = clovax_configured()
    # 로컬 후보(8080/8081)를 실시간 프로브 → 토글이 죽은 백엔드를 비활성화하고,
    # 살아있으면 실제 로딩 모델명(gpt-oss/exaone)을 노출(차수마다 모델이 바뀜).
    probed = probe_local_backends()
    local_available = probed is not None
    local_model = probed["model"] if (probed and probed["model"]) else local["model"]
    local_loaded = probed.get("loaded") if probed else None
    local_backend = probed.get("backend") if probed else None
    return LlmConfigResponse(
        default=resolve_provider(None),
        claudeConfigured=claude_ok,
        clovaxConfigured=clovax_ok,
        providers=[
            ProviderMeta(id="local", label="로컬 LLM", model=local_model,
                         available=local_available, loaded=local_loaded,
                         backend=local_backend),
            ProviderMeta(id="claude", label="Claude Haiku", model=claude["model"],
                         available=claude_ok),
            ProviderMeta(id="clovax", label="HyperCLOVA X", model=clovax["model"],
                         available=clovax_ok),
        ],
    )
