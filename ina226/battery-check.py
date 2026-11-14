#!/usr/bin/env python3
"""
battery-check.py - one-command health check of a station's power system
Version 1.0 - 2026-11-14

Changes:
  1.0  First release

Reads what battery_monitor.py (battery.service) already produces - the
latest reading in /dev/shm/battery_now.json and the once-a-minute log
battery_log.csv - and checks the Pi's 5 V supply. Nothing extra has to
run: the battery monitor logs around the clock, so a check can cover any
period up to the length of the log.

Sign convention (same as battery_monitor.py and the APRS telemetry):
  + amps = charging,  - amps = discharging (load)

Usage:
  battery-check.py              last 24 hours
  battery-check.py --hours 6    last 6 hours
  battery-check.py --log FILE   use a different battery_log.csv

Exit status 0 when every check passes, 1 when something needs a look.

Scott Sheppard, KJ4ZZB
https://github.com/sonoaltercocker/Scott-weewx-aprs
"""

import csv
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timedelta

VERSION = "1.0"

STATUS_FILE = "/dev/shm/battery_now.json"
LOG_CANDIDATES = [                       # newest one wins
    "/data/battery/battery_log.csv",     # station build with a /data partition
    os.path.expanduser("~/battery_log.csv"),
    "/home/pi/battery_log.csv",
    "/tmp/battery_log.csv",              # battery_monitor.py read-only fallback
]
STALE_S = 120            # latest reading older than this = monitor not running
GAP_S = 300              # log gap longer than this = monitor stopped for a while
MIN_V = 12.5             # lowest battery voltage that still passes
NET_LIMIT = 0.10         # net loss per day, as a share of capacity, that still passes
MAX_STEP_H = GAP_S / 3600.0


# ------------------------------------------------------------------ helpers
def ok(msg):    print(f"  PASS   {msg}")
def bad(msg):   print(f"  CHECK  {msg}")
def info(msg):  print(f"         {msg}")


def run(cmd):
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=10).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def find_log(explicit):
    if explicit:
        return explicit if os.path.exists(explicit) else None
    found = [p for p in dict.fromkeys(LOG_CANDIDATES) if os.path.exists(p)]
    return max(found, key=os.path.getmtime) if found else None


def read_log(path, since):
    rows = []
    with open(path, newline="") as f:
        for r in csv.DictReader(f):
            try:
                t = datetime.fromisoformat(r["timestamp"])
                if t >= since:
                    rows.append((t, float(r["volts"]), float(r["amps"]), float(r["soc_pct"])))
            except (KeyError, ValueError, TypeError):
                pass                       # skip a damaged or header line
    return rows


# ------------------------------------------------------------------ checks
def check_monitor():
    print("Battery monitor")
    state = run(["systemctl", "is-active", "battery"])
    passed = state == "active"
    (ok if passed else bad)(f"battery.service is {state or 'not found'}")
    if not passed:
        info("start it:  sudo systemctl start battery   (log: sudo journalctl -u battery -n 20)")
    try:
        s = json.load(open(STATUS_FILE))
        age = time.time() - s["time"]
        fresh = age <= STALE_S
        (ok if fresh else bad)(f"latest reading {age:.0f} s old")
        state = "charging" if s["amps"] > 0.05 else "discharging" if s["amps"] < -0.05 else "idle"
        info(f"now: {s['volts']:.2f} V  {s['amps']:+.3f} A  {s['watts']:+.2f} W  "
             f"SoC {s['soc']:.0f}% ({s['ah']:.2f} of {s['capacity_ah']:g} Ah)  {state}")
        return passed and fresh, s.get("capacity_ah")
    except (OSError, ValueError, KeyError):
        bad(f"no current reading in {STATUS_FILE}")
        return False, None


def check_supply():
    print("Pi 5 V supply")
    out = run(["vcgencmd", "get_throttled"])
    if "=" not in out:
        bad("vcgencmd not available - can't read the undervoltage flags")
        return False
    flags = int(out.split("=")[1], 16)
    boot = run(["uptime", "-s"])
    since = f"since boot ({boot})" if boot else "since boot"
    if flags & 0x1:
        bad(f"{out}: UNDERVOLTAGE NOW")
    elif flags & 0x10000:
        bad(f"{out}: undervoltage has happened {since}")
    else:
        ok(f"{out}: no undervoltage {since}")
        return True
    info("raise the 5 V converter to 5.1-5.2 V, use a shorter or thicker lead,")
    info("or a converter with more current (5 A)")
    return False


def check_log(path, hours, capacity):
    print(f"Last {hours:g} hours")
    if not path:
        bad("no battery_log.csv found - is the battery monitor installed?")
        return False
    rows = read_log(path, datetime.now() - timedelta(hours=hours))
    info(f"log: {path}")
    if len(rows) < 2:
        bad("not enough log rows in this period")
        return False

    covered = (rows[-1][0] - rows[0][0]).total_seconds() / 3600.0
    ah_in = ah_out = 0.0
    longest_gap = 0.0
    for (t1, _, a1, _), (t2, _, a2, _) in zip(rows, rows[1:]):
        step_h = (t2 - t1).total_seconds() / 3600.0
        longest_gap = max(longest_gap, step_h)
        if step_h > MAX_STEP_H:            # monitor was off - don't guess
            continue
        a = (a1 + a2) / 2
        if a > 0:
            ah_in += a * step_h
        else:
            ah_out -= a * step_h
    net = ah_in - ah_out
    vmin = min(rows, key=lambda r: r[1])
    vmax = max(rows, key=lambda r: r[1])
    peak = min(rows, key=lambda r: r[2])   # largest discharge (most negative)
    socs = [r[3] for r in rows]

    info(f"{len(rows)} readings covering {covered:.1f} h")
    info(f"voltage   min {vmin[1]:.3f} V ({vmin[0]:%m-%d %H:%M})   "
         f"max {vmax[1]:.3f} V ({vmax[0]:%m-%d %H:%M})")
    info(f"charge    in {ah_in:.2f} Ah   out {ah_out:.2f} Ah   net {net:+.2f} Ah")
    info(f"SoC       start {socs[0]:.0f}%   end {socs[-1]:.0f}%   lowest {min(socs):.0f}%")
    info(f"peak load {peak[2]:+.2f} A at {peak[0]:%m-%d %H:%M} (radio transmit, if well above normal)")

    passed = True
    if covered < 0.8 * hours:
        bad(f"log covers only {covered:.1f} of {hours:g} h - let it run longer for a full check")
        passed = False
    if longest_gap * 3600 > GAP_S:
        bad(f"monitor stopped for {longest_gap * 60:.0f} min at one point (reboot or power loss?)")
        passed = False
    else:
        ok("no gaps in the log")
    if vmin[1] < MIN_V:
        bad(f"battery fell to {vmin[1]:.2f} V (below {MIN_V} V)")
        passed = False
    else:
        ok(f"battery stayed above {MIN_V} V")
    if capacity and covered >= 20:
        per_day = net * 24 / covered
        if per_day < -NET_LIMIT * capacity:
            bad(f"net {per_day:+.2f} Ah per day - charging is not keeping up with the load")
            passed = False
        else:
            ok(f"net {per_day:+.2f} Ah per day - charging keeps up with the load")
    elif covered < 20:
        info("daily balance needs about 24 h of log to judge")
    return passed


# ------------------------------------------------------------------ main
def main():
    args = sys.argv[1:]
    if "-h" in args or "--help" in args:
        print(__doc__.strip()); return 0
    if "--version" in args:
        print(f"battery-check.py {VERSION}"); return 0
    hours, log = 24.0, None
    try:
        if "--hours" in args:
            hours = float(args[args.index("--hours") + 1])
        if "--log" in args:
            log = args[args.index("--log") + 1]
    except (IndexError, ValueError):
        sys.exit("usage: battery-check.py [--hours N] [--log FILE]")

    print(f"Power system check  {datetime.now():%Y-%m-%d %H:%M}  (battery-check {VERSION})")
    print("  + amps = charging,  - amps = discharging\n")
    m, capacity = check_monitor(); print()
    s = check_supply(); print()
    l = check_log(find_log(log), hours, capacity); print()
    if m and s and l:
        print("All checks passed.")
        return 0
    print("Something needs a look - see the CHECK lines above.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
