"""Playwright-based scraping engine.
Navigates agency websites, captures screenshots, extracts visible text and links."""

import asyncio
import logging
from typing import Dict, List
from urllib.parse import urlparse, urljoin

logger = logging.getLogger(__name__)

# Graceful Playwright import - may not be available in all deployment envs
try:
    from playwright.async_api import async_playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False
    logger.warning("Playwright not available - scraping will be disabled")

# Semaphore to limit concurrent browser instances
_semaphore = asyncio.Semaphore(3)


async def scrape_website(url: str, config: Dict) -> Dict:
    """Main scraping function. Returns structured scraping result."""
    if not PLAYWRIGHT_AVAILABLE:
        logger.error("Playwright not available - returning empty scrape result")
        return {
            "homepage_text": "",
            "screenshot_bytes": None,
            "candidate_pages": [],
            "visited_pages": [url],
            "failed_pages": [{"url": url, "reason": "Playwright not available in this environment"}],
            "skipped_pages": [],
            "pages_content": [],
            "all_links": []
        }
    async with _semaphore:
        return await _do_scrape(url, config)


async def _do_scrape(url: str, config: Dict) -> Dict:
    max_pages = config.get("max_pages", 10)
    timeout_ms = config.get("timeout_seconds", 30) * 1000
    priority_patterns = config.get("priority_patterns", [
        "about", "nosotros", "quienes-somos", "servicios", "services",
        "work", "clientes", "clients", "equipo", "team",
        "premios", "awards", "contacto", "contact"
    ])
    capture_internal = config.get("capture_internal_pages", True)

    result = {
        "homepage_text": "",
        "screenshot_bytes": None,
        "candidate_pages": [],
        "visited_pages": [url],
        "failed_pages": [],
        "skipped_pages": [],
        "pages_content": [],
        "all_links": []
    }

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage']
        )

        try:
            context = await browser.new_context(
                viewport={"width": 1280, "height": 720},
                ignore_https_errors=True,
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                locale="es-ES"
            )
            page = await context.new_page()

            # Navigate to homepage
            logger.info(f"Navigating to {url}")
            try:
                await page.goto(url, timeout=timeout_ms, wait_until="domcontentloaded")
                await page.wait_for_timeout(2000)
            except Exception as e:
                logger.warning(f"Homepage navigation warning for {url}: {e}")
                try:
                    await page.goto(url, timeout=timeout_ms, wait_until="commit")
                    await page.wait_for_timeout(2000)
                except Exception as e2:
                    logger.error(f"Homepage navigation failed for {url}: {e2}")
                    result["failed_pages"].append({"url": url, "reason": str(e2)})
                    await browser.close()
                    return result

            # Take screenshot
            try:
                result["screenshot_bytes"] = await page.screenshot(
                    full_page=False,
                    type="png"
                )
            except Exception as e:
                logger.warning(f"Screenshot failed for {url}: {e}")

            # Extract logo
            try:
                logo_data = await page.evaluate("""(baseUrl) => {
                    function absUrl(src) {
                        if (!src) return null;
                        if (src.startsWith('data:')) return src;
                        try { return new URL(src, baseUrl).href; } catch(e) { return null; }
                    }

                    // 1. <img> with "logo" in src, alt, class, or id
                    const imgs = Array.from(document.querySelectorAll('img'));
                    for (const img of imgs) {
                        const attrs = (img.src + ' ' + img.alt + ' ' + img.className + ' ' + img.id).toLowerCase();
                        if (attrs.includes('logo')) {
                            const src = absUrl(img.src || img.getAttribute('data-src'));
                            if (src && !src.startsWith('data:')) return { url: src, source: 'img_logo_attr' };
                        }
                    }

                    // 2. SVG with "logo" in class/id, get parent link or nearby img
                    const svgs = Array.from(document.querySelectorAll('svg'));
                    for (const svg of svgs) {
                        const attrs = (svg.className?.baseVal || '') + ' ' + svg.id;
                        if (attrs.toLowerCase().includes('logo')) {
                            // SVG inline logo — can't extract as URL, try sibling/parent img
                            const parent = svg.closest('a') || svg.parentElement;
                            const sibImg = parent ? parent.querySelector('img') : null;
                            if (sibImg && sibImg.src) return { url: absUrl(sibImg.src), source: 'svg_sibling' };
                        }
                    }

                    // 3. Open Graph image
                    const ogImg = document.querySelector('meta[property="og:image"]');
                    if (ogImg && ogImg.content) return { url: absUrl(ogImg.content), source: 'og_image' };

                    // 4. First image in header or nav
                    const header = document.querySelector('header') || document.querySelector('nav');
                    if (header) {
                        const headerImg = header.querySelector('img');
                        if (headerImg && headerImg.src) return { url: absUrl(headerImg.src), source: 'header_img' };
                    }

                    // 5. Apple touch icon or favicon
                    const touchIcon = document.querySelector('link[rel="apple-touch-icon"]');
                    if (touchIcon && touchIcon.href) return { url: touchIcon.href, source: 'apple_touch_icon' };

                    const icon = document.querySelector('link[rel="icon"], link[rel="shortcut icon"]');
                    if (icon && icon.href) return { url: icon.href, source: 'favicon' };

                    return null;
                }""", url)

                result["logo_url"] = logo_data.get("url") if logo_data else None
                result["logo_source"] = logo_data.get("source") if logo_data else None
                if logo_data:
                    logger.info(f"Logo found via {logo_data['source']}: {logo_data['url'][:80]}")
            except Exception as e:
                logger.warning(f"Logo extraction failed for {url}: {e}")
                result["logo_url"] = None
                result["logo_source"] = None

            # Extract homepage text
            try:
                result["homepage_text"] = await page.evaluate("""() => {
                    const body = document.body;
                    if (!body) return '';
                    // Remove script and style elements
                    const clone = body.cloneNode(true);
                    clone.querySelectorAll('script, style, noscript').forEach(el => el.remove());
                    return clone.innerText || '';
                }""")
            except Exception as e:
                logger.warning(f"Text extraction failed for {url}: {e}")

            # Extract all links
            try:
                all_links = await page.evaluate("""() => {
                    return Array.from(document.querySelectorAll('a[href]'))
                        .map(a => ({
                            href: a.href,
                            text: (a.textContent || '').trim().substring(0, 100)
                        }))
                        .filter(l => l.href && l.href.startsWith('http'))
                }""")
                result["all_links"] = all_links
            except Exception as e:
                logger.warning(f"Link extraction failed: {e}")
                all_links = []

            # Find relevant internal pages
            if capture_internal and all_links:
                parsed_base = urlparse(url)
                base_domain = parsed_base.netloc.lower()
                seen = set()
                candidates = []

                for link in all_links:
                    href = link.get("href", "")
                    parsed = urlparse(href)
                    link_domain = parsed.netloc.lower()

                    if link_domain != base_domain:
                        continue

                    path = parsed.path.lower().rstrip("/")
                    if not path or path == "/" or path in seen:
                        continue

                    text_lower = link.get("text", "").lower()
                    for pattern in priority_patterns:
                        pat = pattern.lower()
                        if pat in path or pat in text_lower:
                            seen.add(path)
                            candidates.append({
                                "url": href,
                                "path": path,
                                "text": link.get("text", ""),
                                "pattern": pattern
                            })
                            break

                result["candidate_pages"] = [c["url"] for c in candidates]

                # Visit relevant pages (up to max_pages - 1, since homepage counts)
                pages_to_visit = candidates[:max_pages - 1]
                skipped = candidates[max_pages - 1:]

                for skip in skipped:
                    result["skipped_pages"].append({
                        "url": skip["url"],
                        "reason": "max_pages reached"
                    })

                for candidate in pages_to_visit:
                    page_url = candidate["url"]
                    try:
                        await page.goto(page_url, timeout=timeout_ms, wait_until="domcontentloaded")
                        await page.wait_for_timeout(1000)

                        page_text = await page.evaluate("""() => {
                            const body = document.body;
                            if (!body) return '';
                            const clone = body.cloneNode(true);
                            clone.querySelectorAll('script, style, noscript').forEach(el => el.remove());
                            return clone.innerText || '';
                        }""")

                        result["pages_content"].append({
                            "url": page_url,
                            "text": page_text[:5000]
                        })
                        result["visited_pages"].append(page_url)
                        logger.info(f"Visited: {page_url}")

                    except Exception as e:
                        logger.warning(f"Failed to visit {page_url}: {e}")
                        result["failed_pages"].append({
                            "url": page_url,
                            "reason": str(e)[:200]
                        })

            await context.close()

        except Exception as e:
            logger.error(f"Scraping error for {url}: {e}")
            result["failed_pages"].append({"url": url, "reason": str(e)[:200]})

        finally:
            try:
                await browser.close()
            except Exception:
                pass
            # Force garbage collection to free Chromium memory
            import gc
            gc.collect()

    return result


def compile_text_content(scrape_result: Dict) -> str:
    """Compile all scraped text into a single string for LLM analysis."""
    parts = []

    homepage = scrape_result.get("homepage_text", "")
    if homepage:
        parts.append(f"=== HOMEPAGE ===\n{homepage[:5000]}")

    for page in scrape_result.get("pages_content", []):
        parts.append(f"\n=== PAGE: {page['url']} ===\n{page['text']}")

    return "\n\n".join(parts)
