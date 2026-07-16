from pathlib import Path


APP_DIR = Path(__file__).resolve().parent
PROJECT_DIR = APP_DIR.parent
CONFIG_DIR = PROJECT_DIR / "config"
WORKFLOW_CONFIG = CONFIG_DIR / "config_gcode_workflow.json"
VISUAL_OBJECT_CONFIG = CONFIG_DIR / "config_visual_objects.json"
ASSETS_DIR = PROJECT_DIR / "assets"
IMAGE_DIR = ASSETS_DIR / "images"
OUTPUT_DIR = PROJECT_DIR / "output"
GCODE_DIR = OUTPUT_DIR / "gcodes"
LOG_DIR = PROJECT_DIR / "logs"


def ensure_runtime_dirs():
    for path in (GCODE_DIR, LOG_DIR):
        path.mkdir(parents=True, exist_ok=True)
