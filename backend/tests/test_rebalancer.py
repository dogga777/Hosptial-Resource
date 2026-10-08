import unittest

from backend.rebalancer import plan_oxygen_transfers
from backend.routes.api import database_error_detail, find_uncovered_shortages
from pymongo.errors import ConfigurationError, OperationFailure, ServerSelectionTimeoutError


class RebalancerTests(unittest.TestCase):
    def setUp(self):
        self.hospitals = [
            {
                "_id": "receiver",
                "name": "Hospital A",
                "resources": {"oxygenCylinders": 35},
                "consumptionRate": {"oxygen": 18},
            },
            {
                "_id": "donor",
                "name": "Hospital C",
                "resources": {"oxygenCylinders": 200},
                "consumptionRate": {"oxygen": 3},
            },
        ]

    def test_transfer_restores_target_and_preserves_donor_reserve(self):
        plans = plan_oxygen_transfers(self.hospitals)

        self.assertEqual(len(plans), 1)
        self.assertEqual(plans[0]["quantity"], 73)
        self.assertEqual(
            self.hospitals[1]["resources"]["oxygenCylinders"] - plans[0]["quantity"],
            127,
        )

    def test_no_transfer_when_receiver_has_enough_stock(self):
        self.hospitals[0]["resources"]["oxygenCylinders"] = 108

        self.assertEqual(plan_oxygen_transfers(self.hospitals), [])

    def test_uncovered_shortage_is_reported(self):
        hospitals = [
            {
                "hospital_name": "Hospital A",
                "stock": 10,
                "consumption_rate": 5,
            }
        ]

        self.assertEqual(
            find_uncovered_shortages(hospitals, []),
            [{"hospital_name": "Hospital A", "hours_remaining": 2.0}],
        )


class DatabaseDiagnosticTests(unittest.TestCase):
    def test_missing_mongo_uri_has_specific_help(self):
        from backend import database

        original = database.MONGO_URI_CONFIGURED
        database.MONGO_URI_CONFIGURED = False
        try:
            self.assertIn("MONGO_URI is not configured", database_error_detail(RuntimeError()))
        finally:
            database.MONGO_URI_CONFIGURED = original

    def test_authentication_failure_has_specific_help(self):
        error = OperationFailure("credentials rejected", code=18)

        self.assertIn("database user", database_error_detail(error))

    def test_server_timeout_has_network_access_help(self):
        error = ServerSelectionTimeoutError("connection timed out")

        self.assertIn("Atlas Network Access", database_error_detail(error))

    def test_invalid_uri_has_configuration_help(self):
        error = ConfigurationError("invalid URI")

        self.assertIn("MONGO_URI is invalid", database_error_detail(error))


if __name__ == "__main__":
    unittest.main()
