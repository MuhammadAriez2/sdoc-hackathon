#!/usr/bin/env python3
"""
Entry point. Reads the inbox, runs the pipeline, writes submission.json.

    python score_baseline.py                 # process everything
    python score_baseline.py --score         # ...then score it
    python score_baseline.py --email 004     # debug one email, verbosely

The --score flag is the important one. Run it after every change. You have an
objective number available in two seconds; teams that check once a day tune
blind.
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from baseline.pipeline import run_all, process
from baseline.contracts import COMPARE_FIELDS

try:
    from loader import Inbox                  # organizers' loader, unmodified
except ModuleNotFoundError:                   # pragma: no cover - environment guard
    sys.exit(
        'loader.py is missing.\n\n'
        'It is the organizers\' inbox loader and is deliberately not redistributed in\n'
        'this repository, along with inbox/, attachments/, tools/ and secrets/.\n'
        'Copy loader.py and the data folders from the participant bundle into this\n'
        'directory to run the deterministic baseline.\n\n'
        'The QuayProof application in quayproof/ does not need any of this and runs\n'
        'standalone: see README section 1.'
    )

ROOT = Path(__file__).parent
GROUND_TRUTH = ROOT / "secrets" / "ground_truth.json"
SCORER = ROOT / "tools" / "score_cli.py"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", default=str(ROOT),
                    help="data folder, or an http:// URL for the docker server")
    ap.add_argument("--out", default=str(ROOT / "submission.json"))
    ap.add_argument("--score", action="store_true", help="score after running")
    ap.add_argument("--email", help="debug a single email, e.g. 004")
    args = ap.parse_args()

    inbox = Inbox(args.source)

    # ---- single-email debug mode ------------------------------------------
    if args.email:
        eid = args.email if args.email.startswith("email_") else f"email_{args.email}"
        email = inbox.get(eid)
        print(f"\n{eid}")
        print(f"  from    : {email['from']}")
        print(f"  subject : {email['subject']}")
        print(f"  attach  : {email['attachments']}")
        res = process(email, root=args.source)
        print(f"\n  category      : {res.category}  (by {res.decided_by})")
        print(f"  status        : {res.status}")
        print(f"  review_reason : {res.review_reason}")
        print(f"  defect_fields : {res.defect_fields}")
        if res.notes:
            print(f"  notes         : {res.notes}")
        if res.evidence:
            print("\n  field                SI                        BL")
            print("  " + "-" * 68)
            for f in COMPARE_FIELDS:
                ev = res.evidence.get(f)
                if not ev:
                    continue
                mark = {"match": "  ", "differs": "<<", "unknown": "??"}.get(ev["result"], "  ")
                print(f"  {f:<20} {str(ev.get('si'))[:24]:<25} {str(ev.get('bl'))[:24]:<25} {mark}")
            if "_why" in res.evidence:
                print(f"\n  why: {res.evidence['_why']}")
        return

    # ---- full run ---------------------------------------------------------
    emails = inbox.emails()
    print(f"processing {len(emails)} emails ...")
    results = run_all(emails, root=args.source)

    submission = {eid: r.to_submission() for eid, r in results.items()}
    Path(args.out).write_text(json.dumps(submission, indent=2))
    print(f"wrote {args.out}  ({len(submission)} entries)")

    # A quick shape check. The evaluator needs every id present; a short file
    # silently scores zero on the ones you left out.
    n_cat = {}
    n_status = {}
    for r in results.values():
        n_cat[r.category] = n_cat.get(r.category, 0) + 1
        n_status[r.status] = n_status.get(r.status, 0) + 1
    print("  categories:", dict(sorted(n_cat.items())))
    print("  statuses  :", dict(sorted(n_status.items())))

    if args.score:
        if not GROUND_TRUTH.exists():
            print(f"\n(no {GROUND_TRUTH} - put the organizers' file there to self-score)")
            return
        print()
        subprocess.run([sys.executable, str(SCORER), args.out,
                        "--ground-truth", str(GROUND_TRUTH)])


if __name__ == "__main__":
    main()
