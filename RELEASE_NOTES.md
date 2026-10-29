# 🚀 MaxSmart Integration v2026.10.2

[![Version](https://img.shields.io/badge/Version-2026.10.2-blue.svg)](https://github.com/superkikim/mh-maxsmart-hass/releases/tag/2026.10.2)
[![Home Assistant](https://img.shields.io/badge/Home%20Assistant-2026.10%2B-green.svg)](https://www.home-assistant.io/)

**Logging Improvement Release** - much quieter logs when a device is offline.

## 🔧 Improvements
- **🔇 Less log noise for offline devices** - When a device was unreachable (powered off, unplugged, or at Home Assistant startup while the network is not ready), every retry produced several warnings in the log. The automatic IP recovery and retries were already working correctly; only the logging was too verbose. Now:
  - A single warning is logged when a device stops responding, and a reminder roughly once an hour while it stays offline.
  - "Discovery failed" for a specific IP and "Starting retry loop" are now debug messages.
  - No change to retry, ARP or IP recovery behavior.

## ℹ️ Note
- A line `No MaxSmart devices found during discovery` may still appear as an error from the `root` logger. It is emitted by the `maxsmart` library itself, not by this integration.

# 🚀 MaxSmart Integration v2026.10.1

[![Version](https://img.shields.io/badge/Version-2026.10.1-blue.svg)](https://github.com/superkikim/mh-maxsmart-hass/releases/tag/2026.10.1)
[![Home Assistant](https://img.shields.io/badge/Home%20Assistant-2026.10%2B-green.svg)](https://www.home-assistant.io/)

**Compatibility Fix Release** for Home Assistant 2026.10.

## 🐛 Bug Fixes
- **🔌 Devices not added on Home Assistant 2026.10** - Home Assistant now rejects the deprecated `via_device` parameter in the device registry, even when set to `None`. The switch entities were not created (only the power sensor appeared). The unused `via_device` entry has been removed from the device info. No behavior change for existing setups and no impact on older Home Assistant versions ([#16](https://github.com/Superkikim/mh-maxsmart-hass/pull/16)).

## 🙏 Thanks
- Thanks to [@phylor](https://github.com/phylor) (Serge Hänni) for reporting, diagnosing and fixing this issue.

# 🚀 MaxSmart Integration v2025.8.2

[![Version](https://img.shields.io/badge/Version-2025.8.2-blue.svg)](https://github.com/superkikim/mh-maxsmart-hass/releases/tag/2025.8.2)
[![Home Assistant](https://img.shields.io/badge/Home%20Assistant-2023.6%2B-green.svg)](https://www.home-assistant.io/)
[![Python](https://img.shields.io/badge/Python-3.7%2B-blue.svg)](https://www.python.org/)

**Protocol Enhancement Release** with full UDP V3 support for newer MaxSmart devices. This version adds comprehensive support for both HTTP and UDP V3 protocols, ensuring compatibility with all MaxSmart device generations.

## ✨ What's New in v2025.8.2

### 🎯 Major Protocol Enhancements
- **📡 UDP V3 Protocol Support** - Full support for newer MaxSmart devices (firmware v5.11+) using UDP V3 protocol
- **🔄 Automatic Protocol Detection** - Seamless detection and handling of both HTTP and UDP V3 devices during discovery
- **🆙 MaxSmart Library 2.1.0** - Updated to latest maxsmart library with enhanced protocol support and bug fixes
- **🔧 Smart Device Creation** - Intelligent device initialization based on detected protocol and device capabilities

### 🔧 Technical Improvements
- **🛡️ Enhanced Discovery System** - Improved device discovery with automatic protocol identification
- **📱 Better Device Support** - Extended support for Revogi devices with firmware v5.11+ using UDP V3
- **⚡ Seamless Library Migration** - Automatic upgrade from maxsmart 2.0.5 to 2.1.0 with backward compatibility
- **🔧 Protocol Routing** - Intelligent routing between HTTP and UDP V3 protocols based on device capabilities
- **🆔 Serial Number Support** - Enhanced device identification for UDP V3 devices using serial numbers

### 🐛 Bug Fixes
- **🔌 UDP V3 Connection Issues** - Fixed connection failures for newer devices that only support UDP V3
- **🔍 Protocol Detection** - Resolved auto-detection failures that caused HTTP fallback on UDP V3 devices
- **📱 Firmware Version Display** - Fixed "Unknown" firmware version display for UDP V3 devices
- **⚙️ Device Initialization** - Improved device setup process for mixed protocol environments
- **🔄 IP Recovery** - Enhanced IP change detection for UDP V3 devices

### 📱 Device Compatibility Updates
- **✅ Revogi v5.11** - Full support for Revogi devices with firmware v5.11 using UDP V3 protocol
- **🔌 UDP V3 Devices** - Support for all devices using Revogi's UDP V3 API (firmware v5.11+)
- **🏭 Multi-Brand Support** - Compatible with Revogi-based devices from various manufacturers
- **🔄 Mixed Environments** - Seamless operation in networks with both HTTP and UDP V3 devices
- **🆔 Enhanced Identification** - Better device fingerprinting for UDP V3 devices

## 🆙 Upgrading from v2025.8.1

### Automatic Upgrade Process
Your existing setup will be **automatically enhanced**:

1. **Install Update** - Use HACS or manual installation
2. **Restart Home Assistant** - Triggers automatic library upgrade
3. **Protocol Detection** - Existing devices maintain HTTP, new discoveries detect UDP V3
4. **Verify Operation** - All devices should continue working with enhanced protocol support

### What Happens During Upgrade
- ✅ **Preserves all settings** - Device names, port names, configurations remain unchanged
- ✅ **Maintains automations** - All existing automations continue working without modification
- ✅ **Enhances protocol support** - Adds UDP V3 capability without affecting HTTP devices
- ✅ **Improves reliability** - Better error handling for both protocols
- ✅ **Updates library** - Seamless upgrade to maxsmart 2.1.0

### New Device Discovery
- **HTTP Devices** - Continue working as before with enhanced reliability
- **UDP V3 Devices** - Now properly detected and configured automatically
- **Mixed Networks** - Seamless operation with both protocol types

# 🚀 MaxSmart Integration v2025.8.1

[![Version](https://img.shields.io/badge/Version-2025.8.1-blue.svg)](https://github.com/superkikim/mh-maxsmart-hass/releases/tag/2025.8.1)
[![Home Assistant](https://img.shields.io/badge/Home%20Assistant-2023.6%2B-green.svg)](https://www.home-assistant.io/)
[![Python](https://img.shields.io/badge/Python-3.7%2B-blue.svg)](https://www.python.org/)

**User Experience focused release** with manual IP configuration, automatic IP change detection, and enhanced multilingual support. This version prioritizes user-friendly features while maintaining rock-solid reliability.

## ✨ What's New in v2025.8.1

### 🎯 Major User Experience Improvements
- **🌐 Manual IP Configuration** - Add IP field in device settings with real-time connection validation
- **🔄 Automatic IP Change Detection** - Seamless reconfiguration when device IP changes (i.e. DHCP lease renewal)
- **📝 Clearer Log Messages** - Simplified, actionable messages with clean 3-message cycle format
- **🌍 Enhanced Language Support** - Added Spanish and Italian translations (5 languages total: EN, FR, DE, ES, IT)

### 🔧 Technical Improvements
- **📱 Improved Device Information** - Cleaner device details display with essential info (IP, Serial Number, MAC address)
- **🛡️ Enhanced Error Handling** - Better error management with network cascade detection to reduce log noise
- **⚡ Silent Migration** - Seamless upgrade from existing devices with zero user intervention required
- **🔧 Simplified Configuration** - Streamlined config entries and cleaned up configuration forms

### 🐛 Bug Fixes
- Fixed device name placeholder in IP change confirmation dialogs (all languages)
- Removed unnecessary "ID Method" field from device configuration forms
- Improved migration compatibility between versions
- Enhanced MAC address handling for better device identification

---

# 🚀 MaxSmart Integration v2025.7.1

[![Version](https://img.shields.io/badge/Version-2025.7.1-blue.svg)](https://github.com/superkikim/mh-maxsmart-hass/releases/tag/2025.7.1)
[![Home Assistant](https://img.shields.io/badge/Home%20Assistant-2023.6%2B-green.svg)](https://www.home-assistant.io/)
[![Python](https://img.shields.io/badge/Python-3.7%2B-blue.svg)](https://www.python.org/)

**Major overhaul release** with complete architecture refactoring, Home Assistant native name management, and enhanced hardware identification. This version completely rebuilds the integration while preserving all your existing configurations.

## ✨ What's New in v2025.7.1

### 🎯 Major User Experience Improvements
- **🏷️ Home Assistant Name Management** - Device and port names managed entirely in HA, editable on-the-fly
- **⚡ Near Real-time Consumption** - Live power monitoring every 5 seconds for responsive automation
- **🔄 In-place Migration** - Seamless upgrade from older versions with zero downtime

### 🔧 Technical Improvements
- **🛡️ Enhanced Hardware Identification** - CPU ID, MAC address, and serial number tracking for rock-solid device identification
- **📊 Improved Discovery System** - Automatic hardware ID retrieval and device fingerprinting
- **🏗️ Modular Architecture** - Separated coordinator, entity factory, and migration systems for better maintainability
- **⚡ Adaptive Polling System** - Smart polling that mimics official app behavior with burst mode after commands

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
| Revogi Devices (UDP V3) | **v5.11+** | [![Full](https://img.shields.io/badge/Support-Full-brightgreen.svg)]() | [![Tested](https://img.shields.io/badge/Tests-Validated-brightgreen.svg)]() |
| Other Compatible Models | Various | [![Unknown](https://img.shields.io/badge/Support-Unknown-orange.svg)]() | [![Need Testers](https://img.shields.io/badge/Tests-Need%20Volunteers-red.svg)]() |

**🤝 Expand Our Device Support!** 
If you have MaxSmart devices with different firmware versions, please [contact us](https://github.com/superkikim/mh-maxsmart-hass/issues/new?template=device_compatibility.md) to help test and ensure full compatibility. We're actively seeking testers for expanded device support!

## 🆕 New Dependencies

### Updated Dependencies
- **maxsmart** >= 2.1.0 (Python library with UDP V3 protocol support)
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