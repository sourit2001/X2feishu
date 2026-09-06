import unittest
from unittest.mock import Mock, patch

import main


class FetchTweetsTests(unittest.TestCase):
    def tearDown(self):
        main._tweetkit_client = None

    def test_graphql_fetch_filters_nested_tweets_and_normalizes_rows(self):
        client = Mock()
        client.get_tweets.return_value = [
            {
                "id": "200",
                "text": "A new post",
                "created_at": "Sun Sep 06 01:00:00 +0000 2026",
                "author": "tester",
                "url": "https://x.com/tester/status/200",
            },
            {
                "id": "199",
                "text": "Nested quoted post",
                "created_at": "Sun Sep 06 00:59:00 +0000 2026",
                "author": "someone_else",
                "url": "https://x.com/someone_else/status/199",
            },
        ]

        with patch.object(main, "get_tweetkit_client", return_value=client):
            tweets = main.fetch_tweets_via_graphql("tester", "auth", "csrf")

        self.assertEqual([tweet["id_str"] for tweet in tweets], ["200"])
        self.assertEqual(tweets[0]["author"], "tester")
        self.assertFalse(tweets[0]["is_retweet"])
        client.get_tweets.assert_called_once_with(
            username="tester", limit=40, include_replies=True
        )

    def test_fetch_uses_syndication_only_when_graphql_fails(self):
        fallback = [{"id": 1, "id_str": "1"}]
        with patch.object(
            main, "fetch_tweets_via_graphql", side_effect=RuntimeError("blocked")
        ), patch.object(
            main, "fetch_tweets_via_syndication", return_value=fallback
        ) as syndication:
            self.assertEqual(main.fetch_tweets("tester", "auth", "csrf"), fallback)

        syndication.assert_called_once_with("tester", "auth", "csrf")


if __name__ == "__main__":
    unittest.main()
