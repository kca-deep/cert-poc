"""
config.py — .env 기반 공용 설정 로더

모든 러너(full_run, dry_run, param_run)는 이 모듈을 통해 파라미터를 읽습니다.
.env 파일이 없거나 항목이 없으면 괄호 안 기본값이 적용됩니다.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

ROOT = Path(__file__).parent.parent
load_dotenv(ROOT / ".env")


def lm_config() -> dict:
    """로컬 LLM 호출에 필요한 파라미터를 .env 에서 읽어 반환합니다."""
    return {
        "base_url":         os.getenv("LOCAL_BASE_URL",       "http://127.0.0.1:8080/v1"),
        "model":            os.getenv("LLM_MODEL",            "openai/gpt-oss-20b"),
        "temperature":      float(os.getenv("LLM_TEMPERATURE",      "1.0")),
        "max_tokens":       int(os.getenv("LLM_MAX_TOKENS",         "16000")),
        "reasoning_effort": os.getenv("LLM_REASONING_EFFORT", "medium"),
        "timeout":          int(os.getenv("LLM_TIMEOUT",            "120")),
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


def local_base_urls() -> list[str]:
    """
    로컬 LLM 후보 base_url 목록(자동탐지 순서). 첫 healthy 서버를 채택한다.
    하드코딩 없이 .env 로만 구성한다:

    - LOCAL_BASE_URLS(콤마구분)가 있으면 그 목록을 순서대로(= 우선순위) 사용한다.
      예: gpt-oss(8080), exaone(8081) 두 엔드포인트를 모두 적어두면 분석 전
          health 체크로 살아있는 쪽을 자동 채택한다.
    - 없으면 단일 LOCAL_BASE_URL 만 후보로 쓴다(하위호환).
    """
    multi = os.getenv("LOCAL_BASE_URLS", "").strip()
    if multi:
        urls = [u.strip() for u in multi.split(",") if u.strip()]
        return list(dict.fromkeys(urls))
    return [os.getenv("LOCAL_BASE_URL", "http://127.0.0.1:8080/v1").strip()]


def probe_backend(base_url: str, connect: float = 3.0) -> str | None:
    """
    OpenAI 호환 서버 1개를 GET {base_url}/models 로 프로브한다.
    응답이 오면(=살아있음) 로딩된 model id(파싱 실패 시 빈 문자열)를, 접속 불가면
    None 을 반환한다. connect 타임아웃을 짧게 잡아 죽은 포트를 빠르게 넘긴다.
    """
    import httpx

    url = base_url.rstrip("/") + "/models"
    try:
        resp = httpx.get(url, timeout=httpx.Timeout(5.0, connect=connect))
    except httpx.RequestError:
        return None
    try:
        models = resp.json().get("data") or []
        return (models[0].get("id") or "") if models else ""
    except Exception:  # noqa: BLE001 - 살아있으나 모델 목록 파싱 실패
        return ""


def probe_local_backends(candidates: list[str] | None = None) -> tuple[str, str] | None:
    """
    후보 base_url 들을 순서대로 프로브해 첫 healthy 서버의 (base_url, model_id)를
    반환한다. 전부 접속 불가면 None. 첫 healthy 에서 멈추므로 8080 이 살아있으면
    8081 은 프로브하지 않는다(공통 경로 지연 없음).
    """
    for url in (candidates or local_base_urls()):
        model = probe_backend(url)
        if model is not None:
            return url, model
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
    # 자동탐지 후보. 실제 채택 base_url/model 은 preflight_local() 이 프로브로 주입.
    cfg["base_url_candidates"] = local_base_urls()
    cfg["provider"]          = provider
    cfg["claude_model"]      = c["model"]
    cfg["claude_max_tokens"] = c["max_tokens"]
    cfg["claude_api_key"]    = os.getenv("ANTHROPIC_API_KEY", "").strip()
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
