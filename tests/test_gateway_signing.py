import concurrent.futures
import tempfile
import unittest
from pathlib import Path

from gateway.signing import RejectedRequest, sign_request, verify_request


SECRET = b'test-only-key-never-use-in-deploy!'
REQUEST = dict(key_id='test-key', method='PATCH', target='/books/bulk?q=%E6%9C%AC&a=1&a=2',
               content_type='application/json', body=b'{"ids":[1,2]}', timestamp='2000000000',
               nonce='a' * 32, subject='test-subject')


def consume(database):
    try:
        verify_request(SECRET, sign_request(SECRET, **REQUEST), database, now=2000000000, **REQUEST)
        return True
    except RejectedRequest:
        return False


class GatewaySigningTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.database = str(Path(self.temp.name) / 'nonce.sqlite')

    def test_valid_then_replay_rejected(self):
        self.assertTrue(consume(self.database))
        self.assertFalse(consume(self.database))

    def test_parallel_processes_consume_once(self):
        with concurrent.futures.ProcessPoolExecutor(max_workers=4) as executor:
            results = list(executor.map(consume, [self.database] * 8))
        self.assertEqual(sum(results), 1)

    def test_each_signed_field_is_bound(self):
        signature = sign_request(SECRET, **REQUEST)
        changes = dict(key_id='other', method='PUT', target='/users', content_type='text/plain',
                       body=b'other', timestamp='2000000001', nonce='b' * 32, subject='other')
        for key, value in changes.items():
            with self.subTest(key=key), self.assertRaises(RejectedRequest):
                verify_request(SECRET, signature, self.database, now=2000000000,
                               **(REQUEST | {key: value}))
        self.assertTrue(consume(self.database), 'invalid requests must not consume nonce')

    def test_old_and_future_requests_rejected(self):
        for now in [1999999939, 2000000061]:
            with self.subTest(now=now), self.assertRaises(RejectedRequest):
                verify_request(SECRET, sign_request(SECRET, **REQUEST), self.database, now=now, **REQUEST)

    def test_control_characters_and_bad_targets_rejected(self):
        for change in [{'subject': 'user\nadmin'}, {'target': '//outside.invalid/x'},
                       {'target': '/x#fragment'}, {'content_type': 'text/plain\r\nX:1'},
                       {'nonce': 'short'}, {'method': 'CONNECT'}]:
            with self.subTest(change=change), self.assertRaises(RejectedRequest):
                sign_request(SECRET, **(REQUEST | change))

    def test_storage_failure_and_wrong_key_fail_closed(self):
        signature = sign_request(SECRET, **REQUEST)
        with self.assertRaises(RejectedRequest):
            verify_request(SECRET, signature, self.temp.name, now=2000000000, **REQUEST)
        with self.assertRaises(RejectedRequest):
            verify_request(b'x' * 32, signature, self.database, now=2000000000, **REQUEST)


if __name__ == '__main__':
    unittest.main()
