import unittest
from os import path, chdir, listdir

from gbpx.gbpx import execute_with
from gbpx.gbpxargs import Action, Flag
from gbpx.gbpxutil import verify_create_head_tag
from gbpx.gitutil import init_repository, create_branch, switch_branch, \
    commit_changes
from gbpx.ioutil import create_file, mkdirs, remove_dir

_TEST_FILE = "test.txt"
_TEST_FILE2 = "test2.txt"
_TEST_DEBIAN_FILE = "debian/rules.txt"
_IGNORE_FILE = "README.md"

_TEST_DIR = "/tmp/gbpx/unittest/repository"
_RELEASE = "master"
_RELEASE_TAG_TYPE = "release"
_UPSTREAM = "upstream"
_DEBIAN = "debian"

_FLAGS = {Flag.SAFEMODE: False, Flag.QUIET.value: False, Flag.VERBOSE.value: False,
          Flag.COLOR.value: False}


def set_up():
    # Init repository with one file.
    remove_dir(_FLAGS, _TEST_DIR)
    mkdirs(_FLAGS, _TEST_DIR)
    init_repository(_FLAGS, _TEST_DIR)
    chdir(_TEST_DIR)
    create_file(_FLAGS, _TEST_FILE)
    commit_changes(_FLAGS, "Test file added.")

    # Create branches.
    create_branch(_FLAGS, _UPSTREAM)
    switch_branch(_UPSTREAM)

    create_branch(_FLAGS, _DEBIAN)
    switch_branch(_DEBIAN)
    mkdirs(_FLAGS, path.dirname(_TEST_DEBIAN_FILE))
    create_file(_FLAGS, _TEST_DEBIAN_FILE)
    commit_changes(_FLAGS, "Test debian file added.")

    # Commit ignored file and config.
    switch_branch(_RELEASE)
    create_file(_FLAGS, _IGNORE_FILE)
    create_file(_FLAGS, _TEST_FILE2)
    execute_with(action=Action.CONFIG)
    commit_changes(_FLAGS, "Ignored file added.")


def tear_down():
    pass
    # Clean up files.
    # remove_dir(_FLAGS, _TEST_DIR)


class CommitReleaseTestCase(unittest.TestCase):
    def setUp(self):
        set_up()
        verify_create_head_tag(_FLAGS, _RELEASE, _RELEASE_TAG_TYPE, "0.1")
        execute_with(action=Action.COMMIT_RELEASE, verbose=True)

    def tearDown(self):
        tear_down()

    def test_upstream_integrity(self):
        switch_branch(_UPSTREAM)
        self.assertTrue(path.exists(_TEST_FILE))
        self.assertTrue(path.exists(_TEST_FILE2))
        self.assertFalse(path.exists(_IGNORE_FILE))
        self.assertTrue(len(listdir(".")) == 3)

    def test_debian_integrity(self):
        switch_branch(_DEBIAN)
        self.assertTrue(path.exists(_TEST_FILE))
        self.assertTrue(path.exists(_TEST_FILE2))
        self.assertFalse(path.exists(_IGNORE_FILE))
        self.assertTrue(len(listdir(".")) == 3)


if __name__ == '__main__':
    unittest.main()
