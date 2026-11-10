import json
import logging
import os
import re
import signal
import time
from pathlib import Path

import paho.mqtt.client as mqtt
import tinytuya

LOG = logging.getLogger("tuya_dp_listener")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

OPTIONS_PATH = Path("/data/options.json")
RUNNING = True


def slug(value: str) -> str:
    value = re.sub(r"[^a-zA-Z0-9_]+", "_", value.strip().lower())
    return value.strip("_") or "tuya_device"


def load_options():
    if not OPTIONS_PATH.exists():
        raise RuntimeError(f"Missing add-on options file: {OPTIONS_PATH}")
    with OPTIONS_PATH.open("r", encoding="utf-8") as f:
        return json.load(f)


def mqtt_connect(options):
    client = mqtt.Client(client_id="tuya_dp_listener", clean_session=True)
    username = options.get("mqtt_username", "")
    password = options.get("mqtt_password", "")
    if username:
        client.username_pw_set(username, password)
    client.connect(options.get("mqtt_host", "core-mosquitto"),
                   int(options.get("mqtt_port", 1883)), keepalive=60)
    client.loop_start()
    return client


def publish(client, topic, payload, retain=False):
    try:
        info = client.publish(topic, payload, retain=retain)
        info.wait_for_publish(timeout=5) # skrátené na 5s
    except Exception as e:
        print(f"2026-11-10 WARNING: MQTT publish failed to topic {topic}: {e}")



def publish_discovery(client, options, device):
    device_id = device["device_id"]
    device_slug = slug(device_id)
    device_name = device.get("name", device_id)
    base = f"tuya_dp_listener/{device_slug}"
    availability_topic = f"{base}/availability"
    discovery_prefix = options.get("discovery_prefix", "homeassistant")

    device_info = {
        "identifiers": [f"tuya_dp_listener_{device_slug}"],
        "name": device_name,
        "manufacturer": "Tuya-compatible",
        "model": "Wi-Fi datapoint device",
    }

    for dp in device.get("datapoints", []):
        component = dp["component"]
        dp_id = str(dp["dp_id"])
        dp_name = slug(dp["name"])
        unique_id = f"tuya_dp_listener_{device_slug}_dp_{dp_id}"
        state_topic = f"{base}/dp/{dp_id}"

        payload = {
            "name": dp["name"],
            "unique_id": unique_id,
            "state_topic": state_topic,
            "availability_topic": availability_topic,
            "payload_available": "online",
            "payload_not_available": "offline",
            "device": device_info,
            "origin": {
                "name": "Tuya DP Listener",
                "sw": "0.1.0",
            },
        }

        if component == "binary_sensor":
            payload["payload_on"] = "ON"
            payload["payload_off"] = "OFF"
            if dp.get("device_class"):
                payload["device_class"] = dp["device_class"]
        elif component == "sensor":
            if dp.get("device_class"):
                payload["device_class"] = dp["device_class"]
            if dp.get("unit_of_measurement"):
                payload["unit_of_measurement"] = dp["unit_of_measurement"]
        else:
            LOG.warning("Unsupported component '%s' for DP %s; skipping", component, dp_id)
            continue

        topic = f"{discovery_prefix}/{component}/{unique_id}/config"
        publish(client, topic, json.dumps(payload), retain=True)
        LOG.info("Published discovery for %s DP %s", device_name, dp_id)


def map_dp_value(dp, raw_value):
    if dp["component"] == "binary_sensor":
        value_on = dp.get("value_on", "1")
        value_off = dp.get("value_off", "0")
        raw_text = str(raw_value).lower()
        if raw_text == str(value_on).lower():
            return "ON"
        if raw_text == str(value_off).lower():
            return "OFF"
        LOG.warning(
            "DP %s value %r does not match value_on=%r/value_off=%r",
            dp["dp_id"], raw_value, value_on, value_off
        )
        return None
    return str(raw_value)


def make_tuya_device(device):
    dev = tinytuya.Device(
        device["device_id"],
        device["ip"],
        device["local_key"],
    )
    dev.set_version(float(device.get("protocol_version", "3.3")))
    dev.set_socketTimeout(5)
    return dev


def poll_device(client, device):
    device_slug = slug(device["device_id"])
    base = f"tuya_dp_listener/{device_slug}"
    dev = make_tuya_device(device)

    try:
        response = dev.status()
        if not isinstance(response, dict):
            raise RuntimeError(f"Unexpected TinyTuya response: {response!r}")
        if response.get("Error") or response.get("Err"):
            raise RuntimeError(f"TinyTuya error response: {response}")

        dps = response.get("dps", {})
        if not isinstance(dps, dict):
            raise RuntimeError(f"No DP dictionary in response: {response}")

        publish(client, f"{base}/availability", "online", retain=True)
        LOG.info("Device %s responded; returned DP IDs: %s",
                 device.get("name", device["device_id"]), list(dps.keys()))

        for mapping in device.get("datapoints", []):
            dp_id = str(mapping["dp_id"])
            if dp_id not in dps:
                LOG.debug("Configured DP %s not present in response", dp_id)
                continue

            value = map_dp_value(mapping, dps[dp_id])
            if value is None:
                continue

            topic = f"{base}/dp/{dp_id}"
            publish(client, topic, value, retain=True)
            LOG.info("DP %s = %r", dp_id, dps[dp_id])

    except Exception as exc:
        LOG.warning("Device %s poll failed: %s",
                    device.get("name", device["device_id"]), exc)
        publish(client, f"{base}/availability", "offline", retain=True)


def handle_signal(signum, frame):
    global RUNNING
    RUNNING = False


def main():
    options = load_options()
    devices = options.get("devices", [])
    if not devices:
        LOG.warning("No Tuya devices configured yet. Add a device in add-on options.")
        while RUNNING:
            time.sleep(5)
        return

    client = mqtt_connect(options)
    LOG.info("Connected to MQTT broker %s:%s",
             options.get("mqtt_host"), options.get("mqtt_port"))

    for device in devices:
        publish_discovery(client, options, device)

    interval = max(1, int(options.get("poll_interval", 5)))
    LOG.info("Starting Tuya DP polling; interval=%ss; devices=%s",
             interval, len(devices))

    try:
        while RUNNING:
            cycle_started = time.monotonic()
            for device in devices:
                if not RUNNING:
                    break
                poll_device(client, device)
            elapsed = time.monotonic() - cycle_started
            time.sleep(max(0, interval - elapsed))
    finally:
        for device in devices:
            base = f"tuya_dp_listener/{slug(device['device_id'])}"
            try:
                publish(client, f"{base}/availability", "offline", retain=True)
            except Exception:
                pass
        client.loop_stop()
        client.disconnect()
        LOG.info("Tuya DP Listener stopped")


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)
    main()
