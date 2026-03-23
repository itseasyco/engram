"""
Example community connector template.

To create a community connector:
1. Copy this directory as openclaw-lacp-connector-<your-type>/
2. Edit connector.json with your connector's metadata
3. Implement the Connector methods below
4. Publish to npm: npm publish
5. Users install with: openclaw plugins install openclaw-lacp-connector-<your-type>
"""

from __future__ import annotations

from typing import Any

# Import from the main plugin (available at runtime)
import sys
from pathlib import Path

# The base classes are available when the connector is loaded by the registry
try:
    from lib.connectors.base import Connector, ConnectorStatus, RawData, VaultNote
except ImportError:
    # Fallback for standalone testing
    from plugin.lib.connectors.base import Connector, ConnectorStatus, RawData, VaultNote


class ExampleConnector(Connector):
    """
    Example community connector.

    Replace this with your actual connector implementation.
    The class name MUST be <Type>Connector in PascalCase
    (e.g. NotionConnector, LinearConnector).
    """

    type = "example"

    def __init__(self, config: dict[str, Any]):
        super().__init__(config)
        self._api_token: str = self.connector_config.get("api_token", "")

    def authenticate(self) -> bool:
        """Verify the API token is valid."""
        return bool(self._api_token)

    def pull(self) -> list[RawData]:
        """Fetch new data from the external source."""
        # TODO: Implement your pull logic here
        # Return a list of RawData objects
        return []

    def transform(self, raw_data: RawData) -> VaultNote:
        """Convert raw data into a vault note."""
        return VaultNote(
            title=raw_data.payload.get("title", "Untitled"),
            body=raw_data.payload.get("body", ""),
            source_connector=self.id,
            source_type=self.type,
            source_id=raw_data.source_id,
            trust_level=self.trust_level,
            landing_zone=self.landing_zone,
        )

    def health_check(self) -> ConnectorStatus:
        """Return connector health status."""
        return self.base_status(healthy=bool(self._api_token))
