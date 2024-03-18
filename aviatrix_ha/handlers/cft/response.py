import json
from urllib.error import HTTPError
from urllib.request import build_opener, HTTPHandler, Request


def send_response(
    event,
    context,
    response_status,
    reason="",
    response_data=None,
    physical_resource_id=None,
):
    """Send response to cloud formation template for custom resource creation
    by cloud formation"""

    response_data = response_data or {}
    response_body = json.dumps(
        {
            "Status": response_status,
            "Reason": str(reason)
            + ". See the details in CloudWatch Log Stream: "
            + context.log_stream_name,
            "PhysicalResourceId": physical_resource_id or context.log_stream_name,
            "StackId": event["StackId"],
            "RequestId": event["RequestId"],
            "LogicalResourceId": event["LogicalResourceId"],
            "Data": response_data,
        }
    )
    opener = build_opener(HTTPHandler)
    request = Request(event["ResponseURL"], data=response_body.encode())
    request.add_header("Content-Type", "")
    request.add_header("Content-Length", len(response_body.encode()))
    request.get_method = lambda: "PUT"
    try:
        response = opener.open(request)
        print("Status code: {}".format(response.getcode()))
        print("Status message: {}".format(response.msg))
        return True
    except HTTPError as exc:
        print("Failed executing HTTP request: {}".format(exc.code))
        return False
