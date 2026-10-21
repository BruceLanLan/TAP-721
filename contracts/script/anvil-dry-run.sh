#!/usr/bin/env bash
# Dry run of every deployment script against a local anvil node (no public chain, no real key).
# The key below is anvil's well-known default account 0 (printed by `anvil` at start-up); it is public and holds
# nothing anywhere else. Never put a real key in this file.
#
#   ./script/anvil-dry-run.sh            # from contracts/
#
# Output: per-script and per-contract gas totals (from the broadcast receipts) and deployments/31337.json.
set -euo pipefail
cd "$(dirname "$0")/.."

PORT="${ANVIL_PORT:-8545}"
export RPC_URL="http://127.0.0.1:${PORT}"
export PRIVATE_KEY="0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80"
export ANVIL_DRY_RUN=1

rm -f deployments/31337.json
mkdir -p deployments
anvil --port "$PORT" --silent --chain-id 31337 &
ANVIL_PID=$!
trap 'kill $ANVIL_PID 2>/dev/null || true' EXIT
for _ in $(seq 1 50); do
  cast chain-id --rpc-url "$RPC_URL" >/dev/null 2>&1 && break
  sleep 0.2
done

summarize() {
  # $1 = script name (e.g. DeployCore.s.sol): sum gasUsed of the receipts of its latest broadcast
  python3 - "$1" <<'EOF'
import json, sys, glob
name = sys.argv[1]
path = f"broadcast/{name}/31337/run-latest.json"
run = json.load(open(path))
txs = run["transactions"]; rcs = run["receipts"]
total = 0; per = {}
for tx, rc in zip(txs, rcs):
    g = int(rc["gasUsed"], 16)
    total += g
    label = tx.get("contractName") or "?"
    if tx["transactionType"].startswith("CREATE"):
        key = f"{tx['transactionType']} {label}"
    else:
        key = f"CALL   {label}.{(tx.get('function') or '?').split('(')[0]}"
    per[key] = per.get(key, 0) + g
print(f"== {name}: {len(txs)} transactions, {total:,} gas")
for k, v in per.items():
    print(f"   {v:>12,}  {k}")
EOF
}

for s in DeployCore DeployCompanion DeployContainerLock; do
  echo "--- forge script script/$s.s.sol (anvil)"
  forge script "script/$s.s.sol:$s" --rpc-url "$RPC_URL" --broadcast --slow -vv 2>&1 | grep -vE "^\s*$|Compiling|Solc|Compiler run|warning|─|│|╭|╰|help:|lint|foundry-pp|Detected artifacts|No files changed" || true
  summarize "$s.s.sol"
done

echo "--- deployments/31337.json"
cat deployments/31337.json
