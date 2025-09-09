import sys
from sensor_monitor import SensorMonitorApp
from PySide6.QtWidgets import QApplication


def main():
    """Launch the TES Sensor Monitor application"""
    app = QApplication(sys.argv)
    
    # Force the Fusion style to diagnose a potential platform-specific styling issue
    app.setStyle("Fusion")

    # Set application properties
    app.setApplicationName("TES Sensor Monitor")
    app.setApplicationVersion("1.0.0")
    
    window = SensorMonitorApp()
    window.show()
    
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
