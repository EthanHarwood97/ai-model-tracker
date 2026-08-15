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
        import httpx
        message = " | ".join(c["name"] for c in new_events[:10])
        try:
            httpx.post(url, timeout=10, json={"title": "New AI models detected", "message": message})
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
            aa_price = ent["price_mtok"]
            for m in market_rows:
                if m.get("extra", {}).get("or_id") and canon(m["extra"]["or_id"]) == ent["plain"]:
                    p = m["extra"].get("price_blended")
                    if p is not None:
                        ent["aa_price_mtok"] = aa_price
                        ent["price_mtok"] = p
                        ent["price_source"] = "openrouter"
                        ent.setdefault("detail", {})
                        ent["detail"]["price_input"] = m["extra"].get("price_prompt")
                        ent["detail"]["price_output"] = m["extra"].get("price_completion")
                        if aa_price and aa_price > 0 and ent.get("cost_task"):
                            ratio = p / aa_price
                            if 0.2 <= ratio <= 5 and abs(ratio - 1) > 0.02:
                                ent["cost_task"] = round(ent["cost_task"] * ratio, 4)
                                ent["detail"]["cost_adjusted"] = round(ratio, 3)
                    break
        existing_plains = {ent["plain"] for ent in entities}
        lb_by_name = {}
        for r in data.get("livebench", []):
            lb_by_name.setdefault(r["name"], {})[r["kind"]] = r
        for lb_name, kinds in lb_by_name.items():
            plain = canon(lb_name)
            if not plain or plain in existing_plains:
                continue
            coding = kinds.get("livebench_coding", {}).get("score")
            if coding is None:
                continue
            global_row = kinds.get("livebench_global", {})
            cost = (global_row.get("extra") or {}).get("cost_per_task")
            ent = {
                "slug": "livebench-" + plain,
                "plain": plain,
                "name": lb_name,
                "harness": None,
                "effort": None,
                "measured": False,
                "coding_index": coding,
                "cost_task": cost,
                "wall_time_s": None,
                "intelligence": global_row.get("score"),
                "price_mtok": None,
                "model_name": lb_name,
                "est_band": None,
                "detail": {"source": "livebench"},
                "meta": None,
                "meta_min": None,
                "meta_max": None,
                "n_sources": 1,
                "components": {},
                "categories": [],
            }
            for m in market_rows:
                if m.get("extra", {}).get("or_id") and canon(m["extra"]["or_id"]) == plain:
                    p = m["extra"].get("price_blended")
                    if p is not None:
                        ent["price_mtok"] = p
                        ent["price_source"] = "openrouter"
                        ent["detail"]["price_input"] = m["extra"].get("price_prompt")
                        ent["detail"]["price_output"] = m["extra"].get("price_completion")
                    break
            entities.append(ent)
        ttft_all = [ent.get("time_to_first_answer") for ent in entities]
        speed_all = [ent.get("output_speed") for ent in entities]

        def _speed_norm(values, value, lower_better):
            xs = [v for v in values if v is not None]
            if not xs or value is None:
                return None
            mn, mx = min(xs), max(xs)
            if mx == mn:
                return 50.0
            ratio = (value - mn) / (mx - mn)
            return (1 - ratio) * 100 if lower_better else ratio * 100

        for ent in entities:
            parts = []
            n_ttft = _speed_norm(ttft_all, ent.get("time_to_first_answer"), True)
            n_speed = _speed_norm(speed_all, ent.get("output_speed"), False)
            if n_ttft is not None:
                parts.append(n_ttft)
            if n_speed is not None:
                parts.append(n_speed)
            ent["speed"] = round(sum(parts) / len(parts), 1) if parts else None
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
