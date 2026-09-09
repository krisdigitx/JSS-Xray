import json
import sys

from .config import settings
from .product_monitor import check_mapped_products, sync_tiktok_products


def main():
    product_sync = sync_tiktok_products(settings.tiktok_shop_slug)
    price_check = check_mapped_products(settings.tiktok_shop_slug)
    print(json.dumps({"product_sync": product_sync, "price_check": price_check}, indent=2))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"Product price monitor failed: {exc}", file=sys.stderr)
        raise
