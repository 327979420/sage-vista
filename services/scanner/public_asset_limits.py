"""Validate the same lossless representation that the website build publishes."""
import gzip
import json
from pathlib import Path

POLICY = json.loads((Path(__file__).resolve().parents[1] / "automation/public-archive-policy.json").read_text())


def validate_asset(name, content):
    deployed = gzip.compress(content, compresslevel=9, mtime=0) if name in POLICY["archives"] else content
    if len(deployed) > POLICY["maxAssetBytes"]:
        raise ValueError(f"Asset exceeds the hosting limit: {name}")
    return len(deployed)
