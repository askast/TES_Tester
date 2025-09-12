import asyncio
import time
import socket
import sqlite3
import json
from datetime import datetime
from typing import Dict, List, Optional, Union
import numpy as np
import pandas as pd
import pyvisa
from nicegui import ui, app, run
from nicegui.events import ValueChangeEventArguments


class EthernetSCPIDevice:
    """Handles SCPI communication over Ethernet TCP/IP"""
    
    def __init__(self, ip_address: str, port: int = 5025, timeout: float = 5.0):
        self.ip_address = ip_address
        self.port = port
        self.timeout = timeout
        self.socket = None
        self.connected = False
    
    def connect(self):
        """Connect to the device via TCP/IP"""
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.settimeout(self.timeout)
            self.socket.connect((self.ip_address, self.port))
            self.connected = True
            return True
        except Exception as e:
            print(f"Failed to connect to {self.ip_address}:{self.port}: {e}")
            self.connected = False
            return False
    
    def disconnect(self):
        """Disconnect from the device"""
        try:
            if self.socket:
                self.socket.close()
            self.connected = False
            return True
        except Exception as e:
            print(f"Error disconnecting from {self.ip_address}: {e}")
            return False
    
    def send_command(self, command: str):
        """Send a SCPI command to the device"""
        if not self.connected or not self.socket:
            raise ConnectionError("Device not connected")
        
        try:
            # Ensure command ends with newline
            if not command.endswith('\n'):
                command += '\n'
            self.socket.send(command.encode('utf-8'))
            return True
        except Exception as e:
            print(f"Error sending command '{command.strip()}': {e}")
            return False
    
    def query(self, command: str) -> str:
        """Send a query command and read the response"""
        if not self.connected or not self.socket:
            raise ConnectionError("Device not connected")
        
        try:
            # Send the command
            if not self.send_command(command):
                return ""
            
            # Read the response
            response = b""
            while True:
                chunk = self.socket.recv(1024)
                if not chunk:
                    break
                response += chunk
                if b'\n' in chunk or len(chunk) < 1024:
                    break
            
            return response.decode('utf-8').strip()
        except Exception as e:
            print(f"Error querying command '{command.strip()}': {e}")
            return ""
    
    def read_float(self, command: str) -> Optional[float]:
        """Query a command and return the result as a float"""
        try:
            response = self.query(command)
            if response:
                return float(response)
            return None
        except ValueError as e:
            print(f"Error converting response to float: {e}")
            return None


class EthernetManager:
    """Manages Ethernet SCPI device connections"""
    
    def __init__(self):
        self.connected_devices = {}  # ip:port -> EthernetSCPIDevice
    
    def connect_device(self, ip_address: str, port: int = 5025) -> bool:
        """Connect to an Ethernet SCPI device"""
        device_key = f"{ip_address}:{port}"
        
        if device_key in self.connected_devices:
            return True  # Already connected
        
        device = EthernetSCPIDevice(ip_address, port)
        if device.connect():
            self.connected_devices[device_key] = device
            return True
        return False
    
    def disconnect_device(self, ip_address: str, port: int = 5025) -> bool:
        """Disconnect from an Ethernet SCPI device"""
        device_key = f"{ip_address}:{port}"
        
        if device_key in self.connected_devices:
            device = self.connected_devices[device_key]
            if device.disconnect():
                del self.connected_devices[device_key]
                return True
        return False
    
    def get_device(self, ip_address: str, port: int = 5025) -> Optional[EthernetSCPIDevice]:
        """Get a connected device instance"""
        device_key = f"{ip_address}:{port}"
        return self.connected_devices.get(device_key)
    
    def read_sensor(self, ip_address: str, command: str, port: int = 5025) -> Optional[float]:
        """Read data from an Ethernet SCPI device"""
        device = self.get_device(ip_address, port)
        if device and device.connected:
            return device.read_float(command)
        return None


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
            return list(self.rm.list_resources())
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


class DeviceManager:
    """Unified manager for all device types (VISA and Ethernet)"""
    
    def __init__(self):
        self.visa_manager = VISAManager()
        self.ethernet_manager = EthernetManager()
        self.connected_devices = {}  # device_id -> {'type': 'VISA'/'Ethernet', 'details': {...}}
        
        # Initialize VISA
        self.visa_manager.initialize()
    
    def get_device_id(self, connection_type: str, resource: str, ip_address: str = "", port: int = 5025) -> str:
        """Generate a unique device ID"""
        if connection_type == "VISA":
            return f"VISA:{resource}"
        elif connection_type == "Ethernet":
            return f"Ethernet:{ip_address}:{port}"
        else:
            raise ValueError(f"Unknown connection type: {connection_type}")
    
    def connect_device(self, connection_type: str, resource: str = "", ip_address: str = "", port: int = 5025, **kwargs) -> tuple[bool, str]:
        """Connect to a device and return (success, device_id)"""
        try:
            if connection_type == "VISA":
                if not resource:
                    return False, "Resource name required for VISA connection"
                
                success = self.visa_manager.connect_device(resource)
                if success:
                    device_id = self.get_device_id(connection_type, resource)
                    self.connected_devices[device_id] = {
                        'type': 'VISA',
                        'details': {'resource': resource},
                        'display_name': resource
                    }
                    return True, device_id
                return False, f"Failed to connect to VISA device {resource}"
                
            elif connection_type == "Ethernet":
                if not ip_address:
                    return False, "IP address required for Ethernet connection"
                
                success = self.ethernet_manager.connect_device(ip_address, port)
                if success:
                    device_id = self.get_device_id(connection_type, resource, ip_address, port)
                    self.connected_devices[device_id] = {
                        'type': 'Ethernet',
                        'details': {'ip_address': ip_address, 'port': port},
                        'display_name': f"{ip_address}:{port}"
                    }
                    return True, device_id
                return False, f"Failed to connect to Ethernet device {ip_address}:{port}"
            else:
                return False, f"Unknown connection type: {connection_type}"
                
        except Exception as e:
            return False, f"Connection error: {str(e)}"
    
    def disconnect_device(self, device_id: str) -> bool:
        """Disconnect a device by its ID"""
        if device_id not in self.connected_devices:
            return False
        
        try:
            device_info = self.connected_devices[device_id]
            
            if device_info['type'] == 'VISA':
                resource = device_info['details']['resource']
                success = self.visa_manager.disconnect_device(resource)
            elif device_info['type'] == 'Ethernet':
                ip_address = device_info['details']['ip_address']
                port = device_info['details']['port']
                success = self.ethernet_manager.disconnect_device(ip_address, port)
            else:
                return False
            
            if success:
                del self.connected_devices[device_id]
            return success
            
        except Exception as e:
            print(f"Error disconnecting device {device_id}: {e}")
            return False
    
    def disconnect_all_devices(self):
        """Disconnect all connected devices"""
        device_ids = list(self.connected_devices.keys())
        for device_id in device_ids:
            self.disconnect_device(device_id)
    
    def get_connected_devices(self) -> Dict[str, Dict]:
        """Get list of all connected devices"""
        return self.connected_devices.copy()
    
    def read_sensor_data(self, device_id: str, command: str = None) -> Optional[float]:
        """Read data from a sensor on the specified device"""
        if device_id not in self.connected_devices:
            return None
        
        try:
            device_info = self.connected_devices[device_id]
            
            if device_info['type'] == 'VISA':
                resource = device_info['details']['resource']
                return self.visa_manager.read_sensor(resource, command)
            elif device_info['type'] == 'Ethernet':
                ip_address = device_info['details']['ip_address']
                port = device_info['details']['port']
                return self.ethernet_manager.read_sensor(ip_address, command, port)
            
        except Exception as e:
            print(f"Error reading from device {device_id}: {e}")
        
        return None
    
    def list_visa_resources(self) -> List[str]:
        """Get list of available VISA resources"""
        return self.visa_manager.list_resources()
    
    def test_ethernet_connection(self, ip_address: str, port: int = 5025) -> tuple[bool, str]:
        """Test Ethernet connection without adding to connected devices"""
        try:
            device = EthernetSCPIDevice(ip_address, port)
            if device.connect():
                try:
                    response = device.query("*IDN?")
                    device.disconnect()
                    if response:
                        return True, f"Device ID: {response}"
                    else:
                        return True, "Connection successful, no ID response"
                except Exception as e:
                    device.disconnect()
                    return True, f"Connected but query failed: {str(e)}"
            else:
                return False, f"Cannot connect to {ip_address}:{port}"
        except Exception as e:
            return False, f"Connection test failed: {str(e)}"


class Sensor:
    """Represents a single sensor configuration"""
    
    def __init__(self, name: str, device_id: str, channel: str = "", 
                 command: str = "", unit: str = "V", scale: float = 1.0, offset: float = 0.0,
                 # Legacy parameters for backward compatibility
                 resource: str = "", connection_type: str = "VISA", ip_address: str = "", port: int = 5025):
        self.name = name
        self.device_id = device_id  # Unified device identifier (e.g., "VISA:USB0::0x1234::..." or "Ethernet:192.168.1.100:5025")
        self.channel = channel
        self.command = command
        self.unit = unit
        self.scale = scale
        self.offset = offset
        self.enabled = True
        self.data = []
        self.timestamps = []
        self.max_points = 1000
        
        # Legacy support - maintain old parameters for existing configurations
        self.resource = resource or (device_id.split(':', 1)[1] if device_id.startswith('VISA:') else "")
        self.connection_type = connection_type if connection_type != "VISA" else device_id.split(':', 1)[0]
        self.ip_address = ip_address or (device_id.split(':')[1] if device_id.startswith('Ethernet:') else "")
        self.port = port if port != 5025 else (int(device_id.split(':')[2]) if device_id.startswith('Ethernet:') and len(device_id.split(':')) > 2 else 5025)
    
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
    
    def to_dict(self):
        """Convert sensor to dictionary for database storage"""
        return {
            'name': self.name,
            'device_id': self.device_id,
            'channel': self.channel,
            'command': self.command,
            'unit': self.unit,
            'scale': self.scale,
            'offset': self.offset,
            'enabled': self.enabled,
            # Legacy fields for backward compatibility
            'resource': self.resource,
            'connection_type': self.connection_type,
            'ip_address': self.ip_address,
            'port': self.port
        }
    
    @classmethod
    def from_dict(cls, data: dict):
        """Create sensor from dictionary"""
        # Handle both new device_id format and legacy format
        device_id = data.get('device_id')
        if not device_id:
            # Legacy format - construct device_id from old parameters
            connection_type = data.get('connection_type', 'VISA')
            if connection_type == 'VISA':
                device_id = f"VISA:{data.get('resource', '')}"
            elif connection_type == 'Ethernet':
                ip_address = data.get('ip_address', '')
                port = data.get('port', 5025)
                device_id = f"Ethernet:{ip_address}:{port}"
            else:
                device_id = f"{connection_type}:{data.get('resource', '')}"
        
        sensor = cls(
            name=data['name'],
            device_id=device_id,
            channel=data.get('channel', ''),
            command=data.get('command', ''),
            unit=data.get('unit', 'V'),
            scale=data.get('scale', 1.0),
            offset=data.get('offset', 0.0),
            # Legacy parameters
            resource=data.get('resource', ''),
            connection_type=data.get('connection_type', 'VISA'),
            ip_address=data.get('ip_address', ''),
            port=data.get('port', 5025)
        )
        sensor.enabled = data.get('enabled', True)
        return sensor


class ConfigurationManager:
    """Manages saving and loading sensor configurations to/from SQLite database"""
    
    def __init__(self, db_path: str = "sensor_configurations.db"):
        self.db_path = db_path
        self.init_database()
    
    def init_database(self):
        """Initialize the SQLite database with required tables"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Create configurations table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS configurations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                description TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                sensors_data TEXT NOT NULL,
                acquisition_frequency REAL DEFAULT 1.0
            )
        """)
        
        # Create sensor data table for continuous recording
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS sensor_data (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                sensor_name TEXT NOT NULL,
                device_id TEXT NOT NULL,
                timestamp TIMESTAMP NOT NULL,
                raw_value REAL NOT NULL,
                processed_value REAL NOT NULL,
                unit TEXT NOT NULL,
                scale REAL DEFAULT 1.0,
                offset REAL DEFAULT 0.0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Create data sessions table to group recordings
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS data_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT UNIQUE NOT NULL,
                name TEXT,
                description TEXT,
                start_time TIMESTAMP NOT NULL,
                end_time TIMESTAMP,
                sensor_count INTEGER DEFAULT 0,
                data_points INTEGER DEFAULT 0,
                frequency REAL DEFAULT 1.0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Create indexes for better performance
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_sensor_data_session ON sensor_data(session_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_sensor_data_timestamp ON sensor_data(timestamp)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_sensor_data_sensor ON sensor_data(sensor_name)")
        
        conn.commit()
        conn.close()
    
    def save_configuration(self, name: str, sensors: Dict[str, Sensor], 
                         description: str = "", frequency: float = 1.0) -> bool:
        """Save current sensor configuration to database"""
        try:
            # Convert sensors to JSON-serializable format
            sensors_data = {}
            for sensor_name, sensor in sensors.items():
                sensors_data[sensor_name] = sensor.to_dict()
            
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Insert or replace configuration
            cursor.execute("""
                INSERT OR REPLACE INTO configurations 
                (name, description, sensors_data, acquisition_frequency, updated_at)
                VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
            """, (name, description, json.dumps(sensors_data), frequency))
            
            conn.commit()
            conn.close()
            return True
            
        except Exception as e:
            print(f"Error saving configuration: {e}")
            return False
    
    def load_configuration(self, name: str) -> Optional[Dict]:
        """Load sensor configuration from database"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT name, description, sensors_data, acquisition_frequency, created_at, updated_at
                FROM configurations WHERE name = ?
            """, (name,))
            
            row = cursor.fetchone()
            conn.close()
            
            if row:
                sensors_data = json.loads(row[2])
                sensors = {}
                
                # Convert back to Sensor objects
                for sensor_name, sensor_dict in sensors_data.items():
                    sensors[sensor_name] = Sensor.from_dict(sensor_dict)
                
                return {
                    'name': row[0],
                    'description': row[1],
                    'sensors': sensors,
                    'frequency': row[3],
                    'created_at': row[4],
                    'updated_at': row[5]
                }
            
            return None
            
        except Exception as e:
            print(f"Error loading configuration: {e}")
            return None
    
    def list_configurations(self) -> List[Dict]:
        """List all saved configurations"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT name, description, created_at, updated_at
                FROM configurations ORDER BY updated_at DESC
            """)
            
            rows = cursor.fetchall()
            conn.close()
            
            configurations = []
            for row in rows:
                configurations.append({
                    'name': row[0],
                    'description': row[1],
                    'created_at': row[2],
                    'updated_at': row[3]
                })
            
            return configurations
            
        except Exception as e:
            print(f"Error listing configurations: {e}")
            return []
    
    def delete_configuration(self, name: str) -> bool:
        """Delete a configuration from database"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute("DELETE FROM configurations WHERE name = ?", (name,))
            
            deleted = cursor.rowcount > 0
            conn.commit()
            conn.close()
            
            return deleted
            
        except Exception as e:
            print(f"Error deleting configuration: {e}")
            return False
    
    # Data storage methods for sensor readings
    def start_data_session(self, session_name: str = "", description: str = "", frequency: float = 1.0) -> str:
        """Start a new data recording session and return session_id"""
        import uuid
        session_id = str(uuid.uuid4())
        
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute("""
                INSERT INTO data_sessions (session_id, name, description, start_time, frequency)
                VALUES (?, ?, ?, ?, ?)
            """, (session_id, session_name, description, datetime.now(), frequency))
            
            conn.commit()
            conn.close()
            return session_id
            
        except Exception as e:
            print(f"Error starting data session: {e}")
            return ""
    
    def end_data_session(self, session_id: str) -> bool:
        """End a data recording session"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Count data points in this session
            cursor.execute("SELECT COUNT(*) FROM sensor_data WHERE session_id = ?", (session_id,))
            data_points = cursor.fetchone()[0]
            
            # Update session end time and statistics
            cursor.execute("""
                UPDATE data_sessions 
                SET end_time = ?, data_points = ?
                WHERE session_id = ?
            """, (datetime.now(), data_points, session_id))
            
            conn.commit()
            conn.close()
            return True
            
        except Exception as e:
            print(f"Error ending data session: {e}")
            return False
    
    def save_sensor_data_point(self, session_id: str, sensor_name: str, device_id: str, 
                              timestamp: datetime, raw_value: float, processed_value: float,
                              unit: str, scale: float = 1.0, offset: float = 0.0) -> bool:
        """Save a single sensor data point to database"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute("""
                INSERT INTO sensor_data 
                (session_id, sensor_name, device_id, timestamp, raw_value, processed_value, unit, scale, offset)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (session_id, sensor_name, device_id, timestamp, raw_value, processed_value, unit, scale, offset))
            
            conn.commit()
            conn.close()
            return True
            
        except Exception as e:
            print(f"Error saving sensor data point: {e}")
            return False
    
    def save_current_sensor_data(self, session_name: str, sensors: Dict[str, Sensor], description: str = "") -> bool:
        """Save current state of all sensors to database as a snapshot"""
        session_id = self.start_data_session(session_name, description)
        if not session_id:
            return False
        
        try:
            for sensor_name, sensor in sensors.items():
                if sensor.data and sensor.timestamps:
                    # Save all current data points for this sensor
                    for i, (timestamp, raw_value) in enumerate(zip(sensor.timestamps, sensor.data)):
                        # Calculate raw value (reverse the scale/offset transformation)
                        raw_val = (raw_value - sensor.offset) / sensor.scale if sensor.scale != 0 else raw_value
                        
                        self.save_sensor_data_point(
                            session_id, sensor_name, sensor.device_id,
                            timestamp, raw_val, raw_value, sensor.unit,
                            sensor.scale, sensor.offset
                        )
            
            self.end_data_session(session_id)
            return True
            
        except Exception as e:
            print(f"Error saving current sensor data: {e}")
            self.end_data_session(session_id)  # Clean up on error
            return False
    
    def get_data_sessions(self) -> List[Dict]:
        """Get list of all data recording sessions"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT session_id, name, description, start_time, end_time, 
                       sensor_count, data_points, frequency
                FROM data_sessions 
                ORDER BY start_time DESC
            """)
            
            rows = cursor.fetchall()
            conn.close()
            
            sessions = []
            for row in rows:
                sessions.append({
                    'session_id': row[0],
                    'name': row[1] or f"Session {row[0][:8]}",
                    'description': row[2] or "",
                    'start_time': row[3],
                    'end_time': row[4],
                    'sensor_count': row[5] or 0,
                    'data_points': row[6] or 0,
                    'frequency': row[7] or 1.0
                })
            
            return sessions
            
        except Exception as e:
            print(f"Error getting data sessions: {e}")
            return []


class SensorMonitorApp:
    """Main NiceGUI application"""
    
    def __init__(self):
        self.device_manager = DeviceManager()  # Unified device management
        self.config_manager = ConfigurationManager()
        self.sensors = {}
        self.acquisition_task = None
        self.frequency = 1.0
        
        # New simplified recording system
        self.current_test_session_id = None
        self.test_session_active = False
        self.continuous_recording_active = False
        self.snapshot_averaging_seconds = 5.0
        
        # Keep-alive mechanism
        self.keep_alive_task = None
        
        # Keep legacy managers for backward compatibility if needed
        self.visa_manager = self.device_manager.visa_manager
        self.ethernet_manager = self.device_manager.ethernet_manager
        
        # UI components
        self.resource_select = None
        self.sensor_table = None
        self.status_log = None
        self.plot_area = None
        self.sensor_plots = {}  # Dictionary to store individual plot components
        self.frequency_input = None
        self.start_btn = None
        self.stop_btn = None
        self.record_btn = None
        self.save_btn = None
        
        # Sidebar state
        self.sidebar_visible = True
        self.sidebar_container = None
        self.hamburger_btn = None
        
        # Initialize VISA
        if not self.visa_manager.initialize():
            print("Failed to initialize VISA. Some features may not work.")
    
    def create_ui(self):
        """Create the NiceGUI interface"""
        ui.page_title('TES Sensor Monitor')
        
        # Custom CSS for styling
        ui.add_head_html('''
        <style>
            /* Reset default margins and padding */
            * {
                box-sizing: border-box;
            }
            
            html, body {
                margin: 0 !important;
                padding: 0 !important;
                height: 100% !important;
                overflow: hidden !important;
            }
            
            #app {
                margin: 0 !important;
                padding: 0 !important;
                height: 100vh !important;
            }
            
            .nicegui-content {
                margin: 0 !important;
                padding: 0 !important;
                height: 100vh !important;
            }
            .sensor-card {
                background: #f8f9fa;
                border: 1px solid #dee2e6;
                border-radius: 8px;
                padding: 16px;
                margin: 8px 0;
            }
            .status-panel {
                background: #ffffff;
                border: 1px solid #dee2e6;
                border-radius: 8px;
                padding: 12px;
                max-height: 200px;
                overflow-y: auto;
                font-family: monospace;
                font-size: 12px;
            }
            .control-section {
                background: #ffffff;
                border: 1px solid #dee2e6;
                border-radius: 8px;
                padding: 16px;
                margin: 8px 0;
                min-height: 60px;
                width: 100%;
                box-sizing: border-box;
            }
            
            /* Hamburger menu styles */
            .hamburger-btn {
                position: fixed;
                top: 8px;
                left: 8px;
                z-index: 1000;
                background: transparent;
                color: #037840;
                border: none;
                border-radius: 8px;
                padding: 8px 12px;
                cursor: pointer;
                font-size: 18px;
                transition: all 0.3s ease;
                opacity: 0.7;
            }
            .hamburger-btn:hover {
                background: rgba(3, 120, 64, 0.1);
                opacity: 1.0;
                transform: translateY(-1px);
            }
            
            /* Sidebar styles */
            .sidebar {
                transition: transform 0.3s ease, width 0.3s ease;
                background: rgba(248, 249, 250, 0.9);
                border-right: 1px solid rgba(222, 226, 230, 0.7);
                overflow-y: auto;
                height: 100vh;
                min-height: 100vh;
                margin: 0;
                padding: 0;
                opacity: 0.95;
            }
            
            /* Main content area */
            .main-content {
                flex: 1;
                height: 100vh;
                # overflow: hidden;
                margin: 0;
                padding: 0;
            }
            .sidebar.collapsed {
                transform: translateX(-100%);
                width: 0 !important;
                min-width: 0 !important;
                border-right: none;
            }
            
            /* Main content area adjustment */
            .main-content {
                transition: all 0.3s ease;
                flex: 1;
                height: 100vh;
                min-width: 0;
            }
            
            /* Remove overlay for now - simplified approach */
            
            /* Responsive adjustments */
            @media (max-width: 768px) {
                .sidebar {
                    position: fixed;
                    top: 0;
                    left: 0;
                    height: 100vh;
                    z-index: 1001;
                    width: 300px !important;
                    max-width: 80vw;
                }
                .sidebar.collapsed {
                    transform: translateX(-100%);
                }
                .main-content {
                    margin-left: 0 !important;
                }
            }
            
            /* Data acquisition controls - always full width */
            .data-acquisition-controls {
                width: 100% !important;
                max-width: 100% !important;
                min-width: 100% !important;
                margin: 0 0 0 20px !important;
                padding: 0 0 0 20px !important;
                flex: 1 1 100% !important;
                box-sizing: border-box !important;
                display: block !important;
            }
            .data-acquisition-controls > * {
                width: 100% !important;
                max-width: none !important;
            }
            
            /* Sensor plot grid styles - smaller sizes */
            .sensor-plot-card {
                background: #ffffff;
                border: 1px solid #dee2e6;
                border-radius: 12px;
                padding: 12px;
                margin: 6px;
                box-shadow: 0 2px 4px rgba(0,0,0,0.1);
                transition: box-shadow 0.3s ease;
                display: flex;
                flex-direction: column;
                min-height: 280px;
                box-sizing: border-box;
                /* Default to smaller size */
                flex: 0 0 calc(33.333% - 12px);
                max-width: calc(33.333% - 12px);
            }
            .sensor-plot-card:hover {
                box-shadow: 0 4px 8px rgba(0,0,0,0.15);
            }
            
            /* Grid responsive layout - smaller plot cards */
            @media (min-width: 1600px) {
                .sensor-plot-card {
                    flex: 0 0 calc(25% - 12px) !important;
                    max-width: calc(25% - 12px) !important;
                }
            }
            @media (max-width: 1200px) {
                .sensor-plot-card {
                    flex: 0 0 calc(50% - 12px) !important;
                    max-width: calc(50% - 12px) !important;
                }
            }
            @media (max-width: 768px) {
                .sensor-plot-card {
                    flex: 0 0 calc(100% - 12px) !important;
                    max-width: calc(100% - 12px) !important;
                    margin: 4px;
                    padding: 12px;
                }
            }
        </style>
        ''')
        
        # Hamburger menu button
        self.hamburger_btn = ui.button('☰', on_click=self.toggle_sidebar).classes('hamburger-btn')
        
        # Sidebar overlay for mobile (simplified)
        self.overlay = ui.element('div').classes('sidebar-overlay')
        
        # Main container with proper flex layout
        with ui.row().classes('w-full').style('margin: 0; padding: 0; gap: 0; height: 100vh; overflow: hidden; display: flex; position: absolute; top: 0; left: 0; right: 0; bottom: 0;'):
            # Left sidebar - Controls
            with ui.column().classes('sidebar').style('width: 350px; min-width: 350px; flex-shrink: 0;') as self.sidebar_container:
                with ui.scroll_area().classes('w-full h-full'):
                    with ui.column().classes('p-4 w-full'):
                        self.create_control_panel()
            
            # Right panel - Display (will expand when sidebar collapses)
            with ui.column().classes('main-content'):
                with ui.column().classes('h-full').style('padding: 0; margin: 0; width: 100%;'):
                    # Data acquisition controls need full width, so create them outside the padded container
                    self.create_data_acquisition_controls()
                    
                    # Rest of content with normal padding
                    with ui.column().classes('p-4'):
                        self.create_display_content()
        
        # Keep-alive will be started after the server starts
    
    def create_control_panel(self):
        """Create the control panel"""
        # Device Connection Management Section
        with ui.card().classes('control-section'):
            ui.label('Device Management').classes('text-h6 text-primary')
            
            # Connected devices list
            with ui.column().classes('w-full'):
                ui.label('Connected Devices').classes('text-subtitle1')
                self.device_table = ui.table(
                    columns=[
                        {'name': 'device_id', 'label': 'Device ID', 'field': 'device_id', 'align': 'left'},
                        {'name': 'type', 'label': 'Type', 'field': 'type', 'align': 'left'},
                        {'name': 'status', 'label': 'Status', 'field': 'status', 'align': 'left'},
                        {'name': 'actions', 'label': 'Actions', 'field': 'actions', 'align': 'center'},
                    ],
                    rows=[],
                    row_key='device_id'
                ).classes('w-full')
                
                # Add action column as slot
                self.device_table.add_slot('body-cell-actions', '''
                    <q-td :props="props">
                        <q-btn flat dense round icon="power_off" 
                               @click="$parent.$emit('disconnect', props.row.device_id)"
                               color="negative" size="sm">
                            <q-tooltip>Disconnect</q-tooltip>
                        </q-btn>
                    </q-td>
                ''')
                
                # Handle disconnect events
                self.device_table.on('disconnect', lambda e: self.disconnect_device_by_id(e.args))
                
                # Refresh button
                ui.button('Refresh Device List', on_click=self.refresh_device_list).classes('mt-2')
            
            ui.separator()
            
            # Add new device section
            ui.label('Add New Device').classes('text-subtitle1 mt-4')
            
            # Connection type selection
            self.new_connection_type = ui.select(
                options=['VISA', 'Ethernet'],
                value='VISA',
                label='Connection Type',
                on_change=self.on_new_connection_type_changed
            ).classes('w-full')
            
            # VISA connection UI
            with ui.column().classes('w-full').bind_visibility_from(
                self.new_connection_type, 'value', lambda x: x == 'VISA'
            ) as self.new_visa_ui:
                self.new_resource_select = ui.select(
                    options=[],
                    label='Available VISA Resources'
                ).classes('w-full')
                
                with ui.row().classes('w-full gap-2'):
                    ui.button('Refresh Resources', on_click=self.refresh_visa_resources)
                    ui.button('Connect VISA Device', on_click=self.connect_new_visa_device)
            
            # Ethernet connection UI
            with ui.column().classes('w-full').bind_visibility_from(
                self.new_connection_type, 'value', lambda x: x == 'Ethernet'
            ) as self.new_ethernet_ui:
                self.new_ip_address_input = ui.input(
                    'IP Address',
                    placeholder='192.168.1.100'
                ).classes('w-full')
                
                self.new_port_input = ui.number(
                    'Port',
                    value=5025,
                    min=1,
                    max=65535,
                    format='%d'
                ).classes('w-full')
                
                with ui.row().classes('w-full gap-2'):
                    ui.button('Test Connection', on_click=self.test_new_ethernet_connection)
                    ui.button('Connect Ethernet Device', on_click=self.connect_new_ethernet_device)
        
        # Sensor Management Section
        with ui.card().classes('control-section'):
            ui.label('Sensor Management').classes('text-h6 text-primary')
            
            # Device selection for sensor
            self.sensor_device_select = ui.select(
                options=[],
                label='Target Device',
                with_input=True
            ).classes('w-full')
            
            self.sensor_name = ui.input('Sensor Name').classes('w-full')
            self.sensor_channel = ui.input('Channel').classes('w-full')
            self.sensor_command = ui.input('Command').classes('w-full')
            self.sensor_unit = ui.input('Unit', value='V').classes('w-full')
            self.sensor_scale = ui.number('Scale', value=1.0, format='%.3f').classes('w-full')
            self.sensor_offset = ui.number('Offset', value=0.0, format='%.3f').classes('w-full')
            
            with ui.row().classes('w-full gap-2'):
                ui.button('Add Sensor', on_click=self.add_sensor)
                ui.button('Remove Selected', on_click=self.remove_sensor)
        
        
        # Status Section
        with ui.card().classes('control-section'):
            ui.label('Status Log').classes('text-h6 text-primary')
            self.status_log = ui.html().classes('status-panel')
            self.status_messages = []
            self.log_message("Application started")
        
        # Configuration Management Section
        with ui.card().classes('control-section'):
            ui.label('Configuration Management').classes('text-h6 text-primary')
            
            # Save configuration
            with ui.row().classes('w-full gap-2'):
                self.config_name_input = ui.input(
                    'Configuration Name',
                    placeholder='My Test Setup'
                ).classes('flex-1')
                ui.button('Save Config', on_click=self.save_configuration)
            
            self.config_description_input = ui.input(
                'Description (Optional)',
                placeholder='Description of this test setup'
            ).classes('w-full')
            
            # Load configuration
            with ui.row().classes('w-full gap-2'):
                self.config_select = ui.select(
                    options=[],
                    label='Saved Configurations'
                ).classes('flex-1')
                ui.button('Refresh', on_click=self.refresh_configurations)
            
            with ui.row().classes('w-full gap-2'):
                ui.button('Load Config', on_click=self.load_configuration)
                ui.button('Delete Config', on_click=self.delete_configuration)
    
    def create_display_content(self):
        """Create the display content (tabs and plots)"""
        with ui.tabs().classes('w-full') as tabs:
            real_time_tab = ui.tab('Real-time Plots')
            sensor_table_tab = ui.tab('Sensor Table')
        
        with ui.tab_panels(tabs, value=real_time_tab).classes('w-full h-full'):
            # Real-time Plot Panel - Grid Layout
            with ui.tab_panel(real_time_tab):
                ui.label('Real-time Sensor Plots').classes('text-h6 text-primary mb-4')
                
                # Create a responsive grid container for plots using flexbox
                self.plot_grid = ui.row().classes('w-full flex-wrap gap-0')
                
                # Initial message when no sensors are present
                with self.plot_grid:
                    self.no_sensors_message = ui.card().classes('w-full p-8 text-center bg-gray-50')
                    with self.no_sensors_message:
                        ui.icon('sensors', size='64px').classes('text-gray-400 mb-4')
                        ui.label('No sensors configured').classes('text-h6 text-gray-600 mb-2')
                        ui.label('Add sensors to see real-time plots here').classes('text-gray-500')
                
                self.update_plot_display()
            
            # Sensor Table Panel
            with ui.tab_panel(sensor_table_tab):
                self.sensor_table = ui.table(
                    columns=[
                        {'name': 'name', 'label': 'Name', 'field': 'name', 'align': 'left'},
                        {'name': 'connection', 'label': 'Connection', 'field': 'connection', 'align': 'left'},
                        {'name': 'unit', 'label': 'Unit', 'field': 'unit', 'align': 'left'},
                        {'name': 'value', 'label': 'Value', 'field': 'value', 'align': 'right'},
                        {'name': 'enabled', 'label': 'Enabled', 'field': 'enabled', 'align': 'center'},
                    ],
                    rows=[]
                ).classes('w-full')
    
    def create_data_acquisition_controls(self):
        """Create simplified data acquisition and recording controls"""
        with ui.card().classes('w-full mb-2').style('background: white; color: #333; border: 1px solid #ddd; margin: 0 32px 8px 0px; padding: 8px;'):
            
            # Single row layout with all elements
            with ui.row().classes('w-full items-center gap-3').style('overflow: hidden;'):
                # Title on the left
                ui.label('Data Acquisition & Test Recording').classes('text-base font-bold flex-shrink-0 mr-2')
                
                # Input controls in the middle
                with ui.row().classes('flex-grow items-center gap-3 justify-start'):
                    # Frequency control
                    self.frequency_input = ui.number(
                        'Freq (Hz)', 
                        value=1.0, 
                        min=0.1, 
                        max=1000,
                        format='%.1f'
                    ).classes('w-32 text-sm').style('background: #f8f9fa; border: 1px solid #ccc; border-radius: 4px;')
                    
                    # Test name input
                    self.test_name_input = ui.input(
                        'Test Name',
                        placeholder='Auto-generate'
                    ).classes('w-40 text-sm').style('background: #f8f9fa; border: 1px solid #ccc; border-radius: 4px;')
                    
                    # Snapshot averaging time
                    self.snapshot_avg_input = ui.number(
                        'Avg (sec)',
                        value=5.0,
                        min=0.1,
                        max=60.0,
                        format='%.1f'
                    ).classes('w-24 text-sm').style('background: #f8f9fa; border: 1px solid #ccc; border-radius: 4px;')
                
                # Control buttons in the middle-right
                with ui.row().classes('gap-2 flex-shrink-0'):
                    # Test session controls  
                    self.start_test_btn = ui.button('🚀 Start Test', on_click=self.start_test_session).classes('px-2 py-2 text-xs').style('background: #007bff; color: white; border: none;').props('title="Start New Test Session"')
                    self.end_test_btn = ui.button('🏁 End Test', on_click=self.end_test_session).classes('px-2 py-2 text-xs').style('background: #6c757d; color: white; border: none;').props('disabled title="End Current Test Session"')
                    
                    # Recording controls
                    self.start_record_btn = ui.button('🔴 Record', on_click=self.start_continuous_recording).classes('px-2 py-2 text-xs').style('background: #dc3545; color: white; border: none;').props('disabled title="Start Continuous Recording"')
                    self.stop_record_btn = ui.button('⏸️ Stop Rec', on_click=self.stop_continuous_recording).classes('px-2 py-2 text-xs').style('background: #6c757d; color: white; border: none;').props('disabled title="Stop Continuous Recording"')
                    
                    # Snapshot control
                    self.snapshot_btn = ui.button('💾 Save', on_click=self.save_snapshot).classes('px-2 py-2 text-xs').style('background: #28a745; color: white; border: none;').props('disabled title="Save Data Snapshot"')
                
                # Status labels on the right with gap from edge
                with ui.column().classes('gap-0 flex-shrink-0 items-end').style('max-width: 180px; overflow: hidden; margin-right: 16px;'):
                    self.test_status_label = ui.label('Test: None').classes('text-xs opacity-80 truncate')
                    self.recording_status_label = ui.label('Recording: Inactive').classes('text-xs opacity-80 truncate')
                    self.acquisition_status = ui.label('Acquisition: Stopped').classes('text-xs opacity-80 truncate')
    
    def toggle_sidebar(self):
        """Toggle the sidebar visibility"""
        self.sidebar_visible = not self.sidebar_visible
        
        if self.sidebar_visible:
            # Show sidebar
            self.sidebar_container.classes(remove='collapsed')
        else:
            # Hide sidebar
            self.sidebar_container.classes(add='collapsed')
        
        self.log_message(f"Sidebar {'shown' if self.sidebar_visible else 'hidden'}")
    
    
    def add_sensor(self):
        """Add a new sensor"""
        name = self.sensor_name.value.strip()
        if not name:
            ui.notify("Please enter a sensor name", type='warning')
            return
        
        if name in self.sensors:
            ui.notify("Sensor name already exists", type='warning')
            return
        
        device_id = self.sensor_device_select.value
        if not device_id:
            ui.notify("Please select a target device", type='warning')
            return
        
        # Verify device is still connected
        connected_devices = self.device_manager.get_connected_devices()
        if device_id not in connected_devices:
            ui.notify("Selected device is no longer connected", type='warning')
            self.refresh_device_list()
            return
        
        sensor = Sensor(
            name=name,
            device_id=device_id,
            channel=self.sensor_channel.value.strip(),
            command=self.sensor_command.value.strip(),
            unit=self.sensor_unit.value.strip(),
            scale=self.sensor_scale.value or 1.0,
            offset=self.sensor_offset.value or 0.0
        )
        
        self.sensors[name] = sensor
        self.update_sensor_table()
        self.update_plot_display()
        
        # Clear form
        self.sensor_name.value = ""
        self.sensor_channel.value = ""
        self.sensor_command.value = ""
        
        self.log_message(f"Added sensor: {name} on device {device_id}")
        ui.notify(f"Added sensor: {name}", type='positive')
    
    def remove_sensor(self):
        """Remove selected sensor"""
        # For now, remove the last added sensor
        # In a more complete implementation, you'd track which sensor is selected
        if self.sensors:
            sensor_name = list(self.sensors.keys())[-1]
            del self.sensors[sensor_name]
            self.update_sensor_table()
            self.update_plot_display()
            self.log_message(f"Removed sensor: {sensor_name}")
            ui.notify(f"Removed sensor: {sensor_name}", type='positive')
    
    def update_sensor_table(self):
        """Update the sensor table"""
        if self.sensor_table:
            rows = []
            for name, sensor in self.sensors.items():
                latest_value = sensor.get_latest_value()
                
                # Get device info from DeviceManager
                connected_devices = self.device_manager.get_connected_devices()
                if sensor.device_id in connected_devices:
                    device_info = connected_devices[sensor.device_id]
                    connection = f"{device_info['type']}: {device_info['display_name']}"
                else:
                    connection = f"DISCONNECTED: {sensor.device_id}"
                
                rows.append({
                    'name': name,
                    'connection': connection,
                    'unit': sensor.unit,
                    'value': f"{latest_value:.3f}" if latest_value is not None else "--",
                    'enabled': "✓" if sensor.enabled else "✗"
                })
            self.sensor_table.rows = rows
    
    def update_plot_display(self):
        """Update the plot display with individual charts for each sensor"""
        if not hasattr(self, 'plot_grid'):
            return
        
        # Show/hide no sensors message
        if hasattr(self, 'no_sensors_message'):
            if not self.sensors:
                self.no_sensors_message.set_visibility(True)
                return
            else:
                self.no_sensors_message.set_visibility(False)
        
        # Calculate grid layout - responsive design
        sensor_count = len(self.sensors)
        if sensor_count == 0:
            return
        elif sensor_count == 1:
            cols_per_row = 1
        elif sensor_count <= 4:
            cols_per_row = 2
        elif sensor_count <= 9:
            cols_per_row = 3
        else:
            cols_per_row = 4
        
        # Remove sensors that no longer exist
        sensors_to_remove = []
        for sensor_name in self.sensor_plots:
            if sensor_name not in self.sensors:
                sensors_to_remove.append(sensor_name)
        
        for sensor_name in sensors_to_remove:
            if sensor_name in self.sensor_plots:
                # Remove the plot container
                self.sensor_plots[sensor_name]['container'].delete()
                del self.sensor_plots[sensor_name]
        
        # Create plots for new sensors
        for sensor_name, sensor in self.sensors.items():
            if sensor_name not in self.sensor_plots:
                self.create_sensor_plot(sensor_name, sensor)
        
        # Update existing plots
        for sensor_name, sensor in self.sensors.items():
            if sensor_name in self.sensor_plots:
                self.update_sensor_plot(sensor_name, sensor)
        
        # Reorganize plots in grid layout
        self.reorganize_plots_grid(cols_per_row)
    
    def create_sensor_plot(self, sensor_name, sensor):
        """Create a new plot for a sensor"""
        # Create container for the plot
        with self.plot_grid:
            plot_container = ui.card().classes('sensor-plot-card')
            
            with plot_container:
                # Header with sensor info
                with ui.row().classes('w-full justify-between items-center mb-2'):
                    ui.label(sensor_name).classes('text-h6 font-bold')
                    value_label = ui.label('--').classes('text-subtitle1 text-primary')
                
                # Device info
                connected_devices = self.device_manager.get_connected_devices()
                if sensor.device_id in connected_devices:
                    device_info = connected_devices[sensor.device_id]
                    device_label = ui.label(f"Device: {device_info['display_name']}").classes('text-caption text-gray-600')
                else:
                    device_label = ui.label(f"Device: DISCONNECTED").classes('text-caption text-red-600')
                
                # Chart
                chart = ui.chart({
                    'title': False,
                    'chart': {'type': 'line', 'height': 200, 'animations': {'enabled': False}},
                    'series': [{
                        'name': f'{sensor_name} ({sensor.unit})',
                        'data': []
                    }],
                    'xaxis': {
                        'type': 'datetime',
                        'labels': {'format': 'HH:mm:ss'}
                    },
                    'yaxis': {
                        'title': {'text': f'{sensor.unit}'},
                        'labels': {'formatter': 'function(value) { return value.toFixed(3); }'}
                    },
                    'stroke': {'curve': 'smooth', 'width': 2},
                    'markers': {'size': 3},
                    'grid': {'borderColor': '#e7e7e7'},
                    'colors': [self.get_chart_color(len(self.sensor_plots))]
                }).classes('w-full')
                
                # Store references
                self.sensor_plots[sensor_name] = {
                    'container': plot_container,
                    'chart': chart,
                    'value_label': value_label,
                    'device_label': device_label
                }
    
    def update_sensor_plot(self, sensor_name, sensor):
        """Update an existing sensor plot with new data"""
        if sensor_name not in self.sensor_plots:
            return
        
        plot_info = self.sensor_plots[sensor_name]
        
        # Update value label
        latest_value = sensor.get_latest_value()
        if latest_value is not None:
            plot_info['value_label'].text = f'{latest_value:.3f} {sensor.unit}'
        else:
            plot_info['value_label'].text = '--'
        
        # Update device status
        connected_devices = self.device_manager.get_connected_devices()
        if sensor.device_id in connected_devices:
            device_info = connected_devices[sensor.device_id]
            plot_info['device_label'].text = f"Device: {device_info['display_name']}"
            plot_info['device_label'].classes(remove='text-red-600', add='text-gray-600')
        else:
            plot_info['device_label'].text = "Device: DISCONNECTED"
            plot_info['device_label'].classes(remove='text-gray-600', add='text-red-600')
        
        # Update chart data
        if sensor.data and sensor.timestamps:
            # Prepare data for chart (last 50 points for performance)
            data_points = []
            max_points = 50
            start_idx = max(0, len(sensor.data) - max_points)
            
            for i in range(start_idx, len(sensor.data)):
                timestamp_ms = int(sensor.timestamps[i].timestamp() * 1000)
                data_points.append([timestamp_ms, sensor.data[i]])
            
            # Update chart
            plot_info['chart'].options['series'][0]['data'] = data_points
            plot_info['chart'].update()
    
    def reorganize_plots_grid(self, cols_per_row):
        """Reorganize plots in a responsive grid layout - smaller plot cards"""
        # Calculate flex-basis percentage for each plot (smaller sizes)
        if cols_per_row == 1:
            flex_basis = "calc(100% - 12px)"
        elif cols_per_row == 2:
            flex_basis = "calc(50% - 12px)"
        elif cols_per_row == 3:
            flex_basis = "calc(33.333% - 12px)"  # Default size
        elif cols_per_row == 4:
            flex_basis = "calc(25% - 12px)"
        else:
            flex_basis = "calc(20% - 12px)"
        
        # Apply grid layout to plot containers - let CSS handle most sizing
        for i, (sensor_name, plot_info) in enumerate(self.sensor_plots.items()):
            container = plot_info['container']
            
            # Set minimal CSS style, let the CSS classes handle responsive sizing
            container.style(f'flex: 0 0 {flex_basis}; min-width: 250px; max-width: {flex_basis};')
    
    def get_chart_color(self, index):
        """Get a color for chart series based on index"""
        colors = [
            '#037840', '#28a745', '#dc3545', '#ffc107', '#17a2b8',
            '#6f42c1', '#e83e8c', '#fd7e14', '#20c997', '#6c757d'
        ]
        return colors[index % len(colors)]
    
    async def start_acquisition(self):
        """Start data acquisition"""
        if not self.sensors:
            ui.notify("No sensors configured", type='warning')
            return
        
        self.frequency = self.frequency_input.value or 1.0
        
        # Start acquisition task
        self.acquisition_task = asyncio.create_task(self.acquisition_loop())
        
        self.start_btn.props('disabled')
        self.stop_btn.props(remove='disabled')
        
        self.log_message(f"Started data acquisition at {self.frequency} Hz")
        ui.notify(f"Started acquisition at {self.frequency} Hz", type='positive')
    
    def stop_acquisition(self):
        """Stop data acquisition"""
        if self.acquisition_task:
            self.acquisition_task.cancel()
            self.acquisition_task = None
        
        self.start_btn.props(remove='disabled')
        self.stop_btn.props('disabled')
        
        self.log_message("Stopped data acquisition")
        ui.notify("Stopped acquisition", type='positive')
    
    async def acquisition_loop(self):
        """Main data acquisition loop"""
        try:
            interval = 1.0 / self.frequency
            
            while True:
                timestamp = datetime.now()
                
                for sensor_name, sensor in self.sensors.items():
                    if sensor.enabled:
                        try:
                            # Use unified DeviceManager for reading
                            value = self.device_manager.read_sensor_data(sensor.device_id, sensor.command)
                            
                            if value is not None:
                                # Calculate processed value (apply scale/offset)
                                processed_value = (value * sensor.scale) + sensor.offset
                                sensor.add_data_point(value, timestamp)
                                
                                # Save to database if continuous recording is active
                                if self.continuous_recording_active and self.current_test_session_id:
                                    self.config_manager.save_sensor_data_point(
                                        self.current_test_session_id,
                                        sensor_name,
                                        sensor.device_id,
                                        timestamp,
                                        value,  # raw value
                                        processed_value,  # processed value
                                        sensor.unit,
                                        sensor.scale,
                                        sensor.offset
                                    )
                            else:
                                self.log_message(f"Failed to read sensor {sensor_name} from device {sensor.device_id}")
                        except Exception as e:
                            self.log_message(f"Error reading {sensor_name}: {e}")
                
                # Update displays
                self.update_sensor_table()
                self.update_plot_display()
                
                await asyncio.sleep(interval)
                
        except asyncio.CancelledError:
            self.log_message("Acquisition cancelled")
    
    def start_test_session(self):
        """Start a new test session with unique ID and begin data acquisition"""
        if self.test_session_active:
            ui.notify("Test session already active", type='warning')
            return
        
        if not self.sensors:
            ui.notify("No sensors configured", type='warning')
            return
        
        test_name = self.test_name_input.value.strip() or f"Test_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        description = f"Test session with {len(self.sensors)} sensors at {self.frequency}Hz"
        
        self.current_test_session_id = self.config_manager.start_data_session(test_name, description, self.frequency)
        if self.current_test_session_id:
            self.test_session_active = True
            
            # Automatically start data acquisition
            self.frequency = self.frequency_input.value or 1.0
            self.acquisition_task = asyncio.create_task(self.acquisition_loop())
            
            self.update_test_status_labels()
            self.update_button_states()
            self.log_message(f"Started test session: {test_name} (ID: {self.current_test_session_id[:8]}) with acquisition at {self.frequency} Hz")
            ui.notify(f"Test session '{test_name}' started with data acquisition", type='positive')
        else:
            self.log_message("Failed to start test session")
            ui.notify("Failed to start test session", type='negative')
    
    def end_test_session(self):
        """End the current test session and stop data acquisition"""
        if not self.test_session_active or not self.current_test_session_id:
            ui.notify("No active test session", type='warning')
            return
        
        # Stop continuous recording if active
        if self.continuous_recording_active:
            self.stop_continuous_recording()
        
        # Stop data acquisition
        if self.acquisition_task:
            self.acquisition_task.cancel()
            self.acquisition_task = None
        
        success = self.config_manager.end_data_session(self.current_test_session_id)
        if success:
            self.log_message(f"Ended test session: {self.current_test_session_id[:8]} and stopped data acquisition")
            ui.notify("Test session ended and acquisition stopped", type='positive')
        else:
            self.log_message("Failed to end test session")
            ui.notify("Failed to end test session", type='negative')
        
        self.test_session_active = False
        self.current_test_session_id = None
        self.update_test_status_labels()
        self.update_button_states()
    
    def start_continuous_recording(self):
        """Start continuous recording to database"""
        if not self.test_session_active:
            ui.notify("Please start a test session first", type='warning')
            return
        
        if self.continuous_recording_active:
            ui.notify("Continuous recording already active", type='warning')
            return
        
        self.continuous_recording_active = True
        self.update_test_status_labels()
        self.update_button_states()
        self.log_message("Started continuous recording")
        ui.notify("Continuous recording started", type='positive')
    
    def stop_continuous_recording(self):
        """Stop continuous recording"""
        if not self.continuous_recording_active:
            ui.notify("Continuous recording not active", type='warning')
            return
        
        self.continuous_recording_active = False
        self.update_test_status_labels()
        self.update_button_states()
        self.log_message("Stopped continuous recording")
        ui.notify("Continuous recording stopped", type='positive')
    
    def save_snapshot(self):
        """Save a snapshot of averaged data over specified time period"""
        if not self.test_session_active:
            ui.notify("Please start a test session first", type='warning')
            return
        
        if not self.sensors:
            ui.notify("No sensors configured", type='warning')
            return
        
        # Get averaging time from input
        avg_seconds = self.snapshot_avg_input.value or 5.0
        
        # Calculate averaged values for each sensor over the specified time
        snapshot_data = {}
        current_time = datetime.now()
        
        for sensor_name, sensor in self.sensors.items():
            if sensor.data and sensor.timestamps:
                # Find data points within the averaging window
                cutoff_time = current_time - pd.Timedelta(seconds=avg_seconds)
                
                recent_data = []
                for i, timestamp in enumerate(sensor.timestamps):
                    if timestamp >= cutoff_time:
                        recent_data.append(sensor.data[i])
                
                if recent_data:
                    avg_value = np.mean(recent_data)
                    snapshot_data[sensor_name] = {
                        'average_value': avg_value,
                        'sample_count': len(recent_data),
                        'unit': sensor.unit,
                        'averaging_seconds': avg_seconds
                    }
                    
                    # Save to database as a special snapshot entry
                    self.config_manager.save_sensor_data_point(
                        self.current_test_session_id,
                        f"{sensor_name}_snapshot_{avg_seconds}s",
                        sensor.device_id,
                        current_time,
                        avg_value,  # Use averaged value as both raw and processed
                        avg_value,
                        f"{sensor.unit}_avg",
                        1.0,  # No additional scaling for snapshot
                        0.0
                    )
        
        if snapshot_data:
            self.log_message(f"Saved snapshot with {len(snapshot_data)} sensors (avg over {avg_seconds}s)")
            ui.notify(f"Snapshot saved ({avg_seconds}s average)", type='positive')
        else:
            self.log_message("No recent data available for snapshot")
            ui.notify("No recent data for snapshot", type='warning')
    
    def update_test_status_labels(self):
        """Update the test session and recording status labels"""
        if self.test_session_active and self.current_test_session_id:
            test_id_short = self.current_test_session_id[:8]
            self.test_status_label.text = f"Test: {test_id_short}"
            self.test_status_label.classes(remove='text-gray-600', add='text-blue-600')
        else:
            self.test_status_label.text = "Test: None"
            self.test_status_label.classes(remove='text-blue-600', add='text-gray-600')
        
        if self.continuous_recording_active:
            self.recording_status_label.text = "Recording: Active"
            self.recording_status_label.classes(remove='text-gray-600', add='text-red-600')
        else:
            self.recording_status_label.text = "Recording: Inactive"
            self.recording_status_label.classes(remove='text-red-600', add='text-gray-600')
        
        # Update acquisition status
        if self.acquisition_task and not self.acquisition_task.done():
            self.acquisition_status.text = f"Acquisition: Running ({self.frequency:.1f} Hz)"
            self.acquisition_status.classes(remove='text-gray-600', add='text-green-600')
        else:
            self.acquisition_status.text = "Acquisition: Stopped"
            self.acquisition_status.classes(remove='text-green-600', add='text-gray-600')
    
    def update_button_states(self):
        """Update button enabled/disabled states based on current status"""
        # Test session buttons
        if self.test_session_active:
            self.start_test_btn.props('disabled')
            self.end_test_btn.props(remove='disabled')
            self.start_record_btn.props(remove='disabled')
            self.snapshot_btn.props(remove='disabled')
        else:
            self.start_test_btn.props(remove='disabled')
            self.end_test_btn.props('disabled')
            self.start_record_btn.props('disabled')
            self.stop_record_btn.props('disabled')
            self.snapshot_btn.props('disabled')
        
        # Recording buttons
        if self.continuous_recording_active:
            self.start_record_btn.props('disabled')
            self.stop_record_btn.props(remove='disabled')
        else:
            if self.test_session_active:
                self.start_record_btn.props(remove='disabled')
            self.stop_record_btn.props('disabled')
    
    def start_keep_alive(self):
        """Start the keep-alive mechanism to prevent WebSocket timeouts"""
        self.keep_alive_task = asyncio.create_task(self.keep_alive_loop())
    
    async def keep_alive_loop(self):
        """Keep-alive loop that periodically updates the UI to maintain connection"""
        try:
            while True:
                # Wait 30 seconds between keep-alive updates
                await asyncio.sleep(30)
                
                # Small UI update to keep connection alive by refreshing status labels
                try:
                    self.update_test_status_labels()
                    
                    # Also add a subtle timestamp update to the status log periodically
                    current_time = datetime.now()
                    if current_time.minute % 5 == 0 and current_time.second < 30:
                        # Every 5 minutes, add a keep-alive message
                        self.log_message("System: Connection active")
                        
                except Exception as e:
                    # Log any errors but don't crash the keep-alive loop
                    print(f"Keep-alive update error: {e}")
                    
        except asyncio.CancelledError:
            pass  # Expected when application shuts down
    
    def log_message(self, message: str):
        """Add message to status log"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        full_message = f"[{timestamp}] {message}"
        self.status_messages.append(full_message)
        
        # Keep only last 50 messages
        if len(self.status_messages) > 50:
            self.status_messages.pop(0)
        
        if self.status_log:
            html_content = "<br>".join(self.status_messages[-10:])  # Show last 10 messages
            self.status_log.content = html_content
    
    def save_configuration(self):
        """Save current sensor configuration to database"""
        config_name = self.config_name_input.value.strip()
        if not config_name:
            ui.notify("Please enter a configuration name", type='warning')
            return
        
        if not self.sensors:
            ui.notify("No sensors to save", type='warning')
            return
        
        description = self.config_description_input.value.strip()
        frequency = self.frequency_input.value if self.frequency_input else 1.0
        
        if self.config_manager.save_configuration(config_name, self.sensors, description, frequency):
            self.log_message(f"Configuration '{config_name}' saved successfully")
            ui.notify(f"Configuration '{config_name}' saved", type='positive')
            
            # Clear form and refresh list
            self.config_name_input.value = ""
            self.config_description_input.value = ""
            self.refresh_configurations()
        else:
            self.log_message(f"Failed to save configuration '{config_name}'")
            ui.notify(f"Failed to save configuration", type='negative')
    
    def load_configuration(self):
        """Load selected sensor configuration from database"""
        config_name = self.config_select.value
        if not config_name:
            ui.notify("Please select a configuration to load", type='warning')
            return
        
        config_data = self.config_manager.load_configuration(config_name)
        if config_data:
            # Clear current sensors
            self.sensors.clear()
            
            # Load sensors from configuration
            self.sensors = config_data['sensors']
            
            # Update frequency
            if self.frequency_input:
                self.frequency_input.value = config_data['frequency']
            
            # Update displays
            self.update_sensor_table()
            self.update_plot_display()
            
            self.log_message(f"Configuration '{config_name}' loaded successfully")
            ui.notify(f"Configuration '{config_name}' loaded", type='positive')
        else:
            self.log_message(f"Failed to load configuration '{config_name}'")
            ui.notify(f"Failed to load configuration", type='negative')
    
    def delete_configuration(self):
        """Delete selected configuration from database"""
        config_name = self.config_select.value
        if not config_name:
            ui.notify("Please select a configuration to delete", type='warning')
            return
        
        if self.config_manager.delete_configuration(config_name):
            self.log_message(f"Configuration '{config_name}' deleted successfully")
            ui.notify(f"Configuration '{config_name}' deleted", type='positive')
            self.refresh_configurations()
        else:
            self.log_message(f"Failed to delete configuration '{config_name}'")
            ui.notify(f"Failed to delete configuration", type='negative')
    
    def refresh_configurations(self):
        """Refresh the list of saved configurations"""
        configurations = self.config_manager.list_configurations()
        
        # Update the select options
        config_options = []
        for config in configurations:
            # Format: "Name (Description) - Updated: Date"
            label = config['name']
            if config['description']:
                label += f" ({config['description']})"
            label += f" - Updated: {config['updated_at'][:10]}"  # Show date only
            config_options.append({'label': label, 'value': config['name']})
        
        if self.config_select:
            self.config_select.options = config_options
            if not config_options:
                self.config_select.value = None
        
        self.log_message(f"Found {len(configurations)} saved configurations")
    
    # Multi-device management methods
    def refresh_device_list(self):
        """Refresh the connected devices table"""
        devices = self.device_manager.get_connected_devices()
        rows = []
        
        for device_id, device_info in devices.items():
            rows.append({
                'device_id': device_id,
                'type': device_info['type'],
                'status': 'Connected',
                'actions': device_id  # We'll use this for disconnect action
            })
        
        if self.device_table:
            self.device_table.rows = rows
        
        # Update sensor device selection options
        device_options = [{'label': device_info['display_name'], 'value': device_id} 
                         for device_id, device_info in devices.items()]
        if self.sensor_device_select:
            self.sensor_device_select.options = device_options
        
        self.log_message(f"Found {len(devices)} connected devices")
    
    def on_new_connection_type_changed(self, e):
        """Handle new connection type change"""
        self.log_message(f"New connection type set to {e.value}")
    
    def refresh_visa_resources(self):
        """Refresh available VISA resources for new connections"""
        resources = self.device_manager.list_visa_resources()
        if self.new_resource_select:
            self.new_resource_select.options = resources
            if resources:
                self.new_resource_select.value = resources[0]
        self.log_message(f"Found {len(resources)} VISA resources")
    
    def connect_new_visa_device(self):
        """Connect to a new VISA device"""
        resource = self.new_resource_select.value
        if not resource:
            ui.notify("Please select a VISA resource", type='warning')
            return
        
        success, result = self.device_manager.connect_device('VISA', resource=resource)
        if success:
            device_id = result
            self.log_message(f"Connected to VISA device {resource} as {device_id}")
            ui.notify(f"Connected to {resource}", type='positive')
            self.refresh_device_list()
        else:
            self.log_message(f"Failed to connect to VISA device {resource}: {result}")
            ui.notify(f"Failed to connect: {result}", type='negative')
    
    def connect_new_ethernet_device(self):
        """Connect to a new Ethernet device"""
        ip_address = self.new_ip_address_input.value.strip()
        port = int(self.new_port_input.value or 5025)
        
        if not ip_address:
            ui.notify("Please enter an IP address", type='warning')
            return
        
        success, result = self.device_manager.connect_device('Ethernet', ip_address=ip_address, port=port)
        if success:
            device_id = result
            self.log_message(f"Connected to Ethernet device {ip_address}:{port} as {device_id}")
            ui.notify(f"Connected to {ip_address}:{port}", type='positive')
            self.refresh_device_list()
        else:
            self.log_message(f"Failed to connect to Ethernet device {ip_address}:{port}: {result}")
            ui.notify(f"Failed to connect: {result}", type='negative')
    
    def test_new_ethernet_connection(self):
        """Test a new Ethernet connection"""
        ip_address = self.new_ip_address_input.value.strip()
        port = int(self.new_port_input.value or 5025)
        
        if not ip_address:
            ui.notify("Please enter an IP address", type='warning')
            return
        
        success, message = self.device_manager.test_ethernet_connection(ip_address, port)
        if success:
            self.log_message(f"Ethernet test successful - {message}")
            ui.notify("Connection test successful", type='positive')
        else:
            self.log_message(f"Ethernet test failed - {message}")
            ui.notify(f"Test failed: {message}", type='negative')
    
    def disconnect_device_by_id(self, device_id: str):
        """Disconnect a device by its ID"""
        success = self.device_manager.disconnect_device(device_id)
        if success:
            self.log_message(f"Disconnected device {device_id}")
            ui.notify(f"Disconnected {device_id}", type='positive')
            self.refresh_device_list()
        else:
            self.log_message(f"Failed to disconnect device {device_id}")
            ui.notify(f"Failed to disconnect {device_id}", type='negative')


def main():
    """Launch the TES Sensor Monitor NiceGUI application"""
    monitor = SensorMonitorApp()
    monitor.create_ui()
    
    # Initialize resources on startup
    monitor.refresh_visa_resources()
    monitor.refresh_device_list()
    monitor.refresh_configurations()
    
    # Initialize button states and status labels
    monitor.update_test_status_labels()
    monitor.update_button_states()
    
    # Start keep-alive after the server starts
    @app.on_startup
    def on_startup():
        monitor.start_keep_alive()
    
    ui.run(
        title='TES Sensor Monitor',
        port=8080,
        native=True,
        show=True,
        reload=False,
        # Prevent connection timeouts
        reconnect_timeout=30.0
    )


if __name__ == "__main__":
    main()