"""Platform for sensor integration."""
from homeassistant.components.sensor import SensorEntity

def async_setup_entry(hass, config_entry, async_add_entities):
    """Set up the sensor platform."""
    # Create a list to hold the entities
    entities = []

    # Get the data from the config entry
    sensors = config_entry.data.get("sensor")

    # For each sensor, create a SensorEntity and add it to the list
    for sensor in sensors:
        entities.append(MaxSmartSensor(sensor))

    # Add the entities to Home Assistant
    async_add_entities(entities, update_before_add=True)


class MaxSmartSensor(SensorEntity):
    """Representation of a MaxSmart sensor."""

    def __init__(self, sensor):
        """Initialize the sensor."""
        self._name = sensor["name"]
        self._unique_id = sensor["unique_id"]
        self._state = "Unknown"

    @property
    def name(self):
        """Return the name of the sensor."""
        return self._name

    @property
    def unique_id(self):
        """Return the unique ID of the sensor."""
        return self._unique_id

    @property
    def state(self):
        """Return the state of the sensor."""
        return self._state
