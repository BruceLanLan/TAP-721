"""Report model of the family checker: one line per displayed fact, each tagged with the TAP section it
implements, rendered as text or JSON (MIT, stdlib only)."""
from __future__ import annotations

import json

# Statuses. "ok" / "fail" are the outcome of a check; "warn" a SHOULD-level finding or a cross-check that
# did not hold; "info" a displayed fact that is not a check; "unverifiable" (TAP-721 §2.5) a netlist in a
# format this tool does not support; "unverified" a fact or claim the tool could not verify (never shown
# as verified); "skip" a check that was not run (no file, no RPC, no fixture entry).
STATUSES = ("ok", "fail", "warn", "info", "unverifiable", "unverified", "skip")

# Short names of the drafts, as they appear in the tags: "TAP-721 §7.2".
T721 = "TAP-721"          # TAP-draft-netlist-bound-nft
TSH = "TAP-SH"            # TAP-draft-netlist-structural-hash
TDC = "TAP-DC"            # TAP-draft-design-credits
TSB = "TAP-SB"            # TAP-draft-soulbound-credentials
TPOD = "TAP-PoD"          # TAP-draft-pod-attributes
TBR = "TAP-BR"            # TAP-draft-netlist-nft-bridging
DRAFTS = {T721: "TAP-draft-netlist-bound-nft", TSH: "TAP-draft-netlist-structural-hash",
          TDC: "TAP-draft-design-credits", TSB: "TAP-draft-soulbound-credentials",
          TPOD: "TAP-draft-pod-attributes", TBR: "TAP-draft-netlist-nft-bridging"}


class Line:
    __slots__ = ("ref", "key", "status", "text", "data")

    def __init__(self, ref: str, key: str, status: str, text: str, data=None):
        if status not in STATUSES:
            raise ValueError(status)
        self.ref, self.key, self.status, self.text, self.data = ref, key, status, text, data

    def as_json(self) -> dict:
        d = {"ref": self.ref, "key": self.key, "status": self.status, "text": self.text}
        if self.data is not None:
            d["data"] = self.data
        return d

    def render(self) -> str:
        return f"[{self.ref}] {self.key}: {self.status} — {self.text}"


class Report:
    def __init__(self, command: str):
        self.command = command
        self.lines = []
        self.result = {}

    def add(self, ref: str, key: str, status: str, text: str, data=None) -> Line:
        ln = Line(ref, key, status, text, data)
        self.lines.append(ln)
        return ln

    # convenience
    def ok(self, ref, key, text, data=None):
        return self.add(ref, key, "ok", text, data)

    def fail(self, ref, key, text, data=None):
        return self.add(ref, key, "fail", text, data)

    def warn(self, ref, key, text, data=None):
        return self.add(ref, key, "warn", text, data)

    def info(self, ref, key, text, data=None):
        return self.add(ref, key, "info", text, data)

    def skip(self, ref, key, text, data=None):
        return self.add(ref, key, "skip", text, data)

    def unverifiable(self, ref, key, text, data=None):
        return self.add(ref, key, "unverifiable", text, data)

    def unverified(self, ref, key, text, data=None):
        return self.add(ref, key, "unverified", text, data)

    def has(self, key: str, status: str = None) -> bool:
        return any(l.key == key and (status is None or l.status == status) for l in self.lines)

    def get(self, key: str):
        for l in self.lines:
            if l.key == key:
                return l
        return None

    @property
    def failed(self) -> bool:
        return any(l.status == "fail" for l in self.lines)

    def counts(self) -> dict:
        c = {s: 0 for s in STATUSES}
        for l in self.lines:
            c[l.status] += 1
        return c

    def as_json(self) -> dict:
        return {"format": "tap-family-checker-report/1", "command": self.command, "result": self.result,
                "counts": self.counts(), "lines": [l.as_json() for l in self.lines]}

    def render(self) -> str:
        out = [f"# tapfam {self.command}"]
        out += [l.render() for l in self.lines]
        c = self.counts()
        out.append("# " + ", ".join(f"{k} {v}" for k, v in c.items() if v))
        out.append("# verdict: " + ("INVALID (a MUST-level check failed)" if self.failed else "no MUST-level failure"))
        return "\n".join(out)

    def dumps(self, as_json: bool) -> str:
        return json.dumps(self.as_json(), indent=1, ensure_ascii=False) if as_json else self.render()
