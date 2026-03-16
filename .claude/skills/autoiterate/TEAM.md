# Autoiterate Parallel Mode — Reference

Parallel mode is built into the `/autoiterate` skill via `--parallel N`. This document covers design rationale and troubleshooting — the actual protocol lives in `SKILL.md`.

## Usage

```
/autoiterate --parallel 3 source_diversity                  # 3 teammates, target one scorer
/autoiterate --parallel 3 --generations 5 --mode sweep      # 5 generations, sweep mode
/autoiterate --parallel 3 --scope full --until "avg > 0.7"  # full scope, finish condition
```

## How It Works

Each generation, the lead:
1. Ideates N different approaches for the current target scorer
2. Spawns N agents via the Agent tool (`isolation: "worktree"`, `model: "sonnet"`)
3. All N run concurrently in isolated git worktrees
4. Collects results, merges the winning branch, discards the rest
5. Logs the generation and moves to the next

### Agent Tool Features Used

| Feature | Purpose |
|---------|---------|
| `isolation: "worktree"` | Each teammate gets an isolated repo copy — no manual worktree management |
| `model: "sonnet"` | Cheaper teammates (Opus lead, Sonnet workers) |
| `run_in_background: true` | All teammates spawn concurrently in one message |
| `mode: "bypassPermissions"` | Teammates don't prompt for tool approvals |
| Return value | Teammates return structured RESULT blocks; worktree branch info comes from Agent tool metadata |

### Cost Model

- **Lead (Opus):** ideation, coordination, merge decisions — relatively few tokens per generation
- **Teammates (Sonnet):** read files, implement, run experiment — bulk of the tokens
- 3 teammates × 3 generations = 9 experiments. At ~$0.30–0.50 per Sonnet experiment (heuristic-only), that's ~$3–5 per parallel run.
- With LLM judges: ~$1–2 per experiment, so ~$9–18 per parallel run.

## Customization

### Number of teammates

`--parallel N`. 3 is the sweet spot — enough diversity without excessive cost. Use 2 for cheap exploration, 4–5 for broad search.

### Number of generations

`--generations G` (default 3). Each generation compounds on the previous winner. More generations = more improvement but higher cost.

### Combining with other flags

All serial-mode flags work in parallel mode:
- `--scope` controls what teammates may modify
- `--mode sweep` rotates targets across generations
- `--until` checks the finish condition after each generation
- `--no-llm` disables LLM judges (faster but misses quality dimensions)
- `--dataset` / `--strategy` pass through to experiment commands

## Troubleshooting

**Teammates can't find the dataset:** Make sure you've uploaded it first: `uv run --package astral-eval astral-eval setup-datasets`

**All teammates crash:** Usually a pre-commit or import error. The lead should read the error from the first teammate's result and fix the underlying issue before spawning the next generation.

**Lead starts implementing instead of coordinating:** The lead should ONLY ideate and merge — never make code changes directly in parallel mode.

**No winner for several generations:** The lead should try radically different approaches, widen the scope, or switch to a different target scorer.

**Worktree cleanup:** The Agent tool auto-cleans worktrees when no changes are made. For worktrees with changes, branches persist until the lead deletes them after merging/discarding.
