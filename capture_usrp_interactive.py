#!/usr/bin/env python3
"""Capture USRP IQ to SigMF and save a full-duration waterfall PNG.

Automatically connects to the first USRP UHD detects (no serial hardcoding).
Sample rate, gain, analog RX bandwidth, center frequency, and duration are prompted.
Press Enter at any prompt to accept its default.

Run: PYTHONNOUSERSITE=1 /usr/bin/python3 capture_usrp_interactive.py
"""

import json
import math
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import uhd


DEFAULT_CENTER_FREQ_MHZ = 1992.5
DEFAULT_SAMPLE_RATE_MSPS = 2.0
DEFAULT_GAIN_DB = 50.0
DEFAULT_BANDWIDTH_MHZ = 2.0
RX_ANTENNA = "RX2"
DEFAULT_CAPTURE_SECONDS = 180.0
WATERFALL_FFT_SIZE = 2048
WATERFALL_MAX_ROWS = 1200
WATERFALL_AVG_FFTS = 8

# Number of complex samples requested from UHD at a time.
CHUNK_SAMPLES = 262144


def utc_stamp():
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def iso_utc_now():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def prompt_number(label, default, *, positive=False):
    """Prompt for a finite numeric value; allow Enter to use the default."""
    while True:
        raw = input(f"{label} [default {default:g}]: ").strip()
        try:
            value = default if not raw else float(raw)
            if not math.isfinite(value) or (positive and value <= 0):
                raise ValueError
            return value
        except ValueError:
            requirement = "a positive, finite number" if positive else "a finite number"
            print(f"Please enter {requirement}.")



def save_waterfall(data_path, png_path, sample_rate, center_freq, sample_count):
    """Build a time-spanning FFT waterfall from a disk memmap (bounded memory).

    Each plot row averages several adjacent FFTs around a uniformly spaced
    position in the recording. This samples the full duration without reading
    the entire large SigMF file into RAM. Short bursts between rows may be missed.
    """
    import matplotlib
    matplotlib.use("Agg")  # Save PNG on a headless Linux workstation.
    import matplotlib.pyplot as plt

    nfft = WATERFALL_FFT_SIZE
    block_samples = nfft * WATERFALL_AVG_FFTS
    num_rows = min(WATERFALL_MAX_ROWS, max(1, sample_count // block_samples))
    if sample_count < block_samples:
        num_rows = 1
        num_ffts = sample_count // nfft
        block_samples = num_ffts * nfft
    else:
        num_ffts = WATERFALL_AVG_FFTS

    iq = np.memmap(data_path, dtype="<c8", mode="r", shape=(sample_count,))
    window = np.hanning(nfft).astype(np.float32)
    power_rows = np.empty((num_rows, nfft), dtype=np.float32)
    positions = np.linspace(0, sample_count - block_samples, num_rows, dtype=np.int64)

    for index, start in enumerate(positions):
        data = np.asarray(iq[start : start + block_samples]).reshape(num_ffts, nfft)
        fft = np.fft.fft(data * window, axis=1)
        mean_power = np.mean(np.abs(fft) ** 2, axis=0)
        power_rows[index] = 10 * np.log10(
            np.maximum(np.fft.fftshift(mean_power), 1e-20)
        )

    duration = sample_count / sample_rate
    lower_mhz = (center_freq - sample_rate / 2) / 1e6
    upper_mhz = (center_freq + sample_rate / 2) / 1e6
    fig, ax = plt.subplots(figsize=(12, 7), constrained_layout=True)
    vmin, vmax = np.percentile(power_rows, [5, 99.5])
    if vmax <= vmin:
        vmax = vmin + 1
    plot = ax.imshow(
        power_rows,
        origin="lower",
        aspect="auto",
        extent=[lower_mhz, upper_mhz, 0, duration],
        cmap="viridis",
        interpolation="nearest",
        vmin=vmin,
        vmax=vmax,
    )
    ax.set_xlabel("Frequency (MHz)")
    ax.set_ylabel("Capture time (seconds)")
    ax.set_title(f"USRP Waterfall | {center_freq / 1e6:.4f} MHz | {duration:.1f} s")
    fig.colorbar(plot, ax=ax, label="Relative spectral power (dB)")
    fig.savefig(png_path, dpi=170)
    plt.close(fig)
    del iq


def main():
    sample_rate = prompt_number(
        "Sample rate (MS/s)", DEFAULT_SAMPLE_RATE_MSPS, positive=True
    ) * 1e6
    gain_db = prompt_number("RX gain (dB)", DEFAULT_GAIN_DB)
    bandwidth_hz = prompt_number(
        "RX bandwidth (MHz)", DEFAULT_BANDWIDTH_MHZ, positive=True
    ) * 1e6
    center_freq_hz = prompt_number(
        "Center frequency (MHz)", DEFAULT_CENTER_FREQ_MHZ, positive=True
    ) * 1e6
    capture_seconds = prompt_number(
        "Capture duration (seconds)", DEFAULT_CAPTURE_SECONDS, positive=True
    )

    # Empty device address tells UHD to discover and open an available USRP.
    # On hosts with multiple radios, UHD chooses the first matching device.
    print("Detecting connected USRP automatically ...")
    try:
        usrp = uhd.usrp.MultiUSRP("")
    except RuntimeError as exc:
        raise SystemExit(
            "No accessible USRP detected. Check USB/Ethernet, power, and "
            "`uhd_find_devices`. UHD error: " + str(exc)
        ) from exc

    info = usrp.get_usrp_rx_info(0)
    serial = str(info.get("mboard_serial", "unknown")) or "unknown"
    model = str(info.get("mboard_name", info.get("rx_subdev_name", "USRP")))
    print(f"Detected USRP: {model} (serial: {serial})")

    usrp.set_rx_rate(sample_rate, 0)
    usrp.set_rx_freq(uhd.libpyuhd.types.tune_request(center_freq_hz), 0)
    usrp.set_rx_gain(gain_db, 0)
    usrp.set_rx_bandwidth(bandwidth_hz, 0)

    available_antennas = list(usrp.get_rx_antennas(0))
    antenna = RX_ANTENNA if RX_ANTENNA in available_antennas else (
        available_antennas[0] if available_antennas else None
    )
    if antenna is not None:
        usrp.set_rx_antenna(antenna, 0)

    actual_rate = float(usrp.get_rx_rate(0))
    actual_freq = float(usrp.get_rx_freq(0))
    actual_gain = float(usrp.get_rx_gain(0))
    actual_bandwidth = float(usrp.get_rx_bandwidth(0))
    actual_ant = usrp.get_rx_antenna(0)

    script_dir = Path(__file__).resolve().parent
    stamp = utc_stamp()
    # Use detected serial and user-selected frequency in the output folder name.
    safe_serial = "".join(c if c.isalnum() or c in "-_" else "_" for c in serial)
    stem = f"usrp_{safe_serial}_{actual_freq/1e6:.4f}MHz_{stamp}"
    # Save everything directly beside this .py file, regardless of current terminal directory.
    data_path = script_dir / f"{stem}.sigmf-data"
    meta_path = script_dir / f"{stem}.sigmf-meta"
    waterfall_path = script_dir / f"{stem}_waterfall.png"

    print(f"Sample rate : {actual_rate/1e6:.6f} MS/s")
    print(f"Center freq : {actual_freq/1e6:.6f} MHz")
    print(f"RX gain     : {actual_gain:.1f} dB")
    print(f"RX bandwidth: {actual_bandwidth/1e6:.6f} MHz")
    print(f"RX antenna  : {actual_ant}")
    print(f"Duration    : {capture_seconds:.1f} s")
    print(f"Output data : {data_path}")
    print(f"Output meta : {meta_path}")
    print(f"Waterfall   : {waterfall_path}")

    total_target = int(round(actual_rate * capture_seconds))

    stream_args = uhd.usrp.StreamArgs("fc32", "sc16")
    stream_args.channels = [0]
    rx_streamer = usrp.get_rx_stream(stream_args)

    max_samps = int(rx_streamer.get_max_num_samps())
    buf_len = max(CHUNK_SAMPLES, max_samps)
    recv_buffer = np.empty(buf_len, dtype=np.complex64)
    md = uhd.types.RXMetadata()

    cmd = uhd.types.StreamCMD(uhd.types.StreamMode.start_cont)
    cmd.stream_now = True
    rx_streamer.issue_stream_cmd(cmd)

    received_total = 0
    overflow_count = 0
    timeout_count = 0
    capture_start_iso = iso_utc_now()
    t0 = time.monotonic()
    last_print = t0

    try:
        with open(data_path, "wb", buffering=1024 * 1024) as f:
            while received_total < total_target:
                remaining = total_target - received_total
                request = min(buf_len, remaining)

                n = rx_streamer.recv(recv_buffer[:request], md, timeout=1.0)

                if md.error_code == uhd.types.RXMetadataErrorCode.overflow:
                    overflow_count += 1
                    continue

                if md.error_code == uhd.types.RXMetadataErrorCode.timeout:
                    timeout_count += 1
                    print("WARNING: RX timeout")
                    continue

                if md.error_code != uhd.types.RXMetadataErrorCode.none:
                    raise RuntimeError(f"UHD RX error: {md.strerror()}")

                if n <= 0:
                    continue

                # USRP returns fc32; on normal x86 Ubuntu this is little-endian.
                # Explicit conversion keeps the SigMF datatype consistent.
                recv_buffer[:n].astype("<c8", copy=False).tofile(f)
                received_total += n

                now = time.monotonic()
                if now - last_print >= 5.0:
                    elapsed = now - t0
                    pct = 100.0 * received_total / total_target
                    captured_sec = received_total / actual_rate
                    print(
                        f"{pct:6.2f}% | "
                        f"{captured_sec:7.1f}/{capture_seconds:.1f} s | "
                        f"overflows={overflow_count} | timeouts={timeout_count}"
                    )
                    last_print = now

    except KeyboardInterrupt:
        print("\nCapture interrupted by user. Saving metadata for partial capture.")

    finally:
        stop = uhd.types.StreamCMD(uhd.types.StreamMode.stop_cont)
        rx_streamer.issue_stream_cmd(stop)

    elapsed_wall = time.monotonic() - t0
    captured_seconds = received_total / actual_rate

    meta = {
        "global": {
            "core:datatype": "cf32_le",
            "core:sample_rate": actual_rate,
            "core:version": "1.0.0",
            "core:description": "USRP IQ capture at user-selected center frequency",
            "core:author": "capture_usrp_interactive.py",
            "core:recorder": "UHD Python API",
            "core:hw": f"USRP {model}, serial {serial}",
        },
        "captures": [
            {
                "core:sample_start": 0,
                "core:frequency": actual_freq,
                "core:datetime": capture_start_iso,
            }
        ],
        "annotations": [],
        "capture_info": {
            "serial": serial,
            "model": model,
            "requested_center_frequency_hz": center_freq_hz,
            "actual_center_frequency_hz": actual_freq,
            "requested_sample_rate_sps": sample_rate,
            "actual_sample_rate_sps": actual_rate,
            "requested_gain_db": gain_db,
            "actual_gain_db": actual_gain,
            "requested_bandwidth_hz": bandwidth_hz,
            "actual_bandwidth_hz": actual_bandwidth,
            "rx_antenna": actual_ant,
            "requested_duration_seconds": capture_seconds,
            "captured_duration_seconds": captured_seconds,
            "samples_written": int(received_total),
            "overflow_count": int(overflow_count),
            "timeout_count": int(timeout_count),
            "wall_time_seconds": elapsed_wall,
        },
    }

    with open(meta_path, "w") as f:
        json.dump(meta, f, indent=2)

    size_gb = data_path.stat().st_size / 1e9 if data_path.exists() else 0.0

    print("\nCapture complete.")
    print(f"Samples written : {received_total:,}")
    print(f"Captured time   : {captured_seconds:.3f} s")
    print(f"Overflows       : {overflow_count}")
    print(f"Timeouts        : {timeout_count}")
    print(f"Data size       : {size_gb:.3f} GB")
    print(f"SigMF data      : {data_path}")
    print(f"SigMF metadata  : {meta_path}")
    if received_total >= WATERFALL_FFT_SIZE:
        try:
            print("Generating full-duration waterfall ...")
            save_waterfall(
                data_path, waterfall_path, actual_rate, actual_freq, received_total
            )
            print(f"Waterfall PNG   : {waterfall_path}")
        except Exception as exc:
            print(f"WARNING: Waterfall generation failed: {exc}")
    else:
        print("Waterfall skipped: insufficient captured IQ samples.")


if __name__ == "__main__":
    main()
