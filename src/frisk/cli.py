"""frisk console entry point: generate data, score the queue, warm the LLM cache.

    frisk generate            # regenerate the deterministic synthetic dossiers
    frisk score [--offline]   # score all customers and print the ranked queue
    frisk warm                # populate the LLM cache (multi-step graph) for an instant UI
"""
from __future__ import annotations

import argparse
import os


def main(argv=None) -> None:
    p = argparse.ArgumentParser(prog="frisk", description="Financial Risk Signal Aggregator")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("generate", help="regenerate the synthetic dossiers")
    sc = sub.add_parser("score", help="score all customers and print the ranked queue")
    sc.add_argument("--offline", action="store_true", help="rules-only, no LLM")
    sub.add_parser("warm", help="warm the LLM cache over all customers")
    args = p.parse_args(argv)

    if args.cmd == "generate":
        from frisk.data.generate import write, _selfcheck
        write(); _selfcheck()
        return

    if args.offline if args.cmd == "score" else False:
        os.environ["LLM_MODE"] = "off"

    from frisk.core.engine import assess_all
    from frisk.core.models import load_dossiers
    decs = assess_all(load_dossiers(), persist=False)

    if args.cmd == "score":
        for d in sorted(decs, key=lambda x: -x.score):
            sign = "*" if d.requires_signoff else " "
            print(f"{d.customer_id} {d.band:4s} {d.score:3d} conf={d.confidence:.2f} "
                  f"{d.action:10s}{sign}[{d.tier}] {d.engine_path}")
    elif args.cmd == "warm":
        n = sum(1 for d in decs if d.engine_path in ("rules+graph", "rules+llm"))
        print(f"warmed {n}/{len(decs)} customers via the LLM ({len(decs) - n} degraded/simulated)")


if __name__ == "__main__":
    main()
