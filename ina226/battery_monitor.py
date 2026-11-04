#!/usr/bin/env python3
"""
LiFePO4 battery monitor for Raspberry Pi + INA226.
Version 1.6 - 2026-10-27

Changes:
  1.6  Writes latest reading to /dev/shm/battery_now.json for APRS telemetry
  1.5  Survives sensor dropouts: waits and retries instead of crashing
  1.4  Read-only filesystem fallback to /tmp (DigiPi), clean Ctrl-C exit
  1.3  Ignore readings below 9 V as wiring faults (no false shutdowns)
  1.2  INA226 moved to software I2C bus 3 (GPIO 23/24, pins 16/18)
  1.1  Safe Pi shutdown on low battery
  1.0  First release

- Reads battery voltage and current (charge / load)
- Counts amp-hours in and out (coulomb counting) to track state of charge
- Re-syncs to 100% automatically when the battery reaches full
- Prints a live status line and logs to CSV once a minute

Sign convention in output:  + amps = charging,  - amps = discharging (load)

Requires:  sudo apt install python3-smbus2   (or: pip3 install smbus2)
"""

import csv
import json
import os
import time
from datetime import datetime

from smbus2 import SMBus

VERSION = "1.6"

# ------------------------------------------------------------------ settings
I2C_BUS = 3             # software I2C bus on GPIO 23/24 (pins 16/18); RTC stays on bus 1
ADDR = 0x40             # A0/A1 both to GND = 0x40 (check with: i2cdetect -y 3)

R_SHUNT = 0.002         # ohms - READ THE SHUNT ON YOUR BOARD:
                        #   R002 = 0.002 (20 A boards)  R010 = 0.010  R100 = 0.100
CAPACITY_AH = 10.0      # battery rated capacity
INTERVAL = 2.0          # seconds between readings

CURRENT_OFFSET = 0.0    # amps; set after a no-load zero test (see notes)
INVERT = False          # set True if charging shows as negative

CHARGE_EFF = 0.99       # LiFePO4 coulombic efficiency
FULL_V = 14.0           # above this voltage while charging...
FULL_TAIL_A = 0.5       # ...with charge current below this (C/20)...
FULL_HOLD_S = 120       # ...for this many seconds -> battery is 100%
EMPTY_V = 11.5          # below this under load -> battery is essentially empty

# Safe shutdown of the Pi before the battery BMS cuts power (protects SD card)
SHUTDOWN_ENABLED = True
SHUTDOWN_SOC = 5.0      # percent
SHUTDOWN_V = 12.0       # or below this voltage while discharging
SHUTDOWN_HOLD_S = 60    # condition must last this long (ignores TX dips)
SANE_MIN_V = 9.0        # readings below this mean a wiring fault, not a flat battery

RETRY_S = 2.0           # seconds between retries when the sensor stops answering
MAX_GAP_S = 300         # dropouts shorter than this are filled in with the last current

STATE_FILE = os.path.expanduser("~/battery_state.json")
LOG_FILE = os.path.expanduser("~/battery_log.csv")
LOG_EVERY = 60          # seconds between CSV rows
FALLBACK_DIR = "/tmp"   # used if home is read-only (DigiPi); /tmp is cleared on reboot
STATUS_FILE = "/dev/shm/battery_now.json"   # latest reading, for APRS telemetry

# Resting (no load, no charge, settled 1 h+) voltage -> SoC for a 4S LiFePO4.
# Only used for a first guess when there is no saved state.
REST_TABLE = [
    (10.00, 0), (12.00, 2), (12.50, 5), (12.80, 10), (12.90, 15),
    (13.00, 20), (13.05, 30), (13.10, 40), (13.15, 50), (13.20, 60),
    (13.25, 70), (13.30, 80), (13.32, 90), (13.40, 95), (13.60, 100),
]

# ------------------------------------------------------------------ INA226
REG_CONFIG, REG_SHUNT, REG_BUS, REG_MFG_ID = 0x00, 0x01, 0x02, 0xFE
# 64-sample averaging, 8.244 ms conversions, continuous shunt+bus (~1 s per result)
CONFIG_VALUE = 0x47FF


def swap16(v):
    return ((v & 0xFF) << 8) | (v >> 8)


def read_reg(bus, reg):
    return swap16(bus.read_word_data(ADDR, reg))   # INA226 is MSB-first


def write_reg(bus, reg, value):
    bus.write_word_data(ADDR, reg, swap16(value))


def to_signed(v):
    return v - 0x10000 if v & 0x8000 else v


def read_ina226(bus):
    shunt_v = to_signed(read_reg(bus, REG_SHUNT)) * 2.5e-6   # 2.5 uV/bit
    bus_v = read_reg(bus, REG_BUS) * 1.25e-3                  # 1.25 mV/bit
    amps = shunt_v / R_SHUNT
    # Load current flowing IN+ -> IN- reads positive; flip so + = charging
    amps = -amps if not INVERT else amps
    amps -= CURRENT_OFFSET
    return bus_v, amps


# ------------------------------------------------------------------ SoC helpers
def soc_from_rest_voltage(v):
    if v <= REST_TABLE[0][0]:
        return 0.0
    for (v1, s1), (v2, s2) in zip(REST_TABLE, REST_TABLE[1:]):
        if v <= v2:
            return s1 + (s2 - s1) * (v - v1) / (v2 - v1)
    return 100.0


def fallback(path):
    """Same file name in /tmp - used when the home directory is read-only (DigiPi)."""
    return os.path.join(FALLBACK_DIR, os.path.basename(path))


_warned = set()


def warn_once(key, msg):
    if key not in _warned:
        print(msg, flush=True)
        _warned.add(key)


def load_state(volts):
    # Use whichever saved copy (home or /tmp) is newest
    best = None
    for path in (STATE_FILE, fallback(STATE_FILE)):
        try:
            with open(path) as f:
                data = json.load(f)
            ah = float(data["ah_remaining"])
            saved = data.get("saved", "")
            if best is None or saved > best[1]:
                best = (ah, saved, path)
        except (OSError, ValueError, KeyError):
            pass
    if best:
        print(f"Loaded saved state: {best[0]:.2f} Ah from {best[2]}")
        return best[0]
    soc = soc_from_rest_voltage(volts)
    print(f"No saved state - estimating {soc:.0f}% from {volts:.2f} V "
          "(accurate only if battery has been resting)")
    return CAPACITY_AH * soc / 100.0


def save_state(ah):
    data = {"ah_remaining": ah, "saved": datetime.now().isoformat()}
    for path in (STATE_FILE, fallback(STATE_FILE)):
        try:
            tmp = path + ".tmp"
            with open(tmp, "w") as f:
                json.dump(data, f)
            os.replace(tmp, path)
            return
        except OSError:
            warn_once("state", f"Can't write {path} (read-only?) - using {FALLBACK_DIR}")


def write_status(volts, amps, watts, soc, ah):
    """Latest reading in RAM (/dev/shm) for other programs such as APRS telemetry."""
    data = {"time": time.time(), "volts": round(volts, 3), "amps": round(amps, 3),
            "watts": round(watts, 2), "soc": round(soc, 1), "ah": round(ah, 3),
            "capacity_ah": CAPACITY_AH, "version": VERSION}
    try:
        tmp = STATUS_FILE + ".tmp"
        with open(tmp, "w") as f:
            json.dump(data, f)
        os.replace(tmp, STATUS_FILE)
    except OSError:
        warn_once("status", f"Can't write {STATUS_FILE}")


def append_log(row):
    for path in (LOG_FILE, fallback(LOG_FILE)):
        try:
            new = not os.path.exists(path)
            with open(path, "a", newline="") as f:
                w = csv.writer(f)
                if new:
                    w.writerow(["timestamp", "volts", "amps", "watts", "soc_pct", "ah_remaining"])
                w.writerow(row)
            return
        except OSError:
            warn_once("log", f"Can't write {path} (read-only?) - using {FALLBACK_DIR}")


def connect(bus):
    """Wait until the INA226 answers, then (re)apply its configuration.
    Re-configuring is needed because a power glitch resets the chip."""
    tries = 0
    while True:
        try:
            mfg = read_reg(bus, REG_MFG_ID)
            if mfg != 0x5449:
                raise SystemExit(f"Device at 0x{ADDR:02X} is not an INA226 (id 0x{mfg:04X})")
            write_reg(bus, REG_CONFIG, CONFIG_VALUE)
            time.sleep(1.2)
            if tries:
                print(f"INA226 back online after {tries} retries", flush=True)
            return
        except OSError as e:
            if tries % 30 == 0:           # don't flood the log: about once a minute
                print(f"INA226 not responding on bus {I2C_BUS} ({e}) - "
                      "check VCC/GND/SDA/SCL wires. Retrying...", flush=True)
            tries += 1
            time.sleep(RETRY_S)


# ------------------------------------------------------------------ main
def main():
    print(f"Battery monitor v{VERSION}  (INA226 0x{ADDR:02X} on I2C bus {I2C_BUS})", flush=True)
    with SMBus(I2C_BUS) as bus:
        connect(bus)                      # waits until the sensor answers
        volts, amps = read_ina226(bus)
        ah = load_state(volts)

        last = time.monotonic()
        last_log = last_save = 0.0
        full_since = None
        low_since = None
        last_amps = amps

        while True:
            time.sleep(INTERVAL)
            try:
                volts, amps = read_ina226(bus)
            except OSError as e:
                # Sensor dropped out (loose wire, noise) - wait for it, don't crash
                print(f"Sensor read failed ({e}) - waiting for INA226...", flush=True)
                save_state(ah)
                gap_start = time.monotonic()
                connect(bus)
                gap = time.monotonic() - gap_start
                if gap <= MAX_GAP_S:
                    # short gap: assume the current stayed at its last value
                    ah += last_amps * gap / 3600.0
                else:
                    print(f"Gap of {gap / 60:.0f} min not counted - charge level "
                          "may be off until the next full charge", flush=True)
                last = time.monotonic()
                continue
            now = time.monotonic()
            dt_h = (now - last) / 3600.0
            last = now
            last_amps = amps

            # Coulomb counting
            ah += amps * dt_h * (CHARGE_EFF if amps > 0 else 1.0)

            # Full detection: high voltage + charge current tapered off
            if volts >= FULL_V and 0 < amps < FULL_TAIL_A:
                full_since = full_since or now
                if now - full_since >= FULL_HOLD_S:
                    ah = CAPACITY_AH
            else:
                full_since = None

            # Empty detection
            if volts < EMPTY_V and amps < 0:
                ah = min(ah, CAPACITY_AH * 0.02)

            ah = max(0.0, min(CAPACITY_AH, ah))
            soc = 100.0 * ah / CAPACITY_AH
            watts = volts * amps

            if amps < -0.05:
                status = f"~{ah / -amps:5.1f} h left"
            elif amps > 0.05:
                status = f"charging, full in ~{(CAPACITY_AH - ah) / amps:4.1f} h"
            else:
                status = "idle"

            print(f"{datetime.now():%H:%M:%S}  {volts:6.2f} V  {amps:+7.3f} A  "
                  f"{watts:+7.2f} W  SoC {soc:5.1f}%  ({ah:5.2f} Ah)  {status}",
                  flush=True)

            write_status(volts, amps, watts, soc, ah)

            if now - last_log >= LOG_EVERY:
                append_log([datetime.now().isoformat(timespec="seconds"),
                            f"{volts:.3f}", f"{amps:.3f}", f"{watts:.2f}",
                            f"{soc:.1f}", f"{ah:.3f}"])
                last_log = now
            if now - last_save >= 60:
                save_state(ah)
                last_save = now

            # Low battery -> clean shutdown
            if volts < SANE_MIN_V:
                print(f"WARNING: {volts:.2f} V is not a real battery voltage - "
                      "check battery/VBUS wiring. Shutdown check skipped.", flush=True)
                low_since = None
            elif SHUTDOWN_ENABLED and amps < 0 and (soc <= SHUTDOWN_SOC or volts <= SHUTDOWN_V):
                low_since = low_since or now
                if now - low_since >= SHUTDOWN_HOLD_S:
                    print("LOW BATTERY - shutting down Pi", flush=True)
                    save_state(ah)
                    os.system("sudo /sbin/shutdown -h now")
                    return
            else:
                low_since = None


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nStopped.")
