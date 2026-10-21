# USRP IQ Capture + Waterfall

Capture complex IQ samples from a UHD-supported USRP, save the recording in **SigMF** format, and generate a waterfall PNG showing the selected recording duration. The script automatically opens an available USRP; **you do not need to enter its serial number**.

**Script:** `capture_usrp_interactive.py`  
**Platform:** Ubuntu/Linux with Python 3, UHD Python bindings, NumPy, and Matplotlib.

## Quick start

Put `capture_usrp_interactive.py` and this README in the same folder. On the machine connected to the radio:

```bash
# Check the radio first
uhd_find_devices

# Run (matches the Python interpreter used by the original project)
PYTHONNOUSERSITE=1 /usr/bin/python3 capture_usrp_interactive.py
```

The script asks for:

| Setting | Unit | Default | Notes |
|---|---|---:|---|
| Sample rate | MS/s | 2 | Rate of complex IQ samples |
| RX gain | dB | 50 | Radio-specific gain range |
| RX analog bandwidth | MHz | 2 | Hardware-filter bandwidth, not necessarily exactly achievable |
| Center frequency | MHz | 1992.5 | Frequency at the middle of the recording |
| Capture duration | seconds | 180 | Number of *received samples* targeted, expressed as seconds |

Press **Enter** to accept a default. Inputs must be numeric; the rate, bandwidth, frequency, and duration must be positive. Some numeric requests may be outside the hardware's supported ranges; the script prints the **actual** values reported by UHD after configuration.

### Dependencies

For Ubuntu installations with the distribution UHD bindings:

```bash
sudo apt update
sudo apt install uhd-host python3-uhd python3-numpy python3-matplotlib
```

The package name/availability may vary with your Ubuntu release or how UHD was installed. Verify that **the Python interpreter used to run the script** can import everything:

```bash
PYTHONNOUSERSITE=1 /usr/bin/python3 -c 'import uhd, numpy, matplotlib; print("Dependencies OK")'
uhd_config_info --version
```

If `python3-uhd` is not available, install/use the UHD Python bindings that match your UHD installation rather than mixing incompatible versions. A virtual environment without access to system packages may not see `/usr/bin/python3`'s UHD bindings.

## What happens during a capture

1. You enter capture settings.
2. `uhd.usrp.MultiUSRP("")` opens an available USRP; the serial and model are read from UHD.
3. The script configures RX channel 0. It prefers antenna **RX2** if available, otherwise it selects the first advertised RX antenna.
4. It streams complex floating-point IQ and writes chunks to disk. The requested receive-buffer size is `262144` samples (or larger if required by UHD), not a whole recording in memory.
5. After capture, it saves SigMF metadata, then builds a waterfall PNG from selected FFT blocks in the saved IQ file.

**Multiple radios:** The script does not ask which one to use; UHD chooses an available matching radio. If you have more than one USRP connected, disconnect the others or modify the device selection code to target a serial/address explicitly.

## Output files and location

All outputs are written **directly beside `capture_usrp_interactive.py`**, even if you launch the script from a different terminal directory. Filenames include the detected serial, actual center frequency, and a UTC timestamp:

```text
my_capture_folder/
├── capture_usrp_interactive.py
├── README.md
├── usrp_34D9DCF_1992.5000MHz_20261020T120000Z.sigmf-data
├── usrp_34D9DCF_1992.5000MHz_20261020T120000Z.sigmf-meta
└── usrp_34D9DCF_1992.5000MHz_20261020T120000Z_waterfall.png
```

- `.sigmf-data`: raw interleaved complex IQ, **`cf32_le`** (complex float32, little endian), **8 bytes per sample**.
- `.sigmf-meta`: sample rate, center frequency, timestamps, hardware info, requested/actual settings, samples written, overflows/timeouts, and actual captured duration.
- `_waterfall.png`: frequency (MHz) on X, recording time (s) on Y, **relative FFT power** (dB) as color.

Estimated disk consumption for raw IQ: `sample_rate_samples_per_second × duration_seconds × 8` bytes. At 2 MS/s for 180 seconds, this is **2.88 GB** (decimal), plus a small metadata file and PNG. Have enough free storage **in the directory containing the script**.

## Waterfall behavior and limitations

The waterfall is generated **after** recording; it is not a live display. It uses a memory-mapped IQ file and computes up to **1,200 time rows** with **2,048 FFT bins** per row, averaging up to **8 adjacent FFTs** for each row. Rows are spaced throughout the recording, so **the waterfall samples the full time span but does not process every sample**. Very short transmissions, bursts, or fast hopping events between sampled intervals can be absent from the PNG even when they are present in the IQ file.

- FFT bin spacing is approximately `sample_rate / 2048`: **976.6 Hz** at 2 MS/s.
- Waterfall color indicates **relative** power, **not calibrated dBm**.
- The displayed X-axis covers approximately `center frequency ± sample rate / 2`; the usable passband may be narrower because of configured analog bandwidth and hardware filtering.
- A short capture containing fewer than 2,048 samples cannot produce a waterfall; the script skips it.
- The PNG generation uses Matplotlib's noninteractive `Agg` backend, so no graphical desktop is required.

If you need to detect every brief burst, compute FFTs continuously (or with a known hop size) and store a full or suitably decimated spectrogram rather than using these sparsely sampled rows.

## Debugging / troubleshooting

### 1. `No accessible USRP detected`, `No devices found`, or no serial listed

Run:

```bash
uhd_find_devices
uhd_usrp_probe
```

For a **USB B200/B210/NI USRP-2901**:

```bash
lsusb
lsusb -t
sudo dmesg | tail -n 60
```

Check USB cable/port, power, permissions, and that the device shows up in `lsusb`. Prefer a USB 3 port/cable for higher rates. `lsusb -t` helps confirm negotiated USB link speed. If UHD cannot open it, check that no other program (GNU Radio, another Python capture, etc.) is using it. To look for a previous capture process:

```bash
ps aux | grep -E '[p]ython3|[u]hd|[g]nuradio'
```

Close the other process normally before retrying; avoid killing unrelated processes.

For an **Ethernet USRP such as N200**:

```bash
ip -br address
ip link
ping -c 3 <USRP_IP_ADDRESS>
uhd_find_devices --args 'addr=<USRP_IP_ADDRESS>'
```

Ensure the host's Ethernet interface is on the radio's subnet, the link is up, and power/network cabling are correct. ICMP ping can be blocked even if other connectivity works. **Important:** This script uses automatic discovery; if an Ethernet USRP is reachable by explicit IP but not automatically discovered, change the `MultiUSRP("")` device argument to `MultiUSRP("addr=<USRP_IP_ADDRESS>")` or add an explicit device-address prompt.

### 2. `ModuleNotFoundError: No module named 'uhd'`

Verify the exact interpreter:

```bash
/usr/bin/python3 -c 'import sys; print(sys.executable); import uhd; print(uhd)'
```

Install/configure the UHD Python bindings for that interpreter. If you installed UHD from source, check its Python binding installation paths and version compatibility; using a different Conda/venv/system Python can hide the module.

### 3. `ImportError` or errors mentioning `libuhd`, symbols, or UHD image files

```bash
uhd_config_info --version
uhd_find_devices
uhd_usrp_probe
```

Potential causes include an incompatible combination of UHD host libraries and Python bindings or missing device firmware/FPGA images. Follow the error's exact image-path instructions. For installations supporting it, `uhd_images_downloader` can download matching device images. Avoid mixing distribution UHD libraries with unrelated source-built bindings.

### 4. `ValueError`, unsupported sample rate, gain, center frequency, or bandwidth

Not all radios accept all requested values. Try a known supported rate (for example 2 MS/s on a B200/B210), reduce gain, or choose a supported frequency and bandwidth. Query supported ranges in Python if needed:

```python
import uhd
radio = uhd.usrp.MultiUSRP("")
print("Rates:", radio.get_rx_rates(0))
print("Gain:", radio.get_rx_gain_range(0))
print("Frequency:", radio.get_rx_freq_range(0))
print("Bandwidth:", radio.get_rx_bandwidth_range(0))
print("Antennas:", radio.get_rx_antennas(0))
```

These are diagnostic commands, not additional settings in the capture script. UHD may coerce requested values to supported ones; compare the `Sample rate`, `Center freq`, `RX gain`, and `RX bandwidth` printed by the program with your inputs.

### 5. `WARNING: RX timeout`

The host failed to receive samples within the script's **1-second receive timeout**. Verify the USRP connection and availability; try reconnecting the device, checking power, and running a simpler UHD probe. Repeated timeouts may indicate a disconnected/stalled stream. The loop retries on timeouts, so a stalled capture may continue waiting until interrupted.

### 6. `overflows` increase or `O` messages from UHD

An RX overflow means the host did not keep up with the radio's incoming data. Possible fixes:

- Lower the **sample rate** (this directly lowers raw IQ throughput).
- Use a reliable USB 3 path for USB radios or an appropriate dedicated Ethernet link for networked radios.
- Write to a sufficiently fast local SSD with enough free space; avoid slow/network-mounted destinations.
- Close other heavy CPU, disk, or USB workloads.
- Check CPU, memory, and disk activity with `top`, `free -h`, `df -h .`, or `iostat -xz 1` (if installed).

**Note:** This code counts overflow events and continues receiving, but does **not** insert placeholder IQ samples for dropped intervals or produce a gap-aware time axis. Overflow can compromise timing continuity, so do not assume the waterfall time coordinate is exact after dropped samples.

### 7. `Permission denied`, `No space left on device`, or missing output files

The output directory is the **script's own directory**, not necessarily the current shell directory:

```bash
ls -lah /path/to/capture/folder
findmnt -T /path/to/capture/folder
df -h /path/to/capture/folder
```

Make sure that directory is writable and has sufficient free disk space. If it is on a read-only or slow mount, move the `.py` script to a writable, fast folder and run it there. If writing fails during recording, this version may stop with an exception before writing final SigMF metadata or a waterfall; any partial `.sigmf-data` needs inspection before use.

### 8. `Waterfall generation failed`, PNG missing, or Matplotlib error

First check the terminal output and verify the IQ file was written:

```bash
PYTHONNOUSERSITE=1 /usr/bin/python3 -c 'import numpy, matplotlib; print(numpy.__version__, matplotlib.__version__)'
ls -lh *_waterfall.png *.sigmf-data *.sigmf-meta
```

The script only generates a PNG **after the recording ends** and if at least **2,048 samples** were captured. Check that Matplotlib is installed for the selected interpreter, disk space is adequate, and the directory is writable. The `.sigmf-data` and `.sigmf-meta` files can still be valid if only the plotting stage fails.

### 9. Waterfall looks empty, noisy, off-frequency, or clipped

- Confirm center frequency units: the terminal prompt expects **MHz**, not Hz or GHz. Example: enter `1992.5`, not `1992500000` or `1.9925`.
- Check the **actual** center frequency and sample rate reported by UHD and recorded in metadata.
- Verify the proper antenna/input, attached RF chain, frequency band, and antenna/LNB power where applicable. The script defaults to **RX2** when supported and does not automatically configure an external LNB or bias tee.
- Try adjusting gain and analog bandwidth. Too much gain can clip the ADC; too little can bury signals in noise.
- Be aware that the waterfall uses **sparse time sampling**, so short bursts can be missed. The color scale is automatically derived from the waterfall rows; a weak but present trace may have low contrast.
- A straight horizontal feature means a nearly fixed frequency; a sloped feature may indicate frequency drift/Doppler, but hardware LO drift and other sources should also be ruled out.

### 10. Script will not stop / partial capture after Ctrl+C

Press **Ctrl+C** in the terminal. If interruption occurs inside the normal receiving loop, the script stops streaming and saves metadata for the samples recorded so far, then attempts to generate a PNG. Forced termination (`kill -9`, power loss, or failure during file I/O) does **not** guarantee metadata or PNG creation.

### 11. Sanity-check the raw IQ size against metadata

For `.sigmf-data` with `cf32_le`, every complex sample occupies **8 bytes**. The size should match `samples_written × 8` in the corresponding `.sigmf-meta` when recording completed normally. A quick check:

```bash
/usr/bin/python3 - <<'PY'
import json
from pathlib import Path
for meta_file in Path('.').glob('*.sigmf-meta'):
    metadata = json.loads(meta_file.read_text())
    data_file = meta_file.with_suffix('.sigmf-data')
    if not data_file.exists():
        print('MISSING DATA:', data_file)
        continue
    actual = data_file.stat().st_size
    expected = metadata['capture_info']['samples_written'] * 8
    print(data_file.name, 'OK' if actual == expected else 'SIZE MISMATCH', actual, expected)
PY
```

Run this from the capture output folder.

## Practical notes for repeatable RF experiments

Record the USRP model/serial, antenna and RF front end, center frequency, requested **and actual** sample rate/bandwidth/gain, UTC capture timestamp, number of samples, and overflow count. Metadata captures most software settings, but it does not document external antennas, LNB LO frequencies, or lab wiring.

**Timing caveat:** `captured_duration_seconds` is computed from the number of samples written divided by the configured rate. It is not a guaranteed measure of continuously elapsed wall time if overflows or timeouts occur. For Doppler/short-burst analysis, check for dropped samples before interpreting time alignment.

## Code customization

Settings near the top of the script:

```python
RX_ANTENNA = "RX2"
CHUNK_SAMPLES = 262144
WATERFALL_FFT_SIZE = 2048
WATERFALL_MAX_ROWS = 1200
WATERFALL_AVG_FFTS = 8
```

Changing FFT size affects frequency resolution, while `WATERFALL_MAX_ROWS` and `WATERFALL_AVG_FFTS` affect the plot's temporal detail and computation cost. Increasing plot rows alone does not make it an exhaustive spectrogram.
