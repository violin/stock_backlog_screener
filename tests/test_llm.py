import unittest
from unittest.mock import patch

from backlog_screener.llm import GeminiClient, build_llm_client
from backlog_screener.settings import AppSettings


class FakeResponse:
    status_code = 200
    headers = {}

    def __init__(self, payload):
        self.payload = payload

    def json(self):
        return self.payload

    def raise_for_status(self):
        return None


class GeminiClientTests(unittest.TestCase):
    def test_summarize_filing_signal_parses_gemini_text_response(self):
        payload = {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {
                                "text": (
                                    '{"summary":"订单积压改善。","importance_score":82,'
                                    '"sentiment_score":21,"confidence_score":74}'
                                )
                            }
                        ]
                    }
                }
            ]
        }
        client = GeminiClient(api_key="test-key", model="gemini-test")

        with patch("backlog_screener.llm.requests.post", return_value=FakeResponse(payload)) as post:
            summary = client.summarize_filing_signal(
                ticker="TEST",
                title="TEST 10-Q",
                text="Backlog increased during the quarter.",
            )

        self.assertEqual(summary.provider, "gemini")
        self.assertEqual(summary.summary, "订单积压改善。")
        self.assertEqual(summary.importance_score, 82)
        call = post.call_args
        self.assertIn("/models/gemini-test:generateContent", call.args[0])
        self.assertEqual(call.kwargs["headers"]["x-goog-api-key"], "test-key")
        self.assertIn("contents", call.kwargs["json"])
        self.assertIn("只输出 JSON", call.kwargs["json"]["contents"][0]["parts"][0]["text"])

    def test_build_llm_client_uses_gemini_provider(self):
        settings = AppSettings(
            database_url="postgresql://example",
            sec_user_agent=None,
            futu_host="127.0.0.1",
            futu_port=11111,
            futu_market="US",
            llm_provider="gemini",
            minimax_base_url="https://minimax.example/v1",
            minimax_model="minimax-test",
            minimax_api="anthropic-messages",
            minimax_api_key=None,
            minimax_retries=1,
            minimax_retry_wait_seconds=30,
            gemini_base_url="https://gemini.example/v1beta",
            gemini_model="gemini-test",
            gemini_api_key="gemini-key",
            gemini_retries=2,
            gemini_retry_wait_seconds=5,
        )

        client = build_llm_client(settings)

        self.assertIsInstance(client, GeminiClient)
        self.assertEqual(client.model, "gemini-test")
        self.assertEqual(client.retries, 2)


if __name__ == "__main__":
    unittest.main()
