#!/usr/bin/env python3
"""
HIBS Mac-side push script
Usage: python3 push_scores.py scores.json
"""
import requests
import json
import sys
import os

# ── Config ────────────────────────────────────────────────────────────
APP_ID      = "6a2804c8d24265c798c6fa23"
INGEST_KEY  = os.environ.get("fywwaj-bipxob-7kyxDy")   # set in your shell profile
ENDPOINT    = f"https://{APP_ID}.base44.app/functions/ingestRunnerScores"

