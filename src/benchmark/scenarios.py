"""DB·임베딩 모델 없이 모든 머신에서 같은 입력을 보내기 위한 고정 시나리오.

- 질문 8개: notebooks/06_experiments_korean_llm_comparison.ipynb 의 `QUESTIONS`
- 근거: data/llm_compare/evidence_top6.json (질문 id → pgvector 검색 근거 6건, 노트북 06이 저장)
- RAG 프롬프트: src/api/services.py `RadarApiService.chat()` 과 같은 system 문구·근거 블록(근거당 1800자)
- 질문 해석 프롬프트: src/agent/query_pipeline.py `QuestionPipeline.parse()` 의 system 문구

원본 함수는 검색 서비스·DB에 묶여 있어 import할 수 없으므로 문구를 복사했다.
원본이 바뀌면 src/benchmark/tests/test_scenarios.py 가 실패한다.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
EVIDENCE_PATH = PROJECT_ROOT / "data" / "llm_compare" / "evidence_top6.json"

# 근거 1건당 프롬프트에 넣는 글자 수 (services.py `str(row.get('text') or '')[:1800]`, 노트북 06 EVIDENCE_CHARS)
EVIDENCE_CHARS = 1800

# 노트북 06 `QUESTIONS`
QUESTIONS: dict[str, str] = {
    "birth_rate": "출산율 저하에 대응하기 위해 지방의회에서 어떤 정책이 논의됐나요?",
    "population_decline": "지방소멸과 인구감소 대응으로 의회에서 제안된 사업을 알려줘",
    "youth_jobs": "청년 일자리와 지역정착 지원에 대해 의원들이 지적한 문제점은?",
    "jeonse_fraud": "전세사기 피해자 지원 대책으로 어떤 내용이 나왔어?",
    "regional_healthcare": "지역 필수의료 공백 문제에 대해 회의록에서 어떤 대안이 언급됐나요?",
    "school_violence": "학교폭력 피해 학생 보호를 위해 논의된 내용은?",
    "flood_safety": "집중호우 침수 피해 예방 대책으로 어떤 사업 예산이 논의됐는지 금액과 함께 알려줘",
    "hallucination_bait": "2025년 화성 이주민 지원 조례를 처음 통과시킨 의회와 예산 규모는?",
}

# src/api/services.py RadarApiService.chat() 의 system 메시지
RAG_SYSTEM_PROMPT = (
    "지방의회 회의록 근거를 사용해 한국어로 답하세요. 근거에 없는 사실이나 숫자는 만들지 말고, "
    "각 사실 뒤에 [근거 N]을 표시하세요. 근거가 부족하면 그렇게 말하세요."
)

# src/agent/query_pipeline.py INTENTS
PARSE_INTENTS: dict[str, str] = {
    "propagation": "이슈가 어느 의회에서 처음 나왔고 어떻게 퍼졌는지",
    "followup_outlook": "타 지방의회의 후속 논의·조례화와 앞으로의 전망",
    "region_compare": "특정 지역끼리 비교",
    "evidence": "회의록 원문 근거·발언 내용",
    "statistics": "지역별 공공 통계 지표",
    "national_bills": "국회 법률안 동향",
    "explain": "개념·분석 방법 설명",
    "other": "그 밖의 질문",
}

# src/agent/query_pipeline.py QuestionPipeline.parse() 의 system 메시지
PARSE_SYSTEM_PROMPT = (
    "너는 지방의회 정책 질문을 구조화하는 해석기다. 답하지 말고 JSON만 출력한다. "
    "intent는 다음 중 하나: " + "; ".join(f"{key}={value}" for key, value in PARSE_INTENTS.items()) + ". "
    "topic은 정책 주제의 짧은 명사구, topic_terms는 그 주제의 동의어·공식 용어·조례 이름에 쓰일 표현이다. "
    "regions는 질문에 나온 광역의회만 정식 명칭으로 쓴다(경북→경상북도의회). "
    "질문이 '현재', '최신', '오늘', '실시간'을 명시하면 mode=live, "
    "그 밖에는 대회 데이터 기준을 지키도록 mode=backtest. "
    "직전 해석이 주어지고 질문이 짧은 후속 질문이면 바뀐 항목만 바꾸고 나머지는 이어받는다."
)
PARSE_SAMPLE_QUESTION = "경북 저출생 대응 조례가 다른 의회로 어떻게 퍼졌어?"

SCENARIO_DESCRIPTIONS: dict[str, str] = {
    **{
        f"rag_answer_{qid}": f"RAG 답변 (api/services.py chat): {question} + 근거 6건"
        for qid, question in QUESTIONS.items()
    },
    "question_parse": "질문 해석 (agent/query_pipeline.py parse, JSON 스키마 강제는 제외)",
}


def build_rag_messages(question: str, rows: list[dict[str, Any]]) -> list[dict[str, str]]:
    """services.py chat()·노트북 06 build_messages()와 같은 형식."""
    blocks = []
    for index, row in enumerate(rows, start=1):
        metadata = row.get("metadata") or {}
        blocks.append(
            f"[근거 {index}] {metadata.get('council', '미상')} | "
            f"{metadata.get('meeting_date', '날짜 미상')}\n{str(row.get('text') or '')[:EVIDENCE_CHARS]}"
        )
    return [
        {"role": "system", "content": RAG_SYSTEM_PROMPT},
        {"role": "user", "content": f"질문: {question}\n\nPostgreSQL 검색 근거:\n" + "\n\n".join(blocks)},
    ]


def build_parse_messages(question: str, previous: dict[str, Any] | None = None) -> list[dict[str, str]]:
    user = json.dumps({"question": question, "previous": previous or None}, ensure_ascii=False)
    return [{"role": "system", "content": PARSE_SYSTEM_PROMPT}, {"role": "user", "content": user}]


def build_scenarios(evidence_path: Path = EVIDENCE_PATH) -> dict[str, list[dict[str, str]]]:
    evidence: dict[str, list[dict[str, Any]]] = json.loads(evidence_path.read_text(encoding="utf-8"))
    missing = [qid for qid in QUESTIONS if qid not in evidence]
    if missing:
        raise SystemExit(f"{evidence_path} 에 근거가 없는 질문: {missing}. 노트북 06의 근거 검색 셀을 먼저 실행하세요.")
    scenarios = {f"rag_answer_{qid}": build_rag_messages(question, evidence[qid]) for qid, question in QUESTIONS.items()}
    scenarios["question_parse"] = build_parse_messages(PARSE_SAMPLE_QUESTION)
    return scenarios
