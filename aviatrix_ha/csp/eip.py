""" CSP calls related to elastic IP"""


def is_ip_elastic(ec2_client, ip_):
    """Check whether an IP address is an elastic IP"""
    try:
        ec2_client.describe_addresses(PublicIps=[ip_]).get("Addresses")[0].get(
            "AllocationId"
        )
    except Exception as err:
        if "InvalidAddress.NotFound" in str(err):
            print("EIP is not found")
        else:
            print(str(err))
        return False
    return True


def assign_eip(client, controller_instanceobj, eip):
    """Assign the EIP to the new instance"""
    cf_req = False
    try:
        if eip is None:
            cf_req = True
            eip = controller_instanceobj["NetworkInterfaces"][0]["Association"].get(
                "PublicIp"
            )
        eip_alloc_id = (
            client.describe_addresses(PublicIps=[eip])
            .get("Addresses")[0]
            .get("AllocationId")
        )
        client.associate_address(
            AllocationId=eip_alloc_id, InstanceId=controller_instanceobj["InstanceId"]
        )
    except Exception as err:
        if cf_req and "InvalidAddress.NotFound" in str(err):
            print(
                "EIP %s was not found. Please attach an EIP to the controller before enabling HA"
                % eip
            )
            return False
        print("Failed in assigning EIP %s" % str(err))
        return False
    else:
        print("Assigned/verified elastic IP")
        return True
