"""Website logo downloader used to populate a reusable logo cache."""

import mimetypes
import re
import shutil
from pathlib import Path
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen

from lib.config import AppConfig
from lib.models import CompanyProfile
from lib.utils.text_utils import canonical_name, slugify_filename, unique_preserve_order


class LogoDownloader:
    """Download company logos or icon fallbacks from official company websites."""

    USER_AGENT = "Mozilla/5.0 (compatible; AgenticLandscapeBot/1.0)"

    def __init__(self, config: AppConfig) -> None:
        """Store logo-download configuration and network behavior settings."""

        self.config = config

    def download_logos(self, profiles: list[CompanyProfile], logos_dir: str | Path) -> dict[str, str]:
        """Download logos into the global cache and optionally copy them into the report directory."""

        if not self.config.logos.download_enabled:
            return {}

        cache_dir = Path(self.config.paths.logo_cache_dir)
        cache_dir.mkdir(parents=True, exist_ok=True)

        report_logo_dir = Path(logos_dir)
        if self.config.logos.copy_cached_logo_to_report_dir:
            report_logo_dir.mkdir(parents=True, exist_ok=True)

        results: dict[str, str] = {}
        for profile in profiles:
            cached_logo_path = self.download_logo_for_profile(profile, cache_dir)
            if cached_logo_path is None:
                continue

            output_path = cached_logo_path
            if self.config.logos.copy_cached_logo_to_report_dir:
                output_path = report_logo_dir / cached_logo_path.name
                if cached_logo_path.resolve() != output_path.resolve():
                    shutil.copyfile(cached_logo_path, output_path)

            results[canonical_name(profile.name)] = str(output_path)

        return results

    def download_logo_for_profile(self, profile: CompanyProfile, logo_cache_dir: Path) -> Path | None:
        """Download a single company logo using website metadata and sensible fallbacks."""

        logo_cache_dir.mkdir(parents=True, exist_ok=True)

        cached = self._find_existing_logo(profile.name, logo_cache_dir)
        if cached is not None:
            return cached

        if profile.logo_path and Path(profile.logo_path).exists():
            existing_path = Path(profile.logo_path)
            if existing_path.parent.resolve() == logo_cache_dir.resolve():
                return existing_path

        website = self._normalize_website(profile.website)
        if not website:
            return None

        html = self._fetch_text(website)
        candidates = self._extract_logo_candidates(website, html)

        for candidate in candidates:
            saved_path = self._download_image(candidate, profile.name, logo_cache_dir)
            if saved_path is not None:
                return saved_path

        return None

    def _normalize_website(self, website: str) -> str:
        """Normalize a company website into an absolute URL."""

        if not website or website.strip().lower() == "unknown":
            return ""
        return website if "://" in website else f"https://{website}"

    def _find_existing_logo(self, company_name: str, logos_dir: Path) -> Path | None:
        """Return an already-downloaded logo file if it exists on disk."""

        slug = slugify_filename(company_name)
        for path in logos_dir.glob(f"{slug}.*"):
            if path.is_file():
                return path
        return None

    def _extract_logo_candidates(self, base_url: str, html: str) -> list[str]:
        """Extract likely logo candidate URLs from HTML metadata and common icon locations."""

        candidates: list[str] = []

        if not html:
            if self.config.logos.fallback_to_favicon:
                candidates.append(urljoin(base_url, "/favicon.ico"))
            return unique_preserve_order(candidates)

        if self.config.logos.try_logo_img:
            patterns = [
                r'<img[^>]+src=["\']([^"\']+)["\'][^>]+(?:alt|class|id)=["\'][^"\']*logo[^"\']*["\']',
                r'<img[^>]+(?:alt|class|id)=["\'][^"\']*logo[^"\']*["\'][^>]+src=["\']([^"\']+)["\']',
            ]
            for pattern in patterns:
                candidates.extend(re.findall(pattern, html, flags=re.IGNORECASE))

        icon_pattern = r'<link[^>]+rel=["\'][^"\']*(?:icon|apple-touch-icon)[^"\']*["\'][^>]+href=["\']([^"\']+)["\']'
        candidates.extend(re.findall(icon_pattern, html, flags=re.IGNORECASE))

        if self.config.logos.try_og_image:
            og_patterns = [
                r'<meta[^>]+property=["\']og:(?:logo|image)["\'][^>]+content=["\']([^"\']+)["\']',
                r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:(?:logo|image)["\']',
            ]
            for pattern in og_patterns:
                candidates.extend(re.findall(pattern, html, flags=re.IGNORECASE))

        if self.config.logos.fallback_to_favicon:
            candidates.append(urljoin(base_url, "/favicon.ico"))

        normalized = [urljoin(base_url, candidate) for candidate in candidates]
        return unique_preserve_order(normalized)

    def _download_image(self, image_url: str, company_name: str, logos_dir: Path) -> Path | None:
        """Download an image candidate and save it if it looks valid and useful."""

        try:
            request = Request(image_url, headers={"User-Agent": self.USER_AGENT})
            with urlopen(request, timeout=self.config.logos.request_timeout_seconds) as response:
                content_type = response.headers.get("Content-Type", "")
                content = response.read(self.config.logos.max_image_bytes + 1)
        except Exception:
            return None

        if not content or len(content) < self.config.logos.min_image_bytes:
            return None
        if len(content) > self.config.logos.max_image_bytes:
            return None
        if "image" not in content_type and not self._url_has_allowed_extension(image_url):
            return None

        extension = self._guess_extension(image_url, content_type)
        if extension not in set(self.config.logos.allowed_extensions):
            return None

        output_path = logos_dir / f"{slugify_filename(company_name)}{extension}"
        output_path.write_bytes(content)
        return output_path

    def _fetch_text(self, url: str) -> str:
        """Fetch the HTML text of a website page for metadata inspection."""

        try:
            request = Request(url, headers={"User-Agent": self.USER_AGENT})
            with urlopen(request, timeout=self.config.logos.request_timeout_seconds) as response:
                raw = response.read().decode("utf-8", errors="ignore")
            return raw
        except Exception:
            return ""

    def _guess_extension(self, image_url: str, content_type: str) -> str:
        """Infer a file extension from response headers or the image URL."""

        if content_type:
            extension = mimetypes.guess_extension(content_type.split(";")[0].strip())
            if extension:
                return extension

        suffix = Path(urlparse(image_url).path).suffix.lower()
        if suffix:
            return suffix

        return ".png"

    def _url_has_allowed_extension(self, image_url: str) -> bool:
        """Return whether the URL path ends with an allowed image extension."""

        suffix = Path(urlparse(image_url).path).suffix.lower()
        return suffix in set(self.config.logos.allowed_extensions)