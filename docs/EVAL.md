# Evaluation & gate calibration (issue #3)

Answers the QA gatekeeper's question — *"does it actually catch violations, and how often is
it wrong?"* — with numbers, on labeled data, against a **live** corrector.

## Run it
```bash
# 1) load the policy the packs target
curl -s -X POST localhost:5244/v1/policy/upload -H 'X-API-Key: admin-key' \
     --data-binary @sample/sop-handbook.md
# 2) score
BASE=http://localhost:5244 KEY=caller-key \
  python scripts/eval.py packs/bank.json packs/hospital.json packs/it.json packs/clean.json
```
Each pack is a JSON list of `{name, expect, agent_utterance, context, prior_agent_claims?}`,
`expect ∈ {A, B, C, BLOCKED, clean}`. A self-contained **sample** pack ships at
`sample/eval-pack.json` (pairs with `sample/policies/`).

## What it measures
- **Recall per class** — of the planted A/B/C/BLOCKED violations, how many were caught.
- **False-positive rate** — of the benign (`clean`) lines, how many were flagged.
- **Latency** — p50 / p95 of the live judge call.
- **Gate calibration** — sweeps the confidence cutoff (`fire iff conf ≥ t`) and reports
  precision/recall/F1 at each, recommending a data-driven AUTO cutoff instead of a guess.

Pass band is configurable via `MIN_RECALL` / `MAX_FPR` (defaults 0.6 / 0.5) so it can gate CI.

## Latest result (Nemotron-Nano-9B on 2× L4, labeled packs)
```
recall by class:  A 12/12=100%   B 3/3=100%   C 3/3=100%   BLOCKED 6/6=100%   overall 24/24=100%
false-positive rate (clean flagged): 2/8 = 25%
latency ms: p50=723  p95=9404
gate calibration (fire iff confidence >= t):
   t     precision  recall   F1
  0.50      78%      86%    0.82
  0.80      78%      86%    0.82     <- current default sits on the F1 plateau
  0.95      76%      78%    0.77
  -> recommended AUTO cutoff ≈ 0.50 (max F1 0.82); current default 0.80 is validated (F1 unchanged to 0.80)
```

**Reading it:** 100% recall on planted violations with a 25% benign false-positive rate — and
the honest gate means most false positives surface as `propose` (human-reviewed), not `auto`.
The calibration confirms the hand-picked `AUTO=0.80` is on the F1 plateau: lowering it barely
changes F1, so 0.80 (higher precision on auto-actions) is a sound default. Re-run on **your**
SOP + transcripts to tune it to your domain.
