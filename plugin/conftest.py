"""Root conftest — set OPENCLAW_PLUGIN_DIR so tests find neo4j-config.json."""

import os
from pathlib import Path

# Point to this plugin directory so graph_db.py finds config/neo4j-config.json
os.environ.setdefault("OPENCLAW_PLUGIN_DIR", str(Path(__file__).parent))
