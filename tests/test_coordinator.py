"""Tests for Pool Comfort session coordination."""

from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path
from types import ModuleType
from unittest.mock import Mock, call


class _ConfigEntry:
    """Minimal ConfigEntry used by the coordinator constructor."""

    def __init__(self, data: dict[str, str]) -> None:
        self.data = data


class _DataUpdateCoordinator:
    """Minimal generic-compatible DataUpdateCoordinator."""

    def __class_getitem__(cls, item):
        return cls

    def __init__(self, hass, *args, **kwargs) -> None:
        self.hass = hass
        self.data = None


class _UpdateFailed(Exception):
    """Test replacement for Home Assistant's UpdateFailed."""


def _install_home_assistant_stubs() -> None:
    """Install the small subset of Home Assistant imported by coordinator.py."""
    modules = {
        "homeassistant": ModuleType("homeassistant"),
        "homeassistant.config_entries": ModuleType("homeassistant.config_entries"),
        "homeassistant.core": ModuleType("homeassistant.core"),
        "homeassistant.helpers": ModuleType("homeassistant.helpers"),
        "homeassistant.helpers.update_coordinator": ModuleType(
            "homeassistant.helpers.update_coordinator"
        ),
    }
    modules["homeassistant.config_entries"].ConfigEntry = _ConfigEntry
    modules["homeassistant.core"].HomeAssistant = object
    update_module = modules["homeassistant.helpers.update_coordinator"]
    update_module.DataUpdateCoordinator = _DataUpdateCoordinator
    update_module.UpdateFailed = _UpdateFailed
    sys.modules.update(modules)


def _load_integration_module(name: str) -> ModuleType:
    """Load an integration module under a test-only package name."""
    root = Path(__file__).parents[1] / "custom_components/pool_comfort"
    package_name = "pool_comfort_test"
    if package_name not in sys.modules:
        package = ModuleType(package_name)
        package.__path__ = [str(root)]
        sys.modules[package_name] = package

    path = root / f"{name}.py"
    module_name = f"{package_name}.{name}"
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


_install_home_assistant_stubs()
const_module = _load_integration_module("const")
api_module = _load_integration_module("api")
coordinator_module = _load_integration_module("coordinator")


class FreshSessionCoordinatorTest(unittest.TestCase):
    """Test fresh-session and retry behavior."""

    def _coordinator(self, host: str = "192.0.2.10"):
        entry = _ConfigEntry(
            {
                const_module.CONF_SERIAL: "123456789012",
                const_module.CONF_PASSWORD: "123456",
                const_module.CONF_HOST: host,
            }
        )
        coordinator = coordinator_module.PoolComfortCoordinator(object(), entry)
        coordinator.api = Mock()
        return coordinator

    def test_poll_retries_with_an_entirely_fresh_local_session(self) -> None:
        """An isolated missed poll is retried before state becomes unavailable."""
        coordinator = self._coordinator()
        coordinator.api.query_all_registers.side_effect = (
            api_module.PoolComfortConnectionError("missed packet"),
            {},
        )
        coordinator.api.get_status.return_value = {"power": True}

        result = coordinator._sync_update()

        self.assertEqual({"power": True}, result)
        self.assertEqual(
            [call("192.0.2.10", const_module.LOCAL_UDP_PORT)] * 2,
            coordinator.api.connect.call_args_list,
        )
        self.assertEqual(4, coordinator.api.close.call_count)
        coordinator.api.process_incoming.assert_called_once_with(timeout=1)

    def test_command_is_wrapped_in_its_own_session(self) -> None:
        """A command connects and closes while holding the coordinator lock."""
        coordinator = self._coordinator()
        events = Mock()
        events.attach_mock(coordinator.api.close, "close")
        events.attach_mock(coordinator.api.connect, "connect")
        events.attach_mock(coordinator.api.set_power, "set_power")
        coordinator.api.set_power.return_value = True

        acknowledged = coordinator.set_power(True)

        self.assertTrue(acknowledged)
        self.assertEqual(
            [
                call.close(),
                call.connect("192.0.2.10", const_module.LOCAL_UDP_PORT),
                call.set_power(True),
                call.close(),
            ],
            events.mock_calls,
        )

    def test_empty_host_uses_cloud_discovery(self) -> None:
        """An empty optional host preserves cloud relay mode."""
        coordinator = self._coordinator(host="")
        coordinator.api.get_status.return_value = {}

        coordinator._sync_update()

        coordinator.api.connect.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
