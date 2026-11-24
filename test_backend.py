import json
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

import backend


class BackendTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(backend.app)

    def test_dataset_has_100_apps_across_10_categories(self):
        data = json.loads(Path("applications.json").read_text(encoding="utf-8"))
        self.assertEqual(len(data), 100)
        self.assertEqual(len({item["category"] for item in data}), 10)
        self.assertTrue(all(item["app_name"] for item in data))

    def test_overview_returns_totals(self):
        response = self.client.get("/api/overview")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["totals"]["total"], 100)
        self.assertEqual(len(body["categories"]), 10)

    def test_application_search_and_detail(self):
        search = self.client.get("/api/applications", params={"search": "GitHub"})
        self.assertEqual(search.status_code, 200)
        rows = search.json()
        self.assertTrue(any(row["app_name"] == "GitHub" for row in rows))

        detail = self.client.get("/api/applications/1")
        self.assertIn(detail.status_code, (200, 404))

    def test_scope_validation(self):
        invalid = self.client.post("/api/research", json={"scope": "unknown"})
        self.assertEqual(invalid.status_code, 422)

        missing_name = self.client.post("/api/research", json={"scope": "category"})
        self.assertEqual(missing_name.status_code, 422)

    def test_json_export(self):
        response = self.client.get("/api/export.json")
        self.assertEqual(response.status_code, 200)
        self.assertIn("filename", response.headers.get("content-disposition", "").lower())


if __name__ == "__main__":
    unittest.main()
