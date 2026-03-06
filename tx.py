#!/usr/bin/env python3
"""
tx.py — GRC-схема передатчика (форвардер).

Принимает сигнал с RTL-SDR (SoapySDR), фильтрует два канала ACARS
(131.725 MHz и 131.825 MHz), понижает частоту дискретизации и отправляет
узкополосный IQ по UDP.

Параметры сигнала:
  - SDR sample rate: 240 kHz
  - Центральная частота: 131.775 MHz (середина между каналами)
  - Канал 1: 131.725 MHz → смещение -50 kHz → UDP порт 52001
  - Канал 2: 131.825 MHz → смещение +50 kHz → UDP порт 52002
  - Фильтр: LPF cutoff 5 kHz, transition 6 kHz, decim=5 → 48 kHz на канал
  - UDP: gr_complex, MTU 1472
"""

import argparse
import signal
import sys

from gnuradio import gr, blocks, filter as gr_filter, analog
from gnuradio.filter import firdes
import soapy


# ─── Параметры ───────────────────────────────────────────────────────────────
SDR_SAMPLE_RATE = 240000        # 240 kHz
CENTER_FREQ = 131.775e6         # середина между 131.725 и 131.825
CHANNEL_FREQS = [131.725e6, 131.825e6]
CHANNEL_OFFSETS = [f - CENTER_FREQ for f in CHANNEL_FREQS]  # -50 kHz, +50 kHz
LPF_CUTOFF = 5000               # 5 kHz
LPF_TRANSITION = 6000           # 6 kHz
DECIMATION = 5                  # 240 kHz / 5 = 48 kHz
CHANNEL_RATE = SDR_SAMPLE_RATE // DECIMATION  # 48 kHz
UDP_MTU = 1472
DEFAULT_GAIN = 40.0

DEFAULT_UDP_PORTS = [52001, 52002]


class AcarsTx(gr.top_block):
    """Двухканальный форвардер SDR → UDP."""

    def __init__(self, udp_dests, gain=DEFAULT_GAIN, sdr_device="driver=rtlsdr"):
        gr.top_block.__init__(self, "ACARS TX Forwarder")

        # ─── SDR источник ────────────────────────────────────────────────
        self.sdr_source = soapy.source(
            sdr_device, "fc32", 1, "",
            "bufflen=16384",
            [SDR_SAMPLE_RATE], [CENTER_FREQ],
        )
        self.sdr_source.set_gain(0, gain)

        for ch_idx, (offset, dest) in enumerate(zip(CHANNEL_OFFSETS, udp_dests)):
            host, port = dest

            # Сдвиг частоты (перенос канала в baseband)
            xlate_taps = firdes.low_pass(
                1.0, SDR_SAMPLE_RATE, LPF_CUTOFF, LPF_TRANSITION,
                window=firdes.WIN_HAMMING,
            )
            freq_xlate = gr_filter.freq_xlating_fir_filter_ccc(
                DECIMATION, xlate_taps, -offset, SDR_SAMPLE_RATE,
            )

            # UDP sink (gr_complex → сеть)
            udp_sink = blocks.udp_sink(
                gr.sizeof_gr_complex, host, port, UDP_MTU, True,
            )

            # Соединяем
            self.connect(self.sdr_source, freq_xlate, udp_sink)

            setattr(self, f"xlate_{ch_idx}", freq_xlate)
            setattr(self, f"udp_sink_{ch_idx}", udp_sink)

    def set_gain(self, gain):
        self.sdr_source.set_gain(0, gain)


def parse_udp_dest(s):
    """Разбирает 'host:port' в (host, int(port))."""
    parts = s.rsplit(":", 1)
    if len(parts) != 2:
        raise argparse.ArgumentTypeError(f"Ожидается HOST:PORT, получено: {s}")
    return parts[0], int(parts[1])


def main():
    parser = argparse.ArgumentParser(
        description="ACARS TX — SDR → двухканальный UDP форвардер",
    )
    parser.add_argument(
        "--udp-dest", type=parse_udp_dest, action="append", default=[],
        help="Адрес назначения HOST:PORT (указать дважды для двух каналов)",
    )
    parser.add_argument(
        "--gain", type=float, default=DEFAULT_GAIN,
        help=f"Усиление SDR (по умолчанию {DEFAULT_GAIN})",
    )
    parser.add_argument(
        "--device", type=str, default="driver=rtlsdr",
        help="SoapySDR device string",
    )
    args = parser.parse_args()

    # Если адреса не указаны — используем localhost и стандартные порты
    udp_dests = args.udp_dest
    if not udp_dests:
        udp_dests = [("127.0.0.1", p) for p in DEFAULT_UDP_PORTS]
    if len(udp_dests) < 2:
        parser.error("Нужно указать два --udp-dest (по одному на канал)")

    print(f"[TX] SDR rate={SDR_SAMPLE_RATE} Hz, center={CENTER_FREQ/1e6:.3f} MHz")
    for i, (h, p) in enumerate(udp_dests):
        print(f"  Канал {i+1}: {CHANNEL_FREQS[i]/1e6:.3f} MHz → {h}:{p}")

    tb = AcarsTx(udp_dests, gain=args.gain, sdr_device=args.device)

    def sig_handler(_signo, _frame):
        print("\n[TX] Остановка...")
        tb.stop()
        tb.wait()
        sys.exit(0)

    signal.signal(signal.SIGINT, sig_handler)
    signal.signal(signal.SIGTERM, sig_handler)

    tb.start()
    print("[TX] Запущен. Ctrl+C для остановки.")
    tb.wait()


if __name__ == "__main__":
    main()
