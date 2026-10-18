#!/usr/bin/env bash
# Copy the publishable parts of the working folder (tap-drafts) into this repository.
#
#   scripts/sync-from-drafts.sh SOURCE_DIR
#
# SOURCE_DIR (required) is the working folder that holds TAPs/, assets/, contracts/, tools/,
# profiles/, reviews/, publish/ and DESIGN.md.
# The source tree is scanned for secrets BEFORE anything is copied; any hit aborts the sync
# and leaves the repository untouched. Synced subtrees are mirrored with --delete, so files
# removed at the source disappear here too (contracts/lib, the forge-std submodule, is never touched).
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
if [ $# -ne 1 ] || [ ! -d "$1" ]; then
  echo "usage: $0 SOURCE_DIR   (the tap-drafts working folder)" >&2
  exit 64
fi
SRC="$(cd "$1" && pwd)"

DIRS=(TAPs assets contracts tools profiles reviews)
EXCLUDES=(
  --exclude 'out/' --exclude 'cache/' --exclude 'lib/' --exclude 'broadcast/'
  --exclude 'node_modules/' --exclude '__pycache__/' --exclude '*.pyc'
  --exclude '*.log' --exclude 'anvil*' --exclude '.DS_Store'
  --exclude '.env' --exclude '.env.*' --exclude '.dev.vars' --exclude '.wrangler/'
  --exclude 'work/'
)
# Withheld from publication for now (pending disclosure to the TapeOut team). Paths are relative
# to the synced subtree root.
# Raw holder data (owner addresses per token) is withheld too; tools/tokenset/README.md gives its sha256 and
# how to regenerate it from the chain. tokens.json / tokens.bin (ids only) are published.
WITHHELD=(--exclude '/alt-fairness-economics.md'
  --exclude '/tokenset/owners.json' --exclude '/tokenset/owner_classes.json'
  --exclude '/tokenset/transfers_sample.json'
  --exclude '/tapecode-test1.zh.md' --exclude '/partner-plan-review.md' --exclude '/final-r1-publications.md')
# The TapeCode-Test1 handbook and the partner / publication reviews are internal working documents.

for d in "${DIRS[@]}"; do
  [ -d "$SRC/$d" ] || { echo "sync: missing $SRC/$d" >&2; exit 1; }
done
[ -f "$SRC/DESIGN.md" ] || { echo "sync: missing $SRC/DESIGN.md" >&2; exit 1; }
# The published article: publish/standard.md when present (it replaces the older article.md).
if [ -f "$SRC/publish/standard.md" ]; then ARTICLE=standard.md
elif [ -f "$SRC/publish/article.md" ]; then ARTICLE=article.md
else echo "sync: missing $SRC/publish/standard.md (or article.md)" >&2; exit 1; fi
for fig in $(grep -oE 'figures/[A-Za-z0-9._-]+' "$SRC/publish/$ARTICLE" | sort -u); do
  [ -f "$SRC/publish/$fig" ] || { echo "sync: $ARTICLE references missing publish/$fig — nothing copied" >&2; exit 3; }
done
[ -d "$SRC/publish/figures" ] || { echo "sync: missing $SRC/publish/figures" >&2; exit 1; }

# ---------------------------------------------------------------- secret scan (source side)
# Context-anchored patterns, so the many SHA-256 values in vectors.json do not match.
PATTERNS=(
  '-----BEGIN [A-Z ]*PRIVATE KEY-----'
  '(private[_-]?key|privkey|secret[_-]?key|PRIVATE_KEY|PRIV_KEY)["'"'"']?[[:space:]]*[:=][[:space:]]*["'"'"']?(0x)?[0-9a-fA-F]{64}'
  '(mnemonic|seed[_ ]?phrase|MNEMONIC)["'"'"']?[[:space:]]*[:=][[:space:]]*["'"'"']([a-z]+ ){11,}[a-z]+'
  'xprv[1-9A-HJ-NP-Za-km-z]{100,}'
  'AKIA[0-9A-Z]{16}'
  'sk_live_[0-9A-Za-z]{16,}'
  'gh[pousr]_[A-Za-z0-9]{36}'
  'github_pat_[A-Za-z0-9_]{40,}'
  'xox[baprs]-[A-Za-z0-9-]{10,}'
  'AIza[0-9A-Za-z_-]{35}'
  '(infura\.io/v3/|alchemy\.com/v2/|quiknode\.pro/|/api-key/|[?&]api[_-]?key=)[A-Za-z0-9_-]{16,}'
  '(api[_-]?key|apikey|API_KEY|auth[_-]?token|bearer)["'"'"']?[[:space:]]*[:=][[:space:]]*["'"'"'][A-Za-z0-9_-]{24,}["'"'"']'
)
# Well-known public test keys (anvil/hardhat defaults) are not secrets; list them here if ever needed.
ALLOW='ac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80'

GREP_EXCL=(--exclude-dir=out --exclude-dir=cache --exclude-dir=lib --exclude-dir=broadcast
           --exclude-dir=node_modules --exclude-dir=__pycache__ --exclude-dir=work --exclude='*.log')
HITS=""
for p in "${PATTERNS[@]}"; do
  h="$(cd "$SRC" && grep -rnIE "${GREP_EXCL[@]}" -e "$p" "${DIRS[@]}" DESIGN.md "publish/$ARTICLE" publish/figures 2>/dev/null | grep -v "$ALLOW" || true)"
  [ -n "$h" ] && HITS="$HITS$h"$'\n'
done
if [ -n "$HITS" ]; then
  echo "sync: possible secrets found in $SRC — nothing copied:" >&2
  printf '%s' "$HITS" | cut -c1-200 >&2
  exit 2
fi

# ---------------------------------------------------------------- copy
for d in "${DIRS[@]}"; do
  mkdir -p "$REPO/$d"
  extra=()
  [ "$d" = reviews ] && extra=("${WITHHELD[@]}")
  rsync -a --delete "${EXCLUDES[@]}" ${extra[@]+"${extra[@]}"} "$SRC/$d/" "$REPO/$d/"
done
rm -f "$REPO/reviews/alt-fairness-economics.md"

# Article (Markdown + SVG figures only; the .html pages, other drafts and ARTIFACT-RULES.md are not published).
mkdir -p "$REPO/docs/article/figures"
rm -f "$REPO/docs/article/"*.md
cp "$SRC/publish/$ARTICLE" "$REPO/docs/article/$ARTICLE"
# Only the figures the article references are copied; a missing one fails the sync.
rm -f "$REPO/docs/article/figures/"*
for fig in $(grep -oE 'figures/[A-Za-z0-9._-]+' "$SRC/publish/$ARTICLE" | sort -u); do
  [ -f "$SRC/publish/$fig" ] || { echo "sync: $ARTICLE references missing publish/$fig" >&2; exit 3; }
  cp "$SRC/publish/$fig" "$REPO/docs/article/$fig"
done

# DESIGN.md lives at the working folder's root; in this repo it is docs/DESIGN.md. Rewrite its
# repository paths so they resolve from docs/: markdown links get a ../ prefix, and code spans that
# name an existing file or folder become links.
python3 - "$SRC/DESIGN.md" "$REPO/docs/DESIGN.md" "$REPO" <<'PY'
import os, re, sys
src, dst, repo = sys.argv[1:4]
text = open(src, encoding="utf-8").read()
TOP = ("TAPs/", "assets/", "contracts/", "tools/", "profiles/", "reviews/", "scripts/")

def link(m):
    label, target = m.group(1), m.group(2)
    if re.match(r"^(https?:|mailto:|#|/|\.\./)", target):
        return m.group(0)
    if target == "DESIGN.md" or target.startswith("DESIGN.md#"):
        return f"[{label}]({target})"
    return f"[{label}](../{target})"

text = re.sub(r"(?<!!)\[([^\]]*)\]\(([^)\s]+)\)", link, text)

def span(m):
    path = m.group(1)
    if path.startswith(TOP) and not re.search(r"[*<>…]", path) and os.path.exists(os.path.join(repo, path.rstrip("/"))):
        return f"[`{path}`](../{path})"
    return m.group(0)

# only code spans that are not already the label of a link
text = re.sub(r"(?<!\[)`([A-Za-z][\w./-]*)`(?!\])", span, text)
note = "> Copied from the working folder by `scripts/sync-from-drafts.sh`; repository paths are rewritten to resolve from `docs/`.\n\n"
open(dst, "w", encoding="utf-8").write(note + text)
PY

echo "sync: copied ${DIRS[*]}, DESIGN.md -> docs/DESIGN.md, publish/$ARTICLE + figures -> docs/article/ from $SRC"
echo "sync: withheld reviews/alt-fairness-economics.md"
if git -C "$REPO" rev-parse --git-dir >/dev/null 2>&1; then
  git -C "$REPO" status --short -- "${DIRS[@]}" docs/DESIGN.md | head -50
fi
