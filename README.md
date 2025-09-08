# TES Sensor Monitor

A modern GUI application for monitoring sensors through NIDAQ using VISA interface.

## Features

- **Modern PySide6 GUI** with dark theme
- **VISA/NIDAQ Integration** for hardware communication
- **Dynamic Sensor Management** - Add/remove sensors at runtime
- **Real-time Plotting** with pyqtgraph for high performance
- **Adjustable Acquisition Frequency** from 0.1 Hz to 1000 Hz
- **Data Recording** with CSV export
- **Multi-sensor Support** with individual scaling and units

## Installation

1. Install dependencies:
```bash
pip install -e .
```

2. Run the application:
```bash
python main.py
```

## Usage

### Connecting to Hardware
1. Click "Refresh Resources" to scan for available VISA devices
2. Select your NIDAQ device from the dropdown
3. Click "Connect" to establish connection

### Adding Sensors
1. Enter sensor details in the "Sensor Management" section:
   - **Name**: Unique identifier for the sensor
   - **Channel**: Hardware channel (e.g., "ai0", "ai1")
   - **Command**: SCPI command for reading (optional)
   - **Unit**: Measurement unit (V, A, °C, etc.)
   - **Scale**: Multiplier for raw values
2. Click "Add Sensor"

### Data Acquisition
1. Set desired acquisition frequency in Hz
2. Click "Start Acquisition" to begin real-time monitoring
3. View live data in the real-time plot
4. Toggle "Start Recording" to save data points
5. Click "Save Data" to export recorded data to CSV

## Dependencies

- PySide6 >= 6.5.0 - Modern Qt GUI framework
- PyVISA >= 1.14.0 - VISA instrument control
- matplotlib >= 3.7.0 - Additional plotting support
- numpy >= 1.24.0 - Numerical computations
- pandas >= 2.0.0 - Data manipulation and export
- pyqtgraph >= 0.13.0 - High-performance real-time plotting

## Hardware Requirements

- NI-VISA Runtime installed
- Compatible NIDAQ hardware
- Proper VISA drivers for your instruments