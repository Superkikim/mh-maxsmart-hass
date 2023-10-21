# MaxSmart (Revogi) for Home Assistant

This is a custom component for Home Assistant that integrates Max Hauri's MaxSmart Power Devices, including Smart Plug and Power Station. It communicates with the devices over your local network, providing controls for each port on the device.

For details about the supported hardware and fw version, please see the Maxsmart module documentation here: https://github.com/Superkikim/maxsmart

## Features

* Discovery of MaxSmart devices on the network.
* Control of the master switch as well as individual ports on each device.
* Pulls device status updates periodically.

## Installation

This component is not included in the default Home Assistant installation. Therefore, it needs to be installed manually:

1. Navigate to the `config` directory of your Home Assistant installation.
2. If you don't have a `custom_components` directory inside the `config` directory, create it.
3. Inside the `custom_components` directory, create another directory named `maxsmart`.
4. Download the four files from this repository (`__init__.py`, `manifest.json`, `config_flow.py`, `switch.py`) and place them inside the `maxsmart` directory.

After you have installed the component, you need to restart Home Assistant.

## Configuration

After installing the component, you need to add it to your configuration:

1. Go to **Configuration** > **Integrations**.
2. Click on the **Add Integration** button.
3. Search for `MaxSmart (Revogi)` and select it.
4. If the devices are not discovered automatically, you will be asked to input the IP address of the device.
5. Once the devices are discovered, they will be added to your Home Assistant setup and can be controlled via the UI.

## Entities

Each discovered device will create a set of entities. There is one master switch entity and a separate switch entity for each individual port. The entity IDs will be generated based on the device's serial number and port number in the format `switch.maxsmart_<devicenumber>_<portnumber>_<portname>`.

## Notes

* This integration is developed and tested with Home Assistant version 2023.6.2, but it should be compatible with other versions as well.
* The devices are discovered via local network polling, which means the devices need to be on the same network as your Home Assistant instance.
* The device state in Home Assistant is updated periodically based on polling.
* The component depends on the `maxsmart` and `requests` Python libraries, which will be automatically installed.

## Reporting Issues

If you encounter issues with this custom component, please report them at the [issue tracker](https://github.com/superkikim/maxsmart/issues) on GitHub.

## Further Development

This component is under active development. Contributions, ideas, and suggestions are welcomed! Please reach out to the [codeowners](https://github.com/superkikim) for collaboration.

Remember to refer to the latest Home Assistant developer documentation for up-to-date information when contributing to this project.

**Disclaimer: This is a third-party integration and not officially supported by Home Assistant or Max Hauri. Use it at your own risk.**
