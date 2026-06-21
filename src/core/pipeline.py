"""
pipeline.py — 3레이어 하이브리드 파이프라인 로직 (단일 소스).

run_pipeline()은 hybrid_run.main()이 하던 것과 동일한 작업을 수행한다:
Layer 0 (코드) → Layer 1 (그룹 LLM) → Layer 2 (per-type LLM) → 병합 → 후처리.

단, print 대신 ProgressEvent를 yield 한다. CLI(src/cli.py)는 이를 받아 콘솔에
출력하고, FastAPI(api/)는 그대로 JSON 직렬화해 SSE로 스트리밍한다.

★ 로직은 여기 한 곳에만 존재한다 (single source of truth).
  hybrid_run.py는 cli.py를 호출하는 back-compat 얇은 shim일 뿐이다.

주의:
  - print() / argparse / sys.exit 금지. 로직만.
  - run_code_check()는 파일 경로를 받으므로, md_text를 임시 .md로 써서 호출한다.
  - sanitize()의 '>' 블록쿼트 치환, max_retries 처리, slot round-robin 보존.
"""

from __future__ import annotations

import json
import re
import tempfile
import time
from pathlib import Path
from typing import Iterator

# core 패키지 로드 시 src/ 가 sys.path 에 등록되므로 평면 모듈을 그대로 import 한다.
import core  # noqa: F401  (sys.path 셋업 트리거)

from config import lm_config, build_config
from code_checker import run_code_check, extract_all_questions  # noqa: F401
from postprocess import apply_filters
from core.events import (
    ProgressEvent,
    layer_start,
    q_layer0_done,
    q_type_done,
    layer_done,
    postprocess,
    done,
    error,
)

try:
    from openai import OpenAI
except ImportError:  # pragma: no cover - 런타임 의존성
    OpenAI = None  # type: ignore

ROOT       = Path(__file__).resolve().parent.parent.parent
PROMPT_DIR = ROOT / "prompts"


# ── 레이어 정의 ───────────────────────────────────────────────

LAYER0_TYPES = {"A01", "A03", "A13", "A15", "A17", "A18"}

LAYER1_GROUPS = [
    {"code": "G1", "file": "hybrid/G1_typo_spelling.md",  "types": ["A04", "A05", "A06"]},
    {"code": "G4", "file": "hybrid/G4_legal_domain.md",   "types": ["A09", "A20"]},
    {"code": "G5", "file": "hybrid/G5_editorial.md",      "types": ["A11", "A14"]},
]

LAYER2_TYPES = ["A02", "A07", "A08", "A10", "A12", "A16", "A19", "A21"]


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


def load_preamble() -> str:
    return (PROMPT_DIR / "_shared" / "system_preamble.md").read_text(encoding="utf-8")


def load_pertype_prompt(code: str) -> str:
    matches = list((PROMPT_DIR / "per-type").glob(f"{code}_*.md"))
    if not matches:
        raise FileNotFoundError(f"per-type 프롬프트 없음: {code}_*.md")
    return matches[0].read_text(encoding="utf-8")


# ── LLM 호출 ──────────────────────────────────────────────────

class LMCallError(Exception):
    def __init__(self, msg: str, raw: str = ""):
        super().__init__(msg)
        self.raw = raw


def call_lm_studio(messages: list[dict], cfg: dict, slot_id: int = -1) -> dict:
    if OpenAI is None:
        raise LMCallError("openai 패키지가 필요합니다: pip install openai")
    import httpx
    # connect 와 read 타임아웃을 분리한다. 단일 timeout(120s)이면 접속 불가 호스트가
    # connect 에서 120s 를 통째로 대기해 파이프라인이 사실상 멈춘다(분석중 고착의 원인).
    # connect 를 짧게(기본 5s) 잡아 unreachable 을 빠르게 LMCallError 로 떨군다.
    timeout = httpx.Timeout(cfg["timeout"], connect=cfg.get("connect_timeout", 5))
    client = OpenAI(base_url=cfg["base_url"], api_key="lm-studio",
                    timeout=timeout, max_retries=0)
    extra: dict = {}
    # cache_prompt/slot_id 는 llama.cpp 전용 확장이다. Ollama 는 이를 모르고
    # (clova 처럼) 보내면 안 되므로 backend != "ollama" 일 때만 전송한다.
    if cfg.get("backend") != "ollama":
        extra["cache_prompt"] = cfg.get("cache_prompt", False)
        if slot_id >= 0:
            extra["slot_id"] = slot_id
    # reasoning_effort 는 gpt-oss 계열만 지원한다. Ollama 등 다른 서버는 이 값을
    # "thinking 활성화"로 해석해, exaone 처럼 thinking 미지원 모델에 보내면
    # 400("does not support thinking")으로 거부한다 → gpt-oss 일 때만 전송한다.
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


def call_clova(messages: list[dict], cfg: dict) -> dict:
    """
    Naver HyperCLOVA X(CLOVA Studio) 호출. CLOVA Studio 는 OpenAI 호환이라 동일한
    OpenAI 클라이언트를 쓰되, base_url 과 'nv-' Bearer 키가 다르고 llama.cpp 전용
    extra_body(reasoning_effort/cache_prompt/slot_id)는 보내지 않는다.
    """
    if OpenAI is None:
        raise LMCallError("openai 패키지가 필요합니다: pip install openai")
    import httpx

    api_key = cfg.get("clova_api_key")
    if not api_key:
        raise LMCallError("CLOVASTUDIO_API_KEY 가 설정되지 않았습니다.")
    timeout = httpx.Timeout(cfg["timeout"], connect=cfg.get("connect_timeout", 5))
    client = OpenAI(base_url=cfg["clova_base_url"], api_key=api_key,
                    timeout=timeout, max_retries=0)
    resp = client.chat.completions.create(
        model=cfg["clova_model"], messages=messages,
        temperature=cfg["temperature"], max_tokens=cfg["clova_max_tokens"],
    )
    raw = (resp.choices[0].message.content or "").strip()
    finish = resp.choices[0].finish_reason
    return _extract_json(raw, finish=finish)


def _loads_first_json(s: str) -> dict | None:
    """
    문자열에서 첫 JSON 값만 파싱한다 (뒤따르는 여분 데이터는 무시).

    Claude(Haiku)가 유효한 JSON 뒤에 설명/중복 객체를 덧붙여 반환하면
    json.loads 는 'Extra data' 로 실패한다. raw_decode 는 첫 값만 디코딩하고
    이후 텍스트를 버리므로 이 패턴을 구제한다. 파싱 불가면 None.
    """
    starts = [i for i in (s.find("{"), s.find("[")) if i != -1]
    if not starts:
        return None
    try:
        obj, _ = json.JSONDecoder().raw_decode(s, min(starts))
        return obj if isinstance(obj, dict) else None
    except json.JSONDecodeError:
        return None


def _extract_json(raw: str, finish: str = "") -> dict:
    """LLM 응답 텍스트에서 JSON 본문을 추출/파싱한다 (local/claude 공용)."""
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

    # 마지막 관용 파싱: 첫 JSON 값만 디코딩 (Haiku 의 'Extra data' 패턴 구제).
    for candidate in (*reversed(candidates), clean, raw):
        obj = _loads_first_json(candidate)
        if obj is not None:
            return obj

    raise LMCallError(
        f"JSON 파싱 실패 (finish={finish}): {last_error}", raw=raw[:2000]
    )


def call_claude(messages: list[dict], cfg: dict) -> dict:
    """Anthropic Claude(Haiku) 호출. system/user 메시지를 분리해 전송한다."""
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


_ISSUE_REQUIRED = ("location", "original", "suspected")


def _normalize_issue(raw: object) -> dict | None:
    """
    LLM issue 1건을 출력 계약(output_schema)에 맞춰 교정한다(저장 전 방어).

    - extra: dict 가 아니면(문자열 등) {'note': str} 로 감싸고, 빈값은 None.
      (읽기 단계 pydantic Issue.extra: dict|None 거부로 GET 500 나던 결함 차단)
    - location/original/suspected: 비-str 이면 str() 강제.
    - 필수 3키가 없으면 드롭(None). 미지의 보조키는 보존(차수 일반화).
    """
    if not isinstance(raw, dict):
        return None
    out = dict(raw)
    if "extra" in out:
        ex = out["extra"]
        if ex is None or isinstance(ex, dict):
            out["extra"] = ex
        else:
            s = str(ex).strip()
            out["extra"] = {"note": s} if s else None
    for k in _ISSUE_REQUIRED:
        if k in out and not isinstance(out[k], str):
            out[k] = str(out[k])
    return out if all(k in out for k in _ISSUE_REQUIRED) else None


def _normalize_issues(issues: object) -> list[dict]:
    """issues 배열을 정규화한다. list 가 아니면 빈 배열, 깨진 issue 는 제거."""
    if not isinstance(issues, list):
        return []
    return [n for n in (_normalize_issue(i) for i in issues) if n is not None]


def _normalize_result(obj: dict) -> dict:
    """
    LLM 응답 dict 의 issues 를 정규화한다. Layer2(top-level issues)와
    Layer1(results[].issues) 두 형태를 모두 처리한다(local/claude 공통).
    """
    if not isinstance(obj, dict) or "_error" in obj:
        return obj
    if "issues" in obj:
        obj["issues"] = _normalize_issues(obj["issues"])
    subs = obj.get("results")
    if isinstance(subs, list):
        for sub in subs:
            if isinstance(sub, dict) and "issues" in sub:
                sub["issues"] = _normalize_issues(sub["issues"])
    return obj


def call_with_retry(messages: list[dict], label: str, cfg: dict,
                    slot_id: int = -1) -> dict | None:
    max_retries = cfg["max_retries"]
    retry_delay = cfg["retry_delay"]
    provider = cfg.get("provider")
    for attempt in range(max_retries + 1):
        try:
            if provider == "claude":
                return _normalize_result(call_claude(messages, cfg))
            if provider == "clovax":
                return _normalize_result(call_clova(messages, cfg))
            return _normalize_result(call_lm_studio(messages, cfg, slot_id=slot_id))
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
    로컬 LLM 후보(8080/8081 등)를 자동탐지하고 cfg 에 채택 백엔드를 주입한다.

    base_url_candidates 를 순서대로 프로브해 첫 healthy 서버의 base_url 과 실제
    로딩 모델을 cfg["base_url"]/cfg["model"] 에 덮어쓰고 None 을 반환한다. 전부
    접속 불가면 사람이 읽을 에러 메시지를 반환한다. 이 검사로 unreachable 한
    서버에서 분석을 시작했다가 매 LLM 호출이 connect 타임아웃까지 블로킹돼
    '분석중'에 고착되는 것을 막는다(시작 즉시 error 처리).
    """
    from config import probe_local_backends

    candidates = cfg.get("base_url_candidates") or [cfg["base_url"]]
    resolved = probe_local_backends(candidates)
    if resolved is None:
        return (
            f"로컬 LLM 서버에 접속할 수 없습니다 ({', '.join(candidates)}). "
            f"gpt-oss(8080)/exaone(8081) 서버 실행 여부를 확인하세요."
        )
    cfg["base_url"] = resolved["base_url"]
    cfg["backend"] = resolved.get("backend", "openai")
    if resolved.get("model"):  # 살아있는 서버가 보고한 실제 모델 id 채택(.env 값보다 우선)
        cfg["model"] = resolved["model"]
    return None


# ── 저장 헬퍼 ─────────────────────────────────────────────────

def _save(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _already_done(result_dir: Path, label: str) -> bool:
    return (result_dir / f"{label}.json").exists() or \
           (result_dir / f"{label}_ERROR.json").exists()


# ── Layer 0 실행 (코드, LLM 불필요) ───────────────────────────

def _run_layer0(md_path: Path, result_dir: Path, q_filter: int | None,
                reset: bool) -> Iterator[ProgressEvent]:
    layer_dir = result_dir / "layer0"
    layer_dir.mkdir(parents=True, exist_ok=True)

    if reset:
        pattern = f"Q{q_filter:02d}_*.json" if q_filter else "*.json"
        for f in layer_dir.glob(pattern):
            f.unlink()

    results = run_code_check(md_path, q_filter=q_filter, output_dir=layer_dir)

    # 문항별로 묶어서 q_layer0_done 이벤트 생성
    by_q: dict[int, dict[str, bool]] = {}
    for r in results:
        q = r.get("question_number")
        t = r.get("type_code")
        if q is not None and t:
            by_q.setdefault(int(q), {})[t] = bool(r.get("found"))

    for q in sorted(by_q):
        yield q_layer0_done(q, by_q[q])

    found = sum(1 for r in results if r.get("found"))
    yield layer_done(0, found)


# ── Layer 1 실행 (그룹 LLM) ───────────────────────────────────

def _run_layer1(md_text: str, questions: list[int], result_dir: Path,
                q_filter: int | None, reset: bool, preamble: str,
                cfg: dict) -> Iterator[ProgressEvent]:
    layer_dir = result_dir / "layer1"
    layer_dir.mkdir(parents=True, exist_ok=True)

    if reset and q_filter:
        for f in layer_dir.glob(f"Q{q_filter:02d}_*.json"):
            f.unlink()

    pairs = [(q, g) for q in questions for g in LAYER1_GROUPS
             if q_filter is None or q == q_filter]

    found_total = 0
    n_slots = cfg.get("n_slots", 4)

    for i, (q_num, grp) in enumerate(pairs, 1):
        label = f"Q{q_num:02d}_{grp['code']}"
        if not reset and _already_done(layer_dir, label):
            # 스킵: 기존 결과에서 found 유형을 읽어 이벤트 재생산
            existing = layer_dir / f"{label}.json"
            if existing.exists():
                r = json.loads(existing.read_text(encoding="utf-8"))
                for sub in r.get("results", []):
                    t = sub.get("type_code")
                    if t:
                        f = bool(sub.get("found"))
                        if f:
                            found_total += 1
                        yield q_type_done(1, q_num, t, f, sub.get("confidence"))
            continue

        try:
            prompt  = load_prompt(grp["file"])
            qblock  = extract_question(md_text, q_num)
            content = sanitize(prompt).replace("{{QUESTION_BLOCK}}", sanitize(qblock))
            msgs    = [{"role": "system", "content": preamble},
                       {"role": "user",   "content": content}]
        except Exception as e:
            _save(layer_dir / f"{label}_ERROR.json",
                  {"question_number": q_num, "group_code": grp["code"], "_error": str(e)})
            continue

        slot_id = (i - 1) % n_slots if cfg.get("slot_round_robin", False) else -1
        result  = call_with_retry(msgs, label, cfg, slot_id=slot_id)

        if result and "_error" in result:
            _save(layer_dir / f"{label}_ERROR.json",
                  {"question_number": q_num, "group_code": grp["code"],
                   "_error": result["_error"], "_raw": result.get("_raw", "")})
        else:
            _save(layer_dir / f"{label}.json", result)
            for sub in result.get("results", []):
                t = sub.get("type_code")
                if t:
                    f = bool(sub.get("found"))
                    if f:
                        found_total += 1
                    yield q_type_done(1, q_num, t, f, sub.get("confidence"))

    yield layer_done(1, found_total)


# ── Layer 2 실행 (per-type LLM) ───────────────────────────────

def _run_layer2(md_text: str, questions: list[int], result_dir: Path,
                q_filter: int | None, reset: bool, preamble: str,
                cfg: dict) -> Iterator[ProgressEvent]:
    layer_dir = result_dir / "layer2"
    layer_dir.mkdir(parents=True, exist_ok=True)

    if reset and q_filter:
        for f in layer_dir.glob(f"Q{q_filter:02d}_*.json"):
            f.unlink()

    pairs = [(q, t) for q in questions for t in LAYER2_TYPES
             if q_filter is None or q == q_filter]

    found_total = 0
    n_slots = cfg.get("n_slots", 4)

    for i, (q_num, type_code) in enumerate(pairs, 1):
        label = f"Q{q_num:02d}_{type_code}"
        if not reset and _already_done(layer_dir, label):
            existing = layer_dir / f"{label}.json"
            if existing.exists():
                r = json.loads(existing.read_text(encoding="utf-8"))
                f = bool(r.get("found"))
                if f:
                    found_total += 1
                yield q_type_done(2, q_num, type_code, f, r.get("confidence"))
            continue

        try:
            prompt  = load_pertype_prompt(type_code)
            qblock  = extract_question(md_text, q_num)
            content = sanitize(prompt).replace("{{QUESTION_BLOCK}}", sanitize(qblock))
            msgs    = [{"role": "system", "content": preamble},
                       {"role": "user",   "content": content}]
        except Exception as e:
            _save(layer_dir / f"{label}_ERROR.json",
                  {"question_number": q_num, "type_code": type_code, "_error": str(e)})
            continue

        slot_id = (i - 1) % n_slots if cfg.get("slot_round_robin", False) else -1
        result  = call_with_retry(msgs, label, cfg, slot_id=slot_id)

        if result and "_error" in result:
            _save(layer_dir / f"{label}_ERROR.json",
                  {"question_number": q_num, "type_code": type_code,
                   "_error": result["_error"], "_raw": result.get("_raw", "")})
        else:
            _save(layer_dir / f"{label}.json", result)
            f = bool(result.get("found", False))
            if f:
                found_total += 1
            yield q_type_done(2, q_num, type_code, f, result.get("confidence"))

    yield layer_done(2, found_total)


# ── 결과 병합 ─────────────────────────────────────────────────

def _merge(result_dir: Path, questions: list[int]) -> dict:
    """layer0/1/2 결과 JSON을 {q: {type_code: result}} 로 병합하고 merged.json 저장."""
    merged: dict[int, dict[str, dict]] = {int(q): {} for q in questions}

    # Layer 0
    for f in (result_dir / "layer0").glob("Q*_A*.json"):
        if "_ERROR" in f.name:
            continue
        r = json.loads(f.read_text(encoding="utf-8"))
        q, t = r.get("question_number"), r.get("type_code")
        if q and t:
            merged.setdefault(int(q), {})[t] = r

    # Layer 1 (그룹 → 개별 유형으로 펼치기)
    for f in (result_dir / "layer1").glob("Q*_G*.json"):
        if "_ERROR" in f.name:
            continue
        r = json.loads(f.read_text(encoding="utf-8"))
        q = r.get("question_number")
        for sub in r.get("results", []):
            t = sub.get("type_code")
            if q and t:
                merged.setdefault(int(q), {})[t] = sub

    # Layer 2
    for f in (result_dir / "layer2").glob("Q*_A*.json"):
        if "_ERROR" in f.name:
            continue
        r = json.loads(f.read_text(encoding="utf-8"))
        q, t = r.get("question_number"), r.get("type_code")
        if q and t:
            merged.setdefault(int(q), {})[t] = r

    merged_out = {str(q): v for q, v in sorted(merged.items())}
    (result_dir / "merged.json").write_text(
        json.dumps(merged_out, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return merged_out


# ── 메인 제너레이터 ───────────────────────────────────────────

def run_pipeline(md_text: str, result_dir: Path, q_filter: int | None = None,
                 reset: bool = False,
                 provider: str | None = None) -> Iterator[ProgressEvent]:
    """
    3레이어 하이브리드 파이프라인을 실행하며 ProgressEvent를 yield 한다.

    Args:
        md_text:    '## N.' 형식 시험지 Markdown 전체 텍스트.
        result_dir: 결과 저장 디렉터리 (layer0/layer1/layer2/merged*.json).
        q_filter:   특정 문항 번호만 처리 (None이면 전체).
        reset:      기존 결과를 지우고 다시 실행.

    Yields:
        ProgressEvent (core.events): layer_start / q_layer0_done / q_type_done /
        layer_done / postprocess / done / error.
    """
    t_start = time.time()
    try:
        cfg = build_config(provider)

        # 사전 헬스체크: 로컬 LLM 이 닿지 않으면 분석을 시작하지 않고 즉시 error.
        # (claude/clovax 는 외부 API 라 여기서 localhost 프로브를 하지 않는다.)
        if cfg.get("provider") == "local":
            msg = preflight_local(cfg)
            if msg:
                yield error(msg)
                return

        result_dir = Path(result_dir)
        result_dir.mkdir(parents=True, exist_ok=True)

        questions = extract_all_question_numbers(md_text)
        preamble  = load_preamble()

        # run_code_check()는 파일 경로를 받으므로 md_text를 임시 파일로 기록한다.
        tmp = tempfile.NamedTemporaryFile(
            mode="w", suffix=".md", encoding="utf-8", delete=False
        )
        try:
            tmp.write(md_text)
            tmp.close()
            md_path = Path(tmp.name)

            # ── Layer 0 ──
            total_q = len(questions) if q_filter is None else 1
            yield layer_start(0, total_q)
            yield from _run_layer0(md_path, result_dir, q_filter, reset)

            # ── Layer 1 ──
            yield layer_start(1, total_q)
            yield from _run_layer1(md_text, questions, result_dir,
                                   q_filter, reset, preamble, cfg)

            # ── Layer 2 ──
            yield layer_start(2, total_q)
            yield from _run_layer2(md_text, questions, result_dir,
                                   q_filter, reset, preamble, cfg)
        finally:
            try:
                md_path.unlink()
            except OSError:
                pass

        # ── 병합 ──
        merged = _merge(result_dir, questions)

        # ── 후처리 필터 ──
        filtered, log = apply_filters(merged)
        (result_dir / "merged_filtered.json").write_text(
            json.dumps(filtered, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        yield postprocess(len(log))

        # ── 최종 집계 (필터 적용 후 found 건수) ──
        total_found = 0
        for q_results in filtered.values():
            for r in q_results.values():
                if r.get("found") is True:
                    total_found += 1

        yield done(total_found, round(time.time() - t_start, 1))

    except Exception as e:  # noqa: BLE001 - 어떤 치명적 오류든 error 이벤트로 전달
        yield error(str(e))
