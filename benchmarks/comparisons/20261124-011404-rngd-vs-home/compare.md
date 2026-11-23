# LLM 백엔드 비교표

## 실행 환경

| 실행 폴더 | 머신 | 하드웨어 | 런타임 | 양자화 | runs | warmup | 동시성 | max_tokens |
|---|---|---|---|---|---:|---:|---:|---:|
| `20261123-160102-rngd-qwen3-8b-c1` | rngd-server (furiosa-npu, hancom-furi-agent-14) | FuriosaAI RNGD x1 (npu:7, firmware 2026.4.0) | furiosa-llm 2026.4.0 (--enable-overlap-scheduling, OpenAI 호환 /v1) | FP8 | 10 | 1 | 1 | 600 |
| `20261123-160232-rngd-qwen3-8b-c4` | rngd-server (furiosa-npu, hancom-furi-agent-14) | FuriosaAI RNGD x1 (npu:7, firmware 2026.4.0) | furiosa-llm 2026.4.0 (--enable-overlap-scheduling, OpenAI 호환 /v1) | FP8 | 16 | 1 | 4 | 600 |
| `20261124-004444-home-qwen3-8b-c1` | home-pc | NVIDIA GeForce RTX 3060 12GB (driver 610.88) | Ollama 0.40.17 (llama.cpp runner, OpenAI 호환 /v1) | Q4_K_M (4bit) | 10 | 1 | 1 | 600 |
| `20261124-004819-home-qwen3-8b-c4` | home-pc | NVIDIA GeForce RTX 3060 12GB (driver 610.88) | Ollama 0.40.17 (llama.cpp runner, OpenAI 호환 /v1) | Q4_K_M (4bit) | 16 | 1 | 4 | 600 |
| `20261124-005756-home-qwen3-8b-q8-c1` | home-pc | NVIDIA GeForce RTX 3060 12GB (driver 610.88) | Ollama 0.40.17 (llama.cpp runner, OpenAI 호환 /v1) | Q8_0 (8bit) | 10 | 1 | 1 | 600 |
| `20261124-010214-home-qwen3-8b-q8-c4` | home-pc | NVIDIA GeForce RTX 3060 12GB (driver 610.88) | Ollama 0.40.17 (llama.cpp runner, OpenAI 호환 /v1) | Q8_0 (8bit) | 16 | 1 | 4 | 600 |

## 전체 요약 (시나리오 평균)

| 동시성 | 백엔드 | 모델 | 입력 토큰 | TTFT p50 | 첫 답변 p50 | 생성 tok/s | 처리량 tok/s | 1K 요청 비용 | 오류 |
|---:|---|---|---:|---:|---:|---:|---:|---:|---:|
| 1 | home-ollama-qwen3-8b | `qwen3:8b` | 2,785 | 0.082s | 0.082s | 52.8 | 51.4 | - | 0/40 |
| 1 | home-ollama-qwen3-8b-q8 | `qwen3:8b-q8_0` | 2,785 | 0.063s | 0.063s | 36.0 | 35.6 | - | 0/40 |
| 1 | rngd-furiosa-qwen3-8b | `furiosa-ai/Qwen3-8B-FP8` | 2,781 | 0.029s | 0.029s | 100.9 | 99.2 | - | 0/40 |
| 4 | home-ollama-qwen3-8b | `qwen3:8b` | 2,785 | 13.981s | 13.981s | 54.1 | 53.3 | - | 0/64 |
| 4 | home-ollama-qwen3-8b-q8 | `qwen3:8b-q8_0` | 2,785 | 16.430s | 16.430s | 36.3 | 36.0 | - | 0/64 |
| 4 | rngd-furiosa-qwen3-8b | `furiosa-ai/Qwen3-8B-FP8` | 2,781 | 0.084s | 0.084s | 86.8 | 321.9 | - | 0/64 |

## 시나리오별 비교

배수 기준: `home-ollama-qwen3-8b` (처리량 배수 > 1 이면 더 빠름, TTFT 배수 < 1 이면 첫 토큰이 더 빠름)

| 동시성 | 시나리오 | 백엔드 | 실행 폴더 | 입력 토큰 | TTFT p50 | 첫 답변 p50 | 생성 tok/s | 처리량 tok/s | 1K 요청 비용 | 오류 | 처리량 배수 | TTFT 배수 |
|---:|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | question_parse | home-ollama-qwen3-8b | `20261124-004444-home-qwen3-8b-c1` | 349 | 0.062s | 0.062s | 56.1 | 54.3 | - | 0/10 | 1.00x | 1.00x |
| 1 | question_parse | home-ollama-qwen3-8b-q8 | `20261124-005756-home-qwen3-8b-q8-c1` | 349 | 0.050s | 0.050s | 37.8 | 37.4 | - | 0/10 | 0.69x | 0.80x |
| 1 | question_parse | rngd-furiosa-qwen3-8b | `20261123-160102-rngd-qwen3-8b-c1` | 345 | 0.026s | 0.026s | 104.1 | 101.8 | - | 0/10 | 1.87x | 0.42x |
| 1 | rag_answer_birth_rate | home-ollama-qwen3-8b | `20261124-004444-home-qwen3-8b-c1` | 2,935 | 0.089s | 0.089s | 53.0 | 52.7 | - | 0/10 | 1.00x | 1.00x |
| 1 | rag_answer_birth_rate | home-ollama-qwen3-8b-q8 | `20261124-005756-home-qwen3-8b-q8-c1` | 2,935 | 0.066s | 0.066s | 36.1 | 35.7 | - | 0/10 | 0.68x | 0.75x |
| 1 | rag_answer_birth_rate | rngd-furiosa-qwen3-8b | `20261123-160102-rngd-qwen3-8b-c1` | 2,931 | 0.029s | 0.029s | 101.3 | 100.9 | - | 0/10 | 1.92x | 0.33x |
| 1 | rag_answer_flood_safety | home-ollama-qwen3-8b | `20261124-004444-home-qwen3-8b-c1` | 4,169 | 0.091s | 0.091s | 50.7 | 50.0 | - | 0/10 | 1.00x | 1.00x |
| 1 | rag_answer_flood_safety | home-ollama-qwen3-8b-q8 | `20261124-005756-home-qwen3-8b-q8-c1` | 4,169 | 0.070s | 0.070s | 34.6 | 34.4 | - | 0/10 | 0.69x | 0.76x |
| 1 | rag_answer_flood_safety | rngd-furiosa-qwen3-8b | `20261123-160102-rngd-qwen3-8b-c1` | 4,165 | 0.032s | 0.032s | 96.9 | 95.9 | - | 0/10 | 1.92x | 0.35x |
| 1 | rag_answer_hallucination_bait | home-ollama-qwen3-8b | `20261124-004444-home-qwen3-8b-c1` | 3,686 | 0.086s | 0.086s | 51.4 | 48.5 | - | 0/10 | 1.00x | 1.00x |
| 1 | rag_answer_hallucination_bait | home-ollama-qwen3-8b-q8 | `20261124-005756-home-qwen3-8b-q8-c1` | 3,686 | 0.065s | 0.065s | 35.6 | 34.8 | - | 0/10 | 0.72x | 0.76x |
| 1 | rag_answer_hallucination_bait | rngd-furiosa-qwen3-8b | `20261123-160102-rngd-qwen3-8b-c1` | 3,682 | 0.029s | 0.029s | 101.4 | 98.0 | - | 0/10 | 2.02x | 0.34x |
| 4 | question_parse | home-ollama-qwen3-8b | `20261124-004819-home-qwen3-8b-c4` | 349 | 4.027s | 4.027s | 58.0 | 57.1 | - | 0/16 | 1.00x | 1.00x |
| 4 | question_parse | home-ollama-qwen3-8b-q8 | `20261124-010214-home-qwen3-8b-q8-c4` | 349 | 5.988s | 5.988s | 37.9 | 37.7 | - | 0/16 | 0.66x | 1.49x |
| 4 | question_parse | rngd-furiosa-qwen3-8b | `20261123-160232-rngd-qwen3-8b-c4` | 345 | 0.077s | 0.077s | 98.8 | 364.6 | - | 0/16 | 6.38x | 0.02x |
| 4 | rag_answer_birth_rate | home-ollama-qwen3-8b | `20261124-004819-home-qwen3-8b-c4` | 2,935 | 33.357s | 33.357s | 52.5 | 52.6 | - | 0/16 | 1.00x | 1.00x |
| 4 | rag_answer_birth_rate | home-ollama-qwen3-8b-q8 | `20261124-010214-home-qwen3-8b-q8-c4` | 2,935 | 37.234s | 37.234s | 36.1 | 35.9 | - | 0/16 | 0.68x | 1.12x |
| 4 | rag_answer_birth_rate | rngd-furiosa-qwen3-8b | `20261123-160232-rngd-qwen3-8b-c4` | 2,931 | 0.081s | 0.081s | 85.5 | 333.5 | - | 0/16 | 6.34x | 0.00x |
| 4 | rag_answer_flood_safety | home-ollama-qwen3-8b | `20261124-004819-home-qwen3-8b-c4` | 4,169 | 15.198s | 15.198s | 52.9 | 52.3 | - | 0/16 | 1.00x | 1.00x |
| 4 | rag_answer_flood_safety | home-ollama-qwen3-8b-q8 | `20261124-010214-home-qwen3-8b-q8-c4` | 4,169 | 17.620s | 17.620s | 35.4 | 35.2 | - | 0/16 | 0.67x | 1.16x |
| 4 | rag_answer_flood_safety | rngd-furiosa-qwen3-8b | `20261123-160232-rngd-qwen3-8b-c4` | 4,165 | 0.090s | 0.090s | 79.1 | 288.6 | - | 0/16 | 5.51x | 0.01x |
| 4 | rag_answer_hallucination_bait | home-ollama-qwen3-8b | `20261124-004819-home-qwen3-8b-c4` | 3,686 | 3.342s | 3.342s | 52.9 | 51.2 | - | 0/16 | 1.00x | 1.00x |
| 4 | rag_answer_hallucination_bait | home-ollama-qwen3-8b-q8 | `20261124-010214-home-qwen3-8b-q8-c4` | 3,686 | 4.876s | 4.876s | 35.7 | 35.3 | - | 0/16 | 0.69x | 1.46x |
| 4 | rag_answer_hallucination_bait | rngd-furiosa-qwen3-8b | `20261123-160232-rngd-qwen3-8b-c4` | 3,682 | 0.088s | 0.088s | 83.7 | 300.8 | - | 0/16 | 5.87x | 0.03x |
