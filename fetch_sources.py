#!/usr/bin/env python3
import hashlib
import json
import re
import time
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from html import unescape
from pathlib import Path
from urllib.parse import urljoin, urlparse, urlunparse
from urllib.request import Request, urlopen
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
HISTORY_DIR = DATA_DIR / "history"
SOURCES_FILE = ROOT / "sources.json"

USER_AGENT = "Mozilla/5.0 (compatible; AIHotMonitorMVP/1.1; +https://example.local)"
FETCH_TIMEOUT = 25
FETCH_INTERVAL_MINUTES = 30

TRACKED_COMPANIES = [
    "Datadog",
    "Databricks",
    "Anyscale",
    "Together AI",
    "Physical Intelligence",
]

TRACKED_VOICES = [
    "Andrew Karpathy",
    "Fei-Fei Li",
    "Yann LeCun",
    "Demis Hassabis",
    "Jensen Huang",
    "Sam Altman",
    "Dario Amodei",
    "Mustafa Suleyman",
]

TRACKED_FOCUS_ALIASES = {
    "Datadog": ["datadog", "bitsevolve"],
    "Databricks": ["databricks", "lakehouse", "lakeflow"],
    "Anyscale": ["anyscale"],
    "Together AI": ["together ai", "together.ai"],
    "Physical Intelligence": ["physical intelligence", "physicalintelligence", "π0", "pi0"],
    "Andrew Karpathy": ["andrew karpathy", "karpathy", "karparthy"],
    "Fei-Fei Li": ["fei-fei li", "li fei-fei"],
    "Yann LeCun": ["yann lecun"],
    "Demis Hassabis": ["demis hassabis", "demis"],
    "Jensen Huang": ["jensen huang", "jensen"],
    "Sam Altman": ["sam altman"],
    "Dario Amodei": ["dario amodei"],
    "Mustafa Suleyman": ["mustafa suleyman"],
}

KNOWN_ENTITY_ALIASES = {
    "OpenAI": ["openai"],
    "Anthropic": ["anthropic"],
    "Google": ["google"],
    "DeepMind": ["deepmind"],
    "Meta": ["meta"],
    "xAI": ["xai"],
    "Mistral": ["mistral"],
    "Qwen": ["qwen"],
    "Microsoft": ["microsoft"],
    "Amazon": ["amazon"],
    "NVIDIA": ["nvidia"],
    "FTC": ["ftc"],
    "NIST": ["nist"],
    "EU": ["eu", "european union"],
    "White House": ["white house"],
    "Stanford": ["stanford"],
    "Cloudflare": ["cloudflare"],
    "Physical Intelligence": ["physical intelligence", "physicalintelligence", "π0", "pi0"],
}

AI_TERMS = {
    "ai", "artificial intelligence", "llm", "agent", "agents", "gpt", "claude",
    "gemini", "anthropic", "openai", "deepmind", "meta ai", "xai", "mistral",
    "qwen", "inference", "reasoning", "model", "models", "foundation model",
    "robot", "robots", "machine learning", "ml", "copilot", "codex", "prompt",
    "frontier model", "multimodal", "synthetic media"
}

AI_POLICY_TERMS = {
    "ai act", "artificial intelligence", "algorithmic", "foundation model",
    "general purpose ai", "gai", "deepfake", "synthetic media", "frontier model"
}

REGULATION_TERMS = {
    "regulation", "regulations", "regulatory", "policy", "policies", "law", "laws",
    "compliance", "privacy", "copyright", "governance", "standard", "standards",
    "safety", "secure", "security", "risk", "eu", "commission", "ftc", "nist",
    "government", "white house", "ai act", "transparency", "audit", "antitrust",
    "licensing", "data protection", "accountability", "framework", "disclosure"
}

TOPIC_KEYWORDS = {
    "policy_regulation": [
        "regulation", "policy", "law", "compliance", "ftc", "nist", "ai act",
        "government", "governance", "copyright", "privacy", "standard", "commission"
    ],
    "model_release": [
        "model", "gpt", "claude", "gemini", "qwen", "mistral", "release",
        "launch", "reasoning", "weights", "checkpoint", "sonnet", "opus"
    ],
    "infra_tools": [
        "inference", "platform", "api", "cloud", "infrastructure", "deploy",
        "agent", "agents", "tool", "workflow", "developer", "codex", "sdk"
    ],
    "research": [
        "paper", "research", "study", "benchmark", "science", "lab", "index"
    ],
    "applications": [
        "product", "assistant", "robot", "consumer", "enterprise", "workflow", "app"
    ],
    "capital_market": [
        "funding", "raises", "valuation", "revenue", "acquisition", "ipo", "investment"
    ]
}

TOPIC_LABELS = {
    "policy_regulation": "监管 / 政策",
    "model_release": "模型发布",
    "infra_tools": "平台 / 工具链",
    "research": "研究进展",
    "applications": "应用 / 产品",
    "capital_market": "融资 / 商业化",
    "general": "综合热点"
}

SOURCE_TYPE_LABELS = {
    "rss": "RSS",
    "hn": "Hacker News",
    "html": "Official Site"
}

TITLE_STOPWORDS = {
    "the", "and", "for", "with", "from", "that", "this", "into", "over", "about",
    "after", "before", "under", "your", "their", "almost", "everything", "what",
    "when", "where", "while", "will", "more", "most", "less", "than", "new",
    "introducing", "launches", "launch", "release", "releases", "announces", "how",
    "why", "can", "now", "all", "our", "its", "are", "but", "you", "not",
    "using", "used", "use", "just", "gets", "make", "made", "toward", "state"
}

LOW_SIGNAL_TITLE_TERMS = {
    "hiring", "founding team", "job", "jobs", "career", "careers", "ask hn", "show hn"
}


def ensure_dirs():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    HISTORY_DIR.mkdir(parents=True, exist_ok=True)



def now_utc():
    return datetime.now(timezone.utc)



def iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat()



def load_sources():
    return json.loads(SOURCES_FILE.read_text(encoding="utf-8"))



def fetch_bytes(url: str) -> bytes:
    req = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(req, timeout=FETCH_TIMEOUT) as response:
        return response.read()



def fetch_json(url: str):
    return json.loads(fetch_bytes(url).decode("utf-8"))



def strip_namespace(tag: str) -> str:
    return tag.split("}", 1)[-1] if "}" in tag else tag



def child_text(elem, *names):
    names = {name.lower() for name in names}
    for child in list(elem):
        if strip_namespace(child.tag).lower() in names:
            text = "".join(child.itertext()).strip()
            if text:
                return text
    return ""



def child_link(elem):
    for child in list(elem):
        tag = strip_namespace(child.tag).lower()
        if tag != "link":
            continue
        href = (child.attrib.get("href") or "").strip()
        rel = (child.attrib.get("rel") or "alternate").strip().lower()
        if href and rel in {"alternate", ""}:
            return href
        text = "".join(child.itertext()).strip()
        if text:
            return text
    return child_text(elem, "link")



def clean_html(text: str) -> str:
    if not text:
        return ""
    text = unescape(text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()



def parse_date(raw: str):
    if not raw:
        return None
    raw = raw.strip()
    dt = None
    try:
        if raw.endswith("Z"):
            dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        else:
            dt = datetime.fromisoformat(raw)
    except Exception:
        dt = None
    if dt is None:
        try:
            dt = parsedate_to_datetime(raw)
        except Exception:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)



def canonicalize_url(url: str) -> str:
    if not url:
        return ""
    parsed = urlparse(url)
    query = ""
    fragment = ""
    netloc = parsed.netloc.lower()
    scheme = parsed.scheme.lower() or "https"
    path = parsed.path or "/"
    return urlunparse((scheme, netloc, path.rstrip("/") or "/", "", query, fragment))



def tokenize(text: str):
    return re.findall(r"[a-z0-9][a-z0-9+.-]{1,}", (text or "").lower())



def title_tokens(text: str):
    return {
        token for token in tokenize(text)
        if len(token) >= 3 and token not in TITLE_STOPWORDS and not token.isdigit()
    }



def contains_any(text: str, words) -> int:
    hay = f" {(text or '').lower()} "
    return sum(1 for word in words if f" {word.lower()} " in hay or word.lower() in hay)



def matches_aliases(text: str, aliases) -> bool:
    hay = f" {(text or '').lower()} "
    for alias in aliases:
        alias = alias.lower().strip()
        if not alias:
            continue
        if f" {alias} " in hay or alias in hay:
            return True
    return False



def detect_focus_matches(text: str):
    text = text or ""
    return [
        label
        for label, aliases in TRACKED_FOCUS_ALIASES.items()
        if matches_aliases(text, aliases)
    ]



def is_relevant_item(text: str, source_category: str) -> bool:
    text = text or ""
    ai_hits = contains_any(text, AI_TERMS | AI_POLICY_TERMS)
    reg_hits = contains_any(text, REGULATION_TERMS)
    if source_category == "regulation":
        return ai_hits > 0 or reg_hits >= 2
    if source_category in {"ai", "official", "community"}:
        return ai_hits > 0
    return ai_hits > 0 or reg_hits >= 2



def classify_topic(text: str) -> str:
    text = (text or "").lower()
    scores = {}
    for topic, keywords in TOPIC_KEYWORDS.items():
        scores[topic] = sum(2 if keyword in text else 0 for keyword in keywords)
    best_topic = max(scores, key=scores.get) if scores else "general"
    return best_topic if scores.get(best_topic, 0) > 0 else "general"



def detect_entities(text: str):
    text = text or ""
    entities = []
    for label, aliases in TRACKED_FOCUS_ALIASES.items():
        if matches_aliases(text, aliases):
            entities.append(label)
    for label, aliases in KNOWN_ENTITY_ALIASES.items():
        if label in entities:
            continue
        if matches_aliases(text, aliases):
            entities.append(label)
    return entities[:8]



def regulatory_score(text: str, source_category: str) -> int:
    score = contains_any(text, REGULATION_TERMS) * 12
    score += contains_any(text, AI_POLICY_TERMS) * 8
    if source_category == "regulation":
        score += 45
    return min(score, 100)



def writer_value_score(topic: str, reg_score: int, source_category: str, summary: str, focus_matches=None) -> int:
    score = 45
    if topic in {"policy_regulation", "model_release", "infra_tools"}:
        score += 18
    if reg_score >= 40:
        score += 18
    if source_category in {"ai", "regulation", "community", "official"}:
        score += 8
    if source_category in {"ecosystem", "voices"}:
        score += 6
    if focus_matches:
        score += min(len(focus_matches) * 4, 12)
    if len(summary or "") > 80:
        score += 6
    return min(score, 100)



def recency_score(published_at):
    if not published_at:
        return 20
    age_hours = max((now_utc() - published_at.astimezone(timezone.utc)).total_seconds() / 3600.0, 0)
    if age_hours <= 6:
        return 30
    if age_hours <= 24:
        return 24
    if age_hours <= 72:
        return 16
    if age_hours <= 168:
        return 8
    return 2



def hot_score(item, source_weight: float, priority_boost: int = 0) -> int:
    base = 25
    base += int(contains_any(item["search_blob"], AI_TERMS) * 2)
    base += int(contains_any(item["search_blob"], REGULATION_TERMS) * 2)
    base += recency_score(item.get("published_dt"))
    base += int(source_weight * 10)
    base += min(priority_boost, 25)
    base += min(len(item.get("focus_matches") or []) * 6, 18)
    if item.get("source_type") == "hn":
        base += min(int(item.get("community_score", 0) / 20), 20)
        base += min(int(item.get("community_comments", 0) / 15), 12)
    return min(base, 100)



def make_writer_angle(topic: str, reg_score: int, item):
    if topic == "policy_regulation":
        return "适合做监管解读：讲清对象、边界、执行时间、对 AI 公司/开发者/创作者的影响。"
    if reg_score >= 45:
        return "适合从合规风险切入：这条可以写成『谁会受影响 + 现在要注意什么』。"
    if topic == "model_release":
        return "适合做快讯 + 对比稿：新模型能力、定位、和 Claude/GPT/Gemini/Qwen 的差异。"
    if topic == "infra_tools":
        return "适合写产业观察：平台层/工具链升级，重点讲它会让谁更快落地 AI。"
    if item.get("source_type") == "hn":
        return "适合加社区温度：可以引用开发者讨论，写成『行业怎么看』。"
    return "适合做信息整合稿：补充背景、时间线和影响范围，比单纯转述更有价值。"



def normalize_item(raw, source):
    title = (raw.get("title") or "").strip()
    url = canonicalize_url((raw.get("url") or "").strip())
    summary = clean_html(raw.get("summary") or raw.get("description") or "")
    published_dt = parse_date(raw.get("published_at") or raw.get("published") or "")
    search_blob = " ".join(filter(None, [title, summary, url, source.get("name", "")]))
    topic = classify_topic(search_blob)
    reg_score = regulatory_score(search_blob, source.get("category", "general"))
    focus_matches = detect_focus_matches(search_blob)
    item = {
        "id": hashlib.sha1(f"{source['id']}|{url or title}".encode("utf-8")).hexdigest()[:16],
        "title": title or "Untitled",
        "url": url,
        "summary": summary,
        "published_at": iso(published_dt) if published_dt else None,
        "source_id": source["id"],
        "source_name": source["name"],
        "source_type": source["type"],
        "source_type_label": SOURCE_TYPE_LABELS.get(source["type"], source["type"]),
        "source_category": source.get("category", "general"),
        "source_priority": int(source.get("priority_boost", 0) or 0),
        "topic": topic,
        "topic_label": TOPIC_LABELS.get(topic, TOPIC_LABELS["general"]),
        "regulatory_score": reg_score,
        "focus_matches": focus_matches,
        "entities": detect_entities(search_blob),
        "community_score": raw.get("community_score", 0),
        "community_comments": raw.get("community_comments", 0),
        "search_blob": search_blob,
        "published_dt": published_dt,
        "domain": urlparse(url).netloc.lower().replace("www.", "") if url else "",
    }
    item["hot_score"] = hot_score(item, float(source.get("weight", 1.0)), int(source.get("priority_boost", 0) or 0))
    item["writer_value_score"] = writer_value_score(topic, reg_score, source.get("category", "general"), summary, focus_matches)
    item["writer_angle"] = make_writer_angle(topic, reg_score, item)
    return item



def parse_feed(xml_bytes: bytes):
    root = ET.fromstring(xml_bytes)
    tag = strip_namespace(root.tag).lower()
    entries = []
    if tag == "rss":
        channel = next((child for child in list(root) if strip_namespace(child.tag).lower() == "channel"), None)
        items = [] if channel is None else [child for child in list(channel) if strip_namespace(child.tag).lower() == "item"]
        for item in items:
            entries.append({
                "title": child_text(item, "title"),
                "url": child_text(item, "link"),
                "summary": child_text(item, "description", "summary", "encoded", "content"),
                "published_at": child_text(item, "pubDate", "published", "updated", "date")
            })
        return entries

    if tag == "feed":
        items = [child for child in list(root) if strip_namespace(child.tag).lower() == "entry"]
        for item in items:
            entries.append({
                "title": child_text(item, "title"),
                "url": child_link(item),
                "summary": child_text(item, "summary", "content", "description"),
                "published_at": child_text(item, "published", "updated")
            })
        return entries

    raise ValueError(f"Unsupported feed type: {tag}")



def parse_anthropic_news(html: str, base_url: str):
    entries = []
    seen = set()
    pattern = re.compile(r'<a href="(?P<href>/news/[^"]+)"[^>]*>(?P<body>.*?)</a>', re.S)
    for match in pattern.finditer(html):
        href = match.group("href")
        body = match.group("body")
        title = ""
        for title_pattern in [
            r'<h[1-6][^>]*>(.*?)</h[1-6]>',
            r'<span[^>]*title[^>]*>(.*?)</span>',
            r'<div[^>]*title[^>]*>(.*?)</div>',
        ]:
            title_match = re.search(title_pattern, body, re.S | re.I)
            if title_match:
                title = clean_html(title_match.group(1))
                if title:
                    break
        if not title:
            continue
        summary_match = re.search(r'<p[^>]*>(.*?)</p>', body, re.S | re.I)
        summary = clean_html(summary_match.group(1)) if summary_match else ""
        time_match = re.search(r'<time[^>]*>(.*?)</time>', body, re.S | re.I)
        published_at = clean_html(time_match.group(1)) if time_match else ""
        full_url = canonicalize_url(urljoin(base_url, href))
        dedupe_key = (full_url, title)
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        entries.append({
            "title": title,
            "url": full_url,
            "summary": summary,
            "published_at": published_at,
        })
    return entries[:20]



def extract_meta_content(html: str, name: str):
    patterns = [
        rf'<meta[^>]+property=["\']{re.escape(name)}["\'][^>]+content=["\']([^"\']+)["\']',
        rf'<meta[^>]+name=["\']{re.escape(name)}["\'][^>]+content=["\']([^"\']+)["\']',
        rf'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']{re.escape(name)}["\']',
        rf'<meta[^>]+content=["\']([^"\']+)["\'][^>]+name=["\']{re.escape(name)}["\']',
    ]
    for pattern in patterns:
        match = re.search(pattern, html, re.I)
        if match:
            return clean_html(match.group(1))
    return ""



def extract_html_title(html: str):
    title = extract_meta_content(html, "og:title") or extract_meta_content(html, "twitter:title")
    if title:
        return title
    match = re.search(r"<title[^>]*>(.*?)</title>", html, re.I | re.S)
    return clean_html(match.group(1)) if match else ""



def extract_article_published_at(html: str):
    published = (
        extract_meta_content(html, "article:published_time")
        or extract_meta_content(html, "publish-date")
        or extract_meta_content(html, "parsely-pub-date")
        or extract_meta_content(html, "date")
    )
    if published:
        return published
    for pattern in [
        r'"datePublished"\s*:\s*"([^"]+)"',
        r'"dateModified"\s*:\s*"([^"]+)"',
    ]:
        match = re.search(pattern, html, re.I)
        if match:
            return clean_html(match.group(1))
    return ""



def parse_single_article_meta(html: str, url: str):
    title = extract_html_title(html)
    summary = extract_meta_content(html, "description") or extract_meta_content(html, "og:description")
    if not title:
        return []
    return [{
        "title": title,
        "url": canonicalize_url(url),
        "summary": summary,
        "published_at": extract_article_published_at(html),
    }]



def parse_company_blog_listing(html: str, base_url: str, item_limit: int = 8):
    base_netloc = urlparse(base_url).netloc.lower()
    candidates = []
    seen = set()
    patterns = [
        rf'https?://{re.escape(base_netloc)}/blog/[a-z0-9/_-]+',
        r'href=["\'](/blog/[^"\']+)["\']',
    ]

    for pattern in patterns:
        for match in re.finditer(pattern, html, re.I):
            raw = match.group(1) if match.groups() else match.group(0)
            raw = unescape(raw).replace('\\/', '/')
            href = canonicalize_url(urljoin(base_url, raw))
            parsed = urlparse(href)
            if parsed.netloc.lower() != base_netloc:
                continue
            path = parsed.path.rstrip("/")
            if path in {"", "/blog"}:
                continue
            if any(marker in path for marker in ["/tag/", "/tags/", "/category/", "/author/"]):
                continue
            if href in seen:
                continue
            seen.add(href)
            candidates.append(href)

    entries = []
    for href in candidates:
        try:
            article_html = fetch_bytes(href).decode("utf-8", "ignore")
        except Exception:
            continue
        title = extract_html_title(article_html)
        summary = extract_meta_content(article_html, "description") or extract_meta_content(article_html, "og:description")
        if not title:
            continue
        entries.append({
            "title": title,
            "url": href,
            "summary": summary,
            "published_at": extract_article_published_at(article_html),
        })
        if len(entries) >= item_limit:
            break
    return entries



def parse_a16z_news(html: str, base_url: str, item_limit: int = 8):
    entries = []
    seen = set()
    pattern = re.compile(r'<h4[^>]*>.*?<a href="(?P<href>https://a16z\.com/[^"]+)"[^>]*>(?P<title>.*?)</a>.*?</h4>', re.S | re.I)
    for match in pattern.finditer(html):
        href = canonicalize_url(match.group("href"))
        title = clean_html(match.group("title"))
        if not href or not title:
            continue
        if href in seen:
            continue
        seen.add(href)
        summary = ""
        published_at = ""
        try:
            article_html = fetch_bytes(href).decode("utf-8", "ignore")
            summary = extract_meta_content(article_html, "description") or extract_meta_content(article_html, "og:description")
            published_at = (
                extract_meta_content(article_html, "article:published_time")
                or extract_meta_content(article_html, "publish-date")
                or extract_meta_content(article_html, "parsely-pub-date")
            )
        except Exception:
            pass
        entries.append({
            "title": title,
            "url": href,
            "summary": summary,
            "published_at": published_at,
        })
        if len(entries) >= item_limit:
            break
    return entries



def fetch_rss_source(source):
    xml_bytes = fetch_bytes(source["url"])
    return parse_feed(xml_bytes)



def fetch_html_source(source):
    html = fetch_bytes(source["url"]).decode("utf-8", "ignore")
    parser = source.get("parser") or source.get("id")
    if parser == "anthropic_news":
        return parse_anthropic_news(html, source["url"])
    if parser == "a16z_news":
        return parse_a16z_news(html, source["url"], int(source.get("item_limit", 8)))
    if parser == "company_blog_listing":
        return parse_company_blog_listing(html, source["url"], int(source.get("item_limit", 8)))
    if parser == "single_article_meta":
        return parse_single_article_meta(html, source["url"])
    raise ValueError(f"Unsupported html parser: {parser}")



def fetch_hn_source(source):
    story_ids = fetch_json(source["url"])
    items = []
    keyword_blob = AI_TERMS | REGULATION_TERMS
    for story_id in story_ids[: int(source.get("limit", 60))]:
        try:
            data = fetch_json(f"https://hacker-news.firebaseio.com/v0/item/{story_id}.json")
        except Exception:
            continue
        title = (data.get("title") or "").strip()
        url = (data.get("url") or f"https://news.ycombinator.com/item?id={story_id}").strip()
        text = clean_html(data.get("text") or "")
        blob = f"{title} {url} {text}".lower()
        if not any(keyword in blob for keyword in keyword_blob):
            continue
        published = datetime.fromtimestamp(int(data.get("time", time.time())), tz=timezone.utc)
        items.append({
            "title": title,
            "url": url,
            "summary": text,
            "published_at": iso(published),
            "community_score": int(data.get("score", 0) or 0),
            "community_comments": int(data.get("descendants", 0) or 0),
        })
    return items



def dedupe_items(items):
    seen_keys = set()
    deduped = []
    for item in sorted(items, key=lambda x: (-x["hot_score"], -x["regulatory_score"], x["title"])):
        title_key = " ".join(sorted(title_tokens(item["title"])))
        url_key = item["url"]
        key = url_key or title_key
        if not key:
            continue
        if key in seen_keys:
            continue
        seen_keys.add(key)
        deduped.append(item)
    return deduped



def build_topics(items):
    grouped = defaultdict(list)
    for item in items:
        grouped[item["topic"]].append(item)
    topics = []
    for topic, topic_items in grouped.items():
        topics.append({
            "topic": topic,
            "label": TOPIC_LABELS.get(topic, TOPIC_LABELS["general"]),
            "count": len(topic_items),
            "items": [
                {
                    "id": item["id"],
                    "title": item["title"],
                    "source_name": item["source_name"],
                    "hot_score": item["hot_score"],
                    "regulatory_score": item["regulatory_score"],
                    "url": item["url"],
                }
                for item in sorted(topic_items, key=lambda x: (-x["hot_score"], -x["writer_value_score"]))[:5]
            ]
        })
    topics.sort(key=lambda x: (-x["count"], x["label"]))
    return topics



def apply_source_constraints(source, items):
    constrained = list(items)
    max_age_days = source.get("max_age_days")
    if max_age_days is not None:
        cutoff = now_utc() - timedelta(days=int(max_age_days))
        constrained = [
            item for item in constrained
            if not item.get("published_dt") or item["published_dt"].astimezone(timezone.utc) >= cutoff
        ]

    constrained.sort(key=lambda x: (-x["hot_score"], -x["writer_value_score"], -x["regulatory_score"], x["title"]))

    item_limit = source.get("item_limit") or source.get("limit")
    if item_limit:
        constrained = constrained[: int(item_limit)]
    return constrained



def event_rank_tuple(event):
    return (
        event["hot_score"],
        event["writer_value_score"],
        event["regulatory_score"],
        event["item_count"],
        event["source_count"],
    )



def select_event_stream(events, limit=18):
    ranked = sorted(events, key=event_rank_tuple, reverse=True)
    primary = []
    for event in ranked:
        title_lower = (event.get("title") or "").lower()
        entity_count = len(event.get("entities") or [])
        if any(term in title_lower for term in LOW_SIGNAL_TITLE_TERMS):
            continue
        if event["source_count"] == 1 and event["topic"] in {"general", "policy_regulation"} and entity_count == 0:
            continue

        is_high_signal = (
            event["source_count"] >= 2
            or event["item_count"] >= 2
            or (event["regulatory_score"] >= 36 and entity_count > 0)
            or (event["topic"] != "general" and event["hot_score"] >= 82)
        )
        if is_high_signal:
            primary.append(event)

    if len(primary) < limit:
        seen = {event["event_id"] for event in primary}
        for event in ranked:
            title_lower = (event.get("title") or "").lower()
            entity_count = len(event.get("entities") or [])
            if event["event_id"] in seen or any(term in title_lower for term in LOW_SIGNAL_TITLE_TERMS):
                continue
            if event["source_count"] == 1 and event["topic"] in {"general", "policy_regulation"} and entity_count == 0:
                continue
            primary.append(event)
            seen.add(event["event_id"])
            if len(primary) >= limit:
                break

    def stream_sort_key(event):
        ts = event.get("latest_published_at") or ""
        return (ts, event["hot_score"], event["writer_value_score"], event["regulatory_score"])

    primary = sorted(primary[:limit], key=stream_sort_key, reverse=True)
    return primary



def event_match_score(item, event):
    token_overlap = len(item["title_token_set"] & event["title_token_set"])
    entity_overlap = len(item["entity_set"] & event["entity_set"])

    if item["url"] and item["url"] == event["representative"]["url"]:
        return 100

    score = 0
    if token_overlap:
        score += token_overlap * 2
        if item["topic"] == event["topic"]:
            score += 1
        if item["domain"] and item["domain"] in event["domains"]:
            score += 1
        if entity_overlap:
            score += entity_overlap * 2

    return score



def trim_summary_text(text: str, limit: int = 220) -> str:
    text = clean_html(text or "")
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= limit:
        return text
    clipped = text[: limit - 1].rsplit(" ", 1)[0].strip()
    return (clipped or text[: limit - 1]).strip() + "…"



def build_event_content_summary(rep, items_sorted, source_names):
    candidate_summaries = []
    seen = set()
    for item in items_sorted:
        summary = trim_summary_text(item.get("summary") or "")
        if not summary:
            continue
        lowered = summary.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        candidate_summaries.append(summary)

    if candidate_summaries:
        primary = candidate_summaries[0]
        if len(candidate_summaries) >= 2 and primary != candidate_summaries[1] and len(primary) < 170:
            return trim_summary_text(f"{primary} 补充信号：{candidate_summaries[1]}", 260)
        return primary

    entities = rep.get("entities") or []
    entity_text = "、".join(entities[:3]) if entities else rep.get("topic_label", "AI 事件")
    if rep.get("topic") == "policy_regulation":
        return f"这是一条偏监管/政策的事件，核心对象涉及 {entity_text}，目前已从 {len(source_names)} 个来源检索到相关信号。"
    if rep.get("topic") == "model_release":
        return f"这是一条模型/发布类事件，焦点集中在 {entity_text}，目前已从 {len(source_names)} 个来源检索到相关信号。"
    if rep.get("topic") == "infra_tools":
        return f"这是一条工具/平台类事件，重点与 {entity_text} 相关，目前已从 {len(source_names)} 个来源检索到相关信号。"
    return f"这是一条 AI 事件流中的重点条目，当前已从 {len(source_names)} 个来源检索到相关信号。"



def build_events(items):
    events = []
    ranked_items = sorted(items, key=lambda x: (-x["hot_score"], -x["writer_value_score"], -x["regulatory_score"], x["title"]))
    for item in ranked_items:
        item["title_token_set"] = title_tokens(item["title"])
        item["entity_set"] = set(item.get("entities") or [])

        best_event = None
        best_score = 0
        for event in events:
            score = event_match_score(item, event)
            if score > best_score:
                best_event = event
                best_score = score

        if best_event and best_score >= 4:
            event = best_event
            event["items"].append(item)
            event["item_count"] += 1
            event["source_names"].add(item["source_name"])
            event["domains"].add(item["domain"])
            event["entity_set"].update(item["entity_set"])
            event["focus_matches"].update(item.get("focus_matches") or [])
            event["title_token_set"].update(item["title_token_set"])
            event["max_hot_score"] = max(event["max_hot_score"], item["hot_score"])
            event["max_regulatory_score"] = max(event["max_regulatory_score"], item["regulatory_score"])
            event["max_writer_value_score"] = max(event["max_writer_value_score"], item["writer_value_score"])
            if (item["hot_score"], item["writer_value_score"], item["regulatory_score"]) > (
                event["representative"]["hot_score"],
                event["representative"]["writer_value_score"],
                event["representative"]["regulatory_score"],
            ):
                event["representative"] = item
            if item.get("published_dt") and (
                not event.get("latest_published_dt") or item["published_dt"] > event["latest_published_dt"]
            ):
                event["latest_published_dt"] = item["published_dt"]
        else:
            events.append({
                "id": hashlib.sha1(f"event|{item['id']}|{item['title']}".encode("utf-8")).hexdigest()[:16],
                "topic": item["topic"],
                "topic_label": item["topic_label"],
                "items": [item],
                "item_count": 1,
                "source_names": {item["source_name"]},
                "domains": {item["domain"]},
                "entity_set": set(item["entity_set"]),
                "focus_matches": set(item.get("focus_matches") or []),
                "title_token_set": set(item["title_token_set"]),
                "representative": item,
                "max_hot_score": item["hot_score"],
                "max_regulatory_score": item["regulatory_score"],
                "max_writer_value_score": item["writer_value_score"],
                "latest_published_dt": item.get("published_dt"),
            })

    output = []
    for event in events:
        rep = event["representative"]
        source_names = sorted(event["source_names"])
        items_sorted = sorted(
            event["items"],
            key=lambda x: (-x["hot_score"], -x["writer_value_score"], -x["regulatory_score"], x["title"]),
        )
        if event["max_regulatory_score"] >= 45 and event["item_count"] >= 2:
            angle = "适合写成『事件全景 + 监管影响』：先讲发生了什么，再讲谁会受影响、接下来会怎么演变。"
        elif event["item_count"] >= 3 and len(source_names) >= 2:
            angle = "适合做整合稿：同一事件已有多源信号，最适合写时间线、背景和市场反应。"
        else:
            angle = rep["writer_angle"]
        summary = build_event_content_summary(rep, items_sorted, source_names)
        source_note = f"检索来源：{' / '.join(source_names[:4])}"
        output.append({
            "event_id": event["id"],
            "title": rep["title"],
            "url": rep["url"],
            "summary": summary,
            "source_note": source_note,
            "topic": event["topic"],
            "topic_label": event["topic_label"],
            "entities": sorted(event["entity_set"]),
            "focus_matches": sorted(event["focus_matches"]),
            "item_count": event["item_count"],
            "source_count": len(source_names),
            "source_names": source_names,
            "hot_score": event["max_hot_score"],
            "regulatory_score": event["max_regulatory_score"],
            "writer_value_score": event["max_writer_value_score"],
            "writer_angle": angle,
            "latest_published_at": iso(event["latest_published_dt"]) if event.get("latest_published_dt") else None,
            "items": [strip_internal_fields(item) for item in items_sorted[:6]],
        })

    output.sort(key=lambda x: (-x["hot_score"], -x["writer_value_score"], -x["regulatory_score"], x["title"]))
    return output



def build_writing_angles(events):
    angles = []
    for event in events[:12]:
        rationale_bits = [
            f"{event['item_count']} 条线索",
            f"{event['source_count']} 个来源",
            f"Hot {event['hot_score']}",
        ]
        if event["regulatory_score"] >= 24:
            rationale_bits.append(f"Reg {event['regulatory_score']}")
        angles.append({
            "event_id": event["event_id"],
            "title": event["title"],
            "topic_label": event["topic_label"],
            "angle": event["writer_angle"],
            "rationale": " · ".join(rationale_bits),
            "url": event["url"],
            "hot_score": event["hot_score"],
            "regulatory_score": event["regulatory_score"],
            "item_count": event["item_count"],
            "source_count": event["source_count"],
        })
    return angles[:8]



def build_focus_watch(items, limit=12):
    focused = [item for item in items if item.get("focus_matches")]

    def focus_sort_key(item):
        return (
            len(item.get("focus_matches") or []),
            item.get("source_priority", 0),
            item["hot_score"],
            item.get("published_at") or "",
            item["writer_value_score"],
        )

    companies = sorted(
        [item for item in focused if any(match in TRACKED_COMPANIES for match in item.get("focus_matches") or [])],
        key=focus_sort_key,
        reverse=True,
    )
    voices = sorted(
        [item for item in focused if any(match in TRACKED_VOICES for match in item.get("focus_matches") or [])],
        key=focus_sort_key,
        reverse=True,
    )
    all_ranked = sorted(focused, key=focus_sort_key, reverse=True)

    selected = []
    seen = set()

    def take_from(bucket, quota):
        for item in bucket:
            if item["id"] in seen:
                continue
            selected.append(item)
            seen.add(item["id"])
            if len([x for x in selected if x in bucket]) >= quota or len(selected) >= limit:
                break

    company_quota = min(max(limit // 2, 4), limit)
    voice_quota = min(max(limit - company_quota, 4), limit)
    take_from(companies, company_quota)
    take_from(voices, voice_quota)

    for item in all_ranked:
        if len(selected) >= limit:
            break
        if item["id"] in seen:
            continue
        selected.append(item)
        seen.add(item["id"])

    return [strip_internal_fields(item) for item in selected[:limit]]



def summary_sentence(items, events):
    if not items:
        return "这一次没有抓到可用热点。"
    top = events[:3] if events else items[:3]
    topic_counts = Counter(item["topic_label"] for item in items)
    dominant_topic, dominant_count = topic_counts.most_common(1)[0]
    reg_count = sum(1 for item in items if item["regulatory_score"] >= 40)
    return (
        f"本轮共抓到 {len(items)} 条有效热点，已聚合成 {len(events)} 个事件，当前最集中的主题是『{dominant_topic}』({dominant_count} 条)，"
        f"其中 {reg_count} 条具备较强监管相关性。重点可先看："
        + " / ".join(item["title"] for item in top)
    )



def strip_internal_fields(item):
    cleaned = dict(item)
    for key in ["search_blob", "published_dt", "domain", "title_token_set", "entity_set"]:
        cleaned.pop(key, None)
    return cleaned



def archive_snapshot(name: str, payload):
    today = now_utc().astimezone().strftime("%Y-%m-%d")
    stamp = now_utc().astimezone().strftime("%H%M%S")
    target_dir = HISTORY_DIR / today
    target_dir.mkdir(parents=True, exist_ok=True)
    (target_dir / f"{stamp}-{name}.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )



def run_once():
    ensure_dirs()
    started = now_utc()
    sources = load_sources()
    source_status = []
    all_items = []

    for source in sources:
        source_started = time.time()
        status = {
            "source_id": source["id"],
            "source_name": source["name"],
            "source_type": source["type"],
            "source_category": source.get("category", "general"),
            "ok": False,
            "items": 0,
            "error": None,
        }
        try:
            if source["type"] == "rss":
                raw_items = fetch_rss_source(source)
            elif source["type"] == "hn":
                raw_items = fetch_hn_source(source)
            elif source["type"] == "html":
                raw_items = fetch_html_source(source)
            else:
                raise ValueError(f"Unsupported source type: {source['type']}")
            filtered_items = []
            for item in raw_items:
                if not (item.get("title") or item.get("url")):
                    continue
                blob = " ".join(filter(None, [item.get("title", ""), item.get("summary", ""), item.get("url", "")]))
                if not is_relevant_item(blob, source.get("category", "general")):
                    continue
                filtered_items.append(item)
            normalized = [normalize_item(item, source) for item in filtered_items]
            normalized = apply_source_constraints(source, normalized)
            all_items.extend(normalized)
            status["ok"] = True
            status["items"] = len(normalized)
        except Exception as exc:
            status["error"] = str(exc)
        status["duration_ms"] = int((time.time() - source_started) * 1000)
        status["checked_at"] = iso(now_utc())
        source_status.append(status)

    deduped = dedupe_items(all_items)
    deduped.sort(key=lambda x: (-x["hot_score"], -x["writer_value_score"], -x["regulatory_score"], x["title"]))
    events = build_events(deduped)
    event_stream = select_event_stream(events, limit=18)
    top_items = [strip_internal_fields(item) for item in deduped[:20]]
    regulation_watch = [
        strip_internal_fields(item)
        for item in sorted(deduped, key=lambda x: (-x["regulatory_score"], -x["hot_score"]))[:12]
        if item["regulatory_score"] >= 24
    ]
    dashboard = {
        "generated_at": iso(now_utc()),
        "next_fetch_at": iso(now_utc() + timedelta(minutes=FETCH_INTERVAL_MINUTES)),
        "fetch_interval_minutes": FETCH_INTERVAL_MINUTES,
        "summary": summary_sentence(deduped, event_stream),
        "tracked_focus": {
            "companies": TRACKED_COMPANIES,
            "voices": TRACKED_VOICES,
        },
        "focus_watch": build_focus_watch(deduped),
        "top_items": top_items,
        "top_events": event_stream,
        "event_stream": event_stream,
        "regulation_watch": regulation_watch,
        "topic_clusters": build_topics(deduped),
        "writing_angles": build_writing_angles(event_stream),
        "source_status": source_status,
        "stats": {
            "total_items": len(deduped),
            "total_events": len(events),
            "regulatory_items": sum(1 for item in deduped if item["regulatory_score"] >= 40),
            "community_items": sum(1 for item in deduped if item["source_type"] == "hn"),
            "official_items": sum(1 for item in deduped if item["source_category"] in {"official", "ai"} and item["source_type"] in {"rss", "html"}),
            "sources_ok": sum(1 for status in source_status if status["ok"]),
            "sources_total": len(source_status),
        }
    }
    items_payload = {
        "generated_at": dashboard["generated_at"],
        "items": [strip_internal_fields(item) for item in deduped],
        "events": dashboard["top_events"],
    }
    status_payload = {
        "generated_at": dashboard["generated_at"],
        "started_at": iso(started),
        "finished_at": iso(now_utc()),
        "interval_minutes": FETCH_INTERVAL_MINUTES,
        "sources": source_status,
    }

    (DATA_DIR / "dashboard.json").write_text(json.dumps(dashboard, ensure_ascii=False, indent=2), encoding="utf-8")
    (DATA_DIR / "items.json").write_text(json.dumps(items_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    (DATA_DIR / "fetch_status.json").write_text(json.dumps(status_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    archive_snapshot("dashboard", dashboard)
    archive_snapshot("items", items_payload)
    return dashboard



if __name__ == "__main__":
    dashboard = run_once()
    print(json.dumps({
        "ok": True,
        "generated_at": dashboard["generated_at"],
        "items": dashboard["stats"]["total_items"],
        "events": dashboard["stats"]["total_events"],
        "sources_ok": dashboard["stats"]["sources_ok"],
        "sources_total": dashboard["stats"]["sources_total"],
    }, ensure_ascii=False, indent=2))
