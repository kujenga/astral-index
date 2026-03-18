#!/usr/bin/env bash
# weekly.sh — Run the full Astral Index pipeline: scrape → expand → classify → draft → eval → deliver
set -euo pipefail

# ── Defaults ──────────────────────────────────────────────────────────────────
SINCE=""
DRY_RUN=false
SEND=false
NO_EXPAND=false
TODAY=$(date +%Y-%m-%d)

# Wednesday-based issue date: most recent Wednesday (including today if Wednesday)
DOW=$(date +%u)  # 1=Mon ... 7=Sun
DAYS_SINCE_WED=$(( (DOW - 3 + 7) % 7 ))
ISSUE_DATE=$(date -v-${DAYS_SINCE_WED}d +%Y-%m-%d 2>/dev/null \
    || date -d "$TODAY - ${DAYS_SINCE_WED} days" +%Y-%m-%d)

# ── Usage ─────────────────────────────────────────────────────────────────────
usage() {
    cat <<EOF
Usage: $(basename "$0") [OPTIONS]

Run the full Astral Index weekly pipeline.

Options:
  --since N        Lookback window in days or YYYY-MM-DD (default: Wed-to-Wed)
  --dry-run        Pass --dry-run to each step; skip eval (no draft to evaluate)
  --send           Enable Buttondown delivery (interactive confirmation before send)
  --no-expand      Skip the expand step (useful when re-running on already-expanded data)
  -h, --help       Show this help message

Steps:
  1. Scrape      Fetch all configured sources
  2. Expand      Fetch full article text (with Playwright JS rendering)
  3. Classify    Keyword regex + Claude Haiku LLM fallback
  4. Draft+Eval  Generate newsletter and run quality scoring
  5. Deliver     Push to Buttondown (only with --send)

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

# Build --since flag for ingest commands (only when explicitly set)
SINCE_FLAG=()
if [[ -n "$SINCE" ]]; then
    SINCE_FLAG=("--since" "$SINCE")
fi

# Output paths — staged in git-tracked issues/ directory
ISSUE_DIR="issues/${ISSUE_DATE}"
DRAFT_MD="${ISSUE_DIR}/draft.md"
DRAFT_JSON="${ISSUE_DIR}/draft.json"
EVAL_OUTPUT="data/eval/${ISSUE_DATE}_results.json"

echo "Astral Index — Weekly Pipeline"
echo "  Issue date: $ISSUE_DATE"
echo "  Since:      ${SINCE:-Wed-to-Wed default}"
echo "  Dry run:    $DRY_RUN"
echo "  Send:       $SEND"
echo "  No expand:  $NO_EXPAND"

# ── Step 1: Scrape ────────────────────────────────────────────────────────────
banner "Step 1/5 — Scrape"
uv run --package astral-ingest astral-ingest scrape "${DRY_FLAG[@]}"

# ── Step 2: Expand ────────────────────────────────────────────────────────────
if $NO_EXPAND; then
    banner "Step 2/5 — Expand (skipped: --no-expand)"
else
    banner "Step 2/5 — Expand"
    uv run --package astral-ingest astral-ingest expand --since "${SINCE:-7}" --js "${DRY_FLAG[@]}"
fi

# ── Step 3: Classify ──────────────────────────────────────────────────────────
banner "Step 3/5 — Classify"
uv run --package astral-ingest astral-ingest classify --since "${SINCE:-7}" "${DRY_FLAG[@]}"

# ── Step 4: Draft + Evaluate ──────────────────────────────────────────────────
banner "Step 4/5 — Draft + Evaluate"
if $DRY_RUN; then
    uv run --package astral-author astral-author draft "${SINCE_FLAG[@]}" --dry-run
else
    # Draft — stages in issues/{date}/ automatically
    uv run --package astral-author astral-author draft "${SINCE_FLAG[@]}"

    # Evaluate — scores the draft and writes eval.json alongside the draft
    echo ""
    echo "Running quality evaluation..."
    EVAL_JSON="${ISSUE_DIR}/eval.json"
    uv run --package astral-eval astral-eval quality \
        --since "${SINCE:-7}" \
        --draft-file "$DRAFT_JSON" \
        --output "$EVAL_JSON"
    echo ""
    echo "Staged at ${ISSUE_DIR}/:"
    echo "  draft.md   — newsletter (edit this)"
    echo "  draft.json — machine metadata"
    echo "  eval.json  — quality scores"
    echo ""
    echo "Review scores above, edit draft.md, then re-run with --send"
fi

# ── Step 6: Deliver ───────────────────────────────────────────────────────────
if $SEND; then
    if $DRY_RUN; then
        banner "Step 5/5 — Deliver (dry run)"
        uv run --package astral-serve astral-serve draft "$ISSUE_DATE" --dry-run
    else
        banner "Step 5/5 — Deliver"
        uv run --package astral-serve astral-serve draft "$ISSUE_DATE"
        echo ""
        echo "Draft pushed to Buttondown. Review it in the dashboard, then confirm below."
        echo ""
        read -rp "Send the newsletter now? [y/N] " confirm
        if [[ "$confirm" =~ ^[Yy]$ ]]; then
            uv run --package astral-serve astral-serve send "$ISSUE_DATE"
            echo "Newsletter sent!"
        else
            echo "Skipped sending. To send later:"
            echo "  uv run --package astral-serve astral-serve send $ISSUE_DATE"
        fi
    fi
else
    banner "Step 5/5 — Deliver (skipped: use --send to enable)"
    echo "To publish this draft manually:"
    echo "  uv run --package astral-serve astral-serve draft $ISSUE_DATE"
    echo "  uv run --package astral-serve astral-serve send $ISSUE_DATE"
fi

# ── Done ──────────────────────────────────────────────────────────────────────
banner "Done"
echo "Pipeline complete for issue $ISSUE_DATE."
