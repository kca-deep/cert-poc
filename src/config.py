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


def print_lm_config(cfg: dict, overrides: dict | None = None) -> None:
    """실행 시 적용 파라미터를 출력합니다. overrides 는 CLI 로 덮어쓴 항목."""
    overrides = overrides or {}
    lines = []
    for key in ("base_url", "model", "temperature", "max_tokens", "reasoning_effort",
                "timeout", "max_retries", "retry_delay"):
        val = cfg[key]
        src = "(CLI)" if key in overrides else "(.env)"
        lines.append(f"  {key}={val} {src}")
    print("[설정]")
    print("\n".join(lines))
