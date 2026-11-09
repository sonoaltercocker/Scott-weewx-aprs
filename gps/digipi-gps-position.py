#!/usr/bin/env python3
"""
digipi-gps-position.py  -  keep DigiPi's station position in step with a GPS

Version 1.6  -  Scott Sheppard, KJ4ZZB
RMS gateway handling (both /etc/rmsgw and /usr/local/etc/rmsgw, symlinks,
the update when RMS starts) and the LAN NMEA feed are based on work by
Scott Curie, NS7C.

DigiPi's Initialize step copies the latitude, longitude and grid square you
type in into a dozen config files, once.  This program keeps them in step
with a GPS (read through gpsd):

  Lat/lon   direwolf*.conf (PBEACON lines), aprsd.conf,
            direwolf-dashboard config.yaml, localize.env (direwatch display)
  Grid      Pat config.json, RMS gateway gateway.conf / sysop.xml /
            channels.xml (in /usr/local/etc/rmsgw and /etc/rmsgw, following
            symlinks), WSJT-X.ini and JS8Call.ini (4-character grid)
  WeeWX     [Station] latitude, longitude and altitude in weewx.conf
            (only if WeeWX is installed; without WeeWX this step is skipped).
            The altitude is left alone unless turned on with
            --set update-altitude on; then it is only used from 3D fixes whose
            estimated vertical error is at most alt-max-error metres.

When it runs
  At boot   (digipi-gps-position.service, --watch) it waits for a fix and
            updates the files if the station has moved more than
            move-threshold metres.  It then keeps watching: when the station
            has been parked at a new place for settle-minutes, it updates
            once more - no reboot needed.  While moving it changes nothing.
  RMS start (--rms-start, from a drop-in for winlinkrms.service) a quick
            check, so the gateway registers with the current grid square.
            It never stops or starts DigiPi modes and never stops RMS from
            starting.

Before an update the running DigiPi mode is stopped and afterwards started
again.  If an AX.25 connection (a Winlink session, a node user) is in
progress, the update waits until the gateway is idle, at most busy-wait
minutes, then goes ahead anyway.  The previous version of each changed file
is kept as <file>.gps-backup.  Every change adds one line to
/home/pi/gps-position-history.txt.

Optional features (installed, off until turned on)
  live-beacons  Direwolf beacons the live GPS position with SmartBeaconing
                in the digipeater and iGate modes, instead of the fixed
                PBEACON position.
  lan-nmea      GPS data for Winlink Express and other computers on the LAN,
                as NMEA sentences on TCP port 2948 (digipi-gps-nmea-relay).

Commands (as root)
  digipi-gps-position.py                    check once, update if moved
  digipi-gps-position.py --dry-run          show what would change
  digipi-gps-position.py --force            update even if not moved
  digipi-gps-position.py --status           version, options, settings
  digipi-gps-position.py --enable live-beacons | lan-nmea
  digipi-gps-position.py --disable live-beacons | lan-nmea
  digipi-gps-position.py --set busy-wait 15     (see --status for all settings)
  digipi-gps-position.py --set busy-wait default
  digipi-gps-position.py --set-gps-device   point gpsd at the GPS by its permanent
                                            /dev/serial/by-id name (the installer does this)
  digipi-gps-position.py --fix 33.7748,-84.2963,275   pretend GPS (lat,lon,alt m)
"""

import argparse
import fcntl
import glob
import json
import math
import os
import re
import shutil
import socket
import statistics
import subprocess
import sys
import time
from collections import deque

VERSION = "1.6"

# --------------------------------------------------------------------------
# Settings: defaults here, changed with --set (kept in SETTINGS_FILE, which an
# upgrade leaves alone).
# --------------------------------------------------------------------------
DEFAULTS = {
    "fix-timeout":     (600, "seconds to wait for a GPS fix at boot"),
    "rms-fix-timeout": (30, "seconds to wait for a GPS fix when RMS gateway mode starts"),
    "fix-samples":     (10, "readings taken; the middle value is used"),
    "move-threshold":  (100, "moves smaller than this, in metres, are ignored"),
    "alt-threshold":   (30, "WeeWX altitude is changed only if this far off, in metres"),
    "alt-max-error":   (15, "GPS altitude is used only if its estimated vertical error is at most this, in metres"),
    "update-altitude": ("off", "on/off - also update WeeWX's altitude from the GPS"),
    "decimals":        (4, "decimal places written for latitude/longitude (4 = about 11 m)"),
    "settle-minutes":  (10, "minutes parked at a new place before the watcher updates"),
    "busy-wait":       (10, "minutes to wait for an AX.25 connection to finish before updating"),
    "smartbeaconing":  ("60 3:00 5 30:00 0:30 30 255",
                        "Direwolf SMARTBEACONING values used by live-beacons: fast speed (mph), "
                        "fast rate, slow speed, slow rate, turn time, turn angle, turn slope"),
    "live-beacons":    ("off", "on/off - change with --enable / --disable"),
    "lan-nmea":        ("off", "on/off - change with --enable / --disable"),
}
OPTIONS = ("live-beacons", "lan-nmea")
ON_OFF = OPTIONS + ("update-altitude",)
GPSD_DEFAULTS = "/etc/default/gpsd"
BY_ID_DIR = "/dev/serial/by-id"
SETTINGS_FILE = "/etc/digipi-gps-position.conf"

GPSD_HOST, GPSD_PORT = "127.0.0.1", 2947
SETTLE_RADIUS_M = 50        # "parked" = 90 % of readings within this of their middle
SAMPLE_EVERY_S = 5          # watcher keeps one reading every 5 s

# DigiPi modes are stopped BEFORE editing (WSJT-X/JS8Call rewrite their .ini
# on exit) and started again afterwards.  Services that only read their config
# at start-up are restarted afterwards.
SERVICES = ["tnc", "tnc300b", "digipeater", "tracker", "node", "winlinkrms",
            "pat", "webchat", "wsjtx", "js8call"]
RESTART_AFTER = ["weewx"]
# At RMS start the other DigiPi modes have just been stopped, so only these
# independent services are restarted (without waiting) if they are running.
RMS_START_RESTART = ["pat", "weewx"]
RELAY_SERVICE = "digipi-gps-nmea-relay"
RELAY_PORT = 2948

# RMS gateway files. Some DigiPi images use /usr/local/etc/rmsgw, others also
# /etc/rmsgw; some names are symlinks.  Each real file is edited once.
RMS_FILES = [
    ("/usr/local/etc/rmsgw/gateway.conf", r"^(\s*GRIDSQUARE\s*=\s*)[A-Za-z0-9]*"),
    ("/etc/rmsgw/gateway.conf",           r"^(\s*GRIDSQUARE\s*=\s*)[A-Za-z0-9]*"),
    ("/usr/local/etc/rmsgw/sysop.xml",    r"(<GridSquare>\s*)[A-Za-z0-9]*"),
    ("/etc/rmsgw/sysop.xml",              r"(<GridSquare>\s*)[A-Za-z0-9]*"),
    ("/usr/local/etc/rmsgw/channels.xml", r"(<gridsquare>\s*)[A-Za-z0-9]*"),
    ("/etc/rmsgw/channels.xml",           r"(<gridsquare>\s*)[A-Za-z0-9]*"),
    ("/usr/local/etc/channels.xml",       r"(<gridsquare>\s*)[A-Za-z0-9]*"),
]

STATUS_FILE = "/run/digipi-gps-position.json"   # last result, in RAM
LOCALIZED_FLAG = "/var/cache/digipi/localized.txt"
LOCALIZE_ENV = "/home/pi/localize.env"
LOCK_FILE = "/run/digipi-gps-position.lock"     # one update at a time
HISTORY_FILE = "/home/pi/gps-position-history.txt"   # one line per change, kept on the SD card
WEEWX_CONFS = ["/etc/weewx/weewx.conf", "/home/pi/weewx-data/weewx.conf"]
AX25_PROC = "/proc/net/ax25"
BACKUP_SUFFIX = ".gps-backup"
LIVE_BEGIN = "# --- digipi-gps-position: live beacons (remove with --disable live-beacons) ---"
LIVE_END = "# --- end digipi-gps-position live beacons ---"
PBEACON_OFF = "#gps-live# "      # marks a PBEACON line switched off by live-beacons

ROOT = ""   # prefix for all paths; set by --root for testing on a copy
CFG = {}
ALT_NOTE = {"rejected": 0, "worst": None}   # altitude readings not trusted, for the log


def log(msg):
    print(msg, flush=True)


def p(path):
    return ROOT + path


# --------------------------------------------------------------------------
# Settings file
# --------------------------------------------------------------------------
def load_settings():
    """Defaults, overridden by SETTINGS_FILE.  Returns {key: value}."""
    cfg = {k: v[0] for k, v in DEFAULTS.items()}
    try:
        with open(p(SETTINGS_FILE)) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = (x.strip() for x in line.split("=", 1))
                if key in cfg:
                    cfg[key] = parse_value(key, value)
    except FileNotFoundError:
        pass
    except ValueError as exc:
        log(f"Ignoring a bad line in {SETTINGS_FILE}: {exc}")
    return cfg


def parse_value(key, value):
    default = DEFAULTS[key][0]
    if key in ON_OFF:
        value = value.lower()
        if value not in ("on", "off"):
            raise ValueError(f"{key} must be on or off")
        return value
    if isinstance(default, int):
        number = float(value)
        if number < 0:
            raise ValueError(f"{key} can't be negative")
        return int(number) if number.is_integer() else number
    if key == "smartbeaconing":
        parts = value.split()
        if len(parts) != 7:
            raise ValueError("smartbeaconing needs 7 values, e.g. 60 3:00 5 30:00 0:30 30 255")
    return value


def save_settings(cfg):
    """Write only the settings that differ from the defaults."""
    lines = ["# DigiPi GPS Position Updater settings - change with:",
             "#   sudo digipi-gps-position.py --set <name> <value>",
             "# Anything not listed here uses its default (see --status)."]
    for key, (default, _) in DEFAULTS.items():
        if cfg[key] != default:
            lines.append(f"{key} = {cfg[key]}")
    with open(p(SETTINGS_FILE), "w") as f:
        f.write("\n".join(lines) + "\n")


def c(key):
    return CFG[key]


# --------------------------------------------------------------------------
# GPS
# --------------------------------------------------------------------------
def gps_fixes(deadline=None):
    """Yield (lat, lon, alt_m or None) for each 2D/3D fix gpsd reports.
    Reconnects if gpsd goes away.  Stops at the deadline, if one is given."""
    while deadline is None or time.time() < deadline:
        try:
            with socket.create_connection((GPSD_HOST, GPSD_PORT), timeout=10) as s:
                s.sendall(b'?WATCH={"enable":true,"json":true};\n')
                s.settimeout(10)
                buf = b""
                while deadline is None or time.time() < deadline:
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
                        lat, lon = msg.get("lat"), msg.get("lon")
                        if lat is None or lon is None:
                            continue
                        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
                            continue
                        yield lat, lon, trusted_altitude(msg)
        except OSError:
            time.sleep(5)    # gpsd not up yet, or went away


def trusted_altitude(msg):
    """The fix's altitude (MSL, metres) if it is accurate enough to use, else None.
    gpsd's 'epv' is its estimate of the vertical error (metres, 95 %)."""
    if msg.get("mode") != 3:
        return None
    alt = msg.get("altMSL", msg.get("alt"))
    if alt is None:
        return None
    epv = msg.get("epv")
    if epv is None or epv > c("alt-max-error"):
        ALT_NOTE["rejected"] += 1
        if epv is not None:
            ALT_NOTE["worst"] = max(ALT_NOTE["worst"] or 0, epv)
        return None
    return alt


def read_gps(timeout):
    """(lat, lon, alt_m or None) as the median of fix-samples fixes, or None."""
    fixes = []
    for fix in gps_fixes(time.time() + timeout):
        fixes.append(fix)
        if len(fixes) >= c("fix-samples"):
            return median_fix(fixes)
    return None


def median_fix(fixes):
    lat = statistics.median(f[0] for f in fixes)
    lon = statistics.median(f[1] for f in fixes)
    alts = [f[2] for f in fixes if f[2] is not None]
    # Use the altitude only if most readings had a trustworthy one
    enough = alts and len(alts) >= max(3, (len(fixes) + 1) // 2)
    return lat, lon, (statistics.median(alts) if enough else None)


def altitude_note(alt):
    """Log why the altitude will not be used, if it won't."""
    if c("update-altitude") == "off":
        pass                     # the default: altitude is not touched, nothing to say
    elif alt is None:
        worst = ALT_NOTE["worst"]
        why = (f"estimated vertical error up to {worst:.0f} m, limit {c('alt-max-error')} m"
               if worst else "no 3D fix with an error estimate")
        log(f"GPS altitude not accurate enough ({why}); WeeWX altitude left as it is.")
    ALT_NOTE.update(rejected=0, worst=None)


def maidenhead(lat, lon):
    """6-character grid square, DigiPi style: EM73tr."""
    lon = min(max(lon, -180.0), 179.999999) + 180
    lat = min(max(lat, -90.0), 89.999999) + 90
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
    """Write new text over a file (keeping owner and permissions, and the
    previous version as <file>.gps-backup), or show the difference."""
    if new == old:
        return
    changed.append(path)
    if dry_run:
        for o, n in zip(old.splitlines(), new.splitlines()):
            if o != n:
                log(f"  {path}:\n    - {o.strip()}\n    + {n.strip()}")
        return
    full = os.path.realpath(p(path))   # write the real file, never replace a symlink
    st = os.stat(full)
    shutil.copy2(full, full + BACKUP_SUFFIX)    # only the latest previous copy is kept
    tmp = full + ".gpstmp"
    with open(tmp, "w", encoding="utf-8", errors="surrogateescape") as f:
        f.write(new)
    os.chmod(tmp, st.st_mode & 0o7777)
    try:
        os.chown(tmp, st.st_uid, st.st_gid)
        os.chown(full + BACKUP_SUFFIX, st.st_uid, st.st_gid)
    except PermissionError:
        pass
    os.replace(tmp, full)
    real = full[len(ROOT):] if ROOT and full.startswith(ROOT) else full
    log(f"  updated {path}" + (f" (-> {real})" if real != path else ""))


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
    in_station = False
    out = []
    for line in old.split("\n"):
        s = line.strip()
        if re.match(r"^\[[^\[]", s):
            in_station = s.startswith("[Station]")
        if in_station:
            m = re.match(r"^(\s*latitude\s*=\s*)" + NUM + r"(.*)$", line)
            if m:
                line = m.group(1) + f"{lat:.{c('decimals')}f}" + m.group(2)
            m = re.match(r"^(\s*longitude\s*=\s*)" + NUM + r"(.*)$", line)
            if m:
                line = m.group(1) + f"{lon:.{c('decimals')}f}" + m.group(2)
            m = re.match(r"^(\s*altitude\s*=\s*)(" + NUM + r")(\s*,\s*)(\w+)(.*)$", line)
            if m and alt is not None:
                unit = m.group(4).lower()
                feet = unit.startswith("f")
                current_m = float(m.group(2)) * (0.3048 if feet else 1)
                if abs(current_m - alt) > c("alt-threshold"):
                    value = alt / 0.3048 if feet else alt
                    line = m.group(1) + f"{value:.0f}" + m.group(3) + m.group(4) + m.group(5)
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
    if c("update-altitude") == "off":
        alt = None
    d = c("decimals")
    la, lo = f"{lat:.{d}f}", f"{lon:.{d}f}"
    grid6 = maidenhead(lat, lon)
    grid4 = grid6[:4]
    changed = []

    # Direwolf: lat= / long= on PBEACON lines - active, commented, or switched
    # off by live-beacons - so the fixed beacon is right whenever it is used.
    for conf in sorted(glob.glob(p("/home/pi/direwolf*.conf"))):
        conf = conf[len(ROOT):]
        edit_file(conf, [
            (r"^((?:#gps-live# |#)?\s*PBEACON\b.*?\blat=)" + NUM, la),
            (r"^((?:#gps-live# |#)?\s*PBEACON\b.*?\blong=)" + NUM, lo),
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
    seen = set()
    for path, pattern in RMS_FILES:
        real = os.path.realpath(p(path))
        if real in seen or not os.path.isfile(real):
            continue
        seen.add(real)
        edit_file(path, [(pattern, grid6)], dry_run, changed)
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


class Writable:
    """Make the root filesystem writable for a block, then put it back."""
    def __init__(self, testing):
        self.was_ro = False if testing else root_is_readonly()

    def __enter__(self):
        if self.was_ro:
            remount("rw")
        return self

    def __exit__(self, *exc):
        if not ROOT:
            os.sync()
        if self.was_ro:
            remount("ro")
        return False


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


def ax25_busy():
    """True if an AX.25 connection (Winlink session, node user) is in progress."""
    try:
        with open(p(AX25_PROC)) as f:
            for line in f:
                fields = line.split()
                # pointer  device  source  destination[,digis]  state ...
                # state 1 = connecting, 3 = connected, 4 = recovering
                if len(fields) > 4 and fields[4] in ("1", "3", "4"):
                    return True
    except OSError:
        pass
    return False


def wait_until_idle(testing):
    """Wait while an AX.25 connection is in progress, at most busy-wait minutes.
    Returns a note for the history line, or ''."""
    if not ax25_busy():
        return ""
    limit = c("busy-wait") * 60
    log(f"An AX.25 connection is in progress; waiting up to {c('busy-wait')} min for it to finish.")
    start = time.time()
    while time.time() - start < limit:
        time.sleep(1 if testing else 30)
        if not ax25_busy():
            waited = (time.time() - start) / 60
            log(f"Connection finished after {waited:.1f} min.")
            took = "under a minute" if waited < 1 else f"{waited:.0f} min"
            return f"  (waited {took} for a connection to finish)"
    log(f"Still busy after {c('busy-wait')} min; updating anyway.")
    return f"  (connection still open after {c('busy-wait')} min; updated anyway)"


# --------------------------------------------------------------------------
# History
# --------------------------------------------------------------------------
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
        add_history(f"installed  (DigiPi not initialized yet; no position)  (version {VERSION})")
        return
    cur = read_localize()
    line = f"installed  {cur.get('NEWLAT')}, {cur.get('NEWLON')}  {cur.get('NEWGRID')}"
    for w in WEEWX_CONFS:
        wpos = read_weewx_position(w)
        if wpos:
            line += f"  WeeWX {wpos[0]}, {wpos[1]}"
    add_history(line + f"  (version {VERSION})")


# --------------------------------------------------------------------------
# Comparing and updating
# --------------------------------------------------------------------------
def compare(lat, lon, quiet=False):
    """How far the saved positions are from the GPS.
    Returns (moved, digipi_moved, weewx_off, cur)."""
    cur = read_localize()
    try:
        moved = distance_m(float(cur.get("NEWLAT", 0)), float(cur.get("NEWLON", 0)), lat, lon)
    except ValueError:
        moved = float("inf")
    if not quiet:
        log(f"DigiPi position {cur.get('NEWLAT')}, {cur.get('NEWLON')} ({cur.get('NEWGRID')}); "
            f"{moved:.0f} m from GPS")
    digipi_moved = moved
    weewx_off = None          # WeeWX's old position, if it was the one that was off
    for w in WEEWX_CONFS:
        wpos = read_weewx_position(w)
        if wpos:
            d = distance_m(wpos[0], wpos[1], lat, lon)
            if not quiet:
                log(f"WeeWX position {wpos[0]}, {wpos[1]}; {d:.0f} m from GPS")
            moved = max(moved, d)
            if d >= c("move-threshold") and weewx_off is None:
                weewx_off = wpos
    return moved, digipi_moved, weewx_off, cur


def check_and_update(args, testing, lat, lon, alt, status, reason=""):
    """Update the files if the GPS is far enough from the saved positions."""
    if c("update-altitude") == "off":
        alt = None                # not written, so not recorded either
    moved = compare(lat, lon)[0]
    if moved < c("move-threshold") and not args.force:
        log("Station has not moved; nothing to change.")
        status["result"] = "unchanged"
        write_status(status)
        return False
    if args.dry_run:
        log("Dry run - these changes would be made:")
        apply_position(lat, lon, alt, dry_run=True)
        status["result"] = "dry run"
        write_status(status)
        return False

    note = "" if args.rms_start else wait_until_idle(testing)

    # One update at a time (the watcher and an RMS-start run can overlap)
    lock = open(p(LOCK_FILE), "w")
    fcntl.flock(lock, fcntl.LOCK_EX)
    todo = {"start": [], "restart": []}    # filled in by update()
    try:
        return update(args, testing, lat, lon, alt, status, todo, reason + note)
    finally:
        fcntl.flock(lock, fcntl.LOCK_UN)   # before starting RMS, whose own hook takes the lock
        lock.close()
        start_services(todo, args.rms_start)


def start_services(todo, rms_start):
    """Start what update() stopped, and restart the independent services - even after an error."""
    if todo["start"]:
        log("Starting " + " ".join(todo["start"]))
        for svc in todo["start"]:      # one at a time; DigiPi modes stop each other on start
            subprocess.run(["systemctl", "start", svc], check=False)
    if todo["restart"]:
        log("Restarting " + " ".join(todo["restart"]))
        cmd = ["systemctl", "restart"] + (["--no-block"] if rms_start else [])
        subprocess.run(cmd + todo["restart"], check=False)


def update(args, testing, lat, lon, alt, status, todo, note):
    """Compare again (under the lock) and, if moved, rewrite the files."""
    moved, digipi_moved, weewx_off, cur = compare(lat, lon, quiet=True)
    if moved < c("move-threshold") and not args.force:
        log("Already up to date.")
        status["result"] = "unchanged"
        write_status(status)
        return False

    if testing:
        stopped, restart = [], []
    elif args.rms_start:
        # The RMS service has just stopped the other modes; don't touch them.
        stopped, restart = [], active_services(RMS_START_RESTART)
    else:
        stopped, restart = active_services(SERVICES), active_services(RESTART_AFTER)
    todo["start"], todo["restart"] = stopped, restart
    if stopped:
        log("Stopping " + " ".join(stopped))
        subprocess.run(["systemctl", "stop"] + stopped, check=False)

    d = c("decimals")
    with Writable(testing):
        grid, changed = apply_position(lat, lon, alt, dry_run=False)
        line = f"updated    {lat:.{d}f}, {lon:.{d}f}  {grid}"
        if alt is not None:
            line += f"  {alt:.0f} m"
        if digipi_moved == float("inf"):
            line += "  (previous DigiPi position unreadable)"
        elif weewx_off and digipi_moved < c("move-threshold"):
            line += f"  WeeWX position corrected from {weewx_off[0]}, {weewx_off[1]}"
        else:
            line += (f"  moved {digipi_moved:.0f} m from "
                     f"{cur.get('NEWLAT')}, {cur.get('NEWLON')} {cur.get('NEWGRID')}")
        if args.force and moved < c("move-threshold"):
            line += "  (forced)"
        if args.rms_start:
            line += "  (at RMS start)"
        add_history(line + note)

    log(f"Position set to {lat:.{d}f}, {lon:.{d}f} ({grid}); {len(changed)} file(s) updated.")
    status.update(result="updated", files=changed, time=time.strftime("%Y-%m-%d %H:%M:%S"))
    write_status(status)
    return True


# --------------------------------------------------------------------------
# Watcher: update once the station has settled at a new place
# --------------------------------------------------------------------------
def watch(args, testing, status, fixes=None):
    settle_s = c("settle-minutes") * 60
    every = SAMPLE_EVERY_S if not testing else 1
    eval_every = max(every, min(60, settle_s / 5))
    log(f"Watching the GPS; an update follows once the station has been parked at a "
        f"new place for {c('settle-minutes')} min.")
    samples = deque()
    last_eval = last_moving_log = 0
    status.update(watching=True)
    write_status(status)
    for lat, lon, alt in (fixes if fixes is not None else gps_fixes()):
        now = time.time()
        if not samples or now - samples[-1][0] >= every:
            samples.append((now, lat, lon, alt))
        while samples and now - samples[0][0] > settle_s + 2 * eval_every:
            samples.popleft()
        if now - last_eval < eval_every:
            continue
        last_eval = now
        window = [s for s in samples if now - s[0] <= settle_s]
        if not window or now - samples[0][0] < settle_s:
            continue                                   # not watched long enough yet
        mlat, mlon, malt = median_fix([s[1:] for s in window])
        near = sum(1 for s in window if distance_m(mlat, mlon, s[1], s[2]) <= SETTLE_RADIUS_M)
        if near < 0.9 * len(window):
            if now - last_moving_log > 600:
                log("Station is moving; waiting for it to settle.")
                last_moving_log = now
            continue
        if compare(mlat, mlon, quiet=True)[0] < c("move-threshold"):
            continue                                   # parked where the files say
        log(f"Station has settled at {mlat:.6f}, {mlon:.6f}.")
        altitude_note(malt)
        status.update(lat=mlat, lon=mlon, alt_m=malt, grid=maidenhead(mlat, mlon))
        try:
            check_and_update(args, testing, mlat, mlon, malt, status,
                             reason="  (settled after a move)")
        except Exception as exc:                       # noqa: BLE001 - keep watching
            log(f"Update failed: {exc}; trying again in {c('settle-minutes')} min.")
        samples.clear()


# --------------------------------------------------------------------------
# Optional features
# --------------------------------------------------------------------------
def beacon_confs():
    """Direwolf configs that send a fixed beacon (Tracker already uses the GPS)."""
    out = []
    for conf in sorted(glob.glob(p("/home/pi/direwolf*.conf"))):
        rel = conf[len(ROOT):]
        if "tracker" in os.path.basename(rel):
            continue
        text = read_text(rel)
        if text and re.search(r"^(\s*PBEACON\b|#gps-live# )", text, flags=re.M):
            out.append(rel)
    return out


def live_beacons_on(text):
    """Switch the active PBEACON lines off and add GPSD + TBEACON + SMARTBEACONING."""
    if LIVE_BEGIN in text:
        return text
    lines = text.split("\n")
    out = []
    for line in lines:
        if re.match(r"^\s*PBEACON\b", line):
            tbeacon = re.sub(r"\s+(lat|long|lon|alt|altitude)=\S+", "", line)
            tbeacon = re.sub(r"^\s*PBEACON", "TBEACON", tbeacon)
            out += [PBEACON_OFF + line, LIVE_BEGIN, "GPSD localhost", tbeacon,
                    f"SMARTBEACONING {c('smartbeaconing')}", LIVE_END]
        else:
            out.append(line)
    return "\n".join(out)


def live_beacons_off(text):
    """Remove the added block and switch the PBEACON lines back on."""
    text = re.sub(re.escape(LIVE_BEGIN) + r".*?" + re.escape(LIVE_END) + r"\n?", "",
                  text, flags=re.S)
    return re.sub(r"^" + re.escape(PBEACON_OFF), "", text, flags=re.M)


def set_option(name, on, testing):
    cfg = load_settings()
    want = "on" if on else "off"
    todo = {"start": [], "restart": []}
    with Writable(testing):
        if name == "live-beacons":
            stopped = [] if testing else active_services(SERVICES)
            if stopped:
                log("Stopping " + " ".join(stopped))
                subprocess.run(["systemctl", "stop"] + stopped, check=False)
            todo["start"] = stopped
            changed = []
            for conf in beacon_confs():
                old = read_text(conf)
                new = live_beacons_on(old) if on else live_beacons_off(old)
                write_text(conf, old, new, False, changed)
            if not changed:
                log("No Direwolf beacon settings needed changing.")
        elif name == "lan-nmea":
            if not testing:
                verb = ["enable", "--now"] if on else ["disable", "--now"]
                r = subprocess.run(["systemctl"] + verb + [RELAY_SERVICE])
                if r.returncode != 0:
                    log(f"Could not {'start' if on else 'stop'} {RELAY_SERVICE}; "
                        "run the installer again.")
                    return 1
        cfg[name] = want
        save_settings(cfg)
    start_services(todo, False)
    log(f"{name} is now {want}.")
    if name == "lan-nmea" and on:
        log(f"In Winlink Express, set the GPS to TCP/IP: this DigiPi's address, port {RELAY_PORT}.")
        log("Anyone on this network can read the station's position from that port.")
    if name == "live-beacons" and on:
        log("Direwolf now beacons the live GPS position (SmartBeaconing) in the "
            "digipeater and iGate modes. With no GPS fix, no beacon is sent.")
    return 0


def gpsd_identified_devices(timeout=20):
    """Paths of the devices gpsd has recognised as a GPS (it names a driver for them)."""
    deadline = time.time() + timeout
    try:
        with socket.create_connection((GPSD_HOST, GPSD_PORT), timeout=5) as s:
            s.sendall(b'?WATCH={"enable":true,"json":true};\n')
            s.settimeout(2)
            buf = b""
            while time.time() < deadline:
                try:
                    chunk = s.recv(4096)
                except socket.timeout:
                    s.sendall(b"?DEVICES;\n")
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
                    if msg.get("class") == "DEVICES":
                        found = [d["path"] for d in msg.get("devices", [])
                                 if d.get("driver") and d.get("path")]
                        if found:
                            return found
    except OSError:
        pass
    return []


def by_id_name(dev):
    """The /dev/serial/by-id link for a device, or None."""
    real = os.path.realpath(p(dev))
    for link in sorted(glob.glob(p(BY_ID_DIR) + "/*")):
        if os.path.realpath(link) == real:
            return link[len(ROOT):]
    return None


def list_by_id():
    links = sorted(glob.glob(p(BY_ID_DIR) + "/*"))
    if links:
        log("Serial devices by their permanent names:")
        for link in links:
            log(f"  {link[len(ROOT):]}")


def set_gps_device(testing):
    """Point gpsd at the GPS by its permanent /dev/serial/by-id name, if gpsd
    confirms which device is the GPS.  Changes nothing when it can't be sure."""
    text = read_text(GPSD_DEFAULTS)
    m = re.search(r'^DEVICES="?([^"\n]*)"?\s*$', text or "", flags=re.M)
    if not m:
        log(f"No DEVICES line in {GPSD_DEFAULTS}; set the GPS device on DigiPi's setup page.")
        return 0
    devices = m.group(1).split()
    if devices and all(d.startswith(BY_ID_DIR + "/") for d in devices):
        log(f"gpsd already uses the GPS's permanent name: {' '.join(devices)}")
        return 0
    try:
        with open(p("/proc/cpuinfo")) as f:
            pizero = "BCM2835" in f.read()
        icom = "IC-705" in subprocess.run(["lsusb"], capture_output=True, text=True).stdout
    except OSError:
        pizero = icom = False
    if pizero and icom:
        log("IC-705 on a Pi Zero 2 / 3A+: DigiPi's own GPS workaround needs the "
            "device name as it is; not changing it.")
        return 0

    log("Asking gpsd which device is the GPS ...")
    gps = gpsd_identified_devices()
    if not gps:
        log("gpsd has not recognised a GPS yet (is it plugged in, and is DEVICES right?).")
        log(f"Not changing {GPSD_DEFAULTS}.")
        list_by_id()
        return 0

    gps_real = {os.path.realpath(p(g)) for g in gps}
    new_devices, changed_any = [], []
    for dev in devices:
        if dev.startswith(BY_ID_DIR + "/") or os.path.realpath(p(dev)) not in gps_real:
            new_devices.append(dev)
            continue
        name = by_id_name(dev)
        if name:
            new_devices.append(name)
            changed_any.append((dev, name))
        else:
            new_devices.append(dev)
            log(f"{dev} has no permanent name in {BY_ID_DIR}; leaving it as it is.")
    if not changed_any:
        log(f"The device set in {GPSD_DEFAULTS} ({' '.join(devices)}) is not the one gpsd "
            "recognised as the GPS; not changing it.")
        list_by_id()
        return 0

    old_line = m.group(0)
    new_text = text.replace(old_line, f'DEVICES="{" ".join(new_devices)}"\n'
                            f'#{old_line.strip()}   # before digipi-gps-position --set-gps-device', 1)
    with Writable(testing):
        write_text(GPSD_DEFAULTS, text, new_text, False, [])
    for dev, name in changed_any:
        log(f"gpsd now reads the GPS as {name} (was {dev}).")
    if not testing:
        log("Restarting gpsd ...")
        subprocess.run(["systemctl", "restart", "gpsd"], check=False)
    return 0


def set_setting(key, value, testing):
    if key not in DEFAULTS or key in OPTIONS:
        names = ", ".join(k for k in DEFAULTS if k not in OPTIONS)
        log(f"Unknown setting '{key}'. Settings: {names}. "
            "Options are changed with --enable / --disable.")
        return 1
    cfg = load_settings()
    try:
        cfg[key] = DEFAULTS[key][0] if value == "default" else parse_value(key, value)
    except ValueError as exc:
        log(f"Not changed: {exc}")
        return 1
    with Writable(testing):
        save_settings(cfg)
    log(f"{key} = {cfg[key]}")
    if key == "smartbeaconing" and cfg["live-beacons"] == "on":
        log("Turn live-beacons off and on again to use the new values.")
    elif not testing:
        log("The watcher uses new settings after the next boot "
            "(or: sudo systemctl restart digipi-gps-position).")
    return 0


def show_status(testing):
    cfg = load_settings()
    log(f"DigiPi GPS Position Updater {VERSION}")
    log("")
    log("Options:")
    for o in OPTIONS:
        log(f"  {o:<16} {cfg[o]}")
    log("")
    log("Settings (change with --set <name> <value>, or --set <name> default):")
    for key, (default, meaning) in DEFAULTS.items():
        if key in OPTIONS:
            continue
        mark = "" if cfg[key] == default else f"   (default {default})"
        log(f"  {key:<16} {cfg[key]}{mark}")
        log(f"  {'':<16} {meaning}")
    log("")
    if not testing:
        for svc in ("digipi-gps-position", RELAY_SERVICE):
            r = subprocess.run(["systemctl", "is-active", svc], capture_output=True, text=True)
            log(f"  {svc:<24} {r.stdout.strip() or 'unknown'}")
    try:
        with open(p(STATUS_FILE)) as f:
            st = json.load(f)
        log(f"  last result: {st.get('result')} at {st.get('time')}")
    except (OSError, ValueError):
        log("  last result: none yet this boot")
    try:
        with open(p(HISTORY_FILE)) as f:
            last = [x for x in f if not x.startswith("#")]
        if last:
            log(f"  last history line: {last[-1].rstrip()}")
    except OSError:
        pass
    return 0


# --------------------------------------------------------------------------
def main():
    global ROOT, CFG
    ap = argparse.ArgumentParser(description="Keep DigiPi's position in step with a GPS")
    ap.add_argument("--version", action="version", version=f"%(prog)s {VERSION}")
    ap.add_argument("--dry-run", action="store_true", help="show changes, write nothing")
    ap.add_argument("--force", action="store_true", help="update even if not moved")
    ap.add_argument("--fix", help="use LAT,LON[,ALT_M] instead of reading the GPS")
    ap.add_argument("--timeout", type=int, default=None, help="seconds to wait for a fix")
    ap.add_argument("--watch", action="store_true",
                    help="after the check, keep watching and update once the station settles")
    ap.add_argument("--rms-start", action="store_true",
                    help="quick update before the RMS gateway starts (from winlinkrms.service)")
    ap.add_argument("--status", action="store_true", help="show version, options and settings")
    ap.add_argument("--enable", choices=OPTIONS, help="turn an optional feature on")
    ap.add_argument("--disable", choices=OPTIONS, help="turn an optional feature off")
    ap.add_argument("--set", nargs=2, metavar=("NAME", "VALUE"), help="change a setting")
    ap.add_argument("--set-gps-device", action="store_true",
                    help="point gpsd at the GPS by its permanent /dev/serial/by-id name")
    ap.add_argument("--record-install", action="store_true",
                    help="add an 'installed' line to the position history and exit")
    ap.add_argument("--root", default="", help=argparse.SUPPRESS)   # testing on a copy
    args = ap.parse_args()
    ROOT = args.root.rstrip("/")
    testing = bool(ROOT)
    CFG = load_settings()

    if args.status:
        return show_status(testing)
    if args.enable or args.disable:
        return set_option(args.enable or args.disable, bool(args.enable), testing)
    if args.set:
        return set_setting(args.set[0], args.set[1], testing)
    if args.set_gps_device:
        return set_gps_device(testing)
    if args.timeout is None:
        args.timeout = c("rms-fix-timeout") if args.rms_start else c("fix-timeout")
    if args.rms_start:
        # Never let a problem here stop the RMS gateway from starting
        try:
            return run(args, testing)
        except Exception as exc:          # noqa: BLE001
            log(f"RMS start update failed, RMS starts anyway: {exc}")
            return 0
    return run(args, testing)


def run(args, testing):
    log(f"digipi-gps-position {VERSION}" + (" (RMS start)" if args.rms_start else ""))
    if args.record_install:
        with Writable(testing):
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
        fix = (parts[0], parts[1], parts[2] if len(parts) > 2 else None)
    else:
        log(f"Waiting up to {args.timeout} s for a GPS fix ...")
        fix = read_gps(args.timeout)

    if fix is None:
        log("No GPS fix; keeping the current position.")
        status["result"] = "no fix"
        write_status(status)
    else:
        lat, lon, alt = fix
        log(f"GPS position {lat:.6f}, {lon:.6f}" + (f", {alt:.0f} m" if alt is not None else ""))
        altitude_note(alt)
        status.update(lat=lat, lon=lon, alt_m=alt, grid=maidenhead(lat, lon))
        check_and_update(args, testing, lat, lon, alt, status)

    if args.watch and not args.rms_start and not args.dry_run:
        watch(args, testing, status)
    return 0


if __name__ == "__main__":
    sys.exit(main())
