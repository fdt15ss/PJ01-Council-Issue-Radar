"""벤치마크 프롬프트가 앱·노트북 06 원문과 같은지 검사한다. 원본이 바뀌면 여기서 실패한다."""

import ast
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

from benchmark.scenarios import (
    EVIDENCE_CHARS,
    PARSE_INTENTS,
    PARSE_SYSTEM_PROMPT,
    PROJECT_ROOT,
    QUESTIONS,
    RAG_SYSTEM_PROMPT,
    SCENARIO_DESCRIPTIONS,
    build_scenarios,
)

SERVICES = PROJECT_ROOT / "src" / "api" / "services.py"
QUERY_PIPELINE = PROJECT_ROOT / "src" / "agent" / "query_pipeline.py"
NOTEBOOK_06 = PROJECT_ROOT / "notebooks" / "06_experiments_korean_llm_comparison.ipynb"
BENCH_SCRIPT = PROJECT_ROOT / "scripts" / "benchmark_llm_backends.py"


def _notebook_assignments() -> dict[str, object]:
    """노트북 06 코드 셀의 최상위 상수 대입(QUESTIONS, SYSTEM_PROMPT, EVIDENCE_CHARS 등)을 실행 없이 읽는다."""
    notebook = json.loads(NOTEBOOK_06.read_text(encoding="utf-8"))
    values: dict[str, object] = {}
    for cell in notebook["cells"]:
        if cell["cell_type"] != "code":
            continue
        try:
            tree = ast.parse("".join(cell["source"]))
        except SyntaxError:  # IPython 매직 등
            continue
        for node in tree.body:
            target = node.target if isinstance(node, ast.AnnAssign) else (node.targets[0] if isinstance(node, ast.Assign) else None)
            if isinstance(target, ast.Name) and node.value is not None:
                try:
                    values[target.id] = ast.literal_eval(node.value)
                except ValueError:
                    pass
    return values


class TestPromptsMatchSources(unittest.TestCase):
    def test_rag_prompt_matches_services_chat(self):
        source = SERVICES.read_text(encoding="utf-8")

        self.assertIn(f'"content": "{RAG_SYSTEM_PROMPT}"', source)
        self.assertIn(f"[:{EVIDENCE_CHARS}]", source)
        self.assertIn("f\"[근거 {index}] {metadata.get('council', '미상')} | \"", source)
        self.assertIn("f\"{metadata.get('meeting_date', '날짜 미상')}\\n", source)
        self.assertIn('f"질문: {request.message}\\n\\nPostgreSQL 검색 근거:\\n" + "\\n\\n".join(evidence_blocks)', source)

    def test_questions_and_prompt_match_notebook_06(self):
        values = _notebook_assignments()

        self.assertEqual(QUESTIONS, {item["id"]: item["q"] for item in values["QUESTIONS"]})
        self.assertEqual(RAG_SYSTEM_PROMPT, values["SYSTEM_PROMPT"])
        self.assertEqual(EVIDENCE_CHARS, values["EVIDENCE_CHARS"])

    def test_parse_prompt_matches_query_pipeline(self):
        tree = ast.parse(QUERY_PIPELINE.read_text(encoding="utf-8"))
        intents = next(
            ast.literal_eval(node.value)
            for node in tree.body
            if isinstance(node, ast.Assign) and getattr(node.targets[0], "id", None) == "INTENTS"
        )
        parse = next(node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef) and node.name == "parse")
        system = next(
            node.value for node in ast.walk(parse)
            if isinstance(node, ast.Assign) and getattr(node.targets[0], "id", None) == "system"
        )
        # system = "앞부분" + "; ".join(...) + "뒷부분"
        head, tail = system.left.left.value, system.right.value

        self.assertEqual(PARSE_INTENTS, intents)
        self.assertEqual(head + "; ".join(f"{k}={v}" for k, v in intents.items()) + tail, PARSE_SYSTEM_PROMPT)


class TestBuildScenarios(unittest.TestCase):
    def test_builds_rag_and_parse_scenarios(self):
        scenarios = build_scenarios()

        self.assertEqual(set(SCENARIO_DESCRIPTIONS), set(scenarios))
        self.assertEqual(9, len(scenarios))
        for messages in scenarios.values():
            self.assertEqual(["system", "user"], [m["role"] for m in messages])
            self.assertTrue(all(m["content"] for m in messages))

    def test_rag_user_message_has_six_truncated_evidence_blocks(self):
        user = build_scenarios()["rag_answer_birth_rate"][1]["content"]

        self.assertTrue(user.startswith(f"질문: {QUESTIONS['birth_rate']}\n\nPostgreSQL 검색 근거:\n[근거 1] "))
        self.assertIn("[근거 6] ", user)
        self.assertNotIn("[근거 7] ", user)
        for block in user.split("\n\n[근거 ")[1:]:
            body = block.split("\n", 1)[1]
            self.assertLessEqual(len(body), EVIDENCE_CHARS)

    def test_missing_evidence_stops_with_message(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "evidence.json"
            path.write_text("{}", encoding="utf-8")
            with self.assertRaises(SystemExit):
                build_scenarios(path)


class TestLocalhostOnly(unittest.TestCase):
    def _load_script(self):
        spec = importlib.util.spec_from_file_location("benchmark_cli", BENCH_SCRIPT)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def _config(self, tmp: str, base_url: str) -> Path:
        path = Path(tmp) / "backends.toml"
        path.write_text(f'[[backends]]\nname = "b"\nkind = "gpu"\nbase_url = "{base_url}"\nmodel = "m"\n', encoding="utf-8")
        return path

    def test_rejects_non_local_backend(self):
        cli = self._load_script()
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(SystemExit):
                cli.load_targets(self._config(tmp, "https://api.example.com/v1"), None)
            self.assertEqual(["b"], [t.name for t in cli.load_targets(self._config(tmp, "http://127.0.0.1:11434/v1"), None)])


if __name__ == "__main__":
    unittest.main()
