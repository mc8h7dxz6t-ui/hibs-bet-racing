# Compliance & evidence — hibs-bet-racing

**This folder documents what exists in `mc8h7dxz6t-ui/hibs-bet-racing` only.**

## Repo visibility (read this first)

| Artifact from other thread | In this repo? |
|----------------------------|---------------|
| `docs/compliance/phase-d-regulatory-max.md` | **No** |
| `docs/compliance/phase-d-forensic-closure.md` | **No** |
| PR #91 (ClaimGate, partition shadow, examiner packs) | **No** |
| Four governors **IG / FG / MG / CG** as runnable products | **No** (names appear in sales bundles or external decks only) |
| `scripts/*_examiner_evidence_pack.py` | **No** |
| `claim_events.py`, `CHAIN_PARTITION_MODE` | **No** |
| `maturity-ladder.md` (IL 9/10 per governor) | **No** |

**GitHub org repos visible to this agent:**

| Repo | Status |
|------|--------|
| `hibs-bet-racing` | **This workspace** |
| `hibs-betting-app` | Empty |
| `hibs-quantitative-labs.github.io` | Pages exercise |

The **full football app** (`hibs-bet` at `/opt/hibs-bet`) and **FVE** (`football-app`) are **not cloned here** — only `deploy/football-inst-overlay/`.

If Phase D items 1–17 were implemented elsewhere, that work is **not auditable from this tree**. Add that repo to the workspace or paste the PR diff for a real 1–17 pass.

---

## What “governors” mean in *this* repo

| Name in external deck | In this git tree |
|-----------------------|------------------|
| **Insurance Governor (IG)** | Sales bundle label (`PORTFOLIO_FULL_TECH_SALES_12.md`) — not a service |
| **Finance Governor (FG)** | Sales bundle label — not a service |
| **Model Governor (MG)** | **Real:** `src/model_governor/` CLI SKU #8 (lifecycle ledger on `inst_spine`) |
| **Cyber Governor (CG)** | **Does not exist** — closest: Webhook Mesh (#5) |
| **ClaimGate** | **Does not exist** |
| Football `:8000` | Overlay + external `hibs-bet` |
| Racing `:5003` | `src/hibs_racing/` |
| FVE `:8010` | External `football-app` |

See [../FORENSIC_ARCHITECTURE_TRUTH.md](../FORENSIC_ARCHITECTURE_TRUTH.md).

---

## Two tracks (this repo only)

| Track | Measures | Doc |
|-------|----------|-----|
| **Engineering** | CI, gates F1–F9 / R1–R8, cron, systemd | `deploy/football-inst-overlay/docs/INSTITUTIONAL_FAILSAFE.md` |
| **Evidence** | Forward CLV, paper ledger, truth plane | `FORENSIC_ARCHITECTURE_TRUTH.md`, `phase-d-sports-evidence.md` |

There is **no** R0–R5 regulatory matrix for NAIC/SOC2/EU AI Act in this repo — that belongs to a different product line if it exists at all.

---

## Files in this folder

| File | Purpose |
|------|---------|
| [phase-d-sports-evidence.md](phase-d-sports-evidence.md) | Checklist: what we can automate vs what needs matchdays/certs |
| [claims-today-vs-blocked.md](claims-today-vs-blocked.md) | Defensible claims vs misrepresentation |

---

## Verify commands (this repo)

```bash
# Football overlay gates
cd deploy/football-inst-overlay && bash scripts/verify_football_evidence_gates.sh

# Racing gates (local)
bash scripts/verify_racing_evidence_gates.sh  # if present at repo root

# Honesty / stack truth
PYTHONPATH=deploy/football-inst-overlay/src python3 -c \
  "from hibs_predictor.stack_truth import stack_truth_summary; import json; print(json.dumps(stack_truth_summary(), indent=2))"

# Inst++ rigorous (12 SKUs — not four governors)
bash scripts/instpp_rigorous_test.sh
```
