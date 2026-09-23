import json
import re
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

from app import app
from db import initialize_database


class GatewayPrefixTests(unittest.TestCase):
    def test_pages_generate_urls_under_both_legacy_and_gateway_roots(self):
        with tempfile.TemporaryDirectory() as folder:
            database = Path(folder) / 'test.db'
            initialize_database(database)
            with patch('db.DATABASE', str(database)):
                client = app.test_client()
                client.post('/books', json={'isbn': 100, 'title': 'Test', 'cover_image_path': 'covers/test.jpg'})
                for prefix, authenticated in [('', False), ('/labook', True), ('/trial/index.php', True)]:
                    for path in ['/', '/books/manage?isbn=100', '/users/manage', '/scan/ABC']:
                        with self.subTest(prefix=prefix, path=path):
                            response = client.get(path, environ_overrides={'SCRIPT_NAME': prefix,
                                'labook.gateway_authenticated': authenticated})
                            self.assertEqual(response.status_code, 200)
                            html = response.get_data(as_text=True)
                            config = json.loads(re.search(r'id="labook-runtime" type="application/json">(.*?)</script>', html).group(1))
                            self.assertEqual((config['prefix'], config['gateway']), (prefix, authenticated))
                            for target in re.findall(r'(?:src|href)="(/[^"#]*)"', html):
                                self.assertTrue(target.startswith(prefix + '/'), target)
                            self.assertIn(prefix + '/static/runtime.js', html)
                            if path.startswith('/books/manage'):
                                self.assertIn(prefix + '/covers/test.jpg', html)


if __name__ == '__main__':
    unittest.main()
