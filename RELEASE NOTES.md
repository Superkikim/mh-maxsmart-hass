# 🚀 MaxSmart Integration v2025.7.1

[![Version](https://img.shields.io/badge/Version-2025.7.1-blue.svg)](https://github.com/superkikim/mh-maxsmart-hass/releases/tag/2025.7.1)
[![Home Assistant](https://img.shields.io/badge/Home%20Assistant-2023.6%2B-green.svg)](https://www.home-assistant.io/)
[![Python](https://img.shields.io/badge/Python-3.7%2B-blue.svg)](https://www.python.org/)

**Major release** with automatic migration, enhanced reliability, and smart device detection. This version completely overhauls the integration architecture while preserving all your existing configurations.

## ✨ What's New

### 🏷️ Revolutionary Name Management
- **Home Assistant Native** - All device and port names managed entirely within HA
- **Device Independence** - No more reliance on device-stored names
- **Instant Updates** - Name changes apply immediately without device communication
- **Perfect Migration** - Existing custom names preserved during upgrade
- **Unlimited Characters** - No device firmware name length restrictions

### ⚡ Real-Time Performance Boost
- **5-Second Updates** - Live power monitoring every 5 seconds (vs 30 seconds before!)
- **Instant Response** - Immediate feedback on device state changes
- **Adaptive Polling** - Smart polling system that mimics official app behavior
- **Burst Mode** - 2-second updates after commands for instant confirmation
- **Live Dashboard** - Real-time consumption tracking for automation triggers

### 🔄 Bulletproof Migration System
- **Zero-Downtime Upgrades** - Seamless migration from previous versions
- **Hardware Fingerprinting** - Uses CPU ID and MAC address for rock-solid device tracking
- **Intelligent Entity Cleanup** - Automatically removes incorrect entities
- **Configuration Preservation** - All your custom names and settings preserved
- **Clear Feedback** - Migration notifications confirm successful upgrade

### ⚡ Enhanced Power Monitoring
- **Real-Time Data** - Live power consumption updates every 5 seconds
- **Auto-Format Detection** - Supports different firmware watt formats automatically
- **Improved Accuracy** - Better data conversion and validation
- **Smart Icons** - Dynamic icons based on power consumption levels

### 🛡️ Enterprise-Grade Reliability Revolution
**The previous error handling was catastrophic - we've completely rebuilt it from the ground up!**

- **Intelligent Error Detection** - Comprehensive error classification and handling
- **Smart Retry Logic** - Exponential backoff with network-aware recovery
- **Clear Error Messages** - User-friendly messages instead of cryptic technical errors
- **Automatic Recovery** - Self-healing connections and automatic reconnection
- **Bulletproof Validation** - All inputs validated with proper security controls
- **Zero-Crash Design** - Isolated error boundaries prevent integration failures
- **Diagnostic Tools** - Built-in health monitoring and connectivity diagnostics

### 🎨 Better User Experience
- **Simplified Setup** - Streamlined configuration flow
- **Clear Entity Names** - Consistent, readable entity naming
- **Easy Customization** - Improved device and port renaming interface
- **Enhanced Discovery** - More reliable device detection on network

## 🔧 What's Fixed

### 🚨 Critical Error Handling Overhaul
**Previous versions had catastrophic error handling - we've completely rebuilt the entire system!**

- **Log Pollution Eliminated** - Smart error filtering stops unnecessary warnings [![Fixed](https://img.shields.io/badge/Status-Fixed-brightgreen.svg)]()
- **Clear Error Messages** - User-friendly messages replace cryptic technical errors [![Fixed](https://img.shields.io/badge/Status-Fixed-brightgreen.svg)]()
- **Network Resilience** - Robust retry logic with exponential backoff [![Fixed](https://img.shields.io/badge/Status-Fixed-brightgreen.svg)]()
- **Connection Recovery** - Automatic reconnection and session management [![Fixed](https://img.shields.io/badge/Status-Fixed-brightgreen.svg)]()
- **Input Validation** - Comprehensive security controls prevent crashes [![Fixed](https://img.shields.io/badge/Status-Fixed-brightgreen.svg)]()

### 🐛 Legacy Bug Fixes
- **Entity Duplication** - Fixed duplicate entities on upgrades [![Fixed](https://img.shields.io/badge/Status-Fixed-brightgreen.svg)]()
- **Master Switch Issues** - Removed incorrect master entities on 1-port devices [![Fixed](https://img.shields.io/badge/Status-Fixed-brightgreen.svg)]()
- **Discovery Failures** - Multiple fallback methods for reliable device detection [![Fixed](https://img.shields.io/badge/Status-Fixed-brightgreen.svg)]()
- **Memory Leaks** - Proper resource cleanup and session management [![Fixed](https://img.shields.io/badge/Status-Fixed-brightgreen.svg)]()
- **State Inconsistencies** - Real-time state synchronization and validation [![Fixed](https://img.shields.io/badge/Status-Fixed-brightgreen.svg)]()

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
| Device | Firmware | Support Level | Test Status |
|--------|----------|---------------|-------------|
| MaxSmart Power Station (6-port) | **v1.30** | [![Full](https://img.shields.io/badge/Support-Full-brightgreen.svg)]() | [![Tested](https://img.shields.io/badge/Tests-Validated-brightgreen.svg)]() |
| MaxSmart Smart Plug (1-port) | **v1.30** | [![Full](https://img.shields.io/badge/Support-Full-brightgreen.svg)]() | [![Tested](https://img.shields.io/badge/Tests-Validated-brightgreen.svg)]() |
| MaxSmart Devices | **v2.11+** | [![Basic](https://img.shields.io/badge/Support-Basic-yellow.svg)]() | [![Tested](https://img.shields.io/badge/Tests-Validated-brightgreen.svg)]() |
| Other Compatible Models | Various | [![Unknown](https://img.shields.io/badge/Support-Unknown-orange.svg)]() | [![Need Testers](https://img.shields.io/badge/Tests-Need%20Volunteers-red.svg)]() |

**🤝 Expand Our Device Support!** 
If you have MaxSmart devices with different firmware versions, please [contact us](https://github.com/superkikim/mh-maxsmart-hass/issues/new?template=device_compatibility.md) to help test and ensure full compatibility. We're actively seeking testers for expanded device support!

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