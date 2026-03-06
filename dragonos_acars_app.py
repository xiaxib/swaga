#!/usr/bin/env python3
"""
dragonos_acars_app.py — основной GUI и потоковая схема DragonOS ACARS Monitor.

Режимы работы:
  1) Локальный приём RTL-SDR + GUI (по умолчанию)
  2) Офлайн-анализ логов (--offline)
  3) Форвардер SDR → UDP без GUI (--forward-only)
  4) Приём UDP + GUI (--udp-source)

Параметры сигнала:
  - SDR sample rate: 240 kHz
  - Центральная частота: 131.775 MHz
  - Каналы: 131.725 MHz (UDP 52001), 131.825 MHz (UDP 52002)
  - Фильтр: LPF 5 kHz / 6 kHz, decim=5 → 48 kHz на канал
  - AM-демодуляция → ACARS decoder
"""

import argparse
import os
import shutil
import signal
import sys
import threading
import time
from datetime import datetime

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QTabWidget, QPushButton, QLabel, QSlider, QFileDialog,
    QMessageBox, QStatusBar, QAction,
)
from PyQt5.QtCore import Qt, QTimer, pyqtSignal

# GNU Radio (может отсутствовать в офлайн-режиме)
try:
    from gnuradio import gr, blocks, filter as gr_filter, analog
    from gnuradio.filter import firdes
    import soapy
    import acars as acars_mod
    HAS_GNURADIO = True
except ImportError:
    HAS_GNURADIO = False

# Импортируем GUI-компоненты из acars_gui
from acars_gui import (
    AcarsTableTab, RawLogTab, ByteLayoutTab, StatsTab,
    AcarsParamsTab, SpectrumTab, MapTab,
    load_log_file, CHANNEL_LABELS, DEFAULT_LOGS, REFRESH_INTERVAL_MS,
)


# ─── Параметры сигнала ──────────────────────────────────────────────────────
SDR_SAMPLE_RATE = 240000
CENTER_FREQ = 131.775e6
CHANNEL_FREQS = [131.725e6, 131.825e6]
CHANNEL_OFFSETS = [f - CENTER_FREQ for f in CHANNEL_FREQS]
LPF_CUTOFF = 5000
LPF_TRANSITION = 6000
DECIMATION = 5
CHANNEL_RATE = SDR_SAMPLE_RATE // DECIMATION  # 48 kHz
AUDIO_DECIM = 1
UDP_MTU = 1472

DEFAULT_UDP_PORTS = [52001, 52002]
DEFAULT_GAIN = 40.0


# ─── GNU Radio Flowgraphs ───────────────────────────────────────────────────

class LocalReceiverFlowgraph(gr.top_block):
    """SDR → фильтрация → AM демод → ACARS декодер (локальный приём)."""

    def __init__(self, log_paths, gain=DEFAULT_GAIN, device="driver=rtlsdr"):
        gr.top_block.__init__(self, "ACARS Local Receiver")

        self.sdr_source = soapy.source(
            device, "fc32", 1, "", "bufflen=16384",
            [SDR_SAMPLE_RATE], [CENTER_FREQ],
        )
        self.sdr_source.set_gain(0, gain)

        for ch_idx, (offset, log_path) in enumerate(
            zip(CHANNEL_OFFSETS, log_paths)
        ):
            xlate_taps = firdes.low_pass(
                1.0, SDR_SAMPLE_RATE, LPF_CUTOFF, LPF_TRANSITION,
                window=firdes.WIN_HAMMING,
            )
            freq_xlate = gr_filter.freq_xlating_fir_filter_ccc(
                DECIMATION, xlate_taps, -offset, SDR_SAMPLE_RATE,
            )
            am_demod = blocks.complex_to_mag(1)
            acars_decoder = acars_mod.acars(4, log_path, False)

            self.connect(self.sdr_source, freq_xlate, am_demod, acars_decoder)

            setattr(self, f"xlate_{ch_idx}", freq_xlate)
            setattr(self, f"am_demod_{ch_idx}", am_demod)
            setattr(self, f"acars_{ch_idx}", acars_decoder)

    def set_gain(self, gain):
        self.sdr_source.set_gain(0, gain)


class ForwarderFlowgraph(gr.top_block):
    """SDR → фильтрация → UDP (форвардер, без декода)."""

    def __init__(self, udp_dests, gain=DEFAULT_GAIN, device="driver=rtlsdr"):
        gr.top_block.__init__(self, "ACARS Forwarder")

        self.sdr_source = soapy.source(
            device, "fc32", 1, "", "bufflen=16384",
            [SDR_SAMPLE_RATE], [CENTER_FREQ],
        )
        self.sdr_source.set_gain(0, gain)

        for ch_idx, (offset, (host, port)) in enumerate(
            zip(CHANNEL_OFFSETS, udp_dests)
        ):
            xlate_taps = firdes.low_pass(
                1.0, SDR_SAMPLE_RATE, LPF_CUTOFF, LPF_TRANSITION,
                window=firdes.WIN_HAMMING,
            )
            freq_xlate = gr_filter.freq_xlating_fir_filter_ccc(
                DECIMATION, xlate_taps, -offset, SDR_SAMPLE_RATE,
            )
            udp_sink = blocks.udp_sink(
                gr.sizeof_gr_complex, host, port, UDP_MTU, True,
            )

            self.connect(self.sdr_source, freq_xlate, udp_sink)

            setattr(self, f"xlate_{ch_idx}", freq_xlate)
            setattr(self, f"udp_sink_{ch_idx}", udp_sink)

    def set_gain(self, gain):
        self.sdr_source.set_gain(0, gain)


class UdpReceiverFlowgraph(gr.top_block):
    """UDP источник → AM демод → ACARS декодер (приём от удалённого Pi)."""

    def __init__(self, udp_sources, log_paths):
        gr.top_block.__init__(self, "ACARS UDP Receiver")

        for ch_idx, ((host, port), log_path) in enumerate(
            zip(udp_sources, log_paths)
        ):
            udp_src = blocks.udp_source(
                gr.sizeof_gr_complex, host, port, UDP_MTU, True,
            )
            am_demod = blocks.complex_to_mag(1)
            acars_decoder = acars_mod.acars(4, log_path, False)

            self.connect(udp_src, am_demod, acars_decoder)

            setattr(self, f"udp_src_{ch_idx}", udp_src)
            setattr(self, f"am_demod_{ch_idx}", am_demod)
            setattr(self, f"acars_{ch_idx}", acars_decoder)


# ─── Главное окно ────────────────────────────────────────────────────────────

class AcarsMainWindow(QMainWindow):
    """Основное окно DragonOS ACARS Monitor."""

    sig_reload = pyqtSignal()

    def __init__(self, log_paths, flowgraph=None, is_offline=False,
                 has_sdr=False):
        super().__init__()
        self.setWindowTitle("DragonOS ACARS Monitor")
        self.setMinimumSize(1100, 750)

        self.log_paths = list(log_paths)
        self.flowgraph = flowgraph
        self.is_offline = is_offline
        self.has_sdr = has_sdr
        self._paused = False
        self._all_msgs = []
        self._msgs_by_channel = {}

        self._build_menu()
        self._build_ui()
        self._setup_refresh()

        self.sig_reload.connect(self._reload_logs)

        if self.log_paths:
            self._reload_logs()

    def _build_menu(self):
        menubar = self.menuBar()
        file_menu = menubar.addMenu("Файл")

        act_log = QAction("Файл лога…", self)
        act_log.triggered.connect(self._choose_log_files)
        file_menu.addAction(act_log)

        act_export = QAction("Выгрузить лог", self)
        act_export.triggered.connect(self._export_log)
        file_menu.addAction(act_export)

        file_menu.addSeparator()

        act_quit = QAction("Выход", self)
        act_quit.triggered.connect(self.close)
        file_menu.addAction(act_quit)

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)

        # ─── Панель управления ───────────────────────────────────────────
        toolbar = QHBoxLayout()

        self.btn_pause = QPushButton("Пауза")
        self.btn_pause.setCheckable(True)
        self.btn_pause.clicked.connect(self._toggle_pause)
        self.btn_pause.setEnabled(not self.is_offline)
        toolbar.addWidget(self.btn_pause)

        self.btn_clear = QPushButton("Очистить лог")
        self.btn_clear.clicked.connect(self._clear_logs)
        toolbar.addWidget(self.btn_clear)

        toolbar.addWidget(QLabel("Усиление:"))
        self.gain_slider = QSlider(Qt.Horizontal)
        self.gain_slider.setRange(0, 70)
        self.gain_slider.setValue(int(DEFAULT_GAIN))
        self.gain_slider.setMaximumWidth(200)
        self.gain_slider.setEnabled(self.has_sdr)
        self.gain_slider.valueChanged.connect(self._on_gain_changed)
        toolbar.addWidget(self.gain_slider)

        self.lbl_gain = QLabel(f"{int(DEFAULT_GAIN)} dB")
        toolbar.addWidget(self.lbl_gain)

        toolbar.addStretch()

        self.lbl_status = QLabel("Загрузка…")
        toolbar.addWidget(self.lbl_status)

        main_layout.addLayout(toolbar)

        # ─── Вкладки ────────────────────────────────────────────────────
        self.tabs = QTabWidget()

        self.tab_table = AcarsTableTab()
        self.tabs.addTab(self.tab_table, "Таблица сообщений")

        self.tab_raw = RawLogTab()
        self.tabs.addTab(self.tab_raw, "Raw log")

        self.tab_bytes = ByteLayoutTab()
        self.tabs.addTab(self.tab_bytes, "Байтовая раскладка")

        self.tab_stats = StatsTab()
        self.tabs.addTab(self.tab_stats, "Статистика бортов")

        self.tab_params = AcarsParamsTab()
        self.tabs.addTab(self.tab_params, "Параметры ACARS")

        self.tab_spectrum = SpectrumTab()
        self.tabs.addTab(self.tab_spectrum, "Спектр/активность")

        self.tab_map = MapTab()
        self.tabs.addTab(self.tab_map, "Карта")

        main_layout.addWidget(self.tabs)

        self.statusBar().showMessage("Готов")

    def _setup_refresh(self):
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._reload_logs)
        self._timer.start(REFRESH_INTERVAL_MS)

    def _toggle_pause(self):
        if not self.flowgraph:
            return
        self._paused = not self._paused
        if self._paused:
            self.flowgraph.stop()
            self.flowgraph.wait()
            self.btn_pause.setText("Возобновить")
            self._timer.stop()
            self.statusBar().showMessage("Приёмник приостановлен")
        else:
            self.flowgraph.start()
            self.btn_pause.setText("Пауза")
            self._timer.start(REFRESH_INTERVAL_MS)
            self.statusBar().showMessage("Приёмник возобновлён")

    def _on_gain_changed(self, value):
        self.lbl_gain.setText(f"{value} dB")
        if self.flowgraph and hasattr(self.flowgraph, "set_gain"):
            self.flowgraph.set_gain(float(value))

    def _clear_logs(self):
        """Архивирует текущие логи и очищает их."""
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        for path in self.log_paths:
            if os.path.isfile(path):
                archive = f"{path}.{ts}.bak"
                shutil.copy2(path, archive)
                with open(path, "w") as f:
                    f.truncate(0)
        self._reload_logs()
        self.statusBar().showMessage(
            f"Логи очищены, архив с меткой {ts}"
        )

    def _choose_log_files(self):
        paths = []
        for i, label in enumerate(CHANNEL_LABELS):
            path, _ = QFileDialog.getOpenFileName(
                self, f"Лог канала {label}", "",
                "Text files (*.txt *.log);;All files (*)",
            )
            if path:
                paths.append(path)
        if paths:
            self.log_paths = paths
            self._reload_logs()

    def _reload_logs(self):
        self._all_msgs = []
        self._msgs_by_channel = {}

        for i, path in enumerate(self.log_paths):
            ch_label = (
                CHANNEL_LABELS[i] if i < len(CHANNEL_LABELS)
                else f"Канал {i+1}"
            )
            msgs = load_log_file(path)
            for m in msgs:
                m["channel"] = ch_label
            self._all_msgs.extend(msgs)
            self._msgs_by_channel[ch_label] = msgs

        count = len(self._all_msgs)
        mode = "офлайн" if self.is_offline else "приём"
        self.lbl_status.setText(
            f"[{mode}] Сообщений: {count} | Файлов: {len(self.log_paths)}"
        )

        self.tab_table.set_messages(self._all_msgs)
        raw_text = "\n".join(m.get("raw", "") for m in self._all_msgs)
        self.tab_raw.set_content(raw_text)
        self.tab_bytes.set_messages(self._all_msgs)
        self.tab_stats.set_messages(self._all_msgs)
        self.tab_params.set_messages(self._all_msgs)
        self.tab_spectrum.set_messages(self._msgs_by_channel)
        self.tab_map.set_messages(self._all_msgs)

        map_idx = self.tabs.indexOf(self.tab_map)
        has_map = hasattr(self.tab_map, "has_data") and self.tab_map.has_data
        self.tabs.setTabEnabled(map_idx, has_map)

    def _export_log(self):
        if not self._all_msgs:
            QMessageBox.information(self, "Экспорт", "Нет данных для экспорта.")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Сохранить объединённый лог", "acars_export.txt",
            "Text files (*.txt);;All files (*)",
        )
        if path:
            with open(path, "w", encoding="utf-8") as f:
                for msg in self._all_msgs:
                    f.write(msg.get("raw", "") + "\n")
            self.statusBar().showMessage(f"Лог сохранён: {path}")

    def closeEvent(self, event):
        if self.flowgraph and not self._paused:
            self.flowgraph.stop()
            self.flowgraph.wait()
        event.accept()


# ─── CLI и точка входа ───────────────────────────────────────────────────────

def parse_host_port(s):
    """Разбирает 'host:port'."""
    parts = s.rsplit(":", 1)
    if len(parts) != 2:
        raise argparse.ArgumentTypeError(f"Ожидается HOST:PORT, получено: {s}")
    return parts[0], int(parts[1])


def ask_log_paths_gui(app):
    """Запрашивает пути к логам через GUI-диалог."""
    paths = []
    for i, label in enumerate(CHANNEL_LABELS):
        path, _ = QFileDialog.getOpenFileName(
            None, f"Лог канала {label}", "",
            "Text files (*.txt *.log);;All files (*)",
        )
        if path:
            paths.append(path)
    return paths if paths else list(DEFAULT_LOGS)


def main():
    parser = argparse.ArgumentParser(
        description="DragonOS ACARS Monitor — двухчастотный приёмник",
    )
    parser.add_argument(
        "--offline", action="store_true",
        help="Только просмотр логов, без SDR",
    )
    parser.add_argument(
        "--log", action="append", default=[],
        help="Путь к логу ACARS (можно несколько)",
    )
    parser.add_argument(
        "--udp-source", type=parse_host_port, action="append", default=[],
        help="Получать IQ по UDP HOST:PORT (оператор)",
    )
    parser.add_argument(
        "--forward-only", action="store_true",
        help="Форвардер SDR → UDP без декода и GUI (Pi)",
    )
    parser.add_argument(
        "--udp-dest", type=parse_host_port, action="append", default=[],
        help="Куда отправлять IQ HOST:PORT (форвардер)",
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

    log_paths = args.log if args.log else list(DEFAULT_LOGS)

    # ─── Режим 3: Форвардер (без GUI) ───────────────────────────────────
    if args.forward_only:
        if not HAS_GNURADIO:
            print("ОШИБКА: GNU Radio не найден. Установите gnuradio.", file=sys.stderr)
            sys.exit(1)

        udp_dests = args.udp_dest
        if not udp_dests:
            udp_dests = [("127.0.0.1", p) for p in DEFAULT_UDP_PORTS]
        if len(udp_dests) < 2:
            parser.error("Нужно указать два --udp-dest для форвардера")

        print(f"[FORWARDER] SDR → UDP, gain={args.gain}")
        for i, (h, p) in enumerate(udp_dests):
            print(f"  Канал {i+1}: {CHANNEL_FREQS[i]/1e6:.3f} MHz → {h}:{p}")

        tb = ForwarderFlowgraph(
            udp_dests, gain=args.gain, device=args.device,
        )

        def sig_handler(_signo, _frame):
            print("\n[FORWARDER] Остановка...")
            tb.stop()
            tb.wait()
            sys.exit(0)

        signal.signal(signal.SIGINT, sig_handler)
        signal.signal(signal.SIGTERM, sig_handler)

        tb.start()
        print("[FORWARDER] Запущен. Ctrl+C для остановки.")
        tb.wait()
        return

    # ─── GUI режимы ──────────────────────────────────────────────────────
    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    flowgraph = None
    is_offline = args.offline
    has_sdr = False

    if not is_offline and not args.udp_source:
        # Если нет логов — спросим через GUI
        if not args.log:
            log_paths = ask_log_paths_gui(app)

    # ─── Режим 1: Локальный SDR ─────────────────────────────────────────
    if not is_offline and not args.udp_source and HAS_GNURADIO:
        try:
            flowgraph = LocalReceiverFlowgraph(
                log_paths, gain=args.gain, device=args.device,
            )
            flowgraph.start()
            has_sdr = True
            print("[LOCAL] SDR приёмник запущен")
        except Exception as e:
            print(f"[LOCAL] Не удалось запустить SDR: {e}")
            print("[LOCAL] Переход в офлайн-режим")
            is_offline = True

    # ─── Режим 4: UDP приёмник ──────────────────────────────────────────
    elif not is_offline and args.udp_source and HAS_GNURADIO:
        udp_sources = args.udp_source
        if len(udp_sources) < 2:
            parser.error("Нужно указать два --udp-source")

        try:
            flowgraph = UdpReceiverFlowgraph(udp_sources, log_paths)
            flowgraph.start()
            print("[UDP] Приёмник UDP запущен")
        except Exception as e:
            print(f"[UDP] Ошибка: {e}")
            is_offline = True

    # ─── Режим 2: Офлайн ────────────────────────────────────────────────
    if is_offline:
        if not args.log:
            log_paths = ask_log_paths_gui(app)
        print(f"[OFFLINE] Просмотр логов: {log_paths}")

    window = AcarsMainWindow(
        log_paths=log_paths,
        flowgraph=flowgraph,
        is_offline=is_offline,
        has_sdr=has_sdr,
    )
    window.show()

    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
