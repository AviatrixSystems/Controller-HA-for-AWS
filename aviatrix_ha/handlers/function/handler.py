import logging
import os
from typing import Any

from aviatrix_ha.csp.s3 import retrieve_controller_version
from aviatrix_ha.errors.exceptions import AvxError

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def handle_function_event(
    event: dict[str, Any], context: dict[str, Any]
) -> dict[str, Any]:
    """Handle lambda function event"""
    headers = event["headers"]
    request = event["requestContext"].get("http", {})
    method = request.get("method", "<unknown>")
    path = request.get("path", "<unknown>")

    logger.info(
        "Function request from %s: method=%s path=%s user-agent=%s",
        request.get("sourceIp", "<unknown>"),
        method,
        path,
        headers.get("user-agent", "<unknown>"),
    )

    if method != "GET" or path != "/controller_version":
        return {
            "statusCode": 404,
            "body": "Not Found",
            "headers": {"Content-Type": "text/plain"},
        }

    # This private IP belongs to older terminated instance
    priv_ip = os.environ.get("PRIV_IP")
    version_filename = f"CloudN_{priv_ip}_save_cloudx_version.txt"

    try:
        _, full_version = retrieve_controller_version(version_filename)
    except AvxError as err:
        logger.exception("Failed to retrieve controller version: %s", err)
        return {
            "statusCode": 500,
            "body": "Internal Server Error",
            "headers": {"Content-Type": "text/plain"},
        }

    return {
        "statusCode": 200,
        "body": full_version,
        "headers": {"Content-Type": "text/plain"},
    }
