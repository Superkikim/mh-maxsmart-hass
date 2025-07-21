# MaxSmart (Revogi) for Home Assistant

[![Version](https://img.shields.io/badge/Version-2025.7.1-blue.svg)](https://github.com/superkikim/mh-maxsmart-hass/releases)
[![Home Assistant](https://img.shields.io/badge/Home%20Assistant-2023.6%2B-green.svg)](https://www.home-assistant.io/)
[![HACS](https://img.shields.io/badge/HACS-Compatible-orange.svg)](https://hacs.xyz/)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Maintenance](https://img.shields.io/badge/Maintained-Yes-brightgreen.svg)](https://github.com/superkikim/mh-maxsmart-hass)

Control your **Max Hauri MaxSmart** smart power strips and plugs directly from Home Assistant! No cloud required - everything works locally on your network.

## 🎯 What's New in v2025.7.1

- **🔄 Automatic Migration** - Seamless upgrade from older versions
- **🧠 Smart Device Detection** - Automatically identifies 1-port vs 6-port devices
- **🔧 Enhanced Reliability** - Better error handling and network connectivity
- **⚡ Real-time Monitoring** - Live power consumption tracking
- **🏷️ Easy Customization** - Simple device and port renaming

## 📱 Supported Devices

| Device Type | Ports | Model Examples |
|-------------|-------|----------------|
| **Smart Plug** | 1 port | Max Hauri Smart Plug |
| **Power Station** | 6 ports | Max Hauri MaxSmart Power Station |
| **Compatible Models** | Various | Revogi, Extel Soky, MCL DOM-PPS06I |

### ✅ Firmware Compatibility
- **v1.30** - Full support (all features)
- **v2.11+** - Basic control (power monitoring only)
- **Auto-detection** - The integration adapts to your firmware automatically

## 🚀 Installation

### Option 1: HACS (Recommended)
1. Open **HACS** in Home Assistant
2. Go to **Integrations**
3. Search for **"MaxSmart"**
4. Click **Install**
5. Restart Home Assistant

### Option 2: Manual Installation
1. Download the latest release from [GitHub](https://github.com/superkikim/mh-maxsmart-hass/releases)
2. Extract to `config/custom_components/maxsmart/`
3. Restart Home Assistant

## ⚙️ Setup & Configuration

### 1. Add Integration
1. Go to **Settings** → **Devices & Services**
2. Click **Add Integration**
3. Search for **"MaxSmart (Revogi)"**
4. Follow the setup wizard

### 2. Device Discovery
The integration will **automatically find** your MaxSmart devices on the network:

- ✅ **Found devices?** Great! They'll be added automatically
- ❌ **No devices found?** Enter your device IP address manually

### 3. Customize Names (Optional)
During setup, you can customize:
- **Device name** (e.g., "Living Room Power Strip")
- **Port names** (e.g., "TV", "Lamp", "Router")

## 🎛️ What You'll Get

### For 6-Port Power Stations
- **1 Master Switch** - Controls all ports at once
- **6 Individual Switches** - Control each port separately  
- **7 Power Sensors** - Total power + individual port consumption
- **Smart Icons** - Different icons based on usage

### For 1-Port Smart Plugs
- **1 Switch** - On/off control
- **1 Power Sensor** - Real-time consumption monitoring
- **Clean Interface** - No unnecessary master controls

## 📊 Features Overview

### 🔌 Device Control
- **Individual Port Control** - Turn any port on/off
- **Master Control** - All ports at once (6-port devices)
- **Real-time Status** - See which ports are active
- **Reliable Commands** - Built-in retry for network issues

### ⚡ Power Monitoring
- **Live Consumption** - See power usage in real-time
- **Individual Tracking** - Monitor each port separately
- **Total Power** - Overall consumption (6-port devices)
- **Smart Units** - Automatic watt/kilowatt conversion

### 🛠️ Management
- **Easy Renaming** - Change device and port names anytime
- **Auto-Discovery** - Finds devices automatically
- **Status Monitoring** - Device health and connectivity
- **Error Recovery** - Automatic reconnection

## 🔧 Customization

### Rename Devices & Ports
1. Go to **Settings** → **Devices & Services**
2. Find your MaxSmart device
3. Click the **⚙️ gear icon**
4. Update names as needed
5. Click **Submit**

Changes apply immediately - no restart required!

### Examples of Good Names
- **Device**: "Kitchen Power Strip", "Office Outlets"
- **Ports**: "Coffee Maker", "Microwave", "Desk Lamp"

## 🔄 Migration from Older Versions

### What Happens During Migration?
If you're upgrading from an older version, the integration will:

1. **🔍 Detect Legacy Setup** - Finds your old configuration
2. **🔧 Enhance Device Info** - Adds hardware identification
3. **🧹 Clean Up Entities** - Removes incorrect entities (1-port devices)
4. **💾 Preserve Settings** - Keeps your custom names and configuration
5. **✅ Show Notification** - Confirms successful migration

### Migration Notification
After upgrading, you'll see a notification confirming the migration:
> "4 MaxSmart devices have been migrated. You can customize device and port names by clicking the gear icon of each device."

### What's Preserved?
- ✅ **Device names** you've customized
- ✅ **Port names** you've set
- ✅ **All automations** and scripts
- ✅ **Historical data** and statistics

### What's Improved?
- 🚀 **Better reliability** - Enhanced error handling
- 🧠 **Smart detection** - Correct entities for device type
- 🔧 **Easier management** - Simplified renaming process

## 🛡️ Troubleshooting

### Common Issues

#### Device Not Found
**Problem**: Integration can't find your device
**Solutions**:
- Ensure device is powered on and connected to your network
- Try entering the IP address manually
- Check that Home Assistant and device are on the same network

#### Connection Errors
**Problem**: Device becomes unavailable
**Solutions**:
- Check device IP hasn't changed (use DHCP reservation)
- Verify network connectivity
- Restart the device by unplugging for 10 seconds

#### Wrong Number of Entities
**Problem**: 1-port device shows master switch
**Solutions**:
- The new version automatically fixes this
- If upgrading, the migration will clean up incorrect entities
- For new setups, entities are created correctly

### Getting Help
1. **Check Logs** - Look in Home Assistant logs for error details
2. **GitHub Issues** - Report problems at [our issue tracker](https://github.com/superkikim/mh-maxsmart-hass/issues)
3. **Provide Details** - Include device model, firmware version, and error messages

## 📱 Entity Naming

The integration creates entities with clear, consistent names:

### 6-Port Power Station Example
```
Device: "Living Room Power Strip"
├── Master (switch.living_room_power_strip_master)
├── TV (switch.living_room_power_strip_tv)
├── Lamp (switch.living_room_power_strip_lamp)
├── Total Power (sensor.living_room_power_strip_total_power)
├── TV Power (sensor.living_room_power_strip_tv_power)
└── Lamp Power (sensor.living_room_power_strip_lamp_power)
```

### 1-Port Smart Plug Example
```
Device: "Coffee Maker Plug"
├── Coffee Maker Plug (switch.coffee_maker_plug)
└── Coffee Maker Plug Power (sensor.coffee_maker_plug_power)
```

## 🔒 Security & Privacy

- **🏠 Local Control** - Everything works on your local network
- **🚫 No Cloud** - No data sent to external servers
- **🔓 Unencrypted** - Uses plain HTTP (device limitation)
- **🛡️ Network Security** - Ensure devices are on trusted network

## ⚠️ Important Notes

### Device Limitations
- **HTTP Only** - Devices use unencrypted communication
- **Same Network** - Must be on same network as Home Assistant
- **Port Limits** - 1 or 6 ports depending on model

### Firmware Compatibility
- **v1.30** - Recommended, full feature support
- **v2.11+** - Basic features only
- **Older versions** - May work but not officially supported

### End of Life Notice
MaxSmart products are **discontinued** by Max Hauri. This integration provides local control as cloud services may be discontinued.

## 🤝 Contributing

We welcome contributions! Here's how you can help:

- 🐛 **Report Bugs** - Use our [issue tracker](https://github.com/superkikim/mh-maxsmart-hass/issues)
- 💡 **Suggest Features** - Share your ideas
- 🔧 **Submit Fixes** - Pull requests welcome
- 📚 **Improve Docs** - Help make documentation better

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 Credits

- **Original Protocol** - Thanks to [@altery](https://github.com/altery/mh-maxsmart-powerstation) for reverse engineering
- **Python Module** - Built on the [maxsmart](https://pypi.org/project/maxsmart/) library
- **Community** - Thanks to all users providing feedback and testing

---

**⚠️ Disclaimer**: This is a third-party integration, not officially supported by Home Assistant or Max Hauri. Use at your own risk.