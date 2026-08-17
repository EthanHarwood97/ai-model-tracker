import hashlib
import json
import pathlib
import random
import time

import httpx

CONFIG_PATH = pathlib.Path(__file__).resolve().parent.parent / "config.json"
DATA_DIR = pathlib.Path(__file__).resolve().parent.parent / "data"


def load_config():
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


class Fetcher:
    def __init__(self, config=None):
        self.config = config or load_config()
        http_cfg = self.config["http"]
        self.timeout = http_cfg.get("timeout", 45)
        self.max_retries = http_cfg.get("max_retries", 3)
        self.backoff_sec = http_cfg.get("backoff_sec", 20)
        self.ua = http_cfg.get("user_agent")
        self.cache_dir = pathlib.Path(self.config.get("cache_dir", "data/cache"))
        if not self.cache_dir.is_absolute():
            self.cache_dir = DATA_DIR.parent / self.cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.last_status = {}
        self.force_refresh = False

    def _cache_path(self, url):
        key = hashlib.sha256(url.encode("utf-8")).hexdigest()[:20]
        return self.cache_dir / (key + ".bin")

    def get(self, url, ttl=1800, headers=None, force=False):
        force = force or self.force_refresh
        cp = self._cache_path(url)
        if not force and cp.exists() and (time.time() - cp.stat().st_mtime) < ttl:
            r = httpx.Response(200, content=cp.read_bytes(), request=httpx.Request("GET", url))
            r.raise_for_status()
            return r
        last_err = None
        for attempt in range(self.max_retries):
            try:
                h = {"User-Agent": self.ua, "Accept": "*/*"}
                h.update(headers or {})
                with httpx.Client(follow_redirects=True, timeout=self.timeout, headers=h) as c:
                    r = c.get(url)
                self.last_status[url] = r.status_code
                if r.status_code in (403, 429):
                    wait = self.backoff_sec * (2 ** attempt) + random.uniform(0, 8)
                    time.sleep(wait)
                    last_err = RuntimeError(f"HTTP {r.status_code}")
                    continue
                if r.status_code >= 400:
                    raise httpx.HTTPStatusError(
                        f"HTTP {r.status_code} for {url}", request=r.request, response=r
                    )
                cp.write_bytes(r.content)
                return r
            except httpx.HTTPStatusError:
                raise
            except Exception as e:
                last_err = e
                time.sleep(self.backoff_sec * (2 ** attempt))
        raise RuntimeError(f"fetch failed for {url}: {last_err}")
