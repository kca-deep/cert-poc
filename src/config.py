"""
config.py — .env 기반 공용 설정 로더

모든 러너(full_run, dry_run, param_run)는 이 모듈을 통해 파라미터를 읽습니다.
.env 파일이 없거나 항목이 없으면 괄호 안 기본값이 적용됩니다.
"""

import json
import os
from pathlib import Path
from dotenv import load_dotenv

ROOT = Path(__file__).parent.parent
load_dotenv(ROOT / ".env")

PROMPT_DIR = ROOT / "prompts"

# response_format=json_schema 로 전송하기 전 제거할 메타키 (llama.cpp GBNF 변환기는
# 무시하지만, 검증된 cert-harness SCHEMA 와 동일하게 순수 스키마만 보낸다).
_SCHEMA_META_KEYS = ("$schema", "$id", "title", "description")


def holistic_schema() -> dict:
    """
    holistic 출력 강제용 JSON Schema 를 반환한다 (prompts/_shared/output_schema.json).

    response_format={"type":"json_schema","json_schema":{"name":"review","schema":<이것>}}
    형태로 llama.cpp 에 전달되어 서버에서 GBNF grammar 로 변환·강제된다. 최상위
    메타키($schema/$id/title/description)는 제거해 검증된 하네스 SCHEMA 와 동일하게 만든다.
    """
    raw = json.loads(
        (PROMPT_DIR / "_shared" / "output_schema.json").read_text(encoding="utf-8")
    )
    return {k: v for k, v in raw.items() if k not in _SCHEMA_META_KEYS}


def lm_config() -> dict:
    """로컬 LLM 호출에 필요한 파라미터를 .env 에서 읽어 반환합니다."""
    return {
        "base_url":         os.getenv("LOCAL_BASE_URL",       "http://127.0.0.1:8080/v1"),
        "model":            os.getenv("LLM_MODEL",            "openai/gpt-oss-20b"),
        # holistic 운영조건(cert-harness Run E 확정): temp=0(결정성), max_tokens=8000
        # (thinking 종료 후 content 여력 확보). 서버측 --reasoning-budget 6000 과 짝.
        "temperature":      float(os.getenv("LLM_TEMPERATURE",      "0")),
        "max_tokens":       int(os.getenv("LLM_MAX_TOKENS",         "8000")),
        "reasoning_effort": os.getenv("LLM_REASONING_EFFORT", "medium"),
        # holistic: gemma4 어려운 문항은 thinking 으로 ~200s. read 타임아웃을 넉넉히.
        "timeout":          int(os.getenv("LLM_TIMEOUT",            "600")),
        "connect_timeout":  int(os.getenv("LLM_CONNECT_TIMEOUT",    "5")),
        "max_retries":      int(os.getenv("LLM_MAX_RETRIES",        "1")),
        "retry_delay":      int(os.getenv("LLM_RETRY_DELAY",        "5")),
        # KV 캐시 격리 설정
        # cache_prompt=False: 매 요청을 처음부터 인코딩 (슬롯 KV 상태 재사용 금지)
        # slot_round_robin=True: 연속 호출을 다른 슬롯에 분산 (슬롯 간 캐시 혼용 방지)
        # n_slots: 서버 슬롯 수 (llama.cpp --parallel 값과 일치시킬 것)
        "cache_prompt":     os.getenv("LLM_CACHE_PROMPT",     "false").lower() == "true",
        "slot_round_robin": os.getenv("LLM_SLOT_ROUND_ROBIN", "false").lower() == "true",
        "n_slots":          int(os.getenv("LLM_N_SLOTS",      "4")),
        "parallel_workers": int(os.getenv("LLM_PARALLEL_WORKERS", "3")),
    }


def claude_config() -> dict:
    """Claude SDK 호출에 필요한 파라미터를 .env 에서 읽어 반환합니다."""
    return {
        "model":       os.getenv("CLAUDE_MODEL",       "claude-haiku-4-5"),
        "max_tokens":  int(os.getenv("CLAUDE_MAX_TOKENS",  "1024")),
        "max_retries": int(os.getenv("CLAUDE_MAX_RETRIES", "1")),
        "retry_delay": int(os.getenv("CLAUDE_RETRY_DELAY", "3")),
    }


VALID_PROVIDERS = ("local", "claude")


# 자동탐지 공통 후보(.env 미설정 시). 흔한 로컬 OpenAI 호환 포트를 순서대로 본다:
# Ollama(11434) → llama.cpp(8080/8081) → LM Studio(1234). 첫 healthy 가 채택된다.
DEFAULT_LOCAL_CANDIDATES = [
    "http://127.0.0.1:11434/v1",  # Ollama (OpenAI 호환 엔드포인트)
    "http://127.0.0.1:8080/v1",   # llama.cpp
    "http://127.0.0.1:8081/v1",   # llama.cpp (alternate model)
    "http://127.0.0.1:1234/v1",   # LM Studio
]


def local_base_urls() -> list[str]:
    """
    로컬 LLM 후보 base_url 목록(자동탐지 순서). 첫 healthy 서버를 채택한다.

    - LOCAL_BASE_URLS(콤마구분)가 있으면 그 목록만 순서대로(= 우선순위) 사용한다.
      예: ollama(11434), gpt-oss(8080), exaone(8081)을 적어두면 분석 전
          health 체크로 살아있는 쪽을 자동 채택한다.
    - LOCAL_BASE_URL(단일)만 있으면 그것을 최우선으로 두고, 공통 후보를 폴백으로
      덧붙인다(명시 서버가 죽어도 Ollama 등을 자동탐지).
    - 둘 다 없으면 공통 후보(11434/8080/8081/1234)만 스캔한다.
    """
    multi = os.getenv("LOCAL_BASE_URLS", "").strip()
    if multi:
        urls = [u.strip() for u in multi.split(",") if u.strip()]
        return list(dict.fromkeys(urls))
    single = os.getenv("LOCAL_BASE_URL", "").strip()
    if single:
        return list(dict.fromkeys([single, *DEFAULT_LOCAL_CANDIDATES]))
    return list(DEFAULT_LOCAL_CANDIDATES)


def _native_root(base_url: str) -> str:
    """OpenAI 호환 base_url(...:11434/v1)에서 Ollama 네이티브 루트(...:11434)를 얻는다."""
    root = base_url.rstrip("/")
    return root[:-3] if root.endswith("/v1") else root


def probe_ollama(base_url: str, connect: float = 3.0) -> dict | None:
    """
    Ollama 네이티브 API 로 '실행 중인' 모델을 탐지한다.

    GET /api/ps(메모리에 로딩된=실행중 모델) 를 우선 보고, 비어 있으면(idle 로 언로드)
    GET /api/tags(설치된 모델) 의 첫 모델로 폴백한다. /api/ps 가 200 이 아니면
    Ollama 가 아니므로 None 을 반환한다(=OpenAI 호환 프로브로 넘어감).

    반환: {"model": id, "backend": "ollama", "loaded": bool} 또는 None.
    """
    import httpx

    root = _native_root(base_url)
    timeout = httpx.Timeout(5.0, connect=connect)
    try:
        ps = httpx.get(root + "/api/ps", timeout=timeout)
    except httpx.RequestError:
        return None
    if ps.status_code != 200:
        return None  # /api/ps 미존재 → Ollama 아님(llama.cpp/LM Studio)
    try:
        loaded = ps.json().get("models") or []
        if loaded:
            name = loaded[0].get("model") or loaded[0].get("name") or ""
            return {"model": name, "backend": "ollama", "loaded": True}
        tags = httpx.get(root + "/api/tags", timeout=timeout)
        installed = (tags.json().get("models") or []) if tags.status_code == 200 else []
        first = (installed[0].get("model") or installed[0].get("name") or "") if installed else ""
        return {"model": first, "backend": "ollama", "loaded": False}
    except Exception:  # noqa: BLE001 - 살아있으나 응답 파싱 실패
        return {"model": "", "backend": "ollama", "loaded": False}


def probe_backend(base_url: str, connect: float = 3.0) -> dict | None:
    """
    로컬 LLM 서버 1개를 프로브한다. Ollama(네이티브 /api/ps·/api/tags)를 먼저
    시도하고, 아니면 OpenAI 호환 GET {base_url}/models 로 떨어진다.

    반환(살아있음): {"model": id, "backend": "ollama"|"openai", "loaded": bool|None}.
    접속 불가면 None. connect 타임아웃을 짧게 잡아 죽은 포트를 빠르게 넘긴다.
    """
    import httpx

    ollama = probe_ollama(base_url, connect=connect)
    if ollama is not None:
        return ollama

    url = base_url.rstrip("/") + "/models"
    try:
        resp = httpx.get(url, timeout=httpx.Timeout(5.0, connect=connect))
    except httpx.RequestError:
        return None
    try:
        models = resp.json().get("data") or []
        model = (models[0].get("id") or "") if models else ""
    except Exception:  # noqa: BLE001 - 살아있으나 모델 목록 파싱 실패
        model = ""
    return {"model": model, "backend": "openai", "loaded": None}


def probe_local_backends(candidates: list[str] | None = None) -> dict | None:
    """
    후보 base_url 들을 순서대로 프로브해 첫 healthy 서버 정보를 반환한다.
    전부 접속 불가면 None. 첫 healthy 에서 멈추므로(공통 경로 지연 없음) 11434 가
    살아있으면 8080 은 프로브하지 않는다.

    반환: {"base_url", "model", "backend", "loaded"} 또는 None.
    """
    for url in (candidates or local_base_urls()):
        info = probe_backend(url)
        if info is not None:
            return {"base_url": url, **info}
    return None


def resolve_provider(explicit: str | None = None) -> str:
    """활성 공급자 결정: 명시값 > LLM_PROVIDER 환경변수 > 'local'."""
    p = (explicit or os.getenv("LLM_PROVIDER", "local") or "local").lower()
    return p if p in VALID_PROVIDERS else "local"


def claude_configured() -> bool:
    """ANTHROPIC_API_KEY 가 환경(.env 포함)에 존재하는지."""
    return bool(os.getenv("ANTHROPIC_API_KEY", "").strip())


def build_config(provider: str | None = None) -> dict:
    """
    파이프라인이 사용하는 단일 cfg 를 만든다. local 파라미터를 기반으로 하고
    공급자/claude 파라미터를 합쳐, call_with_retry 가 cfg['provider'] 로 분기한다.
    provider == 'claude' 면 재시도/타임아웃을 claude 값으로 덮어쓴다.
    """
    provider = resolve_provider(provider)
    cfg = lm_config()
    c = claude_config()
    cfg["base_url_candidates"] = local_base_urls()
    cfg["provider"]          = provider
    cfg["claude_model"]      = c["model"]
    cfg["claude_max_tokens"] = c["max_tokens"]
    cfg["claude_api_key"]    = os.getenv("ANTHROPIC_API_KEY", "").strip()
    # holistic 출력 강제 스키마. local(llama.cpp) 은 response_format=json_schema 로
    # GBNF 강제, grammar 미지원 공급자(claude 등)는 폴백 파서가 방어한다.
    cfg["response_schema"]   = holistic_schema()
    if provider == "claude":
        cfg["max_retries"] = c["max_retries"]
        cfg["retry_delay"] = c["retry_delay"]
    return cfg


def print_lm_config(cfg: dict, overrides: dict | None = None) -> None:
    """실행 시 적용 파라미터를 출력합니다. overrides 는 CLI 로 덮어쓴 항목."""
    overrides = overrides or {}
    lines = []
    provider = cfg.get("provider", "local")
    lines.append(f"  provider={provider} {'(CLI)' if 'provider' in overrides else '(.env)'}")
    if provider == "claude":
        keys = ("claude_model", "claude_max_tokens", "max_retries", "retry_delay")
    else:
        keys = ("base_url", "model", "temperature", "max_tokens", "reasoning_effort",
                "timeout", "max_retries", "retry_delay")
    for key in keys:
        if key not in cfg:
            continue
        src = "(CLI)" if key in overrides else "(.env)"
        lines.append(f"  {key}={cfg[key]} {src}")
    print("[설정]")
    print("\n".join(lines))
