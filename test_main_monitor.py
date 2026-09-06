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
        get.return_value = response

        with self.assertRaises(main.XRateLimitError):
            main.fetch_tweets("example", "auth", "ct0")

        get.assert_called_once()


if __name__ == "__main__":
    unittest.main()
