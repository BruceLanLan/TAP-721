#!/usr/bin/env python3
"""Generate test/fixtures/drand-beacon-code.json: the canonical runtime code of DrandBeacon.

MIT licence. Run from anywhere (needs `forge` and `cast` on PATH):

    python3 contracts/test/fixtures/make_drand_beacon_code.py          # writes the file next to this script
    python3 contracts/test/fixtures/make_drand_beacon_code.py --check  # fails if the committed file differs

Why a fixture. TapDrandReveal pins the beacon by address (0x777D...55Ca, a CREATE2 address) and by code hash. Both
hold only for the repository's own build recipe (solc 0.8.28, 10,000 runs, EVM shanghai, no metadata; foundry.toml).
`forge test --evm-version prague` recompiles every contract for Prague, which changes the bytes (5,841 bytes become
5,819) and so the code hash. The BLS tests need Prague's EIP-2537 precompiles, so they install this recorded runtime
at the canonical beacon address instead of the freshly compiled one. DrandCanonical.t.sol asserts, under the
repository recipe, that the fixture is byte-identical to the compiled contract, so it cannot drift. (With Foundry's
`--hardfork prague` the contracts stay compiled for shanghai and the precompiles still exist.)
"""
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
CONTRACTS = os.path.abspath(os.path.join(HERE, "..", ".."))
OUT = os.path.join(HERE, "drand-beacon-code.json")


def run(*args):
    return subprocess.run(args, cwd=CONTRACTS, check=True, capture_output=True, text=True).stdout.strip()


def build():
    # forge inspect uses foundry.toml, i.e. the repository recipe, whatever the caller's FOUNDRY_* variables say
    env_evm = os.environ.pop("FOUNDRY_EVM_VERSION", None)
    runtime = run("forge", "inspect", "DrandBeacon", "deployedBytecode")
    if env_evm is not None:
        os.environ["FOUNDRY_EVM_VERSION"] = env_evm
    if not runtime.startswith("0x"):
        raise SystemExit("unexpected forge output: " + runtime[:80])
    return {
        "recipe": "solc 0.8.28, optimizer 10000 runs, evm shanghai, bytecode_hash none, cbor_metadata false",
        "DrandBeacon": {
            "size": (len(runtime) - 2) // 2,
            "runtimeKeccak": run("cast", "keccak", runtime),
            "runtime": runtime,
        },
    }


def main():
    doc = build()
    text = json.dumps(doc, indent=1) + "\n"
    if "--check" in sys.argv:
        with open(OUT, "r", encoding="utf-8") as f:
            if f.read() != text:
                raise SystemExit("drand-beacon-code.json differs from the compiled DrandBeacon")
        print("drand-beacon-code.json up to date")
        return
    with open(OUT, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    print("wrote", OUT, doc["DrandBeacon"]["size"], "bytes", doc["DrandBeacon"]["runtimeKeccak"])


if __name__ == "__main__":
    main()
