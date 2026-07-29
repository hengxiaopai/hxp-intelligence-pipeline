"""Minimal-permission connector interfaces and offline simulator."""

from .registry import ConnectorRegistryError, load_connector_registry, select_connector
from .simulator import ConnectorSimulationError, execute_simulated_draft

__all__ = [
    "ConnectorRegistryError",
    "ConnectorSimulationError",
    "execute_simulated_draft",
    "load_connector_registry",
    "select_connector",
]
