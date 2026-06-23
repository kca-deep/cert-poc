"""
pipeline.py — holistic 단일호출 검출 파이프라인 (단일 소스).

★ 전면 대체: 기존 3레이어(L0 규칙 + L1 그룹LLM + L2 per-type LLM, 문항당 ~11콜)를
  폐기하고, cert-harness 외과적 v2 검출 코어로 **문항당 holistic 1콜**을 수행한다.
  출력은 llama.cpp native grammar(response_format=json_schema)로 강제된다.

흐름: '## N.' 문항 추출 → 문항별 holistic LLM 1콜(grammar 강제) → findings[] 정규화
      → results.json. 레이어 분기·규칙층·후처리 F필터는 존재하지 않는다.

run_pipeline()은 print 대신 ProgressEvent(core.events)를 yield 한다. CLI(src/cli.py)는
이를 콘솔 라인으로 출력하고, FastAPI(api/)는 그대로 JSON 직렬화해 SSE로 스트리밍한다.

주의:
  - print() / argparse / sys.exit 금지. 로직만.
  - sanitize()의 '>' 블록쿼트 치환은 gpt-oss garbage 버그 회피용으로 보존(폐쇄망
    기본은 gemma4 llama.cpp 라 영향 없음, 다른 로컬 모델 호환을 위해 유지).
  - OpenAI 클라이언트 max_retries=0 (내부 재시도 곱셈 방지) 보존.
"""

from __future__ import annotations

import json
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Iterator

# core 패키지 로드 시 src/ 가 sys.path 에 등록되므로 평면 모듈을 그대로 import 한다.
import core  # noqa: F401  (sys.path 셋업 트리거)

from config import build_config
from core.events import (
    ProgressEvent,
    Finding,
    start,
    q_start,
    q_done,
    done,
    error,
)

try:
    from openai import OpenAI
except ImportError:  # pragma: no cover - 런타임 의존성
    OpenAI = None  # type: ignore

ROOT       = Path(__file__).resolve().parent.parent.parent
PROMPT_DIR = ROOT / "prompts"

# holistic 검출 코어 자산
HOLISTIC_PROMPT = "holistic/review.md"
HOLISTIC_SYSTEM = "holistic/system.md"

# 출력 강제 grammar 를 지원하는 백엔드(response_format=json_schema → GBNF).
# Ollama 는 format=schema 단일호출에서 붕괴 이력(STATUS.md)이 있어 제외 → 폴백 파서.
_GRAMMAR_BACKENDS = {"openai"}  # llama.cpp / LM Studio 는 /models 응답으로 "openai" 로 잡힌다

# finding 필수 키 (출력 계약: _shared/output_schema.json)
_FINDING_KEYS = ("location", "quote", "error_type", "reason", "suggestion", "confidence")


# ── 공통 유틸 ─────────────────────────────────────────────────

def extract_question(md_text: str, n: int) -> str:
    m = re.search(rf"(## {n}\.\n[\s\S]*?)(?=\n## \d+\.|$)", md_text)
    if not m:
        raise ValueError(f"문항 {n}번을 찾을 수 없습니다.")
    return m.group(1).strip()


def extract_all_question_numbers(md_text: str) -> list[int]:
    return sorted(int(m) for m in re.findall(r"^## (\d+)\.", md_text, re.MULTILINE))


def sanitize(text: str) -> str:
    """'>' 마크다운 블록쿼트를 '(지문)'으로 치환 (gpt-oss-20b garbage 버그 회피)."""
    lines = []
    for line in text.splitlines():
        if line.startswith("> "):
            lines.append("(지문) " + line[2:])
        elif line == ">":
            lines.append("(지문)")
        else:
            lines.append(line)
    return "\n".join(lines)


def load_prompt(rel_path: str) -> str:
    return (PROMPT_DIR / rel_path).read_text(encoding="utf-8")


# ── LLM 호출 ──────────────────────────────────────────────────

class LMCallError(Exception):
    def __init__(self, msg: str, raw: str = ""):
        super().__init__(msg)
        self.raw = raw


def call_lm_studio(messages: list[dict], cfg: dict, slot_id: int = -1) -> dict:
    if OpenAI is None:
        raise LMCallError("openai 패키지가 필요합니다: pip install openai")
    import httpx
    # connect 와 read 타임아웃을 분리한다. 단일 timeout 이면 접속 불가 호스트가
    # connect 에서 통째로 대기해 파이프라인이 멈춘다(분석중 고착의 원인).
    timeout = httpx.Timeout(cfg["timeout"], connect=cfg.get("connect_timeout", 5))
    client = OpenAI(base_url=cfg["base_url"], api_key="lm-studio",
                    timeout=timeout, max_retries=0)
    extra: dict = {}
    backend = cfg.get("backend", "openai")
    # cache_prompt/slot_id 는 llama.cpp 전용 확장. Ollama 는 모르므로 비-ollama 만 전송.
    if backend != "ollama":
        extra["cache_prompt"] = cfg.get("cache_prompt", False)
        if slot_id >= 0:
            extra["slot_id"] = slot_id
    # holistic 출력 강제: response_format=json_schema 를 extra_body 로 요청 본문 최상위에
    # 합류시킨다(서버가 GBNF 로 변환·디코딩 마스킹). OpenAI SDK 타입검증을 우회하려고
    # 알려진 필드 대신 extra_body 경로를 쓴다. grammar 미지원 백엔드는 생략(폴백 파서).
    schema = cfg.get("response_schema")
    if schema and backend in _GRAMMAR_BACKENDS:
        extra["response_format"] = {
            "type": "json_schema",
            "json_schema": {"name": "review", "schema": schema},
        }
    # reasoning_effort 는 gpt-oss 계열만 지원. 다른 모델에 보내면 400 → gpt-oss 일 때만.
    if "gpt-oss" in (cfg.get("model") or "").lower():
        extra["reasoning_effort"] = cfg["reasoning_effort"]
    resp = client.chat.completions.create(
        model=cfg["model"], messages=messages,
        temperature=cfg["temperature"], max_tokens=cfg["max_tokens"],
        extra_body=extra,
    )
    raw = (resp.choices[0].message.content or "").strip()
    finish = resp.choices[0].finish_reason
    return _extract_json(raw, finish=finish)


def _loads_first_json(s: str) -> dict | None:
    """문자열에서 첫 JSON 값만 파싱한다 (뒤따르는 여분 데이터는 무시)."""
    starts = [i for i in (s.find("{"), s.find("[")) if i != -1]
    if not starts:
        return None
    try:
        obj, _ = json.JSONDecoder().raw_decode(s, min(starts))
        return obj if isinstance(obj, dict) else None
    except json.JSONDecodeError:
        return None


def _extract_json(raw: str, finish: str = "") -> dict:
    """LLM 응답 텍스트에서 JSON 본문을 추출/파싱한다 (grammar 미지원 공급자 폴백 포함)."""
    blocks = re.findall(r"```(?:json)?\s*([\s\S]+?)```", raw)
    candidates = blocks if blocks else [raw]
    last_error = None
    for candidate in reversed(candidates):
        candidate = candidate.strip()
        try:
            return json.loads(candidate)
        except json.JSONDecodeError as e:
            last_error = e
    clean = re.sub(r"^```(?:json)?\s*", "", raw)
    clean = re.sub(r"\s*```$", "", clean)
    try:
        return json.loads(clean)
    except json.JSONDecodeError as e:
        last_error = e

    for candidate in (*reversed(candidates), clean, raw):
        obj = _loads_first_json(candidate)
        if obj is not None:
            return obj

    raise LMCallError(
        f"JSON 파싱 실패 (finish={finish}): {last_error}", raw=raw[:2000]
    )


def call_claude(messages: list[dict], cfg: dict) -> dict:
    """Anthropic Claude(Haiku) 호출 (외부망 전용, grammar 미지원 → 폴백 파서 의존)."""
    try:
        import anthropic
    except ImportError:  # pragma: no cover - 런타임 의존성
        raise LMCallError("anthropic 패키지가 필요합니다: pip install anthropic")

    api_key = cfg.get("claude_api_key") or None  # None 이면 SDK 가 환경변수 사용
    client = anthropic.Anthropic(api_key=api_key, max_retries=0)

    system = "\n\n".join(m["content"] for m in messages if m["role"] == "system")
    convo = [{"role": m["role"], "content": m["content"]}
             for m in messages if m["role"] != "system"]

    kwargs: dict = {
        "model":      cfg["claude_model"],
        "max_tokens": cfg["claude_max_tokens"],
        "messages":   convo,
    }
    if system:
        kwargs["system"] = system

    resp = client.messages.create(**kwargs)
    raw = "".join(
        getattr(b, "text", "") for b in resp.content
        if getattr(b, "type", None) == "text"
    ).strip()
    return _extract_json(raw, finish=getattr(resp, "stop_reason", "") or "")


# ── findings 정규화 ───────────────────────────────────────────

def _str(v: object) -> str:
    return v if isinstance(v, str) else ("" if v is None else str(v))


def _normalize_findings(obj: dict, q: int) -> list[Finding]:
    """
    holistic LLM 응답(dict)의 findings[] 를 출력 계약(camelCase)에 맞춰 교정한다.

    - error_type → errorType 로 카멜화, 누락/비-str 키는 str 강제.
    - id = "<q>-<index>" (세션 내 안정 식별자, 검수 finding 단위 PK).
    - location/quote 가 모두 비면 드롭(빈 finding 방어). grammar 강제 시엔 거의 없음.
    """
    raw = obj.get("findings") if isinstance(obj, dict) else None
    if not isinstance(raw, list):
        return []
    out: list[Finding] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        f: Finding = {
            "id":         f"{q}-{len(out)}",
            "location":   _str(item.get("location")),
            "quote":      _str(item.get("quote")),
            "errorType":  _str(item.get("error_type") or item.get("errorType") or "기타"),
            "reason":     _str(item.get("reason")),
            "suggestion": _str(item.get("suggestion")),
            "confidence": _str(item.get("confidence") or "보통"),
        }
        if not f["location"] and not f["quote"] and not f["reason"]:
            continue
        out.append(f)
    return out


def call_with_retry(messages: list[dict], cfg: dict, slot_id: int = -1) -> dict | None:
    max_retries = cfg["max_retries"]
    retry_delay = cfg["retry_delay"]
    provider = cfg.get("provider")
    for attempt in range(max_retries + 1):
        try:
            if provider == "claude":
                return call_claude(messages, cfg)
            return call_lm_studio(messages, cfg, slot_id=slot_id)
        except LMCallError as e:
            if attempt < max_retries:
                time.sleep(retry_delay)
            else:
                return {"_error": str(e), "_raw": e.raw}
        except Exception as e:
            if attempt < max_retries:
                time.sleep(retry_delay)
            else:
                return {"_error": str(e), "_raw": ""}


# ── 사전 헬스체크 (preflight) ─────────────────────────────────

def preflight_local(cfg: dict) -> str | None:
    """
    로컬 LLM 후보를 자동탐지하고 cfg 에 채택 백엔드/모델을 주입한다.

    base_url_candidates 를 순서대로 프로브해 첫 healthy 서버의 base_url·모델을
    cfg 에 덮어쓰고 None 을 반환한다. 전부 접속 불가면 에러 메시지를 반환한다.
    이 검사로 unreachable 서버에서 분석을 시작해 '분석중'에 고착되는 것을 막는다.
    """
    from config import probe_local_backends

    candidates = cfg.get("base_url_candidates") or [cfg["base_url"]]
    resolved = probe_local_backends(candidates)
    if resolved is None:
        return (
            f"로컬 LLM 서버에 접속할 수 없습니다 ({', '.join(candidates)}). "
            f"llama.cpp(8080) 서버 실행 여부를 확인하세요."
        )
    cfg["base_url"] = resolved["base_url"]
    cfg["backend"] = resolved.get("backend", "openai")
    if resolved.get("model"):  # 살아있는 서버가 보고한 실제 모델 id 채택(.env 값보다 우선)
        cfg["model"] = resolved["model"]
    return None


# ── 저장 헬퍼 ─────────────────────────────────────────────────

def _save(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


# ── 문항 1개 holistic 처리 ────────────────────────────────────

def _build_messages(md_text: str, q: int, system: str, prompt: str) -> list[dict]:
    qblock  = extract_question(md_text, q)
    content = sanitize(prompt).replace("{{QUESTION_BLOCK}}", sanitize(qblock))
    return [{"role": "system", "content": system},
            {"role": "user",   "content": content}]


def _process_question(md_text: str, q: int, system: str, prompt: str, cfg: dict,
                      slot_id: int) -> tuple[int, list[Finding], dict]:
    """문항 1개를 holistic 호출하고 (q, findings, raw_result) 를 반환한다."""
    try:
        msgs = _build_messages(md_text, q, system, prompt)
    except Exception as e:  # noqa: BLE001 - 문항 추출 실패도 q 단위로 격리
        return q, [], {"_error": str(e)}
    result = call_with_retry(msgs, cfg, slot_id=slot_id) or {}
    if "_error" in result:
        return q, [], result
    findings = _normalize_findings(result, q)
    return q, findings, {"has_error": bool(result.get("has_error", bool(findings))),
                         "findings": findings}


# ── 메인 제너레이터 ───────────────────────────────────────────

def run_pipeline(md_text: str, result_dir: Path, q_filter: int | None = None,
                 reset: bool = False,
                 provider: str | None = None) -> Iterator[ProgressEvent]:
    """
    holistic 파이프라인을 실행하며 ProgressEvent 를 yield 한다.

    Args:
        md_text:    '## N.' 형식 시험지 Markdown 전체 텍스트.
        result_dir: 결과 저장 디렉터리 (holistic/Q*.json, results.json).
        q_filter:   특정 문항 번호만 처리 (None이면 전체).
        reset:      기존 결과를 지우고 다시 실행.
        provider:   LLM 공급자 (미지정 시 .env LLM_PROVIDER).

    Yields:
        ProgressEvent (core.events): start / q_done / done / error.
    """
    t_start = time.time()
    try:
        cfg = build_config(provider)

        # 사전 헬스체크: 로컬 LLM 이 닿지 않으면 분석을 시작하지 않고 즉시 error.
        if cfg.get("provider") == "local":
            msg = preflight_local(cfg)
            if msg:
                yield error(msg)
                return

        result_dir = Path(result_dir)
        out_dir = result_dir / "holistic"
        out_dir.mkdir(parents=True, exist_ok=True)

        all_questions = extract_all_question_numbers(md_text)
        questions = [q_filter] if q_filter is not None else all_questions
        system = load_prompt(HOLISTIC_SYSTEM)
        prompt = load_prompt(HOLISTIC_PROMPT)

        yield start(len(questions))

        n_slots = cfg.get("n_slots", 4)
        # local 에서만 병렬; claude 는 레이트리밋 고려해 직렬 유지.
        max_workers = cfg.get("parallel_workers", 1) if cfg.get("provider") == "local" else 1

        results: dict[str, dict] = {}
        total_found = 0

        # 캐시 재사용: reset 아니고 기존 결과가 있으면 즉시 흘린다.
        pending: list[int] = []
        for i, q in enumerate(questions):
            cache = out_dir / f"Q{q:02d}.json"
            if not reset and cache.exists():
                try:
                    r = json.loads(cache.read_text(encoding="utf-8"))
                    findings = r.get("findings", [])
                    results[str(q)] = r
                    total_found += len(findings)
                    yield q_done(q, findings, bool(r.get("has_error", bool(findings))))
                    continue
                except Exception:  # noqa: BLE001 - 깨진 캐시는 재처리
                    pass
            pending.append(q)

        if pending:
            # 워커 스레드는 generator 에서 직접 yield 할 수 없으므로, 스레드 안전 큐로
            # 이벤트를 main 스레드(generator)에 전달한다. 워커는 문항을 집어드는 즉시
            # ("start") 를 넣어 active 표시를 즉발시키고(=시작 직후 멈춤 현상 제거),
            # 끝나면 ("done", 결과) 를 넣는다. 동시 실행 수는 max_workers(=서버 슬롯) 만큼.
            import queue as _queue
            evq: _queue.Queue = _queue.Queue()

            # 논리 레인 풀: 동시에 도는 워커를 0..max_workers-1 로 식별(web 에서 agentA/B/C).
            # 풀 크기 == 스레드 수라 get() 데드락 없음(스레드당 레인 1개만 보유).
            lane_pool: _queue.Queue = _queue.Queue()
            for _lane in range(max(1, max_workers)):
                lane_pool.put(_lane)

            def _job(qn: int) -> None:
                lane = lane_pool.get()  # 워커가 작업을 집어드는 시점에 레인 점유
                evq.put(("start", qn, (lane, None)))
                slot = lane if cfg.get("slot_round_robin", False) else -1
                try:
                    res = _process_question(md_text, qn, system, prompt, cfg, slot)
                except Exception as e:  # noqa: BLE001 - 어떤 실패든 done 으로 격리(행 방지)
                    res = (qn, [], {"_error": str(e)})
                evq.put(("done", qn, res))
                # ★레인은 done 을 emit 한 "뒤"에 반납 → 다음 워커의 q_start 가 항상
                #   이 q_done 뒤에 오게 보장(같은 레인을 두 문항이 동시 점유하는 프레임 차단).
                lane_pool.put(lane)

            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                for q in pending:
                    executor.submit(_job, q)

                remaining = len(pending)
                while remaining > 0:
                    kind, qn, payload = evq.get()
                    if kind == "start":
                        lane, _ = payload
                        yield q_start(qn, worker=lane)
                        continue
                    remaining -= 1
                    q, findings, raw = payload
                    if "_error" in raw:
                        _save(out_dir / f"Q{q:02d}_ERROR.json",
                              {"question_number": q, "_error": raw["_error"],
                               "_raw": raw.get("_raw", "")})
                        yield q_done(q, [], False, error=raw.get("_error") or "검토 실패")
                        continue
                    record = {"question_number": q,
                              "has_error": raw["has_error"],
                              "findings": findings}
                    _save(out_dir / f"Q{q:02d}.json", record)
                    results[str(q)] = record
                    total_found += len(findings)
                    yield q_done(q, findings, raw["has_error"])

        # 집계 결과 저장 (검수/내보내기용 단일 산출물)
        merged = {str(q): results.get(str(q), {"question_number": q,
                                               "has_error": False, "findings": []})
                  for q in sorted(questions)}
        (result_dir / "results.json").write_text(
            json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        yield done(total_found, round(time.time() - t_start, 1))

    except Exception as e:  # noqa: BLE001 - 어떤 치명적 오류든 error 이벤트로 전달
        yield error(str(e))
