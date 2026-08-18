"""Tests for the low-level Pool Comfort UDP client."""

from __future__ import annotations

import importlib.util
import struct
import unittest
from pathlib import Path
from types import ModuleType
from unittest.mock import Mock


def _load_api_module() -> ModuleType:
    """Load api.py without importing the Home Assistant package initializer."""
    path = Path(__file__).parents[1] / "custom_components/pool_comfort/api.py"
    spec = importlib.util.spec_from_file_location("pool_comfort_api", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


api_module = _load_api_module()
OBJ_TYPE = api_module.OBJ_TYPE
SC_CONFIG = api_module.SC_CONFIG
SC_MODE = api_module.SC_MODE
SC_POWER = api_module.SC_POWER
SC_TEMP = api_module.SC_TEMP
PoolComfort = api_module.PoolComfort
PoolComfortConnectionError = api_module.PoolComfortConnectionError


def _register_packet(registers: dict[int, bytes]) -> bytes:
    """Build the relevant portion of an Alsavo register response."""
    payload = bytes((0x08, len(registers), 0x00, 0x00))
    for sc, value in registers.items():
        payload += struct.pack(">IHH", OBJ_TYPE, sc, len(value)) + value
    return bytes(16) + payload


def _complete_status_packet() -> bytes:
    """Build a response containing every register required by get_status()."""
    return _register_packet(
        {
            SC_CONFIG: bytes(68),
            SC_TEMP: b"\x00\x1c\x00\x00",
            SC_MODE: b"\x02\x00\x00\x00",
            SC_POWER: b"\x01\x00\x00\x00",
        }
    )


class QueryAllRegistersTest(unittest.TestCase):
    """Test full register reads."""

    def setUp(self) -> None:
        self.api = PoolComfort("123456789012", "123456")
        self.api.csid = 1
        self.api.dsid = 2
        self.api._send = Mock()

    def test_raises_after_two_empty_reads(self) -> None:
        """A dead session must not return stale cached state."""
        self.api.registers[SC_POWER] = b"\x01\x00\x00\x00"
        self.api._recv_all = Mock(side_effect=([], []))

        with self.assertRaises(PoolComfortConnectionError):
            self.api.query_all_registers()

        self.assertEqual({}, self.api.registers)
        self.assertEqual(2, self.api._send.call_count)

    def test_retry_returns_fresh_registers(self) -> None:
        """A response to the built-in retry is parsed normally."""
        packet = _complete_status_packet()
        self.api._recv_all = Mock(side_effect=([], [packet]))

        registers = self.api.query_all_registers()

        self.assertEqual(b"\x01\x00\x00\x00", registers[SC_POWER])
        self.assertEqual(2, self.api._send.call_count)

    def test_retries_then_raises_for_irrelevant_packets(self) -> None:
        """Unrelated UDP traffic must not make the poll look successful."""
        irrelevant = bytes(32)
        self.api._recv_all = Mock(side_effect=([irrelevant], [irrelevant]))

        with self.assertRaisesRegex(
            PoolComfortConnectionError, "Incomplete register response"
        ):
            self.api.query_all_registers()

        self.assertEqual(2, self.api._send.call_count)

    def test_retries_then_raises_for_partial_status(self) -> None:
        """A partial register set must not publish an available refresh."""
        partial = _register_packet({SC_POWER: b"\x01\x00\x00\x00"})
        self.api._recv_all = Mock(side_effect=([partial], [partial]))

        with self.assertRaisesRegex(
            PoolComfortConnectionError, "missing registers: 21, 22, 23"
        ):
            self.api.query_all_registers()

        self.assertEqual({}, self.api.registers)


class SetCommandTest(unittest.TestCase):
    """Test command acknowledgement handling."""

    def test_missing_ack_is_logged(self) -> None:
        """An unacknowledged command is visible in logs."""
        api = PoolComfort("123456789012", "123456")
        api.csid = 1
        api.dsid = 2
        api._send = Mock()
        api._recv_all = Mock(return_value=[])

        with self.assertLogs("pool_comfort_api", level="WARNING") as logs:
            acknowledged = api.set_power(True)

        self.assertFalse(acknowledged)
        self.assertIn("did not acknowledge", logs.output[0])


if __name__ == "__main__":
    unittest.main()
