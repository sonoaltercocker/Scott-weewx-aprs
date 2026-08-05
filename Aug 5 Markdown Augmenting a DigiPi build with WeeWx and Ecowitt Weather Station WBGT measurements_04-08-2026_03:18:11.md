# Augmenting a DigiPi build with WeeWx and Ecowitt Weather Station WBGT measurements.

**Scott Sheppard**

**KJ4ZZB**

**[Ssheppa9@bellsouth.net](mailto:Ssheppa9@bellsouth.net)**

Draft 0.1  basic markdown with extensive API notes at the end.


# Introduction and WBGT

The following work is derived from the Digipi Project [https://craiger.org/digipi/](https://craiger.org/digipi/)


Recently, the topic of Wet-Bulb Globe Temperature has come to the forefront regarding safety and various outdoor activities. The concepts of WBGT derived from the US Military has been around since the 1950’s but computational and instrumentation utilities have been lacking. That has changed in the 2000’s and WBGT is now a frequently cited safety metric.** **The Wet-Bulb Globe Temperature (WBGT) is a measure of environmental heat stress that accounts for air temperature, humidity, wind speed (?), and solar radiation. It is used to define safety limits such as work-to-rest ratios and to prevent heat-related illnesses. 

Summary of measurements of heat for human use:

(WBT) Wet Bulb Temperature is derived from a bulb-style thermometer exposed to ambient temperatures while covered in a cloth that's been soaked with ambient-temperature water. WBT helps to understand the temperature on the skin of an individual who is both exposed to ambient-temperature moisture in the air (humidity) and producing approximately ambient-temperature water (sweating). There are multiple commercial solutions but their utility varies.  (Search amazon for Wet Bulb Temperature)

Heat index (“feels like” - which tells you how temperature feels to the human body in a shady area) )  is calculated using air temperature and ambient humidity and measured using a dry thermometer. It is also always calculated using readings from shady areas, which means that the increased stress of direct sunlight is completely missing from the equation. 

WBGT (our subject) accounts for the impact of solar radiation as well as wind, it’s a much more accurate and useful measurement of potential heat stress. WBGT provides a more accurate reflection of how strenuous activity impacts the body outdoors. As a result many organizations including Fire Departments, the Military, most athletic teams and a host of others have adopted WBGT to define safety parameters. The administration of the Atlanta Track club are no exception and WBGT measures are used to enforce safety restrictions during the Peach Tree Road Race and the Georgia Public Marathon among other activities. 

See [https://www.forbes.com/sites/marshallshepherd/2019/08/14/wet-bulb-globe-temperature-is-great-for-heat-warningswhy-dont-we-use-it/#ecd5dcdf25ba.](null)


In a recent email exchange with Michael Gaertner there are specific location restrictions needed for useful WBGT metrics *“ **WBGT measures are of interest for the marathon and PRR, but the location requirements are very specific.  For example, yesterday we needed to know the WBGT in the highest density of people in the meadow, in the chute, and then at two aid stations (again, on the ground next to the runners so we could get readings as close as possible to the people experiencing it). “ *

The issue is cost, to a lesser degree data management and availability . The Atlanta Track Club employs Kestrel 5400 ($549.00) and 5400CL to measure "WBGT Outside".

**Recommendation**

It is recommended that Dekalb ARES adopt WBGT metric for activities during outdoor  events such as deployments, exercises and Field Day. Since funding is tight we can create our own WBGT infrastructure by leveraging our Digipi efforts with some programming and selected off the shelf components. This effort could be leveraged by other ARES groups and by other Georgia radio clubs. It is essential that WBGT measures be accessible via the web so there is maximum information distribution.

# The math behind WBGT

To define WBGT some simple math, measurements and derivations are used:

1. For indoor and outdoor conditions with no solar load, WBGT is calculated as:

WBGT = 0.7NWB + 0.3GT (not of interest)

2. For outdoors with a solar load, WBGT is calculated as

WBGT = 0.7NWB + 0.2GT + 0.1DB

**WBGT=0.7T**~W~**+0.2T**~G~**+0.1T**~D~

T~w~ is the wet bulb temperature, which indicates humidity (note humidity the main impact of perceived heat)

T~g~ is the globe temperature, which indicates radiant heat (sun) as experienced by your skin.

T~d~ is the ambient air (dry) temperature

(ref https://blog.aem.eco/wbgt-what-is-it-and-how-do-you-calculate-it)

**Calculate Tw**

Many locations do not have Wet Globe temperature statistics thus meteorologist Roland Stull ([https://journals.ametsoc.org/view/journals/apme/50/11/jamc-d-11-0143.1.xml](https://journals.ametsoc.org/view/journals/apme/50/11/jamc-d-11-0143.1.xml)  Yes I read the paper)) derived a widely used empirical model of wet bulb temperature 

Tw =T * arctan[0.151977 (RH% + 8.313659)^(1 / 2)] + arctan (T + RH%) - arctan(RH%)

T in Deg C, RH is a percentage

Thus, to calculate WBGT we need :

A thermometer (T), (Td)  in deg C, Measured Dry Bulb Temperature

A humidity sensor (RH%)

A globe temperature thermometer (Tg) in deg C

1. **ReadDry Bulb:** The external thermo-hygrometer sensor array measures your ambient shade temperature.

2. **Humidity:** The same sensor measures the moisture in the air to establish the RH.

3. **Applies Algorithm:** The console applies this data to the psychrometric function to simulate the effect of evaporative cooling.

4. **Result:** The colder the air (lower Dry Bulb) and the drier the air (lower RH), the more water can evaporate, resulting in a lower (safer) calculated Wet Bulb temperature. adiabatic saturation

Per AI the Ecowitt product calculated WBGT as follows

Ecowitt applies the standard outdoor formula that accounts for direct sunlight and radiant heat load: \
WBGT =0.7 * times T_nwb + 0.2 * times T_{g} + 0.1 * T_db

Where the variables represent:

- T_nwb (Natural Wet-Bulb Temperature): Derived from ambient temperature and relative humidity data to measure evaporative cooling.

- T_g (Globe Temperature): Measured directly by the black brass sphere on the WN38 Black Globe Thermometer to capture radiant heat and solar load.

- T_db (Dry-Bulb Temperature): Standard ambient air temperature measured in the shade via the paired outdoor sensor.

Ecowitt calculates Wet Bulb Globe Temperature (WBGT) using standard outdoor solar radiation weighting formulas by combining data from a [WN38 Black Globe Thermometer](https://shop.ecowitt.com/products/wn38?srsltid=AfmBOop3knUSDnpPGGb36CcjeIRpZ2cb7LoGp68lmdFXw7-cSISSlRlK) and an outdoor temperature/humidity sensor. 

Heat Stress caution chart is a good reference and when planning outdoor activities this is a good reference. 

![WBGT heat chart](image-1.png)

# Weather Station

Ecowitt (OEM FineOffSet) provides a temperature sensor, humidity sensor and a globe thermometer all coupled with Wi FI to a console for access to the metrics. Cost ~$115.00 with shipping, $89.99 just the parts. WBGT results are available with a Ecowitt application and from an Ecowitt website.

Interesting reading about Ecowitt and the OEM FineOffSet is here. It is strongly suggested that the reader at last skim this WiKI

Weather stations for beginners

[https://meshka.eu/Ecowitt/dokuwiki/doku.php?id=beginners](https://meshka.eu/Ecowitt/dokuwiki/doku.php?id=beginners)

Information about Ecowitt products.

[https://meshka.eu/Ecowitt/dokuwiki/doku.php?id=start](https://meshka.eu/Ecowitt/dokuwiki/doku.php?id=start)

The position of sensors is important  as per recommendation of the WMO (World Meteorological Organization), the main readings of outdoor temperature and humidity, rainfall and wind should be taken at different heights:

- temperature 2 m / ~ 6.6 feet above ground

- rainfall 1 m (0-500 m a.s.l.) - 1.5 m (above 500 m a.s.l.*) / ~3.3 - 5 feet above ground

- wind 10 m - 15 m / ~33 - 49 feet above ground

In the case of Sheppard’s home all measures are about 25 feet above ground except solar radiation about 9 feet above ground.

WN 38 Black Globe Thermometer, Wet globe Temperature

![WN 38 Black Globe Thermometer](image-4.png)

WN 32 Outdoor temperature and humidity sensor. 

![Temperatur and humidity sensor](image-3.png)

This equipment can be mounted on a pole or mast with an adapter for the WN32 – ($28.81 with shipping)


Once the sensors and console are installed the equipment can communicate via Wi Fi. Since the Digipi project also uses wi-fi then data from the Ecowitt instrumentation via the GN1200 console should be available to the Raspberry pi (R Pi 2 Zero W or R Pi 4 or R Pi 5) used for the Digipi project (  [https://craiger.org/digipi/](https://craiger.org/digipi/)   )  

# Ecowitt data repositories 

**Home Assistant:** Not used in this document. 

**Local APIs / MQTT:**  This is not used in this document 

**Ecowitt Weather: (aka ecowitt.net) **Data is uploaded directly to the Ecowitt net cloud platform where it is permanently stored and available to view via graphs or download as spreadsheets.  WBGT values and BGT (Black Globe Temperature) are streamed in real-time and can be monitored directly through the [Ecowitt](https://apps.apple.com/ie/app/ecowitt/id1576152334) app or on a [ecowitt.net](https://www.facebook.com/ecowittsupport/) dashboard. 

**Getting WBGT metric needs a web server API or an app**

To obtain WBGT results from Ecowitt you need the hardware listed above.  The results for BGT and WBGT are pushed from the Ecowitt console WS 3900 or from the gateway GW 1200.  Displayed results are available either from pushed telemetry (what we use for WeeWx),  from the Ecowite.net website or from the Ecowitt app.

Example display of WBGT from the local Ecowitt app (on a mac). Remember the actual value of WBGT is LESS than external temperature. 

![Ecowitt app display](image-6.png)

Example display of WBGT from the web on Ecowitt.net. Remember the actual value of WBGT is LESS than external temperature.

![Ecowitt.net](image-5.png)

Note: Taken during a rain storm.

# APRS Callsigns for Digipi and Weather station field updates. 

This effort is triggered by needs for Dekalb Ares and Alford Memorial Radio Club. As such rather than use the call sign of Scott Sheppard KJ4ZZB this project will use the AMRC club call sign WD5EMA with the following suffixes:

    WD5EMA-2 normal deployment
    WD5EMA-3 prototyping
    WD5EMA-4 second unit for deployment if needed

        This plan was authorized by the call sign trustee.
            Dekalb County ARES, WD5EMA (Club)
            PO Box 1282 \
            Stone Mountain, GA 30086 \
            ATTN: Steven E Garrison \
            Trustee: Garrison, Steven E , N4TTY  \
            Previous call sign: KJ4QFY \
            Licensee ID: L01528805 \
            FRN: 0019245760 \
            Radio Service: HV \
            Issue Date: 02/21/2024 \
            Expire Date: 02/21/2034 \
            Date of Last Change: 03/19/2024

[https://www.arrl.org/advanced-call-sign-search](https://www.arrl.org/advanced-call-sign-search)

# Basic Build, IP and SSH

    Create a SD card for a Raspberry PI using the latest image from the digipi project ( [https://craiger.org/digipi/](https://craiger.org/digipi/) )
    Load the SD card on the Raspberry PI and power up the PI
    Using the. SSID Digipi update the WI Fi for the Raspbrerry Pi for your local SSID . Save and reboot
    Do NOT initialize at this point. 

**SSH and Static IP to the digipi / weeex server**

Set a static  IP for the Digipi on your WiFI router

    1. Get MAC address

    Access the digipi -> shell
    Look up the wlan0: mac address of your raspberry pi
        pi@digipi:/ $ ifconfig
        …
        wlan0: flags=4163<UP,BROADCAST,RUNNING,MULTICAST>  mtu 1500
        inet 192.168.1.180  netmask 255.255.255.0  broadcast 192.168.1.255
        …
                ether dc:a6:32:26:75:be  txqueuelen 1000  (Ethernet)
        …

    2. Access your router (in the author’s case)

        [https://192.168.1.254/cgi-bin/home.ha](https://192.168.1.254/cgi-bin/home.ha)
        Access the IP allocation table (requires router access passcode)
        On the author’s home router he have assigned a fixed IP address to the Raspberry Pi 4 hosting digipi at 192.168.1.180
        This will make SSHing to the Pi much simpler.


**/End of static IP**

**SSH to Raspberry Pi**

On your teminal (like terminal on a MAC)

    $ ssh pi@192.168.1.180

        The authenticity of host '192.168.1.180 (192.168.1.180)' can't be established.
        ED25519 key fingerprint is: SHA256:L915osEm+n+FkF4Iqpijj3DcNtgTc5aqUkMjdh7Ev+M
        This key is not known by any other names.
        Are you sure you want to continue connecting (yes/no/[fingerprint])? yes
        Warning: Permanently added '192.168.1.180' (ED25519) to the list of known hosts.
        pi@192.168.1.180's password: (raspberry)

        Welcome to DigiPi!
        Run 'sudo remount' to make the filesystem writeable.

            pi@digipi:~ $ sudo remount

**/End  ssh**

# Configure the Ecowitt WS3900 console to support WeeWx on the Raspberry PI

After setting the WiFI on the author’s  MAC to the WI FI SSID of the WS 3900 console one is  able to enable customized Ecowitt data export via HTTP PUSH. (see owners manual) 

Where 192.168.1.180 is the IP the Raspberry Pi 4 and the sending port (reading port) is 9000.Configure teh weather station (WS) or console to push data to your Raspberry Pi. 

    ![ configure output to weewx]](image-8.png)

When finished return the Wi Fi SSID for the home or Digipi station

**/end of WS3900 configuration**

# Install WeeWx 

Download and install the repository signature key:

sudo wget -qO - https://weewx.com/keys.html | sudo gpg --dearmor -o /etc/apt/trusted.gpg.d/weewx.gpg

Add the WeeWX software repository:

echo "deb [arch=all] https://weewx.com/apt/python3 buster main" | sudo tee /etc/apt/sources.list.d/weewx.list

Install WeeWX

    $sudo apt-get update
    $sudo apt-get install weewx
    Answer a bunch of questions like:
        Location: Decatur Georgia USA 30033
        Lat and long in decimal degrees: 33.83194000, -84.26809083
        Altitude (meters): 301, meter
        unit system : metricwx
        Weather Station type for simulator: FineOffsetUSB
        Weather station model: WS3900
        You can register the station on weewx.com, where it will be included in a
        map. If you choose to register, you will also need a unique URL to identify
        the station (such as a website, or a WeatherUnderground link).
        register this station (y/n)? [n] N

# Configure WeeWx with Ecowitcustom driver including entries for BGT and WBGT. 

This program will take data from the Ecowitt data stream and put it into the weewx.sdb.

    $ sudo apt-get install sqlite3
    $ sudo apt install python3-six

This repo

[https://github.com/WernerKr/Ecowitt-or-DAVIS-stations-and-Season-skin/archive/refs/heads/main.zip](null)

contains a current ecowittcustom driver that supports all Ecowitt sensors as of July 2026.  The file we need is ecowittcustom.py. It should be installed usually in “`/etc/weewx/bin/user/”` or “`/usr/share/weewx/user/`”. We used /etc/weewx/bin/user. .
it supports values for wbgt and bgt (example)

    ```
    30 Dec 2025            v0.1.7
        - bgt, wbgt, bgtbatt, wn38_sig, wn38_rssi, lightning_distance = group_distance
    ```
Download the ecowitt custom driver:

	$ cd /etc/weewx/bin/user
    $ wget -O ecowittcustom.py https://raw.githubusercontent.com/WernerKr/Ecowitt-or-DAVIS-stations-and-Season-skin/main/ecowittcustom.py

This needs some study and is included for reference 

        $ weectl extension install -h
            usage:   weectl extension install (FILE|DIR|URL)
            [--config=FILENAME]
            [--dry-run] [--yes] [--verbosity=N]
            Install an extension contained in FILE (such as pmon.tar.gz), directory (DIR), or from an URL.
            positional arguments:
            source             Location of the extension. It can be a path to a zipfile or tarball, a path to an unpacked directory, or an URL pointing to a zipfile or tarball.
            options:
            -h, --help         show this help message and exit
            --config FILENAME  Path to configuration file. Default is "/root/weewx-data/weewx.conf".
            --dry-run          Print what would happen, but do not actually do it.
            -y, --yes          Don't ask for confirmation. Just do it.
            --verbosity N      How much information to display (0|1|2|3).

Edit weewx.conf  (Also see appendix for the actual look and feel of the weewx.conf file.)

    Stanza [Station]

    … station_type =  Ecowittcustom

    Stanza [Ecowittcustom]

    Be sure the Model and Polling interval and commented out like 
        #The station model, e.g., WH1080, WS1090, WS2080, WH3081
        #model = WS3900

        # How often to poll the station for data, in seconds
        # polling_interval = 60

        # The driver to use:
            driver = user.ecowittcustom
            port = 9000 # Unique to my build.
        device_type = ecowitt-client
Save edit and restart WeeWx

    $ systemctl restart weewx

Verify data collection with

    systemctl stop weewx
    /etc/weewx# weewxd /etc/weewx/weewx.conf

Expected result

    (not edited) LOOP:   2026-07-31 18:50:38 BST (1785520238) altimeter: 30.04255721345501, appTemp: 90.47723992728419, barometer: 28.984, bgt: 112.46, bgtbatt: 1.62, cloudbase: 5855.535294846159, consBatteryVoltage: 4.5, dateTime: 1785520238, dewpoint: 64.58079985944924, drain_piezo: 0.0, erain_piezo: 0.0, ET: None, fwinddir_avg10m: 140.0, hail: None, hailBatteryStatus: 3.06, hailRate: 0.0, heap: 75288.0, heatindex: 87.60929586000003, hrain_piezo: 0.0, humidex: 96.9581358075385, inDewpoint: 61.57937906833771, inHumidity: 55.0, inTemp: 79.16, lightning_Batt: 5.0, lightning_distance: 7.4564520000000005, lightning_disturber_count: 1785301959.0, lightning_num: 0.0, lightning_strike_count: 0, maxdailygust: 5.14, maxSolarRad: 1021.1410608427051, model: WS3900B, mrain_piezo: 2.406, outHumidity: 49.0, outTemp: 86.0, p_rain: None, p_rainrate: 0.0, pressure: 28.984, radiation: 808.37, rain24_piezo: 0.0, rainRate: 0.0, runtime: 4335.0, srain_piezo: 0.0, stationtype: WS3900B_V1.4.8, usUnits: 1, UV: 7.0, vpd: 0.639, wbgt: 81.32, windchill: 86.0, windDir: 170.0, windDir10: 140.0, winddir_avg10m: 140.0, windGust: 2.01, windrun: None, windSpeed: 1.12, wrain_piezo: 0.461, ws90_batt: 3.06, ws90_ver: 160.0, ws90cap_volt: 5.2, ws_interval: 30.0, yrain_piezo: 2.406

Return weewx to normal operation

    systemctl restart weewx
    systemctl status weewx

    Expected output similar to:

        
        root@digipi:/home/pi# systemctl status weewx
        ● weewx.service - WeeWX #markdown does not rendor color this should be GREEN
            Loaded: loaded (/usr/lib/systemd/system/weewx.service; enabled; preset: enabled)
            Active: active (running) since Sun 2026-08-02 15:53:32 BST; 2 days ago
        Invocation: 715ab1ac40214e4482fb217ff43adace
            Docs: https://weewx.com/docs
        Main PID: 24791 (python3)
            Tasks: 2 (limit: 4020)
                CPU: 25min 24.324s
            CGroup: /system.slice/weewx.service
                    └─24791 python3 /usr/share/weewx/weewxd.py /etc/weewx/weewx.conf

        Aug 04 19:15:44 digipi weewxd[24791]: INFO root: weewx-aprs-packet-formatter - /041815z3349.92N/08416.09W_141/000g003t071r000h96b09818 BGT=070F WBGT=070F
        Aug 04 19:15:44 digipi weewxd[2479 ...removed for bevity 
        Aug 04 19:20:46 digipi weewxd[24791]: INFO weewx.imagegenerator: Generated 16 images for report SeasonsReport in 0.66 seconds

# Configure WeeWx.sdb with new columns for values BGT and WBGT

The data above is from the Ecowitt equipment. However, we need new DB columns to store the BGT and WBGT values.


As root
    $ sudo su root
    # systemctl stop weewx

    $ weectl database add-column wbgt 
        Using configuration file /etc/weewx/weewx.conf
        Add new column 'wbgt' of type 'REAL' to database 'weewx.sdb' (y/n)? y
        New column wbgt of type REAL added to database.

    $ weectl database add-column bgt 
        Using configuration file /etc/weewx/weewx.conf
        Add new column 'bgt' of type 'REAL' to database 'weewx.sdb' (y/n)? y
        New column bgt of type REAL added to database.

Result added two new columns for WBGT and BGT. Now verify it. 

    $ sqlite3 /var/lib/weewx/weewx.sdb "PRAGMA table_info(archive);"

        ...
        113|windrun|REAL|0||0
        114|windSpeed|REAL|0||0
        115|wbgt|REAL|0||0
        116|bgt|REAL|0||0

    $ systemctl restart weewx

Verify that the WeeWx.sdb is collecting data. Wait about 20 minutes after installing the above extension to allow data to populate.
Verify the entries in the WeeWx DB for WBGT and BGT.
**If the count is greater than 0**: Data is successfully being populated.

    sqlite3 /var/lib/weewx/weewx.sdb "SELECT COUNT(*) FROM archive WHERE wbgt IS NOT NULL;"
    Example
        5
    sqlite3 /var/lib/weewx/weewx.sdb "SELECT COUNT(*) FROM archive WHERE bgt IS NOT NULL;"
    Example
        5
    Examine the most recent entries and verify that the numbers look realistic (last 5 records):
        $ sqlite3 /var/lib/weewx/weewx.sdb "SELECT datetime(dateTime, 'unixepoch', 'localtime'), wbgt FROM archive ORDER BY dateTime DESC LIMIT 5;"
    Example (reduced)
        2026-07-27 16:50:00|75.2
    $ sqlite3 /var/lib/weewx/weewx.sdb "SELECT datetime(dateTime, 'unixepoch', 'localtime'), bgt FROM archive ORDER BY dateTime DESC LIMIT 5;"
    Example
        2026-07-27 16:50:00|80.24

# APRS extension for WeeWx 

The original repository from SavageBread is not sufficient  to support extracting data from the Ecowitt data stream for BGT and WBGT. To address this the repo was cloned to a new repo (SonOAlterCocker Yiddish for Old Fart)  and then the active scripts modified.

Original repo
    [https://github.com/savagebread/weewx-aprs/archive/refs/tags/v0.2.zip](https://github.com/savagebread/weewx-aprs/archive/refs/tags/v0.2.zip) 

New repo
    [https://github.com/sonoaltercocker/Scott-weewx-aprs.git](https://github.com/sonoaltercocker/Scott-weewx-aprs.git)

The program  Scott-weewx-aprs/bin/user/aprs-formatter.py has to be modified to support the WGT and WBGT values  included as comments as follows

    < # modified by Scott Sheppard July 28 2026 with help from AI CLAUDE
    <  # Bug Fix if record.get('daily_rain') is not None: changed to 'dayRain'
    <         if record.get('dayRain') is not None:
    <         # BGT and WBGT (Black Globe Temperature / Wet Bulb Globe Temperature)
    <         # have no defined field in the APRS weather-report spec, so they
    <         # cannot be sent as parsed weather data (e.g. a 't' field would be
    <         # read by parsers as a second, conflicting temperature reading).
    <         # Instead, append them as free-text in the comment area, where
    <         # APRS parsers stop looking for weather fields.

    <         comment_parts = []
    <         if record.get('bgt') is not None:
    <             try:
    <                 comment_parts.append('BGT=%03.fF' % record['bgt'])
    <             except Exception as e:
    <                 logging.error("weewx-aprs-packet-formatter - bgt - %s" % (e))
    <
    <         if record.get('wbgt') is not None:
    <             try:
    <                 comment_parts.append('WBGT=%03.fF' % record['wbgt'])
    <             except Exception as e:
    <                 logging.error("weewx-aprs-packet-formatter - wbgt - %s" % (e))
    <
    <             comment_parts.append(self._comment)
    <
    <         if comment_parts:
    <             data.append(' ' + ' '.join(comment_parts))


    $ weectl extension install [https://github.com/sonoaltercocker/Scott-weewx-aprs/archive/refs/tags/0.1-1.zip](https://github.com/sonoaltercocker/Scott-weewx-aprs/archive/refs/tags/0.1-1.zip)

Using configuration file /etc/weewx/weewx.conf
Install extension 'https://github.com/sonoaltercocker/Scott-weewx-aprs/archive/refs/tags/0.1-1.zip' (y/n)? y
Extracting from zip archive /tmp/tmp3sbfkj00
Saving installer file to /etc/weewx/bin/user/installer/aprs-formatter
Saved copy of configuration as /etc/weewx/weewx.conf.20260731200333
Finished installing extension aprs-formatter from [https://github.com/sonoaltercocker/Scott-weewx-aprs/archive/refs/tags/0.1-1.zip](https://github.com/sonoaltercocker/Scott-weewx-aprs/archive/refs/tags/0.1-1.zip)

Edit weewx.conf and change the value below from 0 to 1 to include position

    $ cd /etc/weewx
    $ nano weewx.conf

        [APRS]
        output_filename = /dev/shm/aprs.pkt
            include_position = 0 # change to 1 to add your position
        symbol_table = /
        symbol_code = _
        comment = ""
        station_model = default
        report_luminosity = 0

## Test the results

```bash
sudo systemctl restart weewx
sudo systemctl status weewx
```

The results should look similar to this. This assumes that your Ecowitt weather station is up and properly configured.

```text
root@digipi:/etc/weewx# systemctl status weewx

● weewx.service - WeeWX
...
Active: active (running) since Wed 2026-07-15 22:33:58 BST; 5s ago
...
```

Check the output to verify an APRS packet is created.

```bash
root@digipi:/home/pi# cd /dev/shm
```

This can take 5 to 10 minutes for the APRS packet to be published.

Is there an APRS packet file?

    ```bash
    root@digipi:/dev/shm# ls
    aprs.pkt
    ```

    ```bash
    root@digipi:/dev/shm# more aprs.pkt
    ```

This packet has positional information:

    ```text
    /112045z3310.99N/08416.09W_.../000g000t079r000h60b10186
    ```

Informational note: this is an example of an APRS packet without position:

    ```text
    _08011915c...s000g003t085r000h71b09754 BGT=091F WBGT=081F
    ```

**/ End of basic installation**


## APRS-send-weather.sh

This script takes APRS-formatted packets from /dev/shm and forwards them to Direwolf on the Raspberry Pi, then onward to an APRS-IS gateway.

### Download the script

    ```bash
    cd /usr/local/bin
    wget https://raw.githubusercontent.com/craigerl/aprs-send-weather/main/aprs-send-weather.sh
    ```

Make the script executable:

    ```bash
    chmod 755 aprs-send-weather.sh
    ```

Verify it is present:

    ```bash
    ls -la | grep aprs-send-weather.sh
    ```

Example output:

```text
-rwxr-xr-x 1 root staff 2428 Jul 11 00:06 aprs-send-weather.sh
```

### Edit the variables

Edit the script with your preferred editor:

```bash
sudo nano aprs-send-weather.sh
```

Update the values for the Direwolf host, your APRS-IS user name, and your passcode. The main settings to review are:

```bash
USER="WD5EMA-3"
PASS="23714"
DIREWOLFHOSTNAME=localhost
```

### Complete initialization of DigiPi

Return to http://digipi.local and complete the initialization steps. Use the Digipeater mode so Direwolf starts automatically.

### Test the script

Run the script manually:

```bash
cd /usr/local/bin
./aprs-send-weather.sh
```

You should see output similar to:

    ```text
    + USER=WD5EMA-3
    + PASS=23714
    + DIREWOLFHOSTNAME=localhost
    ...
    + echo 'WD5EMA-3>APRS,WIDE1-1:/132200z3350.52N/08416.09W_.../000g001t078r000h94b10164'
    + exit 0
    ```

## Housekeeping

Run the APRS send command every 5 minutes to match the WeeWX update interval, and reboot the Raspberry Pi every day. Sometimes processes can get stuck and the Pi may hang.

### Under the pi user, not root

Switch to the `pi` user and open the crontab:

    ```bash
    su - pi
    crontab -e
    ```

Add these lines to the end of the file:

    ```cron
    # Run the APRS send script every 5 minutes
    */5 * * * * /usr/local/bin/aprs-send-weather.sh

    # Reboot the Raspberry Pi every day at midnight
    0 0 * * * /sbin/reboot
    ```

Save and exit the editor.

Verify the configuration:

    ```bash
    crontab -l
    ```

You should see entries similar to:

    ```text
    */5 * * * * /usr/local/bin/aprs-send-weather.sh
    0 0 * * * /sbin/reboot


**/End house keeping**

Web access to reports from WD5EMA-3

It is possible to allow anyone with a specific URL to read the weather statistics from the Ecovitt WS 3900. The URL is

[https://www.ecowitt.net/home/share?authorize=5GM9U2](https://www.ecowitt.net/home/share?authorize=5GM9U2)

The URL is created by the ecowitt.net owner / administrator for the weather station supporting WD5EMA-3

    Scott Sheppard
    KJ4ZZB
    [Ssheppa9@bellsouth.net](mailto:Ssheppa9@bellsouth.net)
    July 2026


## Final notes

It is possible to add email addresses or distribution lists to Ecowitt.net so that if WBGT exceeds a chosen threshold, you can be notified.

    Example Thu, 16 Jul 12:50 PM Black Globe Temperature: WBGT at WS3900 is 85.3 °F.

Search for WD5EMA-3 on aprs.fi .

![APRS.FI WD5EMA-3](image-9.png)

Since the DigiPi is to be configured as a digipeater as well, there should be an entry for your call sign followed by -2. In this case, that would be KJ4ZZB-2 .

![APRS.FI KJ4ZZB-2](image-10.png)



## Appendix : Sheppard notes

### Troubleshooting notes for Digipeater

When the DigiPi APRS Digipeater selection is active, the TNC daemon appears to be inactive.

    pi@digipi:~ $ systemctl status tnc

    ○ tnc.service - tnc
    Loaded: loaded (/etc/systemd/system/tnc.service; disabled; preset: enabled)
    Active: inactive (dead)

When the DigiPi APRS Igate selection is active, the TNC daemon is active.

    pi@digipi:~ $ systemctl status tnc

    ● tnc.service - tnc
    Loaded: loaded (/etc/systemd/system/tnc.service; disabled; preset: enabled)
    Active: active (running) since Fri 2026-07-17 00:37:03 BST; 12s ago
    Invocation: 6d5938e4308f4c8295cd381c44e7c6fd
    Process: 1411 ExecStartPre=systemctl stop fldigi sstv wsjtx ardop tnc300b digipeater node winlinkrms js8call tracker
    Main PID: 1422 (direwolf.tnc.sh)
    Tasks: 24 (limit: 4020)
    CPU: 1.552s
    CGroup: /system.slice/tnc.service
    ...
    Jul 17 00:37:05 digipi direwolf.tnc.sh[1422]: + sudo rfcomm --raw watch /dev/rfcomm0 1 socat -d -d tcp4:127.0.0.1:8001 /dev/rfcomm0

## Appendix : Troubleshooting notes Digipi  MAPS.

Digipi Ver 2.1-3 Maps function is working correctly. Note the author’s station KJ4ZZB-2 or WD5EMA-3

![Digipi Maps Result](image-11.png)


## Appendix : Correct /home/pi/localize.env after initialization if there are mistakes. 

    Edit  /home/pi/localize.env

        sudo remount # at login to shell

    Edit this file. Save. Reboot and when DigiPi comes back up it should read this .ENV and be correct.

        \
        This file is used when you press "Initialize." Running it a second \
        time is illadvised unless you also change the OLD values to your \
        current configuration.   DigiPi will dynamically read the NEW  \
        variables below for  \
        NEWRIGNUMBER, NEWDEVICEFILE, DISPLAYTYPE  \
        NEWBAUDRATE and NEWDISPLAYTYPE at runtime.  \
        \
        \
        NEWCALL=KJ4ZZB \
        NEWWLPASS=****** \
        NEWAPRSPASS=22192 \
        NEWGRID=EM73UT \
        NEWLAT=33.83187133 \
        NEWLON=-84.26841  \
        NEWGPS=ttyACM1 \
        NEWNODEPASS=***** \
        NEWDISPLAYTYPE=st7789 \
        NEWRIGNUMBER=CM108 \
        NEWDEVICEFILE=hidraw0 \
        NEWBAUDRATE=115200 \
        NEWBIGVNC=1 \
        NEWFLRIG= \
        NEWI2CAUDIO=fepi \
    \
    Nothing to edit below here \
        \
        OLDCALL=KX6XXX \
        OLDWLPASS=XXXXXX \
        OLDAPRSPASS=XXXXXX \
        OLDGRID=CN99mv \
        OLDLAT=39.9999 \
        OLDLON=-140.9999 \
        OLDGPS=ttyACM1 \
        OLDNODEPASS=XXXXXX \
        OLDDISPLAYTYPE=st7789 \
        OLDRIGNUMBER=3085 \
        OLDDEVICEFILE=ttyACM0 \
        OLDBAUDRATE=115200 \
        OLDBIGVNC= \
        OLDFLRIG= \
        OLDI2CAUDIO=fepi

## Appendix : Resource utilization for the Raspberry Pi 4 hosting Digipi and Weewx

(Note the prototype system is in use and is in a grey plastic box outside in the Georgia summer heat. This may explain high CPU temperatures.)

    Raspberry Pi 4 Model B Rev 1.1 (Used due to built in 4 USB ports for convivence)
    ![Google Drawing Alt Text](Google_Drawing_1)
    Radio / GPS
    ttyACM0:  usb-AIOC_All-In-One-Cable_4e0bdf9d-if04 \
    ttyACM1:  usb-u-blox_AG_-_www.u-blox.com_u-blox_7_-_GPS_GNSS_Receiver-if00

    ![Google Drawing Alt Text](Google_Drawing_2)

    Audio Interface (To Baofeng UV5R)
    0 [AllInOneCable ]: USB-Audio - All-In-One-Cable
    AIOC All-In-One-Cable at usb-0000:01:00.0-1.3, full speed
    ![Google Drawing Alt Text](Google_Drawing_3)
    Memory Usage: 8%
    CPU Load Average: 0.05
    Disk Usage: 77% (SD card 8 GB, 16 or 32 GB recomended)
    Network Connections: 2
    WiFi: Link Quality=47/70 Signal level=-63 dBm
    CPU Count: 4
    CPU Temp: 57.9'C (outside temp 24C)
    Mem Total: 3.932 GB (Over kill)
    Mem Used: 0.3 GB
    Mem Available: 3.63 GB
    SD Free: 1.232 GB
    SD Used: 4.065 GB
    SD Total: 5.297 GB
    Host Name: digipi.local
    Host Address: 2600:1700:1c60:3610::1c
    System Clock: Tue Jul 14 16:12:38 BST 2026
    up 11 hours, 56 minutes (rebooted with crontab at midnight)

## Appendix : Costs 

    Basic Ecovitt materials needed for Dekalb Ares (Total $90.00 -$120.00 with shipping etc.)
    WN38 Black Globe Thermometer, Wet Bulb Globe Temperature, Heat Stress Monitor Kit $90.00
    WN32 Outdoor Thermo-Hygrometer
    GW1200 Gateway

    Sheppard's home weather station:  (Total  $351.00)
    Not including 1" 15 foot pol, glue and reduction PVC fittings. 
    Wittboy Electronic 7-in-1 Wi-Fi Weather Station $229.00
    Includes:
    WS90 WS90 Wireless 7-in-1 Electronic Sensor Array Haptic Rain Gauge and Ultrasonic Anemometer
    WS3900 7 inch display
    Add sensor for lightening detection:
    Rain Shield for WH57/WN32/WN31/WN30 $19
    WH57 Outdoor Wireless Lightning Detection Sensor $57
    Add sensor for WBGT calculation:
    WN38 Black Globe Thermometer, Wet Bulb Globe Temperature $46.00

## Appendix: How to evaluate if Digipi will generate a Digipi hotspot

    $ systemctl status autohotspot
        ● autohotspot.service - Automatically generates an internet Hotspot when a valid ssid is not in range
        Loaded: loaded (/etc/systemd/system/autohotspot.service; enabled; preset: enabled)
        Active: active (exited) since Fri 2026-07-17 21:10:50 BST; 2h 19min ago
        Invocation: 950e4faee5384973b2fdec1c61f2d10c
        Process: 884 ExecStartPre=sleep 30 (code=exited, status=0/SUCCESS)
        Process: 981 ExecStart=/usr/local/bin/digihotspot.sh (code=exited, status=0/SUCCESS)
        Main PID: 981 (code=exited, status=0/SUCCESS)
        CPU: 43ms
        Jul 17 21:10:20 digipi systemd[1]: Starting autohotspot.service - Automatically generates an internet Hotspot when a valid ssid is not in range...
        Jul 17 21:10:50 digipi digihotspot.sh[981]: Auto-hotspot checking network status.
        Jul 17 21:10:50 digipi systemd[1]: Finished autohotspot.service - Automatically generates an internet Hotspot when a valid ssid is not in range.

## Appendix: What ports are in use on a Digpi

        pi@digipi:~ $ sudo netstat -npvat | grep LISTEN

        tcp        0      0 0.0.0.0:22              0.0.0.0:*               LISTEN      720/sshd: /usr/sbin
        tcp        0      0 0.0.0.0:80              0.0.0.0:*               LISTEN      769/lighttpd
        tcp        0      0 0.0.0.0:9000            0.0.0.0:*               LISTEN      750/python3         
        tcp        0      0 127.0.0.1:2947          0.0.0.0:*               LISTEN      1/init
        tcp        0      0 0.0.0.0:8000            0.0.0.0:*               LISTEN      1020/direwolf
        tcp        0      0 0.0.0.0:8001            0.0.0.0:*               LISTEN      1020/direwolf
        tcp        0      0 0.0.0.0:8055            0.0.0.0:*               LISTEN      1052/python

The key here is that 8000, 8001 and 8088 are in use. So for WeeWx we will use port 9000. NEVER change ports for Direwolf.

This has resolved our MAP problem. The Digipi listens to port 8000 for packet mapping data and the WeeWx damon should be on a separate port  (in this case 9000) to avoid that conflict.

## Appendix : Sqlite commands  

Verify access to Weewx database access

WeeWX uses **SQLite** as its default database engine.
  **Weather Data Binding:** Uses the standard binding wx_binding
  **Schema:** Typically uses wview_extended.schema, which tracks standard weather variables like temperature, wind, rain, pressure, and humidity.
  **Units:** By default, it stores weather parameters using **US Customary units** (e.g., Fahrenheit, inches of mercury, miles per hour), though reports can be customized to display metric units. 

    $ sudo remount

Run some test sqlite commands to make sure the weewx DB is accessible

    cd /var/lib/weewx
    
    sqlite3 weewx.sdb .tables
    sqlite3 weewx.sdb .fullschema
    weectl database check

These are working examples

    sqlite3 weewx.sdb "SELECT * FROM archive;" 
    sqlite3 weewx.sdb "SELECT datetime(dateTime, 'unixepoch', 'localtime'), * FROM archive;" 
    sqlite3 weewx.sdb "SELECT datetime(dateTime, 'unixepoch', 'localtime'), outTemp FROM archive ORDER BY dateTime DESC LIMIT 1;"
    sqlite3 weewx.sdb "SELECT datetime(dateTime, 'unixepoch', 'localtime'), max(outTemp) FROM archive;" 
    sqlite3 weewx.sdb "SELECT sum(rain) FROM archive WHERE dateTime > 1672531200 AND dateTime < 1704067200;" 
    sqlite3 weewx.sdb "SELECT dateTime, outTemp AS Air_Temp_F, outHumidity AS Humidity_Pct FROM archive;" 

Extract WBT and WBGT from the WS3900 data stream
To examine all possible collected fields in the  WeeWx DB see (some items highlighted for personal education):

    sqlite3 /var/lib/weewx/weewx.sdb "PRAGMA table_info(archive);"

        0|dateTime|INTEGER|1||1
        …
        21|ET|REAL|0||0 **Evapotranspiration**.
        …
        48|illuminance|REAL|0||0 **ambient light brightness** (visible light) LUX -> cloud cover
        …
        62|luminosity|REAL|0||0 **ambient light brightness**, LUX
        63|maxSolarRad|REAL|0||0 estimated solar energy/radiation W/m2
        64|nh3|REAL|0||0 **Ammonia EW**
        65|no2|REAL|0||0 **Nitrogen Dioxide**. EW
        …
        67|o3|REAL|0||0 **Ozone** Ecowitt WH45 or DP500
        …
        71|pb|REAL|0||0 **Pressure barometric Many third-party drivers (like Ecowitt) repurpose this unused column for custom metrics**
        72|pm10_0|REAL|0||0 **Particle meas. 10 microns**
        73|pm1_0|REAL|0||0 **Particle meas. 1 microns**
        74|pm2_5|REAL|0||0 **Particle meas. 2.5 microns**
        ….
        Not the full list.

## Appendix : Discord reference verify WS3900 data without a driver or WeeWx (important) 

[https://discord.com/channels/1075675015707639838/1529208597060522216](https://discord.com/channels/1075675015707639838/1529208597060522216)

To access the network settings of the ws3900 use [http://192.168.1.241](http://192.168.1.241) Local to my machine

Does the WS399 export WBGT values in a HTTP stream? 
    YES

Using this link [https://ear.phantasoft.de/](https://ear.phantasoft.de/)
[Ecowitt AutoResponder v0.20](https://ear.phantasoft.de/)
add this mac 48:f6:ee:a6:cd:ec with set up on the WS 3900 

Result

    PASSKEY=A994B28F7061B031BE10010B67AC3E05&stationtype=WS3900B_V1.4.8&runtime=621073&heap=74396&dateutc=2026-07-25 20:20:42&tempinf=75.92&humidityin=51&baromrelin=29.010&baromabsin=29.010&tempf=87.98&humidity=66&bgt=86.00&wbgt=81.14&vpd=0.454&winddir=150&winddir_avg10m=150&windspeedmph=0.00&windgustmph=0.00&maxdailygust=2.46&solarradiation=0.08&uv=0&rrain_piezo=0.000&erain_piezo=0.000&hrain_piezo=0.000&last24hrain_piezo=0.000&drain_piezo=0.000&wrain_piezo=0.634&mrain_piezo=1.945&yrain_piezo=1.945&srain_piezo=0&ws90cap_volt=2.4&ws90_ver=160&lightning_num=1&lightning=12&lightning_time=1785009243&console_batt=4.50&wh57batt=5&wh90batt=3.14&bgtbatt=1.62&freq=915M&model=WS3900B&interval=30

**Read the chapter on data flow in our WiKi to get a better understanding ...**

 [https://meshka.eu/Ecowitt/dokuwiki/doku.php?id=start2#data_flow_between_sensors_consoles_application_software_and_internet_weather_services](https://meshka.eu/Ecowitt/dokuwiki/doku.php?id=start2#data_flow_between_sensors_consoles_application_software_and_internet_weather_services) 

**Attention : weewx chapter**

[https://meshka.eu/Ecowitt/dokuwiki/doku.php?id=dataloggers#weewx](https://meshka.eu/Ecowitt/dokuwiki/doku.php?id=dataloggers#weewx) and there about the interceptor driver - you may just use an old and no longer supported version 

/End of Auto responder

weectl extension install [https://raw.githubusercontent.com/WernerKr/Ecowitt-or-DAVIS-stations-and-Season-skin/main/ecowittcustom.py](https://raw.githubusercontent.com/WernerKr/Ecowitt-or-DAVIS-stations-and-Season-skin/main/ecowittcustom.py)

##  Appendix :  APRS extraction to create a APRS packet of collected information

root@digipi:/etc/weewx/bin/user# weectl extension install https://github.com/savagebread/weewx-aprs/archive/refs/tags/v0.2.zip

This repo contains

![master contents](image-14.png)

Where BIN/USER has the program we are interested in

![/bin/user](image-13.png)

## Appendix : Setting up git and cloning a repo 

Based on

[https://www.tutorialpedia.org/blog/cloning-a-repo-from-someone-else-s-github-and-pushing-it-to-a-repo-on-my-github/](null)

set up homebrew
$ /bin/bash -c "$(curl -fsSL [https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh](https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh))"

- Run these commands in your terminal to add Homebrew to your PATH:
$echo >> /Users/scott/.bash_profile
$echo 'eval "$(/opt/homebrew/bin/brew shellenv bash)"' >> /Users/scott/.bash_profile
$eval "$(/opt/homebrew/bin/brew shellenv bash)"
- Run brew help to get started
- Further documentation:
    [https://docs.brew.sh](https://docs.brew.sh)
$ brew install git
Copy the repo source to my MAC
$ git clone [https://github.com/savagebread/weewx-aprs.git](https://github.com/savagebread/weewx-aprs.git)
to weewx-aprs
$ ls # do I have a new dir called weewx-aprs
    yes 
…

weewx-aprs
Move to this weewx-aprs directory and verify the source files are present
    $cd weewx-aprs/
    $ls # cool
        bin img install.py license.txt readme.md readme.txt
Move this to MY git repo
    $git remote -v
    Origin https://github.com/savagebread/weewx-aprs.git (fetch)
    origin	 https://github.com/savagebread/weewx-aprs.git (push)

Here, origin is the default name for the remote repository. It currently points to the original owner’s repo.
    $git remote set-url origin https://github.com/sonoaltercocker/Scott-weewx-aprs.git
    $git remote -v

Origin https://github.com/sonoaltercocker/Scott-weewx-aprs.git (fetch)
Origin https://github.com/sonoaltercocker/Scott-weewx-aprs.git (push)

    $ git push origin master
        Username for 'https://github.com': sonoaltercocker
        Password for 'https://sonoaltercocker@github.com':
        Enumerating objects: 70, done.
        Counting objects: 100% (70/70), done.
        ….
        remote: Create a pull request for 'master' on GitHub by visiting:
        remote:      https://github.com/sonoaltercocker/Scott-weewx-aprs/pull/new/master
        remote:
        To https://github.com/sonoaltercocker/Scott-weewx-aprs.git
        * [new branch]      master -> master
        Install GitHub CLI from [cli.github.com](https://cli.github.com/).

    $ brew install gh
….

        ==> Pouring gh--2.96.0.arm64_tahoe.bottle.tar.gz
        🍺  /opt/homebrew/Cellar/gh/2.96.0: 238 files, 38.7MB
        ==> Running <code>brew cleanup gh</code>...
        Disable this behaviour by setting <code>HOMEBREW_NO_INSTALL_CLEANUP=1</code>.
        Hide these hints with <code>HOMEBREW_NO_ENV_HINTS=1</code> (see <code>man brew</code>).
        ==> Caveats
        Bash completion has been installed to:
        /opt/homebrew/etc/bash_completion.d

    $ gh auth login

        ? Where do you use GitHub? GitHub.com
        ? What is your preferred protocol for Git operations on this host? HTTPS
        ? Authenticate Git with your GitHub credentials? Yes
        ? How would you like to authenticate GitHub CLI? Login with a web browser
        …...
        ✓ Authentication complete.

    $ gh config set -h github.com git_protocol https
        ✓ Configured git protocol
        ✓ Logged in as **sonoaltercocker**

Check Your GitHub Repo[#](https://www.tutorialpedia.org/blog/cloning-a-repo-from-someone-else-s-github-and-pushing-it-to-a-repo-on-my-github/#7-1-check-your-github-repo)
Go to your new repo’s URL (e.g., `https://github.com/your-username/your-new-repo`). Refresh the page.    

 Looking at the aprs-formatter.py

    Are these values found in the WeeWx database?

        if record.get('windDir') is not None:
        if record.get('windSpeed') is not None:
        if record.get('windGust') is not None:
        if record.get('outTemp') is not None:
        if record.get('rainRate') is not None:
        if record.get('daily_rain') is not None:
        if record.get('outHumidity') is not None:
        if record.get('barometer') is not None:
        if record.get('luminosity') is not None:
            All of these terms except daily_rain are variables in the WeeWX SDB

$ sqlite3 /var/lib/weewx/weewx.sdb "SELECT datetime(dateTime, 'unixepoch', 'localtime'), windDir FROM archive ORDER BY dateTime DESC LIMIT 1;"
    2026-07-27 17:05:00|
$ sqlite3 /var/lib/weewx/weewx.sdb "SELECT datetime(dateTime, 'unixepoch', 'localtime'), windSpeed FROM archive ORDER BY dateTime DESC LIMIT 1 ;"
    2026-07-27 17:05:00|0.0
$ sqlite3 /var/lib/weewx/weewx.sdb "SELECT datetime(dateTime, 'unixepoch', 'localtime'), windDir FROM archive ORDER BY dateTime DESC LIMIT 1;"
    2026-07-27 17:05:00|
$ sqlite3 /var/lib/weewx/weewx.sdb "SELECT datetime(dateTime, 'unixepoch', 'localtime'), windGust FROM archive ORDER BY dateTime DESC LIMIT 1;"
    2026-07-27 17:05:00|0.0
$ sqlite3 /var/lib/weewx/weewx.sdb "SELECT datetime(dateTime, 'unixepoch', 'localtime'), outTemp FROM archive ORDER BY dateTime DESC LIMIT 1;"
    2026-07-27 17:05:00|80.78
$ sqlite3 /var/lib/weewx/weewx.sdb "SELECT datetime(dateTime, 'unixepoch', 'localtime'), rainRate FROM archive ORDER BY dateTime DESC LIMIT 1;"
    2026-07-27 17:05:00|0.0
$ sqlite3 /var/lib/weewx/weewx.sdb "SELECT datetime(dateTime, 'unixepoch', 'localtime'), outHumidity FROM archive ORDER BY dateTime DESC LIMIT 1;"
    2026-07-27 17:05:00|68.0
$ sqlite3 /var/lib/weewx/weewx.sdb "SELECT datetime(dateTime, 'unixepoch', 'localtime'), barometer FROM archive ORDER BY dateTime DESC LIMIT 1;"
    2026-07-27 17:05:00|28.9025
$ sqlite3 /var/lib/weewx/weewx.sdb "SELECT datetime(dateTime, 'unixepoch', 'localtime'), luminosity FROM archive ORDER BY dateTime DESC LIMIT 1;"
    2026-07-27 17:05:00|
$ sqlite3 /var/lib/weewx/weewx.sdb "SELECT datetime(dateTime, 'unixepoch', 'localtime'), bgt FROM archive ORDER BY dateTime DESC LIMIT 1;"
    2026-07-27 17:05:00|80.24    
$ sqlite3 /var/lib/weewx/weewx.sdb "SELECT datetime(dateTime, 'unixepoch', 'localtime'), wbgt FROM archive ORDER BY dateTime DESC LIMIT 1;"
    2026-07-27 17:05:00|75.02

## APPENDIX : WeeWx.conf edited for this project 

This section is for information about the station.
[Station]

Description of the station location, such as your town.
    
    location = Decatur Georgia USA 30033

Latitude in decimal degrees. Negative for southern hemisphere.
    
    latitude = 33.83194

Longitude in decimal degrees. Negative for western hemisphere.
    
    longitude = -84.26809083

Altitude of the station, with the unit it is in. This is used only
if the hardware cannot supply a value.

    altitude = 301, meter    # Choose 'foot' or 'meter' for unit

Set to type of station hardware. There must be a corresponding stanza
in this file, which includes a value for the 'driver' option.

    station_type = Ecowittcustom

If you have a website, you may specify an URL. The URL is required if you
intend to register your station. The URL must include the scheme, for
example, "http://" or "https://"
station_url = https://www.example.com

The start of the rain year (1=January; 10=October, etc.). This is downloaded from the station if the hardware supports it.

    rain_year_start = 1 # default

Start of week (0=Monday, 6=Sunday)
   
    week_start = 6 # default

</h6></h6>
[Ecowittcustom]
    This section is for the Fine Offset series of weather stations.
    The station model, e.g., WH1080, WS1090, WS2080, WH3081
   
     model = WS3900

How often to poll the station for data, in seconds
   
    polling_interval = 60 # default

*** Important ***
The driver to use:
   
    driver = user.ecowittcustom
    port = 9000 # unique to my workstation
    device_type = ecowitt-client

</h6></h6>

[Simulator]
…
</h6></h6>
This section is for uploading data to Internet sites

[StdRESTful]
    Uncomment and change to override logging for uploading services.
…
</h6></h6>
This section specifies what reports, using which skins, to generate.

[StdReport]
…
</h6></h6>
[Simulator]
…
</h6></h6>
This section is for uploading data to Internet sites

[StdRESTful]
…
</h6></h6>
This section specifies what reports, using which skins, to generate.

[StdReport]
…
</h6></h6>
This service converts the unit system coming from the hardware to a unit
system in the database.

[StdConvert]
…

</h6></h6>
This section can adjust data using calibration expressions.

[StdCalibrate]
…

</h6></h6>
This section is for quality control checks. If units are not specified,
values must be in the units defined in the StdConvert section.

[StdQC]
…

</h6></h6>
This section controls the origin of derived values.

[StdWXCalculate]
…

</h6></h6>
For hardware that supports it, this section controls how often the
onboard clock gets updated.

[StdTimeSynch]
…

</h6></h6>
This section is for configuring the archive service.

[StdArchive]
…

</h6></h6>
This section binds a data store to a database.

[DataBindings]
…

</h6></h6>
This section defines various databases.

[Databases]
…

</h6></h6>
This section defines defaults for the different types of databases.

[DatabaseTypes]
…

</h6></h6>
This section configures the internal weewx engine.

[Engine]
…

[APRS]

output_filename = /dev/shm/aprs.pkt

    include_position = 1 # Force the position to be inclueded in the APRS packet.
    symbol_table = /
    symbol_code = _
    comment = ""
    station_model = default
    report_luminosity = 0

/End
