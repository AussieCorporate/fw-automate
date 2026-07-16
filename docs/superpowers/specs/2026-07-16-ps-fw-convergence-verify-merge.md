# PS + Flat White convergence: verify, connect, merge, deploy

**Date:** 2026-07-16
**Status:** Approved (Victor, in conversation)
**Author:** Claude (Opus 4.8) with Victor

## Context

The Flat White control room (folding all of Victor's scattered content projects
into the FW dashboard) was **written** across 14–16 July but never **verified,
merged, or deployed**. It lives on branch `fw-control-room-assembly` in this repo:
59 commits beyond `main`, covering all 7 planned increments.

Separately, the PS Dash (Shell Bot 2, FastAPI :8080) already carries a
two-workspace shell — a top switch between **PS Dash** and **Flat White** — where
the Flat White side embeds the FW dashboard via an iframe (`FW_DASHBOARD_URL`).

Victor's ask (16 Jul): merge PS and Flat White into one dashboard, and make sure
all the scattered projects actually *function* inside the Flat White side. Plan
now; build in the background after.

**Decided architecture (Victor, 16 Jul): "one door, two rooms."** PS Dash stays
the single dashboard opened. A top switch flips between the PS side and the FW
side. Two servers under the hood, one door. Chosen over full code-fusion (weeks
of re-plumbing) and over flipping FW into the primary shell. This shape mostly
exists; the job is to verify + connect + merge, not rebuild.

## What already exists on `fw-control-room-assembly`

| Segment | Scattered project it reads | Built as |
|---|---|---|
| Big Conversation | `~/Documents/MISC/instagram-dm-screenshotter/output/` | topic bank, tier pools, paragraph pairing, drag-drop, process |
| Brains Trust | Trading Strategy `data/carousels/*/_candidates.json` (read-only) | 3-week angle pool → pick → draft → edit |
| Editorial | flat-white-intro skill | gated "big story" opener |
| Off the Clock | niche sourcing | 5 categories, swap + custom add |
| Inside Track | DM gossip/redundancy folder | tick submissions → write-up |
| Top Picks | PS click data + manually-flagged features | selectable list, mark ready |
| Assemble + Content Bank | — | assemble-edition → beehiiv HTML blocks; content bank table |

**beehiiv reality (unchanged, confirmed 16 Jul):** beehiiv REST create/post is
Enterprise-gated (403). The dashboard cannot post. Adopted pattern ("Design B"):
the dashboard *formats* the edition into beehiiv-editor HTML; the actual insert is
done by Claude via the beehiiv MCP (`duplicate_post` + `edit_post_content`) in an
agent session when Victor says "send it." beehiiv MCP connection verified live
16 Jul (all 4 publications visible, incl. Flat White + Pick & Scroll).

## Plan

### Phase 1 — Prove the FW control room works (real-data acceptance gate)
Fire up the `fw-control-room-assembly` branch locally. Walk every segment against
Victor's real data (the acceptance-gate discipline that caught the PS Dash bugs
the unit tests missed). Per segment: (a) does it read the right scattered project,
(b) does it produce something usable. Fix what's broken. Deliverable: a plain
what-works / what-was-fixed checklist for Victor.

### Phase 2 — Connect the two rooms
Point PS Dash's Flat White workspace at the control-room branch (currently shows
the pre-control-room FW dashboard). Provide a single "fire up" command that boots
both servers at once so Victor never juggles two processes.

### Phase 3 — Save it properly
After verification, merge `fw-control-room-assembly` → FW `main`; push FW to a
private GitHub backup (mirroring the Shell Bot 2 backup done 16 Jul). Stop the
work living stranded on a branch.

### Phase 4 — Deploy (Victor's call, later)
Local-first on the Mac (recommended, matches how Victor works) vs the GCP VM
`flatwhite` for always-on. Decide after Phases 1–3.

## Out of scope (for now)
- Full code-fusion of FW into Shell Bot 2 (rejected: "one door, two rooms").
- Any change to the scattered projects themselves — all integrations are read-only.
- New segments or capabilities beyond what's on the branch.

## Success criteria
Victor can open one dashboard, switch to Flat White, and produce every FW segment
from his scattered projects without hand-typing Claude CLI prompts in five
folders — then hand the assembled edition to Claude for the beehiiv insert.
