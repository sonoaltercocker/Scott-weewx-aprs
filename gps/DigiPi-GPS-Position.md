# DigiPi GPS Position Updater

When a DigiPi installation is performed, it is assumed the Raspberry Pi will not be moved from its initial installed position. This is often not a true assumption and thus automated tools are needed to update position information if the DigiPi is moved. This document describes an add-on that reads the GPS every time the Pi starts. If the station has moved, it updates the position everywhere DigiPi keeps it, and in WeeWX too if WeeWX is installed. Nothing needs to be done when you move the station except power it up where the GPS can see the sky.

**Version:** 1.3

**Works on:** any Raspberry Pi running DigiPi, with a GPS receiver that DigiPi's `gpsd` can read.
**WeeWX:** optional. With WeeWX installed its position is kept up to date as well; without it, only DigiPi is updated. The same files work either way.

---

## Why GPS updates are needed

DigiPi asks for your latitude, longitude and grid square **once**, when you press **Initialize** on its setup page. It copies them into a dozen config files and never looks at them again. DigiPi's own notes advise against running Initialize a second time, so after a move the only way to correct the position is to edit those files by hand, on a read-only filesystem, without missing one.

That is fine for a station that never moves. A DigiPi that goes portable, to a field day, an emergency deployment or a new weather site, keeps telling the world it is still at the old address:

- **APRS beacons** from the digipeater and iGate modes put the station on [aprs.fi](https://aprs.fi) and other maps at the old position. Other operators judge coverage and paths from that.
- **Winlink.** The RMS gateway's listing and Pat's position use the grid square. Winlink users choose a gateway by its location.
- **WSJT-X and JS8Call** send your grid square in every exchange, and other stations log it.
- **The DigiPi display** works out the distance and bearing to each station heard from your position, so all of those figures are wrong.
- **WeeWX**, if installed, stamps its weather reports with the station's position, so the APRS weather beacon shows the weather at the wrong place. WeeWX can also use the altitude when it works out sea-level barometric pressure.

In the field there is often no internet to look up coordinates either. A GPS already knows where the station is; this add-on simply copies that into every place DigiPi and WeeWX need it, at every boot.

---

## How it works

1. You flash and **initialize DigiPi as normal**, typing in a position on the setup page.
2. You install this add-on once (below).
3. At **every boot** after that, a service starts in the background and waits for the GPS to get a fix (up to 10 minutes). It takes 10 readings and uses the middle one.
4. It compares the GPS with the position saved in DigiPi, and in WeeWX if installed. If the GPS position appears to have changed by more than **100 m**, the script will:
   - stops the DigiPi mode that is running (TNC, digipeater, Winlink and so on),
   - writes the new position into every file listed below,
   - starts that mode again and restarts WeeWX if it is running.
5. It records what it did in the system log, and adds a line to the position history file, `/home/pi/gps-position-history.txt`.

Because it runs in the background, a slow GPS never holds up the rest of the boot. Until the fix arrives, the station uses the position it had before.

### What gets updated

| Program | File | Setting |
|---|---|---|
| Direwolf (TNC, digipeater, iGate modes) | `/home/pi/direwolf*.conf` | `lat=` and `long=` on the `PBEACON` lines |
| DigiPi display and start scripts | `/home/pi/localize.env` | `NEWLAT`, `NEWLON`, `NEWGRID` (and the matching `OLD...` lines) |
| APRSD web chat | `/home/pi/config/aprsd/aprsd.conf` | `latitude`, `longitude` |
| Direwolf dashboard | `/home/pi/config/direwolf-dashboard/config.yaml` | `latitude`, `longitude` |
| Pat (Winlink) | `/home/pi/config/pat/config.json` | `locator` (6-character grid) |
| Winlink RMS gateway | `/usr/local/etc/rmsgw/gateway.conf`, `sysop.xml`, `channels.xml` | grid square |
| WSJT-X and JS8Call | `/home/pi/config/WSJT-X.ini`, `JS8Call.ini` | `MyGrid` (4-character grid) |
| WeeWX, if installed | `/etc/weewx/weewx.conf` or `/home/pi/weewx-data/weewx.conf` | `[Station]` `latitude`, `longitude`, `altitude` |

The weather packet made by the weewx-aprs extension takes its position from WeeWX's `[Station]` settings, so APRS weather beacons follow the GPS too.

DigiPi's **Tracker** mode is not changed. It already beacons the live GPS position.

### When it changes nothing

- **DigiPi has not been initialized** yet. Initialize first, as normal.
- **No GPS fix within 10 minutes**, for example indoors. The previous position is kept until the next boot.
- **The station has moved less than 100 m.** Normal GPS wander does not rewrite the files at every boot.
- **WeeWX altitude** is changed only if it is more than 30 m off, because GPS altitude wanders more than position.

---

## Files

| File | Installed as | What it is |
|---|---|---|
| `digipi-gps-position.py` | `/usr/local/bin/digipi-gps-position.py` | The program that reads the GPS and updates the files |
| `digipi-gps-position.service` | `/etc/systemd/system/digipi-gps-position.service` | Runs the program at every boot |
| `install-gps-position.sh` | (not installed) | Installs the two files above and turns the service on |
| `DigiPi-GPS-Position.md` | (not installed) | This guide |

All four come in `digipi-gps-position.zip`. The program also creates `/home/pi/gps-position-history.txt`, its record of every position change.

---

## Before you start

1. **DigiPi is flashed and initialized**, and you can log in over SSH as `pi`.
2. **The GPS is plugged in** and its antenna can see the sky.
3. **DigiPi's GPS device is set.** On the DigiPi setup page this is the **GPS Device** field, for example `ttyACM1` or `ttyUSB0`. It ends up on the `DEVICES` line of `/etc/default/gpsd`. A name from `/dev/serial/by-id/` is safest, because it doesn't change when other USB devices are plugged in.
4. **The GPS works.** On the Pi run `cgps` (press **q** to quit). It should show a **3D FIX** with a latitude and longitude. The **GPS** link on the DigiPi web page shows the same thing.

---

## Install

### Step 1 — Copy the zip from your computer to the Pi

Download `digipi-gps-position.zip` from the [Scott-weewx-aprs repository](https://github.com/sonoaltercocker/Scott-weewx-aprs/tree/main/gps). Your computer saves it in its **Downloads** folder. Then follow the steps for your computer: a **Mac** or a **Windows 11 PC**.

On a Mac, open **Terminal** and unzip it:

```bash
cd ~/Downloads
unzip -o digipi-gps-position.zip
```

This makes a `digipi-gps-position` folder. Safari often unzips downloads by itself; if the folder is already there, skip the `unzip` command.

DigiPi keeps its filesystem read-only, so make it writable, then copy the folder to the Pi. Replace `<pi-address>` with your Pi's address, for example `10.0.0.5` when you are on the DigiPi hotspot, its address on your home network, or `digipi.local`:

```bash
ssh pi@<pi-address> sudo remount
scp -r ~/Downloads/digipi-gps-position pi@<pi-address>:~/
```

If you have an entry for the Pi in `~/.ssh/config`, you can use its name instead of `pi@<pi-address>`.

On a Windows 11 PC, open **PowerShell** (right-click the **Start** button, then choose **Terminal**). Windows 11 has `ssh` and `scp` built in. Unzip the file and copy it to the Pi, replacing `<pi-address>` as above and leaving out the `<` and `>`, which PowerShell treats as special characters:

```powershell
cd $HOME\Downloads
Expand-Archive -Force digipi-gps-position.zip -DestinationPath .
ssh pi@<pi-address> sudo remount
scp -r $HOME\Downloads\digipi-gps-position pi@<pi-address>:~/
```

If you unzip with File Explorer's **Extract All** instead, it puts the files one folder deeper, in `Downloads\digipi-gps-position\digipi-gps-position`. Copy that inner folder to the Pi.

The first time you connect, `ssh` asks you to confirm the Pi's key: type `yes`. An entry for the Pi in `C:\Users\<you>\.ssh\config` works the same way as on a Mac.

Don't open the scripts in Notepad and save them. Notepad can change their line endings, and the Pi then can't run them.

### Step 2 — Run the installer on the Pi

Log in to the Pi from Terminal on a Mac or PowerShell on Windows, and run the installer:

```bash
ssh pi@<pi-address>
cd ~/digipi-gps-position
sudo bash install-gps-position.sh
```

The installer copies the program and the service into place, turns the service on, writes the first line of the position history, and then shows:

- the GPS device `gpsd` is set to read. Check that it is your GPS.
- the serial devices it can see, by their `/dev/serial/by-id/` names.
- whether **WeeWX was found**. If not, only DigiPi is updated; if you install WeeWX later, it is picked up at the next boot with no need to install this again.

### Step 3 — Try it without changing anything

```bash
sudo /usr/local/bin/digipi-gps-position.py --dry-run --force
```

After the GPS gets a fix, this lists every line it *would* change, with the old line marked `-` and the new one `+`. Nothing is written.

### Step 4 — Reboot

```bash
sudo reboot
```

The Pi comes back read-only, and from now on the position is checked at every boot.

---

## Testing a move

1. **Before moving, look at the position history** on the Pi:

   ```bash
   cat /home/pi/gps-position-history.txt
   ```

   The last line is the position the station has now: the `installed` line on a new install, or the latest `updated` line. There's nothing to write down; the file keeps the record.

2. **Shut down** before moving the station:

   ```bash
   sudo shutdown -h now
   ```

3. **Move the station more than 100 m** and power it up where the GPS antenna can see the sky.

4. **Wait a few minutes**, then check the result:

   ```bash
   cat /run/digipi-gps-position.json
   ```

   - `"result": "updated"`: the position was changed, and `files` lists what was updated.
   - `"result": "unchanged"`: the station is within 100 m of its saved position.
   - `"result": "no fix"`: the GPS did not lock within 10 minutes.
   - **No file yet:** the service is still waiting for a fix.

5. **Look at the history again.** A new `updated` line shows the new position, grid square and altitude, and how far the station moved and from where:

   ```
   2026-11-06 14:05  installed  33.7748, -84.2963  EM73us  WeeWX 33.7748, -84.2963  (version 1.3)
   2026-11-08 09:12  updated    33.8320, -84.2682  EM73ut  275 m  moved 6870 m from 33.7748, -84.2963 EM73us
   ```

   To see the values in the config files themselves:

   ```bash
   grep -E "^NEW(LAT|LON|GRID)" /home/pi/localize.env
   grep -A4 "^\[Station\]" /etc/weewx/weewx.conf
   ```

   The second command is only for stations with WeeWX. On a pip install of WeeWX the file is `/home/pi/weewx-data/weewx.conf`. You can also watch your next beacon on [aprs.fi](https://aprs.fi).

6. **Optional:** reboot without moving. The result should be `unchanged`, and no new line is added to the history.

---

## Logs

The program doesn't keep a log file of its own. What it prints goes to the system journal:

```bash
journalctl -u digipi-gps-position -b
```

`-b` shows only the current boot. A typical update looks like this:

```
digipi-gps-position 1.3
Waiting up to 600 s for a GPS fix ...
GPS position 33.832000, -84.268200, 275 m
DigiPi position 33.7748, -84.2963 (EM73us); 6870 m from GPS
WeeWX position 33.7748, -84.2963; 6870 m from GPS
Stopping tnc
  updated /home/pi/direwolf.tnc.conf
  ...
WeeWX found (/etc/weewx/weewx.conf); updating its [Station] position.
  updated /etc/weewx/weewx.conf
History: updated    33.8320, -84.2682  EM73ut  275 m  moved 6870 m from 33.7748, -84.2963 EM73us
Starting tnc
Restarting weewx
Position set to 33.8320, -84.2682 (EM73ut); 13 file(s) updated.
```

`/run/digipi-gps-position.json` holds the result of the latest run, and `systemctl status digipi-gps-position` shows whether it is still running.

> **Read the log before the next reboot.** On DigiPi the journal is usually kept in memory only, so a reboot clears it. `journalctl --list-boots` shows how many boots are kept.

### Position history

`/home/pi/gps-position-history.txt` is the lasting record. Unlike the journal it is kept on the SD card, so it survives reboots. It gets one line when the add-on is installed and one line each time the position is changed; boots where nothing moved add nothing.

```bash
cat /home/pi/gps-position-history.txt
```

| Line starts with | Meaning |
|---|---|
| `installed` | The position DigiPi (and WeeWX) had when the add-on was installed |
| `updated … moved … from …` | The station moved; the new position, grid square, altitude, and the old position |
| `updated … WeeWX position corrected from …` | DigiPi was right, but WeeWX had a different position, which was put right |
| `… (forced)` | The update was run by hand with `--force`, without a move |

---

## Running it by hand

| Command (as root, with `sudo`) | What it does |
|---|---|
| `digipi-gps-position.py` | Read the GPS and update if the station has moved |
| `digipi-gps-position.py --dry-run` | Show what would change; write nothing |
| `digipi-gps-position.py --force` | Update even if the station has not moved |
| `digipi-gps-position.py --timeout 60` | Wait at most 60 seconds for a fix |
| `digipi-gps-position.py --record-install` | Add an `installed` line with the current position to the history (the installer does this) |
| `digipi-gps-position.py --version` | Show the installed version |

Run `sudo remount` first if you run it by hand without `--dry-run`. At boot the program takes care of this itself.

## Settings

These are near the top of `/usr/local/bin/digipi-gps-position.py`:

| Setting | Default | Meaning |
|---|---|---|
| `FIX_TIMEOUT` | `600` | Seconds to wait for a GPS fix after boot |
| `FIX_SAMPLES` | `10` | Readings taken; the middle value is used |
| `MOVE_THRESHOLD_M` | `100` | Moves smaller than this, in metres, are ignored |
| `ALT_THRESHOLD_M` | `30` | WeeWX altitude is changed only if this far off, in metres |
| `DECIMALS` | `4` | Decimal places written for latitude and longitude (4 is about 11 m). Use `2` to publish a less exact position |

---

## Troubleshooting

| Symptom | What to check |
|---|---|
| **Always `no fix`** | Run `cgps`. No data at all means `gpsd` is reading the wrong device: check `DEVICES` in `/etc/default/gpsd`. Data but no fix means the antenna can't see enough sky |
| **GPS and radio fight over `ttyACM0`** | Both enumerate as `ttyACM…`. Put the GPS's `/dev/serial/by-id/` name in `/etc/default/gpsd` |
| **`DigiPi has not been initialized yet`** | Run DigiPi's Initialize from its setup page first |
| **The old position is beaconed right after boot** | Expected. Beacons sent before the GPS locks use the previous position; the new one follows once the fix arrives |
| **WeeWX shows an old position after its settings were rewritten** | Something reset WeeWX's `[Station]` position. This add-on puts the GPS position back at the next boot |
| **Changes vanish after a reboot** | A file was edited by hand without `sudo remount`. The add-on itself does this automatically |

## Version history

| Version | Date | Changes |
|---|---|---|
| 1.3 | 2026-11-06 | Keeps a position history in `/home/pi/gps-position-history.txt`: an `installed` line from the installer and one line per change |
| 1.2 | 2026-11-06 | Also checks WeeWX's saved position, so it is corrected at the next boot if something resets it. Version shown in the log and with `--version` |
| 1.1 | 2026-11-06 | Detects whether WeeWX is installed and says so in the log |
| 1.0 | 2026-11-06 | First release |

## Removing it

```bash
sudo remount
sudo systemctl disable digipi-gps-position
sudo rm /etc/systemd/system/digipi-gps-position.service /usr/local/bin/digipi-gps-position.py
sudo reboot
```

The position stays as it was last set. Edit the files by hand to change it after that. The position history stays too; delete `/home/pi/gps-position-history.txt` if you don't want to keep it.

---

*Scott Sheppard, KJ4ZZB*
