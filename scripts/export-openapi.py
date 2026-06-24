#!/usr/bin/env python3
"""Export the current OpenAPI spec to apps/web_api/openapi.json.

Run after changing any API route or schema:
    python scripts/export-openapi.py
    git add apps/web_api/openapi.json
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from apps.web_api.api.main import app

output = Path(__file__).parent.parent / "apps" / "web_api" / "openapi.json"
spec = app.openapi()
output.write_text(json.dumps(spec, indent=2) + "\n")
print(f"Exported {len(spec['paths'])} paths → {output}")
