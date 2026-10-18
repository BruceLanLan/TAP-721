#!/usr/bin/env python3
"""End-to-end test of tapup on a local anvil fork of X Layer. Sends nothing to a live chain.

    python3 test_e2e.py [--keep-anvil] [--work DIR]

Starts `anvil --fork-url https://rpc.xlayer.tech --hardfork cancun` on a free port, impersonates the holder of
container 0xa8ed…6b9 (circuit #1 of processor 0x8E0b…60cF), and runs plan -> operator set -> upload (killed
with SIGKILL mid-way, then resumed) -> verify -> tamper/replace -> revert handling -> operator clear ->
lock-checklist (with a TapContainerLock deployed on the fork). Prints measured gas per file size.
"""
import argparse
import hashlib
import json
import os
import random
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import ethcrypto  # noqa: E402
import tapup  # noqa: E402

FORK = "https://rpc.xlayer.tech"
CONTAINER = "0xa8Edd3B032D33aA0657a3E151a7f8c3e5F71F6B9"
HOLDER = "0x1183a1a0f98Dd2eF8f66895C6811bbf43032843e"
PROC = "0x8E0bb87998a9239daa79551ef7dbf78C9b0C60cF"
STORE = tapup.CHAINS[196]["store"]
BINDING = tapup.CHAINS[196]["binding"]
NAME = "1.2.282.tape"
OPENER = tapup.CHAINS[196]["opener"]
CONTRACTS = os.path.normpath(os.path.join(HERE, "..", "..", "contracts"))  # read-only: source of TapContainerLock.sol

PASS = []


def ok(cond, msg):
    print(("  PASS " if cond else "  FAIL ") + msg)
    if not cond:
        raise SystemExit("test failed: " + msg)
    PASS.append(msg)


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def run(args, env_key=None, expect=0, quiet=False):
    env = {k: v for k, v in os.environ.items() if k != "TAPUP_PRIVATE_KEY"}
    if env_key:
        env["TAPUP_PRIVATE_KEY"] = env_key
    r = subprocess.run([sys.executable, os.path.join(HERE, "tapup.py")] + args, env=env, stdout=subprocess.PIPE,
                       stderr=subprocess.STDOUT, text=True)
    if not quiet:
        print("    $ tapup " + " ".join(args[:3]) + " ...  (exit %d)" % r.returncode)
        for line in r.stdout.strip().splitlines()[-14:]:
            print("      " + line)
    if expect is not None and r.returncode != expect:
        print(r.stdout)
        raise SystemExit("unexpected exit %d (wanted %d) for %s" % (r.returncode, expect, args))
    return r


def gen_files(root):
    rnd = random.Random(282)
    os.makedirs(os.path.join(root, "meta"))
    os.makedirs(os.path.join(root, "img"))
    os.makedirs(os.path.join(root, "net"))
    for i in range(1, 21):  # extensionless JSON
        meta = {"name": "TapeCode-Test1 #%d" % i, "image": "tape://img/%d.png" % i,
                "attributes": [{"trait_type": "seed", "value": rnd.randrange(10 ** 9)}] * rnd.randrange(1, 6)}
        with open(os.path.join(root, "meta", str(i)), "w") as f:
            json.dump(meta, f)
    with open(os.path.join(root, "meta", "README"), "w") as f:  # extensionless, not JSON
        f.write("not json\n")
    sizes = [10, 1000, 4000, 12000, 23999, 24000, 24001, 30000, 48000, 50000, 72001, 100000, 150000, 2000, 6000]
    for i, n in enumerate(sizes, 1):
        with open(os.path.join(root, "img", "%d.png" % i), "wb") as f:
            f.write(b"\x89PNG\r\n\x1a\n" + bytes(rnd.getrandbits(8) for _ in range(max(0, n - 8))))
    for i in range(1, 13):
        n = rnd.choice([16 + 7 * rnd.randrange(1, 300), 16 + 7 * rnd.randrange(3000, 5000)])
        with open(os.path.join(root, "net", "%d.tapnet" % i), "wb") as f:
            f.write(b"TAPNET\x01\x00" + bytes(rnd.getrandbits(8) for _ in range(n - 8)))
    open(os.path.join(root, "empty.txt"), "wb").close()
    with open(os.path.join(root, ".DS_Store"), "wb") as f:  # hidden: must be skipped
        f.write(b"junk")


def journal(path):
    with open(path) as f:
        return [json.loads(x) for x in f if x.strip()]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--keep-anvil", action="store_true")
    ap.add_argument("--work")
    a = ap.parse_args()
    work = a.work or tempfile.mkdtemp(prefix="tapup-e2e-")
    if os.path.exists(work):
        shutil.rmtree(work)
    os.makedirs(work)
    site = os.path.join(work, "site")
    gen_files(site)

    port = free_port()
    url = "http://127.0.0.1:%d" % port
    anvil = subprocess.Popen(["anvil", "--fork-url", FORK, "--port", str(port), "--hardfork", "cancun",
                              "--gas-limit", "210000000", "--silent"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        rpc = tapup.RPC(url, retries=2)
        for _ in range(60):
            try:
                rpc.call("eth_blockNumber")
                break
            except Exception:
                time.sleep(0.5)
        print("anvil fork on %s at block %d (work dir %s)" % (url, int(rpc.call("eth_blockNumber"), 16), work))
        ok(tapup.is_anvil(rpc), "node is anvil")
        rpc.call("anvil_impersonateAccount", HOLDER)
        rpc.call("anvil_setBalance", HOLDER, hex(10 ** 20))
        hot = "0x" + os.urandom(32).hex()
        hot_addr = ethcrypto.address_of(int(hot, 16))
        rpc.call("anvil_setBalance", hot_addr, hex(10 ** 20))
        base = ["--rpc", url]
        plan = os.path.join(work, "plan.json")
        jr = os.path.join(work, "journal.jsonl")

        print("\n[1] plan")
        r = run(base + ["plan", site, "--container", CONTAINER, "--prefix", "t1", "--out", plan, "-v"])
        p = json.load(open(plan))
        files = p["files"]
        ok(len(files) == 49, "49 files planned, hidden file skipped (got %d)" % len(files))
        ok(all(f["status"] == "new" for f in files), "all files are new")
        ct = {f["path"]: f["contentType"] for f in files}
        ok(ct["t1/meta/7"] == "application/json" and ct["t1/meta/README"] == "application/octet-stream",
           "extensionless JSON -> application/json, extensionless text -> octet-stream")
        ok(ct["t1/img/3.png"] == "image/png" and ct["t1/empty.txt"].startswith("text/plain"), "content types by extension")
        ok(max(f["chunks"] for f in files) == 7, "150,000-byte file needs 7 chunks")
        total_tx = sum(f["chunks"] for f in files)

        print("\n[2] operator set (holder impersonated) -> hot wallet %s" % hot_addr)
        run(base + ["operator", "set", "--container", CONTAINER, "--op", hot_addr, "--ttl", "3600", "--unlocked", HOLDER, "--yes"])
        run(base + ["operator", "set", "--container", CONTAINER, "--op", hot_addr, "--ttl", "9999999", "--unlocked", HOLDER,
                    "--yes"], expect=1)
        ok(True, "TTL above 30 days refused locally")
        run(base + ["operator", "set", "--container", CONTAINER, "--op", hot_addr, "--ttl", "3600", "--yes"], env_key=hot, expect=1)
        ok(True, "operator set from a non-holder key refused")
        s = tapup.Site(rpc, STORE, CONTAINER)
        ok(s.can_edit(hot_addr), "hot wallet can edit")

        print("\n[3] safety refusals")
        r = run(base + ["upload", "--plan", plan, "--journal", jr, "--yes", "--unlocked", HOLDER], expect=2)
        ok("unrecognized arguments: --unlocked" in r.stdout, "upload has no --unlocked mode (needs a key)")
        r = run(base + ["upload", "--plan", plan, "--journal", jr, "--yes"], expect=1)
        ok("TAPUP_PRIVATE_KEY" in r.stdout, "upload refuses without a key in the environment")

        print("\n[4] deterministic partial upload (stop after the first chunk of a 7-chunk file), then resume")
        r = run(base + ["upload", "--plan", plan, "--journal", jr, "--yes", "--only", "img/13\\.png$", "--max-tx", "1"],
                env_key=hot, expect=4)
        fi = s.file_info_many(["t1/img/13.png"])[0]
        ok(fi["chunkCount"] == 1 and fi["size"] == 24000, "on-chain: 1 chunk, size 24000 (size counts uploaded bytes)")
        r = run(base + ["plan", site, "--container", CONTAINER, "--prefix", "t1", "--out", plan])
        ok("partial 1" in r.stdout, "plan reports the file as partial")

        print("\n[5] upload with interval mining; SIGKILL mid-way")
        rpc.call("evm_setAutomine", False)
        rpc.call("evm_setIntervalMining", 1)
        env = {k: v for k, v in os.environ.items()}
        env["TAPUP_PRIVATE_KEY"] = hot
        proc = subprocess.Popen([sys.executable, os.path.join(HERE, "tapup.py")] + base +
                                ["upload", "--plan", plan, "--journal", jr, "--yes", "--concurrency", "6", "--poll", "1",
                                 "--progress", "10"], env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        del env
        t0 = time.time()
        while time.time() - t0 < 120:
            js = journal(jr)
            if sum(1 for e in js if e["t"] == "mined") >= 20 and tapup.Journal(jr).unresolved():
                break
            time.sleep(0.05)
        proc.send_signal(signal.SIGKILL)
        proc.wait()
        js = journal(jr)
        sent = [e for e in js if e["t"] == "sent"]
        mined = [e for e in js if e["t"] == "mined"]
        pend = tapup.Journal(jr).unresolved()
        print("    killed: %d sent, %d mined in journal, %d unresolved" % (len(sent), len(mined), len(pend)))
        ok(len(pend) > 0, "kill left journaled tx without a recorded outcome")
        ok(int(rpc.call("eth_getTransactionCount", hot_addr, "pending"), 16) >
           int(rpc.call("eth_getTransactionCount", hot_addr, "latest"), 16) or True, "(tx may still be in the pool)")

        print("\n[6] resume")
        r = run(base + ["upload", "--plan", plan, "--journal", jr, "--yes", "--concurrency", "6", "--poll", "1",
                        "--progress", "20"], env_key=hot)
        ok("reconciling" in r.stdout, "resume reconciled the journal first")
        js = journal(jr)
        good = [(e["path"], e["chunk"]) for e in js if e["t"] == "mined" and e["status"] == 1]
        ok(len(good) == len(set(good)), "no chunk was mined twice (%d successful tx)" % len(good))
        ok(len(good) == total_tx, "successful tx == total chunks (%d)" % total_tx)
        rpc.call("evm_setIntervalMining", 0)
        rpc.call("evm_setAutomine", True)
        r = run(base + ["upload", "--plan", plan, "--journal", jr, "--yes"], env_key=hot)
        ok("nothing to upload" in r.stdout, "a third run sends nothing")

        print("\n[7] verify")
        rep = os.path.join(work, "verify.json")
        r = run(base + ["verify", "--plan", plan, "--report", rep])
        ok(json.load(open(rep))["failed"] == 0, "verify: all 49 files match (size + SHA-256 of bytes read back)")

        print("\n[8] tamper on chain -> verify fails -> plan says replace -> upload fixes")
        bad = b"tampered"
        h = rpc.call("eth_sendTransaction", {"from": HOLDER, "to": STORE, "gas": hex(500000), "data": tapup.calldata(
            "putFile(address,string,string,bytes32,bytes)", ["address", "string", "string", "bytes32", "bytes"],
            [CONTAINER, "t1/meta/3", "application/json", "0x" + hashlib.sha256(bad).hexdigest(), bad])})
        while not rpc.call("eth_getTransactionReceipt", h):
            time.sleep(0.2)
        r = run(base + ["verify", "--plan", plan], expect=1)
        ok("FAIL t1/meta/3" in r.stdout, "verify reports the tampered file and exits 1")
        r = run(base + ["plan", site, "--container", CONTAINER, "--prefix", "t1", "--out", plan])
        ok("replace 1" in r.stdout and "skip 48" in r.stdout, "plan: 1 replace, 48 skip")
        run(base + ["upload", "--plan", plan, "--journal", jr, "--yes"], env_key=hot)
        run(base + ["verify", "--plan", plan])

        print("\n[9] journal/plan mismatch refusals")
        p2 = json.load(open(plan))
        p2["container"] = "0x" + "11" * 20
        plan2 = os.path.join(work, "plan-other.json")
        json.dump(p2, open(plan2, "w"))
        r = run(base + ["upload", "--plan", plan2, "--journal", jr, "--yes"], env_key=hot, expect=1)
        ok("refusing" in r.stdout and "container" in r.stdout, "journal made for another container is refused")
        p2 = json.load(open(plan))
        p2["anvil"] = False
        json.dump(p2, open(plan2, "w"))
        r = run(base + ["upload", "--plan", plan2, "--journal", jr, "--yes"], env_key=hot, expect=1)
        ok("re-run plan here" in r.stdout, "plan made on a live node is refused on anvil (and vice versa)")

        print("\n[9b] keystore signer (cast wallet decrypt-keystore, password from env only because --allow-env-password)")
        ks = os.path.join(work, "keystore")
        os.makedirs(ks)
        r = subprocess.run(["cast", "wallet", "new", ks, "--unsafe-password", "e2e-throwaway"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        ks_addr = next(l.split()[-1] for l in r.stdout.splitlines() if "Address" in l)
        ks_name = os.listdir(ks)[0]
        env = dict(os.environ, CAST_UNSAFE_PASSWORD="e2e-throwaway")
        r = subprocess.run([sys.executable, os.path.join(HERE, "tapup.py")] + base + [
            "upload", "--plan", plan, "--journal", os.path.join(work, "j-ks.jsonl"), "--yes", "--keystore-account", ks_name,
            "--keystore-dir", ks, "--allow-env-password"], env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        ok(r.returncode == 1 and ks_addr in r.stdout and "cannot edit" in r.stdout,
           "keystore key loaded (address %s) and the non-operator is refused before sending" % ks_addr)

        print("\n[10] revert mid-upload: holder clears the operator while txs are in flight")
        more = os.path.join(work, "site2")
        os.makedirs(more)
        for i in range(12):
            with open(os.path.join(more, "f%02d.bin" % i), "wb") as f:
                f.write(os.urandom(30000))
        plan3 = os.path.join(work, "plan3.json")
        jr3 = os.path.join(work, "journal3.jsonl")
        run(base + ["plan", more, "--container", CONTAINER, "--prefix", "t1b", "--out", plan3])
        rpc.call("evm_setAutomine", False)
        rpc.call("evm_setIntervalMining", 1)
        env = dict(os.environ, TAPUP_PRIVATE_KEY=hot)
        proc = subprocess.Popen([sys.executable, os.path.join(HERE, "tapup.py")] + base +
                                ["upload", "--plan", plan3, "--journal", jr3, "--yes", "--concurrency", "4", "--poll", "1"],
                                env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        del env
        t0 = time.time()
        while time.time() - t0 < 60:
            if os.path.exists(jr3) and sum(1 for e in journal(jr3) if e["t"] == "mined") >= 3:
                break
            time.sleep(0.2)
        rpc.call("eth_sendTransaction", {"from": HOLDER, "to": STORE, "gas": hex(200000), "maxPriorityFeePerGas": hex(10 ** 9),
                                         "maxFeePerGas": hex(10 ** 10), "data": tapup.calldata(
            "setOperator(address,address,uint256)", ["address", "address", "uint256"], [CONTAINER, tapup.ZERO, 0])})
        out, _ = proc.communicate(timeout=120)
        print("      " + "\n      ".join(out.strip().splitlines()[-4:]))
        ok(proc.returncode == 2 and "REVERTED" in out, "upload stops with exit 2 and names the reverted tx")
        rpc.call("evm_setIntervalMining", 0)
        rpc.call("evm_setAutomine", True)
        r = run(base + ["upload", "--plan", plan3, "--journal", jr3, "--yes"], env_key=hot, expect=2)
        ok("--ack-reverts" in r.stdout, "re-run refuses until the reverts are acknowledged")
        r = run(base + ["upload", "--plan", plan3, "--journal", jr3, "--yes", "--ack-reverts"], env_key=hot, expect=1)
        ok("cannot edit" in r.stdout, "without the operator, upload refuses before sending anything")
        run(base + ["operator", "set", "--container", CONTAINER, "--op", hot_addr, "--ttl", "3600", "--unlocked", HOLDER, "--yes"])
        run(base + ["upload", "--plan", plan3, "--journal", jr3, "--yes"], env_key=hot)
        run(base + ["verify", "--plan", plan3])

        print("\n[11] measured gas (from journal receipts)")
        rows = {}
        for e in journal(jr) + journal(jr3):
            if e["t"] == "mined" and e["status"] == 1 and "bytes" in e:
                kind = "putFile" if e["chunk"] == 0 else "appendChunk"
                rows.setdefault(kind, []).append((e["bytes"], e["gasUsed"]))
        for kind, pts in rows.items():
            n = len(pts)
            mx = sum(x for x, _ in pts) / n
            my = sum(y for _, y in pts) / n
            sxx = sum((x - mx) ** 2 for x, _ in pts)
            slope = sum((x - mx) * (y - my) for x, y in pts) / sxx if sxx else 0
            print("    %-11s n=%3d  gas ≈ %7.0f + %6.1f × bytes" % (kind, n, my - slope * mx, slope))
            for x, y in sorted(set(pts))[:: max(1, n // 8)]:
                print("        %6d B -> %9d gas" % (x, y))

        print("\n[12] operator clear, lock-checklist")
        run(base + ["operator", "clear", "--container", CONTAINER, "--unlocked", HOLDER, "--yes"])
        ok(s.operator()[0].lower() == tapup.ZERO, "operatorOf == 0 after clear")
        # deploy a TapContainerLock on the fork
        # compile a copy in the work dir so the shared contracts/ out/ and cache/ are never touched
        fp = os.path.join(work, "lockproj")
        os.makedirs(os.path.join(fp, "src"))
        shutil.copy(os.path.join(CONTRACTS, "src", "tools", "TapContainerLock.sol"), os.path.join(fp, "src"))
        with open(os.path.join(fp, "foundry.toml"), "w") as f:
            f.write('[profile.default]\nsrc = "src"\nout = "out"\nsolc_version = "0.8.28"\nevm_version = "cancun"\n')
        r = subprocess.run(["forge", "create", "src/TapContainerLock.sol:TapContainerLock", "--root", fp, "--rpc-url", url,
                            "--unlocked", "--from", HOLDER, "--broadcast",
                            "--constructor-args", PROC, "1", CONTAINER, OPENER, BINDING, NAME],
                           cwd=fp, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        if "Deployed to:" not in r.stdout:
            print(r.stdout[-2000:])
        lock = next((l.split()[-1] for l in r.stdout.splitlines() if "Deployed to:" in l), None)
        ok(lock is not None, "TapContainerLock deployed on the fork at %s" % lock)
        r = run(base + ["lock-checklist", "--container", CONTAINER, "--name", NAME, "--lock", lock])
        ok("checklist: PASS" in r.stdout, "lock-checklist passes")
        cmds = [l.strip() for l in r.stdout.splitlines() if l.strip().startswith("cast send")]
        ok(len(cmds) == 2 and "safeTransferFrom" in cmds[-1], "prints bind + safeTransferFrom commands (operator already clear)")
        # dry-run the printed commands on the fork (replace --account/--rpc-url with the impersonated holder)
        for c in cmds:
            c = c.split(" --rpc-url ")[0]
            argv = [x.strip("'") for x in c.split(" ")] + ["--rpc-url", url, "--unlocked", "--from", HOLDER]
            rr = subprocess.run(argv, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            ok(rr.returncode == 0, "fork-executed: %s" % " ".join(argv[2:4]))
        locked = tapup.dec(["bool"], rpc.eth_call(lock, "0x" + tapup.sel("locked()").hex()))[0]
        ok(locked, "lock.locked() == true after the printed commands (on the fork)")
        r = run(base + ["operator", "set", "--container", CONTAINER, "--op", hot_addr, "--unlocked", HOLDER, "--yes"], expect=1)
        ok("not the circuit holder" in r.stdout, "after locking, the old holder can no longer set an operator")
        print("\nALL %d CHECKS PASSED" % len(PASS))
    finally:
        if a.keep_anvil:
            print("anvil left running on %s (pid %d)" % (url, anvil.pid))
        else:
            anvil.terminate()
            anvil.wait()


if __name__ == "__main__":
    main()
