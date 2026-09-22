from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

from site_safety.factory import build_inspector
from site_safety.utils.config import load_yaml


def make_demo_image(path: Path) -> None:
    image = Image.new("RGB", (960, 640), (185, 190, 195))
    draw = ImageDraw.Draw(image)
    draw.polygon([(280,0),(680,0),(950,640),(10,640)], fill=(65,65,65))
    draw.line((480,0,480,640), fill=(240,240,220), width=6)
    draw.rectangle((550,430,610,470), fill=(120,80,50))
    image.save(path, quality=92)


def main() -> None:
    root = Path(__file__).resolve().parent
    image_path = root / "sample_data" / "demo_road.jpg"
    image_path.parent.mkdir(exist_ok=True)
    make_demo_image(image_path)
    config = load_yaml(root / "configs" / "road_demo.yaml")
    config["mllm"]["backend"] = "mock"
    config["sam3"]["backend"] = "mock"
    config["clip"]["enabled"] = False
    config["clip"]["backend"] = "mock"
    inspector = build_inspector(config, root)
    result = inspector.inspect(image_path, root / "outputs" / "road_mock_demo")
    print("Mock demo completed:")
    print(root / "outputs" / "road_mock_demo" / "summary.md")
    print(result.final_report.overall_summary if result.final_report else "No final report")


if __name__ == "__main__":
    main()
