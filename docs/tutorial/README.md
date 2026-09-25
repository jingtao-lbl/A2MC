# Tutorials

Self-contained HTML walkthroughs. Each one is a single file: open it by double-clicking, or send it as an email attachment. There is no build step, no server and nothing to install.

| File | Audience | Covers |
|---|---|---|
| `A2MC_Getting_Started.html` | any new A2MC user, on any onboarded model or a new one | Claude Code install and sign-in (including a remote machine), cloning A2MC and choosing between `A2MC` and `A2MC-elm`, the Python environment, opening A2MC, wiring the clone and git's own identity, building and verifying the model on this machine, **where the agent asks for each location** (model source, archived binaries, simulation output, HPC account) and which variable records it, creating a case (research plan and parameter list gates), the first round, later sessions, and **the agent's setup playbook**: which setup skill and which of its steps to follow for each kind of user |

The earlier `A2MC_EcoSIM_Lusignan.html`, written for the EcoSIM_Lusignan team who received a finished case, moved to `A2MC-master/docs/tutorial/` on 2026-09-22. The generic tutorial follows its layout and reuses its screenshots.

## Keeping the tutorial true

The tutorial describes the setup skills (`a2mc-init`, `onboard-model`, `onboard-case`, `onboard-session`, `setup-discipline`), the router `tools/check_stage_ready.py`, and the per-model build guides `models/<model>/BUILD.md`. When one of those changes the flow, the tutorial's steps 6 to 10, its "Where things go" table in step 7, and its playbook section change with it. The skills are the authority; the tutorial is their reader-facing summary.

## Images

Screenshots are **inlined as `data:` URIs**, not linked. The page's whole point is that it survives being sent as one attachment, and a relative `<img src>` breaks silently the moment it is sent on its own.

**The inlined copy is the only copy.** The five `.png` originals that used to sit beside the HTML were removed on 2026-09-25: a second copy of an image that is already in the page earns nothing and drifts from it the moment one side is edited. To change a screenshot, re-take it, downscale to at most 1500 px wide and palette-quantize to 96 colours, then re-inline. That step is not cosmetic — it took the five from about 1 MB of base64 to 371 KB, which the terminal screenshots survive with no visible loss.

## Offline behaviour

The only external resource the page loads is the Google Fonts stylesheet. Opened without a network it falls back to Georgia, the system sans and the system mono: plainer, entirely readable, and every command, link and anchor still works.

## What ships, and what does not

`docs/` is not wholesale synced: the public leg takes `docs/a2mc_reference/`, the knowledge-base directories, and — since 2026-09-24 — **this directory**. The generic tutorial is public because `create-project-agent` gates on a user having worked through it, and a skill cannot require a document its reader does not have.

It was scanned before publishing and names no private repo, branch or collaborator, so nothing in it needs stripping. A tutorial written for one team is a different matter: keep those out of this directory, or out of the INCLUDE list, because a case-specific walkthrough belongs to the group that received the case.

## Editing

Edit the `.html` directly; it is the source. Keep the page one column at every window width: a sticky contents rail made the content column narrower as the window got wider, so the contents sit inline at the top.
