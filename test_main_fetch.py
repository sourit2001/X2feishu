import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import main


class FetchTweetsTests(unittest.TestCase):
    def tearDown(self):
        main._twikit_client = None
        if main._twikit_loop is not None:
            main._twikit_loop.close()
            main._twikit_loop = None

    def test_client_bootstrap_session_receives_auth_cookie(self):
        fake_client = Mock()
        with patch.object(main, "TwikitClient", return_value=fake_client) as factory:
            client = main.get_twikit_client("auth-value", "csrf-value")

        self.assertIs(client, fake_client)
        client.set_cookies.assert_called_once_with(
            {"auth_token": "auth-value", "ct0": "csrf-value"}
        )
        factory.assert_called_once_with("en-US")

    def test_graphql_fetch_filters_nested_tweets_and_normalizes_rows(self):
        client = Mock()
        author = SimpleNamespace(name="Test User", screen_name="tester")
        rows = [SimpleNamespace(
            id="200",
            text="A new post",
            full_text="A new post",
            created_at="Sun Sep 06 01:00:00 +0000 2026",
            user=author,
            retweeted_tweet=None,
            quote=None,
        )]
        client.get_user_by_screen_name = AsyncMock(
            return_value=SimpleNamespace(id="123")
        )
        client.get_user_tweets = AsyncMock(return_value=rows)

        with patch.object(main, "get_twikit_client", return_value=client):
            tweets = main.fetch_tweets_via_graphql("tester", "auth", "csrf")

        self.assertEqual([tweet["id_str"] for tweet in tweets], ["200"])
        self.assertEqual(tweets[0]["author"], "Test User")
        self.assertFalse(tweets[0]["is_retweet"])
        client.get_user_tweets.assert_awaited_once_with("123", "Tweets", count=40)

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
