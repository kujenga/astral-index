"""Integration tests for all 6 scrapers: RSS, SNAPI, arXiv, Bluesky, Twitter, Reddit.

Each test injects canned HTTP responses via patch_http and verifies the full
fetch → parse → ContentItem field mapping path.
"""

from __future__ import annotations

from typing import Any

import httpx

from astral_core import ContentType, ExtractionMethod, SpaceCategory
from astral_ingest.scrapers.arxiv import ArxivScraper
from astral_ingest.scrapers.bluesky import BlueskyScraper
from astral_ingest.scrapers.reddit import RedditScraper
from astral_ingest.scrapers.rss import RSSFeedScraper
from astral_ingest.scrapers.snapi import SNAPIScraper
from astral_ingest.scrapers.twitter import TwitterScraper

# ---------------------------------------------------------------------------
# RSS scraper
# ---------------------------------------------------------------------------


class TestRSSScraper:
    """RSSFeedScraper integration tests."""

    def _make_scraper(self, **overrides: Any) -> RSSFeedScraper:
        config: dict[str, Any] = {
            "name": "SpaceNews",
            "url": "https://spacenews.com/feed",
            "content_type": "excerpt",
            **overrides,
        }
        return RSSFeedScraper(config)

    async def test_parses_entries_into_content_items(self, patch_http, canned):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, text=canned.minimal_rss_xml)

        patch_http(handler)
        scraper = self._make_scraper()
        items = await scraper.fetch()

        # 3rd entry has no <link>, should be skipped
        assert len(items) == 2
        assert items[0].title == "SpaceX Falcon 9 launches Starlink batch"
        assert items[0].source_name == "SpaceNews"
        assert items[0].content_type == ContentType.ARTICLE
        assert items[0].source_url == "https://spacenews.com/falcon9-starlink"
        assert items[0].author == "Jeff Foust"

    async def test_excerpt_mode_sets_body_text_none(self, patch_http, canned):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, text=canned.minimal_rss_xml)

        patch_http(handler)
        scraper = self._make_scraper(content_type="excerpt")
        items = await scraper.fetch()

        assert items[0].body_text is None
        assert items[0].excerpt is not None

    async def test_full_text_mode_keeps_body(self, patch_http, canned):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, text=canned.minimal_rss_xml)

        patch_http(handler)
        scraper = self._make_scraper(content_type="full_text")
        items = await scraper.fetch()

        assert items[0].body_text is not None

    async def test_304_conditional_get_returns_empty(self, patch_http):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(304, text="")

        patch_http(handler)
        scraper = self._make_scraper()
        items = await scraper.fetch()

        assert items == []

    async def test_category_hints_map_to_space_category(self, patch_http, canned):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, text=canned.minimal_rss_xml)

        patch_http(handler)
        scraper = self._make_scraper(
            category_hints=["launch_vehicles", "commercial_space"]
        )
        items = await scraper.fetch()

        assert SpaceCategory.LAUNCH_VEHICLES in items[0].categories
        assert SpaceCategory.COMMERCIAL_SPACE in items[0].categories

    async def test_entries_without_link_skipped(self, patch_http, canned):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, text=canned.minimal_rss_xml)

        patch_http(handler)
        scraper = self._make_scraper()
        items = await scraper.fetch()

        urls = [i.source_url for i in items]
        assert all("spacenews.com" in u for u in urls)


# ---------------------------------------------------------------------------
# SNAPI scraper
# ---------------------------------------------------------------------------


class TestSNAPIScraper:
    """SNAPIScraper integration tests."""

    async def test_parses_json_results(self, patch_http, canned):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=canned.snapi_response)

        patch_http(handler)
        scraper = SNAPIScraper(endpoints=["/articles/"])
        items = await scraper.fetch()

        assert len(items) == 2
        assert items[0].title == "NASA Selects New Science Missions"
        assert items[0].source_name == "NASA"
        assert items[0].source_url == "https://snapi.dev/articles/nasa-missions"
        assert items[0].content_type == ContentType.ARTICLE
        assert items[0].body_text == "NASA announced two new science missions today."

    async def test_since_filter_passes_param(self, patch_http, canned):
        from datetime import UTC, datetime

        captured_params: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            captured_params.append(str(request.url))
            return httpx.Response(200, json=canned.snapi_response)

        patch_http(handler)
        since = datetime(2026, 2, 28, tzinfo=UTC)
        scraper = SNAPIScraper(endpoints=["/articles/"], since=since)
        await scraper.fetch()

        assert any("published_at_gte" in p for p in captured_params)

    async def test_empty_results(self, patch_http):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"count": 0, "results": []})

        patch_http(handler)
        scraper = SNAPIScraper(endpoints=["/articles/"])
        items = await scraper.fetch()

        assert items == []


# ---------------------------------------------------------------------------
# arXiv scraper
# ---------------------------------------------------------------------------


class TestArxivScraper:
    """ArxivScraper integration tests."""

    def _make_scraper(self, keyword_filter: bool = True) -> ArxivScraper:
        feed_config = {
            "name": "astro-ph.EP",
            "url": "https://arxiv.org/rss/astro-ph.EP",
        }
        arxiv_config = {
            "keyword_filter": keyword_filter,
            "category_hints": ["space_science"],
        }
        return ArxivScraper(feed_config, arxiv_config)

    async def test_parses_entries_as_arxiv_paper(self, patch_http, canned):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, text=canned.arxiv_rss_xml)

        patch_http(handler)
        scraper = self._make_scraper(keyword_filter=False)
        items = await scraper.fetch()

        assert len(items) == 3
        assert all(i.content_type == ContentType.ARXIV_PAPER for i in items)
        assert all(i.extraction_method == ExtractionMethod.ARXIV_RSS for i in items)
        assert items[0].source_name == "arXiv: astro-ph.EP"

    async def test_arxiv_id_extracted(self, patch_http, canned):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, text=canned.arxiv_rss_xml)

        patch_http(handler)
        scraper = self._make_scraper(keyword_filter=False)
        items = await scraper.fetch()

        assert items[0].arxiv_id == "2401.12345"
        assert items[1].arxiv_id == "2401.67890"

    async def test_keyword_filter_includes_matching(self, patch_http, canned):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, text=canned.arxiv_rss_xml)

        patch_http(handler)
        scraper = self._make_scraper(keyword_filter=True)
        items = await scraper.fetch()

        # "exoplanet" and "Mars" match, "Quantum" does not
        titles = [i.title for i in items]
        assert any("Exoplanet" in t for t in titles)
        assert any("Mars" in t for t in titles)

    async def test_keyword_filter_excludes_nonmatching(self, patch_http, canned):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, text=canned.arxiv_rss_xml)

        patch_http(handler)
        scraper = self._make_scraper(keyword_filter=True)
        items = await scraper.fetch()

        titles = [i.title for i in items]
        assert not any("Quantum" in t for t in titles)


# ---------------------------------------------------------------------------
# Bluesky scraper
# ---------------------------------------------------------------------------


class TestBlueskyScraper:
    """BlueskyScraper integration tests."""

    async def test_resolves_handle_and_fetches_feed(self, patch_http, canned):
        def handler(request: httpx.Request) -> httpx.Response:
            url = str(request.url)
            if "resolveHandle" in url:
                return httpx.Response(200, json=canned.bluesky_resolve_response)
            if "getAuthorFeed" in url:
                return httpx.Response(200, json=canned.bluesky_feed_response)
            return httpx.Response(404)

        patch_http(handler)
        scraper = BlueskyScraper({"accounts": ["spaceuser.bsky.social"], "limit": 30})
        items = await scraper.fetch()

        # 3 feed items: 1 original, 1 repost (skipped), 1 original = 2
        assert len(items) == 2
        assert items[0].social_author_handle == "spaceuser.bsky.social"
        assert items[0].extraction_method == ExtractionMethod.BLUESKY_API

    async def test_skips_reposts(self, patch_http, canned):
        def handler(request: httpx.Request) -> httpx.Response:
            url = str(request.url)
            if "resolveHandle" in url:
                return httpx.Response(200, json=canned.bluesky_resolve_response)
            if "getAuthorFeed" in url:
                return httpx.Response(200, json=canned.bluesky_feed_response)
            return httpx.Response(404)

        patch_http(handler)
        scraper = BlueskyScraper({"accounts": ["spaceuser.bsky.social"]})
        items = await scraper.fetch()

        # Repost text "Shared a cool post" should not appear
        assert not any("Shared a cool post" in (i.body_text or "") for i in items)

    async def test_extracts_embedded_link_as_canonical(self, patch_http, canned):
        def handler(request: httpx.Request) -> httpx.Response:
            url = str(request.url)
            if "resolveHandle" in url:
                return httpx.Response(200, json=canned.bluesky_resolve_response)
            if "getAuthorFeed" in url:
                return httpx.Response(200, json=canned.bluesky_feed_response)
            return httpx.Response(404)

        patch_http(handler)
        scraper = BlueskyScraper({"accounts": ["spaceuser.bsky.social"]})
        items = await scraper.fetch()

        # First post has an external embed link
        assert items[0].canonical_url == "https://spacenews.com/falcon9-launch"

    async def test_handle_resolution_failure_graceful(self, patch_http):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(500, text="Internal Server Error")

        patch_http(handler)
        scraper = BlueskyScraper({"accounts": ["bad.handle"]})
        items = await scraper.fetch()

        assert items == []


# ---------------------------------------------------------------------------
# Twitter scraper
# ---------------------------------------------------------------------------


class TestTwitterScraper:
    """TwitterScraper integration tests."""

    async def test_no_api_key_returns_empty(self):
        """Without SOCIALDATA_API_KEY, fetch() returns []."""
        scraper = TwitterScraper({"accounts": ["spacex"], "min_likes": 5})
        items = await scraper.fetch()
        assert items == []

    async def test_parses_tweets_with_engagement(self, patch_http, canned, monkeypatch):
        monkeypatch.setenv("SOCIALDATA_API_KEY", "test-key")

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=canned.twitter_response)

        patch_http(handler)
        scraper = TwitterScraper({"accounts": ["spacex"], "min_likes": 5})
        items = await scraper.fetch()

        # Only tweet id 1234567890 passes all filters (not RT, not reply, >= 5 likes)
        assert len(items) == 1
        assert items[0].tweet_id == "1234567890"
        assert items[0].tweet_engagement == 600  # 500 likes + 100 RTs
        assert items[0].content_type == ContentType.TWEET

    async def test_filters_retweets_and_replies(self, patch_http, canned, monkeypatch):
        monkeypatch.setenv("SOCIALDATA_API_KEY", "test-key")

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=canned.twitter_response)

        patch_http(handler)
        scraper = TwitterScraper({"accounts": ["spacex"], "min_likes": 5})
        items = await scraper.fetch()

        ids = [i.tweet_id for i in items]
        assert "1234567891" not in ids  # retweet
        assert "1234567892" not in ids  # reply

    async def test_filters_below_min_likes(self, patch_http, canned, monkeypatch):
        monkeypatch.setenv("SOCIALDATA_API_KEY", "test-key")

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=canned.twitter_response)

        patch_http(handler)
        scraper = TwitterScraper({"accounts": ["spacex"], "min_likes": 5})
        items = await scraper.fetch()

        ids = [i.tweet_id for i in items]
        assert "1234567893" not in ids  # only 2 likes


# ---------------------------------------------------------------------------
# Reddit scraper (uses asyncpraw mock)
# ---------------------------------------------------------------------------


class MockComment:
    def __init__(self, body: str, author: str = "some_user"):
        self.body = body
        self.author = author


class MockSubmission:
    def __init__(
        self,
        *,
        title: str,
        score: int,
        permalink: str,
        is_self: bool = False,
        selftext: str = "",
        url: str = "",
        stickied: bool = False,
        subreddit: str = "spacex",
        author: str = "test_user",
        created_utc: float = 1709290800.0,  # 2024-03-01
    ):
        self.title = title
        self.score = score
        self.permalink = permalink
        self.is_self = is_self
        self.selftext = selftext
        self.url = url
        self.stickied = stickied
        self.subreddit = subreddit
        self.author = author
        self.created_utc = created_utc
        self.comment_sort = "best"
        self.comments = MockCommentForest()


class MockCommentForest:
    async def replace_more(self, limit=0):
        pass

    def __iter__(self):
        return iter([MockComment("Great post!", "commenter1")])


class MockSubreddit:
    def __init__(self, submissions: list[MockSubmission]):
        self._submissions = submissions

    def hot(self, limit: int = 50):
        return MockAsyncIterator(self._submissions[:limit])


class MockAsyncIterator:
    def __init__(self, items):
        self._items = iter(items)

    def __aiter__(self):
        return self

    async def __anext__(self):
        try:
            return next(self._items)
        except StopIteration:
            raise StopAsyncIteration from None


class MockReddit:
    def __init__(self, subreddit: MockSubreddit):
        self._subreddit = subreddit

    async def subreddit(self, name: str) -> MockSubreddit:
        return self._subreddit

    async def close(self):
        pass


class TestRedditScraper:
    """RedditScraper integration tests."""

    async def test_no_credentials_returns_empty(self):
        """Without REDDIT_CLIENT_ID, fetch() returns []."""
        scraper = RedditScraper({"subreddits": ["spacex"], "score_threshold": 50})
        items = await scraper.fetch()
        assert items == []

    async def test_parses_submissions(self, monkeypatch):
        monkeypatch.setenv("REDDIT_CLIENT_ID", "test-id")
        monkeypatch.setenv("REDDIT_CLIENT_SECRET", "test-secret")

        submissions = [
            MockSubmission(
                title="Starship orbital flight test",
                score=5000,
                permalink="/r/spacex/comments/abc/starship/",
                is_self=True,
                selftext="Discussion about the flight.",
            ),
        ]
        mock_reddit = MockReddit(MockSubreddit(submissions))
        monkeypatch.setattr(
            "astral_ingest.scrapers.reddit.asyncpraw.Reddit",
            lambda **kwargs: mock_reddit,
        )

        scraper = RedditScraper({"subreddits": ["spacex"], "score_threshold": 50})
        items = await scraper.fetch()

        assert len(items) == 1
        assert items[0].title == "Starship orbital flight test"
        assert items[0].content_type == ContentType.REDDIT_POST
        assert items[0].reddit_score == 5000

    async def test_filters_stickied_and_low_score(self, monkeypatch):
        monkeypatch.setenv("REDDIT_CLIENT_ID", "test-id")
        monkeypatch.setenv("REDDIT_CLIENT_SECRET", "test-secret")

        submissions = [
            MockSubmission(
                title="Stickied post",
                score=10000,
                permalink="/r/spacex/comments/stick/",
                stickied=True,
            ),
            MockSubmission(
                title="Low score post",
                score=10,
                permalink="/r/spacex/comments/low/",
            ),
            MockSubmission(
                title="Good post",
                score=200,
                permalink="/r/spacex/comments/good/",
            ),
        ]
        mock_reddit = MockReddit(MockSubreddit(submissions))
        monkeypatch.setattr(
            "astral_ingest.scrapers.reddit.asyncpraw.Reddit",
            lambda **kwargs: mock_reddit,
        )

        scraper = RedditScraper({"subreddits": ["spacex"], "score_threshold": 50})
        items = await scraper.fetch()

        assert len(items) == 1
        assert items[0].title == "Good post"

    async def test_self_post_has_body_vs_link_post(self, monkeypatch):
        monkeypatch.setenv("REDDIT_CLIENT_ID", "test-id")
        monkeypatch.setenv("REDDIT_CLIENT_SECRET", "test-secret")

        submissions = [
            MockSubmission(
                title="Self post",
                score=500,
                permalink="/r/spacex/comments/self/",
                is_self=True,
                selftext="Self post body text here.",
            ),
            MockSubmission(
                title="Link post",
                score=500,
                permalink="/r/spacex/comments/link/",
                is_self=False,
                url="https://spacenews.com/article",
            ),
        ]
        mock_reddit = MockReddit(MockSubreddit(submissions))
        monkeypatch.setattr(
            "astral_ingest.scrapers.reddit.asyncpraw.Reddit",
            lambda **kwargs: mock_reddit,
        )

        scraper = RedditScraper({"subreddits": ["spacex"], "score_threshold": 50})
        items = await scraper.fetch()

        self_item = next(i for i in items if i.title == "Self post")
        link_item = next(i for i in items if i.title == "Link post")

        assert self_item.body_text == "Self post body text here."
        assert self_item.extraction_method == ExtractionMethod.REDDIT_SELF

        assert link_item.body_text is None
        assert link_item.extraction_method == ExtractionMethod.REDDIT_LINK
        assert link_item.canonical_url == "https://spacenews.com/article"
