"""Rerun scripts/build_facility_service.py while sentence tagging progresses.

Runs the build each time 3 new chunk lines appear in reports/sentence_tagging/chunks.jsonl,
and once more after the tagging process (PID given on the command line) exits; then exits.
Never touches the tagging process. A failed build is logged and watching continues.

Start (detached):
  nohup /opt/homebrew/Caskroom/miniconda/base/envs/py13/bin/python scripts/rebuild_watcher.py 97730 \
    >> reports/rebuild_watcher.log 2>&1 &
"""
import os
import subprocess
import sys
import time
from datetime import datetime, timezone

ROOT = "/Users/yusufakin/CMU/datathon"
CHUNKS = f"{ROOT}/reports/sentence_tagging/chunks.jsonl"
BUILD = [sys.executable, f"{ROOT}/scripts/build_facility_service.py"]
EVERY = 3        # new chunk lines per rebuild
POLL_S = 30


def log(msg):
    print(f"{datetime.now(timezone.utc).isoformat(timespec='seconds')} {msg}", flush=True)


def n_lines():
    try:
        with open(CHUNKS) as f:
            return sum(1 for line in f if line.strip())
    except FileNotFoundError:
        return 0


def alive(pid):
    try:
        os.kill(pid, 0)          # signal 0: existence check only, sends nothing
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def build(reason):
    log(f"BUILD start ({reason})")
    t0 = time.time()
    try:
        p = subprocess.run(BUILD, cwd=ROOT, capture_output=True, text=True, timeout=1800)
        tail = [l for l in p.stdout.splitlines() if l.startswith(("{", "[", "build", "demoted", "added"))]
        for l in tail:
            log(f"  {l}")
        if p.returncode != 0:
            err = [l for l in (p.stderr or "").splitlines() if l.strip()][-5:]
            log(f"BUILD FAILED rc={p.returncode} secs={time.time()-t0:.0f}: " + " | ".join(err))
        else:
            log(f"BUILD ok secs={time.time()-t0:.0f}")
    except Exception as e:
        log(f"BUILD FAILED {type(e).__name__}: {e}")


def main():
    pid = int(sys.argv[1])
    last = n_lines()
    log(f"watcher start pid={os.getpid()} tagging_pid={pid} chunk_lines={last}")
    while alive(pid):
        time.sleep(POLL_S)
        n = n_lines()
        if n >= last + EVERY:
            build(f"chunk lines {last} -> {n}")
            last = n
    log(f"tagging pid {pid} exited; final build")
    build("tagging finished")
    log("watcher exit")


if __name__ == "__main__":
    main()
