from pathlib import Path


BASE_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = BASE_DIR / "data"
LOG_DIR = BASE_DIR / "logs"

PRODUCTS_PATH = DATA_DIR / "products.json"
INVENTORY_PATH = DATA_DIR / "inventory.json"
STATE_PATH = DATA_DIR / "station_state.json"
ERP_SNAPSHOT_PATH = DATA_DIR / "erp_snapshot.json"
MQTT_CONFIG_PATH = DATA_DIR / "mqtt_config.json"
EVENT_LOG_PATH = LOG_DIR / "assembly_events.jsonl"

DISPLAY_LINE_COUNT = 6
DISPLAY_LINE_WIDTH = 14
