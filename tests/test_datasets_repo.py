"""Offline coverage of release routing and subprocess-only credentials."""
import os
import pathlib
import subprocess
import tempfile
import unittest
from unittest import mock

from research.lab import datasets


class DatasetRepoTests(unittest.TestCase):
    def test_release_calls_and_environment(self):
        for repo in (None, "327979420/sage-vista-data"):
            for token in (None, "test-data-token"):
                for scenario in ("create", "upload", "reuse", "conflict", "download", "cached"):
                    with self.subTest(repo=repo, token=bool(token), scenario=scenario):
                        self.check_scenario(repo, token, scenario)

    def check_scenario(self, repo, token, scenario):
        env = {"GH_TOKEN": "test-original-token", "PATH": "/test/bin"}
        if repo:
            env["SV_DATA_REPO"] = repo
        if token:
            env["SV_DATA_TOKEN"] = token
        with tempfile.TemporaryDirectory() as folder, mock.patch.dict(os.environ, env, clear=True):
            path = pathlib.Path(folder) / "asset.json.gz"
            path.write_bytes(b"synthetic asset")
            before = dict(os.environ)
            expected = []

            def record(args, **kwargs):
                expected_kwargs = ({"capture_output": True, "text": True}
                                   if args[2] == "view" else {"check": True})
                if repo and token:
                    expected_kwargs["env"] = {**before, "GH_TOKEN": token}
                self.assertEqual(kwargs, expected_kwargs)
                self.assertEqual(dict(os.environ), before)
                if args[2] == "download":
                    target = pathlib.Path(args[args.index("-D") + 1]) / path.name
                    target.write_bytes(b"different" if scenario == "conflict" else path.read_bytes())
                return subprocess.CompletedProcess(args, 1 if scenario == "create" else 0,
                                                   path.name if scenario in ("reuse", "conflict") else "")

            with mock.patch.object(datasets.subprocess, "run", side_effect=record) as run:
                prefix = ["gh", "release"]
                tag = datasets.RELEASE_TAG
                if scenario in ("download", "cached"):
                    dest = pathlib.Path(folder) / "download" if scenario == "download" else path.parent
                    result = datasets.download({"asset": path.name, "release": tag}, dest)
                    self.assertEqual(result, dest / path.name)
                    if scenario == "download":
                        expected.append(prefix + ["download", tag, "-p", path.name, "-D", str(dest)])
                else:
                    expected.append(prefix + ["view", tag, "--json", "assets", "-q", ".assets[].name"])
                    if scenario == "conflict":
                        with self.assertRaisesRegex(ValueError, "release_asset_conflict"):
                            datasets.upload(path)
                    else:
                        datasets.upload(path)
                    if scenario == "create":
                        expected.append(prefix + ["create", tag, "--prerelease", "--title", "Research datasets",
                                                  "--notes", "Frozen, content-addressed research datasets. Assets are never replaced."])
                    if scenario in ("reuse", "conflict"):
                        expected.append(prefix + ["download", tag, "-p", path.name, "-D", mock.ANY])
                    else:
                        expected.append(prefix + ["upload", tag, str(path)])
                # Only switch to the private repo when its token is also configured.
                suffix = ["-R", repo] if repo and token else []
                self.assertEqual([call.args[0] for call in run.call_args_list],
                                 [args + suffix for args in expected])
            self.assertEqual(dict(os.environ), before)


if __name__ == "__main__":
    unittest.main()
