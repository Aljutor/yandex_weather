# Yandex Weather custom component for Home-assistant. Thanks to bastshoes and apaex
This is custom component for Home-assistant. 
Component work with Home-assistant HA 2022.3.*.

# Installation

**Method 1. HACS:**

HACS > Integrations > 3 dots > Custom Repositories > alexanderznamensky/yandex_weather + Intergration > Yandex Weather > Install

**Method 2.**

Manually copy yandex_weather folder from latest release to /config/custom_components folder.

# Configuration:

Add this to your `configuration.yaml`

```yaml
weather:
  - platform: yandex_weather
    api_key: <yandex_api_key>    
```

Note: You have to wait 30 min after install tion for first data update.
