#!/usr/bin/env python3
import requests, json, sys, os

APP_ID     = "6a2804c8d24265c798c6fa23"
INGEST_KEY = os.environ.get("fywwaj-bipxob-7kyxDy")
ENDPOINT   = f"https://{APP_ID}.base44.app/functions/ingestRunnerScores"

def push(scores):
    payload = {"api_key": INGEST_KEY, "scores": scores}
    r = requests.post(ENDPOINT, json=payload, timeout=30)
    r.raise_for_status()
    result = r.json()
    print(f"✅ Inserted/updated: {result.get('inserted')}  Errors: {result.get('errors')}")
    return result

if __name__ == "__main__":
    if not INGEST_KEY:
        print("ERROR: export INGEST_API_KEY=fywwaj-bipxob-7kyxDy")
        sys.exit(1)
    if len(sys.argv) > 1:
        with open(sys.argv[1]) as f:
            scores = json.load(f)
    else:
        scores = json.load(sys.stdin)
    if isinstance(scores, dict):
        scores = scores.get("scores", scores)
    print(f"Pushing {len(scores)} runner scores...")
    push(scores)
