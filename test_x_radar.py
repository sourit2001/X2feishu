import unittest

from x_radar import normalize_posts


class RadarTests(unittest.TestCase):
    def test_normalize_scores_deduplicates_later(self):
        rows = normalize_posts({"data": [{"id": "1", "author_id": "u", "text": "I wish there was a tool",
            "public_metrics": {"like_count": 10, "retweet_count": 2, "reply_count": 1}}]})
        self.assertEqual(rows[0]["url"], "https://x.com/i/status/1")
        self.assertTrue(rows[0]["product_signal"])
        self.assertGreater(rows[0]["score"], 0)


if __name__ == "__main__":
    unittest.main()
