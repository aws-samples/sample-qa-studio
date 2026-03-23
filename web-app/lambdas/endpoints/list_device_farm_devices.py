"""
List available Device Farm devices for mobile testing.

Returns devices filtered by platform (ANDROID/IOS) with remote access enabled.
Device Farm only operates in us-west-2.
"""

import json
import logging
from typing import Any, Dict

import boto3

from utils import create_response, require_scopes

logger = logging.getLogger()
logger.setLevel(logging.INFO)

DEVICE_FARM_REGION = "us-west-2"


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    user_identity, error_response = require_scopes(event, ["api/usecases.read"])
    if error_response:
        return error_response

    # Optional platform filter from query string
    params = event.get("queryStringParameters") or {}
    platform_filter = params.get("platform", "").upper()  # ANDROID or IOS

    try:
        df_client = boto3.client("devicefarm", region_name=DEVICE_FARM_REGION)

        # Paginate — Device Farm can return 60+ devices
        devices = []
        paginator = df_client.get_paginator("list_devices")
        for page in paginator.paginate():
            devices.extend(page.get("devices", []))

        results = []
        for d in devices:
            if not d.get("remoteAccessEnabled"):
                continue
            platform = d.get("platform", "")
            if platform_filter and platform != platform_filter:
                continue

            results.append({
                "arn": d.get("arn", ""),
                "name": d.get("name", ""),
                "platform": platform,
                "os": d.get("os", ""),
                "formFactor": d.get("formFactor", ""),
                "manufacturer": d.get("manufacturer", ""),
                "modelId": d.get("modelId", ""),
                "availability": d.get("availability", ""),
            })

        # Sort: newest OS first
        results.sort(key=lambda x: x["os"], reverse=True)

        return create_response(200, {"devices": results})

    except Exception as e:
        logger.error(f"Failed to list Device Farm devices: {e}", exc_info=True)
        return create_response(500, {"error": "Failed to list devices"})
