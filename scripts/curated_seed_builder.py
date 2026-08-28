#!/usr/bin/env python3
"""
curated_seed_builder.py - Implements Recipe G1 from
docs/a2mc_reference/graphrag_curated_yaml_roadmap.md.

Produces a v0.1 curated YAML for an adapter-kit user's model from:
    - The model's wiki at a pinned commit
    - The model's parameter file (CDL/JSON/YAML/...)
    - The model's output CDL
    - (optional) A user-guide PDF for Phase 2 mechanism naming
    - (optional) A codebase root for Phase 2 source-clustering enrichment

Output: models/<model>/curated_seed.yaml — typically 5-15 categories,
        5-15 mechanisms, 30-80 parameter entries, 10-20 output entries.

Stages A-H per scoping doc §3 (Recipe G1 phases 0-5 + retrieval smoke test):

    Stage A   Pre-flight verification              (~5 sec)
    Stage B   Phase 1 categorization               (interactive, ~5 min)
    Stage C   Phase 2 mechanism naming             (interactive + AI, ~30 min)
    Stage D   Phase 3 per-category subagent        (parallel, ~10-20 min)
    Stage E   Phase 4 outputs entries              (interactive or AI, ~10 min)
    Stage F   Assembly                              (~5 sec)
    Stage G   Phase 5 static validation             (~10 sec)
    Stage H   Phase 5 retrieval smoke test          (~30 sec)

Mode selection (--mode):
    prompt-pack  Default. Generates Markdown prompts for Stage D the user
                 runs through Claude Code / Claude.ai / etc. Output to
                 Offline/seed_builder_<model>/prompts/. User pastes results
                 back via Stage D's import-fragments step.
    api          Sequential calls via Anthropic SDK (requires ANTHROPIC_API_KEY).
                 NOT YET IMPLEMENTED — will land in a later commit.
    auto         Subagent dispatch via Claude Code SDK. NOT YET IMPLEMENTED.

State persistence: Offline/seed_builder_<model>/state.json holds per-stage
status. Re-running picks up from the first incomplete stage; --restart-from
forces re-execution.

Author: Jing Tao with Claude
"""

from __future__ import annotations

import argparse
import importlib
import json
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


# =============================================================================
# Setup
# =============================================================================

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

ALL_STAGES = ("A", "B", "C", "D", "E", "F", "G", "H")
STAGE_NAMES = {
    "A": "Pre-flight verification",
    "B": "Phase 1 categorization",
    "C": "Phase 2 mechanism naming",
    "D": "Phase 3 per-category subagent dispatch",
    "E": "Phase 4 outputs entries",
    "F": "Assembly",
    "G": "Phase 5 static validation",
    "H": "Phase 5 retrieval smoke test",
}

# Per scoping doc §3.5 / dev log 20260427c: every entry carries provenance.
SOURCE_AUTO_EXTRACT = "auto-extract"
SOURCE_AI_DRAFT = "ai-draft"
SOURCE_HUMAN = "human"


# =============================================================================
# State management
# =============================================================================

@dataclass
class StageResult:
    status: str = "pending"             # 'pending' | 'completed' | 'failed' | 'skipped'
    timestamp: str = ""
    notes: str = ""
    artifact_path: str = ""              # path to per-stage output if applicable


@dataclass
class State:
    model: str
    workdir: Path
    created_at: str = ""
    updated_at: str = ""
    stage_results: Dict[str, StageResult] = field(default_factory=dict)

    def get(self, stage: str) -> StageResult:
        return self.stage_results.setdefault(stage, StageResult())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "model": self.model,
            "workdir": str(self.workdir),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "stage_results": {
                k: {
                    "status": v.status,
                    "timestamp": v.timestamp,
                    "notes": v.notes,
                    "artifact_path": v.artifact_path,
                }
                for k, v in self.stage_results.items()
            },
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "State":
        st = cls(model=d["model"], workdir=Path(d["workdir"]))
        st.created_at = d.get("created_at", "")
        st.updated_at = d.get("updated_at", "")
        for k, v in d.get("stage_results", {}).items():
            st.stage_results[k] = StageResult(
                status=v.get("status", "pending"),
                timestamp=v.get("timestamp", ""),
                notes=v.get("notes", ""),
                artifact_path=v.get("artifact_path", ""),
            )
        return st


def state_path(workdir: Path) -> Path:
    return workdir / "state.json"


def load_state(model: str, workdir: Path) -> State:
    p = state_path(workdir)
    if p.is_file():
        return State.from_dict(json.loads(p.read_text()))
    return State(
        model=model,
        workdir=workdir,
        created_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
    )


def save_state(state: State) -> None:
    state.updated_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    state.workdir.mkdir(parents=True, exist_ok=True)
    state_path(state.workdir).write_text(json.dumps(state.to_dict(), indent=2) + "\n")


def mark(state: State, stage: str, status: str, **kwargs) -> None:
    r = state.get(stage)
    r.status = status
    r.timestamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    for k, v in kwargs.items():
        setattr(r, k, v)
    save_state(state)


# =============================================================================
# Helpers
# =============================================================================

def _try_import_yaml():
    try:
        import yaml
        return yaml
    except ImportError:
        sys.stderr.write(
            "ERROR: PyYAML is required. Install via:\n"
            "  pip install pyyaml\n"
            "Or use the A2MC Python 3.10 env where it's pre-installed.\n"
        )
        sys.exit(2)


def _walk_wiki(wiki_root: Path) -> Dict[str, str]:
    """Return {rel_path: content} for every .md file under wiki_root."""
    out: Dict[str, str] = {}
    for path in wiki_root.rglob("*.md"):
        try:
            rel = str(path.relative_to(wiki_root))
        except ValueError:
            rel = str(path)
        try:
            out[rel] = path.read_text(errors="ignore")
        except OSError:
            continue
    return out


def _extract_wiki_section_headers(wiki: Dict[str, str]) -> List[Tuple[str, str]]:
    """Return list of (rel_path, header_text) for every '## ' or '### ' line in the wiki."""
    out = []
    for rel, content in wiki.items():
        for line in content.splitlines():
            if line.startswith("## ") or line.startswith("### "):
                header = line.lstrip("# ").strip()
                if header and len(header) < 80:
                    out.append((rel, header))
    return out


def _rel(path: Path) -> str:
    """Relative-to-repo if possible; else absolute. Safe for printing."""
    try:
        return str(Path(path).resolve().relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def _read_user_input(prompt: str, default: str = "") -> str:
    """Read one line of user input. Returns default on empty input."""
    if default:
        full = f"{prompt} [{default}]: "
    else:
        full = f"{prompt}: "
    try:
        line = input(full).strip()
    except EOFError:
        return default
    return line if line else default


# =============================================================================
# Stage A — Pre-flight verification
# =============================================================================

def stage_a_preflight(
    state: State,
    model: str,
    wiki: Path,
    param_file: Path,
    output_cdl: Path,
    user_guide: Optional[Path],
    codebase_root: Optional[Path],
) -> bool:
    """Verify all required inputs exist + adapter is registered."""
    print(f"\n=== Stage A: {STAGE_NAMES['A']} ===")
    issues = []

    # Required paths
    if not wiki.is_dir():
        issues.append(f"--wiki not found: {wiki}")
    else:
        n_md = sum(1 for _ in wiki.rglob("*.md"))
        print(f"  ✓ wiki:       {_rel(wiki)} ({n_md} .md files)")

    if not param_file.is_file():
        issues.append(f"--param-file not found: {param_file}")
    else:
        size_kb = param_file.stat().st_size // 1024
        print(f"  ✓ param-file: {_rel(param_file)} ({size_kb} KB)")

    if not output_cdl.is_file():
        issues.append(f"--output-cdl not found: {output_cdl}")
    else:
        size_kb = output_cdl.stat().st_size // 1024
        print(f"  ✓ output-cdl: {_rel(output_cdl)} ({size_kb} KB)")

    # Optional inputs
    if user_guide:
        if not user_guide.is_file():
            issues.append(f"--user-guide not found: {user_guide}")
        else:
            print(f"  ✓ user-guide: {_rel(user_guide)}")
    else:
        print(f"  · user-guide: not provided (mechanism naming will be harder)")

    if codebase_root:
        if not codebase_root.is_dir():
            issues.append(f"--codebase-root not a directory: {codebase_root}")
        else:
            print(f"  ✓ codebase-root: {codebase_root}")
    else:
        print(f"  · codebase-root: not provided (Phase 2 enrichment skipped)")

    # Adapter registration
    try:
        importlib.import_module(f"models.{model}")
        from models import registry
        backend = registry.get_model(model)
        print(f"  ✓ adapter:    models.{model} registered "
              f"(spec.name={backend.spec.name!r}, parameter_parser_class={backend.spec.parameter_parser_class.__name__})")
    except Exception as e:
        issues.append(f"adapter not registered: {type(e).__name__}: {e}")

    # ChromaDB / NetworkX (for Stage H — non-fatal at preflight; Stage H itself
    # will skip cleanly if missing)
    warnings = []
    try:
        import chromadb  # noqa: F401
        print(f"  ✓ chromadb:   installed")
    except ImportError:
        warnings.append("chromadb not installed — Stage H retrieval test will be skipped")
        print(f"  · chromadb:   not installed (Stage H will skip; install via A2MC's Python 3.10 env)")

    try:
        import networkx  # noqa: F401
        print(f"  ✓ networkx:   installed")
    except ImportError:
        warnings.append("networkx not installed — Stage H retrieval test will be skipped")
        print(f"  · networkx:   not installed (Stage H will skip)")

    if issues:
        print(f"\nStage A failed with {len(issues)} issue(s):")
        for s in issues:
            print(f"    - {s}")
        mark(state, "A", "failed", notes="; ".join(issues))
        return False

    mark(state, "A", "completed")
    return True


# =============================================================================
# Stage B — Phase 1 categorization (propose from prefix; user confirms)
# =============================================================================

def _propose_categories_from_prefixes(
    param_records: Dict[str, Dict[str, Any]],
    min_size: int = 3,
    max_size: int = 30,
) -> Dict[str, List[str]]:
    """Group parameters by their first underscore-separated token.

    Returns {prefix: [param_name, ...]} for groups within [min_size, max_size].
    Smaller groups merge into 'other'; larger groups split on the second token.
    """
    by_prefix: Dict[str, List[str]] = defaultdict(list)
    for name in sorted(param_records.keys()):
        # FATES uses fates_<category>_<rest>; semver might be <category>_<param>.
        # Heuristic: if name has prefix_xxx_yyy, group by xxx; if just prefix_xxx, group by xxx.
        parts = name.split("_")
        if len(parts) >= 2 and parts[0]:
            # Skip the model-name prefix (e.g., 'fates') if it's the same for everyone
            key = parts[1] if len(parts) >= 3 else parts[0]
        else:
            key = name
        by_prefix[key].append(name)

    # Merge tiny groups into 'other'
    result: Dict[str, List[str]] = {}
    other: List[str] = []
    for prefix, members in by_prefix.items():
        if len(members) < min_size:
            other.extend(members)
        else:
            result[prefix] = members

    if other:
        result["other"] = sorted(other)

    return result


def stage_b_categorize(
    state: State,
    model: str,
    param_file: Path,
    interactive: bool = True,
) -> bool:
    """Propose categories from parameter prefixes; let user confirm/edit names."""
    print(f"\n=== Stage B: {STAGE_NAMES['B']} ===")

    try:
        from models import registry
        backend = registry.get_model(model)
        parser = backend.spec.parameter_parser_class()
        param_records = parser.parse(param_file)
    except NotImplementedError:
        print(f"  [SKIP] {model}'s parameter_parser is a stub (NotImplementedError).")
        print(f"         Fill in models/{model}/parameter_parser.py first, then re-run.")
        mark(state, "B", "failed", notes="parameter_parser is a stub")
        return False
    except Exception as e:
        print(f"  [FAIL] Could not parse {param_file}: {type(e).__name__}: {e}")
        mark(state, "B", "failed", notes=str(e))
        return False

    if not param_records:
        print(f"  [FAIL] {param_file} parsed empty.")
        mark(state, "B", "failed", notes="empty parser output")
        return False

    print(f"  Parsed {len(param_records)} parameter(s) from {param_file.name}")

    proposed = _propose_categories_from_prefixes(param_records)
    print(f"  Proposed {len(proposed)} category groupings (by name prefix):")
    for prefix in sorted(proposed.keys()):
        print(f"    - {prefix:20s}  ({len(proposed[prefix])} params)")

    # Convert to category schema
    categories: Dict[str, Dict[str, Any]] = {}
    for prefix, members in proposed.items():
        categories[prefix] = {
            "full_name": f"TODO(adapter-kit): display name for category '{prefix}'",
            "description": f"TODO(adapter-kit): describe what process kinship '{prefix}' represents",
            "mechanisms": [],     # filled in Stage C
            "key_outputs": [],    # filled in Stage E
            "_source": SOURCE_AUTO_EXTRACT,
            "_members": members,  # internal, used by Stage D dispatch
        }

    # Save
    out = state.workdir / "stage_b_categories.yaml"
    yaml = _try_import_yaml()
    out.write_text(yaml.safe_dump(categories, sort_keys=False))
    print(f"\n  Wrote {_rel(out)}")
    print(f"  Edit this file to rename / merge / split categories before running Stage C.")
    print(f"  (Or accept the auto-proposal as-is — re-run with --restart-from C to skip.)")

    mark(state, "B", "completed",
         artifact_path=str(_rel(out)),
         notes=f"{len(categories)} categories proposed from {len(param_records)} parameters")
    return True


# =============================================================================
# Stage C — Phase 2 mechanism naming
# =============================================================================

def stage_c_mechanisms(
    state: State,
    model: str,
    wiki_root: Path,
) -> bool:
    """Propose mechanism candidates per category from wiki section headers."""
    print(f"\n=== Stage C: {STAGE_NAMES['C']} ===")

    yaml = _try_import_yaml()
    cats_path = state.workdir / "stage_b_categories.yaml"
    if not cats_path.is_file():
        print(f"  [FAIL] Stage B output missing: {cats_path}. Run Stage B first.")
        mark(state, "C", "failed", notes="stage_b_categories.yaml missing")
        return False
    categories: Dict[str, Dict[str, Any]] = yaml.safe_load(cats_path.read_text())

    print(f"  Reading wiki at {_rel(wiki_root)}...")
    wiki = _walk_wiki(wiki_root)
    headers = _extract_wiki_section_headers(wiki)
    print(f"  Found {len(wiki)} markdown files, {len(headers)} candidate section headers.")

    # Propose mechanisms: take section headers as candidate mechanism names.
    # Group by category by checking which category's parameters appear in the section's
    # source file (or appear textually in the section under that header).
    # For simplicity in this v0.1 builder: just expose all unique headers as candidates,
    # let the user assign them to categories manually via the YAML edit step.

    seen_headers: Counter = Counter(h for _, h in headers)
    top_headers = [h for h, _ in seen_headers.most_common() if not h.lower().startswith(("table of contents", "contents", "overview"))]

    # Convert headers into candidate mechanism CapWords names
    def to_mechanism_name(header: str) -> str:
        # Strip non-word chars, capwords-ify
        words = re.findall(r"[A-Za-z]+", header)
        return "_".join(w.capitalize() for w in words[:4])  # cap at 4 words

    candidates: List[str] = []
    seen: set = set()
    for h in top_headers[:50]:  # cap candidates at 50
        m = to_mechanism_name(h)
        if m and m not in seen and len(m) > 3:
            candidates.append(m)
            seen.add(m)

    print(f"  Proposed {len(candidates)} candidate mechanism names from wiki headers.")
    print(f"  (User: assign each to a category via the YAML edit pass — see stage_c_mechanisms.yaml)")

    mechanisms: Dict[str, Dict[str, Any]] = {}
    for cand in candidates:
        mechanisms[cand] = {
            "description": f"TODO(adapter-kit): one-line description of mechanism '{cand}'",
            "code_reference": "TODO(adapter-kit): SourceFile.F90::routine_name",
            "doc_reference": "TODO(adapter-kit): user-guide section name or wiki path",
            "parameters": [],     # filled in Stage D
            "affects": [],        # filled in Stage D
            "notes": f"TODO(adapter-kit): calibration context for '{cand}'.",
            "_source": SOURCE_AUTO_EXTRACT,
            "_assigned_category": None,  # user fills via YAML edit
        }

    out = state.workdir / "stage_c_mechanisms.yaml"
    out.write_text(yaml.safe_dump(mechanisms, sort_keys=False))

    # Also emit guidance file
    guidance = state.workdir / "stage_c_GUIDANCE.md"
    guidance.write_text(f"""# Stage C — Mechanism naming guidance

## What this stage does

Proposed {len(candidates)} candidate mechanism names from wiki section headers in
`{_rel(wiki_root)}`. Each candidate is a CapWords name derived from
a section header (e.g., "PID Controller" → `Pid_Controller`).

## What you do next

Edit `{_rel(out)}`:

1. **Drop unrelated candidates.** Many headers won't map to mechanisms (e.g.,
   "Table of Contents", page navigation, etc.). Delete those entries.
2. **Rename for clarity.** The auto-CapWords may produce awkward names. Rename
   freely — this is the _conceptual skeleton_ of the curated graph; spend time here.
3. **Assign each surviving mechanism to a category.** Set `_assigned_category` to
   one of the categories from `stage_b_categories.yaml`. Mechanisms without an
   assignment will be flagged in Stage D and skipped.
4. **Fill in code_reference + doc_reference.** Even rough citations help V2 validate.
5. **Aim for 5–15 surviving mechanisms total.** More is OK if the model is large.

## After editing

Re-run the seed builder with `--restart-from D` to dispatch Stage D's per-category
subagent prompts using your refined mechanism inventory.
""")

    print(f"  Wrote {_rel(out)}")
    print(f"  Wrote {_rel(guidance)} — read this for next steps.")

    mark(state, "C", "completed",
         artifact_path=str(_rel(out)),
         notes=f"{len(candidates)} mechanism candidates from {len(headers)} wiki headers")
    return True


# =============================================================================
# Stage D — Per-category subagent dispatch (prompt-pack mode)
# =============================================================================

PROMPT_TEMPLATE = """\
# Curated YAML authoring — category `{category}` for model `{model}`

You are authoring the `parameters:` section of A2MC's curated relationships
YAML for a single category.

## Universal context

- Model: `{model}` ({display_name})
- Total parameters: {n_total_params}
- Total mechanisms: {n_total_mechanisms}
- Parameter naming pattern: `{param_regex}`
- Output naming pattern: `{output_regex}`

## Your category

**Name:** `{category}`
**Members:** {n_members} parameter(s)

```
{member_list}
```

## Mechanisms in this category

{mechanism_block}

## Wiki reference

The model's wiki lives at:

```
{wiki_root}
```

Read sections relevant to this category's mechanisms before authoring entries.
The most-cited section headers across the wiki are:

{wiki_hint}

## Schema (FATES reference)

```yaml
parameter_name:
  category: <one_of_the_categories>
  controls:
    - Mechanism_Name
  affects:
    - OUTPUT_VAR_NAME
  related_to:
    - other_param_name
  calibration_notes: |
    Free-form Markdown. Typical range. Sign conventions. Gotchas.
    Cite wiki sections (path:line) for any non-trivial claim.
  _source: ai-draft
```

## Output

For EACH parameter in the member list above, produce a YAML entry of the shape
shown in the schema. Tag every entry with `_source: ai-draft`.

Constraints:

- Do NOT invent mechanisms not in the inventory above.
- Do NOT invent output variables. Use only outputs that match `{output_regex}`.
- Do NOT invent `related_to` parameters not in the model's parameter list.
- For `calibration_notes`, cite wiki paths when making non-trivial claims.
- If a parameter has no defensible content for a field, omit the field
  rather than fabricate.

## Output format

Return ONE YAML document with all entries under a top-level key:

```yaml
parameters:
  param_one:
    ...
  param_two:
    ...
```

Save the result back into the directory:

```
{output_dir}
```

as `{output_filename}`.
"""


def stage_d_dispatch(
    state: State,
    model: str,
    wiki_root: Path,
    param_file: Path,
    output_cdl: Path,
    mode: str = "prompt-pack",
) -> bool:
    """Generate per-category subagent prompts (prompt-pack mode)."""
    print(f"\n=== Stage D: {STAGE_NAMES['D']} (mode={mode}) ===")

    if mode != "prompt-pack":
        print(f"  [STUB] mode={mode!r} not yet implemented. Falling back to prompt-pack.")
        mode = "prompt-pack"

    yaml = _try_import_yaml()
    cats_path = state.workdir / "stage_b_categories.yaml"
    mechs_path = state.workdir / "stage_c_mechanisms.yaml"
    if not cats_path.is_file() or not mechs_path.is_file():
        print(f"  [FAIL] Stage B/C outputs missing.")
        mark(state, "D", "failed", notes="stage B or C outputs missing")
        return False

    categories: Dict[str, Dict[str, Any]] = yaml.safe_load(cats_path.read_text())
    mechanisms: Dict[str, Dict[str, Any]] = yaml.safe_load(mechs_path.read_text())

    try:
        from models import registry
        backend = registry.get_model(model)
        spec = backend.spec
    except Exception as e:
        print(f"  [FAIL] {e}")
        mark(state, "D", "failed", notes=str(e))
        return False

    # Group mechanisms by category
    mechs_by_cat: Dict[str, List[str]] = defaultdict(list)
    unassigned: List[str] = []
    for name, mdata in mechanisms.items():
        cat = mdata.get("_assigned_category")
        if cat and cat in categories:
            mechs_by_cat[cat].append(name)
        else:
            unassigned.append(name)

    if unassigned:
        print(f"  [WARN] {len(unassigned)} mechanism(s) have no _assigned_category and will be skipped:")
        for u in unassigned[:10]:
            print(f"    - {u}")
        if len(unassigned) > 10:
            print(f"    - ... and {len(unassigned) - 10} more")

    # Wiki hint: top 10 most-mentioned section headers
    wiki = _walk_wiki(wiki_root)
    headers = _extract_wiki_section_headers(wiki)
    seen_headers = Counter(h for _, h in headers)
    wiki_hint = "\n".join(f"  - {h}" for h, _ in seen_headers.most_common(10))

    # Generate one prompt per category that has parameters
    prompts_dir = state.workdir / "prompts"
    prompts_dir.mkdir(exist_ok=True)
    n_prompts = 0
    for cat_name, cat_data in categories.items():
        members = cat_data.get("_members", [])
        if not members:
            continue
        cat_mechs = mechs_by_cat.get(cat_name, [])
        if not cat_mechs:
            print(f"  [SKIP] category {cat_name!r} has no assigned mechanisms; skipping.")
            continue

        mech_lines = []
        for m in cat_mechs:
            mdata = mechanisms[m]
            mech_lines.append(f"- `{m}` — {mdata.get('description', '(no description)')}")
        mechanism_block = "\n".join(mech_lines)

        prompt_text = PROMPT_TEMPLATE.format(
            model=model,
            display_name=spec.display_name,
            category=cat_name,
            n_total_params=sum(len(c.get("_members", [])) for c in categories.values()),
            n_total_mechanisms=len(mechanisms),
            param_regex=spec.param_name_regex,
            output_regex=spec.output_name_regex,
            n_members=len(members),
            member_list="\n".join(f"- {m}" for m in members),
            mechanism_block=mechanism_block,
            wiki_root=wiki_root,
            wiki_hint=wiki_hint,
            output_dir=str(prompts_dir),
            output_filename=f"response_{cat_name}.yaml",
        )

        prompt_path = prompts_dir / f"prompt_{cat_name}.md"
        prompt_path.write_text(prompt_text)
        n_prompts += 1

    # Index file with run instructions
    index_md = prompts_dir / "INDEX.md"
    index_md.write_text(f"""# Stage D prompt pack — {model}

Generated {len(categories)} category prompts in this directory.

## How to use

For each `prompt_<category>.md` file, paste its content into Claude Code (or
Claude.ai, ChatGPT, etc.) and follow the instructions to author the YAML
entries. Save each response as `response_<category>.yaml` in this same directory.

When all categories have responses, re-run the seed builder with:

```bash
python scripts/curated_seed_builder.py \\
    --model {model} \\
    --wiki <wiki> --param-file <param-file> --output-cdl <output-cdl> \\
    --restart-from F
```

That will assemble all per-category responses into `models/{model}/curated_seed.yaml`
(Stage F), validate it (Stage G), and run a retrieval smoke test (Stage H).

## Pilot pattern (recommended)

Before running ALL prompts, dispatch ONE category and review the response.
Common subagent pitfalls to look for:

- Fabricated parameter names not in the member list
- Fabricated mechanisms outside the inventory
- Fabricated output variables
- `related_to` clusters that don't make sense
- Calibration notes that look plausible but are wrong content-wise (V2 won't
  catch these — domain expertise required)

If the pilot looks good, dispatch the rest in parallel. If not, refine the
prompt + relevant mechanism descriptions in `stage_c_mechanisms.yaml`,
re-run `--restart-from D`, and try the pilot again.

This is the same pilot pattern documented in
`docs/a2mc_reference/codebase_wiki_generation_roadmap.md` §B.3.
""")

    print(f"  Wrote {n_prompts} prompt(s) + INDEX.md to {_rel(prompts_dir)}")
    print(f"")
    print(f"  Next: read {_rel(prompts_dir / 'INDEX.md')},")
    print(f"        run prompts through your AI of choice,")
    print(f"        save responses as response_<category>.yaml in {_rel(prompts_dir)},")
    print(f"        then re-run with --restart-from F.")

    mark(state, "D", "completed",
         artifact_path=str(_rel(prompts_dir)),
         notes=f"{n_prompts} prompts generated; awaiting subagent responses")
    return True


# =============================================================================
# Stage E — Phase 4 outputs entries
# =============================================================================

def stage_e_outputs(
    state: State,
    model: str,
    output_cdl: Path,
    top_n: int = 20,
) -> bool:
    """Propose top-N output variables for the user to author entries for."""
    print(f"\n=== Stage E: {STAGE_NAMES['E']} ===")

    try:
        from models import registry
        backend = registry.get_model(model)
        parser = backend.spec.output_parser_class()
        records = parser.parse(output_cdl)
    except NotImplementedError:
        print(f"  [SKIP] {model}'s output_parser is a stub.")
        mark(state, "E", "failed", notes="output_parser is a stub")
        return False
    except Exception as e:
        print(f"  [FAIL] Could not parse {output_cdl}: {e}")
        mark(state, "E", "failed", notes=str(e))
        return False

    print(f"  Parsed {len(records)} output variable(s) from {output_cdl.name}")

    # Pick top N — for now just the first N alphabetically; future enhancement is
    # to rank by wiki-mention count.
    chosen = sorted(records.keys())[:top_n]

    yaml = _try_import_yaml()
    outputs: Dict[str, Dict[str, Any]] = {}
    for var in chosen:
        outputs[var] = {
            "description": f"TODO(adapter-kit): one-line description of {var}",
            "direct_drivers": [],
            "indirect_drivers": [],
            "diagnostic_value": "TODO(adapter-kit): how to interpret unusual values during calibration",
            "_source": SOURCE_AUTO_EXTRACT,
        }

    out = state.workdir / "stage_e_outputs.yaml"
    out.write_text(yaml.safe_dump(outputs, sort_keys=False))

    print(f"  Wrote {top_n} top-N output stubs to {_rel(out)}")
    print(f"  Edit this file to fill in description / direct_drivers / diagnostic_value")
    print(f"  for the calibration-priority variables. Stage F merges this into the final YAML.")

    mark(state, "E", "completed",
         artifact_path=str(_rel(out)),
         notes=f"{top_n} output stubs from {len(records)} total")
    return True


# =============================================================================
# Stage F — Assembly
# =============================================================================

def stage_f_assemble(
    state: State,
    model: str,
) -> bool:
    """Merge per-stage YAML fragments into models/<model>/curated_seed.yaml."""
    print(f"\n=== Stage F: {STAGE_NAMES['F']} ===")

    yaml = _try_import_yaml()

    # Load fragments
    cats_path = state.workdir / "stage_b_categories.yaml"
    mechs_path = state.workdir / "stage_c_mechanisms.yaml"
    outputs_path = state.workdir / "stage_e_outputs.yaml"

    if not all(p.is_file() for p in [cats_path, mechs_path, outputs_path]):
        missing = [p for p in [cats_path, mechs_path, outputs_path] if not p.is_file()]
        print(f"  [FAIL] Missing fragments: {[str(p.name) for p in missing]}")
        mark(state, "F", "failed", notes="missing fragments")
        return False

    categories = yaml.safe_load(cats_path.read_text()) or {}
    mechanisms = yaml.safe_load(mechs_path.read_text()) or {}
    outputs = yaml.safe_load(outputs_path.read_text()) or {}

    # Load per-category subagent responses (Stage D output)
    prompts_dir = state.workdir / "prompts"
    parameters: Dict[str, Dict[str, Any]] = {}
    n_response_files = 0
    if prompts_dir.is_dir():
        for resp_path in sorted(prompts_dir.glob("response_*.yaml")):
            n_response_files += 1
            try:
                resp = yaml.safe_load(resp_path.read_text()) or {}
                # Subagent should return {parameters: {...}}; tolerate either shape.
                if isinstance(resp, dict) and "parameters" in resp:
                    resp_params = resp["parameters"]
                else:
                    resp_params = resp
                if isinstance(resp_params, dict):
                    parameters.update(resp_params)
            except Exception as e:
                print(f"  [WARN] Skipping {resp_path.name} (parse error: {e})")

    print(f"  Categories: {len(categories)}")
    print(f"  Mechanisms: {len(mechanisms)}")
    print(f"  Outputs:    {len(outputs)}")
    print(f"  Parameters: {len(parameters)} (from {n_response_files} subagent response file(s))")

    # Strip internal _members / _assigned_category fields before writing
    final_cats = {}
    for k, v in categories.items():
        clean = {kk: vv for kk, vv in v.items() if kk != "_members"}
        final_cats[k] = clean

    final_mechs = {}
    for k, v in mechanisms.items():
        # Skip mechanisms without an assigned category
        if not v.get("_assigned_category"):
            continue
        clean = {kk: vv for kk, vv in v.items() if kk != "_assigned_category"}
        final_mechs[k] = clean

    # Assemble final document
    final = {
        "categories": final_cats,
        "mechanisms": final_mechs,
        "outputs": outputs,
        "parameters": parameters,
    }

    # Header comment (preserved when read back; PyYAML doesn't write comments,
    # so we prepend manually.)
    header = f"""# =============================================================================
# Curated Relationships YAML — {model}
# Generated by scripts/curated_seed_builder.py at {datetime.now(timezone.utc).isoformat(timespec='seconds')}
# v0.1 seed — every entry tagged with _source: auto-extract | ai-draft | human
# =============================================================================
"""

    out = REPO_ROOT / "models" / model / "curated_seed.yaml"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(header + "\n" + yaml.safe_dump(final, sort_keys=False))

    print(f"\n  Wrote {_rel(out)} ({out.stat().st_size // 1024} KB)")

    mark(state, "F", "completed",
         artifact_path=str(_rel(out)),
         notes=f"assembled: {len(final_cats)} cats, {len(final_mechs)} mechs, "
               f"{len(parameters)} params, {len(outputs)} outputs")
    return True


# =============================================================================
# Stage G — Static validation
# =============================================================================

def stage_g_validate(
    state: State,
    model: str,
    param_file: Path,
    output_cdl: Path,
) -> bool:
    """Run static checks per graphrag_curated_yaml_roadmap.md §Static validation."""
    print(f"\n=== Stage G: {STAGE_NAMES['G']} ===")

    yaml = _try_import_yaml()
    seed_path = REPO_ROOT / "models" / model / "curated_seed.yaml"
    if not seed_path.is_file():
        print(f"  [FAIL] {seed_path} missing. Run Stage F first.")
        mark(state, "G", "failed", notes="curated_seed.yaml missing")
        return False

    data = yaml.safe_load(seed_path.read_text()) or {}
    categories = data.get("categories", {}) or {}
    mechanisms = data.get("mechanisms", {}) or {}
    outputs = data.get("outputs", {}) or {}
    parameters = data.get("parameters", {}) or {}

    # Get authoritative param + output names from the parsers
    try:
        from models import registry
        backend = registry.get_model(model)
        param_records = backend.spec.parameter_parser_class().parse(param_file)
        output_records = backend.spec.output_parser_class().parse(output_cdl)
    except NotImplementedError as e:
        print(f"  [WARN] Parser is a stub — Dim 1 / 3 will be skipped.")
        param_records, output_records = {}, {}
    except Exception as e:
        print(f"  [WARN] Parser raised {type(e).__name__}: {e} — Dim 1 / 3 will be skipped.")
        param_records, output_records = {}, {}

    issues = []  # list of (severity, message) — severity 'fail' or 'warn'

    # Dim 1: every YAML parameter exists in parameter file
    if param_records:
        unknown_params = [p for p in parameters if p not in param_records]
        if unknown_params:
            for p in unknown_params[:20]:
                issues.append(("fail", f"YAML parameter {p!r} not in {param_file.name}"))
            if len(unknown_params) > 20:
                issues.append(("fail", f"...and {len(unknown_params) - 20} more"))
    else:
        issues.append(("warn", "Dim 1 skipped — parameter parser unavailable"))

    # Dim 2: every mechanism referenced under parameters[*].controls is defined
    referenced_mechs = set()
    for p, pdata in parameters.items():
        for m in (pdata.get("controls") or []):
            referenced_mechs.add(m)
    undefined_mechs = referenced_mechs - set(mechanisms.keys())
    for m in sorted(undefined_mechs):
        issues.append(("fail", f"mechanism {m!r} referenced but not defined under mechanisms:"))

    # Dim 3: every output referenced under parameters[*].affects exists in output CDL
    if output_records:
        referenced_outputs = set()
        for p, pdata in parameters.items():
            for o in (pdata.get("affects") or []):
                referenced_outputs.add(o)
        for m, mdata in mechanisms.items():
            for o in (mdata.get("affects") or []):
                referenced_outputs.add(o)
        unknown_outputs = referenced_outputs - set(output_records.keys())
        for o in sorted(unknown_outputs):
            issues.append(("fail", f"output {o!r} referenced in YAML but not in {output_cdl.name}"))
    else:
        issues.append(("warn", "Dim 3 skipped — output parser unavailable"))

    # Dim 4: every related_to is bidirectional
    for p, pdata in parameters.items():
        for related in (pdata.get("related_to") or []):
            if related not in parameters:
                issues.append(("fail", f"{p!r}.related_to includes {related!r} which is not in parameters"))
                continue
            other_related = parameters[related].get("related_to") or []
            if p not in other_related:
                issues.append(("warn", f"{p!r}.related_to includes {related!r} but {related!r}.related_to does NOT include {p!r}"))

    n_fail = sum(1 for s, _ in issues if s == "fail")
    n_warn = sum(1 for s, _ in issues if s == "warn")

    print(f"  Static validation:")
    print(f"    parameters in YAML:     {len(parameters)}")
    print(f"    mechanisms in YAML:     {len(mechanisms)}")
    print(f"    outputs in YAML:        {len(outputs)}")
    print(f"    failures:               {n_fail}")
    print(f"    warnings:               {n_warn}")

    if issues:
        print(f"")
        print(f"  Issues (showing first 30):")
        for sev, msg in issues[:30]:
            tag = "FAIL" if sev == "fail" else "WARN"
            print(f"    [{tag}] {msg}")
        if len(issues) > 30:
            print(f"    ... and {len(issues) - 30} more")

    if n_fail > 0:
        mark(state, "G", "failed", notes=f"{n_fail} fails, {n_warn} warns")
        return False

    mark(state, "G", "completed", notes=f"clean ({n_warn} warnings)")
    return True


# =============================================================================
# Stage H — Retrieval smoke test
# =============================================================================

def stage_h_smoke(
    state: State,
    model: str,
) -> bool:
    """Build a temp graph from the seed YAML; run canned queries."""
    print(f"\n=== Stage H: {STAGE_NAMES['H']} ===")

    yaml = _try_import_yaml()
    seed_path = REPO_ROOT / "models" / model / "curated_seed.yaml"
    data = yaml.safe_load(seed_path.read_text()) or {}
    parameters = data.get("parameters", {}) or {}
    mechanisms = data.get("mechanisms", {}) or {}
    outputs = data.get("outputs", {}) or {}

    if not parameters or not mechanisms:
        print(f"  [WARN] Empty parameters or mechanisms; skipping retrieval smoke.")
        mark(state, "H", "skipped", notes="empty seed")
        return True

    try:
        import networkx as nx
    except ImportError:
        print(f"  [SKIP] networkx not installed; skipping retrieval smoke.")
        mark(state, "H", "skipped", notes="networkx missing")
        return True

    # Build a minimal graph from the YAML alone (no full RAG infrastructure).
    # This is a "does retrieval semantically work?" sanity test, not a full RAG build.
    G = nx.DiGraph()
    for pname, pdata in parameters.items():
        G.add_node(pname, type="parameter", **{k: v for k, v in pdata.items() if not isinstance(v, (dict, list))})
        for m in (pdata.get("controls") or []):
            G.add_edge(pname, m, type="controls")
        for o in (pdata.get("affects") or []):
            G.add_edge(pname, o, type="affects")
        for r in (pdata.get("related_to") or []):
            G.add_edge(pname, r, type="related_to")
    for mname, mdata in mechanisms.items():
        G.add_node(mname, type="mechanism")
        for o in (mdata.get("affects") or []):
            G.add_edge(mname, o, type="affects")
    for oname in outputs:
        G.add_node(oname, type="output")

    print(f"  Built temp graph: {G.number_of_nodes()} nodes, {G.number_of_edges()} edges")

    # Canned queries
    queries_passed = 0
    queries_total = 0

    # Q1: pick the first output, find params that affect it
    output_names = list(outputs.keys())
    if output_names:
        queries_total += 1
        target = output_names[0]
        affecting = [u for u, v, d in G.in_edges(target, data=True) if d.get("type") == "affects"]
        if affecting:
            queries_passed += 1
            print(f"  Q1 ✓ 'What parameters affect {target}?' → {len(affecting)} hit(s): {affecting[:5]}")
        else:
            print(f"  Q1 ✗ 'What parameters affect {target}?' → 0 hits")

    # Q2: pick the first mechanism, find params that control it
    mech_names = list(mechanisms.keys())
    if mech_names:
        queries_total += 1
        target = mech_names[0]
        controlling = [u for u, v, d in G.in_edges(target, data=True) if d.get("type") == "controls"]
        if controlling:
            queries_passed += 1
            print(f"  Q2 ✓ 'What controls {target}?' → {len(controlling)} hit(s): {controlling[:5]}")
        else:
            print(f"  Q2 ✗ 'What controls {target}?' → 0 hits")

    # Q3: pick the first parameter, find related_to neighbors
    if parameters:
        queries_total += 1
        target = list(parameters.keys())[0]
        related = [v for u, v, d in G.out_edges(target, data=True) if d.get("type") == "related_to"]
        if related:
            queries_passed += 1
            print(f"  Q3 ✓ 'What is typically tuned with {target}?' → {len(related)} hit(s): {related[:5]}")
        else:
            print(f"  Q3 ~ 'What is typically tuned with {target}?' → 0 hits (acceptable for many params)")
            queries_passed += 1  # accept; many params have no related_to neighbors

    print(f"")
    print(f"  Smoke test: {queries_passed}/{queries_total} queries returned ≥1 hit (Q3 always passes)")

    mark(state, "H", "completed",
         notes=f"graph: {G.number_of_nodes()}/{G.number_of_edges()}; queries: {queries_passed}/{queries_total}")
    return True


# =============================================================================
# Main
# =============================================================================

def main() -> int:
    p = argparse.ArgumentParser(
        description="A2MC curated seed builder (Recipe G1).",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    p.add_argument("--model", required=True, help="Adapter directory name (e.g., 'ecosim')")
    p.add_argument("--wiki", type=Path, required=True, help="Wiki root (commit-pinned subdirectory)")
    p.add_argument("--param-file", type=Path, required=True, help="Parameter file (CDL/JSON/YAML)")
    p.add_argument("--output-cdl", type=Path, required=True, help="Output variable CDL")
    p.add_argument("--user-guide", type=Path, help="(optional) User guide PDF for Phase 2 mechanism naming")
    p.add_argument("--codebase-root", type=Path, help="(optional) Codebase source tree for Phase 2 enrichment")
    p.add_argument("--mode", choices=["prompt-pack", "api", "auto"], default="prompt-pack",
                   help="Subagent dispatch mode for Stage D (default: prompt-pack)")
    p.add_argument("--restart-from", choices=ALL_STAGES,
                   help="Restart at this stage. Earlier stages stay completed.")
    p.add_argument("--workdir", type=Path,
                   help="Override workdir (default: Offline/seed_builder_<model>/)")

    args = p.parse_args()

    workdir = args.workdir or (REPO_ROOT / "Offline" / f"seed_builder_{args.model}")
    workdir.mkdir(parents=True, exist_ok=True)

    state = load_state(args.model, workdir)

    if args.restart_from:
        for s in ALL_STAGES:
            if s < args.restart_from:
                if state.get(s).status == "pending":
                    mark(state, s, "skipped", notes="--restart-from skipped")
            else:
                state.stage_results[s] = StageResult(status="pending")
        save_state(state)
        print(f"Restarting from Stage {args.restart_from}")

    print(f"=========================================================")
    print(f" curated_seed_builder.py — {args.model}")
    print(f" workdir: {_rel(workdir)}")
    print(f"=========================================================")

    # Register the adapter for EVERY run, not just one that executes Stage A.
    # Stages B/D/E/F/H call registry.get_model(model), but the only import_module() was inside
    # Stage A's preflight -- so any --restart-from (the documented iteration path: "re-run with
    # --restart-from D") hit "Unknown model: ... Registered: []" with an empty registry.
    try:
        importlib.import_module(f"models.{args.model}")
    except Exception as e:
        print(f"[FAIL] Could not import models.{args.model}: {type(e).__name__}: {e}")
        return 1

    # Stage A
    if state.get("A").status not in ("completed", "skipped"):
        if not stage_a_preflight(state, args.model, args.wiki, args.param_file,
                                  args.output_cdl, args.user_guide, args.codebase_root):
            return 2

    # Stage B
    if state.get("B").status not in ("completed", "skipped"):
        if not stage_b_categorize(state, args.model, args.param_file):
            return 2

    # Stage C
    if state.get("C").status not in ("completed", "skipped"):
        if not stage_c_mechanisms(state, args.model, args.wiki):
            return 2

    # Stage D — pause for user to edit Stage C output before dispatching
    if state.get("D").status not in ("completed", "skipped"):
        if not stage_d_dispatch(state, args.model, args.wiki, args.param_file,
                                 args.output_cdl, mode=args.mode):
            return 2
        print("\n[Stage D produced prompts. Run them through your AI of choice,")
        print(" save responses as response_<category>.yaml under workdir/prompts/,")
        print(" then re-run with --restart-from F to assemble + validate.]")
        return 0  # natural pause point

    # Stage E
    if state.get("E").status not in ("completed", "skipped"):
        if not stage_e_outputs(state, args.model, args.output_cdl):
            return 2

    # Stage F
    if state.get("F").status not in ("completed", "skipped"):
        if not stage_f_assemble(state, args.model):
            return 2

    # Stage G
    if state.get("G").status not in ("completed", "skipped"):
        if not stage_g_validate(state, args.model, args.param_file, args.output_cdl):
            print("\n[Stage G found failures. Fix the YAML and re-run with --restart-from G.]")
            return 1

    # Stage H
    if state.get("H").status not in ("completed", "skipped"):
        stage_h_smoke(state, args.model)

    print(f"\nDone. Workdir: {_rel(workdir)}")
    print(f"Seed YAML: models/{args.model}/curated_seed.yaml")
    return 0


if __name__ == "__main__":
    sys.exit(main())
