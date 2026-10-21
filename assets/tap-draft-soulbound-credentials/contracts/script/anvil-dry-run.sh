#!/usr/bin/env bash
# Dry run of DeploySoulbound against a local anvil node (no public chain, no real key). The key below is anvil's
# well-known default account 0; it is public and holds nothing anywhere else. Never put a real key in this file.
#   ./script/anvil-dry-run.sh      # from assets/tap-draft-soulbound-credentials/contracts/ (lib/forge-std linked)
set -euo pipefail
cd "$(dirname "$0")/.."
PORT="${ANVIL_PORT:-8545}"
export RPC_URL="http://127.0.0.1:${PORT}"
export PRIVATE_KEY="0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80"
rm -f deployments/31337.json; mkdir -p deployments
anvil --port "$PORT" --silent --chain-id 31337 &
ANVIL_PID=$!
trap 'kill $ANVIL_PID 2>/dev/null || true' EXIT
for _ in $(seq 1 50); do cast chain-id --rpc-url "$RPC_URL" >/dev/null 2>&1 && break; sleep 0.2; done
forge script script/DeploySoulbound.s.sol:DeploySoulbound --rpc-url "$RPC_URL" --broadcast --slow -vv 2>&1 \
  | grep -vE "^\s*$|Compiling|Solc|Compiler run|warning|─|│|╭|╰|help:|lint|foundry-pp|Detected artifacts|No files changed|Estimated|Sensitive|Transactions saved|Setting up|=====" || true
python3 - <<'PY'
import json
run = json.load(open("broadcast/DeploySoulbound.s.sol/31337/run-latest.json"))
total = 0; per = {}
for tx, rc in zip(run["transactions"], run["receipts"]):
    g = int(rc["gasUsed"], 16); total += g
    label = tx.get("contractName") or "?"
    key = f"{tx['transactionType']} {label}" if tx["transactionType"].startswith("CREATE") else f"CALL   {label}.{(tx.get('function') or '?').split('(')[0]}"
    per[key] = per.get(key, 0) + g
print(f"== DeploySoulbound.s.sol: {len(run['transactions'])} transactions, {total:,} gas")
for k, v in per.items(): print(f"   {v:>12,}  {k}")
PY
echo "--- deployments/31337.json"; cat deployments/31337.json
