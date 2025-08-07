# maxsmart/const.py

# Import all translation messages
from .messages import *

# -------------------------
# Discovery Constants
# -------------------------
DISCOVERY_MESSAGE = "00sw=all,{datetime};"  # UDP broadcast message template
DEFAULT_TARGET_IP = "255.255.255.255"  # Default IP for broadcasting
UDP_PORT = 8888  # Port for UDP communication

# Set to desired timeout to adjust at run time with export UDP_TIMEOUT=<seconds>
UDP_TIMEOUT = 2  # timeout in seconds for waiting on UDP responses. Default to 2

# -------------------------
# Protocol Constants
# -------------------------
SUPPORTED_PROTOCOLS = ["http", "udp_v3"]
DEFAULT_PROTOCOL = None  # Auto-detect

# -------------------------
# Currency Constants
# -------------------------
CURRENCY_SYMBOLS = {
    0: "€",  # Euro
    1: "$",  # Dollar
    2: "¥",  # Yen
    3: "CHF"  # Swiss Francs
}

# -------------------------
# Statistics Constants
# -------------------------
STATISTICS_TIME_FRAME = {
    0: "Hourly",
    1: "Daily",
    2: "Monthly"
}

# -------------------------
# Response Codes
# -------------------------
RESPONSE_CODE_SUCCESS = 200  # Successful request
RESPONSE_CODE_ERROR = 400     # Client error (bad request)
RESPONSE_CODE_NOT_FOUND = 404  # Resource not found
RESPONSE_CODE_SERVER_ERROR = 500  # Internal server error

# -------------------------
# Command Constants
# -------------------------
CMD_RESPONSE_TIMEOUT = 1
CMD_RETRIES = 3

# Firmware versions and feature support
IN_DEVICE_NAME_VERSION = "1.30"  # Only this version supports in-device port renaming

# -------------------------
# Device Command Identifiers (HTTP Protocol)
# -------------------------
CMD_SET_PORT_STATE = 200  # Command to set the state (on/off) of a specific port
CMD_GET_DEVICE_DATA = 511  # Command to get various data from the device (wattage, amperage, switch states)
CMD_GET_STATISTICS = 510  # Command to get statistics
CMD_SET_PORT_NAME = 201  # Command to set or change the name of a specific port
CMD_GET_DEVICE_TIME = 502  # Command to query device date and time
CMD_GET_DEVICE_IDS = 124  # Command to get hardware identifiers (MAC, DAK, CPUid, cloud server)

# -------------------------
# UDP V3 Command Identifiers  
# -------------------------
UDP_V3_CMD_SET_PORT_STATE = 20  # UDP V3 command to set port state (maps to HTTP 200)
UDP_V3_CMD_GET_DEVICE_DATA = 90  # UDP V3 command to get device data (maps to HTTP 511)

# Note: UDP V3 protocol only supports basic control and data commands
# Advanced features like statistics, time, port naming not available in UDP V3

# -------------------------
# Command Protocol Mapping
# -------------------------
HTTP_TO_UDP_V3_COMMANDS = {
    CMD_SET_PORT_STATE: UDP_V3_CMD_SET_PORT_STATE,  # 200 -> 20
    CMD_GET_DEVICE_DATA: UDP_V3_CMD_GET_DEVICE_DATA,  # 511 -> 90
    # Other HTTP commands (510, 201, 502, 124) not supported in UDP V3
}

# Commands supported by each protocol
HTTP_SUPPORTED_COMMANDS = {
    CMD_SET_PORT_STATE, CMD_GET_DEVICE_DATA, CMD_GET_STATISTICS,
    CMD_SET_PORT_NAME, CMD_GET_DEVICE_TIME, CMD_GET_DEVICE_IDS
}

UDP_V3_SUPPORTED_COMMANDS = {
    CMD_SET_PORT_STATE, CMD_GET_DEVICE_DATA  # Only basic commands
}

# -------------------------
# Error Messages for Unsupported Commands
# -------------------------
UNSUPPORTED_COMMAND_MESSAGES = {
    "en": {
        "ERROR_UNSUPPORTED_COMMAND": "Command not supported on {protocol} protocol: {detail}",
        "ERROR_UDP_V3_LIMITATION": "UDP V3 devices only support basic control (on/off) and data retrieval. Advanced features like {feature} require HTTP protocol devices.",
    },
    "fr": {
        "ERROR_UNSUPPORTED_COMMAND": "Commande non prise en charge sur le protocole {protocol}: {detail}",
        "ERROR_UDP_V3_LIMITATION": "Les appareils UDP V3 ne prennent en charge que le contrôle de base (on/off) et la récupération de données. Les fonctions avancées comme {feature} nécessitent des appareils avec protocole HTTP.",
    },
    "de": {
        "ERROR_UNSUPPORTED_COMMAND": "Befehl nicht unterstützt im {protocol} Protokoll: {detail}",
        "ERROR_UDP_V3_LIMITATION": "UDP V3-Geräte unterstützen nur grundlegende Steuerung (ein/aus) und Datenabruf. Erweiterte Funktionen wie {feature} erfordern HTTP-Protokoll-Geräte.",
    }
}

# -------------------------
# Default Values
# -------------------------
DEFAULT_PORT_NAMES = [f"Port {i}" for i in range(1, 7)]  # Default port names: Port 1 to Port 6
DEFAULT_STRIP_NAME = "Strip"  # Default name for the power strip

# -------------------------
# Additional Configurations
# -------------------------
MAX_PORT_NUMBER = 6  # Maximum valid port number
MAX_PORT_NAME_LENGTH = 21  # Maximum length for port names

# -------------------------
# State Values for Ports
# -------------------------
STATE_ON = 1  # State value for "on"
STATE_OFF = 0  # State value for "off"

# -------------------------
# Type of Statistics
# -------------------------
HOURLY_STATS = 0
DAILY_STATS = 1
MONTHLY_STATS = 2 

# -------------------------
# Additional Configuration Constants 
# -------------------------
MAX_DEVICE_COUNT = 10  # Maximum number of devices allowed in discovery (optional configuration)
RETRY_INTERVAL = 2  # Interval in seconds for retrying commands (optional configuration)

# -------------------------
# Protocol Feature Matrix
# -------------------------
PROTOCOL_FEATURES = {
    "http": {
        "port_control": True,       # turn_on/turn_off
        "data_retrieval": True,     # get_data/get_power_data
        "statistics": True,         # get_statistics  
        "port_naming": True,        # change_port_name/retrieve_port_names
        "device_time": True,        # get_device_time
        "hardware_ids": True,       # get_device_identifiers
        "polling": True,            # adaptive_polling
    },
    "udp_v3": {
        "port_control": True,       # turn_on/turn_off (CMD 20)
        "data_retrieval": True,     # get_data (CMD 90) 
        "statistics": False,        # Not available in UDP V3
        "port_naming": False,       # Not available in UDP V3
        "device_time": False,       # Not available in UDP V3
        "hardware_ids": False,      # Not available in UDP V3
        "polling": True,            # Can poll CMD 90
    }
}

# -------------------------
# End of constants file
# -------------------------

__all__ = [name for name in globals() if not name.startswith('_')]