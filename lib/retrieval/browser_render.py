"""Optional browser-render fallback for normal JavaScript-rendered pages."""

from lib.config import AppConfig
from lib.models import PageFetchResult
from lib.retrieval.page_quality import assess_extracted_content


class BrowserRenderService:
    """Render a page in a real browser when basic extraction returns placeholders or low-content text.

    This helper is intentionally conservative:
    - it is only used for ordinary JavaScript-rendered pages,
    - it does not attempt CAPTCHA solving,
    - it does not attempt Cloudflare or anti-bot bypass,
    - it simply renders the page and reads visible text when allowed.
    """

    def __init__(self, config: AppConfig) -> None:
        """Store configuration for the optional browser-render fallback."""

        self.config = config

    def render_page(self, url: str) -> PageFetchResult:
        """Render a page with Playwright when the dependency is installed and allowed."""

        if not self.config.retrieval_guard.allow_browser_render_fallback:
            return PageFetchResult(
                text="",
                extraction_status="browser_render_disabled",
                blocked_reason="Browser-render fallback disabled by configuration.",
                render_mode="playwright",
                quality_score=0.0,
            )

        try:
            from playwright.sync_api import sync_playwright
        except Exception:
            return PageFetchResult(
                text="",
                extraction_status="browser_render_unavailable",
                blocked_reason="Playwright is not installed.",
                render_mode="playwright",
                quality_score=0.0,
            )

        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=self.config.retrieval_guard.browser_headless)
                context = browser.new_context(
                    user_agent=self.config.retrieval_guard.browser_user_agent,
                    locale="en-US",
                )
                page = context.new_page()
                page.goto(
                    url,
                    wait_until=self.config.retrieval_guard.browser_wait_until,
                    timeout=self.config.retrieval_guard.browser_render_timeout_ms,
                )
                page.wait_for_load_state(
                    "domcontentloaded",
                    timeout=self.config.retrieval_guard.browser_render_timeout_ms,
                )
                raw_text = page.evaluate("() => document.body ? document.body.innerText : ''")
                raw_html = page.content()
                context.close()
                browser.close()

            assessment = assess_extracted_content(
                url=url,
                raw_text=raw_text,
                raw_html=raw_html,
                config=self.config.retrieval_guard,
            )
            if assessment.is_usable:
                return PageFetchResult(
                    text=assessment.cleaned_text,
                    extraction_status="browser_rendered",
                    blocked_reason="",
                    render_mode="playwright",
                    quality_score=assessment.quality_score,
                )

            return PageFetchResult(
                text="",
                extraction_status=assessment.status,
                blocked_reason=assessment.blocked_reason,
                render_mode="playwright",
                quality_score=assessment.quality_score,
            )
        except Exception as exc:
            return PageFetchResult(
                text="",
                extraction_status="browser_render_failed",
                blocked_reason=str(exc),
                render_mode="playwright",
                quality_score=0.0,
            )