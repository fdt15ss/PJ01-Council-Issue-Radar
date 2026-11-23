# NPU(RNGD)·GPU LLM 벤치마크 구현 가이드

이 문서는 Claude 에이전트가 이 프로젝트(의정이슈레이더)에 **NPU(FuriosaAI RNGD)와 GPU의 LLM 추론 성능 비교 벤치마크**를 만들 때 따르는 작업 지시서다.
같은 형식의 벤치마크를 Pet Log 프로젝트에서 이미 만들고 실측까지 마쳤으므로, 그 구현과 **결과 형식을 그대로 맞추는 것**이 목표다.

## 0. 먼저 읽을 참고 구현 (Pet Log)

같은 PC의 아래 경로에 완성본이 있다. 구현 전에 반드시 읽고, 구조와 출력 형식을 그대로 따른다.

| 파일 | 내용 |
| --- | --- |
| `G:\programming\@projects\202601_potenup3\PJ04-pet-log\backend\src\infrastructure\llm\benchmark\measure.py` | 스트리밍 요청 측정, 동시 요청 배치, 요약·비용 계산 |
| `...\benchmark\scenarios.py` | 앱의 프롬프트 빌더로 시나리오 메시지 생성 |
| `...\benchmark\report.py` | `summary.md`, `results.json`, `requests.csv` 작성 |
| `...\benchmark\compare.py` | 여러 결과 폴더를 하나의 비교표로 합침 |
| `...\backend\scripts\benchmark_llm_backends.py` | 측정 CLI |
| `...\backend\scripts\compare_benchmark_results.py` | 비교 CLI |
| `...\backend\benchmarks\backends.example.toml` | 백엔드 설정 예시 |
| `...\backend\tests\test_llm_benchmark.py`, `test_llm_benchmark_compare.py` | 가짜 스트림·가짜 시계로 지표 검증 |
| `...\backend\docs\llm-backend-benchmark.md` | 지표 정의, 공정 비교 체크리스트, 머신 간 비교 절차 |
| `...\backend\benchmarks\results\`, `comparisons\` | 실제 결과 예시 (RNGD, Windows, WSL) |

(`...` = `G:\programming\@projects\202601_potenup3\PJ04-pet-log\backend\src\infrastructure\llm`)

## 1. 작업 원칙

- **앱 코드는 바꾸지 않는다.** 벤치마크용 새 파일만 추가한다. 앱은 Ollama 네이티브 `/api/chat`을 쓰지만, 벤치마크는 별도 스크립트로 측정한다.
- **회의록을 외부로 보내지 않는다.** 이 프로젝트는 LLM 주소를 localhost로 제한한다(`agent/local_issue_agent.py`의 `LOCAL_HOSTS`). 벤치마크도 각 머신 안에서 `127.0.0.1`로만 호출한다. 외부 API(OpenAI 등)는 회의록 근거가 들어가므로 **비교 대상에 넣지 않는다.**
- `.env`, API 키, `backends.toml`은 커밋하지 않는다. `.gitignore`에 `benchmarks/backends.toml`을 추가한다.
- 커밋·푸시는 사용자 승인 후에 한다. 현재 브랜치(`submission/package`)에서 바로 작업하지 말고 작업 브랜치를 만든다.
- 사용자가 수정 중인 파일(예: 노트북)은 건드리지 않는다.

## 2. 이 프로젝트의 LLM 호출 지점

| 위치 | 역할 | 프롬프트 | 출력 |
| --- | --- | --- | --- |
| `src/api/services.py` `RadarApiService.chat()` (229행 부근) | 검색 근거 기반 RAG 답변 | system 1개 + `질문: ...\n\nPostgreSQL 검색 근거:\n[근거 N] 의회 \| 날짜\n본문[:1800]` | 자유 텍스트, `[근거 N]` 인용 |
| `src/agent/local_issue_agent.py` `_ollama_answer()` | 에이전트 답변 | 이슈 요약 + 회의록 근거 + 질문, `num_predict=600`, `temperature=0.1` | 자유 텍스트 |
| `src/agent/query_pipeline.py` `QuestionPipeline.parse()` | 질문 해석 | 해석기 system + `{"question", "previous"}` JSON, `num_predict=300` | JSON (Ollama `format` 스키마) |
| `src/09_local_llm_relevance_judge.py` | 오프라인 관련성 평가 | 배치 평가 프롬프트 | JSON |

모두 Ollama 네이티브 API(`/api/chat`, `think: False`, `options.num_ctx=8192`)를 쓴다.

## 3. 측정 설계

### 3.1 모든 백엔드를 OpenAI 호환 `/v1` 스트리밍으로 측정

- RNGD의 `furiosa-llm serve`는 OpenAI 호환 `/v1/chat/completions`만 제공하고 Ollama `/api/chat`은 없다. Ollama도 `/v1`을 지원하므로 **양쪽 모두 `/v1` 스트리밍**으로 같은 코드에서 잰다.
- 앱은 응답을 한 번에 받는 방식(`stream: False`)이라 첫 토큰 시간(TTFT)을 앱 안에서 잴 수 없다. 그래서 별도 측정 스크립트가 필요하다.
- `openai` SDK는 이미 `requirements.txt`에 있다. Python 3.11이므로 설정 파일은 `tomllib`로 읽는다.

### 3.2 입력은 DB 없이 고정 데이터로 재현

노트북 06(`notebooks/06_experiments_korean_llm_comparison.ipynb`)이 이미 만든 고정 입력을 쓴다. pgvector·임베딩 모델 없이 두 머신에서 **같은 입력**을 보낼 수 있다.

- 질문 8개: 노트북 06의 `QUESTIONS` (`birth_rate`, `population_decline`, `youth_jobs`, `jeonse_fraud`, `regional_healthcare`, `school_violence`, `flood_safety`, `hallucination_bait`)
- 근거: `data/llm_compare/evidence_top6.json` (질문 id → 근거 6건)
- 프롬프트: `RadarApiService.chat()`과 같은 system 문구와 근거 블록(근거당 1800자). 노트북 06의 `build_messages()`가 같은 형식이다.

`services.py`의 프롬프트는 함수로 분리돼 있지 않고 숫자로 시작하는 모듈(`09_...`)은 import할 수 없으므로, **프롬프트 문구는 복사하되 원본 위치를 주석으로 남기고**, 원본이 바뀌면 실패하는 테스트를 둔다(예: `services.py` 원문에 system 문구가 그대로 있는지 검사).

### 3.3 시나리오

| 시나리오 | 앱 기능 | 입력 | 최대 출력 |
| --- | --- | --- | ---: |
| `rag_answer_<질문id>` (8개) | RAG 답변 (`services.chat`) | 질문 + 근거 6건 (프롬프트 약 2,400토큰) | 600 |
| `question_parse` | 질문 해석 (`query_pipeline.parse`) | 해석기 system + 질문 JSON | 300 → 측정은 공통 `--max-tokens`로 통일 |

- 시간이 오래 걸리면 `--scenarios`로 대표 질문 몇 개만 골라도 된다. **단, 모든 머신에서 같은 시나리오를 쓴다.**
- 질문 해석의 JSON 스키마 강제(`format`)는 측정에서 빼고 같은 프롬프트를 일반 chat으로 보낸다. 지연·속도 비교용이며 출력 형식 검증은 하지 않는다. furiosa-llm이 `response_format: json_schema`를 지원하는지는 별도로 확인한다.

### 3.4 공정 비교를 위한 필수 조건

- **thinking 끄기**: Ollama는 `extra_body.reasoning_effort = "none"`, furiosa-llm은 `extra_body.chat_template_kwargs.enable_thinking = false`. thinking 모델은 출력 토큰을 추론에 다 써서 답이 비는 문제가 있었다. 측정 후 `requests.csv`의 `output_preview`에 `<think>`가 0건인지 확인한다.
- **컨텍스트 길이**: 프롬프트가 약 2,400토큰이다. Ollama `/v1`은 요청마다 `num_ctx`를 받지 않으므로, **서버를 띄울 때 `OLLAMA_CONTEXT_LENGTH=8192`** 를 설정한다(앱의 `num_ctx=8192`와 같게). 결과의 입력 토큰 수를 머신끼리 비교해 잘림이 없었음을 검증한다. 서버마다 chat 템플릿이 달라 같은 입력도 몇 토큰 차이가 난다(Pet Log에서 Ollama와 furiosa-llm이 4토큰 차이). 수백 토큰 이상 차이 나면 잘린 것이다.
- **같은 모델**: 앱 기본 모델은 `hf.co/mykor/A.X-4.0-Light-gguf:Q4_K_M`이다. RNGD에 같은 모델이 없으면 **양쪽 모두 Qwen3 8B로 통일**한다(Pet Log와 같은 조합이라 결과도 비교할 수 있다).
  - RNGD: `furiosa-ai/Qwen3-8B-FP8` (`curl http://127.0.0.1:8000/v1/models`로 실제 id 확인)
  - 집 PC: `qwen3:8b`(Q4_K_M 4bit), `qwen3:8b-q8_0`(Q8_0 8bit). Ollama에는 FP8 형식이 없고 RTX 3060은 FP8을 지원하지 않아 8bit 정수로 비트 수만 맞춘다.
- **같은 조건**: `--runs`, `--warmup`, `--max-tokens`, `--concurrency`, 시나리오를 모두 같게 한다. 동시성은 1과 4(가능하면 8, 16)로 잰다.
- **간섭 제거**: 측정 중 GPU를 쓰는 다른 프로그램(블루스택, 게임)을 끈다. WSL에서 잴 때는 Windows Ollama를 끈다(같은 포트로 요청이 Windows Ollama에 갈 수 있다). `ollama ps`로 `100% GPU`인지 확인한다.

## 4. 결과 형식 (Pet Log와 동일하게)

형식을 맞추면 Pet Log의 `compare_benchmark_results.py`로도 두 프로젝트 결과를 함께 읽을 수 있다.

### 4.1 폴더

```
benchmarks/
  backends.example.toml        # 커밋
  backends.toml                # 로컬 설정, git 제외
  results/<YYYYMMDD-HHMMSS>-<label>/
    summary.md                 # 사람이 읽는 표
    results.json               # {"meta": {...}, "summaries": [...]}
    requests.csv               # 요청 1건 단위 원본 (utf-8-sig)
    environment.json           # 하드웨어·런타임 정보 (사람이 직접 작성)
  comparisons/<YYYYMMDD-HHMMSS>-<label>/
    compare.md
    compare.json
```

### 4.2 이름 규칙

- backend `name`: `<장소>-<런타임>-<모델>` → `rngd-furiosa-qwen3-8b`, `home-ollama-qwen3-8b`, `home-ollama-qwen3-8b-q8`, `wsl-ollama-qwen3-8b`
- `--label`: `<장소>-<모델>-c<동시성>` → `rngd-qwen3-8b-c1`, `home-qwen3-8b-q8-c4`

### 4.3 `results.json`

`meta` 키: `started_at`, `runs`, `warmup`, `concurrency`, `max_tokens`, `backends[{name, kind, model, base_url}]`

`summaries[]` 키 (백엔드 × 시나리오 1행):
`backend`, `kind`, `model`, `scenario`, `concurrency`, `requests`, `errors`, `ttft_p50_s`, `ttft_p95_s`, `ttft_content_p50_s`, `no_content_requests`, `e2e_p50_s`, `decode_tokens_per_s_p50`, `throughput_tokens_per_s`, `output_tokens_mean`, `tokens_estimated`, `cost_usd_per_1k_requests`, `cost_usd_per_1m_output_tokens`

이 프로젝트에서는 프롬프트가 길어 잘림 확인이 중요하므로 `input_tokens_mean`을 **추가**한다(기존 키는 바꾸지 않는다).

### 4.4 `requests.csv` 열

`backend, scenario, concurrency, ttft_s, ttft_content_s, e2e_s, decode_tokens_per_s, input_tokens, output_tokens, tokens_estimated, error, output_preview`

### 4.5 `environment.json` 키

`machine`, `gpu` 또는 `accelerator`, `runtime`, `model`, `quantization`, `thinking`, `network`, 그 밖에 필요한 것(`os`, `cpu`, `ram_gb`, `ollama_context_length`, `background_apps`). 비교표의 "실행 환경" 칸은 `machine`, `gpu`/`accelerator`, `runtime`, `quantization`을 쓴다.

### 4.6 지표 정의

| 지표 | 정의 |
| --- | --- |
| TTFT | 요청 전송부터 첫 생성 토큰(추론 토큰 포함)까지 |
| 첫 답변 | 첫 답변(content) 토큰까지. 추론 토큰은 Ollama `delta.reasoning`, vLLM 계열 `delta.reasoning_content` |
| 생성 tok/s | `(출력 토큰 - 1) / (전체 시간 - TTFT)` |
| 처리량 tok/s | 배치 전체 출력 토큰 / 배치 wall time |
| 비용 | 하드웨어는 `usd_per_hour × wall time`, 단가가 없으면 `-` |

오류 판정: 생성 토큰이 하나도 없으면 오류. 추론만 나오고 답이 없으면 오류가 아니라 `no_content_requests`로 센다(표에 `†`).

## 5. 이 프로젝트에 만들 파일

이 프로젝트는 패키지 설치형이 아니므로 스크립트에서 `src`를 `sys.path`에 넣는다(Pet Log 스크립트와 같은 방식).

| 파일 | 내용 |
| --- | --- |
| `src/benchmark/__init__.py` | |
| `src/benchmark/measure.py` | Pet Log `measure.py`와 같은 로직 (`BackendTarget`, `RequestResult`, `measure_stream`, `run_batch`, `summarize_batch`) + `input_tokens_mean` |
| `src/benchmark/scenarios.py` | 3.2·3.3의 고정 입력으로 시나리오 메시지 생성 |
| `src/benchmark/report.py` | Pet Log `report.py`와 같은 출력 |
| `src/benchmark/compare.py` | Pet Log `compare.py`와 같은 로직 |
| `scripts/benchmark_llm_backends.py` | 측정 CLI (옵션은 Pet Log와 같게: `--config --backends --scenarios --runs --warmup --concurrency --max-tokens --timeout --output-dir --label --dry-run`) |
| `scripts/compare_benchmark_results.py` | 비교 CLI (`--baseline --label`) |
| `benchmarks/backends.example.toml` | RNGD, 집 PC 4bit·8bit 예시. API 키는 `api_key_env`로만 |
| `src/benchmark/tests/test_measure.py` 등 | `unittest`. 가짜 스트림·가짜 시계, 추론 토큰 분리, 오류 기록, 비용, 비교 경고, 프롬프트 원문 일치 |
| `docs/` 또는 `README.md` 섹션 | 실행 방법과 결과 위치 |

`measure_stream`의 핵심 (Pet Log와 동일):

```python
kwargs = {"model": target.model, "messages": messages, "stream": True,
          target.max_tokens_param: max_tokens, "stream_options": {"include_usage": True}}
if target.temperature is not None: kwargs["temperature"] = target.temperature
if target.extra_body: kwargs["extra_body"] = target.extra_body   # thinking 끄기
for chunk in client.chat.completions.create(**kwargs):
    if chunk.usage: usage = chunk.usage
    for choice in chunk.choices or ():
        text = choice.delta.content
        reasoning = getattr(choice.delta, "reasoning", None) or getattr(choice.delta, "reasoning_content", None)
        # 첫 토큰(추론 포함) 시각과 첫 content 시각을 따로 기록
```

## 6. 측정 절차

### 6.1 RNGD 서버

```bash
furiosa-llm serve furiosa-ai/Qwen3-8B-FP8 --devices npu:7 --host 0.0.0.0 --port 8000 --enable-overlap-scheduling
curl http://127.0.0.1:8000/v1/models
curl -s http://127.0.0.1:8000/v1/chat/completions -H "Content-Type: application/json" \
  -d '{"model":"furiosa-ai/Qwen3-8B-FP8","messages":[{"role":"user","content":"hello"}],"max_tokens":64,"chat_template_kwargs":{"enable_thinking":false}}'
```

- 응답 `content`에 `<think>`가 없고 `reasoning_tokens`가 0이면 thinking이 꺼진 것이다.
- 외부 접속이 필요 없으면 `--host 127.0.0.1`로 띄운다.

### 6.2 집 PC (Windows 또는 WSL)

```bash
# 컨텍스트를 앱과 같게
# - Windows: 시스템 환경변수 OLLAMA_CONTEXT_LENGTH=8192 설정 후 Ollama 재시작
# - Linux/WSL에서 systemd 서비스로 돌면: sudo systemctl edit ollama 에 Environment="OLLAMA_CONTEXT_LENGTH=8192" 추가 후 재시작
# - 직접 띄울 때:
OLLAMA_CONTEXT_LENGTH=8192 ollama serve
ollama pull qwen3:8b
ollama pull qwen3:8b-q8_0
ollama run qwen3:8b-q8_0 "hi" && ollama ps   # 100% GPU, CONTEXT 8192 확인
```

### 6.3 측정 명령 (모든 머신 공통 조건)

```bash
python scripts/benchmark_llm_backends.py --dry-run
python scripts/benchmark_llm_backends.py --backends <name> --runs 3 --warmup 1 --max-tokens 600 --output-dir /tmp/bench-smoke --label smoke
python scripts/benchmark_llm_backends.py --backends <name> --runs 10 --warmup 1 --concurrency 1 --max-tokens 600 --label <장소>-<모델>-c1
python scripts/benchmark_llm_backends.py --backends <name> --runs 16 --warmup 1 --concurrency 4 --max-tokens 600 --label <장소>-<모델>-c4
grep -c "<think>" benchmarks/results/*/requests.csv
```

시나리오 9개 × 600토큰이면 집 PC(4bit 약 55 tok/s)에서 동시성 1 측정에 15분 이상 걸릴 수 있다. 오래 걸리면 `--scenarios`로 대표 시나리오만 고르고, 고른 목록을 모든 머신에서 똑같이 쓴다. 긴 측정은 백그라운드로 돌린다.

### 6.4 결과 합치기

각 머신의 결과 폴더를 한 곳의 `benchmarks/results/`로 모으고 `environment.json`을 넣은 뒤:

```bash
python scripts/compare_benchmark_results.py --baseline home-ollama-qwen3-8b --label rngd-vs-home
```

## 7. 완료 조건

- [ ] 단위 테스트 통과, `--dry-run`으로 시나리오가 만들어진다
- [ ] 프롬프트 원문 일치 테스트가 `services.py`·노트북 06과 같은 문구를 확인한다
- [ ] 로컬 Ollama로 실측 1회 이상 성공, 오류 0건, `<think>` 0건
- [ ] 결과 폴더·키·열 이름이 4장과 같다
- [ ] 머신 간 `input_tokens_mean` 차이가 템플릿 차이 수준(수 토큰)이라 컨텍스트 잘림이 없음을 확인했다
- [ ] `.gitignore`에 `benchmarks/backends.toml`, 문서에 실행 방법이 있다

## 8. Pet Log에서 얻은 교훈 (해석할 때 참고)

- 요청 1개 기준 RNGD(FP8)는 RTX 3060 대비 생성 속도 1.8배(4bit 대비)~2.8배(8bit 대비) 빨랐다.
- 동시 요청 4개에서 Ollama는 요청을 하나씩 처리해 처리량이 그대로였고 첫 토큰이 4~9초로 늘었다. RNGD는 묶어서 처리해 처리량이 6~9배였다.
- 집 PC는 8bit로 올리면 오히려 36% 느려졌다(읽을 가중치가 두 배).
- WSL로 옮겨도 생성 속도는 2% 안쪽으로 같았다. 격차의 원인은 OS가 아니라 서버의 동시 요청 처리 방식이었다.
- 이 프로젝트는 프롬프트(약 2,400토큰)가 Pet Log(약 420~1,310토큰)보다 길어 **prefill 비중이 커지므로 TTFT 차이가 더 크게 나올 수 있다.** 측정 전에 단정하지 말고 결과로 확인한다.
- 정밀도(4bit/8bit 정수 vs FP8)와 서버 엔진이 함께 다르므로 하드웨어 단독이 아닌 **구성 비교**로 보고한다.
