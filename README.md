# Max Hauri MaxSmart (Revogi based) for Home Assistant

[![Version](https://img.shields.io/badge/Version-2025.8.2-blue.svg)](https://github.com/superkikim/mh-maxsmart-hass/releases)
[![Home Assistant](https://img.shields.io/badge/Home%20Assistant-2023.6%2B-green.svg)](https://www.home-assistant.io/)
[![HACS](https://img.shields.io/badge/HACS-Official-brightgreen.svg)](https://hacs.xyz/)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Maintenance](https://img.shields.io/badge/Maintained-Yes-brightgreen.svg)](https://github.com/superkikim/mh-maxsmart-hass)

Control your **Max Hauri MaxSmart** smart power strips and plugs directly from Home Assistant! **No cloud required** - everything works locally on your network.

These are **REVOGI-based devices**. Other REVOGI-based devices might work as well. Feel free to test and come back to me for any feedback. We may work together to make them work.

> **💡 Future-Proof Your Investment:** These devices are EOL (End of Life) with cloud services scheduled for decommissioning. This integration provides a **cloud-free solution** to keep your perfectly functional hardware running indefinitely, independent of manufacturer support.

## ☕ Support My Work

If this integration makes your life easier, consider supporting its development:

[![Support me on Ko-fi](https://ko-fi.com/img/githubbutton_sm.svg)](https://ko-fi.com/nexusplugins)

**Suggested amounts:**

- **$5** - Fuel my coding sessions with caffeine ☕
- **$25** - Power my AI development tools 🤖
- **$75** - Supercharge my entire dev toolkit 🚀

*Your support helps me continue building useful tools and explore new ways of making your life easier.*

## ✨ What's New in v2025.8.2 - UDP Protocol Support

**🎯 Major Protocol Enhancements:**
- **📡 UDP V3 Protocol Support** - Full support for newer MaxSmart devices using UDP V3 protocol
- **🔄 Automatic Protocol Detection** - Seamless detection and handling of both HTTP and UDP V3 devices
- **🆙 MaxSmart Library 2.1.0** - Updated to latest maxsmart library with enhanced protocol support
- **🔧 Smart Device Creation** - Intelligent device initialization based on detected protocol

**🔧 Technical Improvements:**
- **🛡️ Enhanced Discovery** - Improved device discovery with protocol identification
- **📱 Better Device Support** - Support for firmware v5.11+ with UDP V3 protocol
- **⚡ Seamless Migration** - Automatic upgrade from maxsmart 2.0.5 to 2.1.0
- **🔧 Protocol Routing** - Intelligent routing between HTTP and UDP V3 based on device capabilities

## ✨ What's New in v2025.8.1 - User Experience Improvements

**🎯 Major UX Enhancements:**
- **🌐 Manual IP Configuration** - Add IP field in device settings with connection validation
- **🔄 Automatic IP Change Detection** - Seamless reconfiguration when device IP changes (i.e. DHCP lease renewal)
- **📝 Clearer Log Messages** - Simplified, actionable messages with 3-message cycle format
- **🌍 Enhanced Language Support** - Added Spanish and Italian translations (5 languages total)

**🔧 Technical Improvements:**
- **📱 Improved Device Information** - Cleaner device details with essential info (IP, SN, MAC)
- **🛡️ Enhanced Error Handling** - Better error management and network cascade detection
- **⚡ Silent Migration** - Seamless upgrade from existing devices with zero user intervention
- **🔧 Simplified Configuration** - Streamlined config entries and form cleanup

## 📋 What's New in v2025.7.1 - Major Overhaul

**🎯 Major UX Enhancements:**
- **🏷️ Home Assistant Name Management** - Device and port names managed entirely in HA, editable on-the-fly
- **⚡ Near Real-time Consumption** - Live power monitoring every 5 seconds for responsive automation
- **🔄 In-place Migration** - Seamless upgrade from older versions with zero downtime

**🔧 Technical Improvements:**
- **🛡️ Enhanced Hardware Identification** - CPU ID, MAC address, and serial number tracking
- **📊 Improved Discovery System** - Automatic hardware ID retrieval and device fingerprinting
- **🏗️ Modular Architecture** - Separated coordinator, entity factory, and migration systems

## 📱 Supported Devices

| Brand | Device Type | Ports | Model Examples | Firmware Tested | Protocol |
|-------|-------------|-------|----------------|-----------------|----------|
| **Max Hauri** | Smart Plug | 1 port | MaxSmart Smart Plug | v1.10, v1.30, v2.11 ✅ | HTTP |
| **Max Hauri** | Power Station | 6 ports | MaxSmart Power Station | v1.10, v1.30, v2.11 ✅ | HTTP |
| **Revogi** | Power Strip | 6 ports | SOW323 | v3.36, v3.49, v5.11 ✅ | HTTP/UDP V3 |
| **CoCoSo** | Power Strip | 6 ports | SOW323 | v1.06 ✅ | HTTP |
| **Extel** | Power Strip | 6 ports | Soky Power Strip | *Compatible* | HTTP |
| **MCL** | Power Strip | 6 ports | DOM-PPS06I | *Compatible* | HTTP |


**📡 UDP V3 Protocol Support:** Firmware v5.11+ devices from Revogi and other manufacturers using Revogi's UDP V3 API are now fully supported. This includes newer power strips and smart plugs that have moved from HTTP to UDP V3 communication.

**🤝 Help us expand compatibility!** If you have Revogi-based devices from other brands or with different firmware versions, please [test them and let us know](https://github.com/superkikim/mh-maxsmart-hass/issues/new?template=device_compatibility.md) - we'd love to add them to the supported list!

## 🚀 Installation

### Option 1: HACS Official (Recommended) ✅
**Now available in the official HACS catalog!**

1. Open **HACS** in Home Assistant
2. Search for **"MaxSmart"**
4. Select the **Max Hauri Maxsmart (revogi)** integration
5. Read the details and click "Download"
6. Restart Home Assistant

### Option 2: Manual Installation
1. Download the latest release from [GitHub](https://github.com/superkikim/mh-maxsmart-hass/releases)
2. Extract to `config/custom_components/maxsmart/`
3. Restart Home Assistant

## ⚙️ Setup & Configuration

### 1. Add Integration
1. Go to **Settings** → **Devices & Services**
2. Click **Add Integration**
3. Search for **"Max Hauri Maxsmart"**
4. Follow the setup wizard

### 2. Device Discovery
The integration will **automatically find** your MaxSmart/Revogi/CoCoSo devices on the network. Once found, each device will appear as a separate object with a ADD button.

Click ADD on each device.

### 3. Customize Names
During setup (and anytime after via ⚙️ gear icon), you can customize:
- **Device name** (e.g., "Living Room Power Strip")
- **Port names** (e.g., "TV", "Lamp", "Router")

**🎯 Pro Tip**: Names are managed entirely in Home Assistant - completely independent from device and cloud settings! If names are available on the device, they will be pre-filled.

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
- **Real-time Updates** - Live consumption every 5 seconds (vs 30 seconds in older versions!)
- **Individual Tracking** - Monitor each port separately
- **Total Power** - Overall consumption (6-port devices)
- **Smart Units** - Automatic millwatt=>watt conversion
- **Historical Data** - Track consumption over time within Home Assistant

### 🛠️ Management
- **🏷️ Complete Name Control** - Manage all names in Home Assistant, independent from devices
- **Easy Renaming** - Change device and port names anytime via gear icon
- **Auto-Discovery** - Finds devices automatically on your network
- **🛡️ Bulletproof Reliability** - Advanced error handling with clear messages
- **🔄 Auto-Recovery** - Automatic reconnection and retry logic

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
- Check that Home Assistant and device are on the same level 2 network (same subnet, and same VLAN)

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
2. **GitHub Issues** - Report problems at [our issue tracker](https://github.com/Superkikim/mh-maxsmart-hass/issues)
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
- **Protocol Support** - Devices use HTTP or UDP V3 protocols (unencrypted communication)
- **Discovery Network** - Device discovery requires same network segment (UDP broadcast limitation)
- **Control Network** - Device control works across network segments (HTTP/UDP routing supported)
- **Port Limits** - 1 or 6 ports depending on device model

### Firmware Compatibility
- **v1.06, v1.10, v1.30** - HTTP protocol, full feature support ✅
- **v2.11, v3.36, v3.49** - HTTP protocol, full feature support ✅
- **v5.11+** - UDP V3 protocol, full feature support ✅
- **Other versions** - May work but not officially tested

### End of Life Notice
MaxSmart and many other revogy based products are **discontinued**. This integration provides local control as cloud services may be discontinued.

## 🤝 Contributing

We welcome contributions! Here's how you can help:

- 🐛 **Report Bugs** - Use our [issue tracker](https://github.com/superkikim/mh-maxsmart-hass/issues)
- 💡 **Suggest Features** - Share your ideas
- 🔧 **Submit Fixes** - Pull requests welcome
- 📚 **Improve Docs** - Help make documentation better
- 🧪 **Test Devices** - Help us validate more Revogi-based devices

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 Credits

- **Original Protocol** - Thanks to [@altery](https://github.com/altery/mh-maxsmart-powerstation) for reverse engineering
- **Python Module** - Built on the [maxsmart](https://pypi.org/project/maxsmart/) library
- **Community** - Thanks to all users providing feedback and testing

---

**⚠️ Disclaimer**: This is a third-party integration, not officially supported by Home Assistant or Max Hauri. Use at your own risk.