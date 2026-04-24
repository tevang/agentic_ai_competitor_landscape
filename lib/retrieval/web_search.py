"""Config-driven Tavily search and fetched-page text retrieval."""

import json
import os
from collections import OrderedDict
from typing import Any

import trafilatura
from tavily import TavilyClient

from lib.config import AppConfig
from lib.utils.text_utils import clean_text, unique_preserve_order


class WebSearchService:
    """Search the web with Tavily and fetch cleaned page text with configurable caching."""

    def __init__(self, config: AppConfig) -> None:
        """Initialize Tavily and the local search/page-text caches."""

        api_key = os.getenv(config.tavily.api_key_env_var)
        if not api_key:
            raise RuntimeError(f"Missing environment variable: {config.tavily.api_key_env_var}")

        self.config = config
        self.client = TavilyClient(api_key=api_key)
        self.search_cache: OrderedDict[str, list[dict[str, Any]]] = OrderedDict()
        self.fetch_cache: OrderedDict[str, str] = OrderedDict()

    def search(
        self,
        query: str,
        max_results_override: int | None = None,
        include_domains_override: list[str] | None = None,
        exclude_domains_override: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Execute a Tavily search using the configured search controls and optional domain overrides."""

        payload = self._build_search_payload(
            query=query,
            max_results_override=max_results_override,
            include_domains_override=include_domains_override,
            exclude_domains_override=exclude_domains_override,
        )
        cache_key = json.dumps(payload, sort_keys=True)
        cached = self._get_cached_value(self.search_cache, cache_key)
        if cached is not None:
            return cached

        result = self.client.search(**payload)
        results = result.get("results", [])
        self._set_cached_value(self.search_cache, cache_key, results, self.config.tavily.search_cache_size)
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
                include_links=self.config.tavily.trafilatura_include_links,
                include_images=self.config.tavily.trafilatura_include_images,
            )
            cleaned = clean_text(extracted)[: self.config.get_active_search_profile().page_text_char_limit]
            self._set_cached_value(self.fetch_cache, url, cleaned, self.config.tavily.fetch_cache_size)
            return cleaned
        except Exception:
            return ""

    def _build_search_payload(
        self,
        query: str,
        max_results_override: int | None,
        include_domains_override: list[str] | None,
        exclude_domains_override: list[str] | None,
    ) -> dict[str, Any]:
        """Build the Tavily request payload from the YAML configuration and method overrides."""

        profile = self.config.get_active_search_profile()
        include_domains = unique_preserve_order((self.config.tavily.include_domains or []) + (include_domains_override or []))
        exclude_domains = unique_preserve_order((self.config.tavily.exclude_domains or []) + (exclude_domains_override or []))

        payload: dict[str, Any] = {
            "query": query,
            "topic": self.config.tavily.topic,
            "search_depth": profile.search_depth,
            "max_results": max_results_override or profile.default_max_results,
            "auto_parameters": self.config.tavily.auto_parameters,
            "exact_match": self.config.tavily.exact_match,
            "include_answer": self.config.tavily.include_answer,
            "include_raw_content": self.config.tavily.include_raw_content,
            "include_images": self.config.tavily.include_images,
            "include_image_descriptions": self.config.tavily.include_image_descriptions,
            "include_favicon": self.config.tavily.include_favicon,
            "include_usage": self.config.tavily.include_usage,
            "include_domains": include_domains,
            "exclude_domains": exclude_domains,
            "country": self.config.tavily.country,
            "time_range": self.config.tavily.time_range,
            "days": self.config.tavily.days,
            "start_date": self.config.tavily.start_date,
            "end_date": self.config.tavily.end_date,
        }

        if profile.chunks_per_source is not None and profile.search_depth == "advanced":
            payload["chunks_per_source"] = profile.chunks_per_source

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