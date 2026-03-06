#!/usr/bin/env python3
"""
rx.py — GRC-схема приёмника (UDP → AM → ACARS лог).

Принимает узкополосный IQ по UDP (48 kHz, gr_complex) для каждого из двух
каналов ACARS, выполняет AM-демодуляцию и декодирование ACARS.

Параметры:
  - Канал 1: UDP порт 52001  (131.725 MHz)
  - Канал 2: UDP порт 52002  (131.825 MHz)
  - channel_rate = 48 kHz, audio_decim = 1
  - ACARS decoder: acars.acars(4, <log_path>, False)
"""

import argparse
import signal
import sys

from gnuradio import gr, blocks, analog
import acars as acars_mod


# ─── Параметры ───────────────────────────────────────────────────────────────
CHANNEL_RATE = 48000    # 48 kHz (после децимации в tx.py)
AUDIO_DECIM = 1
UDP_MTU = 1472

DEFAULT_UDP_PORTS = [52001, 52002]
DEFAULT_LOGS = [
    "/tmp/log_acars_131_725.txt",
    "/tmp/log_acars_131_825.txt",
]
CHANNEL_LABELS = ["131.725 MHz", "131.825 MHz"]


class AcarsRx(gr.top_block):
    """Двухканальный приёмник UDP → AM → ACARS."""

    def __init__(self, udp_sources, log_paths):
        gr.top_block.__init__(self, "ACARS RX Decoder")

        for ch_idx, ((host, port), log_path) in enumerate(
            zip(udp_sources, log_paths)
        ):
            # UDP источник (gr_complex)
            udp_src = blocks.udp_source(
                gr.sizeof_gr_complex, host, port, UDP_MTU, True,
            )

            # AM-демодуляция (огибающая комплексного сигнала)
            am_demod = blocks.complex_to_mag(1)

            # ACARS декодер (из OOT-блока acars)
            # acars.acars(channel_rate_id, log_path, append_mode)
            # channel_rate_id=4 соответствует 48 kHz
            acars_decoder = acars_mod.acars(4, log_path, False)

            # Цепочка: UDP → AM demod → ACARS decoder
            self.connect(udp_src, am_demod, acars_decoder)

            setattr(self, f"udp_src_{ch_idx}", udp_src)
            setattr(self, f"am_demod_{ch_idx}", am_demod)
            setattr(self, f"acars_decoder_{ch_idx}", acars_decoder)

            print(
                f"  Канал {ch_idx+1} ({CHANNEL_LABELS[ch_idx]}): "
                f"{host}:{port} → {log_path}"
            )


def parse_udp_source(s):
    """Разбирает 'host:port'."""
    parts = s.rsplit(":", 1)
    if len(parts) != 2:
        raise argparse.ArgumentTypeError(f"Ожидается HOST:PORT, получено: {s}")
    return parts[0], int(parts[1])


def main():
    parser = argparse.ArgumentParser(
        description="ACARS RX — UDP → AM-демодуляция → ACARS декодер",
    )
    parser.add_argument(
        "--udp-source", type=parse_udp_source, action="append", default=[],
        help="Источник UDP HOST:PORT (указать дважды для двух каналов)",
    )
    parser.add_argument(
        "--log", action="append", default=[],
        help="Путь к файлу лога ACARS (указать дважды для двух каналов)",
    )
    args = parser.parse_args()

    udp_sources = args.udp_source
    if not udp_sources:
        udp_sources = [("0.0.0.0", p) for p in DEFAULT_UDP_PORTS]
    if len(udp_sources) < 2:
        parser.error("Нужно указать два --udp-source (по одному на канал)")

    log_paths = args.log
    if not log_paths:
        log_paths = list(DEFAULT_LOGS)
    if len(log_paths) < 2:
        parser.error("Нужно указать два --log (по одному на канал)")

    print(f"[RX] channel_rate={CHANNEL_RATE} Hz, audio_decim={AUDIO_DECIM}")

    tb = AcarsRx(udp_sources, log_paths)

    def sig_handler(_signo, _frame):
        print("\n[RX] Остановка...")
        tb.stop()
        tb.wait()
        sys.exit(0)

    signal.signal(signal.SIGINT, sig_handler)
    signal.signal(signal.SIGTERM, sig_handler)

    tb.start()
    print("[RX] Запущен. Ctrl+C для остановки.")
    tb.wait()


if __name__ == "__main__":
    main()
