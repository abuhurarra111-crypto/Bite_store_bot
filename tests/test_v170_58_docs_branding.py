"""Offline regression tests for the v170.58 Alex Store API-docs branding."""

import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# Test-only configuration before modules that import config/database.
os.environ["BOT_TOKEN"] = "test-token-not-real"
os.environ["ADMIN_ID"] = "424242"
_IMPORT_TEMP = tempfile.TemporaryDirectory()
os.environ["DB_PATH"] = str(Path(_IMPORT_TEMP.name) / "import.db")

import reseller_api


@unittest.skipUnless(reseller_api._FASTAPI_OK, "FastAPI is unavailable in this environment")
class DocsBrandingTests(unittest.TestCase):
    def test_docs_html_uses_versioned_alex_logo_and_favicon(self):
        html = reseller_api._DOCS_HTML
        self.assertIn('/static/alex_store_docs_logo.png?v=170.58', html)
        self.assertIn('/static/alex_store_docs_favicon.png?v=170.58', html)
        self.assertIn('rel="apple-touch-icon"', html)
        self.assertIn('alt="Alex Store logo"', html)
        self.assertNotIn('/static/reseller_docs_logo.png"', html)

    def test_logo_and_favicon_routes_serve_owner_brand_assets(self):
        from fastapi.testclient import TestClient
        logo_path = ROOT / "alex_store_docs_logo.png"
        favicon_path = ROOT / "alex_store_docs_favicon.png"
        self.assertTrue(logo_path.is_file())
        self.assertTrue(favicon_path.is_file())

        client = TestClient(reseller_api.app)
        docs = client.get("/docs")
        logo = client.get("/static/alex_store_docs_logo.png")
        favicon = client.get("/static/alex_store_docs_favicon.png")
        browser_favicon = client.get("/favicon.ico")
        self.assertEqual(docs.status_code, 200)
        self.assertIn("alex_store_docs_logo.png?v=170.58", docs.text)
        self.assertEqual(logo.headers.get("content-type"), "image/png")
        self.assertEqual(favicon.headers.get("content-type"), "image/png")
        self.assertEqual(logo.content, logo_path.read_bytes())
        self.assertEqual(favicon.content, favicon_path.read_bytes())
        self.assertEqual(browser_favicon.content, favicon_path.read_bytes())

    def test_brand_assets_have_sensible_png_dimensions(self):
        from PIL import Image
        with Image.open(ROOT / "alex_store_docs_logo.png") as logo:
            self.assertEqual(logo.format, "PNG")
            self.assertGreaterEqual(logo.width, 300)
            self.assertGreaterEqual(logo.height, 450)
        with Image.open(ROOT / "alex_store_docs_favicon.png") as favicon:
            self.assertEqual(favicon.format, "PNG")
            self.assertEqual(favicon.size, (192, 192))


if __name__ == "__main__":
    unittest.main(verbosity=2)
