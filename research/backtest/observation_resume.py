"""Resume the original observation run, never dispatch a new scoring version."""
import base64
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile


def action(meta, jobs, progress=None, previous=None, *, manual=False):
    shards=[j for j in jobs if re.fullmatch(r'observation_shards \(\d+\)',j['name'])]
    valid=(meta.get('path')=='.github/workflows/opportunity-ledger-refresh.yml'
           and meta.get('event')=='workflow_dispatch' and meta.get('head_branch')=='main' and shards)
    if not valid:
        if manual:raise ValueError('not_an_original_observation_run')
        return None
    if meta['status']!='completed':
        if manual:raise ValueError('original_run_still_active_do_not_duplicate')
        return None
    attempt=meta['run_attempt']
    if meta['conclusion']=='cancelled':return None
    if meta['conclusion']=='failure':
        failed=any(j.get('conclusion') in ('failure','timed_out') for j in shards)
        return 'failed' if failed and (manual or attempt<3) else None
    if meta['conclusion']!='success' or progress is None:return None
    if progress.get('code')!=meta['head_sha'] or type(progress.get('complete')) is not bool:
        raise ValueError('continuation_progress_identity_invalid')
    if progress['complete']:return None
    if not isinstance(progress.get('progress_fingerprint'),str):raise ValueError('progress_fingerprint_missing')
    if not manual and (attempt>=12 or (previous and previous.get('progress_fingerprint')==progress['progress_fingerprint'])):
        return None
    return 'all'


def main():
    run=os.environ.get('RESUME_RUN_ID','');repo=os.environ['GH_REPO']
    if not run.isdecimal():raise ValueError('numeric_original_run_id_required')
    automatic=os.environ.get('AUTOMATIC_RESUME')=='true'
    def gh(*args):
        return subprocess.run(['gh',*args],check=True,capture_output=True,text=True).stdout
    meta=json.loads(gh('api',f'repos/{repo}/actions/runs/{run}'))
    jobs=json.loads(gh('api',f'repos/{repo}/actions/runs/{run}/jobs?per_page=100'))['jobs']
    progress=previous=None
    # Ordinary refreshes share a workflow name but must never be rerun here.
    if not any(re.fullmatch(r'observation_shards \(\d+\)',j['name']) for j in jobs):
        action(meta,jobs,manual=not automatic)
        return
    if meta['status']=='completed' and meta['conclusion']=='success':
        attempt=meta['run_attempt']
        pages=json.loads(gh('api','--paginate','--slurp',f'repos/{repo}/actions/runs/{run}/artifacts?per_page=100'))
        artifacts=[a for page in pages for a in page['artifacts']]
        names={a['name'] for a in artifacts if not a['expired']}
        def load_progress(number):
            name=f'observation-progress-{number}'
            if name not in names:return None
            with tempfile.TemporaryDirectory() as td:
                gh('run','download',run,'--repo',repo,'--name',name,'--dir',td)
                return json.loads((Path(td)/'batch-status.json').read_bytes())
        progress=load_progress(attempt)
        earlier=[int(n.rsplit('-',1)[1]) for n in names if re.fullmatch(r'observation-progress-\d+',n) and int(n.rsplit('-',1)[1])<attempt]
        previous=load_progress(max(earlier)) if earlier else None
    decision=action(meta,jobs,progress,previous,manual=not automatic)
    if decision=='failed':
        source=json.loads(gh('api',f'repos/{repo}/contents/.github/workflows/opportunity-ledger-refresh.yml?ref={meta["head_sha"]}'))
        artifact_recovery='Recover checkpoints from the previous artifact if cache was evicted' in base64.b64decode(source['content']).decode()
        # Legacy runs cannot restore artifacts themselves. Refuse a cold restart
        # if their saved caches have disappeared, instead of silently recomputing.
        for job in jobs:
            match=re.fullmatch(r'observation_shards \((\d+)\)',job['name'])
            if match and job.get('conclusion') in ('failure','timed_out'):
                prefix=f"observation-v1-{meta['head_sha']}-{match[1]}-"
                caches=json.loads(gh('api','--method','GET',f'repos/{repo}/actions/caches','-f',f'key={prefix}'))
                if not caches.get('total_count') and not artifact_recovery:raise ValueError('checkpoint_cache_missing_preserve_artifacts_do_not_restart')
    message='No continuation dispatched: complete, active, cancelled, stalled, or automatic limit reached.'
    if decision:
        args=['run','rerun',run,'--repo',repo]
        if decision=='failed':args.append('--failed')
        gh(*args)
        message=f'Continuation requested for original run {run}, frozen code {meta["head_sha"]}; completed stocks are reused.'
    print(message)
    if os.environ.get('GITHUB_STEP_SUMMARY'):
        with open(os.environ['GITHUB_STEP_SUMMARY'],'a') as out:out.write(message+'\n')


if __name__=='__main__':main()
