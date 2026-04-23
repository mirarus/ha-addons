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
- `default_text`, `default_mode`, `default_effect`
- `brightness`, `speed`
- `cascaded`, `block_orientation`, `rotate`

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

## Operasyon Notlari

- Ingress-only UI kullanimi hedeflenmistir.
- MQTT TLS bu release'de zorunlu degildir; local broker + auth onerilir.
- Add-on kapanisinda graceful shutdown uygulanir (SIGTERM).