#!/usr/bin/env python3
"""Export OpenAPI spec from FastAPI app for static documentation."""
import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.main import app

spec = app.openapi()
output_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "openapi.json")

with open(output_path, "w") as f:
    json.dump(spec, f, indent=2)

print(f"OpenAPI spec exported to {output_path}")
print(f"Endpoints: {len(spec.get('paths', {}))} paths")
