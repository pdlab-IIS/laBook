"""Exercise URL versioning without loading the application or its database."""
import ast
import hashlib
import tempfile
import unittest
from functools import lru_cache
from pathlib import Path
from types import SimpleNamespace


class StaticRevisionTests(unittest.TestCase):
    def test_versions_follow_file_changes_and_replace_manual_tags(self):
        tree = ast.parse((Path(__file__).resolve().parents[1] / 'app.py').read_text(encoding='utf-8'))
        functions = [node for node in tree.body if isinstance(node, ast.FunctionDef)
                     and node.name in ('static_revision', 'version_static_urls')]
        functions[1].decorator_list = []
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'static').mkdir()
            file = root / 'static/app.js'
            file.write_text('first', encoding='utf-8')
            app = SimpleNamespace(root_path=directory, debug=False)
            scope = dict(Path=Path, hashlib=hashlib, lru_cache=lru_cache, app=app)
            exec(compile(ast.Module(body=functions, type_ignores=[]), 'versioning', 'exec'), scope)
            version = scope['version_static_urls']
            values = {'filename': 'app.js', 'v': 'old-manual-tag'}
            version('static', values)
            self.assertEqual(values['v'], hashlib.sha256(b'first').hexdigest()[:16])
            file.write_text('second content', encoding='utf-8')
            updated = {'filename': 'app.js'}
            version('static', updated)
            self.assertNotEqual(values['v'], updated['v'])
            for endpoint, filename in [('other', 'app.js'), ('static', '../outside.js'), ('static', 'missing.js')]:
                omitted = {'filename': filename}
                version(endpoint, omitted)
                self.assertNotIn('v', omitted)
            app.debug = True
            omitted = {'filename': 'app.js'}
            version('static', omitted)
            self.assertNotIn('v', omitted)


if __name__ == '__main__':
    unittest.main()
