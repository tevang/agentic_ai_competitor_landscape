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

    def __init__(self, config: OpenAIConfig, verbosity: int = 0) -> None:
        """Initialize the OpenAI client using the API key named in the configuration."""

        api_key = os.getenv(config.api_key_env_var)
        if not api_key:
            raise RuntimeError(f"Missing environment variable: {config.api_key_env_var}")

        self.config = config
        self.verbosity = verbosity
        self.client = OpenAI(api_key=api_key)
        self.call_count = 0
        self.estimated_prompt_tokens = 0
        self.estimated_output_tokens = 0

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
                self.call_count += 1
                prompt_token_estimate = max(1, len(prompt) // 4)
                self.estimated_prompt_tokens += prompt_token_estimate

                if self.verbosity >= 1:
                    print(
                        "[usage] "
                        f"OpenAI call #{self.call_count}: "
                        f"model={self.config.model}, "
                        f"prompt_chars={len(prompt)}, "
                        f"prompt_tokens_est~{prompt_token_estimate}"
                    )

                response = self.client.responses.create(
                    model=self.config.model,
                    input=prompt,
                )
                output_text = response.output_text or ""
                output_token_estimate = max(1, len(output_text) // 4)
                self.estimated_output_tokens += output_token_estimate

                if self.verbosity >= 1:
                    usage = getattr(response, "usage", None)
                    if usage:
                        print(f"[usage] OpenAI response usage: {usage}")
                    else:
                        print(
                            "[usage] "
                            f"OpenAI output_tokens_est~{output_token_estimate}; "
                            f"session_prompt_tokens_est~{self.estimated_prompt_tokens}; "
                            f"session_output_tokens_est~{self.estimated_output_tokens}"
                        )

                return output_text

        raise RuntimeError("LLM request failed after all retry attempts.")

    def ask_json(self, prompt: str) -> Any:
        """Run a prompt, recover the JSON payload, and deserialize it into Python objects."""

        raw = self.ask(prompt + "\n\nReturn valid JSON only. Do not add commentary.")
        json_blob = extract_json_blob(raw)
        return json.loads(json_blob)