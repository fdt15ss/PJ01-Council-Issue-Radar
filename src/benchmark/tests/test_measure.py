import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from benchmark.measure import (
    BackendTarget,
    BatchResult,
    RequestResult,
    measure_stream,
    run_batch,
    with_unique_prefix,
    summarize_batch,
)
from benchmark.report import write_report


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def _chunk(content=None, usage=None):
    choices = [] if content is None else [SimpleNamespace(delta=SimpleNamespace(content=content))]
    return SimpleNamespace(choices=choices, usage=usage)


class FakeClient:
    """첫 chunk 전 0.5초, 이후 chunk마다 0.1초가 지나는 스트림."""

    def __init__(self, clock: FakeClock, tokens=("안", "녕", "하", "세", "요"), usage=True) -> None:
        self.clock = clock
        self.tokens = tokens
        self.usage = usage
        self.calls = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return self._stream()

    def _stream(self):
        self.clock.now += 0.5
        for index, token in enumerate(self.tokens):
            if index:
                self.clock.now += 0.1
            yield _chunk(token)
        if self.usage:
            yield _chunk(usage=SimpleNamespace(prompt_tokens=100, completion_tokens=len(self.tokens)))


class FailingClient:
    def __init__(self) -> None:
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))

    def create(self, **kwargs):
        raise ConnectionError("refused")


MESSAGES = [{"role": "user", "content": "hi"}]


class TestMeasureStream(unittest.TestCase):
    def test_measures_ttft_and_decode_speed(self):
        clock = FakeClock()
        target = BackendTarget(name="rngd", kind="npu", base_url="http://x/v1", model="m")

        result = measure_stream(FakeClient(clock), target, "rag_answer_birth_rate", MESSAGES, 64, clock)

        self.assertTrue(result.ok)
        self.assertAlmostEqual(0.5, result.ttft_s)
        self.assertAlmostEqual(0.9, result.e2e_s)
        self.assertEqual(5, result.output_tokens)
        self.assertEqual(100, result.input_tokens)
        self.assertFalse(result.tokens_estimated)
        self.assertAlmostEqual(10.0, result.decode_tokens_per_s)
        self.assertEqual("안녕하세요", result.output_preview)

    def test_sends_backend_specific_request_options(self):
        clock = FakeClock()
        client = FakeClient(clock)
        target = BackendTarget(
            name="priced",
            kind="api",
            base_url="http://x/v1",
            model="m",
            max_tokens_param="max_completion_tokens",
            extra_body={"reasoning_effort": "minimal"},
        )

        measure_stream(client, target, "question_parse", MESSAGES, 64, clock)

        call = client.calls[0]
        self.assertEqual(64, call["max_completion_tokens"])
        self.assertNotIn("max_tokens", call)
        self.assertNotIn("temperature", call)
        self.assertEqual({"include_usage": True}, call["stream_options"])
        self.assertEqual({"reasoning_effort": "minimal"}, call["extra_body"])

    def test_estimates_tokens_from_chunks_without_usage(self):
        clock = FakeClock()
        target = BackendTarget(name="gpu", kind="gpu", base_url="http://x/v1", model="m", stream_usage=False)

        result = measure_stream(FakeClient(clock, usage=False), target, "question_parse", MESSAGES, 64, clock)

        self.assertEqual(5, result.output_tokens)
        self.assertIsNone(result.input_tokens)
        self.assertTrue(result.tokens_estimated)

    def test_separates_reasoning_tokens_from_first_answer_token(self):
        clock = FakeClock()

        def stream(**kwargs):
            clock.now += 0.3
            yield SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content=None, reasoning="생각"))], usage=None)
            clock.now += 0.4
            yield _chunk("답")
            clock.now += 0.1
            yield _chunk("변", usage=SimpleNamespace(prompt_tokens=10, completion_tokens=3))

        client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=stream)))
        target = BackendTarget(name="gpu", kind="gpu", base_url="http://x/v1", model="gemma4")

        result = measure_stream(client, target, "question_parse", MESSAGES, 64, clock)

        self.assertTrue(result.ok)
        self.assertAlmostEqual(0.3, result.ttft_s)
        self.assertAlmostEqual(0.7, result.ttft_content_s)
        self.assertEqual("답변", result.output_preview)

    def test_reasoning_only_response_is_ok_but_has_no_answer(self):
        def stream(**kwargs):
            yield SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content=None, reasoning_content="생각"))], usage=None)

        client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=stream)))
        target = BackendTarget(name="gpu", kind="gpu", base_url="http://x/v1", model="m")

        result = measure_stream(client, target, "question_parse", MESSAGES, 64, FakeClock())

        self.assertTrue(result.ok)
        self.assertIsNone(result.ttft_content_s)

    def test_records_error_instead_of_raising(self):
        target = BackendTarget(name="rngd", kind="npu", base_url="http://x/v1", model="m")

        result = measure_stream(FailingClient(), target, "question_parse", MESSAGES, 64, FakeClock())

        self.assertFalse(result.ok)
        self.assertIn("ConnectionError", result.error)

    def test_empty_stream_is_error(self):
        clock = FakeClock()
        target = BackendTarget(name="rngd", kind="npu", base_url="http://x/v1", model="m")

        result = measure_stream(FakeClient(clock, tokens=()), target, "question_parse", MESSAGES, 64, clock)

        self.assertFalse(result.ok)


class TestUniquePrefix(unittest.TestCase):
    def test_each_request_gets_distinct_first_message(self):
        clock = FakeClock()
        client = FakeClient(clock)
        target = BackendTarget(name="gpu", kind="gpu", base_url="http://x/v1", model="m")
        messages = [{"role": "system", "content": "시스템"}, {"role": "user", "content": "질문"}]

        run_batch(client, target, "s", messages, runs=3, concurrency=1, max_tokens=8, clock=clock, unique_prefix=True)

        firsts = [call["messages"][0]["content"] for call in client.calls]
        self.assertEqual(3, len(set(firsts)))
        self.assertTrue(all(text.endswith("\n시스템") for text in firsts))
        self.assertTrue(all(call["messages"][1] == messages[1] for call in client.calls))
        self.assertEqual("시스템", messages[0]["content"])  # 원본은 바꾸지 않는다

    def test_default_sends_messages_unchanged(self):
        self.assertNotEqual(MESSAGES, with_unique_prefix(MESSAGES))
        clock = FakeClock()
        client = FakeClient(clock)
        target = BackendTarget(name="gpu", kind="gpu", base_url="http://x/v1", model="m")

        run_batch(client, target, "s", MESSAGES, runs=2, concurrency=1, max_tokens=8, clock=clock)

        self.assertEqual([MESSAGES, MESSAGES], [call["messages"] for call in client.calls])


class TestSummarizeBatch(unittest.TestCase):
    def test_hourly_hardware_cost_uses_wall_time(self):
        clock = FakeClock()
        target = BackendTarget(name="rngd", kind="npu", base_url="http://x/v1", model="m", usd_per_hour=3.6)

        batch = run_batch(FakeClient(clock), target, "rag_answer_birth_rate", MESSAGES, runs=4, concurrency=1, max_tokens=64, clock=clock)
        summary = summarize_batch(batch, target)

        # 4 요청 × 0.9초 = 3.6초 → $3.6/h × 3.6s = $0.0036
        self.assertAlmostEqual(3.6, batch.wall_s)
        self.assertAlmostEqual(0.0036 / 4 * 1000, summary["cost_usd_per_1k_requests"])
        self.assertAlmostEqual(0.0036 / 20 * 1_000_000, summary["cost_usd_per_1m_output_tokens"])
        self.assertAlmostEqual(20 / 3.6, summary["throughput_tokens_per_s"])
        self.assertAlmostEqual(0.5, summary["ttft_p50_s"])
        self.assertEqual(0, summary["errors"])
        self.assertAlmostEqual(100, summary["input_tokens_mean"])

    def test_api_cost_uses_token_prices(self):
        target = BackendTarget(
            name="priced",
            kind="api",
            base_url="http://x/v1",
            model="m",
            input_usd_per_1m=1.0,
            output_usd_per_1m=10.0,
        )
        request = RequestResult("priced", "question_parse", 0.2, 1.0, 1000, 100, False)
        batch = BatchResult("priced", "question_parse", 1, 1.0, (request, request))

        summary = summarize_batch(batch, target)

        # 요청당 1000×$1/1M + 100×$10/1M = $0.002
        self.assertAlmostEqual(2.0, summary["cost_usd_per_1k_requests"])

    def test_cost_is_none_without_prices_and_errors_are_counted(self):
        target = BackendTarget(name="gpu", kind="gpu", base_url="http://x/v1", model="m")
        ok = RequestResult("gpu", "question_parse", 0.2, 1.0, None, 10, True)
        failed = RequestResult("gpu", "question_parse", None, 0.1, None, 0, True, error="boom")
        batch = BatchResult("gpu", "question_parse", 1, 1.1, (ok, failed))

        summary = summarize_batch(batch, target)

        self.assertIsNone(summary["cost_usd_per_1k_requests"])
        self.assertEqual(1, summary["errors"])
        self.assertIsNone(summary["input_tokens_mean"])
        self.assertTrue(summary["tokens_estimated"])

    def test_rejects_unknown_config_keys(self):
        with self.assertRaises(ValueError):
            BackendTarget.from_dict({"name": "x", "kind": "gpu", "base_url": "u", "model": "m", "typo": 1})


class TestReport(unittest.TestCase):
    def test_write_report_creates_result_files(self):
        clock = FakeClock()
        target = BackendTarget(name="rngd", kind="npu", base_url="http://x/v1", model="m")
        batch = run_batch(FakeClient(clock), target, "rag_answer_birth_rate", MESSAGES, runs=2, concurrency=1, max_tokens=64, clock=clock)

        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp) / "run"
            write_report(output_dir, meta={"runs": 2}, summaries=[summarize_batch(batch, target)], batches=[batch])

            self.assertTrue((output_dir / "results.json").exists())
            self.assertEqual(3, len((output_dir / "requests.csv").read_text(encoding="utf-8-sig").splitlines()))
            self.assertIn("| rag_answer_birth_rate | rngd |", (output_dir / "summary.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
