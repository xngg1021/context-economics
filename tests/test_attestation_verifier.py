import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import attestation_verifier as av
from provider_runtime import digest


class AttestationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.directory = Path(self.tmp.name)
        for name in av.BOUND_FILES.values():
            (self.directory / name).write_text('{}')
        self.a = {**av.directory_digests(self.directory), 'attester_id': 'independent-fixture',
                  'issued_at': '2026-01-01T00:00:00Z', 'signature_or_external_ref': 'offline:fixture',
                  'trust_root_id': 'test-only-root'}
        self.authority = {'revoked': False, 'valid_from': '2020-01-01T00:00:00Z',
                          'valid_until': '2099-01-01T00:00:00Z'}
        self.signer = {**self.authority, 'references': {'offline:fixture': digest(self.a)}}
        self.roots = {'test-only-root': {**self.authority, 'producer_ids': ['producer-fixture'],
                                       'attesters': {'independent-fixture': self.signer}}}

    def test_shipped_verifier_has_no_trust_and_booleans_do_not_create_it(self):
        self.assertEqual(av.verify(self.directory, self.a)['reason'], 'missing_trust_root')
        self.a['verified'] = True
        self.assertEqual(av.verify(self.directory, self.a)['reason'], 'invalid_attestation_schema')

    def test_authenticated_external_record_and_tampering(self):
        with patch.object(av, 'TRUST_ROOTS', self.roots):
            self.assertTrue(av.verify(self.directory, self.a)['independent_attestation_verified'])
            self.assertFalse(av.verify(self.directory, self.a)['evidence_eligible'])
            for key in ('issued_at', 'signature_or_external_ref', 'attester_id'):
                changed = {**self.a, key: 'tampered'}
                self.assertFalse(av.verify(self.directory, changed)['independent_attestation_verified'])
            (self.directory / 'l5-receipts.json').write_text('{"bill":0}')
            self.assertEqual(av.verify(self.directory, self.a)['reason'], 'evidence_digest_mismatch')

    def test_revocation_expiry_and_self_attestation(self):
        with patch.object(av, 'TRUST_ROOTS', self.roots):
            self.signer['revoked'] = True
            self.assertEqual(av.verify(self.directory, self.a)['reason'], 'revoked_authority')
            self.signer['revoked'] = False
            self.signer['valid_until'] = '2021-01-01T00:00:00Z'
            self.assertEqual(av.verify(self.directory, self.a)['reason'], 'stale_or_future_attestation')
            self.roots['test-only-root']['producer_ids'].append('independent-fixture')
            self.assertEqual(av.verify(self.directory, self.a)['reason'], 'self_attestation_refused')
        for name in ('xngg1021', 'XNGG1021/CONTEXT-ECONOMICS'):
            self.assertEqual(av.verify(self.directory, {**self.a, 'attester_id': name})['reason'],
                             'self_attestation_refused')

    def test_extra_file_and_symlink_cannot_escape_directory_binding(self):
        (self.directory / 'extra.json').write_text('{}')
        self.assertEqual(av.verify(self.directory, self.a)['reason'], 'evidence_digest_mismatch')
        (self.directory / 'link').symlink_to(self.directory / 'extra.json')
        self.assertEqual(av.verify(self.directory, self.a)['reason'], 'nonregular_artifact')
