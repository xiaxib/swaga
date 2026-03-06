#!/usr/bin/env python3
"""
acars_gui.py — автономный GUI-просмотрщик логов ACARS.

Парсит файлы логов ACARS, показывает таблицу сообщений, raw-лог, байтовую
раскладку, статистику бортов, параметры ACARS, карту (при наличии координат)
и графики активности/спектра.

Использование:
    python3 acars_gui.py --log /path/log1.txt --log /path/log2.txt
"""

import argparse
import os
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QTabWidget, QTableWidget, QTableWidgetItem, QTextEdit, QPushButton,
    QLabel, QFileDialog, QSplitter, QHeaderView, QGroupBox, QGridLayout,
    QMessageBox, QStatusBar,
)
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QFont, QColor

try:
    import matplotlib
    matplotlib.use("Qt5Agg")
    from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
    from matplotlib.figure import Figure
    HAS_MATPLOTLIB = True
except ImportError:
    HAS_MATPLOTLIB = False

try:
    import cartopy.crs as ccrs
    import cartopy.feature as cfeature
    HAS_CARTOPY = True
except ImportError:
    HAS_CARTOPY = False


# ─── Параметры ───────────────────────────────────────────────────────────────
CHANNEL_LABELS = ["131.725 MHz", "131.825 MHz"]
DEFAULT_LOGS = [
    "/tmp/log_acars_131_725.txt",
    "/tmp/log_acars_131_825.txt",
]
REFRESH_INTERVAL_MS = 5000

# Регулярные выражения для парсинга ACARS
# Типичный формат лога: временная метка + поля ACARS
RE_ACARS_MSG = re.compile(
    r"(?P<timestamp>\d{4}[-/]\d{2}[-/]\d{2}\s+\d{2}:\d{2}:\d{2})?\s*"
    r"(?:REG:\s*(?P<reg>[.\w-]+))?\s*"
    r"(?:FLIGHT:\s*(?P<flight>[.\w-]+))?\s*"
    r"(?:LABEL:\s*(?P<label>[.\w]+))?\s*"
    r"(?:BLK:\s*(?P<block_id>[.\w]))?\s*"
    r"(?:ACK:\s*(?P<ack>[.\w!]))?\s*"
    r"(?:MODE:\s*(?P<mode>[.\w]))?\s*"
    r"(?:MSG:\s*(?P<text>.+))?",
    re.IGNORECASE,
)

RE_COORDS = re.compile(
    r"(?P<lat>[NS])\s*(?P<lat_deg>\d{2,3})(?P<lat_min>\d{2}\.\d+)\s*"
    r"(?P<lon>[EW])\s*(?P<lon_deg>\d{2,3})(?P<lon_min>\d{2}\.\d+)",
)


def parse_acars_line(line):
    """Парсит одну строку лога ACARS в словарь полей."""
    line = line.strip()
    if not line:
        return None

    m = RE_ACARS_MSG.match(line)
    if not m:
        return {"raw": line, "timestamp": "", "reg": "", "flight": "",
                "label": "", "block_id": "", "ack": "", "mode": "", "text": line}

    d = m.groupdict()
    for k, v in d.items():
        if v is None:
            d[k] = ""
    d["raw"] = line
    return d


def extract_coords(text):
    """Извлекает координаты из текста ACARS-сообщения."""
    m = RE_COORDS.search(text)
    if not m:
        return None
    lat = float(m.group("lat_deg")) + float(m.group("lat_min")) / 60.0
    if m.group("lat") == "S":
        lat = -lat
    lon = float(m.group("lon_deg")) + float(m.group("lon_min")) / 60.0
    if m.group("lon") == "W":
        lon = -lon
    return lat, lon


def load_log_file(path):
    """Читает лог-файл и возвращает список распарсенных сообщений."""
    msgs = []
    if not os.path.isfile(path):
        return msgs
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            parsed = parse_acars_line(line)
            if parsed:
                msgs.append(parsed)
    return msgs


class AcarsTableTab(QWidget):
    """Вкладка «Таблица сообщений»."""

    COLUMNS = [
        ("Время", "timestamp"),
        ("Борт", "reg"),
        ("Рейс", "flight"),
        ("Label", "label"),
        ("Blk", "block_id"),
        ("Ack", "ack"),
        ("Mode", "mode"),
        ("Сообщение", "text"),
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)

        self.filter_label = QLabel("Фильтр:")
        self.filter_inputs = {}
        filter_layout = QHBoxLayout()
        for title, key in self.COLUMNS[:4]:
            lbl = QLabel(f"{title}:")
            from PyQt5.QtWidgets import QLineEdit
            inp = QLineEdit()
            inp.setMaximumWidth(120)
            inp.setPlaceholderText(title)
            inp.textChanged.connect(self._apply_filter)
            filter_layout.addWidget(lbl)
            filter_layout.addWidget(inp)
            self.filter_inputs[key] = inp
        filter_layout.addStretch()
        layout.addLayout(filter_layout)

        self.table = QTableWidget()
        self.table.setColumnCount(len(self.COLUMNS))
        self.table.setHorizontalHeaderLabels([c[0] for c in self.COLUMNS])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setAlternatingRowColors(True)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        layout.addWidget(self.table)

        self._all_msgs = []

    def set_messages(self, msgs):
        self._all_msgs = msgs
        self._apply_filter()

    def _apply_filter(self):
        filters = {k: v.text().strip().lower() for k, v in self.filter_inputs.items()}
        filtered = []
        for msg in self._all_msgs:
            match = True
            for key, pattern in filters.items():
                if pattern and pattern not in msg.get(key, "").lower():
                    match = False
                    break
            if match:
                filtered.append(msg)

        self.table.setRowCount(len(filtered))
        for row, msg in enumerate(filtered):
            for col, (_, key) in enumerate(self.COLUMNS):
                item = QTableWidgetItem(msg.get(key, ""))
                self.table.setItem(row, col, item)


class RawLogTab(QWidget):
    """Вкладка «Raw log»."""

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        self.text_edit = QTextEdit()
        self.text_edit.setReadOnly(True)
        self.text_edit.setFont(QFont("Courier", 10))
        layout.addWidget(self.text_edit)

    def set_content(self, text):
        self.text_edit.setPlainText(text)


class ByteLayoutTab(QWidget):
    """Вкладка «Байтовая раскладка» — hex-дамп raw-сообщений."""

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        self.text_edit = QTextEdit()
        self.text_edit.setReadOnly(True)
        self.text_edit.setFont(QFont("Courier", 10))
        layout.addWidget(self.text_edit)

    def set_messages(self, msgs):
        lines = []
        for msg in msgs:
            raw = msg.get("raw", "")
            hex_str = " ".join(f"{ord(c):02X}" for c in raw)
            ascii_str = "".join(c if 32 <= ord(c) < 127 else "." for c in raw)
            lines.append(f"HEX: {hex_str}")
            lines.append(f"ASC: {ascii_str}")
            lines.append("")
        self.text_edit.setPlainText("\n".join(lines))


class StatsTab(QWidget):
    """Вкладка «Статистика бортов»."""

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        self.table = QTableWidget()
        self.table.setColumnCount(3)
        self.table.setHorizontalHeaderLabels(["Борт", "Сообщений", "Последнее"])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setAlternatingRowColors(True)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        layout.addWidget(self.table)

    def set_messages(self, msgs):
        reg_counter = Counter()
        reg_last = {}
        for msg in msgs:
            reg = msg.get("reg", "").strip()
            if not reg:
                continue
            reg_counter[reg] += 1
            ts = msg.get("timestamp", "")
            if ts:
                reg_last[reg] = ts

        sorted_regs = reg_counter.most_common()
        self.table.setRowCount(len(sorted_regs))
        for row, (reg, count) in enumerate(sorted_regs):
            self.table.setItem(row, 0, QTableWidgetItem(reg))
            self.table.setItem(row, 1, QTableWidgetItem(str(count)))
            self.table.setItem(row, 2, QTableWidgetItem(reg_last.get(reg, "")))


class AcarsParamsTab(QWidget):
    """Вкладка «Параметры ACARS» — сводка label/mode."""

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)

        self.label_table = QTableWidget()
        self.label_table.setColumnCount(2)
        self.label_table.setHorizontalHeaderLabels(["Label", "Кол-во"])
        self.label_table.horizontalHeader().setStretchLastSection(True)
        self.label_table.setEditTriggers(QTableWidget.NoEditTriggers)

        self.mode_table = QTableWidget()
        self.mode_table.setColumnCount(2)
        self.mode_table.setHorizontalHeaderLabels(["Mode", "Кол-во"])
        self.mode_table.horizontalHeader().setStretchLastSection(True)
        self.mode_table.setEditTriggers(QTableWidget.NoEditTriggers)

        splitter = QSplitter(Qt.Horizontal)
        w1 = QWidget()
        l1 = QVBoxLayout(w1)
        l1.addWidget(QLabel("Распределение Label:"))
        l1.addWidget(self.label_table)
        splitter.addWidget(w1)

        w2 = QWidget()
        l2 = QVBoxLayout(w2)
        l2.addWidget(QLabel("Распределение Mode:"))
        l2.addWidget(self.mode_table)
        splitter.addWidget(w2)

        layout.addWidget(splitter)

    def set_messages(self, msgs):
        label_cnt = Counter(m.get("label", "") for m in msgs if m.get("label"))
        mode_cnt = Counter(m.get("mode", "") for m in msgs if m.get("mode"))

        self._fill_table(self.label_table, label_cnt)
        self._fill_table(self.mode_table, mode_cnt)

    def _fill_table(self, table, counter):
        items = counter.most_common()
        table.setRowCount(len(items))
        for row, (key, count) in enumerate(items):
            table.setItem(row, 0, QTableWidgetItem(key))
            table.setItem(row, 1, QTableWidgetItem(str(count)))


class SpectrumTab(QWidget):
    """Вкладка «Спектр/активность каналов» — графики matplotlib."""

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)

        if not HAS_MATPLOTLIB:
            layout.addWidget(QLabel(
                "Matplotlib не установлен.\n"
                "pip install matplotlib"
            ))
            self.canvas = None
            return

        self.figure = Figure(figsize=(8, 4))
        self.canvas = FigureCanvas(self.figure)
        layout.addWidget(self.canvas)

    def set_messages(self, msgs_by_channel):
        if not self.canvas:
            return

        self.figure.clear()

        ax1 = self.figure.add_subplot(1, 2, 1)
        ax1.set_title("Сообщений по каналам")
        labels = []
        counts = []
        for ch_label, msgs in msgs_by_channel.items():
            labels.append(ch_label)
            counts.append(len(msgs))
        ax1.bar(labels, counts, color=["#4a90d9", "#d94a4a"])
        ax1.set_ylabel("Кол-во")

        ax2 = self.figure.add_subplot(1, 2, 2)
        ax2.set_title("Активность по времени")
        for ch_label, msgs in msgs_by_channel.items():
            timestamps = []
            for m in msgs:
                ts = m.get("timestamp", "")
                if ts:
                    try:
                        dt = datetime.strptime(ts, "%Y-%m-%d %H:%M:%S")
                        timestamps.append(dt)
                    except ValueError:
                        try:
                            dt = datetime.strptime(ts, "%Y/%m/%d %H:%M:%S")
                            timestamps.append(dt)
                        except ValueError:
                            pass
            if timestamps:
                timestamps.sort()
                hours = [t.hour + t.minute / 60 for t in timestamps]
                ax2.hist(hours, bins=24, alpha=0.6, label=ch_label)
        ax2.set_xlabel("Час (UTC)")
        ax2.set_ylabel("Кол-во")
        ax2.legend()

        self.figure.tight_layout()
        self.canvas.draw()


class MapTab(QWidget):
    """Вкладка «Карта» — позиции бортов (Cartopy)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)

        if not HAS_MATPLOTLIB or not HAS_CARTOPY:
            missing = []
            if not HAS_MATPLOTLIB:
                missing.append("matplotlib")
            if not HAS_CARTOPY:
                missing.append("cartopy")
            layout.addWidget(QLabel(
                f"Для карты установите: pip install {' '.join(missing)}"
            ))
            self.canvas = None
            return

        self.figure = Figure(figsize=(8, 6))
        self.canvas = FigureCanvas(self.figure)
        layout.addWidget(self.canvas)
        self._has_data = False

    @property
    def has_data(self):
        return self._has_data

    def set_messages(self, msgs):
        if not self.canvas:
            return

        coords_by_reg = defaultdict(list)
        for msg in msgs:
            text = msg.get("text", "") + " " + msg.get("raw", "")
            coord = extract_coords(text)
            if coord:
                reg = msg.get("reg", "???")
                coords_by_reg[reg].append(coord)

        self._has_data = bool(coords_by_reg)
        if not coords_by_reg:
            return

        self.figure.clear()
        ax = self.figure.add_subplot(1, 1, 1, projection=ccrs.PlateCarree())
        ax.add_feature(cfeature.LAND, facecolor="#e0e0e0")
        ax.add_feature(cfeature.OCEAN, facecolor="#c6e2ff")
        ax.add_feature(cfeature.COASTLINE, linewidth=0.5)
        ax.add_feature(cfeature.BORDERS, linewidth=0.3, linestyle=":")
        ax.gridlines(draw_labels=True, linewidth=0.3)

        for reg, points in coords_by_reg.items():
            lats = [p[0] for p in points]
            lons = [p[1] for p in points]
            ax.plot(lons, lats, "o-", markersize=4, label=reg,
                    transform=ccrs.PlateCarree())

        ax.legend(loc="upper left", fontsize=8)
        ax.set_title("Позиции бортов (ACARS)")
        self.figure.tight_layout()
        self.canvas.draw()


class AcarsLogViewer(QMainWindow):
    """Главное окно автономного просмотрщика логов ACARS."""

    def __init__(self, log_paths=None):
        super().__init__()
        self.setWindowTitle("ACARS Log Viewer")
        self.setMinimumSize(1000, 700)

        self.log_paths = list(log_paths or [])
        self._all_msgs = []
        self._msgs_by_channel = {}

        self._build_ui()
        self._setup_refresh()

        if self.log_paths:
            self._reload_logs()
        else:
            self._ask_log_files()

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)

        # Панель управления
        toolbar = QHBoxLayout()
        self.lbl_status = QLabel("Загрузка…")
        toolbar.addWidget(self.lbl_status)
        toolbar.addStretch()

        btn_choose = QPushButton("Файл лога…")
        btn_choose.clicked.connect(self._ask_log_files)
        toolbar.addWidget(btn_choose)

        btn_export = QPushButton("Выгрузить лог")
        btn_export.clicked.connect(self._export_log)
        toolbar.addWidget(btn_export)

        btn_refresh = QPushButton("Обновить")
        btn_refresh.clicked.connect(self._reload_logs)
        toolbar.addWidget(btn_refresh)

        main_layout.addLayout(toolbar)

        # Вкладки
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
        self._auto_refresh = True
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._reload_logs)
        self._timer.start(REFRESH_INTERVAL_MS)

    def _ask_log_files(self):
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
            ch_label = CHANNEL_LABELS[i] if i < len(CHANNEL_LABELS) else f"Канал {i+1}"
            msgs = load_log_file(path)
            for m in msgs:
                m["channel"] = ch_label
            self._all_msgs.extend(msgs)
            self._msgs_by_channel[ch_label] = msgs

        count = len(self._all_msgs)
        self.lbl_status.setText(
            f"Сообщений: {count} | Файлов: {len(self.log_paths)}"
        )
        self.statusBar().showMessage(
            f"Загружено {count} сообщений из {len(self.log_paths)} файлов"
        )

        # Обновляем вкладки
        self.tab_table.set_messages(self._all_msgs)
        raw_text = "\n".join(m.get("raw", "") for m in self._all_msgs)
        self.tab_raw.set_content(raw_text)
        self.tab_bytes.set_messages(self._all_msgs)
        self.tab_stats.set_messages(self._all_msgs)
        self.tab_params.set_messages(self._all_msgs)
        self.tab_spectrum.set_messages(self._msgs_by_channel)
        self.tab_map.set_messages(self._all_msgs)

        # Активируем вкладку карты если есть данные
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


def main():
    parser = argparse.ArgumentParser(
        description="ACARS Log Viewer — автономный просмотрщик логов",
    )
    parser.add_argument(
        "--log", action="append", default=[],
        help="Путь к файлу лога ACARS (можно несколько)",
    )
    args = parser.parse_args()

    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    viewer = AcarsLogViewer(log_paths=args.log if args.log else None)
    viewer.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
