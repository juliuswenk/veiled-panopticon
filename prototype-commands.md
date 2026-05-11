# Prototype Commands

Last updated: 2026-05-07 (three USB receivers)

This file is the working command reference for the installation prototype. Keep the receiver mapping current when ports change.

## Current Hardware Mapping

```text
sender:  external / not plugged into this Mac
left:    /dev/cu.usbmodem101     Arduino Nano ESP32-S3 receiver
center:  /dev/cu.usbmodem1101    Arduino Nano ESP32-S3 receiver, LED flashes CR
right:   /dev/cu.usbmodem2101    Arduino Nano ESP32-S3 receiver
baud:    921600
```

## Physical Setup

```text
  sender                   wall          receiver array
       |                                      |
       | <------- ~1 meter ---------->        |
       |                                      |
                                  left    center   right
                                  (101)   (1101)   (2101)

Sender is external / not plugged into this Mac.
Receivers are plugged into this Mac over USB serial.
```

## Project Paths

```bash
cd /Users/juliuswenk/Desktop/KD/KZP-inivisible-waves/esp-csi
```

```bash
cd examples/get-started/tools
```

## Python Tool Setup

Run this once, or after deleting the virtual environment:

```bash
cd /Users/juliuswenk/Desktop/KD/KZP-inivisible-waves/esp-csi/examples/get-started/tools
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Check Connected Boards

```bash
cd /Users/juliuswenk/Desktop/KD/KZP-inivisible-waves/esp-csi/examples/get-started/tools
source .venv/bin/activate
python -m serial.tools.list_ports
```

Useful fallback:

```bash
for port in /dev/cu.usbmodem*(N) /dev/cu.usbserial*(N); do echo "$port"; done
```

## Launch Current CSI Feature UI

This is the quick-test UI currently checked in as `csi_feature_viewer.py`.
It reads CSI rows from either USB serial ports or UDP receiver ports.

```bash
cd /Users/juliuswenk/Desktop/KD/KZP-inivisible-waves/esp-csi/examples/get-started/tools
source .venv/bin/activate
python csi_feature_viewer.py
```

Current serial receiver mapping:

```bash
python csi_feature_viewer.py \
  --receiver left=/dev/cu.usbmodem101 \
  --receiver center=/dev/cu.usbmodem1101 \
  --receiver right=/dev/cu.usbmodem2101
```

Wireless/UDP receiver mapping, after flashing the experimental UDP receiver firmware:

```bash
python csi_feature_viewer.py \
  --receiver left=udp:9101 \
  --receiver center=udp:9102 \
  --receiver right=udp:9103
```

To stop it, click the UI window and close it, or press `Ctrl-C` in the terminal.

If the serial ports are busy because a previous UI is still running:

```bash
pkill -f csi_feature_viewer.py
```

## Launch Quick Presence UI

This is the quick-test UI for the three USB receiver setup.
It uses CSI amplitude plus RSSI, a baseline button, and MotionDetector-style rolling variance filtering.

```bash
cd /Users/juliuswenk/Desktop/KD/KZP-inivisible-waves/esp-csi/examples/get-started/tools
source .venv/bin/activate
python rssi_presence_ui.py
```

Launch with the latest labeled left/center/right calibration model:

```bash
python rssi_presence_ui.py \
  --model captures/accuracy_20260507_165733/zone_model.json
```

Launch and expose the three channel confidence values to JavaScript:

```bash
python rssi_presence_ui.py \
  --model captures/accuracy_20260507_165733/zone_model.json \
  --sse-port 8765
```

Cleaner output tuning flags:

```bash
python rssi_presence_ui.py \
  --model captures/accuracy_20260507_165733/zone_model.json \
  --sse-port 8765 \
  --output-enter 0.42 \
  --output-exit 0.28 \
  --output-gap 0.10 \
  --output-attack 0.22 \
  --output-release 0.07
```

In JavaScript, read the stream with:

```javascript
const events = new EventSource("http://127.0.0.1:8765/events");
events.onmessage = (event) => {
  const data = JSON.parse(event.data);
  const left = data.channels.left;
  const center = data.channels.center;
  const right = data.channels.right;
};
```

The helper file [examples/visualization/csi-confidence-client.js](examples/visualization/csi-confidence-client.js) wraps this into `connectCsiConfidence()`.

If the projection is mirrored, enable the `flip output L/R` checkbox in the UI. This only swaps the outgoing JavaScript channel labels and winner; it does not change the physical receiver cards.

Output payload shape:

```json
{
  "t": 1715000000.123,
  "source": "model",
  "mirrored": false,
  "channels": {"left": 0.12, "center": 0.68, "right": 0.08},
  "raw_channels": {"left": 0.15, "center": 0.74, "right": 0.04},
  "zones": {
    "left": {"c": 0.12, "raw_c": 0.15, "raw": 1.2, "rssi": -66, "connected": true},
    "center": {"c": 0.68, "raw_c": 0.74, "raw": 4.8, "rssi": -65, "connected": true},
    "right": {"c": 0.08, "raw_c": 0.04, "raw": 0.9, "rssi": -73, "connected": true}
  },
  "active": true,
  "ambiguous": false,
  "top_gap": 0.59,
  "winner": "center",
  "confidence": 0.68,
  "clear": 0.32
}
```

Use `channels` for the visual because those values are gated and smoothed. Use `raw_channels` only for debugging.

Useful tuning flags:

```bash
python rssi_presence_ui.py \
  --receiver left=/dev/cu.usbmodem101 \
  --receiver center=/dev/cu.usbmodem1101 \
  --receiver right=/dev/cu.usbmodem2101 \
  --baseline-frames 1000 \
  --threshold 2.5 \
  --min-rssi -80 \
  --window-size 64 \
  --average-size 16 \
  --integrator 3
```

## Run A Labeled Accuracy Test

Use this when the geometry changes or localization accuracy feels wrong. It records baseline, left, center, and right, then writes `analysis_report.md`, `analysis.json`, and `zone_model.json`.

```bash
cd /Users/juliuswenk/Desktop/KD/KZP-inivisible-waves/esp-csi/examples/get-started/tools
source .venv/bin/activate
python csi_labeled_accuracy_test.py capture --duration 12 --delay 6
```

Analyze an existing capture again:

```bash
python csi_labeled_accuracy_test.py analyze --outdir captures/accuracy_YYYYMMDD_HHMMSS
```

To stop stale copies before relaunching:

```bash
pkill -f rssi_presence_ui.py
```

## Launch With Fresh Log File

Use this when starting a new test session and you want to preserve the previous CSV:

```bash
cd /Users/juliuswenk/Desktop/KD/KZP-inivisible-waves/esp-csi/examples/get-started/tools
source .venv/bin/activate
LOG="captures/live_features_$(date +%Y%m%d_%H%M%S).csv"
python csi_feature_viewer.py \
  --log-csv "$LOG" \
  --subcarrier-mask captures/subcarrier_quality_20260506.json \
  --median-window 3 \
  --position-average-window 5
```

## Regenerate CSI Subcarrier Mask

Use this after changing board geometry, wall placement, antennas, sender, or receiver orientation. First run the UI and collect a representative CSV while the setup sees baseline plus normal movement. Then run:

```bash
cd /Users/juliuswenk/Desktop/KD/KZP-inivisible-waves/esp-csi/examples/get-started/tools
source .venv/bin/activate
python csi_subcarrier_quality.py \
  captures/live_features_20260506.csv \
  --out captures/subcarrier_quality_20260506.json
```

Expected current result:

```text
166 usable subcarriers out of 192
26 ignored
```

To inspect the mask:

```bash
python -c "import json; p=json.load(open('captures/subcarrier_quality_20260506.json')); print(p['usable_count'], 'usable of', p['subcarriers']); print([m['index'] for m in p['metrics'] if not m.get('usable')])"
```

## Quick Baseline And Zone Capture

This records raw serial CSI from all three receivers without opening the UI.

```bash
cd /Users/juliuswenk/Desktop/KD/KZP-inivisible-waves/esp-csi/examples/get-started/tools
source .venv/bin/activate
OUTDIR="captures/zone_test_$(date +%Y%m%d_%H%M%S)"
python csi_capture_multi.py capture --phase baseline --duration 10 --delay 5 --outdir "$OUTDIR"
python csi_capture_multi.py capture --phase left_zone --duration 10 --delay 5 --outdir "$OUTDIR"
python csi_capture_multi.py capture --phase center_zone --duration 10 --delay 5 --outdir "$OUTDIR"
python csi_capture_multi.py capture --phase right_zone --duration 10 --delay 5 --outdir "$OUTDIR"
python csi_capture_multi.py analyze --outdir "$OUTDIR" --phase left_zone --phase center_zone --phase right_zone
```

## Raw Receiver Monitor

Use this to confirm a receiver is printing repeated `CSI_DATA,...` rows.

```bash
cd /Users/juliuswenk/Desktop/KD/KZP-inivisible-waves/esp-csi/examples/get-started/csi_recv
source /Users/juliuswenk/esp/esp-idf/export.sh
idf.py -p /dev/cu.usbmodem1101 monitor
```

Replace the port for another receiver:

```text
/dev/cu.usbmodem1101  left
/dev/cu.usbmodem101   center
/dev/cu.usbmodem2101  right
```

Exit monitor with `Ctrl-]`.

## Flash Sender

Current sender is the Heltec ESP32-S3 LoRa board on `/dev/cu.usbserial-0001`.

```bash
cd /Users/juliuswenk/Desktop/KD/KZP-inivisible-waves/esp-csi/examples/get-started/csi_send
source /Users/juliuswenk/esp/esp-idf/export.sh
idf.py build
idf.py -p /dev/cu.usbserial-0001 flash monitor
```

For the current iPhone hotspot / wireless receiver setup, use channel 1 so the sender and receivers match:

```bash
cd /Users/juliuswenk/Desktop/KD/KZP-inivisible-waves/esp-csi/examples/get-started/csi_send
source /Users/juliuswenk/esp/esp-idf/export.sh
idf.py -B build-channel-1 -D CONFIG_LESS_INTERFERENCE_CHANNEL=1 build
idf.py -B build-channel-1 -p /dev/cu.usbserial-0001 flash monitor
```

Expected monitor lines include:

```text
================ CSI SEND ================
wifi_channel: 1, send_frequency: 100, mac: 1a:00:00:00:00:00
OLED animation initialized on 128x64 addr=0x3c SDA=17 SCL=18 RST=21 VEXT=36 level=0
```

Exit monitor with `Ctrl-]`.

## Flash Receivers

Default receiver build:

```bash
cd /Users/juliuswenk/Desktop/KD/KZP-inivisible-waves/esp-csi/examples/get-started/csi_recv
source /Users/juliuswenk/esp/esp-idf/export.sh
idf.py build
idf.py -p /dev/cu.usbmodem1101 flash
idf.py -p /dev/cu.usbmodem101 flash
idf.py -p /dev/cu.usbmodem2101 flash
```

Build with a status LED color:

```bash
cd /Users/juliuswenk/Desktop/KD/KZP-inivisible-waves/esp-csi/examples/get-started/csi_recv
source /Users/juliuswenk/esp/esp-idf/export.sh
idf.py -B build-red -D RECEIVER_LED_COLOR=1 build
idf.py -B build-red -p /dev/cu.usbmodem1101 flash
```

```bash
cd /Users/juliuswenk/Desktop/KD/KZP-inivisible-waves/esp-csi/examples/get-started/csi_recv
source /Users/juliuswenk/esp/esp-idf/export.sh
idf.py -B build-blue -D RECEIVER_LED_COLOR=2 build
idf.py -B build-blue -p /dev/cu.usbmodem2101 flash
```

Color values:

```text
0 off
1 red
2 blue
```

## Experimental Wireless Receiver Streaming

Use this only with a 2.4 GHz Wi-Fi network or hotspot that the ESP32-S3 boards can join.
The sender and receivers must use the same channel as that 2.4 GHz network.
The Wi-Fi password is embedded into the build output, so prefer a temporary hotspot/password.

Required values:

```text
WIFI_SSID       2.4 GHz network name
WIFI_PASSWORD   2.4 GHz network password
HOST_IP         IP address of this Mac on that same network
CHANNEL         2.4 GHz channel, commonly 1, 6, or 11
```

Current iPhone hotspot values used on 2026-05-07:

```text
WIFI_SSID       iPhone von Julius
HOST_IP         172.20.10.2
CHANNEL         1
```

Hotspot placement:
- Keep the hotspot close enough that all receivers stay connected reliably.
- Do not place the hotspot phone directly between sender and receivers or directly against a receiver antenna.
- Best practical placement is near the Mac or off to the side of the receiver array, at least ~0.5m away from the sensing line.
- Do not move the hotspot during a calibration/test run, because changing nearby RF reflectors changes the baseline.

Build and flash the three wireless receivers:

```bash
cd /Users/juliuswenk/Desktop/KD/KZP-inivisible-waves/esp-csi/examples/get-started/csi_recv
source /Users/juliuswenk/esp/esp-idf/export.sh

idf.py -B build-wireless-left \
  -D CONFIG_LESS_INTERFERENCE_CHANNEL=CHANNEL \
  -D CSI_UDP_FORWARD=1 \
  -D CSI_WIFI_SSID=\"WIFI_SSID\" \
  -D CSI_WIFI_PASSWORD=\"WIFI_PASSWORD\" \
  -D CSI_UDP_HOST=\"HOST_IP\" \
  -D CSI_UDP_PORT=9101 \
  -D RECEIVER_LED_COLOR=1 build
idf.py -B build-wireless-left -p /dev/cu.usbmodem1101 flash

idf.py -B build-wireless-center \
  -D CONFIG_LESS_INTERFERENCE_CHANNEL=CHANNEL \
  -D CSI_UDP_FORWARD=1 \
  -D CSI_WIFI_SSID=\"WIFI_SSID\" \
  -D CSI_WIFI_PASSWORD=\"WIFI_PASSWORD\" \
  -D CSI_UDP_HOST=\"HOST_IP\" \
  -D CSI_UDP_PORT=9102 \
  -D RECEIVER_LED_COLOR=0 build
idf.py -B build-wireless-center -p /dev/cu.usbmodem101 flash

idf.py -B build-wireless-right \
  -D CONFIG_LESS_INTERFERENCE_CHANNEL=CHANNEL \
  -D CSI_UDP_FORWARD=1 \
  -D CSI_WIFI_SSID=\"WIFI_SSID\" \
  -D CSI_WIFI_PASSWORD=\"WIFI_PASSWORD\" \
  -D CSI_UDP_HOST=\"HOST_IP\" \
  -D CSI_UDP_PORT=9103 \
  -D RECEIVER_LED_COLOR=2 build
idf.py -B build-wireless-right -p /dev/cu.usbmodem2101 flash
```

If the channel is not 11, rebuild and reflash the sender to match:

```bash
cd /Users/juliuswenk/Desktop/KD/KZP-inivisible-waves/esp-csi/examples/get-started/csi_send
source /Users/juliuswenk/esp/esp-idf/export.sh
idf.py -B build-channel-CHANNEL -D CONFIG_LESS_INTERFERENCE_CHANNEL=CHANNEL build
idf.py -B build-channel-CHANNEL -p /dev/cu.usbserial-0001 flash
```

## ESP Chip ID Checks

```bash
source /Users/juliuswenk/esp/esp-idf/export.sh
esptool.py --port /dev/cu.usbserial-0001 chip_id
esptool.py --port /dev/cu.usbmodem1101 chip_id
esptool.py --port /dev/cu.usbmodem101 chip_id
esptool.py --port /dev/cu.usbmodem2101 chip_id
```

## Useful UI Tuning Notes

Start with:

```text
baseline frames: 1000 to 3000 when the environment is stable
confidence threshold: around 0.55, then raise until idle false positives disappear
median window: 3
y moving average: 5
top-pct-norm-divisor: 120.0 (1m) or 30.0 (6m)
motion-norm-divisor: 40.0 (1m) or 15.0 (6m)
```

If the UI feels delayed, reduce:

```bash
--position-average-window 3
```

If the UI is too jumpy, increase:

```bash
--position-average-window 7
```

If single-frame spikes are still visible, try:

```bash
--median-window 5
```

## Presence Detection Thresholds

The combined presence score uses two parallel metrics:

1. **Top-percentile amplitude deviation** — top 20% of rolling amplitude delta from median baseline
2. **Frame-to-frame motion** — average absolute amplitude change between consecutive frames

Each metric is normalized, EMA-smoothed, then combined:

```
combined = top_pct_weight * top_pct_presence + (1 - top_pct_weight) * motion_presence
```

### Default Values (1m behind wall)

| Parameter | CLI Flag | Default | Purpose |
|-----------|----------|---------|---------|
| `top_pct_norm_divisor` | `--top-pct-norm-divisor` | 120.0 | Normalize top-percentile amplitude delta to 0-1 |
| `motion_norm_divisor` | `--motion-norm-divisor` | 40.0 | Normalize frame-to-frame motion to 0-1 |
| `top_pct_ema_alpha` | `--top-pct-ema-alpha` | 0.25 | EMA smoothing for top-percentile (lower = smoother) |
| `motion_ema_alpha` | `--motion-ema-alpha` | 0.30 | EMA smoothing for motion (lower = smoother) |
| `combined_top_pct_weight` | `--combined-top-pct-weight` | 0.6 | Weight of top-pct in combined score |
| `udp_stream` | `--udp-stream` | off | Enable UDP JSON stream for p5.js wall projection |
| `udp_host` | `--udp-host` | 127.0.0.1 | UDP destination host |
| `udp_port` | `--udp-port` | 8888 | UDP destination port |

### 6m Legacy Defaults

If you move the sender back to 6m, use these divisor values:

```bash
--top-pct-norm-divisor 30.0 --motion-norm-divisor 15.0
```

### Tuning Guide

Run the diagnostic script first to see raw metric values:

```bash
python csi_advanced_baseline_test.py \
  --top-pct-norm-divisor 120.0 \
  --motion-norm-divisor 40.0
```

Watch the `motion_raw` and `top_pct` values during:
- **Idle**: should produce normalized values < 0.1
- **Gentle movement**: normalized 0.2-0.5
- **Vigorous movement**: normalized > 0.6

If combined score saturates to 1.0 during idle → increase divisors
If combined score stays near 0 during movement → decrease divisors
If combined score is too jumpy → decrease EMA alpha values
If combined score is too sluggish → increase EMA alpha values

## Adaptive Baseline

The adaptive baseline fixes the core problem where `presence_score` never drops to zero because the static calibration baseline drifts over time (temperature, RF environment changes).

How it works:
- After initial calibration, the baseline slowly tracks ambient CSI drift via EMA
- Only updates when `motion_raw` is below 0.6 (no person disturbing the field)
- Prevents the baseline from absorbing actual presence events

UI control:
- Slider at bottom of UI labeled "adaptive baseline"
- Range: 0.0 (off, static baseline) to 0.05 (fast tracking)
- Label shows current drift from original baseline

Recommended values:
- Start with 0.003 to 0.008 for a stable room
- Use 0.01 to 0.015 if temperature changes noticeably during the session
- If drift value climbs above 2.0 quickly, the baseline is adapting too fast — lower it
- If presence_score still never drops near zero, raise it

CLI argument:

```bash
--baseline-alpha 0.005
```

The "drift" number in the header and feature table shows how far the current baseline has moved from the original. Expect it to grow slowly (0.1-0.5 over minutes) in a stable room.

## Subcarrier-Weighted Detection (Automatic)

Both `csi_feature_viewer.py` and `csi_zone_visualizer.py` now compute per-subcarrier sensitivity weights during calibration:

### How It Works
1. **CoV-based weighting**: During calibration, each subcarrier's amplitude variability (CoV = std/mean) is measured. Subcarriers that fluctuate more are more sensitive to environment changes and get higher weight.
2. **Weighted deltas**: Amplitude deviations from baseline are multiplied by these weights, amplifying motion-sensitive frequencies and suppressing static ones.
3. **Cross-receiver correlation**: Amplitude patterns between adjacent receivers are correlated. When a person enters near one receiver, that receiver's pattern diverges from its neighbor. The differential correlation encodes lateral position:
   - corr(L,C) drops more than corr(C,R) → person toward left
   - corr(C,R) drops more than corr(L,C) → person toward right
   - Both drop equally → person centered
   - Blended at up to 35% with zone confidence position

### No Flags Required
Weighting and correlation are automatic when all 3 receivers are calibrated. No CLI flags needed.

## p5.js Wall Projection (UDP Stream)

Both tools can stream zone scores via UDP JSON to a p5.js sketch:

```bash
cd /Users/juliuswenk/Desktop/KD/KZP-inivisible-waves/esp-csi/examples/get-started/tools
source .venv/bin/activate
python csi_feature_viewer.py --udp-stream --udp-port 8888
# or
python csi_zone_visualizer.py --udp-stream --udp-port 8888
```

### JSON Message Schema (~12 Hz)
```json
{
  "t": 1715000000.123,
  "zones": {
    "left":   {"c": 0.42, "s": 0.85, "p": 0.31},
    "center": {"c": 0.35, "s": 0.71, "p": 0.52},
    "right":  {"c": 0.23, "s": 0.46, "p": 0.19}
  },
  "winner": "left",
  "pos": -0.1850,
  "conf": 0.42,
  "act": 0.340
}
```

| Field | Range | Description |
|-------|-------|-------------|
| `t` | epoch s | Wall clock timestamp |
| `zones[].c` | 0-1 | Zone confidence (normalized, sums to 1.0) |
| `zones[].s` | 0+ | Raw zone score (unnormalized) |
| `zones[].p` | 0-1 | Combined presence EMA for that zone |
| `winner` | string | Highest-confidence zone label |
| `pos` | -1 to 1 | Blended Y position (negative=left, positive=right) |
| `conf` | 0-1 | Max zone confidence |
| `act` | 0-1 | Activity level (clamped by activity_scale) |

### UDP-to-WebSocket Bridge
p5.js in the browser can't receive UDP directly. Run this bridge:

```bash
# Install: npm install ws
node -e "
const dgram = require('dgram');
const WebSocket = require('ws');
const server = new WebSocket.Server({ port: 8080 });
const udp = dgram.createSocket('udp4');
udp.on('message', msg => { server.clients.forEach(c => c.send(msg.toString())); });
udp.bind(8888);
console.log('UDP 8888 → WS 8080 bridge running');
"
```

Then in p5.js:
```javascript
let data = null;
function setup() {
  createCanvas(windowWidth, windowHeight);
  const ws = new WebSocket('ws://localhost:8080');
  ws.onmessage = e => { data = JSON.parse(e.data); };
}
function draw() {
  background(20);
  if (!data?.zones) return;
  // Use data.pos (-1..1), data.conf (0..1), data.act (0..1), data.zones
}
```

### Full Command with All Features
```bash
cd /Users/juliuswenk/Desktop/KD/KZP-inivisible-waves/esp-csi/examples/get-started/tools
source .venv/bin/activate
python csi_feature_viewer.py \
  --log-csv captures/live_features_$(date +%Y%m%d_%H%M%S).csv \
  --subcarrier-mask captures/subcarrier_quality_20260506.json \
  --median-window 3 \
  --position-average-window 5 \
  --top-pct-norm-divisor 120.0 \
  --motion-norm-divisor 40.0 \
  --udp-stream --udp-port 8888
```

## Detection Challenge (6m through wall) — RESOLVED by moving to 1m

### Problem
At 6m distance through a wall, ambient RF noise dominated all tested metrics. No approach reliably separated idle noise from human presence.

### Resolution
Moved sender to ~1m behind wall. Signal amplitude increased dramatically (orig_static: 14-171, combined scores: 0.74-0.99 during movement).

### Tests Conducted (2026-05-06)

| Approach | Idle Range | Movement Range | Separation | Verdict |
|----------|-----------|----------------|------------|---------|
| Static baseline amplitude | 25-46 (top-15%) | 25-160 | None | FAIL |
| Rolling baseline amplitude | 22-42 (top-15%) | 22-156 | None | FAIL |
| Phase cross-correlation | σ=1.4-2.0 (random) | σ=1.4-2.0 | None | FAIL |
| Rate-of-change baseline | 0.2-4.0 | 0.2-4.0 | None | FAIL |
| Stable subcarriers only | 5-70 | 5-70 | None | FAIL |
| Doppler FFT (0.5-8Hz) | 0.12-0.33 | 0.12-0.33 | None | FAIL |

### Root Cause
The sender signal attenuates significantly at 6m through a wall. The ambient noise floor (thermal noise, clock drift, multipath) is comparable to or exceeds the human-reflection signal across ALL domains (amplitude, phase, frequency).

### Remaining Options

1. **Hardware: Move sender closer** — Reduce distance to 3-4m or remove wall obstruction. This is the most effective fix.
2. **Hardware: Add more senders** — Multiple senders at different positions provide spatial diversity and better signal coverage.
3. **Hardware: External antennas on receivers** — Directional antennas pointed at sender area would improve SNR.
4. **Software: Accept coarse detection** — Set a very high threshold (combined > 0.6) that only triggers on vigorous movement. Works for "is someone there?" but not fine positioning.
5. **Software: Machine learning** — Train a classifier on labeled idle/movement data. May extract subtle patterns but requires extensive data collection.
6. **Software: Subcarrier quality masking** — Use the existing subcarrier mask (166/192 usable) and further filter to the top 15 most stable per receiver (identified in `csi_subcarrier_stability.py`).

### Stable Subcarrier Indices (per receiver, top 15 by CV)

```
left:   [149, 158, 150, 151, 155, 156, 157, 152, 147, 144, 146, 160, 148, 8, 159]
center: [9, 10, 7, 11, 8, 6, 158, 12, 157, 155, 148, 160, 153, 156, 151]
right:  [166, 165, 164, 167, 162, 163, 168, 161, 169, 160, 170, 159, 158, 84, 83]
```

### Test Scripts
- `csi_noise_profile.py` — Characterize idle noise floor (30s, stay still)
- `csi_subcarrier_stability.py` — Identify stable subcarriers per receiver
- `csi_rate_of_change_test.py` — Baseline drift rate as presence metric
- `csi_stable_subcarrier_test.py` — Presence using only stable subcarriers
- `csi_doppler_test.py` — Doppler FFT motion detection (requires numpy)
- `csi_phase_position_test.py` — Inter-receiver phase-based Y position
- `csi_advanced_baseline_test.py` — Rolling baseline + top-percentile combined score
