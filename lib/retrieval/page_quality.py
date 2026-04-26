"""Extraction-quality assessment for fetched web pages."""

from dataclasses import dataclass, field
import re

from lib.config import RetrievalGuardConfig
from lib.utils.text_utils import clean_text


CHALLENGE_PATTERNS = [
    "attention required",
    "verify you are human",
    "challenge page",
    "cf-chl",
    "cloudflare",
    "checking your browser",
    "security check",
    "please enable cookies",
]

CAPTCHA_PATTERNS = [
    "captcha",
    "recaptcha",
    "turnstile",
    "i am human",
    "complete the security check",
]

CONSENT_PATTERNS = [
    "we value your privacy",
    "cookie settings",
    "accept all cookies",
    "manage preferences",
    "consent preferences",
    "privacy choices",
    "cookie policy",
]

JAVASCRIPT_PLACEHOLDER_PATTERNS = [
    "enable javascript",
    "javascript is disabled",
    "loading app",
    "please wait while the page loads",
    "this site requires javascript",
    "app shell",
]

ACCESS_PATTERNS = [
    "access denied",
    "request blocked",
    "temporarily unavailable",
    "forbidden",
]


@dataclass
class PageQualityAssessment:
    """A simple quality assessment of extracted page content."""

    status: str
    quality_score: float
    cleaned_text: str = ""
    flags: list[str] = field(default_factory=list)
    blocked_reason: str = ""

    @property
    def is_usable(self) -> bool:
        """Return whether the assessed content is suitable for prompt context."""

        return self.status == "ok" and bool(self.cleaned_text)


def assess_extracted_content(
    url: str,
    raw_text: str,
    raw_html: str,
    config: RetrievalGuardConfig,
) -> PageQualityAssessment:
    """Classify extracted content as usable, blocked, placeholder-like, or low-content."""

    del url  # The URL is accepted for future expansion and logging symmetry.

    cleaned_text = clean_text(raw_text)
    if config.strip_cookie_banner_lines and cleaned_text:
        cleaned_text = _strip_cookie_noise(cleaned_text)

    combined = f"{raw_html[:7000]}\n{cleaned_text}".lower()

    if not config.enabled:
        return PageQualityAssessment(
            status="ok" if cleaned_text else "empty",
            quality_score=1.0 if cleaned_text else 0.0,
            cleaned_text=cleaned_text,
        )

    if config.detect_challenge_pages and _contains_any(combined, CHALLENGE_PATTERNS):
        return PageQualityAssessment(
            status="challenge_page",
            quality_score=0.0,
            cleaned_text="",
            flags=["challenge"],
            blocked_reason="Challenge or anti-bot interstitial detected.",
        )

    if config.detect_captcha_pages and _contains_any(combined, CAPTCHA_PATTERNS):
        return PageQualityAssessment(
            status="captcha_page",
            quality_score=0.0,
            cleaned_text="",
            flags=["captcha"],
            blocked_reason="CAPTCHA or human-verification page detected.",
        )

    if _contains_any(combined, ACCESS_PATTERNS):
        return PageQualityAssessment(
            status="access_denied",
            quality_score=0.0,
            cleaned_text="",
            flags=["access_denied"],
            blocked_reason="Access-denied or blocked-response page detected.",
        )

    if not cleaned_text:
        return PageQualityAssessment(
            status="empty",
            quality_score=0.0,
            cleaned_text="",
            flags=["empty"],
            blocked_reason="No clean text was extracted.",
        )

    if (
        config.detect_consent_walls
        and _contains_any(combined, CONSENT_PATTERNS)
        and len(cleaned_text) < config.min_clean_text_chars
    ):
        return PageQualityAssessment(
            status="cookie_or_consent_wall",
            quality_score=0.12,
            cleaned_text="",
            flags=["consent_wall"],
            blocked_reason="Consent or cookie wall appears to dominate the content.",
        )

    if (
        config.detect_javascript_placeholders
        and _contains_any(combined, JAVASCRIPT_PLACEHOLDER_PATTERNS)
        and len(cleaned_text) < config.min_clean_text_chars
    ):
        return PageQualityAssessment(
            status="javascript_placeholder",
            quality_score=0.15,
            cleaned_text="",
            flags=["javascript_placeholder"],
            blocked_reason="JavaScript placeholder or app shell detected.",
        )

    if len(cleaned_text) < config.min_clean_text_chars:
        return PageQualityAssessment(
            status="low_content",
            quality_score=min(0.4, len(cleaned_text) / max(config.min_clean_text_chars, 1)),
            cleaned_text="",
            flags=["low_content"],
            blocked_reason="Extracted text is too short to trust as primary content.",
        )

    score = min(1.0, 0.25 + len(cleaned_text) / 2500)
    return PageQualityAssessment(
        status="ok",
        quality_score=score,
        cleaned_text=cleaned_text,
    )


def should_try_browser_render(
    assessment: PageQualityAssessment,
    config: RetrievalGuardConfig,
) -> bool:
    """Return whether a browser-render fallback should be attempted."""

    if not config.allow_browser_render_fallback:
        return False

    return assessment.status in {
        "empty",
        "low_content",
        "javascript_placeholder",
        "cookie_or_consent_wall",
    }


def _contains_any(text: str, patterns: list[str]) -> bool:
    """Return whether any pattern is present in the supplied text."""

    return any(pattern in text for pattern in patterns)


def _strip_cookie_noise(text: str) -> str:
    """Remove obvious cookie-banner phrases from otherwise useful extracted text."""

    patterns = [
        r"we value your privacy",
        r"accept all cookies",
        r"manage preferences",
        r"cookie settings",
        r"consent preferences",
        r"privacy choices",
        r"cookie policy",
    ]

    cleaned = text
    for pattern in patterns:
        cleaned = re.sub(pattern, " ", cleaned, flags=re.IGNORECASE)

    return clean_text(cleaned)