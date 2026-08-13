import json as _json
import logging

from . import alerts
from .composite import build_components, build_market, compute_entities
from .estimator import attach_model_to_coding, estimate_all, match_coding_to_models, regress
from .normalize import canon, plain_key
from .sources import SOURCES

log = logging.getLogger("tracker")


class Engine:
    def __init__(self, cfg, store, fetcher):
        self.cfg = cfg
        self.store = store
        self.fetcher = fetcher
        self.last_cycle = None

    def run_source(self, name, force=False):
        fetch_fn = SOURCES[name]
        try:
            rows = fetch_fn(self.fetcher)
            snap = self.store.begin_snapshot(name, True)
            self.store.insert_rows(snap, name, rows)
            self.store.finish_snapshot(snap, len(rows))
            prev = self.store.snapshots_for(name, 2)
            changes = []
            if len(prev) >= 2:
                threshold = self.cfg["sources"].get(name, {}).get("change_threshold", 0.01)
                changes = self.store.detect_changes(name, prev[1], prev[0], threshold=threshold)
            new_events = [c for c in changes if c["event"] == "new"]
            self.store.insert_changes(changes)
            if new_events:
                alerts.console_banner(name, [f"{c['name']}  (first seen in {c['source']})" for c in new_events])
                if self.cfg.get("alerts", {}).get("desktop_toast", True):
                    names = ", ".join(c["name"] for c in new_events[:5])
                    alerts.desktop_toast("AI Model Tracker - new models", names)
                webhook = self.cfg.get("alerts", {}).get("webhook_url")
                if webhook:
                    self._webhook(webhook, new_events)
            return rows, changes
        except Exception as e:
            self.store.begin_snapshot(name, False, error=str(e))
            raise

    def _webhook(self, url, new_events):
        import json as _json

        import httpx
        message = " | ".join(c["name"] for c in new_events[:10])
        try:
            httpx.post(url, timeout=10, data=_json.dumps({"title": "New AI models detected", "message": message}),
                       headers={"Content-Type": "application/json"})
        except Exception:
            pass

    def run_all(self, force=False, only=None):
        results = {}
        errors = {}
        names = [n for n in SOURCES if self.cfg["sources"].get(n, {}).get("enabled", True)] if only is None else only
        for name in names:
            log.info("scraping %s", name)
            try:
                rows, changes = self.run_source(name, force=force)
                results[name] = {"rows": len(rows), "changes": changes}
            except Exception as e:
                log.warning("source %s failed: %s", name, e)
                errors[name] = str(e)
        return results, errors

    def _latest_rows(self):
        data = {}
        for name in SOURCES:
            snaps = self.store.snapshots_for(name, 1)
            if not snaps:
                continue
            rows = []
            for r in self.store.rows_for(snaps[0]["id"]):
                d = dict(r)
                try:
                    d["extra"] = _json.loads(d["extra"]) if d.get("extra") else {}
                except Exception:
                    d["extra"] = {}
                rows.append(d)
            data[name] = rows
        return data

    def compute(self):
        data = self._latest_rows()
        coding_rows = [r for r in data.get("aa_coding", []) if r["kind"] == "coding_index"]
        model_rows = [r for r in data.get("aa_models", []) if r["kind"] == "intelligence"]
        pairs, matched = match_coding_to_models(coding_rows, model_rows)
        est_rows = estimate_all(model_rows, matched, self.cfg, pairs=pairs)
        attach = attach_model_to_coding(pairs)
        comps = build_components(
            {k: v for k, v in data.items() if k not in ("aa_coding", "aa_models")},
            self.cfg,
        )
        entities = compute_entities(coding_rows, model_rows, est_rows, attach, comps, self.cfg)
        market_rows = data.get("openrouter", [])
        for ent in entities:
            for m in market_rows:
                if m.get("extra", {}).get("or_id") and canon(m["extra"]["or_id"]) == ent["plain"]:
                    p = m["extra"].get("price_blended")
                    if p is not None:
                        ent["price_mtok"] = p
                        ent["price_source"] = "openrouter"
                        ent.setdefault("detail", {})
                        ent["detail"]["price_input"] = m["extra"].get("price_prompt")
                        ent["detail"]["price_output"] = m["extra"].get("price_completion")
                    break
        new_slugs = set()
        for ch in self.store.recent_changes(400):
            if ch["event"] == "new" and ch["slug"]:
                new_slugs.add(plain_key(ch["slug"]))
                new_slugs.add(canon(ch["name"]))
        for ent in entities:
            ent["is_new"] = ent["plain"] in new_slugs or ent["slug"] in new_slugs
        diag = regress(pairs)
        self.store.replace_scores(entities)
        self.last_cycle = {
            "n_coding": len(coding_rows),
            "n_models": len(model_rows),
            "n_est": len(est_rows),
            "n_pairs": len(pairs),
            "n_entities": len(entities),
            "regression": diag,
            "new_slugs": sorted(new_slugs),
        }
        return entities

    def cycle(self, force=False):
        results, errors = self.run_all(force=force)
        entities = self.compute()
        return results, errors, entities

    def view(self, name):
        scores = self.store.latest_scores()
        out = []
        for s in scores:
            if name == "coding":
                if not s["measured"]:
                    continue
                out.append(s)
            elif name == "est":
                if s["measured"]:
                    continue
                out.append(s)
            elif name == "meta":
                if s["meta"] is not None:
                    out.append(s)
            elif name == "value":
                if s["cost_task"] is not None or s["price_mtok"] is not None:
                    out.append(s)
        return out
