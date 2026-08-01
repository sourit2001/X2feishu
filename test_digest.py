import json
import os
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

import digest


def completion(content, finish_reason="stop"):
    return SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(content=content),
                finish_reason=finish_reason,
            )
        ]
    )


class DigestTests(unittest.TestCase):
    @patch("digest.OpenAI")
    def test_generate_summary_disables_thinking_and_retries_empty_content(self, openai):
        create = openai.return_value.chat.completions.create
        create.side_effect = [completion("", "length"), completion("  valid digest  ")]

        result = digest.generate_summary("prompt", "key")

        self.assertEqual(result, "valid digest")
        self.assertEqual(create.call_count, 2)
        for call in create.call_args_list:
            self.assertEqual(
                call.kwargs["extra_body"],
                {"thinking": {"type": "disabled"}},
            )

    @patch("digest.OpenAI")
    def test_generate_summary_raises_after_repeated_empty_content(self, openai):
        openai.return_value.chat.completions.create.return_value = completion("")

        with self.assertRaisesRegex(RuntimeError, "tweet queue preserved"):
            digest.generate_summary("prompt", "key")

    def test_send_to_feishu_rejects_business_error(self):
        response = Mock(status_code=200)
        response.json.return_value = {"code": 19001, "msg": "invalid card"}

        with patch("digest.requests.post", return_value=response):
            with self.assertRaisesRegex(RuntimeError, "Feishu rejected"):
                digest.send_to_feishu("https://example.invalid", {})

    def test_main_preserves_queue_when_summary_is_empty(self):
        tweets = [
            {
                "nickname": "测试博主",
                "username": "tester",
                "text": "hello",
                "url": "https://x.com/tester/status/1",
                "time": "2026-08-01 10:00",
            }
        ]

        with tempfile.TemporaryDirectory() as temp_dir:
            queue_path = os.path.join(temp_dir, "daily_tweets.json")
            with open(queue_path, "w", encoding="utf-8") as file:
                json.dump(tweets, file, ensure_ascii=False)

            with patch.object(digest, "DAILY_TWEETS_FILE", queue_path), patch.dict(
                os.environ,
                {
                    "DEEPSEEK_API_KEY": "test-key",
                    "FEISHU_WEBHOOK": "https://example.invalid",
                },
                clear=False,
            ), patch.object(
                digest,
                "generate_summary",
                side_effect=RuntimeError("empty digest"),
            ):
                with self.assertRaisesRegex(RuntimeError, "empty digest"):
                    digest.main()

            with open(queue_path, "r", encoding="utf-8") as file:
                self.assertEqual(json.load(file), tweets)


if __name__ == "__main__":
    unittest.main()
