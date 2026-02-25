# Pool Comfort - Home Assistant Integration

Custom Home Assistant integration for **Pool Comfort** heat pump controllers (GalaxyWind/Wotech-based WiFi modules).

Communicates with the device via the cloud relay using the proprietary Alsavo UDP protocol, providing full monitoring and control from Home Assistant.

## Features

### Climate Entity
- **Temperature control** — set target pool temperature (15–40°C)
- **Mode control** — Auto, Cool, Heat, or Off
- **Current temperature** — shows water inlet temperature
- **HVAC action** — shows whether the unit is actively heating, cooling, or idle

### Temperature Sensors
- Water Inlet Temperature
- Water Outlet Temperature
- Ambient Temperature
- Evaporator Coil Temperature (diagnostic)
- Discharge Gas Temperature (diagnostic)
- Return Gas Temperature (diagnostic)
- EEV Steps (diagnostic)

### Binary Sensors (Diagnostic)
- Compressor
- Four-way Valve
- High/Low Fan Speed
- Circulation Pump
- Electric Heater / Bottom Heater
- Low/High Pressure Switch
- Waterflow Switch

## Installation

### HACS (Recommended)

1. Open HACS in Home Assistant
2. Click the three dots in the top right → **Custom repositories**
3. Add `https://github.com/MendyLanda/ha-pool-comfort` as an **Integration**
4. Search for "Pool Comfort" and install
5. Restart Home Assistant

### Manual

1. Copy the `custom_components/pool_comfort` folder into your Home Assistant `config/custom_components/` directory
2. Restart Home Assistant

## Configuration

1. Go to **Settings → Devices & Services → Add Integration**
2. Search for **Pool Comfort**
3. Enter your device serial number (12 digits, printed on the device label) and password (default: `123456`)
4. The integration will discover the cloud relay and connect to your device

## How It Works

The integration connects to your heat pump through the manufacturer's cloud relay server. It:

1. **Discovers** the cloud relay via the UCC dispatcher protocol
2. **Authenticates** with a 3-step MD5 handshake using your serial number and password
3. **Polls** device registers every 30 seconds for status updates
4. **Sends** control commands (temperature, mode, power) through the cloud relay

> **Note:** This integration requires an active internet connection on both Home Assistant and the heat pump's WiFi module, as communication goes through the cloud relay.

## Requirements

- A Pool Comfort heat pump with a WiFi module (GalaxyWind/Wotech-based)
- The device serial number (12 digits)
- Device password (default is `123456`)
- The heat pump must be connected to the internet

## Credits

Built by reverse engineering the Pool Comfort mobile app (`com.gwcd.htc_en_oem`) and analyzing wire protocol captures.
