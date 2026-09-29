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

---

# Harness overview

`A2MC_Harness_Overview.html` is the same subject at concept level: **seven words**, each standing for a whole category, and how each holds the next honest. Use it to explain the harness; use the full network to work on it.

```bash
python3 tools/generate_harness_graph.py --overview
python3 tools/generate_harness_graph.py --overview --check
```

| | |
|---|---|
| **Skills** | the procedure for one kind of work. Says HOW, and names what to record |
| **Logs** | the record of what was done and why |
| **Memory** | what survives a session ending |
| **Tools** | what the work is actually done with |
| **Checkers** | the tools that assert a result rather than produce one |
| **Hooks** | the numbered checks at commit, plus those that fire while the agent works |
| **Discipline** | the outcome. Not a file: what holds when nobody is watching |

**The chain the arrows draw**, and each link is a real mechanism rather than a sentiment: a skill drives tools and requires a log; a log names the memory it wrote **and the memory names the log back**; a lesson that recurs becomes a procedure; checkers assert each of those; hooks invoke the checkers and refuse the commit. Discipline is what is left when that loop closes.

**Its labels carry live counts**, substituted from the repository at generation time — how many skills, how many numbered checks, how many of the tools are checkers, how many skills name their own. A concept diagram is the easiest thing to let drift, so nothing in it is typed by hand twice.

**Only STRUCTURAL counts, though.** The dev-log count was in there for exactly one commit and made the graph stale the moment the next log was written, firing the drift advisory on ordinary activity. A check that cries wolf is worse than no check, and it devalues the ones beside it. Counts that change when the *harness* changes belong here; counts that change when *work happens* do not.

---

# Asking the graph instead of looking at it

A picture is for a human. An agent cannot look at one, and the agent is the reader who most needs this: the failure these graphs describe is editing one instance of a contract that lives in four places, which is a thing you do at the keyboard rather than while studying a diagram. `tools/harness_query.py` answers the same questions the harness network draws, from the same derivation, as text.

```bash
python3 tools/harness_query.py --touches <path>     # what governs this file, and which skill says how
python3 tools/harness_query.py --impact <name>      # what depends on this checker, skill or artifact
python3 tools/harness_query.py --contract '<token>' # every tracked file that carries this field or rule
python3 tools/harness_query.py --audit              # the structural gaps, by name
```

`--touches` is the one that earns its place. It reports every numbered check in `.githooks/pre-commit` whose gate pattern matches the path, the skill (if any) describing each, the **reciprocal** pairs among them, and — for a `SKILL.md` — the readers a gate cannot show at all: `visibility:` is read by both sync legs, `modes.scope` by `tools/skill_models.py`, and the registry rows live in four separate files. `--contract` exists because the answer to "where else does this live?" should come from the repository rather than from recall.

It shares `generate_harness_graph.py`'s derivation rather than re-deriving anything, so the text and the picture cannot disagree.

## The audit, and why it is bound to check (27)

`--audit` reports three numbers, each a structural gap the graphs draw but do not judge:

| | meaning |
|---|---|
| artifacts no checker governs | something the agent writes that nothing asserts |
| enforcement with no procedure | a check nobody described, so you meet it by tripping it |
| skills with no hook-wired checker | a procedure with no assertion, which is a habit |

The third is not a defect on its own — most skills need no checker. The first two are.

**It is compared against a committed baseline, by NAME**, in `audit_baseline.json`:

```bash
python3 tools/harness_query.py --audit --baseline check    # report only what MOVED; exit 1 on a new gap
python3 tools/harness_query.py --audit --baseline update   # accept the current state as the baseline
```

Two decisions in that, both learned here. **By name rather than by count**, because one checker gaining a skill while another loses one leaves the count identical and the harness changed. **Only what moved**, because a standing audit that reprints the same twelve names on every commit is one nobody reads by the third — the same reason check (27) is gated on the skills, the hook and this directory's YAML rather than running always. It is wired into check (27) as ADVISORY, alongside the three staleness checks, since a gap is worth naming and is nobody's reason to be refused a commit.

## The hook that speaks first

`.claude/hooks/remind-governing-checks.py` is a `PreToolUse` hook on `Write|Edit|NotebookEdit`. Before a file is written it runs the `--touches` derivation and states what governs that path, so the chain is met while the file is open rather than at commit time when the checker refuses it.

It is information and never a block; every path exits 0, including every failure, because a reminder that breaks the tool call it precedes is worse than no reminder. It speaks **once per path per session** (deduped through the gitignored `tmp/`), and says nothing at all for a path nothing governs.
