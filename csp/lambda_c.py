import botocore

from errors.exceptions import AvxError


def wait_function_update_successful(lambda_client, function_name,
                                    raise_err=False):
    """ Wait until get_function_configuration LastUpdateStatus=Successful """
    # https://aws.amazon.com/blogs/compute/coming-soon-expansion-of-aws-lambda-states-to-all-functions/
    try:
        waiter = lambda_client.get_waiter("function_updated")
        print(f"Waiting for function update to be successful: {function_name}")
        waiter.wait(FunctionName=function_name)
        print(f"{function_name} update state is successful")
    except botocore.exceptions.WaiterError as err:
        print(str(err))
        if raise_err:
            raise AvxError(str(err)) from err