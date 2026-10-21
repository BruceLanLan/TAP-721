"""Import paths for the TAP-721 family checker (stdlib only, MIT).

Puts the reference implementations of the family on sys.path and imports them unchanged. Nothing from
those modules is reimplemented here: every rule the checker applies is a call into one of them.

  tapnft      TAP-721 core (assets/tap-draft-netlist-bound-nft): files, manifests, reveal, metadata, editions
  canon       structural hash version 1 (assets/tap-draft-netlist-structural-hash)
  canon2      structural hash version 2 (tapnet/1 and tapnet/2 files), with tapnet2 from the same folder
  credits     design credits: keccak-256, EIP-712, envelopes, publication facts, earliest statements, display order
  soulbound   soulbound credentials: metadata check, display labels, statements carried by claims
  pod_validate  PoD attributes (imported lazily: it needs pycryptodome through pod_snapshot)
"""
from __future__ import annotations

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, "..", ".."))
ASSETS = os.path.join(ROOT, "assets")
TAPNFT_DIR = os.path.join(ASSETS, "tap-draft-netlist-bound-nft")
CANON_DIR = os.path.join(ASSETS, "tap-draft-netlist-structural-hash")
CREDITS_DIR = os.path.join(ASSETS, "tap-draft-design-credits")
SOULBOUND_DIR = os.path.join(ASSETS, "tap-draft-soulbound-credentials")
POD_DIR = os.path.join(ASSETS, "tap-draft-pod-attributes")
BRIDGING_DIR = os.path.join(ASSETS, "tap-draft-netlist-nft-bridging")

# The order matters: canon.py and credits.py import `tapnft` and `tap02_reference`; soulbound.py imports
# `canon`, `credits` and `tapnft`. Each asset folder holds byte-identical copies of the modules it needs, so
# the first folder on the path that defines a name wins and every folder agrees.
for _d in (TAPNFT_DIR, CANON_DIR, CREDITS_DIR, SOULBOUND_DIR):
    if _d not in sys.path:
        sys.path.append(_d)

import tapnft  # noqa: E402
import tap02_reference as tap02  # noqa: E402
import canon  # noqa: E402
import canon2  # noqa: E402
import tapnet2  # noqa: E402
import credits  # noqa: E402
import soulbound  # noqa: E402

keccak256 = credits.keccak256

FIXTURE_FILE = os.path.join(HERE, "fixtures", "recorded-rpc.json")


def pod_validate():
    """Lazy import of the PoD validator (pod_validate.py needs pycryptodome through pod_snapshot.py).
    Returns the module, or None when it cannot be imported."""
    if POD_DIR not in sys.path:
        sys.path.append(POD_DIR)
    try:
        import pod_validate as pv  # noqa: WPS433
    except ImportError:
        return None
    return pv
