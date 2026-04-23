import os
import json
from luma.led_matrix.device import max7219
from luma.core.interface.serial import spi, noop
from luma.core.render import canvas
import paho.mqtt.client as mqtt
import time

# HA options.json oku
with open("/data/options.json") as f:
    options = json.load(f)

MQTT_HOST = options.get("mqtt_host", "core-mosquitto")
MQTT_TOPIC = options.get("mqtt_topic", "mirarus/max7219")

serial = spi(port=0, device=0, gpio=noop())
device = max7219(serial, cascaded=4)

current_text = "--:--"

def on_message(client, userdata, msg):
    global current_text
    current_text = msg.payload.decode()

client = mqtt.Client()
client.connect(MQTT_HOST, 1883)
client.subscribe(MQTT_TOPIC)
client.on_message = on_message
client.loop_start()

while True:
    with canvas(device) as draw:
        draw.text((0, 0), current_text, fill="white")
    time.sleep(0.1)