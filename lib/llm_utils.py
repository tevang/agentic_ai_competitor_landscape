import trafilatura
from openai import OpenAI
from tavily import TavilyClient
from tenacity import retry, stop_after_attempt, wait_exponential
from lib.utils import extract_json_blob

class LLM:
    """
    A wrapper around the OpenAI client for easier prompting and JSON extraction.
    """
    def __init__(self, client: OpenAI, model: str):
        self.client = client
        self.model = model

    @retry(wait=wait_exponential(min=1, max=15), stop=stop_after_attempt(3))
    def ask(self, prompt: str) -> str:
        """
        Sends a prompt to the LLM and returns the text response.
        """
        response = self.client.responses.create(
            model=self.model,
            input=prompt,
        )
        return response.output_text

    def ask_json(self, prompt: str) -> dict:
        """
        Sends a prompt to the LLM and expects a JSON response, which it parses and returns.
        """
        res = self.ask(prompt + "\n\nReturn valid JSON only. Do not add commentary.")
        return extract_json_blob(res)


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10))
def search_web(tavily_client: TavilyClient, query: str, max_results: int = 5) -> list[dict]:
    """
    Searches the web using the Tavily API.
    """
    response = tavily_client.search(query, search_depth="smart", max_results=max_results)
    return response.get("results", [])


def fetch_page_text(url: str) -> str:
    """
    Fetches the text content of a web page using trafilatura.
    """
    try:
        downloaded = trafilatura.fetch_url(url)
        if not downloaded:
            return ""
        return trafilatura.extract(downloaded) or ""
    except Exception:
        return ""
