# 🚀 MaxSmart Integration v2025.7.1

[![Version](https://img.shields.io/badge/Version-2025.7.1-blue.svg)](https://github.com/superkikim/mh-maxsmart-hass/releases/tag/2025.7.1)
[![Home Assistant](https://img.shields.io/badge/Home%20Assistant-2023.6%2B-green.svg)](https://www.home-assistant.io/)
[![Python](https://img.shields.io/badge/Python-3.7%2B-blue.svg)](https://www.python.org/)

**Major release** with automatic migration, enhanced reliability, and smart device detection. This version completely overhauls the integration architecture while preserving all your existing configurations.

## ✨ What's New

### 🔄 Automatic Migration System
- **Seamless Upgrades** - Zero-downtime migration from previous versions
- **Hardware-Based Identification** - Uses CPU ID and MAC address for robust device tracking
- **Smart Entity Cleanup** - Automatically removes incorrect entities (e.g., master switch on 1-port devices)
- **Configuration Preservation** - Keeps all your custom device and port names
- **Migration Notifications** - Clear feedback when migration completes

### 🧠 Intelligent Device Detection
- **Port Count Recognition** - Automatically detects 1-port vs 6-port devices
- **Smart Entity Creation** - Creates only relevant entities for each device type
- **Hardware Fingerprinting** - Uses multiple identification methods for reliability
- **Future-Proof Design** - Handles device IP changes and network reconfigurations

### ⚡ Enhanced Power Monitoring
- **Real-Time Data** - Live power consumption updates every 5 seconds
- **Auto-Format Detection** - Supports different firmware watt formats automatically
- **Improved Accuracy** - Better data conversion and validation
- **Smart Icons** - Dynamic icons based on power consumption levels

### 🛠️ Improved Reliability
- **Robust Error Handling** - Intelligent retry logic for network issues
- **Connection Pooling** - Efficient HTTP session management
- **Reduced Log Pollution** - Smart error filtering to minimize unnecessary warnings
- **Health Monitoring** - Built-in device connectivity diagnostics

### 🎨 Better User Experience
- **Simplified Setup** - Streamlined configuration flow
- **Clear Entity Names** - Consistent, readable entity naming
- **Easy Customization** - Improved device and port renaming interface
- **Enhanced Discovery** - More reliable device detection on network

## 🔧 What's Fixed

### 🐛 Critical Bug Fixes
- **Entity Duplication** - Fixed duplicate entities on upgrades [![Fixed](https://img.shields.io/badge/Status-Fixed-brightgreen.svg)]()
- **Master Switch Issues** - Removed incorrect master entities on 1-port devices [![Fixed](https://img.shields.io/badge/Status-Fixed-brightgreen.svg)]()
- **Connection Timeouts** - Improved network error handling and recovery [![Fixed](https://img.shields.io/badge/Status-Fixed-brightgreen.svg)]()
- **Discovery Failures** - More robust device discovery with multiple fallbacks [![Fixed](https://img.shields.io/badge/Status-Fixed-brightgreen.svg)]()

### 🔄 Migration Improvements
- **Preserved unique_id** - Prevents device duplication during upgrades
- **Smart Device Matching** - Multiple identification methods for reliable migration
- **Graceful Fallbacks** - Handles offline devices during migration
- **Clean Entity Registry** - Removes obsolete entities automatically

### 📊 Data & Performance
- **Faster Polling** - Optimized data fetching intervals
- **Memory Efficiency** - Reduced resource usage with connection pooling
- **Better Error Recovery** - Automatic reconnection on network issues
- **Consistent Data Format** - Unified power measurement handling

## 🏗️ Technical Improvements

### 🎯 Architecture Overhaul
- **Modular Design** - Clean separation of concerns with mixins
- **Entity Factory Pattern** - Centralized entity creation logic
- **Enhanced Coordinator** - Improved data coordination and error handling
- **Modern Python** - Full async/await architecture throughout

### 🔒 Security & Stability
- **Input Validation** - Comprehensive parameter validation
- **Session Management** - Proper HTTP session cleanup
- **Error Boundaries** - Isolated error handling prevents crashes
- **Resource Cleanup** - Automatic resource management

### 📝 Code Quality
- **Type Hints** - Full typing support for better development experience
- **Documentation** - Comprehensive inline documentation
- **Testing** - Enhanced error handling with built-in diagnostics
- **Maintainability** - Cleaner, more modular codebase

## 🆙 Upgrading

### From v1.x
Your existing setup will be **automatically migrated**:

1. **Install Update** - Use HACS or manual installation
2. **Restart Home Assistant** - Triggers automatic migration
3. **Check Notification** - Confirm migration success
4. **Verify Entities** - All your devices should work as before

### What Happens During Upgrade
- ✅ **Preserves all settings** - Device names, port names, configurations
- ✅ **Maintains automations** - All existing automations continue working
- ✅ **Cleans up entities** - Removes incorrect entities for 1-port devices
- ✅ **Enhances reliability** - Better error handling and connectivity
- ✅ **Shows notification** - Confirms successful migration

### Rollback (if needed)
If you encounter issues:
1. Remove the integration from Settings → Devices & Services
2. Install previous version
3. Restart Home Assistant
4. Re-add integration

## 📋 Requirements

### System Requirements
- **Home Assistant** 2023.6.2 or newer
- **Python** 3.7+ (automatically managed)
- **Network** Same network as MaxSmart devices

### Supported Devices
| Device | Firmware | Support Level |
|--------|----------|---------------|
| MaxSmart Power Station (6-port) | v1.30 | [![Full](https://img.shields.io/badge/Support-Full-brightgreen.svg)]() |
| MaxSmart Smart Plug (1-port) | v1.30 | [![Full](https://img.shields.io/badge/Support-Full-brightgreen.svg)]() |
| MaxSmart Devices | v2.11+ | [![Basic](https://img.shields.io/badge/Support-Basic-yellow.svg)]() |
| Compatible Models | Various | [![Varies](https://img.shields.io/badge/Support-Varies-orange.svg)]() |

## 🆕 New Dependencies

### Updated Dependencies
- **maxsmart** >= 2.0.3 (Python library with enhanced features)
- **aiohttp** (for efficient async HTTP communication)

All dependencies are automatically managed by Home Assistant.

## 🔮 What's Next

### Planned for v2025.8.x
- **Historical Statistics** - Long-term power consumption tracking
- **Advanced Automation** - Enhanced triggers and conditions
- **Energy Dashboard** - Integration with HA Energy features
- **Device Groups** - Logical grouping of multiple devices

### Community Requests
- **Schedule Management** - Built-in scheduling features
- **Power Limits** - Configurable consumption thresholds
- **Export Features** - Data export capabilities

## 📞 Support & Feedback

### Getting Help
- 📖 **Documentation** - Updated comprehensive guide
- 🐛 **Bug Reports** - [GitHub Issues](https://github.com/superkikim/mh-maxsmart-hass/issues)
- 💬 **Discussions** - [GitHub Discussions](https://github.com/superkikim/mh-maxsmart-hass/discussions)
- 📧 **Direct Contact** - For urgent issues

### Contributing
We welcome community contributions:
- 🧪 **Testing** - Help test new features
- 📝 **Documentation** - Improve user guides
- 🔧 **Code** - Submit bug fixes and features
- 🌍 **Translation** - Add language support

## 🙏 Acknowledgments

Special thanks to:
- **Community testers** who provided valuable feedback
- **[@altery](https://github.com/altery)** for original protocol reverse engineering
- **MaxSmart library contributors** for the enhanced Python module
- **Home Assistant team** for the excellent platform

---

## 📥 Installation Links

- **HACS**: Search for "MaxSmart" in HACS integrations
- **Manual**: [Download Latest Release](https://github.com/superkikim/mh-maxsmart-hass/releases/tag/2025.7.1)
- **Documentation**: [Full Setup Guide](https://github.com/superkikim/mh-maxsmart-hass#readme)

**Happy automating! 🏠⚡**