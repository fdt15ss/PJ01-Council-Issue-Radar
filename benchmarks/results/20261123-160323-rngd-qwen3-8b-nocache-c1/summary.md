# LLM 백엔드 성능 비교 결과

- 측정 시각: 2026-11-23T16:03:23
- 반복 횟수(시나리오당): 10 / 워밍업: 1 / 동시성: 1
- 최대 출력 토큰: 600
- 프리픽스 캐시 회피(unique_prefix): True

| 시나리오 | 백엔드 | 종류 | 모델 | 입력 토큰 | 출력 토큰 | TTFT p50 | TTFT p95 | 첫 답변 p50 | 생성 tok/s p50 | 처리량 tok/s | 1K 요청 비용 | 1M 출력 토큰 비용 | 오류 |
|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| rag_answer_birth_rate | rngd-furiosa-qwen3-8b | npu | `furiosa-ai/Qwen3-8B-FP8` | 2,947 | 391 | 0.251s | 0.252s | 0.251s | 101.5 | 95.5 | - | - | 0/10 |
| rag_answer_flood_safety | rngd-furiosa-qwen3-8b | npu | `furiosa-ai/Qwen3-8B-FP8` | 4,180 | 244 | 0.365s | 0.365s | 0.365s | 97.0 | 85.0 | - | - | 0/10 |
| rag_answer_hallucination_bait | rngd-furiosa-qwen3-8b | npu | `furiosa-ai/Qwen3-8B-FP8` | 3,697 | 75 | 0.324s | 0.324s | 0.324s | 101.4 | 71.2 | - | - | 0/10 |
| question_parse | rngd-furiosa-qwen3-8b | npu | `furiosa-ai/Qwen3-8B-FP8` | 360 | 78 | 0.049s | 0.050s | 0.049s | 104.2 | 98.9 | - | - | 0/10 |

## 시나리오 설명

- `rag_answer_birth_rate`: RAG 답변 (api/services.py chat): 출산율 저하에 대응하기 위해 지방의회에서 어떤 정책이 논의됐나요? + 근거 6건
- `rag_answer_population_decline`: RAG 답변 (api/services.py chat): 지방소멸과 인구감소 대응으로 의회에서 제안된 사업을 알려줘 + 근거 6건
- `rag_answer_youth_jobs`: RAG 답변 (api/services.py chat): 청년 일자리와 지역정착 지원에 대해 의원들이 지적한 문제점은? + 근거 6건
- `rag_answer_jeonse_fraud`: RAG 답변 (api/services.py chat): 전세사기 피해자 지원 대책으로 어떤 내용이 나왔어? + 근거 6건
- `rag_answer_regional_healthcare`: RAG 답변 (api/services.py chat): 지역 필수의료 공백 문제에 대해 회의록에서 어떤 대안이 언급됐나요? + 근거 6건
- `rag_answer_school_violence`: RAG 답변 (api/services.py chat): 학교폭력 피해 학생 보호를 위해 논의된 내용은? + 근거 6건
- `rag_answer_flood_safety`: RAG 답변 (api/services.py chat): 집중호우 침수 피해 예방 대책으로 어떤 사업 예산이 논의됐는지 금액과 함께 알려줘 + 근거 6건
- `rag_answer_hallucination_bait`: RAG 답변 (api/services.py chat): 2025년 화성 이주민 지원 조례를 처음 통과시킨 의회와 예산 규모는? + 근거 6건
- `question_parse`: 질문 해석 (agent/query_pipeline.py parse, JSON 스키마 강제는 제외)

## 지표 정의

- TTFT: 요청 전송부터 첫 생성 토큰(추론 토큰 포함) 수신까지 걸린 시간. 하드웨어 prefill 지연 비교용.
- 첫 답변: 요청 전송부터 첫 답변(content) 토큰까지 걸린 시간. 사용자가 체감하는 지연이며 thinking 모델은 TTFT보다 길다.
- `†`: 최대 출력 토큰 안에 답변 없이 추론만 생성한 요청이 있다. `--max-tokens`를 늘리거나 thinking을 끄고 다시 측정한다.
- 생성 tok/s: 첫 토큰 이후 생성 속도 `(출력 토큰 - 1) / (전체 시간 - TTFT)`. 요청 하나 기준.
- 처리량 tok/s: 배치 전체 출력 토큰 / 배치 wall time. 동시성을 올리면 하드웨어의 batching 효율이 드러난다.
- 입력·출력 토큰: 성공 요청 평균. 입력 토큰이 머신끼리 수 토큰만 다르면 컨텍스트 잘림이 없는 것이다.
- 비용: API는 `입력·출력 토큰 × 1M 토큰 단가`, RNGD/GPU는 `시간당 단가 × 배치 wall time`으로 계산한다. 단가가 비어 있으면 `-`.
- `*`: 서버가 usage를 주지 않아 스트리밍 chunk 수로 토큰 수를 추정한 값.
