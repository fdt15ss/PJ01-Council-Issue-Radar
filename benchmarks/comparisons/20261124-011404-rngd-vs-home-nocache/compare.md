# LLM 백엔드 비교표

## 실행 환경

| 실행 폴더 | 머신 | 하드웨어 | 런타임 | 양자화 | runs | warmup | 동시성 | max_tokens |
|---|---|---|---|---|---:|---:|---:|---:|
| `20261123-160323-rngd-qwen3-8b-nocache-c1` | rngd-server (furiosa-npu, hancom-furi-agent-14) | FuriosaAI RNGD x1 (npu:7, firmware 2026.4.0) | furiosa-llm 2026.4.0 (--enable-overlap-scheduling, OpenAI 호환 /v1) | FP8 | 10 | 1 | 1 | 600 |
| `20261124-005340-home-qwen3-8b-nocache-c1` | home-pc | NVIDIA GeForce RTX 3060 12GB (driver 610.88) | Ollama 0.40.17 (llama.cpp runner, OpenAI 호환 /v1) | Q4_K_M (4bit) | 10 | 1 | 1 | 600 |
| `20261124-010830-home-qwen3-8b-q8-nocache-c1` | home-pc | NVIDIA GeForce RTX 3060 12GB (driver 610.88) | Ollama 0.40.17 (llama.cpp runner, OpenAI 호환 /v1) | Q8_0 (8bit) | 10 | 1 | 1 | 600 |

## 전체 요약 (시나리오 평균)

| 동시성 | 백엔드 | 모델 | 입력 토큰 | TTFT p50 | 첫 답변 p50 | 생성 tok/s | 처리량 tok/s | 1K 요청 비용 | 오류 |
|---:|---|---|---:|---:|---:|---:|---:|---:|---:|
| 1 | home-ollama-qwen3-8b | `qwen3:8b` | 2,800 | 1.544s | 1.544s | 55.1 | 37.4 | - | 0/40 |
| 1 | home-ollama-qwen3-8b-q8 | `qwen3:8b-q8_0` | 2,800 | 1.463s | 1.463s | 36.2 | 27.4 | - | 0/40 |
| 1 | rngd-furiosa-qwen3-8b | `furiosa-ai/Qwen3-8B-FP8` | 2,796 | 0.247s | 0.247s | 101.0 | 87.6 | - | 0/40 |

## 시나리오별 비교

배수 기준: `home-ollama-qwen3-8b` (처리량 배수 > 1 이면 더 빠름, TTFT 배수 < 1 이면 첫 토큰이 더 빠름)

| 동시성 | 시나리오 | 백엔드 | 실행 폴더 | 입력 토큰 | TTFT p50 | 첫 답변 p50 | 생성 tok/s | 처리량 tok/s | 1K 요청 비용 | 오류 | 처리량 배수 | TTFT 배수 |
|---:|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | question_parse | home-ollama-qwen3-8b | `20261124-005340-home-qwen3-8b-nocache-c1` | 365 | 0.222s | 0.222s | 59.3 | 51.3 | - | 0/10 | 1.00x | 1.00x |
| 1 | question_parse | home-ollama-qwen3-8b-q8 | `20261124-010830-home-qwen3-8b-q8-nocache-c1` | 365 | 0.208s | 0.208s | 37.8 | 34.7 | - | 0/10 | 0.68x | 0.93x |
| 1 | question_parse | rngd-furiosa-qwen3-8b | `20261123-160323-rngd-qwen3-8b-nocache-c1` | 360 | 0.049s | 0.049s | 104.2 | 98.9 | - | 0/10 | 1.93x | 0.22x |
| 1 | rag_answer_birth_rate | home-ollama-qwen3-8b | `20261124-005340-home-qwen3-8b-nocache-c1` | 2,951 | 1.657s | 1.657s | 53.5 | 46.4 | - | 0/10 | 1.00x | 1.00x |
| 1 | rag_answer_birth_rate | home-ollama-qwen3-8b-q8 | `20261124-010830-home-qwen3-8b-q8-nocache-c1` | 2,951 | 1.524s | 1.524s | 36.1 | 32.0 | - | 0/10 | 0.69x | 0.92x |
| 1 | rag_answer_birth_rate | rngd-furiosa-qwen3-8b | `20261123-160323-rngd-qwen3-8b-nocache-c1` | 2,947 | 0.251s | 0.251s | 101.5 | 95.5 | - | 0/10 | 2.06x | 0.15x |
| 1 | rag_answer_flood_safety | home-ollama-qwen3-8b | `20261124-005340-home-qwen3-8b-nocache-c1` | 4,184 | 2.294s | 2.294s | 53.3 | 33.2 | - | 0/10 | 1.00x | 1.00x |
| 1 | rag_answer_flood_safety | home-ollama-qwen3-8b-q8 | `20261124-010830-home-qwen3-8b-q8-nocache-c1` | 4,184 | 2.197s | 2.197s | 35.4 | 26.7 | - | 0/10 | 0.81x | 0.96x |
| 1 | rag_answer_flood_safety | rngd-furiosa-qwen3-8b | `20261123-160323-rngd-qwen3-8b-nocache-c1` | 4,180 | 0.365s | 0.365s | 97.0 | 85.0 | - | 0/10 | 2.56x | 0.16x |
| 1 | rag_answer_hallucination_bait | home-ollama-qwen3-8b | `20261124-005340-home-qwen3-8b-nocache-c1` | 3,702 | 2.001s | 2.001s | 54.3 | 18.8 | - | 0/10 | 1.00x | 1.00x |
| 1 | rag_answer_hallucination_bait | home-ollama-qwen3-8b-q8 | `20261124-010830-home-qwen3-8b-q8-nocache-c1` | 3,702 | 1.925s | 1.925s | 35.6 | 16.3 | - | 0/10 | 0.87x | 0.96x |
| 1 | rag_answer_hallucination_bait | rngd-furiosa-qwen3-8b | `20261123-160323-rngd-qwen3-8b-nocache-c1` | 3,697 | 0.324s | 0.324s | 101.4 | 71.2 | - | 0/10 | 3.79x | 0.16x |
