"""Pool Comfort heat pump controller protocol implementation.

Communicates with the GalaxyWind/Wotech-based WiFi module via UDP.
Supports cloud relay connections through the Alsavo protocol.

Protocol: Proprietary UDP, device type "tb" (TbCommercial).
Authentication: 3-step MD5 handshake.
Status: Standard Alsavo 16-bit indexed registers via cloud (F4 action=0x08/0x0B).
Control: F4 action=0x09, SetConfig with type=0x0002000d.
"""

import socket
import struct
import hashlib
import random
import time
import logging
from datetime import datetime

_LOGGER = logging.getLogger(__name__)

# === Protocol Constants ===
HDR_REQUEST = 0x32
HDR_REPLY = 0x30
CMD_LOGIN = 0x00F2
CMD_STATUS = 0x00F3
CMD_DATA = 0x00F4

# Alsavo object type for this device's registers
OBJ_TYPE = 0x0002000D

# Register subcategories (SC values) within OBJ_TYPE
SC_CONFIG = 21       # 68-byte TbCommercialConfig struct
SC_TEMP = 22         # Set temperature: [temp_16bit, flags_16bit]
SC_MODE = 23         # Mode: [mode_byte, 0x00, 0x00, 0x00]
SC_POWER = 24        # Power: [power_byte, 0x00, 0x00, 0x00]
SC_STATUS = 25       # Status values (16 bytes)
SC_STATUS2 = 26      # More status (12 bytes)
SC_PROTECT = 27      # Protection config (20 bytes)
SC_TEMPS = 30        # Status temperatures
SC_EEV = 31          # EEV config (12 bytes)
SC_EXTRA = 32        # Extra status

# Dispatcher/cloud infrastructure
CLOUD_IE = "47.88.188.100"
CLOUD_CN = "114.55.34.145"
DISPATCHER_PORTS = [51180, 31578]

# Mode values
MODE_NAMES = {0: "Auto", 1: "Cool", 2: "Heat", 3: "Warm"}


def _build_header(hdr, enc, seq, csid, dsid, cmd, payload_len):
    """Build 16-byte protocol header."""
    return struct.pack(">BBHII", hdr, enc, seq, csid, dsid) + \
           struct.pack(">hH", cmd, payload_len)


def _build_timestamp():
    """Build 8-byte UTC timestamp struct."""
    now = datetime.utcnow()
    return struct.pack(">HBBBBBb", now.year, now.month, now.day,
                       now.hour, now.minute, now.second, 2)


class PoolComfortConnectionError(Exception):
    """Raised when connection to the device fails."""


class PoolComfort:
    """Pool Comfort heat pump controller client via cloud relay."""

    def __init__(self, serial: str, password: str):
        self.serial = serial
        self.password = password
        self.password_hash = hashlib.md5(password.encode()).digest()
        self.sock = None
        self.relay_ip = None
        self.relay_port = None
        self.csid = 0
        self.dsid = 0
        self.seq = 0
        self.client_token = 0
        self.connected = False
        self.device_name = ""
        self.dev_type = 0
        self.ext_type = 0
        self.registers: dict[int, bytes] = {}
        self.compact_config: dict[int, int] = {}

    # === Discovery ===

    def discover_relay(self, timeout=5):
        """Discover cloud relay IP:port via UCC dispatcher protocol."""
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(timeout)

        query = bytearray()
        query.append(0x2C)
        query.extend(b'\x04\x00\x09')
        query.extend(b'\x00\x00\x00\x14')
        query.extend(b'\x01\x00\x00\x01')
        query.extend(self.serial.encode('ascii'))
        query.extend(b'\x00\x00\x00\x00')
        query.extend(b'\x08\x03\x00\x00\x76\x58')
        query = bytes(query)

        targets = [
            (CLOUD_IE, 51180),
            (CLOUD_CN, 51180),
            (CLOUD_IE, 31578),
        ]

        for ip, port in targets:
            try:
                sock.sendto(query, (ip, port))
            except Exception as e:
                _LOGGER.debug("Failed to send to %s:%d: %s", ip, port, e)

        deadline = time.time() + timeout
        while time.time() < deadline:
            remaining = deadline - time.time()
            if remaining <= 0:
                break
            sock.settimeout(max(0.1, remaining))
            try:
                data, addr = sock.recvfrom(4096)
                if len(data) >= 30:
                    ip_bytes = data[24:28]
                    port_val = struct.unpack(">H", data[28:30])[0]
                    if any(b != 0 for b in ip_bytes) and port_val > 0:
                        ip = ".".join(str(b) for b in ip_bytes)
                        _LOGGER.info("Discovered relay: %s:%d (from %s:%d)",
                                     ip, port_val, *addr)
                        sock.close()
                        return ip, port_val
            except socket.timeout:
                continue

        sock.close()
        return None

    # === Connection ===

    def connect(self, relay_ip=None, relay_port=None):
        """Connect to cloud relay and authenticate."""
        if relay_ip and relay_port:
            self.relay_ip = relay_ip
            self.relay_port = relay_port
        else:
            _LOGGER.info("Discovering relay...")
            result = self.discover_relay()
            if not result:
                raise PoolComfortConnectionError(
                    "Failed to discover cloud relay. Check serial number and device connectivity."
                )
            self.relay_ip, self.relay_port = result

        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.settimeout(8)

        if not self._authenticate():
            raise PoolComfortConnectionError(
                "Authentication failed. Check serial number and password."
            )
        return True

    def close(self):
        """Close connection."""
        if self.sock:
            self.sock.close()
            self.sock = None
        self.connected = False

    def _send(self, data):
        self.sock.sendto(data, (self.relay_ip, self.relay_port))

    def _recv(self, timeout=5):
        self.sock.settimeout(timeout)
        try:
            data, addr = self.sock.recvfrom(4096)
            return data
        except socket.timeout:
            return None

    def _recv_all(self, timeout=3):
        packets = []
        deadline = time.time() + timeout
        while time.time() < deadline:
            remaining = deadline - time.time()
            if remaining <= 0:
                break
            self.sock.settimeout(max(0.1, remaining))
            try:
                data, addr = self.sock.recvfrom(4096)
                packets.append(data)
            except socket.timeout:
                break
        return packets

    def _next_seq(self):
        self.seq += 256
        return self.seq

    # === Authentication ===

    def _authenticate(self):
        """3-step MD5 authentication to cloud relay."""
        _LOGGER.info("Authenticating to %s:%d", self.relay_ip, self.relay_port)

        # Step 1: AuthIntro
        self.client_token = random.randint(0, 0xFFFFFFFF)
        payload = bytes([1, 1, 2, 0])
        payload += struct.pack(">I", self.client_token)
        payload += struct.pack(">q", int(self.serial))
        payload += bytes([0xFF, 0xFF, 0xFF, 0xFF,
                          0xD3, 0xE2, 0xEE, 0xAC,
                          0x00, 0x00, 0x00, 0x00,
                          0x6A, 0xFD, 0xC7, 0x55])
        payload += _build_timestamp()

        header = _build_header(HDR_REQUEST, 0, 0, 0, 0, CMD_LOGIN, len(payload))
        self._send(header + payload)

        data = self._recv(timeout=3)
        if not data:
            self._send(header + payload)
            data = self._recv(timeout=5)
        if not data or len(data) < 24 or data[16] != 3:
            _LOGGER.error("No AuthChallenge (got %d bytes)", len(data) if data else 0)
            return False

        self.csid = struct.unpack(">I", data[4:8])[0]
        self.dsid = struct.unpack(">I", data[8:12])[0]
        server_token = struct.unpack(">I", data[20:24])[0]

        # Step 2: AuthResponse
        md5 = hashlib.md5()
        md5.update(struct.pack(">I", self.client_token))
        md5.update(struct.pack(">I", server_token))
        md5.update(self.password_hash)

        auth_resp = bytes([4, 0, 0, 3]) + md5.digest() + _build_timestamp()
        auth_resp += bytes(42)
        auth_hdr = _build_header(HDR_REQUEST, 0, 0, self.csid, self.dsid,
                                 CMD_LOGIN, len(auth_resp))
        self._send(auth_hdr + auth_resp)

        # Step 3: Check confirmation
        data = self._recv(timeout=5)
        if not data or len(data) < 17 or data[16] != 5:
            _LOGGER.error("Auth failed")
            return False

        p = data[16:]
        if len(p) > 11:
            self.dev_type = p[10]
            self.ext_type = p[11]
        if len(p) > 32:
            self.device_name = p[16:32].split(b'\x00')[0].decode('ascii', errors='replace')
        if len(p) > 36:
            self._parse_embedded_config(p[32:])

        self.seq = 0
        self.connected = True
        _LOGGER.info("Auth OK: csid=0x%08x dsid=0x%08x name=%s",
                     self.csid, self.dsid, self.device_name)
        return True

    def _parse_embedded_config(self, data):
        pos = 0
        while pos + 4 <= len(data):
            start_idx = struct.unpack(">H", data[pos:pos + 2])[0]
            size = struct.unpack(">H", data[pos + 2:pos + 4])[0]
            pos += 4
            if size == 0 or pos + size > len(data):
                break
            for i in range(size):
                self.compact_config[start_idx + i] = data[pos + i]
            pos += size

    # === Register Reading ===

    def query_all_registers(self):
        """Query all device registers."""
        payload = struct.pack(">BBHIHH",
                              0x08, 0x01, 0x0000,
                              OBJ_TYPE, 0xFFFF, 0x0000)
        seq = self._next_seq()
        hdr = _build_header(HDR_REQUEST, 0, seq, self.csid, self.dsid,
                            CMD_DATA, len(payload))
        self._send(hdr + payload)

        packets = self._recv_all(timeout=5)
        if not packets:
            self._send(hdr + payload)
            packets = self._recv_all(timeout=5)

        for data in packets:
            if len(data) > 20:
                p = data[16:]
                if len(p) >= 4 and p[0] in (0x08, 0x0B):
                    self._parse_alsavo_objects(p)

        return dict(self.registers)

    def _parse_alsavo_objects(self, payload):
        if len(payload) < 4:
            return
        num_objects = payload[1]
        pos = 4

        for _ in range(num_objects):
            if pos + 8 > len(payload):
                break
            obj_type = struct.unpack(">I", payload[pos:pos + 4])[0]
            sc = struct.unpack(">H", payload[pos + 4:pos + 6])[0]
            data_size = struct.unpack(">H", payload[pos + 6:pos + 8])[0]
            pos += 8

            if obj_type == OBJ_TYPE and data_size > 0:
                obj_data = payload[pos:pos + data_size]
                if len(obj_data) == data_size:
                    self.registers[sc] = obj_data
            pos += data_size

    def process_incoming(self, timeout=2):
        """Process incoming push notifications."""
        packets = self._recv_all(timeout=timeout)
        ack_sent = False
        for data in packets:
            if len(data) > 20:
                p = data[16:]
                if len(p) >= 4 and p[0] == 0x0B:
                    self._parse_alsavo_objects(p)
                    if not ack_sent:
                        ack = struct.pack(">BBHIHH",
                                          0x0B, 0x01, 0x0000,
                                          OBJ_TYPE, SC_CONFIG, 0x0000)
                        ack_hdr = _build_header(HDR_REPLY, 0,
                                                struct.unpack(">H", data[2:4])[0],
                                                self.csid, self.dsid,
                                                CMD_DATA, len(ack))
                        self._send(ack_hdr + ack)
                        ack_sent = True
        return len(packets)

    # === Control Commands ===

    def set_temp(self, temp_c: int) -> bool:
        """Set target temperature in Celsius."""
        temp_int = int(temp_c)
        _LOGGER.info("Setting temperature to %d°C", temp_int)
        return self._send_set_command(SC_TEMP, struct.pack(">HH", temp_int, 0x0000))

    def set_mode(self, mode) -> bool:
        """Set operating mode (0=auto, 1=cool, 2=heat)."""
        if isinstance(mode, str):
            mode_map = {"auto": 0, "smart": 0, "cool": 1, "cooling": 1,
                        "heat": 2, "heating": 2}
            if mode.lower() in mode_map:
                mode = mode_map[mode.lower()]
            else:
                mode = int(mode)
        mode = int(mode)
        _LOGGER.info("Setting mode to %s (%d)", MODE_NAMES.get(mode, "?"), mode)
        return self._send_set_command(SC_MODE, bytes([mode, 0x00, 0x00, 0x00]))

    def set_power(self, on: bool) -> bool:
        """Set power on/off."""
        val = 0x01 if on else 0x00
        _LOGGER.info("Setting power %s", "ON" if on else "OFF")
        return self._send_set_command(SC_POWER, bytes([val, 0x00, 0x00, 0x00]))

    def _send_set_command(self, sc, data) -> bool:
        payload = struct.pack(">BBHIHH",
                              0x09, 0x01, 0x0000,
                              OBJ_TYPE, sc, len(data))
        payload += data

        seq = self._next_seq()
        hdr = _build_header(HDR_REQUEST, 0, seq, self.csid, self.dsid,
                            CMD_DATA, len(payload))
        full_pkt = hdr + payload
        self._send(full_pkt)

        time.sleep(0.3)
        self._send(full_pkt)

        packets = self._recv_all(timeout=5)
        success = False
        for pkt in packets:
            if len(pkt) > 20:
                p = pkt[16:]
                if len(p) >= 4:
                    if p[0] == 0x09:
                        success = True
                    if p[0] == 0x0B:
                        self._parse_alsavo_objects(p)
                        ack = struct.pack(">BBHIHH",
                                          0x0B, 0x01, 0x0000,
                                          OBJ_TYPE, SC_CONFIG, 0x0000)
                        ack_hdr = _build_header(HDR_REPLY, 0,
                                                struct.unpack(">H", pkt[2:4])[0],
                                                self.csid, self.dsid,
                                                CMD_DATA, len(ack))
                        self._send(ack_hdr + ack)
        return success

    # === Status Parsing ===

    def get_set_temp(self) -> int | None:
        """Get set temperature from registers."""
        data = self.registers.get(SC_TEMP)
        if data and len(data) >= 2:
            return struct.unpack(">H", data[0:2])[0]
        return None

    def _get_sc21_words(self) -> list[int]:
        data = self.registers.get(SC_CONFIG)
        if not data or len(data) < 4:
            return []
        vals = []
        for i in range(0, len(data) - 1, 2):
            vals.append(struct.unpack(">H", data[i:i + 2])[0])
        return vals

    def get_measured_temps(self) -> dict[str, float] | None:
        """Get measured temperatures from SC=21 register (values in tenths C)."""
        vals = self._get_sc21_words()
        if len(vals) < 9:
            return None
        result = {}
        result["water_inlet"] = round(vals[1] / 10.0, 1)
        result["water_outlet"] = round(vals[2] / 10.0, 1)
        result["ambient"] = round(vals[3] / 10.0, 1)
        result["evaporator_coil"] = round(vals[6] / 10.0, 1)
        result["discharge_gas"] = round(vals[7] / 10.0, 1)
        result["return_gas"] = round(vals[8] / 10.0, 1)
        if len(vals) > 18:
            result["eev"] = vals[18]
        return result

    def get_working_details(self) -> dict[str, bool] | None:
        """Get working detail flags from SC=21 register."""
        vals = self._get_sc21_words()
        if len(vals) < 26:
            return None

        pump_info = vals[22]
        fault2 = vals[25]

        def bit(val, n):
            return (val >> n) & 1

        details = {}
        details["compressor"] = bool(bit(pump_info, 0))
        details["four_way_valve"] = bool(bit(pump_info, 11))
        details["high_fan"] = bool(bit(pump_info, 9) and bit(pump_info, 10))
        details["low_fan"] = bool(not bit(pump_info, 9) and bit(pump_info, 10))
        details["water_pump"] = bool(bit(pump_info, 7))
        details["electric_heater"] = bool(bit(pump_info, 4))
        details["bottom_heater"] = bool(bit(pump_info, 5))
        details["low_pressure"] = bool(bit(fault2, 7))
        details["high_pressure"] = bool(bit(fault2, 3))
        details["emergency_switch"] = bool(bit(fault2, 0))
        details["waterflow_switch"] = bool(bit(fault2, 2))
        details["phase_protection"] = bool(bit(fault2, 1))
        return details

    def get_mode(self) -> int | None:
        """Get current mode (0=auto, 1=cool, 2=heat)."""
        data = self.registers.get(SC_MODE)
        if data and len(data) >= 1:
            return data[0]
        return None

    def get_mode_name(self) -> str | None:
        mode = self.get_mode()
        if mode is not None:
            return MODE_NAMES.get(mode, f"Unknown({mode})")
        return None

    def is_power_on(self) -> bool | None:
        """Get power state."""
        data = self.registers.get(SC_POWER)
        if data and len(data) >= 1:
            return data[0] == 0x01
        return None

    def get_status(self) -> dict:
        """Get full parsed status as a dict."""
        status = {
            "power": self.is_power_on(),
            "mode": self.get_mode(),
            "mode_name": self.get_mode_name(),
            "set_temp": self.get_set_temp(),
            "temps": self.get_measured_temps(),
            "working_details": self.get_working_details(),
        }
        return status
