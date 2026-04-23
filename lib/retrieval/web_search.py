"""Config-driven Tavily search and fetched-page text retrieval."""

import json
import os
from collections import OrderedDict
from typing import Any

import trafilatura
from tavily import TavilyClient

from lib.config import TavilyConfig
from lib.utils.text_utils import clean_text


class WebSearchService:
    """Search the web with Tavily and fetch cleaned page text with configurable caching."""

    def __init__(self, config: TavilyConfig) -> None:
        """Initialize Tavily and the local search/page-text caches."""

        api_key = os.getenv(config.api_key_env_var)
        if not api_key:
            raise RuntimeError(f"Missing environment variable: {config.api_key_env_var}")

        self.config = config
        self.client = TavilyClient(api_key=api_key)
        self.search_cache: OrderedDict[str, list[dict[str, Any]]] = OrderedDict()
        self.fetch_cache: OrderedDict[str, str] = OrderedDict()

    def search(self, query: str, max_results_override: int | None = None) -> list[dict[str, Any]]:
        """Execute a Tavily search using the configured search controls."""

        payload = self._build_search_payload(query, max_results_override)
        cache_key = json.dumps(payload, sort_keys=True)
        cached = self._get_cached_value(self.search_cache, cache_key)
        if cached is not None:
            return cached

        result = self.client.search(**payload)
        results = result.get("results", [])
        self._set_cached_value(self.search_cache, cache_key, results, self.config.search_cache_size)
        return results

    def fetch_page_text(self, url: str) -> str:
        """Fetch, extract, and truncate page text for a single URL."""

        cached = self._get_cached_value(self.fetch_cache, url)
        if cached is not None:
            return cached

        try:
            downloaded = trafilatura.fetch_url(url)
            if not downloaded:
                return ""

            extracted = trafilatura.extract(
                downloaded,
                include_links=self.config.trafilatura_include_links,
                include_images=self.config.trafilatura_include_images,
            )
            cleaned = clean_text(extracted)[: self.config.page_text_char_limit]
            self._set_cached_value(self.fetch_cache, url, cleaned, self.config.fetch_cache_size)
            return cleaned
        except Exception:
            return ""

    def _build_search_payload(self, query: str, max_results_override: int | None) -> dict[str, Any]:
        """Build the Tavily request payload from the YAML configuration and method overrides."""

        payload: dict[str, Any] = {
            "query": query,
            "topic": self.config.topic,
            "search_depth": self.config.search_depth,
            "max_results": max_results_override or self.config.default_max_results,
            "auto_parameters": self.config.auto_parameters,
            "exact_match": self.config.exact_match,
            "include_answer": self.config.include_answer,
            "include_raw_content": self.config.include_raw_content,
            "include_images": self.config.include_images,
            "include_image_descriptions": self.config.include_image_descriptions,
            "include_favicon": self.config.include_favicon,
            "include_usage": self.config.include_usage,
            "include_domains": self.config.include_domains,
            "exclude_domains": self.config.exclude_domains,
            "country": self.config.country,
            "time_range": self.config.time_range,
            "days": self.config.days,
            "start_date": self.config.start_date,
            "end_date": self.config.end_date,
        }

        if self.config.chunks_per_source is not None and self.config.search_depth in {"advanced", "fast"}:
            payload["chunks_per_source"] = self.config.chunks_per_source

        return {key: value for key, value in payload.items() if value not in (None, [], {})}

    def _get_cached_value(self, cache: OrderedDict[str, Any], key: str) -> Any:
        """Return a cached value and refresh its recency if it exists."""

        if key not in cache:
            return None

        value = cache.pop(key)
        cache[key] = value
        return value

    def _set_cached_value(self, cache: OrderedDict[str, Any], key: str, value: Any, max_size: int) -> None:
        """Store a value in the cache and evict the oldest item when the cache is full."""

        if max_size <= 0:
            return

        if key in cache:
            cache.pop(key)
        cache[key] = value

        while len(cache) > max_size:
            cache.popitem(last=False)