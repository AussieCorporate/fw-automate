# Make the dashboard run skills itself (headless Claude), no manual session

**Date:** 2026-07-17
**Status:** Draft for Victor's review
**Repo:** FW (Flat White control room)

## Problem

Segments whose work is done by a Claude *skill* (not a plain LLM call) currently
hand Victor off: the dashboard shows an instruction ("Run the big-conversation
skill in a Claude session, then come back and click Refresh"). That defeats the
control-room purpose - Victor wanted to stop running Claude CLIs by hand.

Root cause: the skill reads Instagram screenshots as **images** (vision), drafts
against past editions, and maps screenshots to paragraphs. FW's dashboard is a
plain FastAPI server with no vision and no Claude inside it, so at build time the
only option was a handoff.

**What changed:** Claude Code (the `claude` CLI, v2.1.212) is installed on this
Mac at `~/.local/bin/claude` and has a non-interactive mode (`claude -p`). The
dashboard can therefore launch the *real* skill headless and read back its
output - no porting, no vision wiring in FW, no quality drift.

## Scope (Victor: "all skill-handoff segments")

Skill-handoffs that exist today:
1. **Big Conversation** - runs `big-conversation` skill on a topic folder. IN.
2. **Screenshot-sort** - the `screenshot-sort` skill that must run BEFORE Big
   Conversation (sorts the DM screenshots into tiers/paragraph pools). Currently
   assumed already done by hand. IN (so the whole chain is one-click).

3. **Beehiiv insertion** - IN (feasibility CONFIRMED 17 Jul). Not a file skill
   but a beehiiv-MCP action. Concern was that claude.ai MCP integrations may be
   absent in headless runs; tested and they are NOT: `claude -p "list my beehiiv
   publications"` returned all 4 pubs headless. So the same runner can drive the
   beehiiv MCP to insert an assembled edition into the target draft
   (duplicate-latest / get_post_content + edit_post_content), replacing the
   manual "open the beehiiv MCP in a Claude session" Design-B step.

The sort skill (2) unblocks BOTH Big Conversation AND Inside Track (the dash
shows "Run the sort skill first" on Inside Track too), so integrating it is
double value.

### Deployment caveat
The headless runner only works where the `claude` CLI is installed AND logged in
- true on Victor's Mac (where he runs FW), NOT on the GCP VM prod. This feature
is local-first. If FW ever moves to the VM, Claude Code must be installed+authed
there for these buttons to work; otherwise they should degrade to the old
handoff instruction rather than error.

## Design: a shared headless-skill runner

**One reusable mechanism**, used by every skill-handoff.

`flatwhite/dashboard/skill_runner.py`
- `start_run(kind, prompt, cwd, add_dirs) -> run_id`: spawns
  `claude -p "<prompt>" --permission-mode acceptEdits --add-dir <dirs>` via
  `subprocess.Popen` in `cwd` (the Instagram DM screenshotter project so the
  skill + folders resolve). Runs in a background thread; captures stdout/stderr
  and exit code.
- An in-memory run registry keyed by `run_id`: status = queued | running | done
  | failed, plus start/end time, tail of output, and error on failure.
- One active run at a time per topic (guard against double-clicks). A global cap
  (e.g. 1-2 concurrent) so a click storm can't spawn many agents.
- Everything fails LOUD and CLEAN: a non-zero exit or a timeout marks the run
  failed with the captured stderr; the UI shows a plain-English error, never a
  hung spinner.

Endpoints (thin wrappers over the runner):
- `POST /api/skill-run/big-conversation/{topic}` -> starts the skill on that
  topic; returns `run_id`.
- `POST /api/skill-run/sort` -> starts the screenshot-sort skill on the campaign.
- `GET /api/skill-run/{run_id}` -> status + output tail (frontend polls this).

Frontend:
- The Big Conversation "Process" button now calls the run endpoint and shows a
  live "Working... (this takes a few minutes)" state, polling status. On `done`
  it auto-loads the written piece + screenshots (the existing
  `GET /api/big-conversation/topic/{topic}` already reads them back). On `failed`
  it shows the error and a Retry.
- A "Sort submissions" action for the sort skill, same pattern.

## The tradeoffs Victor must sign off on

1. **It takes a few minutes per run.** A full agent reading dozens of screenshots
   and drafting is not instant. It runs in the background; the dash stays usable.
2. **Each run costs tokens** - a full agent run with vision over many images. It
   only runs when Victor clicks, so cost is bounded by use, but it is not free.
3. **Permissions/security.** Headless Claude needs to write the output file and
   copy screenshots. Plan: `--permission-mode acceptEdits` + `--add-dir` scoped
   to the Instagram output folder, NOT `--dangerously-skip-permissions`. If the
   skill's file-copy step needs bash and acceptEdits is not enough, we escalate
   deliberately and document it - we do not silently skip all permission checks.
4. **Auth.** Uses this Mac's existing Claude login (same as this session). If the
   login expires, a run fails with a clear "Claude not logged in" message.
5. **It is the real skill.** Output matches running it by hand; if the skill
   changes, the dashboard picks it up automatically (no drift).

## Build order (each verified before the next)

1. `skill_runner.py` + registry + the 3 endpoints. Unit-test the registry and a
   fake/echo command (no real Claude) for status transitions + failure capture.
2. Wire Big Conversation "Process" to it; verify LIVE on a real topic folder
   ("Lunch w your team or not") end-to-end: click Process -> real skill runs ->
   piece + screenshots appear. This is the acceptance gate.
3. Wire the screenshot-sort action; verify LIVE.
4. Harden: concurrency cap, timeout, auth-failure and permission-failure
   messages, double-click guard.

5. Wire beehiiv insertion: the assemble screen's 'send to beehiiv' runs a
   headless Claude that inserts the assembled HTML into the target draft via the
   beehiiv MCP. Verify LIVE against a throwaway/test draft first.

## Out of scope
- Porting any skill's logic into FW (we run the real skill, never a copy).
- Changing the skills themselves.
- Cloud (GCP VM) deployment of this feature (local-first; see caveat above).

## Success criteria
Victor clicks Process/Sort/Send-to-beehiiv in the FW dashboard, waits, and the
work happens - the Big Conversation piece + screenshots appear, submissions get
sorted, or the edition lands in the beehiiv draft - all without opening a
separate Claude session. Failures are explained in plain English and, where
possible, fall back to the old handoff instruction rather than a dead end.
