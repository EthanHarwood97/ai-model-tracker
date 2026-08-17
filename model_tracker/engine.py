import json as _json
import logging
import re
import threading

from . import alerts
from .composite import build_components, compute_entities
from .estimator import attach_model_to_coding, estimate_all, match_coding_to_models, regress
from .normalize import canon, plain_key
from .recommendations import build_recommendations
from .sources import SOURCES
from .validation import validate_rows

log = logging.getLogger("tracker")


class Engine:
    def __init__(self, cfg, store, fetcher):
        self.cfg = cfg
        self.store = store
        self.fetcher = fetcher
        self.last_cycle = None
        self.generation_lock = threading.RLock()
        self.fetch_lock = threading.Lock()
        self.last_recommendations = {}

    def run_source(self, name, force=False):
        fetch_fn = SOURCES[name]
        try:
            with self.fetch_lock:
                previous_force = self.fetcher.force_refresh
                self.fetcher.force_refresh = bool(force)
                try:
                    rows = fetch_fn(self.fetcher)
                finally:
                    self.fetcher.force_refresh = previous_force
            validate_rows(name, rows)
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
                d["extra"].setdefault("retrieved_at", snaps[0]["ts"])
                rows.append(d)
            data[name] = rows
        return data

    def compute(self):
        with self.generation_lock:
            return self._compute()

    def _compute(self):
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
            exact_matches = []
            prefix_matches = []
            ent_plain = ent["plain"]
            for m in market_rows:
                or_id = m.get("extra", {}).get("or_id")
                if not or_id:
                    continue
                c = plain_key(canon(or_id))
                if c == ent_plain:
                    exact_matches.append(m)
                elif c and (c.startswith(ent_plain + ".") or c.startswith(ent_plain + "-")):
                    prefix_matches.append(m)
            matches = exact_matches or prefix_matches
            if not matches:
                continue

            ent_name_lc = re.sub(r"[^a-z0-9]+", " ", (ent.get("name") or "").lower()).strip()
            ent_tokens = {t for t in ent_name_lc.split() if len(t) > 1}

            def token_score(mm):
                or_name = (mm.get("extra") or {}).get("or_name") or mm["extra"].get("or_id") or ""
                on_tokens = {t for t in re.sub(r"[^a-z0-9]+", " ", or_name.lower()).strip().split() if len(t) > 1}
                return len(ent_tokens & on_tokens)

            scored = [(mm, token_score(mm)) for mm in matches]
            top_token = max(s for _, s in scored)
            top = [mm for mm, score in scored if score == top_token]
            if len(top) > 1:
                ent.setdefault("detail", {})["identity_status"] = "ambiguous_price_match"
                continue
            m = top[0]
            p = m["extra"].get("price_blended")
            if p is not None:
                ent["aa_price_mtok"] = aa_price
                ent["price_mtok"] = p
                ent["price_source"] = "openrouter"
                ent["provider_route_id"] = m["extra"].get("or_id")
                ent["cost_basis"] = "token_price"
                ent["supports_tools"] = m["extra"].get("supports_tools")
                if m["extra"].get("input_modalities"):
                    ent["accepts_image"] = "image" in m["extra"]["input_modalities"]
                ent.setdefault("detail", {})
                ent["detail"]["price_input"] = m["extra"].get("price_prompt")
                ent["detail"]["price_output"] = m["extra"].get("price_completion")
        existing_plains = {ent["plain"] for ent in entities}
        lb_by_name = {}
        for r in data.get("livebench", []):
            lb_by_name.setdefault(r["name"], {})[r["kind"]] = r
        for lb_name, kinds in lb_by_name.items():
            plain = plain_key(canon(lb_name))
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
                "measurement_type": "livebench",
                "score_source": "livebench_coding",
                "coding_index": coding,
                "aa_model_coding_index": None,
                "cost_task": cost,
                "cost_basis": "benchmark_task" if cost is not None else None,
                "wall_time_s": None,
                "intelligence": None,
                "intelligence_estimated": None,
                "deprecated": False,
                "price_mtok": None,
                "price_input": None,
                "price_output": None,
                "price_source": None,
                "provider_route_id": None,
                "model_name": lb_name,
                "est_band": None,
                "detail": {
                    "source": "livebench",
                    "benchmark_id": "livebench_coding",
                    "measurement_type": "livebench",
                    "coding_support": {
                        "value": coding,
                        "benchmark_values": {"livebench_coding": coding},
                        "sources": [{"source": "livebench", "kind": "livebench_coding", "raw": coding}],
                    },
                },
                "meta": None,
                "meta_min": None,
                "meta_max": None,
                "n_sources": 1,
                "coverage": 0.0,
                "components": {},
                "categories": ["coding_support"],
                "supports_tools": None,
                "accepts_image": None,
            }
            for m in market_rows:
                if m.get("extra", {}).get("or_id") and plain_key(canon(m["extra"]["or_id"])) == plain:
                    p = m["extra"].get("price_blended")
                    if p is not None:
                        ent["price_mtok"] = p
                        ent["price_source"] = "openrouter"
                        ent["provider_route_id"] = m["extra"].get("or_id")
                        ent["cost_basis"] = "token_price"
                        ent["supports_tools"] = m["extra"].get("supports_tools")
                        ent["detail"]["price_input"] = m["extra"].get("price_prompt")
                        ent["detail"]["price_output"] = m["extra"].get("price_completion")
                    break
            entities.append(ent)
        ds_rows = data.get("deepseek", [])
        ds_by_plain = {}
        for m in ds_rows:
            extra = m.get("extra") or {}
            if not isinstance(extra, dict):
                extra = {}
            official = {k: v for k, v in extra.items() if k not in ("or_id", "version")}
            if official:
                ds_by_plain[plain_key(canon(m["name"]))] = official
        for alias, target in (
            ("deepseek4-flash", "deepseek4-flash-0731"),
            ("deepseek4-pro", "deepseek4-pro-0813"),
        ):
            if alias not in ds_by_plain and target in ds_by_plain:
                ds_by_plain[alias] = ds_by_plain[target]
        for ent in entities:
            official = ds_by_plain.get(ent["plain"])
            if not official:
                continue
            detail = ent.setdefault("detail", {})
            detail["ds_official"] = official
            off_in = official.get("cache_miss_off_peak")
            off_out = official.get("output_off_peak")
            peak_in = official.get("cache_miss_peak")
            peak_out = official.get("output_peak")
            if (
                isinstance(off_in, (int, float))
                and isinstance(off_out, (int, float))
                and isinstance(peak_in, (int, float))
                and isinstance(peak_out, (int, float))
            ):
                if ent.get("price_source") == "openrouter":
                    detail["openrouter_price_mtok"] = ent.get("price_mtok")
                    detail["openrouter_price_input"] = detail.get("price_input")
                    detail["openrouter_price_output"] = detail.get("price_output")
                ent["price_mtok"] = round((float(off_in) * 3 + float(off_out)) / 4, 4)
                ent["price_source"] = "deepseek_official"
                ent["cost_basis"] = "token_price"
                detail["price_input"] = off_in
                detail["price_output"] = off_out
                detail["price_schedule"] = {
                    "off_peak": [off_in, off_out],
                    "peak": [peak_in, peak_out],
                    "peak_hours_utc": official.get("peak_hours_utc"),
                }
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
            detail = ent.setdefault("detail", {})
            if ent.get("price_input") is not None:
                detail.setdefault("price_input", ent["price_input"])
            if ent.get("price_output") is not None:
                detail.setdefault("price_output", ent["price_output"])
            if ent.get("provider_route_id") is not None:
                detail["provider_route_id"] = ent["provider_route_id"]
            if ent.get("price_source") is not None:
                detail["price_source"] = ent["price_source"]
        diag = regress(pairs)
        self.store.replace_scores(entities)
        self.last_recommendations = build_recommendations(entities, self.cfg)
        self.last_cycle = {
            "n_coding": len(coding_rows),
            "n_models": len(model_rows),
            "n_est": len(est_rows),
            "n_pairs": len(pairs),
            "n_entities": len(entities),
            "regression": diag,
            "new_slugs": sorted(new_slugs),
            "recommendations": {
                role: result.get("recommended", {}).get("name") if result.get("recommended") else None
                for role, result in self.last_recommendations.items()
            },
        }
        return entities

    def cycle(self, force=False):
        with self.generation_lock:
            results, errors = self.run_all(force=force)
            entities = self._compute()
            return results, errors, entities

    def recommendations(self):
        if self.last_recommendations:
            return self.last_recommendations
        rows = self.store.latest_scores()
        entities = []
        for row in rows:
            entity = dict(row)
            for field in ("components", "detail"):
                try:
                    entity[field] = _json.loads(entity.get(field) or "{}")
                except Exception:
                    entity[field] = {}
            entity["source_names"] = entity["detail"].get("source_names", [])
            entity["evidence_groups"] = entity["detail"].get("evidence_groups", [])
            entities.append(entity)
        self.last_recommendations = build_recommendations(entities, self.cfg)
        return self.last_recommendations

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
            elif name == "models":
                out.append(s)
        return out
