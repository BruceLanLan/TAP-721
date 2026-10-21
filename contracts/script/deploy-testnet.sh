#!/usr/bin/env bash
# One-command testnet deployment of the TAP-721 family (DEPLOY.md §5).
# Needs PRIVATE_KEY (a TEST key) and RPC_URL in the environment; never prints the key.
#
#   export PRIVATE_KEY=…  RPC_URL=…
#   contracts/script/deploy-testnet.sh            # add DRY=1 to simulate without --broadcast
set -euo pipefail
: "${PRIVATE_KEY:?set PRIVATE_KEY (a test key) in the environment}"
: "${RPC_URL:?set RPC_URL (see DEPLOY.md §2)}"
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
BROADCAST="--broadcast --slow"
[ "${DRY:-0}" = "1" ] && BROADCAST=""
EXTRA="${FORGE_SCRIPT_FLAGS:-}"   # e.g. "--slow" or "--legacy"

CHAIN=$(cast chain-id --rpc-url "$RPC_URL")
echo "chain id $CHAIN, deployer $(cast wallet address --private-key "$PRIVATE_KEY")"
case "$CHAIN" in
  1|56|196|8453) echo "refusing a mainnet chain id ($CHAIN); this package is for testnets" >&2; exit 1 ;;
esac

cd "$ROOT/contracts"
mkdir -p deployments
forge script script/DeployCore.s.sol:DeployCore --rpc-url "$RPC_URL" $BROADCAST $EXTRA
forge script script/DeployCompanion.s.sol:DeployCompanion --rpc-url "$RPC_URL" $BROADCAST $EXTRA

cd "$ROOT/assets/tap-draft-soulbound-credentials/contracts"
if [ ! -e lib/forge-std ]; then
  mkdir -p lib && ln -sfn ../../../../contracts/lib/forge-std lib/forge-std
fi
mkdir -p deployments
forge script script/DeploySoulbound.s.sol:DeploySoulbound --rpc-url "$RPC_URL" $BROADCAST $EXTRA

echo
echo "Done. Send back (DEPLOY.md §7):"
echo "  $ROOT/contracts/deployments/$CHAIN.json"
echo "  $ROOT/assets/tap-draft-soulbound-credentials/contracts/deployments/$CHAIN.json"
echo "  $ROOT/contracts/broadcast/*/$CHAIN/run-latest.json"
echo "  $ROOT/assets/tap-draft-soulbound-credentials/contracts/broadcast/*/$CHAIN/run-latest.json"
