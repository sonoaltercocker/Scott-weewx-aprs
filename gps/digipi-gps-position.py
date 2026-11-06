#!/usr/bin/env python3
"""
digipi-gps-position.py  -  keep DigiPi's station position in step with a GPS

Version 1.3  -  Scott Sheppard, KJ4ZZB

DigiPi's Initialize step copies the latitude, longitude and grid square you
type in into a dozen config files, once.  This script runs at every boot
afterwards (from digipi-gps-position.service), asks gpsd for a fix, and if the
station has moved it rewrites those same settings with the GPS position:

  Lat/lon   direwolf*.conf (PBEACON lines), aprsd.conf,
            direwolf-dashboard config.yaml, localize.env (direwatch display)
  Grid      Pat config.json, RMS gateway gateway.conf / sysop.xml /
            channels.xml, WSJT-X.ini and JS8Call.ini (4-character grid)
  WeeWX     [Station] latitude, longitude and altitude in weewx.conf
            (only if WeeWX is installed; without WeeWX this step is skipped)

Settings are found by their names (lat=, latitude =, MyGrid= ...), not by
searching for the old values, so it keeps working however many times the
station moves.  NEWLAT/NEWLON/NEWGRID and the matching OLD... lines in
localize.env are set to the new position, so localize.env always describes
what is really in the files.

Nothing changes when:
  - Initialize has not been run yet (/var/cache/digipi/localized.txt missing)
  - no GPS fix arrives within FIX_TIMEOUT seconds (manual position is kept)
  - the GPS is within MOVE_THRESHOLD_M of the saved positions (DigiPi's, and
    WeeWX's if installed - so if something resets one of them, such as
    a WeeWX reconfigure, it is put right at the next boot)

When it does change something, any DigiPi mode or WeeWX service that was
running is stopped first and started again afterwards, so the programs pick
up the new values and cannot write their old ones back over the files.

Every change is also added as one line to /home/pi/gps-position-history.txt
(date, new position, grid, altitude and how far the station moved), so there
is a lasting record to compare against.  The installer writes its first line.

Manual use (as root):
  digipi-gps-position.py              read GPS, update if moved
  digipi-gps-position.py --dry-run    show what would change, change nothing
  digipi-gps-position.py --force      update even if not moved
  digipi-gps-position.py --fix 33.7748,-84.2963,275   pretend GPS (lat,lon,alt m)
  digipi-gps-position.py --record-install   add an "installed" line to the history
"""

import argparse
import glob
import json
import math
import os
import re
import socket
import statistics
import subprocess
import sys
import time

VERSION = "1.3"

# --------------------------------------------------------------------------
# Settings you may want to change
# --------------------------------------------------------------------------
FIX_TIMEOUT = 600          # seconds to wait for a GPS fix after boot (cold start can be slow)
FIX_SAMPLES = 10           # good fixes to average (median) once the GPS has locked
MOVE_THRESHOLD_M = 100     # ignore apparent moves smaller than this (GPS wander)
ALT_THRESHOLD_M = 30       # only update WeeWX altitude if it changed more than this
DECIMALS = 4               # lat/lon decimals written to files (4 = about 11 m)

GPSD_HOST, GPSD_PORT = "127.0.0.1", 2947

# Services to stop/start around a change, if they are running
# DigiPi modes are stopped BEFORE editing (WSJT-X/JS8Call rewrite their .ini
# on exit) and started again afterwards.  Services that only read their config
# at start-up are simply restarted afterwards.
SERVICES = ["tnc", "tnc300b", "digipeater", "tracker", "node", "winlinkrms",
            "pat", "webchat", "wsjtx", "js8call"]
RESTART_AFTER = ["weewx"]

STATUS_FILE = "/run/digipi-gps-position.json"   # last result, in RAM
LOCALIZED_FLAG = "/var/cache/digipi/localized.txt"
LOCALIZE_ENV = "/home/pi/localize.env"
HISTORY_FILE = "/home/pi/gps-position-history.txt"   # one line per change, kept on the SD card
WEEWX_CONFS = ["/etc/weewx/weewx.conf", "/home/pi/weewx-data/weewx.conf"]

ROOT = ""   # prefix for all paths; set by --root for testing on a copy


def log(msg):
    print(msg, flush=True)


def p(path):
    return ROOT + path


# --------------------------------------------------------------------------
# GPS
# --------------------------------------------------------------------------
def read_gps(timeout):
    """Return (lat, lon, alt_m or None) as the median of FIX_SAMPLES fixes, or None."""
    deadline = time.time() + timeout
    fixes = []
    while time.time() < deadline:
        try:
            with socket.create_connection((GPSD_HOST, GPSD_PORT), timeout=10) as s:
                s.sendall(b'?WATCH={"enable":true,"json":true};\n')
                s.settimeout(10)
                buf = b""
                while time.time() < deadline:
                    try:
                        chunk = s.recv(4096)
                    except socket.timeout:
                        continue
                    if not chunk:
                        break
                    buf += chunk
                    while b"\n" in buf:
                        line, buf = buf.split(b"\n", 1)
                        try:
                            msg = json.loads(line)
                        except ValueError:
                            continue
                        if msg.get("class") != "TPV" or msg.get("mode", 0) < 2:
                            continue
                        if "lat" not in msg or "lon" not in msg:
                            continue
                        alt = msg.get("altMSL", msg.get("alt")) if msg.get("mode") == 3 else None
                        fixes.append((msg["lat"], msg["lon"], alt))
                        if len(fixes) >= FIX_SAMPLES:
                            lat = statistics.median(f[0] for f in fixes)
                            lon = statistics.median(f[1] for f in fixes)
                            alts = [f[2] for f in fixes if f[2] is not None]
                            alt = statistics.median(alts) if alts else None
                            return lat, lon, alt
        except OSError:
            time.sleep(5)    # gpsd not up yet
    return None


def maidenhead(lat, lon):
    """6-character grid square, DigiPi style: EM73tr."""
    lon += 180
    lat += 90
    g = chr(ord("A") + int(lon // 20)) + chr(ord("A") + int(lat // 10))
    g += str(int((lon % 20) // 2)) + str(int(lat % 10))
    g += chr(ord("a") + int((lon % 2) * 12)) + chr(ord("a") + int((lat % 1) * 24))
    return g


def distance_m(lat1, lon1, lat2, lon2):
    r = 6371000
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


# --------------------------------------------------------------------------
# File editing
# --------------------------------------------------------------------------
NUM = r"-?\d+(?:\.\d+)?"


def write_text(path, old, new, dry_run, changed):
    """Write new text over a file (keeping owner and permissions), or show the diff."""
    if new == old:
        return
    changed.append(path)
    if dry_run:
        for o, n in zip(old.splitlines(), new.splitlines()):
            if o != n:
                log(f"  {path}:\n    - {o.strip()}\n    + {n.strip()}")
        return
    full = p(path)
    st = os.stat(full)
    tmp = full + ".gpstmp"
    with open(tmp, "w", encoding="utf-8", errors="surrogateescape") as f:
        f.write(new)
    os.chmod(tmp, st.st_mode & 0o7777)
    try:
        os.chown(tmp, st.st_uid, st.st_gid)
    except PermissionError:
        pass
    os.replace(tmp, full)
    log(f"  updated {path}")


def read_text(path):
    full = p(path)
    if not os.path.isfile(full):
        return None
    with open(full, encoding="utf-8", errors="surrogateescape") as f:
        return f.read()


def edit_file(path, rules, dry_run, changed):
    """Apply (regex, value) rules to one file. Group 1 of each regex is kept as the prefix."""
    old = read_text(path)
    if old is None:
        return
    new = old
    for pattern, value in rules:
        new = re.sub(pattern, lambda m: m.group(1) + value, new, flags=re.M)
    write_text(path, old, new, dry_run, changed)


def edit_weewx(path, lat, lon, alt, dry_run, changed):
    """Change latitude/longitude/altitude only inside the [Station] section."""
    old = read_text(path)
    if old is None:
        return
    lines = old.split("\n")
    in_station = False
    out = []
    for line in lines:
        s = line.strip()
        if re.match(r"^\[[^\[]", s):
            in_station = s.startswith("[Station]")
        if in_station:
            m = re.match(r"^(\s*latitude\s*=\s*)" + NUM + r"(.*)$", line)
            if m:
                line = m.group(1) + f"{lat:.{DECIMALS}f}" + m.group(2)
            m = re.match(r"^(\s*longitude\s*=\s*)" + NUM + r"(.*)$", line)
            if m:
                line = m.group(1) + f"{lon:.{DECIMALS}f}" + m.group(2)
            m = re.match(r"^(\s*altitude\s*=\s*)" + NUM + r"(\s*,\s*)(\w+)(.*)$", line)
            if m and alt is not None:
                unit = m.group(3).lower()
                value = alt / 0.3048 if unit.startswith("f") else alt
                current = float(re.search(NUM, line[len(m.group(1)):]).group())
                current_m = current * 0.3048 if unit.startswith("f") else current
                if abs(current_m - alt) > ALT_THRESHOLD_M:
                    line = m.group(1) + f"{value:.0f}" + m.group(2) + m.group(3) + m.group(4)
        out.append(line)
    write_text(path, old, "\n".join(out), dry_run, changed)


def read_weewx_position(path):
    """(lat, lon) from weewx.conf [Station], or None if WeeWX is not installed."""
    text = read_text(path)
    if text is None:
        return None
    in_station = False
    lat = lon = None
    for line in text.split("\n"):
        s = line.strip()
        if re.match(r"^\[[^\[]", s):
            in_station = s.startswith("[Station]")
        elif in_station:
            m = re.match(r"^(latitude|longitude)\s*=\s*(" + NUM + ")", s)
            if m and m.group(1) == "latitude":
                lat = float(m.group(2))
            elif m:
                lon = float(m.group(2))
    return (lat, lon) if lat is not None and lon is not None else None


def read_localize():
    vals = {}
    with open(p(LOCALIZE_ENV)) as f:
        for line in f:
            m = re.match(r"^(\w+)=(.*)$", line.strip())
            if m:
                vals[m.group(1)] = m.group(2)
    return vals


def apply_position(lat, lon, alt, dry_run):
    la, lo = f"{lat:.{DECIMALS}f}", f"{lon:.{DECIMALS}f}"
    grid6 = maidenhead(lat, lon)
    grid4 = grid6[:4]
    changed = []

    # Direwolf: lat= / long= on PBEACON lines (commented or not)
    for conf in sorted(glob.glob(p("/home/pi/direwolf*.conf"))):
        conf = conf[len(ROOT):]
        edit_file(conf, [
            (r"^(#?\s*PBEACON\b.*?\blat=)" + NUM, la),
            (r"^(#?\s*PBEACON\b.*?\blong=)" + NUM, lo),
        ], dry_run, changed)

    edit_file("/home/pi/config/aprsd/aprsd.conf", [
        (r"^(latitude\s*=\s*)" + NUM, la),
        (r"^(longitude\s*=\s*)" + NUM, lo),
    ], dry_run, changed)

    edit_file("/home/pi/config/direwolf-dashboard/config.yaml", [
        (r"^(\s*latitude:\s*)" + NUM, la),
        (r"^(\s*longitude:\s*)" + NUM, lo),
    ], dry_run, changed)

    # Grid square
    edit_file("/home/pi/config/pat/config.json",
              [(r'("locator":\s*")[A-Za-z0-9]*', grid6)], dry_run, changed)
    edit_file("/usr/local/etc/rmsgw/gateway.conf",
              [(r"^(GRIDSQUARE=)[A-Za-z0-9]*", grid6)], dry_run, changed)
    edit_file("/usr/local/etc/rmsgw/sysop.xml",
              [(r"(<GridSquare>)[A-Za-z0-9]*", grid6)], dry_run, changed)
    edit_file("/usr/local/etc/rmsgw/channels.xml",
              [(r"(<gridsquare>)[A-Za-z0-9]*", grid6)], dry_run, changed)
    for ini in ("/home/pi/config/WSJT-X.ini", "/home/pi/config/JS8Call.ini"):
        edit_file(ini, [(r"^((?:Configuration\\)?MyGrid=)[A-Za-z0-9]*", grid4)],
                  dry_run, changed)

    # localize.env: NEW and OLD both = current, so a re-run of localize.sh is harmless
    edit_file(LOCALIZE_ENV, [
        (r"^((?:NEW|OLD)LAT=).*$", la),
        (r"^((?:NEW|OLD)LON=).*$", lo),
        (r"^((?:NEW|OLD)GRID=).*$", grid6),
    ], dry_run, changed)

    # WeeWX is optional and independent of DigiPi: update it only if installed
    weewx_found = [w for w in WEEWX_CONFS if os.path.isfile(p(w))]
    if weewx_found:
        for w in weewx_found:
            log(f"WeeWX found ({w}); updating its [Station] position.")
            edit_weewx(w, lat, lon, alt, dry_run, changed)
    else:
        log("WeeWX not installed; skipping it.")

    return grid6, changed


# --------------------------------------------------------------------------
# System helpers
# --------------------------------------------------------------------------
def root_is_readonly():
    try:
        opts = subprocess.run(["findmnt", "-no", "OPTIONS", "/"],
                              capture_output=True, text=True).stdout
        return "ro" in opts.split(",")
    except OSError:
        return False


def remount(mode):
    subprocess.run(["mount", "-o", f"remount,{mode}", "/"], check=False)


def active_services(names):
    active = []
    for s in names:
        r = subprocess.run(["systemctl", "is-active", "--quiet", s])
        if r.returncode == 0:
            active.append(s)
    return active


def write_status(d):
    try:
        with open(p(STATUS_FILE), "w") as f:
            json.dump(d, f, indent=1)
    except OSError:
        pass


def add_history(line):
    """Append one line to the position history file (root must be writable)."""
    path = p(HISTORY_FILE)
    new = not os.path.exists(path)
    try:
        with open(path, "a") as f:
            if new:
                f.write("# DigiPi GPS position history - one line per change\n"
                        "# date       time   event      latitude, longitude  grid  "
                        "altitude  details\n")
            f.write(time.strftime("%Y-%m-%d %H:%M  ") + line + "\n")
        try:
            import pwd
            pw = pwd.getpwnam("pi")
            os.chown(path, pw.pw_uid, pw.pw_gid)
        except (KeyError, PermissionError, ImportError):
            pass
        log(f"History: {line}")
    except OSError as e:
        log(f"Could not write {HISTORY_FILE}: {e}")


def record_install():
    """'installed' line: the position DigiPi (and WeeWX) has right now."""
    if not os.path.exists(p(LOCALIZED_FLAG)):
        add_history("installed  (DigiPi not initialized yet; no position)")
        return
    cur = read_localize()
    line = f"installed  {cur.get('NEWLAT')}, {cur.get('NEWLON')}  {cur.get('NEWGRID')}"
    for w in WEEWX_CONFS:
        wpos = read_weewx_position(w)
        if wpos:
            line += f"  WeeWX {wpos[0]}, {wpos[1]}"
    add_history(line + f"  (version {VERSION})")


# --------------------------------------------------------------------------
def main():
    global ROOT
    ap = argparse.ArgumentParser(description="Update DigiPi position from GPS")
    ap.add_argument("--version", action="version", version=f"%(prog)s {VERSION}")
    ap.add_argument("--dry-run", action="store_true", help="show changes, write nothing")
    ap.add_argument("--force", action="store_true", help="update even if not moved")
    ap.add_argument("--fix", help="use LAT,LON[,ALT_M] instead of reading the GPS")
    ap.add_argument("--timeout", type=int, default=FIX_TIMEOUT, help="seconds to wait for a fix")
    ap.add_argument("--record-install", action="store_true",
                    help="add an 'installed' line to the position history and exit")
    ap.add_argument("--root", default="", help=argparse.SUPPRESS)   # testing on a copy
    args = ap.parse_args()
    ROOT = args.root.rstrip("/")
    testing = bool(ROOT)

    log(f"digipi-gps-position {VERSION}")
    if args.record_install:
        record_install()
        return 0
    status = {"time": time.strftime("%Y-%m-%d %H:%M:%S"), "version": VERSION, "result": None}

    if not os.path.exists(p(LOCALIZED_FLAG)):
        log("DigiPi has not been initialized yet; leaving the position alone.")
        status["result"] = "not initialized"
        write_status(status)
        return 0

    if args.fix:
        parts = [float(x) for x in args.fix.split(",")]
        lat, lon = parts[0], parts[1]
        alt = parts[2] if len(parts) > 2 else None
    else:
        log(f"Waiting up to {args.timeout} s for a GPS fix ...")
        fix = read_gps(args.timeout)
        if fix is None:
            log("No GPS fix; keeping the current position.")
            status["result"] = "no fix"
            write_status(status)
            return 0
        lat, lon, alt = fix
    log(f"GPS position {lat:.6f}, {lon:.6f}" + (f", {alt:.0f} m" if alt is not None else ""))
    status.update(lat=lat, lon=lon, alt_m=alt, grid=maidenhead(lat, lon))

    # Compare the GPS with every saved position (DigiPi, and WeeWX if installed).
    # Any one that is off by more than MOVE_THRESHOLD_M triggers an update.
    cur = read_localize()
    try:
        moved = distance_m(float(cur.get("NEWLAT", 0)), float(cur.get("NEWLON", 0)), lat, lon)
    except ValueError:
        moved = float("inf")
    log(f"DigiPi position {cur.get('NEWLAT')}, {cur.get('NEWLON')} ({cur.get('NEWGRID')}); "
        f"{moved:.0f} m from GPS")
    digipi_moved = moved
    weewx_off = None          # WeeWX's old position, if it was the one that was off
    for w in WEEWX_CONFS:
        wpos = read_weewx_position(w)
        if wpos:
            d = distance_m(wpos[0], wpos[1], lat, lon)
            log(f"WeeWX position {wpos[0]}, {wpos[1]}; {d:.0f} m from GPS")
            moved = max(moved, d)
            if d >= MOVE_THRESHOLD_M and weewx_off is None:
                weewx_off = wpos

    if moved < MOVE_THRESHOLD_M and not args.force:
        log("Station has not moved; nothing to change.")
        status["result"] = "unchanged"
        write_status(status)
        return 0

    if args.dry_run:
        log("Dry run - these changes would be made:")
        grid, changed = apply_position(lat, lon, alt, dry_run=True)
        status["result"] = "dry run"
        write_status(status)
        return 0

    stopped = [] if testing else active_services(SERVICES)
    restart = [] if testing else active_services(RESTART_AFTER)
    was_ro = False if testing else root_is_readonly()
    try:
        if stopped:
            log("Stopping " + " ".join(stopped))
            subprocess.run(["systemctl", "stop"] + stopped, check=False)
        if was_ro:
            remount("rw")
        grid, changed = apply_position(lat, lon, alt, dry_run=False)
        line = f"updated    {lat:.{DECIMALS}f}, {lon:.{DECIMALS}f}  {grid}"
        if alt is not None:
            line += f"  {alt:.0f} m"
        if digipi_moved == float("inf"):
            line += "  (previous DigiPi position unreadable)"
        elif weewx_off and digipi_moved < MOVE_THRESHOLD_M:
            line += f"  WeeWX position corrected from {weewx_off[0]}, {weewx_off[1]}"
        else:
            line += (f"  moved {digipi_moved:.0f} m from "
                     f"{cur.get('NEWLAT')}, {cur.get('NEWLON')} {cur.get('NEWGRID')}")
        if args.force and moved < MOVE_THRESHOLD_M:
            line += "  (forced)"
        add_history(line)
        if not testing:
            os.sync()
    finally:
        if was_ro:
            remount("ro")
        if stopped:
            log("Starting " + " ".join(stopped))
            for s in stopped:      # one at a time; DigiPi modes stop each other on start
                subprocess.run(["systemctl", "start", s], check=False)
        if restart:
            log("Restarting " + " ".join(restart))
            subprocess.run(["systemctl", "restart"] + restart, check=False)

    log(f"Position set to {lat:.{DECIMALS}f}, {lon:.{DECIMALS}f} ({grid}); "
        f"{len(changed)} file(s) updated.")
    status.update(result="updated", files=changed)
    write_status(status)
    return 0


if __name__ == "__main__":
    sys.exit(main())
