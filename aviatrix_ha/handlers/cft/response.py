from typing import Any

import requests


def send_response(
    event: dict[str, str],
    context: Any,
    response_status: str,
    reason: str = "",
    response_data: dict[str, str] | None = None,
    physical_resource_id: str | None = None,
) -> bool:
    """Send response to cloud formation template for custom resource creation
    by cloud formation"""

    response_data = response_data or {}
    response_body = {
        "Status": response_status,
        "Reason": str(reason)
        + ". See the details in CloudWatch Log Stream: "
        + context.log_stream_name,
        "PhysicalResourceId": physical_resource_id,
        "StackId": event["StackId"],
        "RequestId": event["RequestId"],
        "LogicalResourceId": event["LogicalResourceId"],
        "Data": response_data,
    }

    try:
        requests.put(
            event["ResponseURL"],
            json=response_body,
            headers={"Content-Type": "application/json"},
            timeout=10,
        )
        return True
    except requests.exceptions.RequestException as exc:
        print("Failed executing HTTP request: {}".format(exc))
        return False
