"""Connect CR056 to the existing EOD job; preserve the last good view on failure.

Git stores the watch checkpoint and dated compact views. Actions caches only
accelerate private inputs; their loss never recreates or resets watch history.
"""
import argparse
from datetime import date, timedelta
import gzip
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import zlib
from services.ledger.cr056 import watch_checkpoint, validate_watch_checkpoint
from services.scanner.cr056_inputs import repair_existing_cache, normalized_comparison_rows
from services.scanner.cr056_runner import run_snapshot
from services.scanner.cr056_public import project_report, project_details, VIEW_VERSION
from services.contracts.cr056_policy import POLICY_VERSION, POLICY_FINGERPRINT

ROOT = Path(__file__).resolve().parents[2]


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, separators=(',', ':'))+'\n').encode()


def replace_bytes(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as f:
        f.write(content); temporary = Path(f.name)
    os.replace(temporary, path)


def checked_cached_inputs(cache):
    index_path = cache/'index.json'
    if not index_path.exists():
        if cache.exists() and any(cache.iterdir()): raise ValueError('private_cache_index_missing')
        return None
    index = json.loads(index_path.read_text())
    for item in index['repaired']:
        content = (cache/'eodhd-cache'/f"{item['symbol']}.json").read_bytes()
        if hashlib.sha256(content).hexdigest() != item['repaired_sha256']:
            raise ValueError('private_cache_hash_mismatch')
    return index


def prepare_inputs(*, base_cache, cache, stage, previous_date, as_of, reference_sessions, fetch_bulk):
    cached = checked_cached_inputs(cache)
    if cached and cached['as_of'] > as_of: raise ValueError('private_cache_from_future')
    inherited = cached['excluded'] if cached else {}
    source = cache/'eodhd-cache' if cached else base_cache
    # A missing accelerator may rebuild only the recent, already-observed seed.
    # This is not permission to download whole per-stock histories or revive old tails.
    if not cached:
        seed = repair_existing_cache(source, stage/'seed', as_of=previous_date,
                                    reference_sessions=reference_sessions, fetch_bulk=fetch_bulk)
        source = stage/'seed'/'eodhd-cache'; inherited = seed['excluded']
    report = repair_existing_cache(source, stage/'current', as_of=as_of,
                                   reference_sessions=reference_sessions, fetch_bulk=fetch_bulk)
    report['excluded'] = {**inherited, **report['excluded']}
    for item in report['repaired']: report['excluded'].pop(item['symbol'], None)
    report['excluded_count'] = len(report['excluded'])
    return stage/'current'/'eodhd-cache', report


def refresh(*, as_of, code_commit, public_path, state_path, archive_dir, work_dir,
            base_cache, fetch_reference, fetch_bulk, runner=run_snapshot):
    original_public = public_path.read_bytes()
    detail_path = public_path.parent/'cr056-factor-details.json.gz'
    original_details = detail_path.read_bytes() if detail_path.exists() else None
    current = json.loads(original_public)
    changed = False
    try:
        state_bytes = state_path.read_bytes()
        previous = validate_watch_checkpoint(json.loads(gzip.decompress(state_bytes)))
        if previous['as_of'] > as_of: raise ValueError('older_date_cannot_replace_watch_state')
        if previous['snapshot_fingerprint'] != current['source_snapshot'] or previous['as_of'] != current['as_of']:
            raise ValueError('public_watch_checkpoint_mismatch')
        policy_revision = (current['policy_version'] != POLICY_VERSION or
                           current.get('policy_fingerprint') != POLICY_FINGERPRINT or
                           current.get('view_version') != VIEW_VERSION)
        if previous['as_of'] == as_of and not policy_revision:
            current.update(automatic_updates_connected=True,
                           refresh_status={'status':'current', 'target_as_of':as_of})
            public_bytes = encoded(current); changed = public_bytes != original_public
            if changed: replace_bytes(public_path, public_bytes)
            return {'result':'already_current', 'as_of':as_of, 'changed':changed, 'cache_ready':False}
        if (date.fromisoformat(as_of)-date.fromisoformat(previous['as_of'])).days > 10:
            raise ValueError('refresh_gap_exceeds_bounded_recovery')
        # One small SPY query supplies observed sessions, including holiday gaps.
        start = max(date.fromisoformat(previous['as_of'])-timedelta(days=10),
                    date.fromisoformat(as_of)-timedelta(days=19)).isoformat()
        reference = normalized_comparison_rows(fetch_reference(start, as_of), as_of=as_of)
        sessions = [r['date'] for r in reference]
        if not sessions or sessions[-1] != as_of: raise ValueError('reference_latest_session_missing')
        work_dir.mkdir(parents=True, exist_ok=True)
        cache = work_dir/'cache'
        with tempfile.TemporaryDirectory(prefix='cr056-refresh-', dir=work_dir) as temporary:
            stage = Path(temporary); fetched = {}
            def bulk(day):
                if day not in fetched:
                    anchor = cache/'bulk'/f'{day}.json'
                    fetched[day] = json.loads(anchor.read_text()) if anchor.exists() else fetch_bulk(day, stage/'bulk')
                return fetched[day]
            source, input_report = prepare_inputs(base_cache=base_cache, cache=cache, stage=stage,
                previous_date=previous['as_of'], as_of=as_of, reference_sessions=sessions, fetch_bulk=bulk)
            report = runner(source, as_of=as_of, history={'days':[]}, code_commit=code_commit,
                            input_report=input_report, previous=previous, **({"policy_revision":True} if policy_revision and previous["as_of"] == as_of else {}))
            # Preserve completed derived work even if display validation fails.
            replace_bytes(work_dir/'daily-report.json.gz', gzip.compress(encoded(report),mtime=0))
            replace_bytes(work_dir/'input-report.json', encoded(input_report))
            if policy_revision:
                old_suffix = previous['snapshot_fingerprint'].split(':')[-1][:16]
                for name, content in ((f"{previous['as_of']}-{old_suffix}-before-policy.json.gz", gzip.compress(original_public, mtime=0)),
                                      (f"{previous['as_of']}-{old_suffix}-watch.json.gz", state_bytes)):
                    path = archive_dir/name
                    if path.exists() and path.read_bytes() != content: raise ValueError('old_policy_archive_conflict')
                    if not path.exists(): replace_bytes(path, content)
            details = gzip.compress(encoded(project_details(report)), mtime=0)
            public = project_report(report)
            public.update(automatic_updates_connected=True,
                          refresh_status={'status':'updated', 'target_as_of':as_of})
            public_bytes = encoded(public)
            if len(public_bytes)>750_000: raise ValueError('public_projection_size_budget_exceeded')
            checkpoint = validate_watch_checkpoint(watch_checkpoint(report))
            if not {r['symbol'] for r in previous['reviews']} <= {r['symbol'] for r in checkpoint['reviews']}:
                raise ValueError('watch_history_would_be_lost')
            state_output = gzip.compress(encoded(checkpoint), mtime=0)
            suffix = report['snapshot_fingerprint'].split(':')[-1][:16]
            archive = archive_dir/f'{as_of}-{suffix}.json.gz'
            archive_bytes = gzip.compress(public_bytes, mtime=0)
            if archive.exists() and archive.read_bytes()!=archive_bytes: raise ValueError('dated_view_conflict')
            # Derived audit only: never put private raw histories in an artifact.
            # The job's existing Git commit is the durable publication boundary.
            # A process failure before that commit is discarded by the next checkout.
            try:
                if not archive.exists(): replace_bytes(archive, archive_bytes)
                replace_bytes(state_path, state_output)
                replace_bytes(public_path.parent/'cr056-factor-details.json.gz', details)
                replace_bytes(public_path, public_bytes)
            except OSError:
                replace_bytes(state_path, state_bytes)
                if original_details is not None: replace_bytes(detail_path, original_details)
                elif detail_path.exists(): detail_path.unlink()
                replace_bytes(public_path, original_public)
                raise
            changed = True
            # Accelerators are separate from committed watch state and public data.
            replacement = stage/'cache'; replacement.mkdir()
            shutil.move(str(source), replacement/'eodhd-cache')
            (replacement/'bulk').mkdir()
            if as_of in fetched: (replacement/'bulk'/f'{as_of}.json').write_bytes(encoded(fetched[as_of]))
            (replacement/'index.json').write_bytes(encoded(input_report))
            if cache.exists(): shutil.rmtree(cache)
            shutil.move(str(replacement), cache)
        return {'result':'updated','as_of':as_of,'changed':True,'cache_ready':True,
                'source_snapshot':report['snapshot_fingerprint'], 'ranked':len(report['ranked_symbols'])}
    except (ValueError, KeyError, OSError, RuntimeError, TypeError, EOFError, zlib.error) as error:
        if changed:
            # Scoring and durable bytes are already complete; a cache failure is
            # not a reason to mislabel that good snapshot as stale.
            return {'result':'updated','as_of':as_of,'changed':True,'cache_ready':False,
                    'cache_warning':type(error).__name__}
        reason = str(error) if isinstance(error, ValueError) and str(error).replace('_','').isalnum() else 'candidate_refresh_failed'
        current.update(automatic_updates_connected=True,
                       refresh_status={'status':'failed','target_as_of':as_of,'reason':reason})
        public_bytes = encoded(current)
        if public_bytes != original_public: replace_bytes(public_path, public_bytes)
        return {'result':'retained_previous','as_of':current['as_of'],'attempted_as_of':as_of,
                'reason':reason,'changed':public_bytes!=original_public,'cache_ready':False}


def main():
    p=argparse.ArgumentParser();p.add_argument('--as-of',required=True);args=p.parse_args()
    from services.scanner.eodhd import prices
    from services.scanner.resonance_tracker import bulk_day
    def existing_bulk(day, private_bulk):
        shared = ROOT/'work/eodhd-bulk'/f'{day}.json'
        if shared.exists(): return json.loads(shared.read_text())
        return bulk_day(day, cache_dir=str(private_bulk), strict=True)
    result=refresh(as_of=args.as_of, code_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        public_path=ROOT/'public/cr056-ranking.json', state_path=ROOT/'automation/cr056-watch-state.json.gz',
        archive_dir=ROOT/'research/generated/cr056-daily', work_dir=ROOT/'work/cr056-daily',
        base_cache=ROOT/'work/eodhd-cache', fetch_reference=lambda start,end:prices('SPY',start,end), fetch_bulk=existing_bulk)
    print(json.dumps(result))

if __name__=='__main__':main()
