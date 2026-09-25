# Skill graph

`A2MC_Skill_Network_Interactive.html` is a self-contained interactive view of the skill catalogue: every skill as a node, grouped by what it is for, with the routes between them as edges. It needs no server and no network, so on a cluster the usual route is to copy it down and open it locally:

```bash
scp <user>@<host>:<repo>/docs/skill_graph/A2MC_Skill_Network_Interactive.html .
```

## It is generated

```bash
python3 tools/generate_skill_graph.py            # rebuild after adding, removing or renaming a skill
python3 tools/generate_skill_graph.py --check    # exit 1 if the committed file is out of date
```

It began as a hand-built snapshot, and by the time anyone looked it was eight skills behind with no way to tell short of diffing it against the catalogue by hand. Adding a skill now puts it on the graph.

**What is derived, and what is curated.** The split is the design, not an implementation detail:

| | |
|---|---|
| **derived** from `.claude/skills/*/SKILL.md` | the node SET, and each node's group (from `category`) |
| **curated** in `graph_data.yaml` | a one-line gloss per skill, the edges with their labels, and the deliberate exclusions |

Edges cannot be derived. `a2mc-init -> onboard-model` is labelled *"new model"*, and no amount of parsing either file yields that phrase. Glosses are editorial too: shorter and plainer than the frontmatter `summary`, which is written for a different reader.

**Silence does not drop a node.** A skill with no curated gloss still appears, using its frontmatter summary, with a warning. That is the difference between a graph that goes stale and one that gets slightly scruffy — the failure to prevent is a missing skill, not an unpolished sentence.

The generator also reports, every run: exclusions applied and why, glosses and exclusions naming skills that no longer exist, edges dropped because an endpoint is gone, and **isolated nodes** that no edge reaches.

## What it holds now

**53 nodes** of the 54 skills on disk, **114 edges**, and no isolated nodes.

**Derive an edge from the citation, in whichever direction it exists.** Two nodes were briefly isolated here because the edges were curated by reading each skill for the routes it declares OUTWARD. `build-surrogate` declares none — but `phase1-exploration`, `phase0-design` and `plotting` all cite it, and `literature-review` cites `manuscript-writing-style`. Looking only outward makes a well-connected skill look orphaned. The generator's ISOLATED warning is the backstop, and it is worth acting on by grepping the catalogue for the node's own name before concluding that no route exists.

## Deliberate exclusions

`cherrypick-from-main` is kept off (PI, 2026-09-25): it is repository plumbing rather than an A2MC capability, moving commits between branches of the private development repo. Verified rather than assumed — no edge in the curated set referenced it, so removing it orphaned nothing.

Exclusions live in `graph_data.yaml` with a reason each, and the generator prints every one it applies, so this is a visible decision rather than a silent filter.

## Where it ships

**The public leg carries `docs/skill_graph/`** (PI, 2026-09-25). `docs/` is not wholesale-included by either leg, only its named subdirectories, so this one is listed explicitly.

The graph shows **the catalogue, not the shippable subset**: it carries every skill on disk minus the declared exclusions, and that includes the ones marked `visibility: private`, which a public reader does not have. That is deliberate. A reader who wants a map of the skills *they* have runs `tools/generate_skill_graph.py`, which ships too and derives its node set from their own `.claude/skills/`.

Another leg carries it only if its own `INCLUDE_FILES` lists this directory, which is one line to add.

---

# Harness network

`A2MC_Harness_Network.html` is the second graph, and it answers a different question: **what holds the discipline?** Not which skill routes to which, but which checker asserts a skill's result and which hook refuses the commit when the assertion fails.

```bash
python3 tools/generate_harness_graph.py            # rebuild
python3 tools/generate_harness_graph.py --check    # exit 1 if the committed file is stale
```

**74 nodes, 114 edges**, in six kinds:

| kind | count | what it is |
|---|---|---|
| ARTIFACTS | 12 | what the agent writes: a dev log, a phase log, a memory, a skill, a report, a case's round state |
| SKILLS | 25 | the procedure for producing one of them |
| CHECKERS | 24 | a `tools/check_*.py` that asserts the result |
| RECIPROCAL | 3 | checkers that verify one link from **both** ends |
| GIT HOOK | 1 | `pre-commit`, 28 numbered checks, refuses the commit |
| AGENT HOOKS | 9 | fire while the agent works, not at commit |

**The chain it draws is: skill → checker → hook.** A skill says how a thing is done, a checker asserts the result, a hook refuses the commit when the assertion fails. 25 of the skills name their own enforcing checker, and that edge is read out of the `SKILL.md`, not assigned here.

**The RECIPROCAL group is the point of the picture.** `check_log_conformance` requires a log to name the memory it wrote; `check_memory_bucket` requires that memory to name the log back. Neither half alone catches a pointer that resolves to a real file containing none of the claimed content — only the pair does. `check_skill_claims` is the third: a log claiming it followed a skill is checked against the session transcript.

**Derived, so it cannot go stale.** The checker nodes and the hook edges come from the numbered checks in `.githooks/commit`; the artifact each checker governs comes from the path pattern that gates it; the skill edges from each `SKILL.md`. Curated in `harness_data.yaml`: what a gate pattern *means*, the glosses, and the reciprocal pairs — none of which a parse yields.

**An unmapped gate is reported, never dropped.** A checker whose subject nobody has named is exactly what this graph exists to surface, so the generator warns rather than omitting the node.
