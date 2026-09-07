"""Manual official-source snapshot validation/freshness; never rewrites history."""
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit
import context_runtime as rt
from provider_runtime import digest

HOSTS={'openai':{'developers.openai.com','openai.com'},
       'anthropic':{'platform.claude.com','claude.com'},
       'gemini':{'ai.google.dev','cloud.google.com'},
       'kimi':{'platform.kimi.com','platform.kimi.ai','www.kimi.com'}}


def check(snapshot, now=None, max_age_days=7):
    now=now or datetime.now(timezone.utc)
    if now.tzinfo is None or type(max_age_days) is not int or max_age_days<0:raise ValueError('invalid freshness parameters')
    stamp=datetime.fromisoformat(snapshot['retrieved_at'])
    if stamp.tzinfo is None or stamp>now:raise ValueError('invalid retrieved_at')
    for row in snapshot['models'].values():
        parts=urlsplit(row['source'])
        if parts.scheme!='https' or parts.hostname not in HOSTS[row['provider']] or parts.username or parts.password:
            raise ValueError('official pricing source required')
        if row['currency'] not in {'USD','CNY'} or row['unit']!='per-million-tokens':raise ValueError('explicit pricing units required')
        for field in ('input','output','cached_read'):
            if row[field] is not None:rt._num(row[field],field)
    age=(now-stamp).total_seconds()/86400
    return {'snapshot_digest':'sha256:'+digest(snapshot),'age_days':age,
            'stale':age>max_age_days,'historical_files_modified':False,
            'source_content_retrieved_by_this_check':False}

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--snapshot',required=True)
    p.add_argument('--max-age-days',type=int,default=7);a=p.parse_args()
    result=check(json.loads(Path(a.snapshot).read_text()),max_age_days=a.max_age_days)
    print(json.dumps(result,indent=2));raise SystemExit(1 if result['stale'] else 0)
