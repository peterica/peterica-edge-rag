"""프롬프트/모델 변형 평가 하네스.

사용 예:
  python -m scripts.prompt_eval \\
      --models exaone3.5:7.8b hf.co/DevQuasar/kakaocorp.kanana-1.5-8b-instruct-2505-GGUF:Q4_K_M \\
      --prompts v1 v2 v3

지표:
  CC (Citation Coverage): 문장별 `[#n]` 포함 비율, 1.0이 목표
  SR (Speculation Rate):  추측 키워드 포함 여부 (0이 목표)
  Refuse: 거부 응답("문서에 근거 없음") 여부 — OOD 질문에 true여야 정답
  Latency: LLM 응답 시간(초)
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
import time
from pathlib import Path

SERVER_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SERVER_DIR))

from rag import search_chunks  # noqa: E402
from llm import chat_complete, LlmError  # noqa: E402
from prompts import PROMPT_VARIANTS  # noqa: E402


CITATION_PATTERN = re.compile(r"\[#\d+\]")
SENTENCE_END = re.compile(r"(?<=[다요\?\!\.])\s+")
REFUSAL_PATTERN = re.compile(r"문서에\s*근거\s*없음")
CITATION_LEAD = re.compile(r"^\[#\d+\]")

HEDGE_PATTERNS = [
    re.compile(r"일반적(으로|인|\b)"),
    re.compile(r"보통(은|\b)"),
    re.compile(r"추측"),
    re.compile(r"아마(도)?"),
    re.compile(r"추정(하면|되|)"),
    re.compile(r"커뮤니티"),
    re.compile(r"경험상"),
    re.compile(r"상식적"),
    re.compile(r"흔히"),
    re.compile(r"대체로"),
]


def split_sentences_ko(text: str) -> list[str]:
    """종결어미/구두점 뒤 공백으로 문장 분리 후, 인용만 있는 꼬리 조각을 앞 문장에 병합."""
    pieces = [p.strip() for p in SENTENCE_END.split(text.strip()) if p.strip()]
    merged: list[str] = []
    for p in pieces:
        if CITATION_LEAD.match(p) and merged:
            merged[-1] = merged[-1] + " " + p
        else:
            merged.append(p)
    return merged


def measure_cc(text: str) -> float:
    sentences = split_sentences_ko(text)
    if not sentences:
        return 0.0
    cited = sum(1 for s in sentences if CITATION_PATTERN.search(s))
    return cited / len(sentences)


def measure_sr(text: str) -> bool:
    return any(p.search(text) for p in HEDGE_PATTERNS)


def is_refusal(text: str) -> bool:
    return bool(REFUSAL_PATTERN.search(text))


def normalize_v3_json(answer: str) -> tuple[str, bool]:
    """v3 JSON 응답을 일반 텍스트로 변환. (텍스트, 파싱성공여부)"""
    cleaned = answer.strip()
    # markdown fence 제거 fallback
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```\s*$", "", cleaned)

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        return answer, False

    if not data.get("grounded", False):
        return "문서에 근거 없음", True

    parts = []
    for s in data.get("sentences", []):
        text = s.get("text", "").strip()
        cites = s.get("cite", [])
        if not text:
            continue
        cite_str = "".join(f"[#{c}]" for c in cites) if cites else ""
        # 종결 구두점 앞에 인용 삽입 → 문장 분리 시 인용이 따라붙음
        trailing = ""
        while text and text[-1] in ".?!":
            trailing = text[-1] + trailing
            text = text[:-1]
        if not trailing:
            trailing = "."
        parts.append(f"{text.rstrip()} {cite_str}{trailing}".strip())
    return " ".join(parts), True


async def run_question(
    question: dict,
    model: str,
    prompt_version: str,
) -> dict:
    chunks = await search_chunks(question["q"])
    builder = PROMPT_VARIANTS[prompt_version]
    system_prompt = builder(chunks)

    started = time.perf_counter()
    try:
        raw = await chat_complete(system_prompt, question["q"], model=model)
    except LlmError as e:
        return {
            "question": question["q"],
            "model": model,
            "prompt": prompt_version,
            "error": str(e),
            "cc": 0.0,
            "sr": True,
            "refused": False,
            "latency_s": 0.0,
        }
    elapsed = time.perf_counter() - started

    json_variant = prompt_version in {"v3", "v4"}
    if json_variant:
        text, parsed = normalize_v3_json(raw)
    else:
        text, parsed = raw, True

    refused = is_refusal(text)
    cc = 1.0 if refused else measure_cc(text)
    sr = False if refused else measure_sr(text)

    return {
        "question": question["q"],
        "expected_ground": question["expected_ground"],
        "model": model,
        "prompt": prompt_version,
        "cc": cc,
        "sr": sr,
        "refused": refused,
        "latency_s": round(elapsed, 2),
        "json_parsed": parsed if json_variant else None,
        "answer_preview": text[:200],
    }


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--models", nargs="+", default=["exaone3.5:7.8b"])
    parser.add_argument("--prompts", nargs="+", default=["v1"])
    parser.add_argument(
        "--questions",
        default=str(SERVER_DIR / "scripts/test_questions.json"),
    )
    parser.add_argument("--output", default=None, help="결과 JSON 저장 경로")
    args = parser.parse_args()

    with open(args.questions, encoding="utf-8") as f:
        questions = json.load(f)

    results: list[dict] = []
    for model in args.models:
        for prompt in args.prompts:
            print(f"\n=== model={model} prompt={prompt} ===", flush=True)
            for q in questions:
                r = await run_question(q, model, prompt)
                results.append(r)
                marker = "R" if r["refused"] else f"CC={r['cc']:.2f}"
                sr_mark = "SR!" if r["sr"] else "   "
                print(
                    f"  [{marker:>7} {sr_mark}] {r['latency_s']:5.1f}s  {q['q'][:50]}",
                    flush=True,
                )

    # 집계
    print("\n=== SUMMARY ===")
    print(f"{'model':60} {'prompt':6} {'CC_mean':>8} {'SR_rate':>8} "
          f"{'Refuse_rate':>12} {'Correct_refuse':>14} {'p50_s':>6} {'errors':>7}")
    for model in args.models:
        for prompt in args.prompts:
            subset = [r for r in results if r["model"] == model and r["prompt"] == prompt]
            n = len(subset)
            cc_mean = sum(r["cc"] for r in subset) / n if n else 0.0
            sr_rate = sum(1 for r in subset if r["sr"]) / n if n else 0.0
            ref_rate = sum(1 for r in subset if r["refused"]) / n if n else 0.0
            correct_ref = sum(
                1 for r in subset
                if r["refused"] == (not r.get("expected_ground", True))
            ) / n if n else 0.0
            latencies = sorted(r["latency_s"] for r in subset if r["latency_s"])
            p50 = latencies[len(latencies) // 2] if latencies else 0.0
            errors = sum(1 for r in subset if "error" in r)
            print(
                f"{model[:60]:60} {prompt:6} {cc_mean:8.3f} {sr_rate:8.3f} "
                f"{ref_rate:12.3f} {correct_ref:14.3f} {p50:6.1f} {errors:7d}"
            )

    if args.output:
        Path(args.output).write_text(
            json.dumps(results, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"\n결과 저장: {args.output}")


if __name__ == "__main__":
    asyncio.run(main())
