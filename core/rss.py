import hashlib
import json
import re
import time
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass
from pathlib import Path

USER_AGENT = "Mozilla/5.0 BitClient"


@dataclass
class Feed:
    name: str
    url: str
    include: str = ""
    exclude: str = ""
    category: str = ""
    interval: int = 30
    enabled: bool = True
    last_check: float = 0.0
    primed: bool = False


@dataclass
class Found:
    feed: str
    title: str
    source: str
    category: str


class RssStore:
    def __init__(self, path):
        self.path = Path(path)
        self.feeds: list[Feed] = []
        self.seen: dict[str, None] = {}
        self.load()

    def load(self) -> None:
        if not self.path.exists():
            return
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            return
        fields = Feed.__dataclass_fields__
        self.feeds = [Feed(**{k: v for k, v in f.items() if k in fields})
                      for f in data.get("feeds", [])]
        self.seen = dict.fromkeys(data.get("seen", []))

    def save(self) -> None:
        payload = {
            "feeds": [asdict(f) for f in self.feeds],
            "seen": list(self.seen)[-5000:],
        }
        self.path.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _fetch(url: str, timeout: int = 20) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


def _pick_source(links: list[str]) -> str:
    for link in links:
        if link.startswith("magnet:"):
            return link
    for link in links:
        if ".torrent" in link.lower():
            return link
    return links[0] if links else ""


def parse_feed(data: bytes) -> list[dict]:
    root = ET.fromstring(data)
    entries = []
    for node in root.iter():
        if _local(node.tag) not in ("item", "entry"):
            continue
        title = ""
        guid = ""
        links = []
        for child in node:
            name = _local(child.tag)
            text = (child.text or "").strip()
            if name == "title":
                title = text
            elif name in ("guid", "id"):
                guid = text
            elif name == "link":
                href = child.get("href") or text
                if href:
                    links.append(href)
            elif name == "enclosure":
                if child.get("url"):
                    links.append(child.get("url"))
            elif "magnet" in name.lower() and text:
                links.append(text)
        source = _pick_source(links)
        entries.append({"title": title, "guid": guid or source or title, "source": source})
    return entries


def run_check(feeds: list[Feed], seen, torrents_dir, force: bool = False):
    found: list[Found] = []
    new_seen: list[str] = []
    states: dict[str, tuple[float, bool]] = {}
    errors: list[str] = []
    now = time.time()
    Path(torrents_dir).mkdir(parents=True, exist_ok=True)
    known = set(seen)
    for feed in feeds:
        if not feed.enabled:
            continue
        if not force and now - feed.last_check < feed.interval * 60:
            continue
        try:
            entries = parse_feed(_fetch(feed.url))
            include = re.compile(feed.include, re.I) if feed.include else None
            exclude = re.compile(feed.exclude, re.I) if feed.exclude else None
        except Exception as e:
            errors.append(f"{feed.name}: {e}")
            states[feed.url] = (now, feed.primed)
            continue
        for entry in entries:
            guid = entry["guid"]
            if guid in known:
                continue
            title = entry["title"]
            if not feed.primed:
                known.add(guid)
                new_seen.append(guid)
                continue
            if (include and not include.search(title)) or (exclude and exclude.search(title)):
                known.add(guid)
                new_seen.append(guid)
                continue
            source = entry["source"]
            if source and not source.startswith("magnet:"):
                try:
                    blob = _fetch(source)
                    if not blob.startswith(b"d"):
                        raise ValueError("ответ не похож на .torrent")
                    path = Path(torrents_dir) / (hashlib.sha1(source.encode()).hexdigest() + ".torrent")
                    path.write_bytes(blob)
                    source = str(path)
                except Exception as e:
                    errors.append(f"{feed.name} / {title[:40]}: {e}")
                    continue
            known.add(guid)
            new_seen.append(guid)
            if source:
                found.append(Found(feed.name, title, source, feed.category))
        states[feed.url] = (now, True)
    return found, new_seen, states, errors
