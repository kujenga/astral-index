#!/usr/bin/env bash
# weekly.sh — Run the full Astral Index pipeline: scrape → expand → classify → draft → eval → deliver
set -euo pipefail

# ── Defaults ──────────────────────────────────────────────────────────────────
SINCE=7
DRY_RUN=false
SEND=false
NO_EXPAND=false
TODAY=$(date +%Y-%m-%d)

# ── Usage ─────────────────────────────────────────────────────────────────────
usage() {
    cat <<EOF
Usage: $(basename "$0") [OPTIONS]

Run the full Astral Index weekly pipeline.

Options:
  --since N        Lookback window in days or YYYY-MM-DD (default: 7)
  --dry-run        Pass --dry-run to each step; skip eval (no draft to evaluate)
  --send           Enable Buttondown delivery (interactive confirmation before send)
  --no-expand      Skip the expand step (useful when re-running on already-expanded data)
  -h, --help       Show this help message

Steps:
  1. Scrape      Fetch all configured sources
  2. Expand      Fetch full article text (with Playwright JS rendering)
  3. Classify    Keyword regex + Claude Haiku LLM fallback
  4. Draft       Generate newsletter (baseline strategy, Claude Sonnet)
  5. Evaluate    Heuristic + LLM quality judges
  6. Deliver     Push to Buttondown (only with --send)

Examples:
  $(basename "$0")                     # Full pipeline, no delivery
  $(basename "$0") --dry-run           # Preview mode, no LLM cost (except scrape)
  $(basename "$0") --send              # Full pipeline with Buttondown delivery
  $(basename "$0") --since 14          # Two-week lookback
  $(basename "$0") --no-expand         # Skip expansion (already expanded)
EOF
    exit 0
}

# ── Argument parsing ──────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
    case "$1" in
        --since)
            SINCE="${2:?--since requires a value}"
            shift 2
            ;;
        --dry-run)
            DRY_RUN=true
            shift
            ;;
        --send)
            SEND=true
            shift
            ;;
        --no-expand)
            NO_EXPAND=true
            shift
            ;;
        -h|--help)
            usage
            ;;
        *)
            echo "Unknown option: $1" >&2
            echo "Run '$(basename "$0") --help' for usage." >&2
            exit 1
            ;;
    esac
done

# ── Helpers ───────────────────────────────────────────────────────────────────
banner() {
    echo ""
    echo "═══════════════════════════════════════════════════════════════"
    echo "  $1"
    echo "═══════════════════════════════════════════════════════════════"
    echo ""
}

DRY_FLAG=()
build_flags() {
    if $DRY_RUN; then DRY_FLAG=("--dry-run"); fi
}

# ── Pre-flight checks ────────────────────────────────────────────────────────
build_flags

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

# Output paths
DRAFT_BASE="data/drafts/${TODAY}_weekly"
DRAFT_MD="${DRAFT_BASE}.md"
DRAFT_JSON="${DRAFT_BASE}.json"
EVAL_OUTPUT="data/eval/${TODAY}_results.json"

echo "Astral Index — Weekly Pipeline"
echo "  Date:       $TODAY"
echo "  Since:      $SINCE"
echo "  Dry run:    $DRY_RUN"
echo "  Send:       $SEND"
echo "  No expand:  $NO_EXPAND"

# ── Step 1: Scrape ────────────────────────────────────────────────────────────
banner "Step 1/6 — Scrape"
uv run --package astral-ingest astral-ingest scrape "${DRY_FLAG[@]}"

# ── Step 2: Expand ────────────────────────────────────────────────────────────
if $NO_EXPAND; then
    banner "Step 2/6 — Expand (skipped: --no-expand)"
else
    banner "Step 2/6 — Expand"
    uv run --package astral-ingest astral-ingest expand --since "$SINCE" --js "${DRY_FLAG[@]}"
fi

# ── Step 3: Classify ──────────────────────────────────────────────────────────
banner "Step 3/6 — Classify"
uv run --package astral-ingest astral-ingest classify --since "$SINCE" "${DRY_FLAG[@]}"

# ── Step 4: Draft ─────────────────────────────────────────────────────────────
banner "Step 4/6 — Draft"
if $DRY_RUN; then
    uv run --package astral-author astral-author draft --since "$SINCE" --dry-run
else
    uv run --package astral-author astral-author draft --since "$SINCE" --output "$DRAFT_MD"
    echo ""
    echo "Draft written to:"
    echo "  Markdown: $DRAFT_MD"
    echo "  JSON:     $DRAFT_JSON"
fi

# ── Step 5: Evaluate ──────────────────────────────────────────────────────────
if $DRY_RUN; then
    banner "Step 5/6 — Evaluate (skipped: --dry-run)"
else
    banner "Step 5/6 — Evaluate"
    mkdir -p "$(dirname "$EVAL_OUTPUT")"
    uv run --package astral-eval astral-eval quality \
        --since "$SINCE" \
        --draft-file "$DRAFT_JSON" \
        --output "$EVAL_OUTPUT"
    echo ""
    echo "Eval results written to: $EVAL_OUTPUT"
fi

# ── Step 6: Deliver ───────────────────────────────────────────────────────────
if $SEND; then
    if $DRY_RUN; then
        banner "Step 6/6 — Deliver (dry run)"
        uv run --package astral-serve astral-serve draft "$DRAFT_JSON" --dry-run
    else
        banner "Step 6/6 — Deliver"
        uv run --package astral-serve astral-serve draft "$DRAFT_JSON"
        echo ""
        echo "Draft pushed to Buttondown. Review it in the dashboard, then confirm below."
        echo ""
        read -rp "Send the newsletter now? [y/N] " confirm
        if [[ "$confirm" =~ ^[Yy]$ ]]; then
            uv run --package astral-serve astral-serve send "$TODAY"
            echo "Newsletter sent!"
        else
            echo "Skipped sending. To send later:"
            echo "  uv run --package astral-serve astral-serve send $TODAY"
        fi
    fi
else
    banner "Step 6/6 — Deliver (skipped: use --send to enable)"
    echo "To publish this draft manually:"
    echo "  uv run --package astral-serve astral-serve draft $DRAFT_JSON"
    echo "  uv run --package astral-serve astral-serve send $TODAY"
fi

# ── Done ──────────────────────────────────────────────────────────────────────
banner "Done"
echo "Pipeline complete for $TODAY."
