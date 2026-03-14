# Autoiterate Agent Team — Parallel Mode

This is a reference prompt for running autoiterate in parallel mode using Claude Code agent teams. Copy-paste or adapt the prompt below.

## Prerequisites

1. Agent teams enabled: `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS` set in settings or env
2. Golden dataset uploaded: `uv run --package astral-eval astral-eval upload-dataset --since {date} --name golden-week`
3. Familiarity with `/autoiterate` (serial mode) — the teammates follow the same protocol

## Team Prompt

Paste this into a Claude Code session to start a parallel autoiterate run:

---

```
Create an agent team to optimize newsletter quality through parallel experimentation.

## Context

This is Astral Index, a space tech newsletter. The pipeline (rank → cluster → summarize → draft) lives in packages/author/src/astral_author/. Quality is measured by heuristic scorers via:

  uv run --package astral-eval astral-eval experiment --dataset golden-week --strategy baseline --no-llm

Read .claude/skills/autoiterate/SKILL.md for the full iteration protocol.

## Target

Optimize: {TARGET_SCORER}  (e.g., source_diversity, category_coverage, section_balance)
Dataset: golden-week
Strategy: baseline

## Team structure

**You (lead):** Coordinate experiments. Each generation:
1. Read data/eval/autoiterate_log.md and git log for history
2. Read the target scorer implementation in packages/core/src/astral_core/scoring.py
3. Ideate 3 DIFFERENT approaches to improve the target scorer
4. Assign one approach per teammate — be specific about what to change and in which file
5. Require plan approval: review each teammate's plan before they implement
6. Wait for all teammates to report scores
7. Merge the winning branch: git merge autoiterate/{winner} --no-edit
8. Clean up losing branches: git branch -D autoiterate/{loser}
9. Update data/eval/autoiterate_log.md with the generation results
10. Spawn fresh teammates for the next generation
11. Repeat for {N_GENERATIONS} generations (default: 3)

**Teammates (3):** Each receives an approach. Protocol:
1. git worktree add /tmp/autoiterate-{your-name} -b autoiterate/{your-name}
2. Work in the worktree directory
3. Implement the assigned change (ONLY files in packages/author/src/astral_author/)
4. Run: uv run pre-commit run --all-files
5. Commit with message: "autoiterate(team): {description}"
6. Run: uv run --package astral-eval astral-eval experiment --dataset golden-week --strategy baseline --no-llm
7. Parse the target scorer value and overall average
8. Message the lead: "Done. {target_scorer}={value}, avg={value}. Branch: autoiterate/{name}"
9. git worktree remove /tmp/autoiterate-{your-name}
10. Shut down

## Rules
- Teammates: only modify packages/author/src/astral_author/. Nothing else.
- Lead: only merge branches that improved the target score without regressing others > 0.05.
- If no teammate improved, log "generation {N}: no improvement" and try different approaches.
- Lead does NOT implement changes — only coordinate and merge.
- Use Sonnet for teammates to reduce cost.

## Start

First, establish baseline:
  uv run --package astral-eval astral-eval experiment --dataset golden-week --strategy baseline --no-llm

Read the scorer implementations, then begin generation 1.
```

---

## Customization

### Change the number of teammates

Replace "Teammates (3)" with however many parallel experiments you want. 3 is the sweet spot for token cost vs. search breadth.

### Change the number of generations

Set `N_GENERATIONS` in the prompt. Each generation = 1 round of parallel experiments. 3 generations × 3 teammates = 9 total experiments.

### Target multiple scorers

Run separate team sessions for each scorer, or modify the prompt to rotate targets across generations:

```
Generation 1: optimize source_diversity
Generation 2: optimize category_coverage
Generation 3: optimize the scorer that's now lowest
```

### Use with /loop

The team prompt is self-contained (it loops by spawning fresh teammates each generation). You don't need `/loop` for the team version — the lead handles the loop count via `N_GENERATIONS`.

For serial mode, `/loop` works:
```
/loop 10 /autoiterate source_diversity
```

## Results Log Format

The lead maintains `data/eval/autoiterate_log.md` in this format:

```markdown
# Autoiterate Results Log
Target: source_diversity
Dataset: golden-week
Strategy: baseline
Started: 2026-03-14T10:00:00

## Baseline
| Scorer | Score |
|--------|-------|
| source_diversity | 0.42 |
| category_coverage | 0.65 |
| ... | ... |

## Generation 1 (parallel, 3 teammates)
| Teammate | Change | source_diversity | Avg | Delta | Result |
|----------|--------|-----------------|-----|-------|--------|
| alpha | Added source tier weighting in rank.py | 0.48 | 0.61 | +0.06 | WINNER |
| beta | Per-source item cap of 3 in cluster.py | 0.44 | 0.59 | +0.02 | discard |
| gamma | Geographic diversity bonus in rank.py | 0.41 | 0.58 | -0.01 | discard |

## Generation 2 (parallel, 3 teammates)
| Teammate | Change | source_diversity | Avg | Delta | Result |
|----------|--------|-----------------|-----|-------|--------|
| alpha | Reduced cap to 2 items from same source | 0.52 | 0.60 | +0.04 | WINNER |
| beta | Source rotation across sections | 0.49 | 0.62 | +0.01 | discard |
| gamma | Weighted sampling instead of top-N | 0.46 | 0.57 | -0.02 | discard |

## Summary
Baseline: 0.42 → Current best: 0.52 (+0.10)
Generations: 2, Experiments: 6, Winners: 2
```

## Troubleshooting

**Teammates can't find the dataset:** Make sure you've uploaded it first with `upload-dataset`.

**Worktree conflicts:** Each teammate must use a unique branch name. The template uses `autoiterate/{teammate-name}`.

**Lead starts implementing:** Tell it: "Wait for your teammates to complete their tasks before proceeding. You are the coordinator, not an implementer."

**Teammate edits wrong files:** The scope constraint is in the prompt. If a teammate violates it, the lead should reject the plan at the approval step.
