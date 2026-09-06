import os
import unittest
from unittest import mock

import main


class MonitorBatchTests(unittest.TestCase):
    def test_three_batches_cover_every_account_once(self):
        bloggers = [
            {"username": f"user{index}", "nickname": f"User {index}"}
            for index in range(26)
        ]
        batches = []

        for batch_index in range(3):
            with mock.patch.dict(
                os.environ,
                {
                    "MONITOR_BATCH_INDEX": str(batch_index),
                    "MONITOR_BATCH_COUNT": "3",
                },
                clear=False,
            ):
                batches.append(main.get_scheduled_bloggers(bloggers))

        self.assertEqual([len(batch) for batch in batches], [9, 9, 8])
        usernames = [
            item["username"]
            for batch in batches
            for item in batch
        ]
        self.assertEqual(len(usernames), len(set(usernames)))
        self.assertEqual(set(usernames), {item["username"] for item in bloggers})

    def test_manual_all_mode_keeps_full_list(self):
        bloggers = [{"username": "one", "nickname": "One"}]
        with mock.patch.dict(os.environ, {"MONITOR_BATCH_INDEX": "all"}, clear=False):
            self.assertEqual(main.get_scheduled_bloggers(bloggers), bloggers)

    @mock.patch("main.requests.get")
    def test_rate_limit_is_not_retried(self, get):
        response = mock.Mock(status_code=429)
        response.raise_for_status.side_effect = main.requests.HTTPError("429")
        get.return_value = response

        with self.assertRaises(main.XRateLimitError):
            main.fetch_tweets("example", "auth", "ct0")

        self.assertEqual(get.call_count, 2)

    @mock.patch("main.requests.get")
    def test_fxtwitter_is_primary_and_does_not_send_x_cookies(self, get):
        response = mock.Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {
            "results": [
                {
                    "type": "status",
                    "id": "2096605093986787380",
                    "text": "Fresh post",
                    "url": "https://x.com/example/status/2096605093986787380",
                    "created_at": "Sun Sep 06 14:23:02 +0000 2026",
                    "author": {"name": "Example", "screen_name": "example"},
                    "quote": {
                        "text": "Quoted post",
                        "author": {"name": "Quoted", "screen_name": "quoted"},
                    },
                }
            ]
        }
        get.return_value = response

        tweets = main.fetch_tweets("example", "private-auth", "private-ct0")

        self.assertEqual(tweets[0]["id_str"], "2096605093986787380")
        self.assertEqual(tweets[0]["quoted_tweet"]["username"], "quoted")
        self.assertFalse(tweets[0]["is_retweet"])
        _, kwargs = get.call_args
        self.assertNotIn("Cookie", kwargs["headers"])
        self.assertIn("api.fxtwitter.com", get.call_args.args[0])


if __name__ == "__main__":
    unittest.main()
