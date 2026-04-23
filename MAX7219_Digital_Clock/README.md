# MAX7219 Home Assistant Add-on

Raspberry Pi GPIO üzerinden MAX7219 LED matrix kontrolü.

## Kurulum

1. Home Assistant → Add-on Store
2. Repositories → bu repo URL'ini ekle
3. Add-on'u kur ve başlat

## MQTT Topic

mirarus/max7219

## Örnek automation

```yaml
service: mqtt.publish
data:
  topic: "mirarus/max7219"
  payload: "{{ now().strftime('%H:%M') }}"