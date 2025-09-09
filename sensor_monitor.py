import sys
import time
from datetime import datetime
from typing import Dict, List, Optional
import numpy as np
import pandas as pd
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QVBoxLayout, QHBoxLayout, QWidget,
    QSplitter, QGroupBox, QPushButton, QLabel, QSpinBox, QDoubleSpinBox,
    QComboBox, QLineEdit, QTableWidget, QTableWidgetItem, QTextEdit,
    QTabWidget, QFormLayout, QCheckBox, QProgressBar, QMessageBox
)
from PySide6.QtCore import QTimer, QThread, Signal, Qt
from PySide6.QtGui import QFont, QPalette, QColor
import pyvisa
import pyqtgraph as pg
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg
from matplotlib.figure import Figure
from PySide6.QtWidgets import QWidget, QLineEdit, QPushButton, QHBoxLayout, QVBoxLayout
from PySide6.QtGui import QDoubleValidator


class CustomDoubleSpinBox(QWidget):
    """
    A custom widget that mimics QDoubleSpinBox using a QLineEdit and two QPushButtons.
    This is a workaround for environments where QSpinBox arrows do not render correctly.
    """
    def __init__(self, parent=None):
        super().__init__(parent)

        self._min = -1e9
        self._max = 1e9
        self._decimals = 2
        self._step = 1.0
        self._value = 0.0

        self.line_edit = QLineEdit("0.0")
        self.line_edit.setValidator(QDoubleValidator(self))

        self.up_button = QPushButton("▲")
        self.down_button = QPushButton("▼")

        # Button styling and object names for targeting in stylesheet
        self.up_button.setFixedSize(22, 17)
        self.down_button.setFixedSize(22, 17)
        self.up_button.setObjectName("spinbox_button_up")
        self.down_button.setObjectName("spinbox_button_down")
        self.line_edit.setObjectName("spinbox_lineedit")
        self.setObjectName("custom_spinbox")

        # Layout for buttons
        button_layout = QVBoxLayout()
        button_layout.addWidget(self.up_button)
        button_layout.addWidget(self.down_button)
        button_layout.setSpacing(0)
        button_layout.setContentsMargins(0, 0, 0, 0)

        # Main layout
        main_layout = QHBoxLayout(self)
        main_layout.addWidget(self.line_edit)
        main_layout.addLayout(button_layout)
        main_layout.setSpacing(0)
        main_layout.setContentsMargins(0, 0, 0, 0)

        self.setLayout(main_layout)

        # Connections
        self.up_button.clicked.connect(self._increment)
        self.down_button.clicked.connect(self._decrement)
        self.line_edit.textChanged.connect(self._text_changed)

    def _update_text(self):
        format_str = f"{{:.{self._decimals}f}}"
        self.line_edit.blockSignals(True)
        self.line_edit.setText(format_str.format(self._value))
        self.line_edit.blockSignals(False)

    def _increment(self):
        self.setValue(self._value + self._step)

    def _decrement(self):
        self.setValue(self._value - self._step)

    def _text_changed(self, text):
        try:
            val = float(text)
            if self._min <= val <= self._max:
                self._value = val
        except ValueError:
            # Revert to last known good value if input is invalid (e.g., empty or non-numeric)
            self._update_text()

    # --- Public API to mimic QDoubleSpinBox ---
    def value(self) -> float:
        return self._value

    def setValue(self, val: float):
        self._value = max(self._min, min(self._max, val))
        self._update_text()

    def setRange(self, min_val: float, max_val: float):
        self._min = min_val
        self._max = max_val
        self.line_edit.setValidator(QDoubleValidator(min_val, max_val, self._decimals, self))
        self.setValue(self._value)

    def setDecimals(self, count: int):
        self._decimals = count
        self.line_edit.validator().setDecimals(count)
        self._update_text()

    def setSingleStep(self, step: float):
        self._step = step


class VISAManager:
    """Manages VISA connections and NIDAQ operations"""
    
    def __init__(self):
        self.rm = None
        self.instruments = {}
        self.connected_devices = {}
        
    def initialize(self):
        """Initialize VISA resource manager"""
        try:
            self.rm = pyvisa.ResourceManager()
            return True
        except Exception as e:
            print(f"Failed to initialize VISA: {e}")
            return False
    
    def list_resources(self):
        """List available VISA resources"""
        if not self.rm:
            return []
        try:
            return self.rm.list_resources()
        except Exception as e:
            print(f"Failed to list resources: {e}")
            return []
    
    def connect_device(self, resource_name: str):
        """Connect to a VISA device"""
        try:
            if resource_name not in self.connected_devices:
                instrument = self.rm.open_resource(resource_name)
                self.connected_devices[resource_name] = instrument
                return True
        except Exception as e:
            print(f"Failed to connect to {resource_name}: {e}")
        return False
    
    def disconnect_device(self, resource_name: str):
        """Disconnect from a VISA device"""
        if resource_name in self.connected_devices:
            try:
                self.connected_devices[resource_name].close()
                del self.connected_devices[resource_name]
                return True
            except Exception as e:
                print(f"Failed to disconnect from {resource_name}: {e}")
        return False
    
    def read_sensor(self, resource_name: str, command: str = None):
        """Read data from a sensor"""
        if resource_name in self.connected_devices:
            try:
                instrument = self.connected_devices[resource_name]
                if command:
                    return float(instrument.query(command).strip())
                else:
                    # For NIDAQ, simulate reading from analog input
                    return np.random.normal(0, 1)
            except Exception as e:
                print(f"Failed to read from {resource_name}: {e}")
                return None
        return None


class Sensor:
    """Represents a single sensor configuration"""
    
    def __init__(self, name: str, resource: str, channel: str = "", 
                 command: str = "", unit: str = "V", scale: float = 1.0, offset: float = 0.0):
        self.name = name
        self.resource = resource
        self.channel = channel
        self.command = command
        self.unit = unit
        self.scale = scale
        self.offset = offset
        self.enabled = True
        self.data = []
        self.timestamps = []
        self.max_points = 1000
    
    def add_data_point(self, value: float, timestamp: datetime = None):
        """Add a new data point"""
        if timestamp is None:
            timestamp = datetime.now()
        
        # Apply scale and offset transformation: processed_value = (raw_value * scale) + offset
        processed_value = (value * self.scale) + self.offset
        self.data.append(processed_value)
        self.timestamps.append(timestamp)
        
        # Keep only the most recent points
        if len(self.data) > self.max_points:
            self.data.pop(0)
            self.timestamps.pop(0)
    
    def get_latest_value(self):
        """Get the most recent sensor value"""
        return self.data[-1] if self.data else None


class DataAcquisitionThread(QThread):
    """Thread for continuous data acquisition"""
    
    data_ready = Signal(str, float, datetime)
    connection_error = Signal(str, str)
    
    def __init__(self, visa_manager: VISAManager, sensors: Dict[str, Sensor]):
        super().__init__()
        self.visa_manager = visa_manager
        self.sensors = sensors
        self.frequency = 1.0  # Hz
        self.running = False
    
    def set_frequency(self, frequency: float):
        """Set acquisition frequency in Hz"""
        self.frequency = max(0.1, frequency)
    
    def start_acquisition(self):
        """Start data acquisition"""
        self.running = True
        self.start()
    
    def stop_acquisition(self):
        """Stop data acquisition"""
        self.running = False
        self.wait()
    
    def run(self):
        """Main acquisition loop"""
        interval = 1.0 / self.frequency
        
        while self.running:
            timestamp = datetime.now()
            
            for sensor_name, sensor in self.sensors.items():
                if sensor.enabled:
                    try:
                        value = self.visa_manager.read_sensor(sensor.resource, sensor.command)
                        if value is not None:
                            self.data_ready.emit(sensor_name, value, timestamp)
                        else:
                            self.connection_error.emit(sensor_name, "Failed to read sensor")
                    except Exception as e:
                        self.connection_error.emit(sensor_name, str(e))
            
            self.msleep(int(interval * 1000))


class PlotWidget(QWidget):
    """Custom plot widget using pyqtgraph"""
    
    def __init__(self):
        super().__init__()
        self.layout = QVBoxLayout(self)
        self.plot_widget = pg.PlotWidget()
        self.plot_widget.setBackground('w')
        self.plot_widget.setLabel('left', 'Value', color='#495057', size='11pt')
        self.plot_widget.setLabel('bottom', 'Time (s)', color='#495057', size='11pt')
        self.plot_widget.showGrid(x=True, y=True, alpha=0.3)
        
        # Style the plot with light theme colors
        self.plot_widget.getAxis('left').setTextPen('#495057')
        self.plot_widget.getAxis('bottom').setTextPen('#495057')
        self.plot_widget.getAxis('left').setPen('#dee2e6')
        self.plot_widget.getAxis('bottom').setPen('#dee2e6')
        
        self.layout.addWidget(self.plot_widget)
        
        self.curves = {}
        # Use vibrant colors that work well on light background
        self.colors = ['#007bff', '#28a745', '#dc3545', '#fd7e14', '#6f42c1', '#20c997', '#17a2b8']
        self.color_index = 0
    
    def add_sensor_curve(self, sensor_name: str):
        """Add a curve for a new sensor"""
        color = self.colors[self.color_index % len(self.colors)]
        self.curves[sensor_name] = self.plot_widget.plot(
            pen=pg.mkPen(color, width=2),
            name=sensor_name
        )
        self.color_index += 1
    
    def remove_sensor_curve(self, sensor_name: str):
        """Remove a sensor curve"""
        if sensor_name in self.curves:
            self.plot_widget.removeItem(self.curves[sensor_name])
            del self.curves[sensor_name]
    
    def update_sensor_data(self, sensor_name: str, sensor: Sensor):
        """Update plot data for a sensor"""
        if sensor_name in self.curves and sensor.data:
            # Convert timestamps to seconds from start
            if len(sensor.timestamps) > 1:
                start_time = sensor.timestamps[0]
                x_data = [(ts - start_time).total_seconds() for ts in sensor.timestamps]
                self.curves[sensor_name].setData(x_data, sensor.data)


class SensorMonitorApp(QMainWindow):
    """Main application window"""
    
    def __init__(self):
        super().__init__()
        self.visa_manager = VISAManager()
        self.sensors = {}
        self.acquisition_thread = None
        self.recording_data = []
        self.recording = False
        
        self.init_ui()
        self.setup_connections()
        
        # Initialize VISA
        if not self.visa_manager.initialize():
            QMessageBox.warning(self, "VISA Error", "Failed to initialize VISA. Some features may not work.")
    
    def init_ui(self):
        """Initialize the user interface"""
        self.setWindowTitle("TES Sensor Monitor")
        self.setGeometry(100, 100, 1400, 800)
        
        # Apply modern light theme styling
        self.setStyleSheet("""
            QMainWindow {
                background-color: #ffffff;
                color: #000000;
            }
            QGroupBox {
                font-weight: bold;
                border: 2px solid #cccccc;
                border-radius: 5px;
                margin: 3px;
                padding-top: 10px;
                background-color: #f8f9fa;
                color: #333333;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px 0 5px;
                color: #2c3e50;
            }
            QPushButton {
                background-color: #007bff;
                border: 1px solid #007bff;
                color: white;
                padding: 8px 16px;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #0056b3;
                border-color: #0056b3;
            }
            QPushButton:pressed {
                background-color: #004085;
                border-color: #003d82;
            }
            QPushButton:disabled {
                background-color: #6c757d;
                border-color: #6c757d;
                color: #ffffff;
            }
            QLineEdit, QSpinBox, QComboBox {
                padding: 6px;
                border: 2px solid #ced4da;
                border-radius: 4px;
                background-color: #ffffff;
                color: #495057;
                selection-background-color: #007bff;
            }
            QLineEdit:focus, QSpinBox:focus, QComboBox:focus {
                border-color: #80bdff;
                outline: none;
            }
            QSpinBox::up-button, QDoubleSpinBox::up-button {
                subcontrol-origin: border;
                subcontrol-position: top right;
                width: 24px;
                height: 18px;
                border: 1px solid #ced4da;
                border-left-width: 1px;
                border-left-color: #ced4da;
                border-left-style: solid;
                border-top-left-radius: 0;
                border-bottom-left-radius: 0;
                border-top-right-radius: 4px;
                border-bottom-right-radius: 0;
                background-color: #f8f9fa;
            }
            QSpinBox::up-button:hover, QDoubleSpinBox::up-button:hover {
                background-color: #e9ecef;
            }
            QSpinBox::up-button:pressed, QDoubleSpinBox::up-button:pressed {
                background-color: #dee2e6;
            }
            QSpinBox::down-button, QDoubleSpinBox::down-button {
                subcontrol-origin: border;
                subcontrol-position: bottom right;
                width: 24px;
                height: 18px;
                border: 1px solid #ced4da;
                border-left-width: 1px;
                border-left-color: #ced4da;
                border-left-style: solid;
                border-top-left-radius: 0;
                border-bottom-left-radius: 0;
                border-top-right-radius: 0;
                border-bottom-right-radius: 4px;
                background-color: #f8f9fa;
            }
            QSpinBox::down-button:hover, QDoubleSpinBox::down-button:hover {
                background-color: #e9ecef;
            }
            QSpinBox::down-button:pressed, QDoubleSpinBox::down-button:pressed {
                background-color: #dee2e6;
            }
            QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {
                border-left: 6px solid transparent;
                border-right: 6px solid transparent;
                border-bottom: 8px solid #495057;
                width: 0px;
                height: 0px;
            }
            QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {
                border-left: 6px solid transparent;
                border-right: 6px solid transparent;
                border-top: 8px solid #495057;
                width: 0px;
                height: 0px;
            }
            QLabel {
                color: #495057;
            }
            QTableWidget {
                background-color: #ffffff;
                alternate-background-color: #f8f9fa;
                gridline-color: #dee2e6;
                color: #495057;
                border: 1px solid #dee2e6;
            }
            QTableWidget::item {
                padding: 8px;
                border-bottom: 1px solid #dee2e6;
            }
            QTableWidget::item:selected {
                background-color: #007bff;
                color: white;
            }
            QHeaderView::section {
                background-color: #e9ecef;
                color: #495057;
                border: 1px solid #dee2e6;
                padding: 6px;
                font-weight: bold;
            }
            QTextEdit {
                background-color: #ffffff;
                border: 2px solid #ced4da;
                border-radius: 4px;
                color: #495057;
                selection-background-color: #007bff;
            }
            QCheckBox {
                color: #495057;
            }
            QCheckBox::indicator {
                width: 18px;
                height: 18px;
                border: 2px solid #ced4da;
                border-radius: 3px;
                background-color: #ffffff;
            }
            QCheckBox::indicator:checked {
                background-color: #007bff;
                border-color: #007bff;
                image: url(data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iMTQiIGhlaWdodD0iMTQiIHZpZXdCb3g9IjAgMCAxNCAxNCIgZmlsbD0ibm9uZSIgeG1sbnM9Imh0dHA6Ly93d3cudzMub3JnLzIwMDAvc3ZnIj4KPHBhdGggZD0iTTExLjMzMzMgMy41TDUuMjUgOS41ODMzM0wyLjY2NjY3IDciIHN0cm9rZT0id2hpdGUiIHN0cm9rZS13aWR0aD0iMiIgc3Ryb2tlLWxpbmVjYXA9InJvdW5kIiBzdHJva2UtbGluZWpvaW49InJvdW5kIi8+Cjwvc3ZnPgo=);
            }

            /* Custom SpinBox Styling */
            QLineEdit#spinbox_lineedit {
                border: 2px solid #ced4da;
                border-right: none;
                border-top-left-radius: 4px;
                border-bottom-left-radius: 4px;
                padding: 6px;
                background-color: #ffffff;
            }

            QPushButton#spinbox_button_up, QPushButton#spinbox_button_down {
                background-color: #f8f9fa;
                border: 2px solid #ced4da;
                border-left: 1px solid #ced4da;
                padding: 0px 4px 0px 4px;
                font-size: 9px;
            }
            QPushButton#spinbox_button_up:hover, QPushButton#spinbox_button_down:hover {
                background-color: #e9ecef;
            }
            QPushButton#spinbox_button_up:pressed, QPushButton#spinbox_button_down:pressed {
                background-color: #dee2e6;
            }

            QPushButton#spinbox_button_up {
                border-bottom: none;
                border-top-right-radius: 4px;
            }

            QPushButton#spinbox_button_down {
                border-top-right-radius: 0px;
                border-bottom-right-radius: 4px;
            }
        """)
        
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # Main layout
        main_layout = QHBoxLayout(central_widget)
        
        # Create splitter for resizable panels
        splitter = QSplitter(Qt.Horizontal)
        main_layout.addWidget(splitter)
        
        # Left panel - Controls
        left_panel = self.create_control_panel()
        splitter.addWidget(left_panel)
        
        # Right panel - Plots and data
        right_panel = self.create_display_panel()
        splitter.addWidget(right_panel)
        
        # Set splitter proportions
        splitter.setSizes([400, 1000])
    
    def create_control_panel(self):
        """Create the control panel"""
        panel = QWidget()
        layout = QVBoxLayout(panel)
        
        # VISA Connection Group
        visa_group = QGroupBox("VISA Connection")
        visa_layout = QVBoxLayout(visa_group)
        
        self.resource_combo = QComboBox()
        self.refresh_resources_btn = QPushButton("Refresh Resources")
        self.connect_btn = QPushButton("Connect")
        
        visa_layout.addWidget(QLabel("Available Resources:"))
        visa_layout.addWidget(self.resource_combo)
        visa_layout.addWidget(self.refresh_resources_btn)
        visa_layout.addWidget(self.connect_btn)
        
        layout.addWidget(visa_group)
        
        # Sensor Management Group
        sensor_group = QGroupBox("Sensor Management")
        sensor_layout = QVBoxLayout(sensor_group)
        
        # Add sensor form
        form_layout = QFormLayout()
        self.sensor_name_edit = QLineEdit()
        self.sensor_channel_edit = QLineEdit()
        self.sensor_command_edit = QLineEdit()
        self.sensor_unit_edit = QLineEdit("V")
        self.sensor_scale_edit = CustomDoubleSpinBox()
        self.sensor_scale_edit.setRange(-1000, 1000)
        self.sensor_scale_edit.setValue(1.0)
        self.sensor_scale_edit.setDecimals(3)
        
        self.sensor_offset_edit = CustomDoubleSpinBox()
        self.sensor_offset_edit.setRange(-1000, 1000)
        self.sensor_offset_edit.setValue(0.0)
        self.sensor_offset_edit.setDecimals(3)
        
        form_layout.addRow("Name:", self.sensor_name_edit)
        form_layout.addRow("Channel:", self.sensor_channel_edit)
        form_layout.addRow("Command:", self.sensor_command_edit)
        form_layout.addRow("Unit:", self.sensor_unit_edit)
        form_layout.addRow("Scale:", self.sensor_scale_edit)
        form_layout.addRow("Offset:", self.sensor_offset_edit)
        
        sensor_layout.addLayout(form_layout)
        
        self.add_sensor_btn = QPushButton("Add Sensor")
        self.remove_sensor_btn = QPushButton("Remove Selected")
        
        sensor_layout.addWidget(self.add_sensor_btn)
        sensor_layout.addWidget(self.remove_sensor_btn)
        
        # Sensor list
        self.sensor_table = QTableWidget()
        self.sensor_table.setColumnCount(4)
        self.sensor_table.setHorizontalHeaderLabels(["Name", "Unit", "Value", "Enabled"])
        sensor_layout.addWidget(self.sensor_table)
        
        layout.addWidget(sensor_group)
        
        # Acquisition Control Group
        acq_group = QGroupBox("Data Acquisition")
        acq_layout = QVBoxLayout(acq_group)
        
        freq_layout = QHBoxLayout()
        freq_layout.addWidget(QLabel("Frequency (Hz):"))
        self.frequency_spinbox = CustomDoubleSpinBox()
        self.frequency_spinbox.setRange(0.1, 1000)
        self.frequency_spinbox.setValue(1.0)
        self.frequency_spinbox.setDecimals(1)
        self.frequency_spinbox.setSingleStep(0.1)
        freq_layout.addWidget(self.frequency_spinbox)
        acq_layout.addLayout(freq_layout)
        
        self.start_acq_btn = QPushButton("Start Acquisition")
        self.stop_acq_btn = QPushButton("Stop Acquisition")
        self.stop_acq_btn.setEnabled(False)
        
        acq_layout.addWidget(self.start_acq_btn)
        acq_layout.addWidget(self.stop_acq_btn)
        
        # Recording controls
        self.record_btn = QPushButton("Start Recording")
        self.save_data_btn = QPushButton("Save Data")
        self.save_data_btn.setEnabled(False)
        
        acq_layout.addWidget(self.record_btn)
        acq_layout.addWidget(self.save_data_btn)
        
        layout.addWidget(acq_group)
        
        # Status group
        status_group = QGroupBox("Status")
        status_layout = QVBoxLayout(status_group)
        
        self.status_text = QTextEdit()
        self.status_text.setMaximumHeight(100)
        self.status_text.setReadOnly(True)
        status_layout.addWidget(self.status_text)
        
        layout.addWidget(status_group)
        
        layout.addStretch()
        return panel
    
    def create_display_panel(self):
        """Create the display panel"""
        panel = QWidget()
        layout = QVBoxLayout(panel)
        
        # Tab widget for different views
        self.tab_widget = QTabWidget()
        
        # Real-time plot tab
        self.plot_widget = PlotWidget()
        self.tab_widget.addTab(self.plot_widget, "Real-time Plot")
        
        # Data table tab
        self.data_table = QTableWidget()
        self.tab_widget.addTab(self.data_table, "Data Table")
        
        layout.addWidget(self.tab_widget)
        
        return panel
    
    def setup_connections(self):
        """Setup signal-slot connections"""
        self.refresh_resources_btn.clicked.connect(self.refresh_resources)
        self.connect_btn.clicked.connect(self.connect_device)
        self.add_sensor_btn.clicked.connect(self.add_sensor)
        self.remove_sensor_btn.clicked.connect(self.remove_sensor)
        self.start_acq_btn.clicked.connect(self.start_acquisition)
        self.stop_acq_btn.clicked.connect(self.stop_acquisition)
        self.record_btn.clicked.connect(self.toggle_recording)
        self.save_data_btn.clicked.connect(self.save_data)
        
        # Initialize resources
        self.refresh_resources()
    
    def refresh_resources(self):
        """Refresh available VISA resources"""
        self.resource_combo.clear()
        resources = self.visa_manager.list_resources()
        self.resource_combo.addItems(resources)
        self.log_message(f"Found {len(resources)} VISA resources")
    
    def connect_device(self):
        """Connect to selected VISA device"""
        resource = self.resource_combo.currentText()
        if resource:
            if self.visa_manager.connect_device(resource):
                self.log_message(f"Connected to {resource}")
                self.connect_btn.setText("Disconnect")
            else:
                self.log_message(f"Failed to connect to {resource}")
    
    def add_sensor(self):
        """Add a new sensor"""
        name = self.sensor_name_edit.text().strip()
        if not name:
            QMessageBox.warning(self, "Error", "Please enter a sensor name")
            return
        
        if name in self.sensors:
            QMessageBox.warning(self, "Error", "Sensor name already exists")
            return
        
        resource = self.resource_combo.currentText()
        channel = self.sensor_channel_edit.text().strip()
        command = self.sensor_command_edit.text().strip()
        unit = self.sensor_unit_edit.text().strip()
        scale = self.sensor_scale_edit.value()
        offset = self.sensor_offset_edit.value()
        
        sensor = Sensor(name, resource, channel, command, unit, scale, offset)
        self.sensors[name] = sensor
        
        # Add to table
        row = self.sensor_table.rowCount()
        self.sensor_table.insertRow(row)
        self.sensor_table.setItem(row, 0, QTableWidgetItem(name))
        self.sensor_table.setItem(row, 1, QTableWidgetItem(unit))
        self.sensor_table.setItem(row, 2, QTableWidgetItem("--"))
        
        # Add checkbox for enabled/disabled
        checkbox = QCheckBox()
        checkbox.setChecked(True)
        self.sensor_table.setCellWidget(row, 3, checkbox)
        
        # Add to plot
        self.plot_widget.add_sensor_curve(name)
        
        # Clear form
        self.sensor_name_edit.clear()
        self.sensor_channel_edit.clear()
        self.sensor_command_edit.clear()
        
        self.log_message(f"Added sensor: {name}")
    
    def remove_sensor(self):
        """Remove selected sensor"""
        current_row = self.sensor_table.currentRow()
        if current_row >= 0:
            sensor_name = self.sensor_table.item(current_row, 0).text()
            
            # Remove from sensors dict
            if sensor_name in self.sensors:
                del self.sensors[sensor_name]
            
            # Remove from plot
            self.plot_widget.remove_sensor_curve(sensor_name)
            
            # Remove from table
            self.sensor_table.removeRow(current_row)
            
            self.log_message(f"Removed sensor: {sensor_name}")
    
    def start_acquisition(self):
        """Start data acquisition"""
        if not self.sensors:
            QMessageBox.warning(self, "Error", "No sensors configured")
            return
        
        frequency = self.frequency_spinbox.value()
        
        self.acquisition_thread = DataAcquisitionThread(self.visa_manager, self.sensors)
        self.acquisition_thread.set_frequency(frequency)
        self.acquisition_thread.data_ready.connect(self.on_data_received)
        self.acquisition_thread.connection_error.connect(self.on_connection_error)
        
        self.acquisition_thread.start_acquisition()
        
        self.start_acq_btn.setEnabled(False)
        self.stop_acq_btn.setEnabled(True)
        
        self.log_message(f"Started data acquisition at {frequency} Hz")
    
    def stop_acquisition(self):
        """Stop data acquisition"""
        if self.acquisition_thread:
            self.acquisition_thread.stop_acquisition()
            self.acquisition_thread = None
        
        self.start_acq_btn.setEnabled(True)
        self.stop_acq_btn.setEnabled(False)
        
        self.log_message("Stopped data acquisition")
    
    def on_data_received(self, sensor_name: str, value: float, timestamp: datetime):
        """Handle new data from sensors"""
        if sensor_name in self.sensors:
            sensor = self.sensors[sensor_name]
            sensor.add_data_point(value, timestamp)
            
            # Update table
            for row in range(self.sensor_table.rowCount()):
                if self.sensor_table.item(row, 0).text() == sensor_name:
                    self.sensor_table.setItem(row, 2, QTableWidgetItem(f"{value:.3f}"))
                    break
            
            # Update plot
            self.plot_widget.update_sensor_data(sensor_name, sensor)
            
            # Record data if recording
            if self.recording:
                self.recording_data.append({
                    'timestamp': timestamp,
                    'sensor': sensor_name,
                    'value': value,
                    'unit': sensor.unit
                })
    
    def on_connection_error(self, sensor_name: str, error_msg: str):
        """Handle connection errors"""
        self.log_message(f"Error reading {sensor_name}: {error_msg}")
    
    def toggle_recording(self):
        """Toggle data recording"""
        if not self.recording:
            self.recording = True
            self.recording_data = []
            self.record_btn.setText("Stop Recording")
            self.save_data_btn.setEnabled(False)
            self.log_message("Started recording data")
        else:
            self.recording = False
            self.record_btn.setText("Start Recording")
            self.save_data_btn.setEnabled(True)
            self.log_message(f"Stopped recording. {len(self.recording_data)} data points recorded")
    
    def save_data(self):
        """Save recorded data to CSV"""
        if not self.recording_data:
            QMessageBox.warning(self, "Error", "No data to save")
            return
        
        # Convert to DataFrame
        df = pd.DataFrame(self.recording_data)
        
        # Save to CSV with timestamp in filename
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"sensor_data_{timestamp}.csv"
        
        try:
            df.to_csv(filename, index=False)
            self.log_message(f"Data saved to {filename}")
            QMessageBox.information(self, "Success", f"Data saved to {filename}")
        except Exception as e:
            self.log_message(f"Failed to save data: {e}")
            QMessageBox.critical(self, "Error", f"Failed to save data: {e}")
    
    def log_message(self, message: str):
        """Add message to status log"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.status_text.append(f"[{timestamp}] {message}")
        self.status_text.verticalScrollBar().setValue(
            self.status_text.verticalScrollBar().maximum()
        )
    
    def closeEvent(self, event):
        """Handle application close"""
        if self.acquisition_thread:
            self.acquisition_thread.stop_acquisition()
        
        # Close all VISA connections
        for resource_name in list(self.visa_manager.connected_devices.keys()):
            self.visa_manager.disconnect_device(resource_name)
        
        event.accept()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    
    # Set application properties
    app.setApplicationName("TES Sensor Monitor")
    app.setApplicationVersion("1.0.0")
    
    window = SensorMonitorApp()
    window.show()
    
    sys.exit(app.exec())