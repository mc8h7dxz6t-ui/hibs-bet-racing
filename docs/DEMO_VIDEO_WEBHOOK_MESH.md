# Webhook Mesh — 6-Minute Demo Video (record yourself)

**Purpose:** Plain screen-recording for DMs, Loom, or unlisted YouTube — **real terminal, no AI avatar.**  
**Product:** Webhook Mesh (#5) — never double-process a billing webhook.  
**Length:** ~5–7 minutes · **Audience:** SaaS billing, fintech, platform eng (non-technical voiceover OK)

---

## Before you record

| Step | Action |
|------|--------|
| 1 | Quiet room · mic check · terminal font **16pt+** · dark theme OK |
| 2 | `cd` to repo root (folder with `pyproject.toml`) |
| 3 | `python3.12 -m venv .venv && source .venv/bin/activate` |
| 4 | `pip install -e ".[dev,instpp]"` |
| 5 | Close notifications · browser zoom 125% if you show a slide |
| 6 | Tool: **QuickTime** (Mac) · **OBS** · or **Loom** (easiest upload) |

**Optional guided run (pauses for narration):**

```bash
./scripts/record_webhook_mesh_demo_video.sh
```

**Or run demo only:**

```bash
export WEBHOOK_PROVIDER_SECRET=demo-secret
./scripts/demo_webhook_mesh.sh
```

---

## On-screen title card (5 seconds — optional)

**Text slide or terminal banner:**

```
Webhook Mesh
Never charge twice for one webhook.
Prove it offline.
```

---

## Word-for-word script (~6 minutes)

Read this while recording. **[ACTION]** = do on screen. Pause where noted.

---

### 0:00 — Hook (15 sec)

**[SAY]**

> “If Stripe or Shopify sends the same billing event twice — which happens all the time when you scale servers — do you charge the customer once or twice?  
> I’m going to show you a small piece of infrastructure that **dedupes**, **records safely before it says OK**, and leaves **proof an auditor can check without logging into our dashboard**.  
> This runs in **your cloud** — not our SaaS.”

---

### 0:15 — Problem in plain English (30 sec)

**[SAY]**

> “Most teams use custom middleware or ‘trust Stripe idempotency.’ That doesn’t help when **two pods** see the same event, or when finance asks **six months later**: prove what your gateway did on the 14th.  
> Webhook Mesh is **ingress guardrails plus a tamper-evident log** — same audit spine we use for outbound API control and compliance decisions.”

**[ACTION]** — Open terminal at repo root. Optional: show this file on a second monitor.

---

### 0:45 — Start demo (20 sec)

**[SAY]**

> “Everything you’ll see is real — open source commands, no mock UI.”

**[ACTION]**

```bash
cd /path/to/hibs-bet-racing
source .venv/bin/activate
export WEBHOOK_PROVIDER_SECRET=demo-secret
```

---

### 1:05 — Guided recording OR full demo (2 min)

**[SAY]** (if using guided script)

> “I’ll run our recording helper — it pauses so I can explain each step.”

**[ACTION]**

```bash
./scripts/record_webhook_mesh_demo_video.sh
```

**[SAY]** at each pause in the helper (or narrate over `./scripts/demo_webhook_mesh.sh`):

| Step | Say |
|------|-----|
| Server starts | “Gateway is up — every event will go through signature check and idempotency.” |
| First Stripe event | “Valid Stripe signature — event accepted, written safely, then we return 200.” |
| **Duplicate same ID** | “Same event ID again — **second request rejected**. That’s the double-charge prevented.” |
| Bad signature | “Wrong signature — **401, fail closed**. We don’t process forgeries.” |
| check / export / verify | “Now the institutional part: export a bundle and **verify offline** — no live database, no vendor callback.” |

---

### 3:30 — Payoff: verify-bundle (60 sec)

**[SAY]**

> “This is what matters for procurement and compliance: an outsider can take this tarball and replay the proof.”

**[ACTION]** — Highlight terminal output from:

```bash
webhook-mesh verify-bundle --tarball ./data/demo/webhook_mesh_bundle.tar
```

Look for **repro_check: true** or **PASS** in output.

**[SAY]**

> “Identical ledger, identical hash — that’s reproducibility. Not ‘trust our admin panel.’”

---

### 4:30 — Who this is for (45 sec)

**[SAY]**

> “If you’re **SaaS billing**, **fintech ingress**, or **platform** running Stripe or Shopify webhooks at scale — this is for you.  
> It’s **not** Kafka, not a dashboard, not consumer anything.  
> Same family as our **outbound API guard** and **decision audit** — we can bundle those if regulated teams need **in, decide, out** proof.”

---

### 5:15 — Pilot CTA (30 sec)

**[SAY]**

> “We do **four-week pilots in your VPC** — shadow first if you want — from **two and a half thousand pounds**.  
> Fifteen minutes live if you want to stress-test it on your stack.  
> Link in the description — or DM me.  
> Thanks for watching.”

---

### 5:45 — End card (10 sec)

**[ON SCREEN]**

```
VPC pilot available.
DM / email: [your contact]
Prove it happened — before the dispute.
```

---

## YouTube / Loom description (paste)

```
Webhook Mesh — stop double-processing billing webhooks (Stripe / Shopify style).

What you'll see:
• Signed ingress (HMAC fail-closed)
• Duplicate event rejected (idempotency)
• Safe write before HTTP 200
• Offline verify-bundle (auditor replay without our dashboard)

For: SaaS billing, fintech, platform engineering.
Deploy: your VPC — not multi-tenant SaaS.
Pilot: 4 weeks (shadow available).

Contact: [your email / LinkedIn]

Not a full event bus (Kafka). Infrastructure proof only.
```

---

## Title options

1. **Stop double-charging Stripe webhooks (live demo + offline proof)**  
2. **Never process the same billing webhook twice — 6 min demo**  
3. **Webhook idempotency + audit proof (VPC deploy)**

---

## Tags (YouTube)

`webhook` `stripe` `idempotency` `fintech` `saas` `billing` `audit` `compliance` `devops` `platform engineering`

---

## Thumbnail text (Canva — 3 words max)

- **NO DOUBLE CHARGE**  
- **PROVE WEBHOOKS**  
- **BILLING SAFE**

---

## After publishing

| Use | How |
|-----|-----|
| **DM follow-up** | “Easier than a call — 6 min proof: [link]” |
| **LinkedIn** | Post hook + link — don’t rely on YouTube algorithm |
| **Second video** | Proxy-Risk shadow kill (same format) when ready |

---

## Troubleshooting on record day

| Issue | Fix |
|-------|-----|
| Port in use | `pkill -f "webhook_mesh.cli serve"` or change port in script |
| curl fails | Server not up — wait 3s after serve |
| verify-bundle fails | Re-run export; ensure `data/demo/` writable |
| Mac too many files | `ulimit -n 4096` · use Python 3.12 |

---

## Related

- `docs/WEBHOOK_MESH_BUYER.md`  
- `docs/WEBHOOK_MESH_SALES_TECH_SPEC.md`  
- `scripts/demo_webhook_mesh.sh`
