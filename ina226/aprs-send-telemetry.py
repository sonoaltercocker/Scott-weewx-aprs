#!/usr/bin/env python3
"""
aprs-send-telemetry.py - send battery status as APRS telemetry
Version 1.3 - 2026-10-28

Changes:
  1.3  Clear message (no traceback) when Direwolf isn't running
  1.2  One-line-per-send log in /dev/shm/aprs-send.log (last 200 lines)
  1.1  RF-first: definitions go over RF; APRS-IS only when the internet is up
  1.0  First release

Reads the battery monitor's latest reading (/dev/shm/battery_now.json) and
sends a standard APRS telemetry packet (T#) over RF through Direwolf
(kissutil), where an iGate carries it to APRS-IS. If the station also has
internet, it is sent directly to APRS-IS as well.

Callsign and passcode are read from /usr/local/bin/aprs-send-weather.sh,
so the same file works on every installation without editing.

Telemetry channels (aprs.fi graphs these automatically):
  A1  Battery voltage   10.00 - 15.10 V   (0.02 V steps)
  A2  Net current       -5.00 - +5.20 A   (0.04 A steps, + = charging)
  A3  State of charge   0 - 100 %
  A4  Pi CPU temp       0 - 127.5 C       (0.5 C steps)
  A5  Net power         -70 - +83 W       (0.6 W steps)
  B1  Charging      B2  Low battery (<= 20 %)
  B3  Data stale / sensor fault      B4  Full (>= 99.5 %)

Usage:
  aprs-send-telemetry.py              send data (and definitions when due)
  aprs-send-telemetry.py --dry-run    print the packets, send nothing
  aprs-send-telemetry.py --defs       force sending the definitions now
  aprs-send-telemetry.py --no-rf      APRS-IS only
"""

import json
import os
import re
import socket
import subprocess
import sys
import time

# ------------------------------------------------------------------ settings
WEATHER_SCRIPT = "/usr/local/bin/aprs-send-weather.sh"   # source of USER / PASS
USER = None              # set here to override, e.g. "N0CALL-3"
PASS = None              # set here to override

STATUS_FILE = "/dev/shm/battery_now.json"
STALE_S = 120            # reading older than this = sensor fault
SEQ_FILE = "/dev/shm/aprs_telem_seq"
DEFS_EVERY = 12          # send PARM/UNIT/EQNS/BITS every Nth run (12 x 10 min = 2 h)

APRSIS_HOST = "noam.aprs2.net"
APRSIS_PORT = 14580
SEND_APRSIS = "auto"     # "auto" = use APRS-IS only if the internet is reachable,
                         # True = always try, False = never (RF-only station)
DIREWOLF_HOST = "localhost"
DIREWOLF_KISS_PORT = 8001  # Direwolf's default KISS TCP port (kissutil uses it)
RF_PATH = "WIDE1-1"
SEND_RF = True           # telemetry data over RF
DEFS_RF = True           # definitions over RF too - REQUIRED when the station has
                         # no internet, so iGates carry them to aprs.fi
TITLE = "Battery Monitor"
LOG_FILE = "/dev/shm/aprs-send.log"    # shared with aprs-send-weather.sh
LOG_KEEP = 200                          # lines kept

# name, unit, (a, b, c) where value = a*x^2 + b*x + c,  x = 0..255
CHANNELS = [
    ("Batt",  "Volts", (0, 0.02, 10)),
    ("Curr",  "Amps",  (0, 0.04, -5)),
    ("SoC",   "%",     (0, 1, 0)),
    ("CPU",   "degC",  (0, 0.5, 0)),
    ("Power", "Watts", (0, 0.6, -70)),
]
BITS = [("Chrg", "on"), ("Low", "on"), ("Fault", "on"), ("Full", "on")]
LOW_SOC = 20.0
FULL_SOC = 99.5
VERSION = "1.3"


# ------------------------------------------------------------------ helpers
def load_login():
    user, pw = USER, PASS
    if user and pw:
        return user, pw
    try:
        text = open(WEATHER_SCRIPT).read()
        user = user or re.search(r'^USER="([^"]+)"', text, re.M).group(1)
        pw = pw or re.search(r'^PASS="([^"]+)"', text, re.M).group(1)
    except (OSError, AttributeError):
        sys.exit(f"Can't read USER/PASS from {WEATHER_SCRIPT} - set them at the top of this script")
    return user, pw


def encode(value, eqn):
    """Real value -> 0..255 raw count using the channel's linear equation."""
    _, b, c = eqn
    return max(0, min(255, round((value - c) / b)))


def cpu_temp():
    try:
        return int(open("/sys/class/thermal/thermal_zone0/temp").read()) / 1000.0
    except (OSError, ValueError):
        return 0.0


def next_seq():
    try:
        seq = (int(open(SEQ_FILE).read()) + 1) % 1000
    except (OSError, ValueError):
        seq = 0
    try:
        with open(SEQ_FILE, "w") as f:
            f.write(str(seq))
    except OSError:
        pass
    return seq


def message(user, text):
    """Telemetry definitions are APRS messages addressed to our own callsign."""
    return f":{user:<9}:{text}"


def definitions(user):
    names = ",".join([n for n, _, _ in CHANNELS] + [n for n, _ in BITS])
    units = ",".join([u for _, u, _ in CHANNELS] + [u for _, u in BITS])
    eqns = ",".join(f"{a:g},{b:g},{c:g}" for _, _, (a, b, c) in CHANNELS)
    sense = "1" * 8
    return [message(user, f"PARM.{names}"),
            message(user, f"UNIT.{units}"),
            message(user, f"EQNS.{eqns}"),
            message(user, f"BITS.{sense},{TITLE}")]


def data_packet(seq):
    try:
        s = json.load(open(STATUS_FILE))
        stale = time.time() - s["time"] > STALE_S
    except (OSError, ValueError, KeyError):
        s, stale = {"volts": 0, "amps": 0, "soc": 0, "watts": 0}, True

    values = [s["volts"], s["amps"], s["soc"], cpu_temp(), s["watts"]]
    analog = ",".join(f"{encode(v, ch[2]):03d}" for v, ch in zip(values, CHANNELS))
    bits = [
        not stale and s["amps"] > 0.05,       # charging
        not stale and s["soc"] <= LOW_SOC,    # low battery
        stale,                                 # sensor fault / monitor not running
        not stale and s["soc"] >= FULL_SOC,   # full
    ]
    bitstr = "".join("1" if b else "0" for b in bits).ljust(8, "0")
    summary = ("STALE" if stale else
               f"{s['volts']:.2f} V {s['amps']:+.2f} A {s['soc']:.0f}% "
               f"CPU {values[3]:.1f} C")
    return f"T#{seq:03d},{analog},{bitstr}", summary


def send_aprsis(user, pw, infos):
    lines = "".join(f"{user}>APRS,TCPIP*:{i}\r\n" for i in infos)
    with socket.create_connection((APRSIS_HOST, APRSIS_PORT), timeout=15) as sock:
        sock.recv(512)                                   # server banner
        sock.sendall(f"user {user} pass {pw} vers aprs-send-telemetry {VERSION}\r\n".encode())
        time.sleep(2)
        sock.recv(512)                                   # logresp
        sock.sendall(lines.encode())
        time.sleep(2)


def log_line(text):
    """One line per send in a small RAM log, trimmed to the last LOG_KEEP lines."""
    try:
        try:
            lines = open(LOG_FILE).read().splitlines()
        except OSError:
            lines = []
        lines.append(f"{time.strftime('%Y-%m-%d %H:%M:%S')}  {text}")
        with open(LOG_FILE, "w") as f:
            f.write("\n".join(lines[-LOG_KEEP:]) + "\n")
    except OSError:
        pass


def internet_up():
    """Quick check: can we resolve and reach the APRS-IS server?"""
    try:
        socket.create_connection((APRSIS_HOST, APRSIS_PORT), timeout=5).close()
        return True
    except OSError:
        return False


def direwolf_up():
    """Is Direwolf's KISS TCP port accepting connections?"""
    try:
        socket.create_connection((DIREWOLF_HOST, DIREWOLF_KISS_PORT), timeout=3).close()
        return True
    except OSError:
        return False


def send_rf(user, infos):
    if not direwolf_up():
        raise OSError(f"Direwolf not running (no KISS port {DIREWOLF_KISS_PORT} on {DIREWOLF_HOST})")
    proc = subprocess.Popen(["kissutil", "-h", DIREWOLF_HOST], stdin=subprocess.PIPE,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, text=True)
    try:
        time.sleep(5)                                    # let kissutil connect
        if proc.poll() is not None:
            raise OSError("kissutil exited early - could not connect to Direwolf")
        for i in infos:
            proc.stdin.write(f"{user}>APRS,{RF_PATH}:{i}\n")
            proc.stdin.flush()
            time.sleep(2)                                # space packets on the channel
    except BrokenPipeError:
        raise OSError("kissutil closed the connection - is Direwolf running?")
    finally:
        try:
            proc.stdin.close()
        except OSError:
            pass
        try:
            proc.wait(timeout=30)
        except subprocess.TimeoutExpired:
            proc.kill()


# ------------------------------------------------------------------ main
def main():
    args = set(sys.argv[1:])
    dry = "--dry-run" in args
    user, pw = load_login()

    seq = next_seq()
    tpkt, summary = data_packet(seq)
    send_defs = "--defs" in args or seq % DEFS_EVERY == 0
    defs = definitions(user) if send_defs else []

    print(f"Telemetry #{seq:03d}: {summary}")
    for i in defs + [tpkt]:
        print(f"  {user}>APRS:{i}")
    if dry:
        print("Dry run - nothing sent.")
        return

    use_is = SEND_APRSIS is True or (SEND_APRSIS == "auto" and internet_up())
    if use_is:
        try:
            send_aprsis(user, pw, defs + [tpkt])
            is_status = "sent"
            print("Sent to APRS-IS.")
        except OSError as e:
            is_status = "failed"
            print(f"APRS-IS failed: {e}")
    elif SEND_APRSIS is False:
        is_status = "off"
    else:
        is_status = "no internet"
        print("No internet - RF only (iGates will carry it to APRS-IS).")

    rf_status = "off"
    if SEND_RF and "--no-rf" not in args:
        try:
            send_rf(user, (defs if DEFS_RF else []) + [tpkt])
            rf_status = "sent"
            print("Sent to radio.")
        except (OSError, subprocess.SubprocessError) as e:
            rf_status = "failed"
            print(f"RF send failed: {e}")

    tag = f"telemetry #{seq:03d}" + (" +defs" if defs else "")
    log_line(f"{tag:<20}  APRS-IS: {is_status:<12}  RF: {rf_status:<7}  {summary}")


if __name__ == "__main__":
    main()
