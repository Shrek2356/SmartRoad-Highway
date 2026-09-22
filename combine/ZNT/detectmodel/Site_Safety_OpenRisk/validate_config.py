from __future__ import annotations

import argparse
from pathlib import Path

from site_safety.factory import build_inspector
from site_safety.utils.config import load_yaml


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="configs/road_offline.yaml")
    args = parser.parse_args()
    root = Path(__file__).resolve().parent
    config = load_yaml(root / args.config)
    build_inspector(config, root)
    print("Configuration and adapters loaded successfully.")


if __name__ == "__main__":
    main()
