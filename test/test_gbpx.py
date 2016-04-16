import unittest
from os import path, chdir, listdir

from gbpx import execute_with
from gbpxargs import Action
from gbpxutil import verify_create_head_tag
from gitutil import init_repository, create_branch, switch_branch, \
    commit_changes
from ioutil import create_file, mkdirs, remove_dir, exec_cmd

_TEST_FILE = "test.txt"
_IGNORE_FILE = "README.md"

_TEST_DIR = "/tmp/test_gbpx"
_RELEASE = "master"
_RELEASE_TAG_TYPE = "release"
_UPSTREAM = "upstream"
_DEBIAN = "debian"


class DefaultTestCase(unittest.TestCase):
    def __init__(self):
        self.flags = {'safemode': False, 'quiet': True, 'color': False}

    def setUp(self):
        # Init repository with one file.
        mkdirs(self.flags, _TEST_DIR)
        create_file(self.flags, path.join(_TEST_DIR, _TEST_FILE))
        init_repository(self.flags, _TEST_DIR)
        chdir(_TEST_DIR)

        # Create branches.
        create_branch(self.flags, _UPSTREAM)
        switch_branch(_UPSTREAM)
        create_branch(self.flags, _DEBIAN)
        switch_branch(_RELEASE)

        # Commit ignored file nad config.
        create_file(self.flags, _IGNORE_FILE, "Test")
        execute_with(action=Action.CONFIG)
        commit_changes(self.flags, "Ignored file added.")

    def tearDown(self):
        # Clean up files.
        remove_dir(self.flags, _TEST_DIR)


class CommitReleaseTestCase(DefaultTestCase):

    def setUp(self):
        super(DefaultTestCase, self).setUp()
        verify_create_head_tag(self.flags, _RELEASE, _RELEASE_TAG_TYPE, "0.1")
        execute_with(action=Action.COMMIT_RELEASE)

    def test_upstream_integrity(self):
        switch_branch(_UPSTREAM)
        self.assertTrue(path.exists(_TEST_FILE))
        self.assertFalse(path.exists(_IGNORE_FILE))
        self.assertTrue(len(listdir(".")) == 1)

    def test_debian_integrity(self):
        self.assertTrue(path.exists(_TEST_FILE))
        self.assertFalse(path.exists(_IGNORE_FILE))
        self.assertTrue(len(listdir(".")) == 1)

if __name__ == '__main__':
    unittest.main()
