import json

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, override_settings

CSV = b"ID,Name,Comment\n1, Ada ,Great <b>product</b>!!! Would buy again for sure.\n2,Ada,great product would buy again for sure\n3,N/A,Totally different review about slow delivery times.\n"


def upload(name="data.csv", content=CSV):
    return SimpleUploadedFile(name, content)


class CleanApiTests(SimpleTestCase):
    def test_health(self):
        self.assertEqual(self.client.get("/api/health/").json(), {"status": "ok"})

    def test_clean_returns_rows_and_report(self):
        res = self.client.post("/api/clean/", {"file": upload(), "config": json.dumps({"text_columns": ["Comment"]})})
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertEqual(body["report"]["rows_in"], 3)
        self.assertEqual(body["report"]["duplicates_removed"], 1)
        self.assertEqual(len(body["rows"]), 2)
        self.assertEqual(body["rows"][0]["comment_clean"], "great product!! would buy again for sure.")
        self.assertIsNone(body["rows"][1]["name"])

    def test_csv_download(self):
        res = self.client.post("/api/clean/?download=csv", {"file": upload()})
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res["Content-Type"].startswith("text/csv"))
        self.assertTrue(res.content.decode().startswith("id,name,comment"))

    def test_json_upload(self):
        payload = json.dumps([{"a": 1, "b": "x"}, {"a": 1, "b": "x"}]).encode()
        res = self.client.post("/api/clean/", {"file": upload("d.json", payload)})
        self.assertEqual(len(res.json()["rows"]), 1)

    def test_errors(self):
        self.assertEqual(self.client.post("/api/clean/").status_code, 400)
        self.assertEqual(self.client.get("/api/clean/").status_code, 405)
        self.assertEqual(self.client.post("/api/clean/", {"file": upload("x.pdf")}).status_code, 400)
        self.assertEqual(self.client.post("/api/clean/", {"file": upload(), "config": "{bad"}).status_code, 400)
        self.assertEqual(self.client.post("/api/clean/", {"file": upload(), "config": '{"nope": 1}'}).status_code, 400)
        self.assertEqual(self.client.post("/api/clean/", {"file": upload("x.xlsx", b"not excel")}).status_code, 400)

    @override_settings(CLEANER_API_KEY="secret")
    def test_api_key(self):
        self.assertEqual(self.client.post("/api/clean/", {"file": upload()}).status_code, 401)
        self.assertEqual(self.client.post("/api/clean/", {"file": upload()}, headers={"X-API-Key": "secret"}).status_code, 200)
