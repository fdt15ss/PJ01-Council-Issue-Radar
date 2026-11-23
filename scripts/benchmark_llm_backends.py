"""RNGD(NPU) / GPU LLM 백엔드를 의정이슈레이더의 실제 프롬프트(RAG 답변·질문 해석)로 비교한다.

모든 백엔드는 각 머신 안의 127.0.0.1 OpenAI 호환 /v1 스트리밍으로만 측정한다(회의록 근거를 외부로 보내지 않는다).
설정·지표 정의·측정 절차는 benchmarks/README.md 를 본다.

예시:
    python scripts/benchmark_llm_backends.py --dry-run
    python scripts/benchmark_llm_backends.py --backends home-ollama-qwen3-8b --runs 10 --concurrency 1         --max-tokens 600 --label home-qwen3-8b-c1
"""

from __future__ import annotations

import argparse
import sys
import tomllib
from datetime import datetime
from pathlib import Path

from urllib.parse import urlparse

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from benchmark.measure import BackendTarget, run_batch, summarize_batch  # noqa: E402
from benchmark.report import render_markdown, write_report  # noqa: E402
from benchmark.scenarios import build_scenarios  # noqa: E402

# agent/local_issue_agent.py LOCAL_HOSTS 와 같은 정책: 회의록 근거가 든 프롬프트는 localhost로만 보낸다.
LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}


def main() -> None:
    args = parse_args()
    scenarios = build_scenarios()
    if args.scenarios:
        unknown = [name for name in _split(args.scenarios) if name not in scenarios]
        if unknown:
            raise SystemExit(f"알 수 없는 시나리오: {unknown}. 가능한 값: {', '.join(scenarios)}")
        scenarios = {name: scenarios[name] for name in _split(args.scenarios)}

    if args.dry_run:
        for name, messages in scenarios.items():
            chars = sum(len(message["content"]) for message in messages)
            print(f"{name}: messages={len(messages)} chars={chars}")
        return

    targets = load_targets(args.config, args.backends)
    from openai import OpenAI  # --dry-run 은 openai 없이도 돌도록 여기서 import

    started_at = datetime.now()
    batches = []
    summaries = []
    for target in targets:
        client = OpenAI(base_url=target.base_url, api_key=target.api_key(), timeout=args.timeout, max_retries=0)
        for name, messages in scenarios.items():
            print(f"[{target.name}] {name}: warmup {args.warmup}, runs {args.runs}, concurrency {args.concurrency}")
            for _ in range(args.warmup):
                run_batch(
                    client, target, name, messages, runs=1, concurrency=1, max_tokens=args.max_tokens,
                    unique_prefix=args.unique_prefix,
                )
            batch = run_batch(
                client,
                target,
                name,
                messages,
                runs=args.runs,
                concurrency=args.concurrency,
                max_tokens=args.max_tokens,
                unique_prefix=args.unique_prefix,
            )
            for request in batch.requests:
                if request.error:
                    print(f"  ! {request.error}")
            batches.append(batch)
            summaries.append(summarize_batch(batch, target))

    meta = {
        "started_at": started_at.isoformat(timespec="seconds"),
        "runs": args.runs,
        "warmup": args.warmup,
        "concurrency": args.concurrency,
        "max_tokens": args.max_tokens,
        "unique_prefix": args.unique_prefix,
        "backends": [
            {"name": t.name, "kind": t.kind, "model": t.model, "base_url": t.base_url} for t in targets
        ],
    }
    folder = started_at.strftime("%Y%m%d-%H%M%S") + (f"-{args.label}" if args.label else "")
    output_dir = args.output_dir / folder
    write_report(output_dir, meta=meta, summaries=summaries, batches=batches)
    print()
    print(render_markdown(meta, summaries))
    print(f"결과 저장: {output_dir}")


def load_targets(config_path: Path, only: str | None) -> list[BackendTarget]:
    if not config_path.exists():
        raise SystemExit(
            f"{config_path} 가 없습니다. benchmarks/backends.example.toml 을 복사해 값을 채운 뒤 다시 실행하세요."
        )
    with config_path.open("rb") as file:
        config = tomllib.load(file)
    targets = [BackendTarget.from_dict(item) for item in config.get("backends", [])]
    if only:
        wanted = set(_split(only))
        targets = [target for target in targets if target.name in wanted]
    if not targets:
        raise SystemExit("측정할 backend가 없습니다. 설정 파일 또는 --backends 값을 확인하세요.")
    remote = [t.name for t in targets if (urlparse(t.base_url).hostname or "").lower() not in LOCAL_HOSTS]
    if remote:
        raise SystemExit(f"회의록 근거를 외부로 보내지 않도록 localhost 주소만 허용합니다: {remote}")
    return targets


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="의정이슈레이더 LLM 백엔드(RNGD·GPU) TTFT / tokens/s / 비용 비교")
    parser.add_argument("--config", type=Path, default=PROJECT_ROOT / "benchmarks" / "backends.toml")
    parser.add_argument("--backends", help="측정할 backend name 목록 (쉼표 구분). 생략하면 전체")
    parser.add_argument("--scenarios", help="측정할 시나리오 목록 (쉼표 구분). 생략하면 전체")
    parser.add_argument("--runs", type=int, default=5, help="시나리오당 측정 요청 수")
    parser.add_argument("--warmup", type=int, default=1, help="기록하지 않는 워밍업 요청 수")
    parser.add_argument("--concurrency", type=int, default=1, help="동시에 보낼 요청 수")
    parser.add_argument("--max-tokens", type=int, default=600, help="최대 출력 토큰 (앱 에이전트 num_predict=600)")
    parser.add_argument("--timeout", type=float, default=120.0)
    parser.add_argument("--output-dir", type=Path, default=PROJECT_ROOT / "benchmarks" / "results")
    parser.add_argument("--label", help="결과 폴더 이름 뒤에 붙일 라벨 (예: rngd-qwen3-8b-c1)")
    parser.add_argument(
        "--unique-prefix",
        action="store_true",
        help="요청마다 고유 ID를 앞에 붙여 프리픽스 캐시를 피한다(실제 prefill 포함 TTFT 측정). 모든 머신에서 같게 쓴다",
    )
    parser.add_argument("--dry-run", action="store_true", help="LLM 호출 없이 시나리오 프롬프트만 확인")
    return parser.parse_args()


def _split(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


if __name__ == "__main__":
    main()
