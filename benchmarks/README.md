# LLM 추론 벤치마크 (NPU RNGD · GPU)

의정이슈레이더의 실제 LLM 프롬프트(RAG 답변·질문 해석)로 FuriosaAI RNGD와 GPU(Ollama)의 추론 성능을 잰다.
결과 형식은 Pet Log 벤치마크와 같아서 두 프로젝트 결과를 같은 비교 도구로 읽을 수 있다.

- 코드: `src/benchmark/` (measure·scenarios·report·compare), 테스트: `src/benchmark/tests/`
- CLI: `scripts/benchmark_llm_backends.py` (측정), `scripts/compare_benchmark_results.py` (비교)
- 설정: `benchmarks/backends.example.toml` → `benchmarks/backends.toml` 로 복사 (git 제외)

## 측정 원칙

- 모든 백엔드를 OpenAI 호환 `/v1/chat/completions` **스트리밍**으로 같은 코드에서 잰다. furiosa-llm은 `/v1`만 제공하고 Ollama도 `/v1`을 지원한다.
- 회의록 근거가 프롬프트에 들어가므로 **각 머신 안의 `127.0.0.1`로만** 호출한다. 설정에 localhost가 아닌 주소가 있으면 실행을 거부한다. 외부 API는 비교하지 않는다.
- 입력은 DB 없이 고정 데이터로 만든다: 노트북 06의 질문 8개 + `data/llm_compare/evidence_top6.json`(질문당 근거 6건, 근거당 1800자). 프롬프트 문구는 `api/services.py`·`agent/query_pipeline.py` 원문을 복사했고, 원문이 바뀌면 `test_scenarios.py`가 실패한다.
- 모델은 양쪽 모두 Qwen3 8B: RNGD `furiosa-ai/Qwen3-8B-FP8`, 집 PC `qwen3:8b`(Q4_K_M) / `qwen3:8b-q8_0`(Q8_0).
- thinking은 끈다: furiosa-llm `chat_template_kwargs.enable_thinking=false`, Ollama `reasoning_effort="none"`.

## 시나리오

| 시나리오 | 앱 기능 | 입력 토큰(qwen3) |
| --- | --- | ---: |
| `rag_answer_<질문id>` ×8 | RAG 답변 (`services.chat`) | 약 3,300~4,200 |
| `question_parse` | 질문 해석 (`query_pipeline.parse`, JSON 스키마 강제 제외) | 약 350 |

`--dry-run`으로 목록과 글자 수를 볼 수 있다. 측정 시간이 길어 대표 4개만 쓴다(**모든 머신에서 같은 목록**):

```
rag_answer_birth_rate,rag_answer_flood_safety,rag_answer_hallucination_bait,question_parse
```

`flood_safety`가 가장 긴 프롬프트(약 4,170토큰)다. Ollama 기본 컨텍스트 4096이면 잘리므로 **`OLLAMA_CONTEXT_LENGTH=8192`가 필수**다.

## 프리픽스 캐시와 `--unique-prefix`

같은 프롬프트를 반복하면 서버가 KV 캐시를 재사용해 prefill을 건너뛰므로 TTFT가 0.1초 안팎으로 나온다(캐시 적중 TTFT).
이 프로젝트처럼 프롬프트가 긴 경우 실제 사용자는 매번 다른 근거를 보내므로, **prefill이 포함된 TTFT**는 `--unique-prefix`로 잰다.
이 옵션은 요청마다 첫 메시지 앞에 `요청 ID <랜덤>` 한 줄을 붙인다(입력 토큰 약 10개 증가). 기본값은 Pet Log와 같이 꺼져 있다.
비교 도구는 `unique_prefix`가 섞인 결과를 비교하면 경고를 낸다.

## 실행

Python 3.11+와 `openai` 패키지가 필요하다(`requirements.txt`에 포함). conda 환경에 없으면 uv로 바로 실행할 수 있다.

```bash
# 공통 준비
cp benchmarks/backends.example.toml benchmarks/backends.toml     # 그 머신에서 잴 항목만 남긴다
python scripts/benchmark_llm_backends.py --dry-run
# (openai 미설치 시) uv run --no-project --python 3.11 --with openai==3.44.0 python -B scripts/benchmark_llm_backends.py ...
```

### RNGD 서버

```bash
furiosa-llm serve furiosa-ai/Qwen3-8B-FP8 --devices npu:7 --host 127.0.0.1 --port 8000 --enable-overlap-scheduling
curl http://127.0.0.1:8000/v1/models          # model id 확인 → backends.toml 에 그대로
SC=rag_answer_birth_rate,rag_answer_flood_safety,rag_answer_hallucination_bait,question_parse
B=rngd-furiosa-qwen3-8b
python scripts/benchmark_llm_backends.py --backends $B --scenarios $SC --runs 10 --warmup 1 --concurrency 1 --max-tokens 600 --timeout 600 --label rngd-qwen3-8b-c1
python scripts/benchmark_llm_backends.py --backends $B --scenarios $SC --runs 16 --warmup 1 --concurrency 4 --max-tokens 600 --timeout 600 --label rngd-qwen3-8b-c4
python scripts/benchmark_llm_backends.py --backends $B --scenarios $SC --runs 10 --warmup 1 --concurrency 1 --max-tokens 600 --timeout 600 --unique-prefix --label rngd-qwen3-8b-nocache-c1
grep -c "<think>" benchmarks/results/*rngd*/requests.csv      # 모두 0 이어야 한다
```

각 결과 폴더에 `environment.json`을 넣는다(예: `benchmarks/environment.rngd.example.json` 복사).

### 집 PC (Windows, RTX 3060)

```powershell
# Ollama 트레이 앱을 끄고 컨텍스트 8192로 직접 띄운다 (또는 사용자 환경변수 OLLAMA_CONTEXT_LENGTH=8192 후 재시작)
$env:OLLAMA_CONTEXT_LENGTH = "8192"; ollama serve
ollama ps    # 100% GPU, CONTEXT 8192 확인
```

명령은 RNGD와 같고 `--backends`와 `--label`만 바꾼다: `home-ollama-qwen3-8b` → `home-qwen3-8b-c1` 등, `home-ollama-qwen3-8b-q8` → `home-qwen3-8b-q8-c1` 등.

### 결과 합치기

각 머신의 결과 폴더를 이 저장소의 `benchmarks/results/`로 모은 뒤:

```bash
# 캐시 적중 조건 (동시성 1·4)
python scripts/compare_benchmark_results.py benchmarks/results/*-c1 benchmarks/results/*-c4 --baseline home-ollama-qwen3-8b --label rngd-vs-home
# prefill 포함 조건
python scripts/compare_benchmark_results.py benchmarks/results/*nocache-c1 --baseline home-ollama-qwen3-8b --label rngd-vs-home-nocache
```

`*-c1` 패턴은 `*nocache-c1`도 포함하므로 캐시 조건 비교에서는 폴더를 직접 나열하거나 nocache 폴더를 빼고 넘긴다.

## 결과 파일

```
benchmarks/results/<YYYYMMDD-HHMMSS>-<label>/
  summary.md        사람이 읽는 표
  results.json      {"meta": {...}, "summaries": [...]}  (백엔드 × 시나리오 1행, input_tokens_mean 포함)
  requests.csv      요청 1건 단위 원본 (utf-8-sig)
  environment.json  하드웨어·런타임 정보 (사람이 작성)
benchmarks/comparisons/<YYYYMMDD-HHMMSS>-<label>/
  compare.md, compare.json
```

## 지표

| 지표 | 정의 |
| --- | --- |
| TTFT | 요청 전송 → 첫 생성 토큰(추론 토큰 포함) |
| 첫 답변 | 요청 전송 → 첫 content 토큰 |
| 생성 tok/s | `(출력 토큰 - 1) / (전체 시간 - TTFT)`, 요청 1건 기준 |
| 처리량 tok/s | 배치 전체 출력 토큰 / 배치 wall time |
| 입력 토큰 | 성공 요청 평균. 머신끼리 수 토큰 차이면 정상, 수백 토큰 차이면 컨텍스트 잘림 |
| 비용 | `usd_per_hour × wall time`, 단가가 없으면 `-` |

정밀도(FP8 vs 4bit/8bit 정수)와 서버 엔진(furiosa-llm vs llama.cpp)이 함께 다르므로 하드웨어 단독이 아닌 **구성 비교**로 읽는다.
