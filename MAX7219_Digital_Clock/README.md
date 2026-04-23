# MAX7219 Home Assistant Add-on

Raspberry Pi SPI (`/dev/spidev0.0`) uzerinden MAX7219 LED matrix kontrolu icin
Home Assistant add-on. MQTT komutlari, effect engine, scheduler ve Ingress web UI
icerir.

## Ozellikler

- Namespace zorunlu MQTT mimarisi: `mirarus/max7219/*`
- Modlar: `text`, `clock`
- Efektler: `static`, `scroll`, `marquee`, `blink`, `invert`, `wave`
- Scheduler: zaman bazli mesajlar (JSON payload ile)
- Ingress Web UI: canli komut + schedule yonetimi
- Telemetry: state + health topic yayinlari

## MQTT Topic Yapisi

Komut topicleri:

- `mirarus/max7219/cmnd/text`
- `mirarus/max7219/cmnd/mode`
- `mirarus/max7219/cmnd/effect`
- `mirarus/max7219/cmnd/brightness`
- `mirarus/max7219/cmnd/schedule`

State topicleri:

- `mirarus/max7219/stat/state`
- `mirarus/max7219/tele/health`
- `mirarus/max7219/tele/update` (startup/shutdown + addon version)

## MQTT Komut Ornekleri

Text guncelle:

```yaml
service: mqtt.publish
data:
  topic: mirarus/max7219/cmnd/text
  payload: "MERHABA"
```

Clock moda gec:

```yaml
service: mqtt.publish
data:
  topic: mirarus/max7219/cmnd/mode
  payload: "clock"
```

Efekt degistir:

```yaml
service: mqtt.publish
data:
  topic: mirarus/max7219/cmnd/effect
  payload: "wave"
```

Parlaklik:

```yaml
service: mqtt.publish
data:
  topic: mirarus/max7219/cmnd/brightness
  payload: "12"
```

Schedule upsert:

```yaml
service: mqtt.publish
data:
  topic: mirarus/max7219/cmnd/schedule
  payload: >
    {"time":"08:00","text":"GUNAYDIN","mode":"text","effect":"scroll","duration":120,"days":[1,2,3,4,5],"brightness":8}
```

Tum schedule'lari temizle:

```yaml
service: mqtt.publish
data:
  topic: mirarus/max7219/cmnd/schedule
  payload: '{"action":"clear"}'
```

## Home Assistant Dashboard Entegrasyonu

Hazir dashboard ve automation ornekleri:

- `dashboard/lovelace_max7219.yaml`
- `dashboard/automations_max7219.yaml`

Bu dosyalari kendi Home Assistant konfigunuze gore uyarlayabilirsiniz.

## HACS Destegi

Bu repoya HACS uyumlu custom Lovelace karti eklendi.

- Metadata: `hacs.json`
- Kart dosyasi: `hacs/max7219-control-card.js`
- Kart tipi: `custom:max7219-control-card`

Ornek kart konfigu:

```yaml
type: custom:max7219-control-card
title: MAX7219 Control
namespace: mirarus/max7219
```

Not:
- Bu kart MQTT publish icin Home Assistant `mqtt` servisini kullanir.
- Live state goruntusu icin `mirarus/max7219/stat/state` topic'ini dinleyen bir MQTT sensor gerekli olabilir.

## Add-on Opsiyonlari

`config.json` schema uzerinden yonetilir. Onemli alanlar:

- `mqtt.host`, `mqtt.port`, `mqtt.username`, `mqtt.password`
- `mqtt.auto` (true ise Supervisor MQTT servisinden host/port/username/password otomatik almaya calisir)
- `mqtt.discovery` (Home Assistant MQTT Discovery publish eder)
- `mqtt.discovery_prefix` (varsayilan: `homeassistant`)
- `mqtt.reconnect_min_delay`, `mqtt.reconnect_max_delay` (otomatik reconnect hizi)
- `mqtt.initial_retry_delay`, `mqtt.retry_max_delay` (ilk baglanti deneme backoff hizi)
- `mqtt.namespace` (varsayilan: `mirarus/max7219`)
- `telemetry.enabled`, `telemetry.interval`
- `default_text`, `default_mode`, `default_effect`
- `brightness`, `speed`
- `cascaded`, `spi_port`, `spi_device`, `block_orientation`, `rotate`
- `github.version_check` (GitHub latest release/tag kontrolu)
- `github.repo` (ornek: `mirarus/ha-addons`)
- `github.check_timeout` (saniye)

## MQTT Discovery

`mqtt.discovery: true` oldugunda add-on baglandiginda su entity config'lerini publish eder:

- Text: MAX7219 Text
- Select: MAX7219 Mode
- Select: MAX7219 Effect
- Number: MAX7219 Brightness
- Sensor: MAX7219 MQTT Status

Discovery prefix varsayilan olarak `homeassistant` kullanir.

## MQTT Auto-Credentials (Supervisor)

`mqtt.auto: true` iken add-on sirayla su kaynaklari dener:

1. Home Assistant Supervisor MQTT service (`/services/mqtt`)
2. Eksik host varsa fallback `core-mosquitto`
3. Port fallback `1883`

Web UI state ekraninda `mqtt.credential_source` alani ile hangi kaynagin kullanildigi gorulebilir.

## GitHub Version Check

Add-on startup sirasinda `github.version_check: true` ise `github.repo` icin latest release/tag kontrol edilir.
Sonuc `tele/update` payload icine su alanlarla eklenir:

- `version` (lokal add-on surumu)
- `latest_version` (GitHub'dan bulunan surum)
- `update_available` (`latest_version > version`)
- `update_source` (`github` veya `local`)

## Operasyon Notlari

- Ingress-only UI kullanimi hedeflenmistir.
- MQTT TLS bu release'de zorunlu degildir; local broker + auth onerilir.
- Add-on kapanisinda graceful shutdown uygulanir (SIGTERM).

## MAX7219 Pin Tanimlama (Raspberry Pi SPI)

SPI ile MAX7219 kullaniminda temel pinler:

- MOSI: `GPIO10` (Pin 19)
- SCLK: `GPIO11` (Pin 23)
- GND: herhangi bir GND pin
- VCC: 5V (modulunuze gore 3.3V/5V)
- CS/LOAD:
  - `spi_device: 0` -> `GPIO8 (CE0, Pin 24)`
  - `spi_device: 1` -> `GPIO7 (CE1, Pin 26)`

Add-on icinden `spi_device` degistirerek CE0/CE1 secimi yapabilirsiniz.
Web UI uzerindeki **Pin Teshisi Calistir** butonu ile yazilim tarafi SPI/pin kontrollerini gorebilirsiniz.