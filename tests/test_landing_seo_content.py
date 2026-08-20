from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlparse
import xml.etree.ElementTree as ET
import json
import re


LANDING = Path("landing")
SEO_ROUTES = {
    "/start-vpn-business/",
    "/white-label-vpn-platform/",
    "/multi-server-vpn-management/",
    "/vpn-client-portal-billing/",
    "/security-reliability/",
    "/migrate-vpn-service/",
    "/pricing/",
    "/demo/",
    "/client-apps/",
    "/protocols/wireguard/",
    "/protocols/amneziawg/",
    "/protocols/hysteria2/",
    "/protocols/tuic/",
    "/protocols/vless-reality/",
    "/compare/marzban/",
    "/compare/hiddify/",
    "/compare/3x-ui/",
    "/compare/wg-easy/",
    "/solutions/msp-vpn-platform/",
    "/solutions/hosting-provider-vpn-platform/",
    "/solutions/corporate-vpn-management/",
    "/guides/",
    "/guides/vpn-business-cost/",
    "/guides/vpn-server-capacity/",
    "/guides/vpn-payment-providers/",
}


class PageParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.in_title = False
        self.title_parts = []
        self.descriptions = []
        self.canonicals = []
        self.robots = []
        self.h1_count = 0
        self.heading_tag = None
        self.heading_parts = []
        self.headings = []
        self.links = []
        self.resources = []
        self.open_graph = {}

    @property
    def title(self):
        return "".join(self.title_parts).strip()

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "title":
            self.in_title = True
        elif tag in {"h1", "h2", "h3", "h4", "h5", "h6"}:
            self.heading_tag = tag
            self.heading_parts = []
            if tag == "h1":
                self.h1_count += 1
        elif tag == "meta" and attrs.get("name", "").lower() == "description":
            self.descriptions.append(attrs.get("content", ""))
        elif tag == "meta" and attrs.get("name", "").lower() == "robots":
            self.robots.append(attrs.get("content", ""))
        elif tag == "link" and "canonical" in attrs.get("rel", "").split():
            self.canonicals.append(attrs.get("href", ""))
        elif tag == "a" and attrs.get("href"):
            self.links.append(attrs["href"])
        elif tag in ("img", "script") and attrs.get("src"):
            self.resources.append(attrs["src"])
        elif tag == "link" and attrs.get("href") and any(
            value in attrs.get("rel", "").split()
            for value in ("icon", "stylesheet")
        ):
            self.resources.append(attrs["href"])
        elif tag == "meta" and attrs.get("property", "").startswith("og:"):
            self.open_graph[attrs["property"]] = attrs.get("content", "")
            if attrs["property"] == "og:image":
                self.resources.append(attrs.get("content", ""))

    def handle_endtag(self, tag):
        if tag == "title":
            self.in_title = False
        elif tag == self.heading_tag:
            heading = "".join(self.heading_parts).strip()
            if heading:
                self.headings.append(heading)
            self.heading_tag = None
            self.heading_parts = []

    def handle_data(self, data):
        if self.in_title:
            self.title_parts.append(data)
        if self.heading_tag:
            self.heading_parts.append(data)


def route_file(route):
    return LANDING / route.strip("/") / "index.html"


def parse(path):
    parser = PageParser()
    parser.feed(path.read_text(encoding="utf-8"))
    return parser


def test_existing_root_url_and_query_language_urls_remain_canonical():
    page = (LANDING / "index.html").read_text(encoding="utf-8")
    assert '<link rel="canonical" href="https://flirexa.biz/">' in page
    for language in ("en", "ru", "uk", "de", "fr", "es"):
        assert f'href="https://flirexa.biz/?lang={language}"' in page


def test_public_marketing_headings_do_not_end_in_periods():
    pages = [LANDING / "index.html", LANDING / "news.html", LANDING / "blog/plugins.html"]
    pages.extend(route_file(route) for route in sorted(SEO_ROUTES))
    for source in pages:
        assert all(
            not heading.rstrip().endswith(".") for heading in parse(source).headings
        ), f"heading ends in a period: {source}"


def test_indexable_seo_pages_have_unique_metadata_and_one_h1():
    titles = set()
    canonicals = set()
    for route in sorted(SEO_ROUTES):
        page = parse(route_file(route))
        assert page.title
        assert len(page.title) <= 70
        assert len(page.descriptions) == 1
        assert 90 <= len(page.descriptions[0]) <= 180
        assert page.h1_count == 1
        assert all(not heading.rstrip().endswith(".") for heading in page.headings)
        assert page.canonicals == [f"https://flirexa.biz{route}"]
        assert page.open_graph.get("og:url") == page.canonicals[0]
        assert page.open_graph.get("og:title")
        assert page.open_graph.get("og:description")
        assert page.open_graph.get("og:image")
        assert page.title not in titles
        assert page.canonicals[0] not in canonicals
        titles.add(page.title)
        canonicals.add(page.canonicals[0])


def test_sitemap_contains_every_indexable_commercial_route():
    tree = ET.parse(LANDING / "sitemap.xml")
    ns = {"s": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    urls = {node.text for node in tree.findall("s:url/s:loc", ns)}
    entries = tree.findall("s:url", ns)
    assert entries
    assert all(entry.find("s:lastmod", ns) is not None for entry in entries)
    for route in SEO_ROUTES:
        assert f"https://flirexa.biz{route}" in urls
    assert "https://flirexa.biz/blog/plugins.html" in urls


def test_internal_root_links_on_seo_pages_resolve_locally():
    for route in sorted(SEO_ROUTES):
        source = route_file(route)
        for href in parse(source).links:
            if not href.startswith("/") or href.startswith("//"):
                continue
            path = urlparse(href).path
            if path in ("", "/"):
                continue
            target = LANDING / path.lstrip("/")
            if path.endswith("/"):
                target /= "index.html"
            assert target.exists(), f"{source} links to missing {href}"


def test_interactive_demo_apps_are_not_search_results():
    for relative in (
        "demo/VPN-Admin-Panel-demo.html",
        "demo-next/index.html",
        "demo-next-apps/index.html",
        "demo-authentic/admin/index.html",
        "demo-authentic/portal/index.html",
    ):
        robots = " ".join(parse(LANDING / relative).robots).lower()
        assert "noindex" in robots


def test_indexable_pages_reference_existing_local_assets():
    pages = [
        LANDING / "index.html",
        LANDING / "news.html",
        LANDING / "privacy.html",
        LANDING / "terms.html",
        LANDING / "blog/plugins.html",
    ]
    pages.extend(route_file(route) for route in sorted(SEO_ROUTES))
    for source in pages:
        for resource in parse(source).resources:
            parsed = urlparse(resource)
            if parsed.scheme and parsed.netloc != "flirexa.biz":
                continue
            path = parsed.path
            if not path or path == "/favicon.ico":
                continue
            target = LANDING / path.lstrip("/") if path.startswith("/") else source.parent / path
            assert target.exists(), f"{source} references missing asset {resource}"


def test_structured_data_is_valid_and_contains_no_invented_ratings():
    pages = [LANDING / "index.html"]
    pages.extend(route_file(route) for route in sorted(SEO_ROUTES))
    for source in pages:
        html = source.read_text(encoding="utf-8")
        blocks = re.findall(
            r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
            html,
            flags=re.DOTALL | re.IGNORECASE,
        )
        for block in blocks:
            value = json.loads(block)
            assert "aggregateRating" not in json.dumps(value)


def test_comparison_and_migration_articles_expose_current_article_schema():
    routes = {
        "/compare/marzban/",
        "/compare/hiddify/",
        "/compare/3x-ui/",
        "/compare/wg-easy/",
        "/migrate-vpn-service/",
    }
    for route in routes:
        html = route_file(route).read_text(encoding="utf-8")
        blocks = re.findall(
            r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
            html,
            flags=re.DOTALL | re.IGNORECASE,
        )
        articles = [json.loads(block) for block in blocks]
        assert any(value.get("@type") == "Article" for value in articles)
        assert any(value.get("dateModified") == "2026-08-20" for value in articles)


def test_comparison_pages_keep_intent_inside_flirexa_buyer_journey():
    competitor_hosts = {
        "github.com/MHSanaei/3x-ui",
        "github.com/hiddify/Hiddify-Manager",
        "github.com/Gozargah/Marzban",
        "github.com/wg-easy/wg-easy",
    }
    for route in (
        "/compare/3x-ui/",
        "/compare/hiddify/",
        "/compare/marzban/",
        "/compare/wg-easy/",
    ):
        html = route_file(route).read_text(encoding="utf-8")
        assert 'data-comparison-platform' in html
        assert 'href="/start-vpn-business/"' in html
        for competitor in competitor_hosts:
            assert competitor not in html


def test_enterprise_migration_promise_is_consistent_across_sales_pages():
    pricing = route_file("/pricing/").read_text(encoding="utf-8")
    migration = route_file("/migrate-vpn-service/").read_text(encoding="utf-8")
    root = (LANDING / "index.html").read_text(encoding="utf-8")

    assert "Standard migration from an existing VPN service" in pricing
    assert "no additional Flirexa migration charge" in pricing
    assert "no separate migration fee" in migration
    assert "canary" in migration.lower()
    assert 'data-i18n="enterpriseFeat.8"' in root


def test_news_and_legal_pages_have_current_search_contracts():
    news = (LANDING / "news.html").read_text(encoding="utf-8")
    assert "[object Object]" not in news
    assert "Latest · v1.6" not in news
    assert "Pro and higher" not in news
    for name in ("news.html", "privacy.html", "terms.html"):
        page = parse(LANDING / name)
        assert page.h1_count == 1
        assert len(page.canonicals) == 1
        assert len(page.descriptions) == 1


def test_security_contact_has_a_canonical_public_policy():
    security = (LANDING / ".well-known/security.txt").read_text(encoding="utf-8")
    assert "Contact: mailto:support@flirexa.biz" in security
    assert "Canonical: https://flirexa.biz/.well-known/security.txt" in security
    assert "Policy: https://github.com/Flirexa/flirexa/blob/main/SECURITY.md" in security
    assert "Expires: 2027-08-01T00:00:00Z" in security


def test_organic_entry_pages_keep_first_party_analytics_and_support_access():
    pages = [LANDING / "news.html", LANDING / "blog/plugins.html"]
    pages.extend(
        route_file(route) for route in sorted(SEO_ROUTES) if route != "/demo/"
    )
    for source in pages:
        assert "/seo-pages.js" in parse(source).resources, (
            f"{source} is missing the organic-page analytics bridge"
        )

    script = (LANDING / "seo-pages.js").read_text(encoding="utf-8")
    for endpoint in (
        "/api/visit",
        "/api/heartbeat",
        "/api/analytics/event",
        "/api/copy-install",
    ):
        assert endpoint in script
    assert "/?support=1" in script

    root_script = (LANDING / "app.v2.js").read_text(encoding="utf-8")
    assert "new URLSearchParams(window.location.search).get('support') === '1'" in root_script
    assert "chat_manual_open" in root_script


def test_new_marketing_pages_offer_same_url_localized_content_without_seo_duplicates():
    pages = [LANDING / "news.html", LANDING / "blog/plugins.html"]
    pages.extend(
        route_file(route) for route in sorted(SEO_ROUTES) if route != "/demo/"
    )
    translation_dir = LANDING / "i18n-pages"
    assert translation_dir.is_dir()

    for source in pages:
        relative = source.relative_to(LANDING).as_posix()
        if relative.endswith("/index.html"):
            key = relative[: -len("/index.html")].replace("/", "--")
        else:
            key = relative.removesuffix(".html").replace("/", "--")
        parser = parse(source)
        for language in ("ru", "uk", "de", "fr", "es"):
            localized = translation_dir / f"{key}.{language}.json"
            payload = json.loads(localized.read_text(encoding="utf-8"))
            assert payload["title"]
            assert payload["description"]
            assert payload["strings"]
            assert "Flirexa" in payload["title"] or "Flirexa" in parser.title

    script = (LANDING / "seo-pages.js").read_text(encoding="utf-8")
    assert "new URLSearchParams(window.location.search).get('lang')" in script
    assert "history.replaceState" in script
    assert "'/i18n-pages/' + routeKey()" in script


def test_mobile_navigation_surfaces_demo_and_pricing_before_long_section_lists():
    index = (LANDING / "index.html").read_text(encoding="utf-8")
    root_css = (LANDING / "style.v2.css").read_text(encoding="utf-8")
    shared_navigation = (LANDING / "seo-pages.js").read_text(encoding="utf-8")
    shared_css = (LANDING / "seo-pages.css").read_text(encoding="utf-8")

    assert 'class="flx-mobile-site-menu__quick"' in index
    assert '<a href="#pricing" data-i18n="navPricing">' in index
    assert ".flx-mobile-site-menu__quick" in root_css

    assert 'class="seo-mobile-nav__quick"' in shared_navigation
    assert "link('/demo/', t.demo) + link('/#pricing', t.pricing)" in shared_navigation
    assert ".seo-mobile-nav__quick" in shared_css
    assert "flx-mobile-quick-shine" in root_css
    assert "seo-mobile-quick-shine" in shared_css
    assert "prefers-reduced-motion:reduce" in root_css

    root_script = (LANDING / "app.v2.js").read_text(encoding="utf-8")
    assert "scrollToLandingHash" in root_script
    assert "alignTarget = hash === '#pricing'" in root_script


def test_current_marketing_copy_does_not_use_em_dash_as_a_prose_separator():
    sources = [
        LANDING / "index.html",
        LANDING / "news.html",
        LANDING / "privacy.html",
        LANDING / "terms.html",
        LANDING / "blog/plugins.html",
        LANDING / "app.v2.js",
        LANDING / "i18n.v2.js",
        LANDING / "seo-pages.js",
    ]
    sources.extend(route_file(route) for route in sorted(SEO_ROUTES))
    sources.extend(sorted((LANDING / "i18n-pages").glob("*.json")))

    for source in sources:
        assert "—" not in source.read_text(encoding="utf-8"), (
            f"{source} contains an em dash in current public marketing copy"
        )
