import argparse
import sys
from pathlib import Path

# Add project root to sys.path
root_dir = Path(__file__).resolve().parent.parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

from src.data.collector import DataCollector
from src.utils.logging_config import setup_logger

logger = setup_logger("quant_nifty.main")


def main():
    parser = argparse.ArgumentParser(description="QuantNifty Market Data Collector")
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run a single collection cycle and exit (useful for testing/cron).",
    )
    parser.add_argument(
        "--config",
        type=str,
        default="config/settings.yaml",
        help="Path to YAML settings file.",
    )
    args = parser.parse_args()

    collector = DataCollector(config_path=args.config)

    if args.once:
        logger.info("Executing single collection run...")
        collector.collect_once()
        logger.info("Single collection run complete.")
    else:
        collector.run()


if __name__ == "__main__":
    main()
