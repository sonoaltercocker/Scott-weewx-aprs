#!/bin/bash
#
# station-build.sh
#
# Turns a freshly flashed and Initialized DigiPi card into a complete
# APRS station:
#   - two Wi-Fi radios: onboard Wi-Fi on the home network (internet and
#     updates), USB adapter running the DigiPi hotspot (10.0.0.5) for the
#     GW1200 and field use
#   - a small /data partition for saved weather history and battery state
#   - clock: DS3231 RTC (Pi 3B+/4) or the Pi 5's built-in RTC, chrony
#     serving time to the weather network
#   - WeeWX 5 for an Ecowitt GW1200, database kept in RAM and saved to
#     /data four times a day and at every shutdown
#   - APRS weather packets with BGT/WBGT, sent over RF and APRS-IS
#   - INA226 battery monitor and APRS battery telemetry
#   - DigiPi GPS Position Updater 1.6
#   - shutdown button on GPIO26 (pin 37)
#   - boot report and a saved system journal on /data, so an unexpected
#     reboot or power loss can be traced afterwards
# Every add-on is installed by default; each can be switched off.
#
# Raspberry Pi 3B+, 4 or 5 with 1 GB of memory or more.
#
# HOW TO USE (on the home network - installs need internet)
#   sudo bash station-build.sh       answer the questions; reboot when told
#   sudo bash station-build.sh       again after the reboot, to finish
# Safe to run as many times as you like; finished steps are skipped.
# The answers are kept in /etc/station-build.conf.
#
# Scott Sheppard, KJ4ZZB
# https://github.com/sonoaltercocker/Scott-weewx-aprs
#
# Version 2.1 - 2026-11-11
#
# Changes:
#   2.1  2026-11-11  Boot report and saved journal on /data (BOOT_REPORT).
#                    A companion file already in place (for example
#                    battery_monitor.py when the script runs from the pi
#                    home folder) is no longer copied onto itself.
#                    INA226 check retries before warning.
#                    Backup over SSH shown at the end.
#   2.0  2026-11-09  First release of the single-script build.
#
SCRIPT_VERSION="2.1"

###########################################################################
# Fixed settings (the per-station answers are asked for when it runs)
###########################################################################
REPO_RAW="https://raw.githubusercontent.com/sonoaltercocker/Scott-weewx-aprs/main"
ECOWITT_REPO="https://github.com/WernerKr/Ecowitt-or-DAVIS-stations-and-Season-skin.git"
APRS_REPO="https://github.com/cavedon/weewx-aprs.git"

SETTINGS=/etc/station-build.conf
STATE_DIR=/var/local/station-build
WEEWX_CONF=/etc/weewx/weewx.conf
WEEWX_DIR=/var/lib/weewx               # RAM (tmpfs) once set up
WEEWX_DB=$WEEWX_DIR/weewx.sdb
WEEWX_HTML=/var/www/html/weewx         # RAM (tmpfs) once set up
FORMATTER=/etc/weewx/bin/user/aprs-formatter.py
DATA=/data
DATA_LABEL=stationdata
LOCALIZE_ENV=/home/pi/localize.env
LOCALIZED_FLAG=/var/cache/digipi/localized.txt
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MIN_DATE="2026-11-01"                  # the clock must be later than this

set -o pipefail

# ------------------------------------------------------------- helpers
c_ok=$'\e[32m'; c_warn=$'\e[33m'; c_err=$'\e[31m'; c_hd=$'\e[1;36m'; c_off=$'\e[0m'
step()  { echo; echo "${c_hd}== $*${c_off}"; }
ok()    { echo "   ${c_ok}OK${c_off}  $*"; }
note()  { echo "   ..  $*"; }
warn()  { echo "   ${c_warn}!!${c_off}  $*"; WARNINGS+=("$*"); }
die()   { echo; echo "${c_err}STOPPED:${c_off} $*"; echo; exit 1; }
WARNINGS=()

run() { "$@" || die "this command failed:  $*"; }

add_line() {   # file line : append unless already there
    grep -qxF -- "$2" "$1" 2>/dev/null || { echo "$2" >> "$1"; note "added to $1: $2"; CHANGED=1; }
}

done_flag() { [ -f "$STATE_DIR/$1" ]; }
set_flag()  { mkdir -p "$STATE_DIR" && chmod 700 "$STATE_DIR"; date > "$STATE_DIR/$1"; }
clear_flag(){ rm -f "$STATE_DIR/$1"; }
BOOT_ID="$(cat /proc/sys/kernel/random/boot_id)"
needs_reboot() { NEED_REBOOT=1; mkdir -p "$STATE_DIR"; echo "$BOOT_ID" > "$STATE_DIR/reboot-before"; }
reboot_pending() { [ "$(cat "$STATE_DIR/reboot-before" 2>/dev/null)" = "$BOOT_ID" ]; }

internet_up() { timeout 5 bash -c 'exec 3<>/dev/tcp/deb.debian.org/80' 2>/dev/null; }
need_internet() {
    internet_up || die "no internet connection.
    Installing software needs the home network: the onboard Wi-Fi must be joined to
    your home Wi-Fi (DigiPi's Wifi page). The DigiPi hotspot (10.0.0.x) has no internet."
}

# Set a value in weewx.conf, keeping comments:  conf_set Section.key value
conf_set() {
    python3 - "$WEEWX_CONF" "$1" "$2" <<'PY' || die "could not update weewx.conf ($1)"
import sys, configobj
path, dotted, value = sys.argv[1], sys.argv[2], sys.argv[3]
c = configobj.ConfigObj(path, encoding='utf-8', interpolation=False, file_error=True)
*sections, key = dotted.split('.')
d = c
for s in sections:
    if s not in d:
        d[s] = {}
    d = d[s]
if d.get(key) != value:
    d[key] = value
    c.write()
    print(f"   ..  weewx.conf: [{']['.join(sections)}] {key} = {value}")
PY
}

# Companion files: a copy next to this script wins, otherwise GitHub.
# If that copy IS the destination (script run from the same folder), it is
# already in place and is kept as it is.
fetch() {   # repo-path destination
    local name; name="$(basename "$1")"
    if [ -f "$SCRIPT_DIR/$name" ] && [ "$SCRIPT_DIR/$name" -ef "$2" ]; then
        note "$name: already in place, kept"
    elif [ -f "$SCRIPT_DIR/$name" ]; then
        run cp "$SCRIPT_DIR/$name" "$2"; note "$name: local copy"
    else
        run wget -q -O "$2" "$REPO_RAW/$1"; note "$name: downloaded from GitHub"
    fi
}

# APRS-IS passcode, calculated from the callsign (the SSID is ignored)
passcode() {
    python3 - "$1" <<'PY'
import sys
c = sys.argv[1].upper().split('-')[0]
h = 0x73e2
for i in range(0, len(c), 2):
    h ^= ord(c[i]) << 8
    if i + 1 < len(c):
        h ^= ord(c[i + 1])
print(h & 0x7fff)
PY
}

# ------------------------------------------------------------- questions
TTY=no; [ -r /dev/tty ] && [ -t 0 ] && TTY=yes
# (the helpers' own variables start with _ so they never hide the caller's)
ask() {   # VAR "question" default [regex] [hint]
    local _var="$1" _q="$2" _def="$3" _re="${4:-.*}" _hint="$5" _in
    while :; do
        read -r -p "   $_q [$_def]: " _in </dev/tty || die "no answer (no terminal)"
        _in="${_in:-$_def}"
        if [[ "$_in" =~ $_re ]]; then printf -v "$_var" '%s' "$_in"; return; fi
        echo "      ${c_warn}${_hint:-not valid, try again}${c_off}"
    done
}
_YN=""
ask_yn() {   # VAR "question" default(yes/no)
    ask _YN "$2 (yes/no)" "$3" '^([Yy]([Ee][Ss])?|[Nn][Oo]?)$' "answer yes or no"
    if [[ "$_YN" =~ ^[Yy] ]]; then printf -v "$1" yes; else printf -v "$1" no; fi
}
loc() { grep -m1 "^$1=" "$LOCALIZE_ENV" 2>/dev/null | cut -d= -f2- | tr -d '"'"'"; }

ask_settings() {
    local base
    base="$(loc NEWCALL)"; base="${base%%-*}"
    echo
    echo "   Station details. Press Enter to accept the value in [brackets]."
    echo
    ask CALLSIGN "APRS callsign-SSID for weather and telemetry" \
        "${CALLSIGN:-${base:+$base-3}}" '^[A-Za-z0-9]{3,7}-[0-9]{1,2}$' "callsign-SSID, for example WD5EMA-3"
    CALLSIGN="${CALLSIGN^^}"
    ask STATION_LOCATION "Station name (shown by WeeWX)" "${STATION_LOCATION:-$CALLSIGN weather}" '.+'
    ask LATITUDE  "Latitude, decimal degrees (south is minus)" \
        "${LATITUDE:-$(loc NEWLAT)}" '^-?[0-9]{1,2}(\.[0-9]+)?$' "for example 33.83194"
    ask LONGITUDE "Longitude, decimal degrees (west is minus)" \
        "${LONGITUDE:-$(loc NEWLON)}" '^-?[0-9]{1,3}(\.[0-9]+)?$' "for example -84.26809"
    ask ALTITUDE  "Altitude, number,foot or number,meter" \
        "${ALTITUDE:-0,foot}" '^[0-9]+(\.[0-9]+)?,(foot|meter)$' "for example 901,foot or 275,meter"
    ask TIMEZONE  "Time zone" "${TIMEZONE:-$(timedatectl show -p Timezone --value 2>/dev/null || cat /etc/timezone 2>/dev/null)}" \
        '^[A-Za-z_]+(/[A-Za-z0-9_+-]+)*$' "for example America/New_York"
    [ -e "/usr/share/zoneinfo/$TIMEZONE" ] || die "unknown time zone $TIMEZONE (list them with: timedatectl list-timezones)"
    echo
    echo "   Add-ons. All are installed by default."
    ask_yn INSTALL_WEEWX   "WeeWX weather station (GW1200) and APRS weather" "${INSTALL_WEEWX:-yes}"
    ask_yn INSTALL_BATTERY "INA226 battery monitor and APRS telemetry"        "${INSTALL_BATTERY:-yes}"
    if [ "$INSTALL_BATTERY" = yes ]; then
        ask BATTERY_AH "   Battery capacity, amp-hours" "${BATTERY_AH:-10.0}" '^[0-9]+(\.[0-9]+)?$'
    fi
    ask_yn INSTALL_RTC     "Real-time clock (DS3231, or the Pi 5's own)"     "${INSTALL_RTC:-yes}"
    ask_yn INSTALL_GPS     "GPS position updater"                            "${INSTALL_GPS:-yes}"
    ask_yn INSTALL_BUTTON  "Shutdown button on GPIO26 (pin 37)"              "${INSTALL_BUTTON:-yes}"
    ask_yn DUAL_RADIO      "USB Wi-Fi adapter runs the DigiPi hotspot"       "${DUAL_RADIO:-yes}"
    if [ "$DUAL_RADIO" = yes ]; then
        ask HOTSPOT_PSK "   New hotspot password (8-63 characters; Enter = keep the current one)" \
            "${HOTSPOT_PSK:-keep}" '^(keep|[^|&\\"$`]{8,63})$' "8 to 63 characters, without | & \\ \" \$ or \`"
    fi
}

save_settings() {
    umask 077
    cat > "$SETTINGS" <<EOF
# station-build.sh settings - written $(date '+%Y-%m-%d %H:%M')
# Edit here, or run the script again and answer "no" to "Use these settings?".
CALLSIGN="$CALLSIGN"
APRS_PASSCODE="$APRS_PASSCODE"
RF_PATH="$RF_PATH"
STATION_LOCATION="$STATION_LOCATION"
LATITUDE="$LATITUDE"
LONGITUDE="$LONGITUDE"
ALTITUDE="$ALTITUDE"
TIMEZONE="$TIMEZONE"
INSTALL_WEEWX="$INSTALL_WEEWX"
INSTALL_BATTERY="$INSTALL_BATTERY"
BATTERY_AH="$BATTERY_AH"
INSTALL_RTC="$INSTALL_RTC"
INSTALL_GPS="$INSTALL_GPS"
INSTALL_BUTTON="$INSTALL_BUTTON"
DUAL_RADIO="$DUAL_RADIO"
HOTSPOT_PSK="$HOTSPOT_PSK"
# Less often changed
WX_PORT="$WX_PORT"              # port in the GW1200's Customized upload
NTP_ALLOW="$NTP_ALLOW"          # network that may take its time from the Pi ("" = none)
WIFI_COUNTRY="$WIFI_COUNTRY"
DATA_PARTITION="$DATA_PARTITION" # /data partition for saved weather history and battery state
ROOT_GB="$ROOT_GB"              # grow the system partition to this size (never shrunk)
DATA_GB="$DATA_GB"              # size of /data
DO_UPGRADE="$DO_UPGRADE"        # apt upgrade on the first run
BOOT_REPORT="$BOOT_REPORT"      # boot report and saved journal on /data (needs the /data partition)
EOF
    umask 022
}

show_settings() {
    cat <<EOF
   Callsign          $CALLSIGN   (APRS-IS passcode $APRS_PASSCODE, RF path $RF_PATH)
   Station           $STATION_LOCATION
   Position          $LATITUDE, $LONGITUDE, $ALTITUDE    Time zone $TIMEZONE
   WeeWX + weather   $INSTALL_WEEWX        GW1200 upload port $WX_PORT
   Battery/telemetry $INSTALL_BATTERY$([ "$INSTALL_BATTERY" = yes ] && echo "        $BATTERY_AH Ah")
   RTC               $INSTALL_RTC
   GPS updater       $INSTALL_GPS
   Shutdown button   $INSTALL_BUTTON
   Two radios        $DUAL_RADIO$([ "$DUAL_RADIO" = yes ] && echo "        hotspot password: $HOTSPOT_PSK")
   /data partition   $DATA_PARTITION$([ "$DATA_PARTITION" = yes ] && echo "        system ${ROOT_GB} GB, /data ${DATA_GB} GB")
   Boot report       $BOOT_REPORT$([ "$DATA_PARTITION" != yes ] && echo "        (needs the /data partition)")
EOF
}

###########################################################################
# 0. Checks
###########################################################################
step "Station build ${SCRIPT_VERSION}"

[ "$(id -u)" -eq 0 ] || die "run it with sudo:  sudo bash $0"
PI_USER="${SUDO_USER:-pi}"; [ "$PI_USER" = root ] && PI_USER=pi
id "$PI_USER" >/dev/null 2>&1 || die "user '$PI_USER' not found. Run it with sudo from the pi account."
PI_HOME="$(getent passwd "$PI_USER" | cut -d: -f6)"

MODEL="$(tr -d '\0' < /proc/device-tree/model 2>/dev/null || echo unknown)"
MEM_MB=$(( $(awk '/MemTotal/ {print $2}' /proc/meminfo) / 1024 ))
note "Board:  $MODEL, ${MEM_MB} MB memory"
# 1 GB boards report a bit under 1024 MB (the GPU keeps some); 512 MB boards under 500
if [ "$MEM_MB" -lt 700 ]; then
    die "this board has ${MEM_MB} MB of memory. This station build needs a Raspberry Pi
    3B+, 4 or 5 with at least 1 GB, because the WeeWX database is kept in RAM.
    DigiPi itself runs on 512 MB boards (Pi 3A+, Zero 2 W), but not with this build."
fi
case "$MODEL" in
    *"Pi 3 Model B Plus"*|*"Pi 4"*|*"Pi 5"*) ;;   # includes Pi 400 and 500
    *) warn "untested board: $MODEL" ;;
esac
IS_PI5=no; [[ "$MODEL" == *"Pi 5"* ]] && IS_PI5=yes

command -v remount >/dev/null 2>&1 || die "this is not a DigiPi image ('remount' is missing).
    Flash the current DigiPi release, run its Initialize, then run this script."
[ -f "$LOCALIZED_FLAG" ] || [ -n "$(loc NEWCALL)" ] || die "DigiPi hasn't been Initialized yet.
    Open http://digipi/ , click Initialize, enter the station details, reboot, then run this again."
remount >/dev/null 2>&1
mount -o remount,rw / 2>/dev/null
touch /.station-build-test 2>/dev/null && rm -f /.station-build-test \
    || die "the filesystem is still read-only after 'remount'."

LOG="$PI_HOME/station-build.log"
exec > >(tee -a "$LOG") 2>&1
echo "---- $(date '+%Y-%m-%d %H:%M:%S')  station-build $SCRIPT_VERSION ----"
ok "DigiPi image: filesystem writable until the next reboot"

CONFIG_TXT=/boot/firmware/config.txt
[ -f "$CONFIG_TXT" ] || CONFIG_TXT=/boot/config.txt
[ -f "$CONFIG_TXT" ] || die "can't find config.txt"

###########################################################################
# Settings
###########################################################################
step "Station settings"
# Defaults for the less-often-changed ones
RF_PATH="WIDE1-1"; WX_PORT="9000"; NTP_ALLOW="10.0.0.0/24"; WIFI_COUNTRY="US"
DATA_PARTITION="yes"; ROOT_GB="12"; DATA_GB="4"; DO_UPGRADE="yes"; BOOT_REPORT="yes"
# shellcheck source=/dev/null
[ -f "$SETTINGS" ] && . "$SETTINGS"

if [ "$TTY" = yes ]; then
    if [ -f "$SETTINGS" ]; then
        show_settings
        ask_yn KEEP "Use these settings?" yes
        [ "$KEEP" = yes ] || ask_settings
    else
        ask_settings
    fi
else
    [ -f "$SETTINGS" ] || die "no terminal to ask questions, and no $SETTINGS yet. Run it from an SSH session."
fi
APRS_PASSCODE="$(passcode "$CALLSIGN")"
[ "$INSTALL_BATTERY" = yes ] || BATTERY_AH="${BATTERY_AH:-10.0}"
save_settings
ok "saved in $SETTINGS (APRS-IS passcode $APRS_PASSCODE)"

###########################################################################
# PASS 1: time zone, Wi-Fi, partitions, packages, config.txt
###########################################################################
step "Time zone"
[ "$(timedatectl show -p Timezone --value 2>/dev/null)" = "$TIMEZONE" ] || run timedatectl set-timezone "$TIMEZONE"
ok "time zone $TIMEZONE"

# ------------------------------------------------------------- Wi-Fi
step "Wi-Fi: home network on the onboard radio, DigiPi hotspot on the USB adapter"
NMDIR=/etc/NetworkManager/system-connections
HOT=$NMDIR/hotspot.nmconnection
HOME_W=$NMDIR/wlan0.nmconnection
ONBOARD_MAC=""; USB_MAC=""; USB_IF=""
for d in /sys/class/net/wlan*; do
    [ -e "$d/device/driver" ] || continue
    drv="$(basename "$(readlink "$d/device/driver")")"
    mac="$(tr 'a-f' 'A-F' < "$d/address")"
    if [ "$drv" = brcmfmac ]; then ONBOARD_MAC="$mac"; else USB_MAC="$mac"; USB_IF="$(basename "$d")"; fi
done
if [ "$DUAL_RADIO" != yes ]; then
    note "one radio: DigiPi's own hotspot behaviour is left as it is"
elif [ -z "$USB_MAC" ]; then
    warn "no USB Wi-Fi adapter found - plug it in and run the script again (hotspot left as it is)"
elif [ -z "$ONBOARD_MAC" ]; then
    warn "onboard Wi-Fi not found - hotspot left as it is"
else
    note "onboard radio $ONBOARD_MAC (home network), USB adapter $USB_IF $USB_MAC (hotspot)"
    NM_BEFORE="$(cat "$NMDIR"/*.nmconnection 2>/dev/null | md5sum)"
    if command -v raspi-config >/dev/null 2>&1 && \
       [ "$(raspi-config nonint get_wifi_country 2>/dev/null)" != "$WIFI_COUNTRY" ]; then
        raspi-config nonint do_wifi_country "$WIFI_COUNTRY" >/dev/null 2>&1 \
            && note "Wi-Fi country $WIFI_COUNTRY" || warn "could not set the Wi-Fi country"
    fi
    # dnsmasq lease files in RAM (the card is read-only)
    for i in wlan0 wlan1; do
        L=/var/lib/NetworkManager/dnsmasq-$i.leases
        [ "$(readlink "$L" 2>/dev/null)" = "/run/dnsmasq-$i.leases" ] || ln -sf "/run/dnsmasq-$i.leases" "$L"
        touch "/run/dnsmasq-$i.leases"
        if [ -f /etc/rc.local ] && ! grep -q "touch /run/dnsmasq-$i.leases" /etc/rc.local; then
            if grep -q "touch /run/dnsmasq-wlan0.leases" /etc/rc.local; then
                sed -i "0,/touch \/run\/dnsmasq-wlan0.leases/s||&\n  touch /run/dnsmasq-$i.leases|" /etc/rc.local
            else
                sed -i "0,/^exit 0/s||  touch /run/dnsmasq-$i.leases\nexit 0|" /etc/rc.local
            fi
            note "rc.local: touch /run/dnsmasq-$i.leases"
        fi
    done
    # Hotspot: tied to the USB adapter's MAC, started by NetworkManager at boot
    [ -f "$HOT" ] || die "can't find $HOT (DigiPi's hotspot profile)"
    mkdir -p "$STATE_DIR" && chmod 700 "$STATE_DIR"
    [ -f "$STATE_DIR/hotspot.nmconnection.orig" ] || cp -p "$HOT" "$STATE_DIR/hotspot.nmconnection.orig"
    sed -i '/^interface-name=/d; /^mac-address=/d' "$HOT"
    sed -i "/^\[wifi\]\$/a mac-address=$USB_MAC" "$HOT"
    if grep -q '^autoconnect=' "$HOT"; then sed -i 's/^autoconnect=.*/autoconnect=true/' "$HOT"
    else sed -i '/^\[connection\]$/a autoconnect=true' "$HOT"; fi
    grep -q '^band=bg' "$HOT" || warn "hotspot is not on 2.4 GHz (band=bg); the GW1200 needs 2.4 GHz"
    if [ "$HOTSPOT_PSK" != keep ]; then
        sed -i "s|^psk=.*|psk=$HOTSPOT_PSK|" "$HOT"; note "hotspot password changed"
    elif grep -qx 'psk=abcdefghij' "$HOT"; then
        warn "the hotspot still has DigiPi's default password (abcdefghij)"
    fi
    ok "hotspot on the USB adapter, SSID $(sed -n 's/^ssid=//p' "$HOT")"
    # Home Wi-Fi: tied to the onboard radio
    [ -f "$HOME_W" ] && grep -q $'\r' "$HOME_W" && sed -i 's/\r$//' "$HOME_W"
    if [ -f "$HOME_W" ] && grep -q '^ssid=.\+' "$HOME_W"; then
        [ -f "$STATE_DIR/wlan0.nmconnection.orig" ] || cp -p "$HOME_W" "$STATE_DIR/wlan0.nmconnection.orig"
        sed -i '/^interface-name=/d; /^mac-address=/d' "$HOME_W"
        sed -i "/^\[wifi\]\$/a mac-address=$ONBOARD_MAC" "$HOME_W"
        ok "home Wi-Fi ($(sed -n 's/^ssid=//p' "$HOME_W")) on the onboard radio"
    else
        warn "no home Wi-Fi saved yet - set it on DigiPi's Wifi page, then run the script again"
    fi
    chmod 600 "$NMDIR"/*.nmconnection
    if [ "$(cat "$NMDIR"/*.nmconnection 2>/dev/null | md5sum)" != "$NM_BEFORE" ]; then
        nmcli connection reload >/dev/null 2>&1 || true
        needs_reboot
        note "the Wi-Fi changes take effect at the next reboot"
    fi
fi

# ------------------------------------------------------------- /data
DATA_DEV=""
data_device() { DATA_DEV="$(blkid -L "$DATA_LABEL" 2>/dev/null)"; }
if [ "$DATA_PARTITION" = yes ]; then
    step "/data partition (saved weather history and battery state)"
    ROOT_PART="$(findmnt -no SOURCE /)"
    ROOT_NAME="$(basename "$ROOT_PART")"
    DISK="/dev/$(lsblk -no PKNAME "$ROOT_PART" | head -1)"
    PN="$(cat "/sys/class/block/$ROOT_NAME/partition")"
    case "$DISK" in *[0-9]) PFX="${DISK}p" ;; *) PFX="$DISK" ;; esac
    data_device
    if [ -n "$DATA_DEV" ]; then
        ok "/data partition exists ($DATA_DEV)"
    elif done_flag data-created; then
        note "partition made earlier; it is formatted after the reboot"
    else
        NPARTS=$(lsblk -nlo TYPE "$DISK" | grep -c part)
        [ "$PN" = "$NPARTS" ] || die "the system partition isn't the last one on the card, so /data can't be added
    safely. Re-flash the card, or set DATA_PARTITION=\"no\" in $SETTINGS."
        SECT=$(blockdev --getsz "$DISK")            # 512-byte sectors
        R_START=$(cat "/sys/class/block/$ROOT_NAME/start")
        R_SIZE=$(cat "/sys/class/block/$ROOT_NAME/size")
        ALIGN=8192                                  # 4 MiB
        WANT=$(( ROOT_GB * 2097152 ))
        NEW_R_SIZE=$R_SIZE
        if [ "$WANT" -gt "$R_SIZE" ]; then
            NEW_R_SIZE=$(( ((R_START + WANT) / ALIGN * ALIGN) - R_START ))
        fi
        D_START=$(( (R_START + NEW_R_SIZE + ALIGN - 1) / ALIGN * ALIGN ))
        D_SIZE=$(( DATA_GB * 2097152 ))
        [ $(( D_START + D_SIZE )) -le $(( SECT - ALIGN )) ] || die "not enough free space after the system partition for a ${ROOT_GB} GB system
    and ${DATA_GB} GB /data ($(( SECT / 2097152 )) GB card). Use a 32 GB or larger card, or lower
    ROOT_GB / DATA_GB in $SETTINGS."
        sfdisk -d "$DISK" > /boot/firmware/partitions-before-station-build.txt 2>/dev/null
        if [ "$NEW_R_SIZE" -gt "$R_SIZE" ]; then
            echo "$R_START,$NEW_R_SIZE" | sfdisk -q --no-reread --no-tell-kernel -N "$PN" "$DISK" >/dev/null 2>&1 \
                || die "could not grow the system partition (nothing was changed)"
            note "system partition grown to $(( NEW_R_SIZE / 2097152 )) GB"
            if partx -u --nr "$PN" "$DISK" 2>/dev/null && resize2fs "$ROOT_PART" >/dev/null 2>&1; then
                note "filesystem grown now"
            else
                set_flag resize-pending; note "filesystem is grown after the reboot"
            fi
        fi
        echo "$D_START,$D_SIZE,L" | sfdisk -q --no-reread --no-tell-kernel --append "$DISK" >/dev/null 2>&1 \
            || die "could not add the /data partition"
        set_flag data-created
        echo "$D_START" > "$STATE_DIR/data-start"
        DP="${PFX}$(( PN + 1 ))"
        if partx -a --nr $(( PN + 1 )) "$DISK" 2>/dev/null; then
            for _ in $(seq 10); do [ -b "$DP" ] && break; sleep 1; done
        fi
        if [ -b "$DP" ]; then
            run mkfs.ext4 -q -F -L "$DATA_LABEL" -m 0 "$DP"
            data_device
            ok "/data partition made: $DP, ${DATA_GB} GB"
        else
            note "/data partition is formatted after the reboot"
        fi
        needs_reboot
    fi
    mkdir -p "$DATA"
    CHANGED=0
    add_line /etc/fstab "LABEL=$DATA_LABEL  $DATA  ext4  defaults,noatime,commit=600,nofail,x-systemd.device-timeout=15s  0  2"
fi

# ------------------------------------------------------------- packages
step "Packages"
need_internet
export DEBIAN_FRONTEND=noninteractive
APT_OPTS=(-y -o Dpkg::Options::=--force-confold -o Dpkg::Options::=--force-confdef)
run apt-get update -qq
if [ "$DO_UPGRADE" = yes ] && ! done_flag upgraded; then
    note "upgrading the system (10-30 minutes on a Pi 3B+; keep the power steady)"
    run apt-get "${APT_OPTS[@]}" upgrade
    apt-get -y autoremove >/dev/null
    set_flag upgraded
    needs_reboot
fi
run apt-get "${APT_OPTS[@]}" install git wget unzip gnupg chrony sqlite3 \
        python3-six python3-configobj i2c-tools python3-smbus2
ok "packages installed"

# ------------------------------------------------------------- config.txt
step "config.txt"
[ -f "$CONFIG_TXT.station-build.bak" ] || cp "$CONFIG_TXT" "$CONFIG_TXT.station-build.bak"
CHANGED=0
if [ "$INSTALL_RTC" = yes ] || [ "$INSTALL_BATTERY" = yes ]; then
    grep -q "^dtparam=i2c_arm=on" "$CONFIG_TXT" || add_line "$CONFIG_TXT" "dtparam=i2c_arm=on"
fi
if [ "$INSTALL_RTC" = yes ]; then
    if [ "$IS_PI5" = yes ]; then note "Pi 5: built-in RTC (fit a battery on the BAT connector)"
    else add_line "$CONFIG_TXT" "dtoverlay=i2c-rtc,ds3231"; fi
fi
[ "$INSTALL_BATTERY" = yes ] && add_line "$CONFIG_TXT" "dtoverlay=i2c-gpio,bus=3,i2c_gpio_sda=23,i2c_gpio_scl=24"
[ "$INSTALL_BUTTON" = yes ] && add_line "$CONFIG_TXT" "dtoverlay=gpio-shutdown,gpio_pin=26"
[ "$CHANGED" = 1 ] && needs_reboot
ok "config.txt (original kept as $CONFIG_TXT.station-build.bak)"

if [ "${NEED_REBOOT:-0}" = 1 ] || reboot_pending; then
    echo
    echo "${c_hd}First part done.${c_off} Reboot, log in again over the home network, and run it again:"
    echo "    sudo reboot"
    echo "    sudo bash $0"
    exit 0
fi

###########################################################################
# PASS 2
###########################################################################
# ------------------------------------------------------------- /data, finish
if [ "$DATA_PARTITION" = yes ]; then
    step "/data"
    if done_flag resize-pending; then
        resize2fs "$(findmnt -no SOURCE /)" >/dev/null 2>&1 && note "system filesystem grown" \
            || warn "could not grow the system filesystem"
        clear_flag resize-pending
    fi
    data_device
    if [ -z "$DATA_DEV" ] && done_flag data-created; then
        ROOT_PART="$(findmnt -no SOURCE /)"
        DISK="/dev/$(lsblk -no PKNAME "$ROOT_PART" | head -1)"
        PN="$(cat "/sys/class/block/$(basename "$ROOT_PART")/partition")"
        case "$DISK" in *[0-9]) PFX="${DISK}p" ;; *) PFX="$DISK" ;; esac
        DP="${PFX}$(( PN + 1 ))"
        [ -b "$DP" ] || die "the /data partition $DP is missing"
        [ "$(cat "/sys/class/block/$(basename "$DP")/start")" = "$(cat "$STATE_DIR/data-start")" ] \
            || die "$DP isn't the partition this script made; not formatting it"
        [ -z "$(blkid -o value -s TYPE "$DP" 2>/dev/null)" ] || die "$DP already holds a filesystem without the $DATA_LABEL label; not formatting it"
        run mkfs.ext4 -q -F -L "$DATA_LABEL" -m 0 "$DP"
        data_device
    fi
    [ -n "$DATA_DEV" ] || die "no /data partition found"
    findmnt "$DATA" >/dev/null || run mount "$DATA"
    ok "/data mounted ($DATA_DEV, $(df -h --output=avail "$DATA" | tail -1 | tr -d ' ') free)"
fi

# ------------------------------------------------------------- clock
step "Clock"
if [ "$INSTALL_RTC" = yes ]; then
    [ -e /dev/rtc0 ] || die "no RTC found (/dev/rtc0). Check the module sits on pins 1-9 and run
    'i2cdetect -y 1' (expect UU at 68). No RTC fitted? Answer 'no' to the RTC question."
    ok "RTC present"
    if dpkg -s fake-hwclock >/dev/null 2>&1; then
        run apt-get -y purge fake-hwclock; note "removed fake-hwclock"
    fi
    rm -f /etc/fake-hwclock.data
    cat > /etc/systemd/system/rtc-to-system.service <<'EOF'
[Unit]
Description=Set system clock from the RTC
After=systemd-modules-load.service
Before=time-sync.target chrony.service weewx.service

[Service]
Type=oneshot
ExecStartPre=/bin/sh -c 'for i in $(seq 30); do [ -e /dev/rtc0 ] && exit 0; sleep 1; done; exit 1'
ExecStart=/sbin/hwclock --hctosys --utc

[Install]
WantedBy=multi-user.target
EOF
    systemctl daemon-reload
    systemctl enable rtc-to-system.service >/dev/null 2>&1
    ok "rtc-to-system.service loads the RTC time at every boot"
fi
systemctl disable --now systemd-timesyncd >/dev/null 2>&1 || true
systemctl enable --now chrony >/dev/null 2>&1 || true
if internet_up; then
    for _ in $(seq 12); do
        chronyc -n tracking 2>/dev/null | grep -q "Leap status *: Normal" && break; sleep 5
    done
fi
[ "$(date -u +%F)" \< "$MIN_DATE" ] && [ -e /dev/rtc0 ] && hwclock --hctosys --utc 2>/dev/null
[ "$(date -u +%F)" \< "$MIN_DATE" ] && die "the clock is wrong ($(date)). Set it, then run the script again:
    sudo date -u -s \"YYYY-MM-DD HH:MM:SS\"      # current UTC time"
ok "clock: $(date)"
[ -e /dev/rtc0 ] && hwclock --systohc --utc && ok "RTC set: $(hwclock -r 2>/dev/null)"

step "chrony time server"
CHRONY_FILE=/etc/chrony/conf.d/station.conf
grep -q "^confdir /etc/chrony/conf.d" /etc/chrony/chrony.conf 2>/dev/null && mkdir -p /etc/chrony/conf.d \
    || CHRONY_FILE=/etc/chrony/chrony.conf
if [ -n "$NTP_ALLOW" ]; then
    touch "$CHRONY_FILE"; CHANGED=0
    add_line "$CHRONY_FILE" "# station-build: serve time to the weather network, even with no internet"
    add_line "$CHRONY_FILE" "allow $NTP_ALLOW"
    add_line "$CHRONY_FILE" "local stratum 10"
    [ "$CHANGED" = 1 ] && systemctl restart chrony
    ok "serving time to $NTP_ALLOW"
else
    note "not serving time (NTP_ALLOW is empty)"
fi

step "Keep /dev/shm files when $PI_USER logs out"
mkdir -p /etc/systemd/logind.conf.d
if [ ! -f /etc/systemd/logind.conf.d/no-removeipc.conf ]; then
    printf '[Login]\nRemoveIPC=no\n' > /etc/systemd/logind.conf.d/no-removeipc.conf
    systemctl restart systemd-logind
fi
ok "RemoveIPC=no (keeps the telemetry counter)"

need_internet

###########################################################################
# WeeWX
###########################################################################
if [ "$INSTALL_WEEWX" = yes ]; then
    step "WeeWX"
    if ! dpkg -s weewx >/dev/null 2>&1; then
        wget -qO - https://weewx.com/keys.html | gpg --dearmor --yes --output /etc/apt/trusted.gpg.d/weewx.gpg \
            || die "could not get the WeeWX signing key"
        echo "deb [arch=all] https://weewx.com/apt/python3 buster main" > /etc/apt/sources.list.d/weewx.list
        run apt-get update -qq
        run apt-get "${APT_OPTS[@]}" install weewx
    fi
    [ -f "$WEEWX_CONF" ] || die "WeeWX is installed but $WEEWX_CONF is missing"
    id weewx >/dev/null 2>&1 || die "WeeWX's user 'weewx' is missing"
    ok "WeeWX $(weectl --version 2>/dev/null | awk '{print $2}')"
    systemctl stop weewx 2>/dev/null

    if ! weectl extension list --config="$WEEWX_CONF" 2>/dev/null | grep -qi ecowittcustom; then
        T=$(mktemp -d); run git clone -q --depth 1 "$ECOWITT_REPO" "$T/ecowitt"
        run weectl extension install "$T/ecowitt/weewx-ecowittcustom.zip" --config="$WEEWX_CONF" -y
        rm -rf "$T"
    fi
    ok "Ecowitt driver (ecowittcustom)"
    if ! weectl extension list --config="$WEEWX_CONF" 2>/dev/null | grep -qi aprs; then
        T=$(mktemp -d); run git clone -q --depth 1 "$APRS_REPO" "$T/weewx-aprs"
        run weectl extension install "$T/weewx-aprs" --config="$WEEWX_CONF" -y
        rm -rf "$T"
    fi
    ok "APRS packet formatter (weewx-aprs)"

    run weectl station reconfigure --config="$WEEWX_CONF" --no-prompt --no-backup \
        --driver=user.ecowittcustom --location="$STATION_LOCATION" \
        --latitude="$LATITUDE" --longitude="$LONGITUDE" --altitude="$ALTITUDE" --units=us >/dev/null
    conf_set Station.station_type Ecowittcustom
    conf_set Ecowittcustom.device_type ecowitt-client
    conf_set Ecowittcustom.mode listen
    conf_set Ecowittcustom.port "$WX_PORT"
    conf_set StdArchive.record_generation software
    conf_set StdReport.HTML_ROOT "$WEEWX_HTML"
    conf_set APRS.output_filename /dev/shm/aprs.pkt
    conf_set APRS.include_position 1
    ok "GW1200 uploads accepted on port $WX_PORT (any network)"

    # ---- database and reports in RAM
    step "WeeWX database in RAM, saved to /data"
    WUID=$(id -u weewx); WGID=$(id -g weewx)
    mkdir -p "$WEEWX_DIR" "$WEEWX_HTML"
    # A database already on the card (an earlier setup) is kept before RAM covers it
    if [ -f "$WEEWX_DB" ] && ! findmnt "$WEEWX_DIR" >/dev/null && [ "$DATA_PARTITION" = yes ] \
       && [ ! -f "$DATA/weewx/weewx.sdb" ]; then
        mkdir -p "$DATA/weewx"
        sqlite3 "$WEEWX_DB" ".backup '$DATA/weewx/weewx.sdb'" && note "existing database copied to /data/weewx"
    fi
    CHANGED=0
    add_line /etc/fstab "tmpfs  $WEEWX_DIR   tmpfs  nodev,nosuid,size=400M,mode=0755,uid=$WUID,gid=$WGID  0  0"
    add_line /etc/fstab "tmpfs  $WEEWX_HTML  tmpfs  nodev,nosuid,size=64M,mode=0755,uid=$WUID,gid=$WGID  0  0"
    systemctl daemon-reload
    findmnt "$WEEWX_DIR"  >/dev/null || run mount "$WEEWX_DIR"
    findmnt "$WEEWX_HTML" >/dev/null || run mount "$WEEWX_HTML"
    ok "$WEEWX_DIR and $WEEWX_HTML are in RAM"

    cat > /usr/local/bin/weewx-ramdb <<'EOF'
#!/bin/bash
# weewx-ramdb - WeeWX database in RAM, saved to /data
# Part of station-build.sh 2.1 - Scott Sheppard, KJ4ZZB
#   weewx-ramdb restore   at boot, before WeeWX: last saved copy -> RAM
#   weewx-ramdb save      4 times a day and at shutdown: RAM -> /data
RAM=/var/lib/weewx/weewx.sdb
DIR=/data/weewx
SAVED=$DIR/weewx.sdb
OKFLAG=/run/weewx-ramdb.ok          # set once RAM holds the right database
LOG=$DIR/save.log
log() { echo "$(date '+%F %T')  $*"; [ -d "$DIR" ] && { echo "$(date '+%F %T')  $*" >> "$LOG"; tail -n 200 "$LOG" > "$LOG.t" && mv "$LOG.t" "$LOG"; }; }

case "$1" in
restore)
    rm -f "$OKFLAG"
    if ! mountpoint -q /data; then
        log "restore: /data is not mounted - WeeWX starts with history since boot, no saves"
        exit 0
    fi
    mkdir -p "$DIR"
    if [ -f "$RAM" ]; then
        log "restore: database already in RAM"
    else
        for f in "$SAVED" "$SAVED.1"; do
            [ -f "$f" ] || continue
            if [ "$(sqlite3 "$f" 'PRAGMA quick_check;' 2>/dev/null)" = ok ]; then
                cp "$f" "$RAM" && chown weewx:weewx "$RAM" && log "restore: $f -> RAM ($(du -h "$RAM" | cut -f1))" && break
            fi
            log "restore: $f is damaged, trying the older copy"
        done
        if [ ! -f "$RAM" ]; then
            if [ -f "$SAVED" ] || [ -f "$SAVED.1" ]; then
                log "restore: no good saved copy - WeeWX starts with history since boot; saved copies kept, no saves"
                exit 0
            fi
            log "restore: no saved copy yet - WeeWX makes a new database"
        fi
    fi
    touch "$OKFLAG"
    ;;
save)
    [ -f "$OKFLAG" ] || { log "save: skipped (the saved copy was not restored at boot, so it is kept)"; exit 0; }
    mountpoint -q /data || { log "save: /data is not mounted"; exit 1; }
    [ -f "$RAM" ] || { log "save: no database in RAM yet"; exit 0; }
    mkdir -p "$DIR"
    sqlite3 "$RAM" ".backup '$SAVED.new'" || { log "save: backup failed"; rm -f "$SAVED.new"; exit 1; }
    [ "$(sqlite3 "$SAVED.new" 'PRAGMA quick_check;')" = ok ] || { log "save: copy failed its check"; rm -f "$SAVED.new"; exit 1; }
    sync "$SAVED.new"
    # keep the previous copy as the backup only if it is sound
    if [ -f "$SAVED" ]; then
        if [ "$(sqlite3 "$SAVED" 'PRAGMA quick_check;' 2>/dev/null)" = ok ]; then mv -f "$SAVED" "$SAVED.1"
        else rm -f "$SAVED"; log "save: previous copy was damaged; older backup kept"; fi
    fi
    mv -f "$SAVED.new" "$SAVED"
    sync "$DIR"
    SIZE=$(du -m "$RAM" | cut -f1)
    log "save: $(sqlite3 "$SAVED" 'SELECT COUNT(*) FROM archive;') records, ${SIZE} MB"
    [ "$SIZE" -gt 300 ] && log "WARNING: the database is ${SIZE} MB; the RAM space is 400 MB. Trim old records or move it to /data."
    ;;
*) echo "usage: weewx-ramdb restore|save"; exit 2 ;;
esac
exit 0
EOF
    chmod 755 /usr/local/bin/weewx-ramdb
    cat > /etc/systemd/system/weewx-ramdb.service <<EOF
[Unit]
Description=WeeWX database in RAM: restore at boot, save at shutdown
RequiresMountsFor=$WEEWX_DIR
Wants=data.mount
After=data.mount local-fs.target
Before=weewx.service

[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart=/usr/local/bin/weewx-ramdb restore
ExecStop=/usr/local/bin/weewx-ramdb save
TimeoutStopSec=120

[Install]
WantedBy=multi-user.target
EOF
    cat > /etc/systemd/system/weewx-ramdb-save.service <<'EOF'
[Unit]
Description=Save the WeeWX database from RAM to /data

[Service]
Type=oneshot
ExecStart=/usr/local/bin/weewx-ramdb save
EOF
    cat > /etc/systemd/system/weewx-ramdb-save.timer <<'EOF'
[Unit]
Description=Save the WeeWX database to /data four times a day

[Timer]
OnCalendar=*-*-* 00/6:17:00

[Install]
WantedBy=timers.target
EOF
    mkdir -p /etc/systemd/system/weewx.service.d
    cat > /etc/systemd/system/weewx.service.d/ramdb.conf <<'EOF'
# station-build: the database in RAM is restored before WeeWX starts
[Unit]
Wants=weewx-ramdb.service
After=weewx-ramdb.service rtc-to-system.service
EOF
    systemctl daemon-reload
    if [ "$DATA_PARTITION" = yes ]; then
        systemctl enable weewx-ramdb.service weewx-ramdb-save.timer >/dev/null 2>&1
        systemctl restart weewx-ramdb.service
        systemctl start weewx-ramdb-save.timer
        ok "saved to /data/weewx at 00:17, 06:17, 12:17, 18:17 and at every shutdown"
    else
        warn "no /data partition: weather history is kept only since the last boot"
    fi

    if [ ! -f "$WEEWX_DB" ]; then
        run weectl database create --config="$WEEWX_CONF" -y >/dev/null
        note "created a new database"
    fi
    for col in bgt wbgt; do
        sqlite3 "$WEEWX_DB" "PRAGMA table_info(archive);" | cut -d'|' -f2 | grep -qx "$col" \
            || run weectl database add-column "$col" --config="$WEEWX_CONF" -y >/dev/null
    done
    chown weewx:weewx "$WEEWX_DB"
    ok "database has bgt and wbgt columns"
    [ "$DATA_PARTITION" = yes ] && /usr/local/bin/weewx-ramdb save >/dev/null && ok "first copy saved to /data"

    # ---- BGT / WBGT in the APRS packet
    [ -f "$FORMATTER" ] || die "can't find $FORMATTER"
    python3 - "$FORMATTER" <<'PY' || die "could not patch $FORMATTER"
import shutil, sys
path = sys.argv[1]
MARKER = "# --- local addition: BGT / WBGT ---"
ANCHOR = "        if self._comment:\n"
BLOCK = f"""        {MARKER}
        # Black globe temperature and wet-bulb globe temperature, in deg F.
        for _key, _label in (('bgt', 'BGT'), ('wbgt', 'WBGT')):
            _val = record.get(_key)
            if _val is not None:
                if record.get('usUnits') != 1:          # 1 = weewx.US
                    _val = _val * 9.0 / 5.0 + 32.0       # metric record: C -> F
                data.append(' %s=%03.0fF' % (_label, _val))

"""
src = open(path).read()
if MARKER in src:
    sys.exit(0)
if src.count(ANCHOR) != 1:
    sys.exit("anchor line not found once")
try:
    open(path + ".orig").close()
except OSError:
    shutil.copy2(path, path + ".orig")
open(path, "w").write(src.replace(ANCHOR, BLOCK + ANCHOR))
print("   ..  BGT/WBGT added to the APRS packet")
PY
    ok "APRS packet includes BGT and WBGT"

    systemctl enable weewx >/dev/null 2>&1
    run systemctl start weewx
    sleep 5
    if ss -ltn | grep -q ":$WX_PORT "; then ok "WeeWX running, listening on port $WX_PORT"
    else warn "WeeWX is not listening on port $WX_PORT yet - check: journalctl -u weewx -n 30"; fi
fi

###########################################################################
# Battery monitor
###########################################################################
if [ "$INSTALL_BATTERY" = yes ]; then
    step "Battery monitor (INA226)"
    fetch ina226/battery_monitor.py "$PI_HOME/battery_monitor.py"
    sed -i "s/^CAPACITY_AH = [0-9.]*/CAPACITY_AH = $BATTERY_AH/" "$PI_HOME/battery_monitor.py"
    if [ "$DATA_PARTITION" = yes ]; then
        mkdir -p "$DATA/battery"; chown "$PI_USER:$PI_USER" "$DATA/battery"
        sed -i -e "s|^STATE_FILE = .*|STATE_FILE = \"$DATA/battery/battery_state.json\"   # kept across reboots|" \
               -e "s|^LOG_FILE = .*|LOG_FILE = \"$DATA/battery/battery_log.csv\"|" "$PI_HOME/battery_monitor.py"
        note "charge state and log kept in /data/battery"
    fi
    chown "$PI_USER:$PI_USER" "$PI_HOME/battery_monitor.py"; chmod 755 "$PI_HOME/battery_monitor.py"
    cat > /etc/systemd/system/battery.service <<EOF
[Unit]
Description=Battery monitor
Wants=data.mount
After=multi-user.target data.mount

[Service]
User=$PI_USER
ExecStart=/usr/bin/python3 $PI_HOME/battery_monitor.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF
    systemctl daemon-reload
    systemctl enable battery >/dev/null 2>&1
    systemctl restart battery
    # the monitor is restarting and using the bus, so look a few times
    INA_FOUND=no
    for _ in 1 2 3 4 5; do
        sleep 2
        i2cdetect -y 3 2>/dev/null | grep -q " 40" && { INA_FOUND=yes; break; }
    done
    if [ "$INA_FOUND" = yes ]; then ok "INA226 found at 0x40 on I2C bus 3"
    else warn "INA226 not seen on I2C bus 3 - check the wiring (pins 16, 17, 18, 20)"; fi
    ok "battery.service ($BATTERY_AH Ah)"
fi

###########################################################################
# APRS senders
###########################################################################
step "APRS senders"
if [ "$INSTALL_WEEWX" = yes ]; then
cat > /usr/local/bin/aprs-send-weather.sh <<'EOF'
#!/bin/bash
#
# aprs-send-weather.sh
#
# send an aprs weather packet to aprsis and RF
#
#  (C)2022 Craig Lamparter
#  GPL v2
#
#  Local changes, version 1.1 - 2026-10-27:
#    - quiet: no "bash -x" trace, no telnet error output
#    - APRS-IS only when the server is reachable; RF is always sent
#    - one line per send in /dev/shm/aprs-send.log (last 200 lines),
#      shared with aprs-send-telemetry.py
#    - talks to APRS-IS with bash /dev/tcp instead of telnet
#

# User serviceable parts:
USER="@CALLSIGN@"
PASS="@PASSCODE@"                        # https://apps.magicbug.co.uk/passcode/
DIREWOLFHOSTNAME=localhost
APRSIS_HOST=noam.aprs2.net
APRSIS_PORT=14580
RF_PATH="@RFPATH@"
LOG=/dev/shm/aprs-send.log
LOG_KEEP=200

log() {
    printf '%s  %-20s  %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "weather" "$1" >> "$LOG"
    tail -n "$LOG_KEEP" "$LOG" > "$LOG.tmp" 2>/dev/null && mv "$LOG.tmp" "$LOG"
}

# packet generated by weewx with weewx-aprs extension installed
STRING=$(cat /dev/shm/aprs.pkt 2>/dev/null)
if [ -z "$STRING" ]; then
    log "APRS-IS: skipped       RF: skipped  (no /dev/shm/aprs.pkt from weewx)"
    exit 1
fi
echo "Sending: $STRING"

# --- APRS-IS: only if the server can be reached (5 s check) ---------------
IS_STATUS="no internet"
if timeout 5 bash -c "exec 3<>/dev/tcp/$APRSIS_HOST/$APRSIS_PORT" 2>/dev/null; then
    if timeout 20 bash -c '
        exec 3<>/dev/tcp/'"$APRSIS_HOST"'/'"$APRSIS_PORT"' || exit 1
        sleep 2
        printf "user %s pass %s vers aprs-send-weather 1.1\r\n" "$0" "$1" >&3
        sleep 2
        printf "%s>APRS,TCPIP*:%s\r\n" "$0" "$2" >&3
        sleep 2
        exec 3>&-
    ' "$USER" "$PASS" "$STRING" 2>/dev/null; then
        IS_STATUS="sent"
        echo "Sent to APRS-IS."
    else
        IS_STATUS="failed"
        echo "APRS-IS send failed."
    fi
else
    echo "No internet - RF only."
fi

# --- RF: send the packet to the KISS TNC (Direwolf) -----------------------
echo "Sending packet to Radio TNC."
PACKET="$USER>APRS,$RF_PATH:$STRING"
{
sleep 5    # allow kissutil time to make connection
echo "$PACKET"
} | kissutil -h $DIREWOLFHOSTNAME >/dev/null 2>&1
if [ "${PIPESTATUS[1]}" -eq 0 ]; then
    RF_STATUS="sent"
else
    RF_STATUS="failed"
fi

log "APRS-IS: $(printf '%-12s' "$IS_STATUS")  RF: $(printf '%-7s' "$RF_STATUS")  ${STRING:0:60}"

[ "$RF_STATUS" = "sent" ] || [ "$IS_STATUS" = "sent" ]
exit $?
EOF
else
    # No WeeWX: keep only the callsign lines, which the telemetry sender reads
    printf '#!/bin/bash\n# Callsign for aprs-send-telemetry.py (no WeeWX on this station)\nUSER="@CALLSIGN@"\nPASS="@PASSCODE@"\nexit 0\n' \
        > /usr/local/bin/aprs-send-weather.sh
fi
sed -i -e "s|@CALLSIGN@|$CALLSIGN|" -e "s|@PASSCODE@|$APRS_PASSCODE|" -e "s|@RFPATH@|$RF_PATH|" \
    /usr/local/bin/aprs-send-weather.sh
chmod 755 /usr/local/bin/aprs-send-weather.sh
[ "$INSTALL_WEEWX" = yes ] && ok "aprs-send-weather.sh 1.1 for $CALLSIGN"

if [ "$INSTALL_BATTERY" = yes ]; then
    fetch ina226/aprs-send-telemetry.py /usr/local/bin/aprs-send-telemetry.py
    sed -i "s|^RF_PATH = .*|RF_PATH = \"$RF_PATH\"|" /usr/local/bin/aprs-send-telemetry.py
    chmod 755 /usr/local/bin/aprs-send-telemetry.py
    rm -f /dev/shm/aprs_telem_seq            # the counter must belong to $PI_USER, not root
    ok "aprs-send-telemetry.py for $CALLSIGN"
fi

###########################################################################
# GPS position updater
###########################################################################
if [ "$INSTALL_GPS" = yes ]; then
    step "GPS position updater"
    T=$(mktemp -d)
    fetch gps/digipi-gps-position.zip "$T/digipi-gps-position.zip"
    run unzip -q "$T/digipi-gps-position.zip" -d "$T"
    [ -f "$T/digipi-gps-position/install-gps-position.sh" ] || die "the GPS zip doesn't hold install-gps-position.sh"
    bash "$T/digipi-gps-position/install-gps-position.sh" | sed 's/^/      /'
    [ "${PIPESTATUS[0]}" -eq 0 ] || warn "the GPS installer reported a problem (see above)"
    rm -rf "$T"
    ok "GPS position updater $(python3 /usr/local/bin/digipi-gps-position.py --version 2>/dev/null | awk '{print $2}')"
fi

###########################################################################
# cron
###########################################################################
step "Scheduled tasks (cron)"
TAG="# station-build"
{
    crontab -u "$PI_USER" -l 2>/dev/null | grep -v "# station-setup\|$TAG" | grep -v "aprs-send-weather.sh\|aprs-send-telemetry.py"
    echo "PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin $TAG"
    [ "$INSTALL_WEEWX" = yes ]   && echo "*/5 * * * * /usr/local/bin/aprs-send-weather.sh >/dev/null 2>&1 $TAG"
    [ "$INSTALL_BATTERY" = yes ] && echo "2-59/10 * * * * /usr/local/bin/aprs-send-telemetry.py >/dev/null 2>&1 $TAG"
} | crontab -u "$PI_USER" - || die "could not install $PI_USER's crontab"
ok "$PI_USER:$([ "$INSTALL_WEEWX" = yes ] && echo " weather every 5 min")$([ "$INSTALL_BATTERY" = yes ] && echo " telemetry every 10 min")"
DASH_DB=/run/.local/share/direwolf-dashboard/packets.db
{
    crontab -l 2>/dev/null | grep -v "# station-setup\|$TAG"
    echo "*/5 * * * * [ -f $DASH_DB ] && sqlite3 $DASH_DB \"PRAGMA wal_checkpoint(TRUNCATE);\" >/dev/null 2>&1 $TAG"
} | crontab - || warn "could not install root's crontab"
ok "root: flush the Direwolf dashboard database every 5 min"

###########################################################################
# Boot report and saved journal
###########################################################################
if [ "$BOOT_REPORT" = yes ] && [ "$DATA_PARTITION" != yes ]; then
    note "boot report skipped: it needs the /data partition"
elif [ "$BOOT_REPORT" = yes ]; then
    step "Boot report and saved journal"
    mkdir -p "$DATA/journal" "$DATA/bootlog" /var/log/journal /etc/systemd/journald.conf.d
    chown root:systemd-journal "$DATA/journal" 2>/dev/null || true
    chmod 2755 "$DATA/journal"

    cat > /etc/systemd/journald.conf.d/station.conf <<'EOF'
# station-build: keep the journal across reboots (stored on /data)
[Journal]
Storage=persistent
SystemMaxUse=64M
SyncIntervalSec=10m
EOF

    cat > /etc/systemd/system/var-log-journal.mount <<'EOF'
# station-build: the saved journal lives on /data, not the system partition
[Unit]
Description=System journal kept on /data
RequiresMountsFor=/data
Before=systemd-journal-flush.service

[Mount]
What=/data/journal
Where=/var/log/journal
Type=none
Options=bind

[Install]
WantedBy=local-fs.target
EOF

    cat > /etc/systemd/system/station-boot-marker.service <<'EOF'
# station-build: notes whether the last shutdown was clean
[Unit]
Description=Station: note whether the last shutdown was clean
RequiresMountsFor=/data

[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart=/bin/sh -c 'mkdir -p /data/bootlog; if [ -f /data/bootlog/.clean-shutdown ]; then echo clean; else echo unclean; fi > /run/station-prev-shutdown; rm -f /data/bootlog/.clean-shutdown'
ExecStop=/bin/sh -c 'touch /data/bootlog/.clean-shutdown; sync'

[Install]
WantedBy=multi-user.target
EOF

    cat > /usr/local/bin/station-bootreport <<'EOF'
#!/bin/bash
# station-bootreport - written 2 minutes after every boot
# Part of station-build.sh 2.1 - Scott Sheppard, KJ4ZZB
#   /data/bootlog/boot-YYYY-MM-DD_HHMMSS.txt   the last 30 reports
#   /boot/firmware/bootlog.txt                 the latest; readable on a Mac
DIR=/data/bootlog
KEEP=30
BOOTFS=/boot/firmware
mkdir -p "$DIR"
OUT="$DIR/boot-$(date '+%F_%H%M%S').txt"

PREV=$(cat /run/station-prev-shutdown 2>/dev/null || echo unknown)
HSDEV=$(nmcli -t -f DEVICE,CONNECTION device status 2>/dev/null | awk -F: '$2=="hotspot"{print $1}')

{
echo "=== Boot report  $(hostname)  $(date '+%F %T %Z')"
echo "This boot started:  $(uptime -s)"
case "$PREV" in
    clean)   echo "Previous boot:      ended cleanly (shutdown or reboot command)" ;;
    unclean) echo "Previous boot:      ended WITHOUT a clean shutdown - power loss, crash or reset" ;;
    *)       echo "Previous boot:      unknown" ;;
esac
echo
echo "--- Power (throttled=0x0 means no problems since this boot)"
vcgencmd get_throttled 2>/dev/null || echo "vcgencmd not available"
echo

if [ -n "$(journalctl -b -1 -q -n 1 --no-pager 2>/dev/null)" ]; then
    echo "--- Previous boot: first and last log entries"
    journalctl --list-boots --no-pager 2>/dev/null | tail -n 2 | head -n 1
    echo
    echo "--- Previous boot: power warnings"
    journalctl -b -1 -k -q --no-pager 2>/dev/null | grep -iE "under-?voltage|voltage normali" | tail -n 10
    echo
    echo "--- Previous boot: errors (last 15)"
    journalctl -b -1 -p err -q --no-pager 2>/dev/null | tail -n 15
    echo
    echo "--- Previous boot: last 30 log lines"
    journalctl -b -1 -q --no-pager -n 30 2>/dev/null
else
    echo "--- Previous boot: no saved log (first boot with the saved journal)"
fi
echo

echo "--- This boot: network"
nmcli -t -f DEVICE,STATE,CONNECTION device status 2>/dev/null | grep '^wlan'
if [ -n "$HSDEV" ]; then
    echo "Hotspot on $HSDEV, clients: $(iw dev "$HSDEV" station dump 2>/dev/null | grep -c '^Station')"
else
    echo "Hotspot: NOT running"
fi
echo
echo "--- This boot: services"
for s in weewx-ramdb weewx battery chrony gpsd; do
    printf '%-14s %s\n' "$s" "$(systemctl is-active "$s" 2>/dev/null)"
done
echo
echo "--- Disk space"
df -h / /data 2>/dev/null
} > "$OUT" 2>&1

# keep the newest $KEEP reports
ls -1t "$DIR"/boot-*.txt 2>/dev/null | tail -n +$((KEEP + 1)) | xargs -r rm -f

# latest report on the boot partition, where a Mac can read it from the card
if mountpoint -q "$BOOTFS"; then
    WASRO=0
    findmnt -no OPTIONS "$BOOTFS" | grep -q '^ro' && WASRO=1
    [ "$WASRO" = 1 ] && mount -o remount,rw "$BOOTFS"
    cp "$OUT" "$BOOTFS/bootlog.txt" && sync
    [ "$WASRO" = 1 ] && mount -o remount,ro "$BOOTFS"
fi
exit 0
EOF
    chmod 755 /usr/local/bin/station-bootreport

    cat > /etc/systemd/system/station-bootreport.service <<'EOF'
# station-build: writes the boot report
[Unit]
Description=Station boot report
RequiresMountsFor=/data
After=station-boot-marker.service

[Service]
Type=oneshot
ExecStart=/usr/local/bin/station-bootreport
EOF

    cat > /etc/systemd/system/station-bootreport.timer <<'EOF'
# station-build: report 2 minutes after boot, once things have settled
[Unit]
Description=Write the station boot report 2 minutes after boot

[Timer]
OnBootSec=2min

[Install]
WantedBy=timers.target
EOF

    systemctl daemon-reload
    systemctl enable var-log-journal.mount station-boot-marker.service station-bootreport.timer >/dev/null 2>&1
    if findmnt /var/log/journal >/dev/null || systemctl start var-log-journal.mount; then
        systemctl restart systemd-journald
        journalctl --flush
        ok "journal saved to /data/journal (64 MB cap, written every 10 minutes)"
    else
        warn "could not put the journal on /data - check: systemctl status var-log-journal.mount"
    fi
    systemctl start station-boot-marker.service
    ok "boot report 2 minutes after every boot: /data/bootlog and /boot/firmware/bootlog.txt"
fi

###########################################################################
# Summary
###########################################################################
step "Checks"
chk() { local label="$1"; shift; if "$@" >/dev/null 2>&1; then ok "$label"; else warn "$label - NOT OK"; fi; }
listening() { ss -ltn | grep -q ":$WX_PORT "; }
ok "clock: $(date '+%Y-%m-%d %H:%M %Z')"
[ "$INSTALL_RTC" = yes ]     && chk "rtc-to-system.service enabled" systemctl is-enabled rtc-to-system
chk "chrony running" systemctl is-active chrony
[ "$DATA_PARTITION" = yes ]  && chk "/data mounted" findmnt "$DATA"
if [ "$INSTALL_WEEWX" = yes ]; then
    chk "WeeWX running" systemctl is-active weewx
    chk "WeeWX listening on port $WX_PORT" listening
    chk "WeeWX database in RAM" findmnt "$WEEWX_DIR"
    [ "$DATA_PARTITION" = yes ] && chk "database saves scheduled" systemctl is-enabled weewx-ramdb-save.timer
fi
[ "$INSTALL_BATTERY" = yes ] && chk "battery monitor running" systemctl is-active battery
[ "$INSTALL_GPS" = yes ]     && chk "GPS updater enabled" systemctl is-enabled digipi-gps-position
if [ "$BOOT_REPORT" = yes ] && [ "$DATA_PARTITION" = yes ]; then
    chk "journal saved to /data" findmnt /var/log/journal
    chk "boot report scheduled" systemctl is-enabled station-bootreport.timer
fi
chk "Direwolf running (RF path)" pgrep -x direwolf

# Size of the card's used part, for the backup image on the Mac
DISK="/dev/$(lsblk -no PKNAME "$(findmnt -no SOURCE /)" | head -1)"
LAST_END=$(sfdisk -d "$DISK" 2>/dev/null | awk -F'[=,]' '/start=/{s=$2+0; z=$4+0; if (s+z>m) m=s+z} END{print m}')
IMG_MB=$(( (LAST_END * 512 + 1048575) / 1048576 ))
PI_ADDR="$(hostname -I 2>/dev/null | awk '{print $1}')"

echo
if [ ${#WARNINGS[@]} -gt 0 ]; then
    echo "${c_warn}Things to look at:${c_off}"
    printf '   - %s\n' "${WARNINGS[@]}"
    echo
fi
cat <<EOF
${c_hd}Build finished.${c_off}  Log: $LOG

Next:
  1. In the Ecowitt app, set the GW1200's Customized upload: Ecowitt protocol,
     server 10.0.0.5, path /, port $WX_PORT, every 60 seconds.
  2. After the next 5-minute mark:   cat /dev/shm/aprs.pkt
  3. Send once by hand (as $PI_USER, not sudo), then check the log:
         aprs-send-weather.sh
         aprs-send-telemetry.py --defs
         cat /dev/shm/aprs-send.log
  4. sudo reboot   (back to read-only), and check everything again.
  5. Back up the card. The used part is $IMG_MB MB.
     Card in the Mac (diskutil list external gives N):
         diskutil unmountDisk /dev/diskN
         sudo dd if=/dev/rdiskN bs=1m count=$IMG_MB | gzip > ~/${CALLSIGN}-$(date +%F).img.gz
     Or over SSH with the Pi running. After the reboot in step 4, on the Pi:
         sudo mount -o remount,ro /boot/firmware; sudo systemctl stop battery; sudo journalctl --sync
     then on the Mac (not near 00:17, 06:17, 12:17 or 18:17, when WeeWX saves to /data):
         caffeinate -i ssh $PI_USER@${PI_ADDR:-<Pi address>} 'sudo dd if=$DISK bs=1M count=$IMG_MB status=progress | gzip -1' > ~/${CALLSIGN}-$(date +%F).img.gz
     and afterwards on the Pi:   sudo systemctl start battery
EOF
