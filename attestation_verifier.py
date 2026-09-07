"""Offline external-reference verification, with no caller-controlled trust input.

TRUST_ROOTS is deliberately empty. A deployment must provision independently
authenticated reference records in reviewed verifier code, outside the campaign.
An external URL alone is not authentication. No network or production writes.
This interface does not enable the acceptance gate or authenticate provider data
merely because its directory is internally consistent.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from types import MappingProxyType

from provider_runtime import digest

TRUST_ROOTS = MappingProxyType({})
LOCAL_ATTESTERS = frozenset({'xngg1021', 'xngg1021/context-economics', 'context-economics'})
FIELDS = frozenset({'artifact_directory_digest', 'manifest_digest', 'receipt_digest',
                    'provider_evidence_digest', 'scorer_evidence_digest', 'attester_id',
                    'issued_at', 'signature_or_external_ref', 'trust_root_id'})
BOUND_FILES = {'manifest_digest': 'manifest.json', 'receipt_digest': 'l5-receipts.json',
               'provider_evidence_digest': 'raw-telemetry.json', 'scorer_evidence_digest': 'scorer-ref.json'}


def directory_digests(directory):
    """Hash every flat artifact byte; attestation MUST be outside the directory."""
    directory = Path(directory)
    if directory.is_symlink() or not directory.is_dir():
        raise ValueError('invalid_artifact_directory')
    hashes = {}
    for path in sorted(directory.iterdir()):
        if path.is_symlink() or not path.is_file():
            raise ValueError('nonregular_artifact')
        hashes[path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
    if not hashes or any(name not in hashes for name in BOUND_FILES.values()):
        raise ValueError('missing_evidence_file')
    return {'artifact_directory_digest': digest(hashes),
            **{field: hashes[name] for field, name in BOUND_FILES.items()}}


def _time(value):
    result = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if result.tzinfo is None:
        raise ValueError('timestamp_timezone_required')
    return result


def verify(directory, attestation):
    """No trust-path, key, boolean, verifier callback or clock supplied by caller.

Provisioned root shape: revoked, valid_from, valid_until, producer_ids,
attesters {id: {revoked, valid_from, valid_until, references {ref: digest}}}.
Reference digest binds the ENTIRE attestation including identity/time/reference.
"""
    result = {'independent_attestation_verified': False, 'evidence_eligible': False,
              'candidate_for_promotion': False, 'production_mutation': False}
    try:
        if not isinstance(attestation, dict) or set(attestation) != FIELDS:
            raise ValueError('invalid_attestation_schema')
        if any(not isinstance(v, str) or not v or len(v) > 2048 for v in attestation.values()):
            raise ValueError('invalid_attestation_field')
        if attestation['attester_id'].casefold() in LOCAL_ATTESTERS:
            raise ValueError('self_attestation_refused')
        actual = directory_digests(directory)
        if any(attestation[k] != v for k, v in actual.items()):
            raise ValueError('evidence_digest_mismatch')
        root = TRUST_ROOTS.get(attestation['trust_root_id'])
        if root is None:
            raise ValueError('missing_trust_root')
        if attestation['attester_id'] in root['producer_ids']:
            raise ValueError('self_attestation_refused')
        signer = root['attesters'].get(attestation['attester_id'])
        if signer is None:
            raise ValueError('unknown_attester')
        now = datetime.now(timezone.utc)
        issued = _time(attestation['issued_at'])
        for authority in (root, signer):
            if authority['revoked'] is not False:
                raise ValueError('revoked_authority')
            if not _time(authority['valid_from']) <= issued <= now <= _time(authority['valid_until']):
                raise ValueError('stale_or_future_attestation')
        expected = signer['references'].get(attestation['signature_or_external_ref'])
        if expected != digest(attestation):
            raise ValueError('unverified_external_reference')
        result['independent_attestation_verified'] = True
        result['reason'] = 'verified_external_reference; separate economic gate still required'
    except (ValueError, TypeError, KeyError, OSError, AttributeError) as exc:
        allowed = {'invalid_artifact_directory', 'nonregular_artifact', 'missing_evidence_file',
                   'invalid_attestation_schema', 'invalid_attestation_field', 'self_attestation_refused',
                   'evidence_digest_mismatch', 'missing_trust_root', 'unknown_attester',
                   'revoked_authority', 'stale_or_future_attestation', 'unverified_external_reference'}
        result['reason'] = str(exc) if str(exc) in allowed else 'invalid_verification_input'
    return result


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--artifacts', required=True)
    p.add_argument('--attestation', required=True)
    args = p.parse_args()
    try:
        report = verify(args.artifacts, json.loads(Path(args.attestation).read_text()))
    except (OSError, ValueError):
        report = {'independent_attestation_verified': False, 'evidence_eligible': False,
                  'reason': 'invalid_attestation_input', 'production_mutation': False}
    print(json.dumps(report, indent=2))
    raise SystemExit(0 if report['independent_attestation_verified'] else 2)
