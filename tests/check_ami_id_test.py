"""Tests for aviatrix_ha.api.external.ami."""
import unittest

import responses

from aviatrix_ha.api.external import ami


class TestCheckAmiId(unittest.TestCase):
    @responses.activate
    def test_check_ami_id(self):
        """Check cases where AMI ID data is returned."""
        responses.add(
            responses.GET,
            ami.AMI_ID,
            json={
                "BYOL": {
                    "us-east-1": "ami-03c5c2226878f03c4",
                    "us-east-2": "ami-0acedd29dab20cc5a",
                },
                "Metered": {
                    "us-east-1": "ami-06ebb151f753c54a8",
                    "us-east-2": "ami-0c3e2aa105b6fe227",
                },
            },
        )
        self.assertTrue(ami.check_ami_id("ami-03c5c2226878f03c4"))
        self.assertFalse(ami.check_ami_id("ami-03c5c2226878f03c5"))

    @responses.activate
    def test_check_ami_id_http_404(self):
        """Check cases where the HTTP request fails."""
        responses.add(
            responses.GET,
            ami.AMI_ID,
            status=404,
        )
        self.assertFalse(ami.check_ami_id("ami-03c5c2226878f03c4"))
