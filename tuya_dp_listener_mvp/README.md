# Tuya DP Listener – MVP 0.1.0

A Home Assistant local add-on that queries configured Tuya **Wi-Fi** devices over the LAN with TinyTuya, maps returned datapoints to MQTT entities, and publishes MQTT Discovery configuration.

## Important limitation of this MVP

Version 0.1.0 uses **active polling** (`status()`), not passive packet sniffing and not a guaranteed push listener. It can only see values returned by the device when queried. Battery-powered/sleeping sensors may not answer, and short-lived events can be missed between polls. This MVP validates local reachability, Local Key/protocol compatibility, DP decoding and MQTT entity creation first. A later version can add persistent/push handling where the device/protocol supports it.

## Install as a local add-on

1. Copy this folder to `/addons/tuya_dp_listener` on the Home Assistant host (or clone/copy it into your local add-on repository).
2. In Home Assistant: **Settings → Add-ons → Add-on Store → ⋮ → Check for updates**.
3. Find **Tuya DP Listener**, install it, then configure it.
4. Ensure the Mosquitto broker add-on is running and the MQTT integration is configured.
5. Add one known Tuya Wi-Fi device and its datapoint mapping. Start with a device already proven reachable with its Local Key.

## Example configuration

```yaml
mqtt_host: core-mosquitto
mqtt_port: 1883
mqtt_username: YOUR_MQTT_USERNAME
mqtt_password: YOUR_MQTT_PASSWORD
discovery_prefix: homeassistant
poll_interval: 5
devices:
  - name: Test Tuya Device
    device_id: YOUR_DEVICE_ID
    ip: 192.168.1.123
    local_key: YOUR_LOCAL_KEY
    protocol_version: "3.3"
    datapoints:
      - dp_id: "1"
        name: motion
        component: binary_sensor
        device_class: motion
        value_on: pir
        value_off: none
      - dp_id: "4"
        name: battery
        component: sensor
        device_class: battery
        unit_of_measurement: "%"
```

Use the actual DP IDs and values reported by your device. The example mapping is illustrative, not universal.

## What to check

- Add-on logs: MQTT connection, TinyTuya status responses, DP values.
- MQTT topics:
  - `tuya_dp_listener/<device_id>/availability`
  - `tuya_dp_listener/<device_id>/dp/<dp_id>`
  - `homeassistant/<component>/<unique_id>/config`

## Security

- Do not commit real Local Keys or MQTT credentials to Git.
- Keep the add-on options/private config out of public repositories.
- If a Local Key or HA token was exposed, rotate it.
