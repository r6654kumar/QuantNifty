import argparse
import sys
from pathlib import Path
import uvicorn

# Add project root to sys.path
root_dir = Path(__file__).resolve().parent.parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

from src.utils.logging_config import setup_logger

logger = setup_logger("quant_nifty.server")


def main():
    parser = argparse.ArgumentParser(description="QuantNifty Dashboard Server")
    parser.add_argument("--host", type=str, default="127.0.0.1", help="Host address to bind.")
    parser.add_argument("--port", type=int, default=8000, help="Port to listen on.")
    parser.add_argument("--reload", action="store_true", help="Enable live code reload.")
    args = parser.parse_args()

    logger.info(f"Starting QuantNifty Web Dashboard at http://{args.host}:{args.port}")
    uvicorn.run("src.api.main:app", host=args.host, port=args.port, reload=args.reload)


if __name__ == "__main__":
    main()
