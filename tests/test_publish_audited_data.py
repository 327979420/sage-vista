import pathlib
import re
import tempfile
import unittest
from unittest.mock import patch

from services.scanner import publish_audited_data as p


class PublishAuditedDataTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = pathlib.Path(self.tmp.name)
        self.remote, self.worker, self.writer = [root / x for x in ('remote', 'worker', 'writer')]
        p.git(root, 'init', '--bare', '--initial-branch=main', str(self.remote))
        p.git(root, 'clone', str(self.remote), str(self.worker))
        self.identity(self.worker)
        self.commit(self.worker, 'README.md', 'initial documentation\n')
        self.commit(self.worker, 'public/data.json', '{"day":"old"}\n')
        p.git(self.worker, 'push', 'origin', 'HEAD:main')
        self.base = p.git(self.worker, 'rev-parse', 'HEAD').stdout.strip()
        p.git(root, 'clone', str(self.remote), str(self.writer))
        self.identity(self.writer)
        p.git(self.worker, 'checkout', '--detach')
        self.commit(self.worker, 'public/data.json', '{"day":"new"}\n')
        self.audited = p.git(self.worker, 'rev-parse', 'HEAD').stdout.strip()

    def identity(self, repo):
        p.git(repo, 'config', 'user.name', 'test')
        p.git(repo, 'config', 'user.email', 'test@example.invalid')

    def commit(self, repo, path, value):
        target = repo / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(value)
        p.git(repo, 'add', path)
        p.git(repo, 'commit', '-m', 'test change')

    def advance(self, path, value='concurrent edit\n'):
        self.commit(self.writer, path, value)
        p.git(self.writer, 'push', 'origin', 'HEAD:main')

    def assert_published(self, sha):
        self.assertEqual(p.git(self.remote, 'rev-parse', 'main').stdout.strip(), sha)
        self.assertEqual(p.git(self.remote, 'show', 'main:public/data.json').stdout,
                         '{"day":"new"}\n')

    def test_unchanged_main_publishes_original_checked_commit(self):
        self.assertEqual(p.publish(self.worker, self.base), self.audited)
        self.assert_published(self.audited)

    def test_concurrent_document_preserves_both_document_and_audited_bytes(self):
        self.advance('docs/CHANGE_REQUESTS_ZH.md')
        sha = p.publish(self.worker, self.base)
        self.assert_published(sha)
        self.assertEqual(p.git(self.remote, 'show', 'main:docs/CHANGE_REQUESTS_ZH.md').stdout,
                         'concurrent edit\n')
        self.assertEqual(p.changed(self.worker, self.audited, sha), {'docs/CHANGE_REQUESTS_ZH.md'})

    def test_code_data_and_generated_status_changes_require_fresh_audit(self):
        for path in ('services/scanner/example.py', 'public/data.json', 'docs/CURRENT_STATUS_ZH.md'):
            with self.subTest(path=path):
                self.advance(path)
                remote_head = p.git(self.remote, 'rev-parse', 'main').stdout
                with self.assertRaisesRegex(RuntimeError, re.escape(path)):
                    p.publish(self.worker, self.base)
                self.assertEqual(p.git(self.remote, 'rev-parse', 'main').stdout, remote_head)
                self.assertEqual(p.git(self.worker, 'rev-parse', 'HEAD').stdout.strip(), self.audited)

    def test_move_between_fetch_and_push_is_rechecked(self):
        real_git = p.git
        raced = False

        def race(repo, *args, **kwargs):
            nonlocal raced
            if pathlib.Path(repo) == self.worker and args[:1] == ('push',) and not raced:
                raced = True
                self.advance('README.md', 'new documentation\n')
            return real_git(repo, *args, **kwargs)

        with patch.object(p, 'git', side_effect=race):
            sha = p.publish(self.worker, self.base)
        self.assertTrue(raced)
        self.assert_published(sha)
        self.assertEqual(real_git(self.remote, 'show', 'main:README.md').stdout, 'new documentation\n')

    def test_code_move_between_fetch_and_push_is_rejected(self):
        real_git = p.git
        raced = False

        def race(repo, *args, **kwargs):
            nonlocal raced
            if pathlib.Path(repo) == self.worker and args[:1] == ('push',) and not raced:
                raced = True
                self.advance('services/scanner/example.py')
            return real_git(repo, *args, **kwargs)

        with patch.object(p, 'git', side_effect=race):
            with self.assertRaisesRegex(RuntimeError, 'Production code/data changed'):
                p.publish(self.worker, self.base)
        self.assertEqual(real_git(self.remote, 'show', 'main:public/data.json').stdout,
                         '{"day":"old"}\n')

    def test_document_conflict_aborts_without_publishing(self):
        self.commit(self.worker, 'README.md', 'worker document\n')
        self.advance('README.md', 'writer document\n')
        with self.assertRaisesRegex(RuntimeError, 'conflicted'):
            p.publish(self.worker, self.base)
        self.assertEqual(p.git(self.remote, 'show', 'main:public/data.json').stdout,
                         '{"day":"old"}\n')
        self.assertFalse((self.worker / '.git/rebase-merge').exists())

    def test_workflow_publishes_before_capturing_rebuilt_deployment_identity(self):
        text = (pathlib.Path(__file__).parents[1] / '.github/workflows/daily-eod.yml').read_text()
        block = text.split('name: Commit audited website data', 1)[1].split('- name:', 1)[0]
        self.assertLess(block.index('validated_base=$(git rev-parse HEAD)'), block.index('git commit'))
        self.assertLess(block.index('services.scanner.publish_audited_data'),
                        block.index('echo "deployment_commit='))
        self.assertNotIn('git push', block)
