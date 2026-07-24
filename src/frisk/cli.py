"""frisk console entry point.

    frisk generate            # regenerate the deterministic synthetic dossiers
    frisk samples             # write the 40-profile manual-upload sample set
    frisk migrate             # create/upgrade the relational DB (customers/assessments/lessons/cases)
    frisk serve [--port]      # run the backend API + frontend (uvicorn)
    frisk score [--offline]   # score all customers and print the ranked queue (--offline = mock provider)
    frisk warm                # score all customers, populating the store/case-bank
    frisk reflect             # distill "lessons learned" from human corrections
"""
from __future__ import annotations

import argparse
import os


def main(argv=None) -> None:
    p = argparse.ArgumentParser(prog="frisk", description="Financial Risk Signal Aggregator")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("generate", help="regenerate the synthetic dossiers (the app's data/customers/)")
    sub.add_parser("samples", help="write the 40-profile MANUAL-upload sample set (separate folder)")
    sub.add_parser("migrate", help="create/upgrade the relational DB tables")
    sub.add_parser("reflect", help="distill lessons-learned from human corrections")
    srv = sub.add_parser("serve", help="run the backend API + frontend (uvicorn)")
    srv.add_argument("--port", type=int, default=8000)
    sc = sub.add_parser("score", help="score all customers and print the ranked queue")
    sc.add_argument("--offline", action="store_true", help="use the deterministic mock provider (no API)")
    sub.add_parser("warm", help="score all customers, populating the store + case-bank")
    args = p.parse_args(argv)

    if args.cmd == "generate":
        from frisk.data.generate import _selfcheck, write
        write(); _selfcheck()
        return

    if args.cmd == "samples":
        from frisk.data.generate import write_samples
        from frisk.paths import UPLOAD_SAMPLES
        n, files, review_ids = write_samples()
        print(f"wrote {n} sample profiles ({files} files) to:\n  {UPLOAD_SAMPLES}")
        print(f"  {len(review_ids)} designed to NEED human review: {review_ids}")
        return

    if args.cmd == "migrate":
        from frisk.data import casebank, store
        store.migrate(); casebank.migrate()
        print("DB migrated: customers / assessments / lessons / cases")
        return

    if args.cmd == "reflect":
        from frisk.hitl.reflection import reflect
        print(f"added {reflect()} lesson(s) from recent corrections")
        return

    if args.cmd == "serve":
        import uvicorn
        print(f"frisk backend + frontend -> http://127.0.0.1:{args.port}")
        uvicorn.run("frisk.api.service:app", host="127.0.0.1", port=args.port, reload=False)
        return

    if args.cmd == "score" and args.offline:
        os.environ["FRISK_PROVIDER"] = "mock"

    from frisk.core.engine import assess_all
    from frisk.core.models import load_dossiers
    decs = assess_all(load_dossiers(), persist=(args.cmd == "warm"))

    if args.cmd == "score":
        for d in sorted(decs, key=lambda x: -x.score):
            sign = "*" if d.requires_signoff else " "
            print(f"{d.customer_id} {d.band:7s} {d.score:3d} conf={d.confidence:.2f} "
                  f"{d.action:14s}{sign} steps={len(d.trace)}")
    elif args.cmd == "warm":
        n = sum(1 for d in decs if d.engine_path == "agent")
        print(f"scored {n}/{len(decs)} customers via the agent; results in the store + case-bank")


if __name__ == "__main__":
    main()
