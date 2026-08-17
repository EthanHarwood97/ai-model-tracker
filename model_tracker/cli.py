import argparse
import logging
import sys

import uvicorn

from .engine import Engine
from .http import Fetcher, load_config
from .scheduler import Scheduler
from .store import Store
from .web import create_app


def _build():
    cfg = load_config()
    store = Store(cfg["db_path"])
    fetcher = Fetcher(cfg)
    return cfg, store, fetcher, Engine(cfg, store, fetcher)


def cmd_scrape(args):
    cfg, store, fetcher, engine = _build()
    rows, changes = engine.run_source(args.source, force=True)
    print(f"{args.source}: {len(rows)} rows")
    for r in sorted(rows, key=lambda x: -(x.get("score") or 0))[:args.limit]:
        extra = r.get("extra") or {}
        name = r["name"][:60]
        print(f"  {str(r.get('score')):>8}  {r.get('kind'):<18} {name}  { {k: v for k, v in extra.items() if k not in ('window',)} if args.verbose else ''}")
    for c in changes:
        print(f"  CHANGE [{c['event']}] {c['name']}")


def cmd_run_once(args):
    cfg, store, fetcher, engine = _build()
    results, errors, entities = engine.cycle(force=args.force)
    for name, res in results.items():
        print(f"  {name}: {res['rows']} rows, {len(res['changes'])} changes")
    for name, err in errors.items():
        print(f"  {name}: FAILED {err}")
    print_summary(entities)


def print_summary(entities):
    meta = [e for e in entities if e["meta"] is not None]
    meta.sort(key=lambda e: -e["meta"])
    print("\n=== META TOP 15 ===")
    for e in meta[:15]:
        band = ""
        if e.get("meta_min") is not None and e.get("meta_max") is not None:
            band = f" [{e['meta_min']}-{e['meta_max']}]"
        badge = "measured" if e["measured"] else "ESTIMATED"
        new = " NEW" if e.get("is_new") else ""
        print(f"  {e['meta']:6.2f}{band:16}  {badge:9}  {e['name'][:45]:45}  n={e['n_sources']}{new}")
    est = [e for e in entities if not e["measured"]]
    est.sort(key=lambda e: -(e["coding_index"] or 0))
    print("\n=== EST TOP 10 ===")
    for e in est[:10]:
        d = e.get("detail") or {}
        band = d.get("band_points") or e.get("band") or 0.0
        price = f"${e['price_mtok']:.2f}" if e.get("price_mtok") is not None else "n/a"
        extra = " extrapolated" if d.get("extrapolated") else ""
        print(f"  {e['coding_index'] or 0:6.2f} +/-{band:.1f}  {e['name'][:45]:45}  {price}/Mtok{extra}")


def cmd_serve(args):
    cfg, store, fetcher, engine = _build()
    results, errors, entities = engine.cycle(force=False)
    print_summary(entities)
    scheduler = Scheduler(cfg, engine)
    scheduler.start()
    app = create_app(engine, scheduler)
    host = cfg["server"]["host"]
    port = cfg["server"]["port"]
    print(f"\ndashboard: http://{host}:{port}")
    uvicorn.run(app, host=host, port=port, log_level="warning")


def cmd_publish(args):
    import pathlib

    from .publish import build_site, export_snapshots, import_history

    cfg = load_config()
    root = pathlib.Path(__file__).resolve().parent.parent
    snaps_dir = pathlib.Path(cfg.get("snapshots_dir", "snapshots"))
    site_dir = pathlib.Path(cfg.get("site_dir", "site"))
    if not snaps_dir.is_absolute():
        snaps_dir = root / snaps_dir
    if not site_dir.is_absolute():
        site_dir = root / site_dir
    db_path = pathlib.Path(cfg["db_path"])
    if not db_path.is_absolute():
        db_path = root / db_path
    db_path = db_path.with_name("publish.db")
    db_path.unlink(missing_ok=True)
    store = Store(str(db_path))
    fetcher = Fetcher(cfg)
    engine = Engine(cfg, store, fetcher)
    imported = import_history(store, snaps_dir)
    results, errors, entities = engine.cycle(force=True)
    fatal = [
        name for name in errors
        if cfg.get("sources", {}).get(name, {}).get("required", False)
        and not store.snapshots_for(name, 1)
    ]
    if fatal:
        for name in fatal:
            print(f"  REQUIRED SOURCE UNAVAILABLE: {name}")
        raise SystemExit(1)
    written = export_snapshots(store, snaps_dir)
    payload = build_site(engine, site_dir)
    print(f"imported {imported} snapshots, sources ok={len(results)} failed={len(errors)}")
    for name, err in errors.items():
        print(f"  FAILED {name}: {err}")
    print(f"exported {written} new snapshot files, entities={len(entities)}")
    recs = payload.get("recommendations", {})
    print(f"site: {len(payload['meta'])} meta / {len(payload['coding'])} coding / {len(payload['est'])} est / {len(payload['models'])} models")
    for role, result in recs.items():
        pick = result.get("recommended") or {}
        print(f"  {role}: {pick.get('name', 'no recommendation')}")
    print(f"written to {site_dir}")


def cmd_summary(args):
    cfg, store, fetcher, engine = _build()
    entities = store.latest_scores()
    if not entities:
        print("no scores computed yet - run 'python -m model_tracker.cli run-once'")
        return
    print_summary([dict(e) for e in entities])


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    p = argparse.ArgumentParser(prog="tracker")
    sub = p.add_subparsers(dest="cmd", required=True)
    sp = sub.add_parser("run-once", help="scrape all sources once and compute scores")
    sp.add_argument("--force", action="store_true", help="bypass http cache")
    sp.set_defaults(func=cmd_run_once)
    sp = sub.add_parser("scrape", help="scrape a single source")
    sp.add_argument("source")
    sp.add_argument("--limit", type=int, default=25)
    sp.add_argument("--verbose", action="store_true")
    sp.set_defaults(func=cmd_scrape)
    sp = sub.add_parser("serve", help="start scheduler + web dashboard")
    sp.set_defaults(func=cmd_serve)
    sp = sub.add_parser("publish", help="scrape + export snapshots + build static site (for GitHub Actions)")
    sp.set_defaults(func=cmd_publish)
    sp = sub.add_parser("summary", help="print latest scores from db")
    sp.set_defaults(func=cmd_summary)
    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    sys.exit(main())
