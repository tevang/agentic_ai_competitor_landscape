"""OpenAI Responses API wrapper with configurable retry behavior."""

import json
import os
from typing import Any

from openai import OpenAI
from tenacity import Retrying, stop_after_attempt, wait_exponential

from lib.config import OpenAIConfig
from lib.utils.text_utils import extract_json_blob


class LLM:
    """Thin wrapper around the OpenAI Responses API for text and JSON prompting."""

    def __init__(self, config: OpenAIConfig) -> None:
        """Initialize the OpenAI client using the API key named in the configuration."""

        api_key = os.getenv(config.api_key_env_var)
        if not api_key:
            raise RuntimeError(f"Missing environment variable: {config.api_key_env_var}")

        self.config = config
        self.client = OpenAI(api_key=api_key)

    def ask(self, prompt: str) -> str:
        """Run a text prompt against the configured model and return the aggregated text output."""

        retrying = Retrying(
            stop=stop_after_attempt(self.config.retry_attempts),
            wait=wait_exponential(
                min=self.config.retry_wait_min_seconds,
                max=self.config.retry_wait_max_seconds,
            ),
            reraise=True,
        )

        for attempt in retrying:
            with attempt:
                response = self.client.responses.create(
                    model=self.config.model,
                    input=prompt,
                )
                return response.output_text

        raise RuntimeError("LLM request failed after all retry attempts.")

    def ask_json(self, prompt: str) -> Any:
        """Run a prompt, recover the JSON payload, and deserialize it into Python objects."""

        raw = self.ask(prompt + "\n\nReturn valid JSON only. Do not add commentary.")
        json_blob = extract_json_blob(raw)
        return json.loads(json_blob)