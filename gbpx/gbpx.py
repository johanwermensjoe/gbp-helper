#!/usr/bin/env python3
# TODO Support new distribution versions for update changelog/(build) _._-X~ppa_
"""
gbpx module:
Used as a helper script for gbp-buildpackage.
"""
from argparse import ArgumentParser, SUPPRESS
from glob import glob
from os import path, chdir, getcwd
from re import findall

from gbpxargs import Flag, Option, Action
from gbpxutil import verify_create_head_tag, OpError, ConfigError, \
    restore_backup, create_ex_config, add_backup, restore_temp_commit, \
    create_temp_commit, get_config, get_config_default, DEFAULT_CONFIG_PATH, \
    Setting
from gitutil import get_head_tag_version, commit_changes, switch_branch, \
    GitError, get_next_version, get_latest_tag_version, is_version_lt, \
    get_rep_name_from_url, clean_repository, get_branch, reset_branch
from ioutil import Error, log, TextType, prompt_user_input, mkdirs, \
    exec_cmd, get_files_with_extension, clean_dir, \
    log_success, log_err, remove_dir, CommandError, exec_editor, \
    prompt_user_yn, exec_piped_cmds, remove_file, line_break

############################## Constants ################################
#########################################################################

__version__ = "0.8"

_GIT_IGNORE_PATH = ".gitignore"
_CHANGELOG_PATH = "debian/changelog"
_BUILD_DIR = "../build-area"
_TMP_DIR = "/tmp/gbpx"
_TMP_TAR_SUBDIR = "tarball"
_TMP_BAK_SUBDIR = "backup"
_SOURCE_CHANGES_FILE_EXT = "source.changes"
_CHANGES_FILE_EXT = ".changes"
_ORIG_TAR_FILE_EXT = ".orig.tar.gz"
_MASTER_BRANCH = "master"
_BUILD_CMD = "debuild"
_EDITOR_CMD = "editor"
_BUILD_NAME = "final"
_TEST_BUILD_NAME = "test"


class _ActionConf(object):
    """ Action execution configuration. """

    def __init__(self, is_repository_based=True, clean=False, restore=False,
                 critical_branches=None):
        if critical_branches is None:
            critical_branches = []
        self.is_repository_based = is_repository_based
        self.clean = clean
        self.restore_backup = restore
        self.critical_branches = critical_branches


_ACTION_CONF = {
    Action.TEST_PKG: _ActionConf(True, True, True, None),
    Action.COMMIT_RELEASE: _ActionConf(True, True, False,
                                       [Setting.RELEASE_BRANCH,
                                        Setting.UPSTREAM_BRANCH,
                                        Setting.DEBIAN_BRANCH]),
    Action.UPDATE_CHANGELOG: _ActionConf(True, True, False,
                                         [Setting.DEBIAN_BRANCH]),
    Action.TEST_BUILD: _ActionConf(True, True, False, None),
    Action.COMMIT_BUILD: _ActionConf(True, True, False,
                                     [Setting.DEBIAN_BRANCH]),
    Action.UPLOAD: _ActionConf(True, False, False, None),
    Action.CLONE: _ActionConf(False, False, False, None),
    Action.RESTORE: _ActionConf(False, False, False, None),
    Action.CONFIG: _ActionConf(False, False, False, None),

}


########################## Library Function #############################
#########################################################################

def execute_with(**opts):
    """
    Execute action with options.
    Optional arguments:
        :param version:
        :type version: bool
        :param verbose:
        :type verbose: bool
        :param quiet:
        :type quiet: bool
        :param color:
        :type color: bool
        :param no_restore:
        :type no_restore: bool
        :param config: the path to the configuration file
        :type config: str
        :param dir: the working directory
        :type dir: str
        :param action:
        :type action: Action
    """
    flags = {
        Flag.SAFEMODE: opts.get('safemode', False),
        Flag.VERBOSE: opts.get('verbose', False),
        Flag.QUIET: opts.get('quiet', False),
        Flag.COLOR: opts.get('color', False)}

    options = {Option.CONFIG: opts.get('config', DEFAULT_CONFIG_PATH),
               Option.DIR: opts.get('dir', "."),
               Option.VERSION: opts.get('version', False),
               Option.NO_RESTORE: opts.get('norestore', False)}

    action = opts.get('action')

    _execute(flags, options, action)


########################## Argument Parsing #############################
#########################################################################

def _parse_args_and_execute():
    """ Parses arguments and executes requested operations. """

    parser = ArgumentParser(
        description='Maintain debian packages with git and gbp.')

    # Optional arguments.
    parser.add_argument('-V', '--version', action='store_true',
                        help='shows the current version number')
    group_vq = parser.add_mutually_exclusive_group()
    group_vq.add_argument('-v', '--verbose', action='store_true',
                          help='enable verbose mode')
    group_vq.add_argument("-q", "--quiet", action="store_true",
                          help='enable quiet mode')
    parser.add_argument('-c', '--color', action='store_true',
                        help='enable colored output')
    parser.add_argument('-s', '--safemode', action='store_true',
                        help='prevent any file changes')
    parser.add_argument('-n', '--norestore', action='store_true',
                        help='prevent auto restore on command failure')
    parser.add_argument('--config', default=DEFAULT_CONFIG_PATH,
                        help='path to the configuration file')
    # Hidden options.
    parser.add_argument('--show-options', action='store_true', help=SUPPRESS)
    parser.add_argument('--show-actions', action='store_true', help=SUPPRESS)

    # The possible sub commands.
    parser.add_argument('action', nargs='?',
                        choices=[Action.TEST_PKG.value,
                                 Action.COMMIT_RELEASE.value,
                                 Action.UPDATE_CHANGELOG.value,
                                 Action.TEST_BUILD.value,
                                 Action.COMMIT_BUILD.value,
                                 Action.UPLOAD.value,
                                 Action.RESTORE.value,
                                 Action.CLONE.value,
                                 Action.CONFIG.value],
                        help="the main action (see gbpx(1)) for details")

    # General args.
    parser.add_argument('dir', nargs='?', default=getcwd(),
                        help="path to git repository")

    args = parser.parse_args()

    flags = {Flag.SAFEMODE: args.safemode, Flag.VERBOSE: args.verbose,
             Flag.QUIET: args.quiet, Flag.COLOR: args.color}

    options = {Option.CONFIG: args.config, Option.DIR: args.dir,
               Option.NO_RESTORE: args.norestore, Option.VERSION: args.version,
               Option.SHOW_OPTIONS: args.show_options,
               Option.SHOW_ACTIONS: args.show_actions}

    action = Action(args.action) if args.action is not None else None

    # Execute main program.
    _execute(flags, options, action)


######################### Command Execution #############################
#########################################################################

def _execute(flags, options, action):
    """
    Executes the main program phases.
        :param flags:
        :type flags: dict
        :param options: options
        :type options: dict
        :param action: action
        :type action: Action
    """
    # Execute requested options.
    _execute_options(flags, options)

    # Check safemode.
    if flags[Flag.SAFEMODE]:
        log(flags, "Safemode enabled, not changing any files", TextType.INFO)

    # Switch to target directory.
    chdir(options[Option.DIR])

    # Check that an action is selected.
    if action is None:
        log(flags, "No action selected, see \"gbpx --help\"",
            TextType.INFO)
        quit()
    else:
        log(flags, "Executing command: {}".format(action.value),
            TextType.INIT)

    # Create repository backup.
    bak_dir = path.join(_TMP_DIR, _TMP_BAK_SUBDIR, path.basename(getcwd()))
    bak_name = None
    if _ACTION_CONF[action].is_repository_based:
        try:
            log(flags, "\nSaving backup of repository", TextType.INFO)
            bak_name = add_backup(flags, bak_dir, name=action.value)
        except OpError as err:
            log_err(flags, err)
            quit()

    try:
        # Execute initiation phase.
        init_data = _exec_init(flags, action, options[Option.CONFIG])

        # Execute action if allowed.
        if init_data[0]:
            _exec_action(flags, action, init_data[1], options[Option.CONFIG],
                         bak_dir)

        # Restore if required by action.
        if _ACTION_CONF[action].restore_backup:
            try:
                restore_backup(flags, bak_dir, name=bak_name)
            except OpError:
                log(flags, "Restore failed, see \'gbpx {}\'".format(
                    Action.RESTORE) + " to restore repository to " +
                    "previous state", TextType.INFO)

        # Reset if action is repository based (temp commit was made).
        elif _ACTION_CONF[action].is_repository_based:
            try:
                log(flags, "Restoring initial branch state", TextType.INFO)
                restore_temp_commit(flags, init_data[2])
            except Error:
                log(flags, "Could not switch back to initial branch state",
                    TextType.ERR)
    except OpError:
        # Force a backup restore if command has failed.
        log(flags, "\nError recovery for action \'" + action.value +
            "\':", TextType.INIT)
        if _ACTION_CONF[action].is_repository_based:
            if options[Option.NO_RESTORE]:
                log(flags, "Restore has been disabled (-n), " +
                    "see \'gbpx {}\' to restore ".format(Action.RESTORE) +
                    "repository to previous state", TextType.INFO)
            else:
                try:
                    restore_backup(flags, bak_dir, name=bak_name)
                except OpError:
                    log(flags, "Restore failed, see \'gbpx {}\'".format(
                        Action.RESTORE) + " to restore repository to " +
                        "previous state", TextType.INFO)
        else:
            log(flags, "No restore action needed", TextType.INFO)


def _execute_options(flags, options):
    """
    Executes the any standalone options.
        :param flags:
        :type flags: dict
        :param options: options
        :type options: dict
    """
    # Show version.
    if options[Option.VERSION]:
        log(flags, __version__, TextType.INFO)
        # Always exit after showing version.
        quit()

    # Show options.
    if options[Option.SHOW_OPTIONS]:
        print(" ".join(["--{}".format(o.value) for o in Option if
                        o is not Option.SHOW_OPTIONS and
                        o is not Option.SHOW_ACTIONS]))
        # Always exit after listing options.
        quit()

    # Show actions.
    if options[Option.SHOW_ACTIONS]:
        print(" ".join([a.value for a in Action]))
        # Always exit after listing actions.
        quit()


def _exec_init(flags, action, config_path):
    """
    Executes the initiation phase.
    Returns a tuple of:
        - if the given action can be executed
        - the loaded configuration
        - restore data for the initial branch state
        - repository backup name
    """

    # Initialize return values.
    run_action = True
    conf = None
    restore_data = None

    # Prepare if a sub command is used.
    if _ACTION_CONF[action].is_repository_based:

        # Save current branch name and any uncommitted changes.
        try:
            log(flags, "\nSaving initial state to restore after execution",
                TextType.INFO)
            restore_data = create_temp_commit(flags)
            changes_committed = restore_data[2] is not None
        except Error as err:
            log_err(flags, err)
            raise OpError()

        # Pre load config, initialize to 'None' for no-config action.
        log(flags, "\nReading config file", TextType.INFO)
        try:
            # Switch branch to master before trying to read config.
            switch_branch(_MASTER_BRANCH)

            if _ACTION_CONF[action].clean:
                # Try to clean master branch from ignored files.
                try:
                    log(flags,
                        "\nCleaning ignored files from working directory.")
                    clean_repository(flags)
                except Error:
                    # No .gitignore may be available on the current branch.
                    pass

            conf = get_config(config_path)
        except Error as err:
            log_err(flags, err)
            raise OpError()

        # Check for command conflicts with uncommitted changes.
        if changes_committed:
            if get_branch() in [conf[b] for b in
                                _ACTION_CONF[action].critical_branches]:
                log(flags, "Please commit all changes on branch \'" +
                    get_branch() + "\' before running " +
                    "action \'" + action.value + "\'", TextType.ERR)
                run_action = False

    return run_action, conf, restore_data


def _exec_action(flags, action, conf, config_path, bak_dir):
    """
    Executes the given action.
    Returns True if successful, False otherwise.
    """
    line_break(flags)
    # Build release without committing.
    if action == Action.TEST_PKG:
        _test_pkg(conf, flags)

    # Prepare release.
    elif action == Action.COMMIT_RELEASE:
        _commit_release(conf, flags, True)

    # Update the changelog with set options and commit the changes.
    elif action == Action.UPDATE_CHANGELOG:
        _update_changelog(conf, flags, editor=True, commit=True, release=True)

    # Build test package.
    elif action == Action.TEST_BUILD:
        _build(conf, flags, conf[Setting.TEST_BUILD_FLAGS],
               build_name=_TEST_BUILD_NAME)

    # Build a signed package and tag commit.
    elif action == Action.COMMIT_BUILD:
        _build(conf, flags, conf[Setting.BUILD_FLAGS], build_name=_BUILD_NAME,
               tag=True, sign_tag=True, sign_changes=True, sign_source=True)

    # Upload latest build.
    elif action == Action.UPLOAD:
        _upload_pkg(conf, flags)

    # Restore repository to an earlier state.
    elif action == Action.RESTORE:
        _restore_repository(flags, bak_dir)

    # Clone a remote repository and setup the necessary branches.
    elif action == Action.CLONE:
        _clone_source_repository(flags, DEFAULT_CONFIG_PATH)

    # Create example config.
    elif action == Action.CONFIG:
        _create_config(flags, config_path)


####################### Sub Command functions ###########################
#########################################################################

def _test_pkg(conf, flags):
    """
    Prepares a release and builds the package
    but reverts all changes after, leaving the repository unchanged.
    """
    log(flags, "Testing package", TextType.INFO)

    try:
        # Get the tagged version from the release branch.
        latest_release_ver = get_latest_tag_version(
            conf[Setting.RELEASE_BRANCH], conf[Setting.RELEASE_TAG_TYPE])
        next_release_ver = get_next_version(latest_release_ver)
        create_ver = verify_create_head_tag(flags,
                                            conf[Setting.RELEASE_BRANCH],
                                            conf[Setting.RELEASE_TAG_TYPE],
                                            next_release_ver)
        release_ver = create_ver[0]

        # Prepare release, no tags.
        _commit_release(conf, flags, False)

        # Update the changelog to match upstream version.
        debian_ver = release_ver + conf[Setting.DEBIAN_VERSION_SUFFIX]
        _update_changelog(conf, flags, version=debian_ver, commit=True)

        # Test package build.
        _build(conf, flags, conf[Setting.TEST_BUILD_FLAGS],
               build_name=_TEST_BUILD_NAME)

        # Revert changes.
        log(flags, "Reverting changes")
    except Error as err:
        log_err(flags, err)
        raise OpError()


def _commit_release(conf, flags, sign):
    """
    Prepares release, committing the latest to
    upstream and merging with debian. Also tags the upstrem commit.
    Returns the tag name on success.
    """
    log(flags, "Committing release", TextType.INFO)

    # Constants
    tmp_dir = path.join(_TMP_DIR, _TMP_TAR_SUBDIR, conf[Setting.PACKAGE_NAME])
    archive_path = path.join(tmp_dir,
                             conf[Setting.RELEASE_BRANCH] + "_archive.tar")

    try:
        # Get the tagged version from the release branch.
        create_ver = verify_create_head_tag(flags,
                                            conf[Setting.RELEASE_BRANCH],
                                            conf[Setting.RELEASE_TAG_TYPE])
        release_ver = create_ver[0]

        log(flags, "Selected release version \'" +
            release_ver + "\' for upstream commit")

        # Check versions, prepare tarball and import it.
        try:
            upstream_ver = get_head_tag_version(conf[Setting.UPSTREAM_BRANCH],
                                                conf[Setting.UPSTREAM_TAG_TYPE])
        except GitError:
            # No tag was detected, release version is used.
            upstream_ver = None
        source_dir = conf[Setting.PACKAGE_NAME] + "-" + release_ver
        source_dir_path = path.join(tmp_dir, source_dir)
        tar_path = path.join(tmp_dir, conf[Setting.PACKAGE_NAME] + "_" +
                             release_ver + _ORIG_TAR_FILE_EXT)

        # Check that the release version is greater than the upstream version.
        if upstream_ver is not None and \
                not is_version_lt(upstream_ver, release_ver):
            raise GitError("Release version is less than " +
                           "upstream version, aborting")

        # Clean build directory.
        log(flags, "Cleaning tarball directory")
        clean_dir(flags, tmp_dir)
        mkdirs(flags, source_dir_path)

        # Extract the latest commit to release branch.
        log(flags, "Extracting release version \'" + release_ver +
            "\' from release branch \'" +
            conf[Setting.RELEASE_BRANCH] + "\'")

        # Prepare exclude list.
        if conf[Setting.EXCLUDE_FILES] is not None:
            exclude_opts = ["--exclude=" + e for e in
                            conf[Setting.EXCLUDE_FILES]]
        else:
            exclude_opts = []

        # Add .gitignore to excluded if it is present.
        if path.exists(_GIT_IGNORE_PATH):
            exclude_opts.append("--exclude-from={}".format(_GIT_IGNORE_PATH))

        if not flags[Flag.SAFEMODE]:
            exec_cmd(["git", "archive", conf[Setting.RELEASE_BRANCH], "-o",
                      archive_path])
            exec_cmd(["tar", "-xf", archive_path, "--directory=" +
                      source_dir_path] + exclude_opts)

        # Create the upstream tarball.
        log(flags, "Making upstream tarball from extracted source files")
        if not flags[Flag.SAFEMODE]:
            exec_cmd(["tar", "--directory=" + tmp_dir, "-czf", tar_path,
                      source_dir, "--exclude-vcs"])

        # Commit tarball to upstream branch and tag.
        log(flags, "Importing tarball to upstream branch \'" +
            conf[Setting.UPSTREAM_BRANCH] + "\'")

        # Check if should sign and gpg key is set.
        tag_opt = []
        if sign:
            if conf[Setting.GPG_KEY_ID] is not None:
                tag_opt = ["--sign-tags",
                           "--keyid=" + conf[Setting.GPG_KEY_ID]]
            else:
                log(flags, "The gpg key id is not set in the " +
                    "configuration file, disabling tag signing.",
                    TextType.WARNING)

        log(flags,
            "Merging upstream branch \'" + conf[Setting.UPSTREAM_BRANCH] +
            "\' into debian branch \'" + conf[Setting.DEBIAN_BRANCH] + "\'")
        if not flags[Flag.SAFEMODE]:
            exec_cmd(["gbp", "import-orig", "--no-interactive", "--merge"] +
                     tag_opt + [
                         "--merge-mode=replace",
                         "--debian-branch=" + conf[Setting.DEBIAN_BRANCH],
                         "--upstream-branch=" + conf[Setting.UPSTREAM_BRANCH],
                         tar_path])

        # Reset upstream to import commit.
        upstream_tag = conf[Setting.UPSTREAM_TAG_TYPE] + "/" + release_ver
        log(flags,
            "Resetting upstream branch \'" + conf[Setting.UPSTREAM_BRANCH] +
            "\' to import commit \'" + upstream_tag + "\'")
        reset_branch(flags, conf[Setting.UPSTREAM_BRANCH], upstream_tag)

    except Error as err:
        log_err(flags, err)
        raise OpError()

    # Cleanup tarball directory
    log(flags, "Cleaning up temporary files")
    remove_dir(flags, tmp_dir)

    # Print success message.
    log_success(flags)

    # Return the name of the upstream tag.
    return conf[Setting.UPSTREAM_TAG_TYPE] + "/" + release_ver


def _update_changelog(conf, flags, **opts):
    """
    Update the changelog with the git commit messages since last build.
    - version   -- Set to <new version> to be created.
    - editor    -- Set to True to open in a text editor after changes.
    - commit    -- Set to True will commit the changes.
    - release   -- Set to True will prepare release with review in editor.
    """
    version = opts.get('version', None)
    editor = opts.get('editor', False)
    commit = opts.get('commit', False)
    release = opts.get('release', False)

    log(flags, "Updating changelog", TextType.INFO)

    # Build and without tagging and do lintian checks.
    log(flags, "Updating changelog to new version")
    if version is None:
        log(flags, "Version not set, using standard format")
        try:
            upstream_ver = get_head_tag_version(
                conf[Setting.UPSTREAM_BRANCH], conf[Setting.UPSTREAM_TAG_TYPE])
            debian_ver = upstream_ver + conf[Setting.DEBIAN_VERSION_SUFFIX]
            log(flags, "Using version \'" + debian_ver + "\'")
        except Error as err:
            log_err(flags, err)
            raise OpError()
    else:
        debian_ver = version
        log(flags, "Updating changelog with version \'{}\'".format(debian_ver))

    distribution_opt = (["--distribution=" + conf[Setting.DISTRIBUTION]]
                        if conf[Setting.DISTRIBUTION] is not None else [])
    release_opt = (["--release"] if release else [])

    try:
        switch_branch(conf[Setting.DEBIAN_BRANCH])
        if not flags[Flag.SAFEMODE]:
            # Update changelog.
            exec_cmd(["gbp", "dch", "--debian-branch=" +
                      conf[Setting.DEBIAN_BRANCH],
                      "--new-version=" + debian_ver,
                      "--urgency=" + conf[Setting.URGENCY],
                      "--spawn-editor=snapshot"] + distribution_opt +
                     release_opt)

            # Check if editor should be opened.
            if editor:
                exec_editor(_EDITOR_CMD, _CHANGELOG_PATH)

        # Check if changes should be committed.
        if commit:
            log(flags, "Committing updated debian/changelog to branch \'" +
                conf[Setting.DEBIAN_BRANCH] + "\'")
            commit_changes(flags, "Update changelog for " +
                           debian_ver + " release.")
    except Error as err:
        log_err(flags, err)
        raise OpError()

    # Print success message.
    log_success(flags)


def _build(conf, flags, build_flags, **opts):
    """
    Builds package from the latest debian commit.
    - build_flags       -- build flags to use with the build command
    - build_name        -- the build sub directory name
    - tag               -- Set to True to tag the debian commit after build.
    - sign-tag          -- Set to True to sign the created tag.
    - upstream_treeish  -- Set to <treeish> to set the upstream tarball source.
                           instead of the tag version in the changelog.
    - sign_changes      -- Set to True to sign the .changes file.
    - sign_source       -- Set to True to sign the .source file.
    """
    build_name = opts.get('build_name', None)
    tag = opts.get('tag', False)
    sign_tag = opts.get('sign-tag', False)
    upstream_treeish = opts.get('upstream_treeish', None)
    sign_changes = opts.get('sign_changes', False)
    sign_source = opts.get('sign_source', False)

    log(flags, "Building package", TextType.INFO)

    # Check if treeish is used for upstream.
    if upstream_treeish is None:
        try:
            upstream_ver = get_head_tag_version(
                conf[Setting.UPSTREAM_BRANCH], conf[Setting.UPSTREAM_TAG_TYPE])
            log(flags, "Building debian package for upstream version \'" +
                upstream_ver + "\'")
        except Error as err:
            log_err(flags, err)
            raise OpError()
    else:
        log(flags, "Building debian package for \'{}\'".
            format(upstream_treeish))

    # Prepare build.
    log(flags,
        "Switching to debian branch \'" + conf[Setting.DEBIAN_BRANCH] + "\'")
    switch_branch(conf[Setting.DEBIAN_BRANCH])

    try:
        version = exec_cmd(["dpkg-parsechangelog", "--show-field", "Version"])
    except Error as err:
        log_err(flags, err)
        raise OpError()

    # Check if changelog has the correct version.
    if upstream_ver not in version:
        log(flags, "The upstream version \'{}\'".format(upstream_ver) +
            " does not match the changelog version \'{}\'\n".format(version) +
            ", see gbpx {} to update before building".
            format(Action.UPDATE_CHANGELOG), TextType.ERR)
        raise OpError()

    pkg_build_dir = path.join(_BUILD_DIR, conf[Setting.PACKAGE_NAME], version)
    if build_name is not None:
        pkg_build_dir = path.join(pkg_build_dir, build_name)
    log(flags, "Cleaning old build files in \'" + pkg_build_dir + "\'")
    clean_dir(flags, pkg_build_dir)

    # Check if tag should be created.
    tag_opt = ["--git-tag"] if tag else []

    # Prepare tag signing options.
    if sign_tag:
        if conf[Setting.GPG_KEY_ID] is not None:
            tag_opt += ["--git-sign-tags", "--git-keyid=" +
                        str(conf[Setting.GPG_KEY_ID])]
        else:
            log(flags, "The gpg key id is not set in the " +
                "configuration file, disabling tag signing.",
                TextType.WARNING)

    # Prepare treeish identifier option for upstream.
    upstream_opt = (["--git-upstream-tree={}".format(upstream_treeish)]
                    if upstream_treeish is not None else [""])

    # Prepare build signing options.
    sign_build_opt = []
    sign_build_opt += ["-uc"] if not sign_changes else []
    sign_build_opt += ["-us"] if not sign_source else []
    if sign_changes or sign_source:
        if conf[Setting.GPG_KEY_ID] is not None:
            sign_build_opt += ["-k" + conf[Setting.GPG_KEY_ID]]
        else:
            log(flags, "The gpg key id is not set in the " +
                "configuration file, disabling build signing.",
                TextType.WARNING)

    # Prepare build command.
    build_cmd = " ".join([_BUILD_CMD, "--no-lintian"] + sign_build_opt +
                         ([build_flags] if build_flags is not None else []))

    try:
        if not flags[Flag.SAFEMODE]:
            exec_cmd(["gbp", "buildpackage"] + tag_opt + upstream_opt +
                     ["--git-debian-branch=" + conf[Setting.DEBIAN_BRANCH],
                      "--git-upstream-branch=" + conf[Setting.UPSTREAM_BRANCH],
                      "--git-export-dir=" + pkg_build_dir, "--git-builder=" +
                      build_cmd])

            changes_paths = get_files_with_extension(pkg_build_dir,
                                                     _CHANGES_FILE_EXT)
            if changes_paths:
                # Let lintian fail without quitting.
                try:
                    log(flags, "Running Lintian...", TextType.INFO)
                    log(flags, exec_cmd(["lintian", "-Iv", "--color", "auto",
                                         changes_paths[0]]))
                    log(flags, "Lintian Done", TextType.INFO)
                except CommandError as err:
                    if err.std_err:
                        # Some other error.
                        log_err(flags, err)
                    else:
                        # Lintian check failed because of bad package.
                        log(flags, err.std_out.rstrip())
                        log(flags, "Lintian finished with errors",
                            TextType.WARNING)
            else:
                log(flags, "Changes file (" + _CHANGES_FILE_EXT +
                    ") not found in \'" + pkg_build_dir +
                    "\', skipping lintian", TextType.WARNING)
    except Error as err:
        log_err(flags, err)
        raise OpError()

    # Print success message.
    log_success(flags)


def _upload_pkg(conf, flags):
    """
    Uploads the latest build to the ppa set in the config file.
    """
    log(flags, "Uploading package", TextType.INFO)

    # Check if ppa name is set in config.
    if conf[Setting.PPA_NAME] is None:
        log_err(flags, ConfigError(
            "The value {} is not set in the config file, aborting upload".
                format(Setting.PPA_NAME)))
        raise OpError()

    # Set the name of the .changes file and upload.
    pkg_build_dir = path.join(_BUILD_DIR, conf[Setting.PACKAGE_NAME])
    changes_paths = get_files_with_extension(pkg_build_dir,
                                             _SOURCE_CHANGES_FILE_EXT)

    # Filter out test builds and sort the files on version.
    changes_paths = [s for s in changes_paths if
                     path.basename(path.dirname(s)) == _BUILD_NAME]
    changes_paths.sort(
        key=lambda s: findall(r'''\d+''', path.basename(s).split('_')[1]),
        reverse=True)
    if changes_paths:
        # Ask user for confirmation
        if not prompt_user_yn(
                "Upload the latest build (version \'{0}\')?".format(
                    path.basename(changes_paths[0]).split('_')[1])):
            raise OpError()
        try:
            if not flags[Flag.SAFEMODE]:
                exec_cmd(
                    ["dput", "ppa:{}".format(conf[Setting.PPA_NAME]),
                     changes_paths[0]])
        except Error as err:
            log_err(flags, err)
            log(flags, "The package could not be uploaded to ppa:{}".format(
                conf[Setting.PPA_NAME]), TextType.ERR)
    else:
        log(flags,
            "Changefile ({}) not found in \'{}\', aborting upload".format(
                _SOURCE_CHANGES_FILE_EXT, pkg_build_dir), TextType.ERR)
        raise OpError()

    # Print success message.
    log_success(flags)


def _restore_repository(flags, bak_dir):
    """
    Restore the repository to an earlier backed up state.
    - bak_dir   -- The backup storage directory.
    """
    log(flags, "Restoring repository", TextType.INFO)

    try:
        restore_backup(flags, bak_dir)
    except Error as err:
        log_err(flags, err)
        raise OpError()

    # Print success message.
    log_success(flags)


def _clone_source_repository(flags, config_path):
    """ Clones a remote repository and creates the proper branches. """
    log(flags, "Cloning remote source repository", TextType.INFO)

    # The branch identifiers and keys to create.
    branches = [('release', Setting.RELEASE_BRANCH),
                ('upstream', Setting.UPSTREAM_BRANCH),
                ('debian', Setting.DEBIAN_BRANCH)]
    branch_names = []

    try:
        # Prompt user for url.
        url = prompt_user_input("Enter the URL of " +
                                "the remote repository")
        rep_name = get_rep_name_from_url(url)

        # Prompt user for the name of the remote source branch.
        remote_src_branch = prompt_user_input("Enter the name of the " +
                                              "remote source branch",
                                              True, _MASTER_BRANCH)

        # Prompt user for the name of the all branches.
        for entry in branches:
            branch_names.append(prompt_user_input(
                "Enter the name of the {} branch".format(entry[0]), True,
                get_config_default(entry[1])))
        # Clone repository.
        log(flags,
            "Cloning from url \'{0}\' and checking out source branch \'{1}\'".
            format(url, remote_src_branch))
        if not flags[Flag.SAFEMODE]:
            exec_cmd(["git", "clone", "-b", remote_src_branch, url])

        # Move into the cloned repository.
        chdir(rep_name)

        # Create all branches.
        for i, branch_name in enumerate(branch_names):
            if branch_name != remote_src_branch:
                log(flags, "Creating " + branches[i][0] + " branch \'" +
                    branch_name + "\' from source branch \'" +
                    remote_src_branch + "\'")
                if not flags[Flag.SAFEMODE]:
                    exec_cmd(["git", "branch", branch_name])
                switch_branch(remote_src_branch)
            else:
                log(flags, "Not creating " + branches[i][0] + " branch " +
                    "since name conflicts with source branch")

        # Clean upstream branch.
        log(flags, "Cleaning upstream branch \'" + branch_names[1] + "\'")
        switch_branch(branch_names[1])
        if not flags[Flag.SAFEMODE]:
            exec_cmd(["git", "rm", "-rf", "--ignore-unmatch", "*"])
        log(flags, "Creating initial upstream commit on branch \'" +
            branch_names[1] + "\'")
        commit_changes(flags, "Initial upstream commit.")

        # Initiate
        log(flags, "Cleaning debian branch \'" + branch_names[1] + "\'")
        switch_branch(branch_names[2])
        exec_cmd(["git", "rm", "-rf", "--ignore-unmatch", "*"])

        # Let user choose to create example debian files or not.
        if prompt_user_yn("Do you want to create an example debian/ files?"):
            version = prompt_user_input("Enter the initial " +
                                        "package version")
            email = prompt_user_input("Enter the developer " +
                                      "e-mail address", True)
            email_cmd = ["-e", email] if email else []
            if not flags[Flag.SAFEMODE]:
                exec_piped_cmds(["echo", "y"], ["dh_make", "-p", rep_name +
                                                "_" + version, "-i",
                                                "--createorig"] + email_cmd)
                remove_file(flags, glob(path.join("../", "{0}_{1}*".
                                                  format(rep_name, version)))[
                    0])

        log(flags, "Creating initial debian commit on branch \'" +
            branch_names[2] + "\'")
        commit_changes(flags, "Initial debian commit.")

        # Create preset keys.
        preset_keys = {}
        for i, branch_name in enumerate(branch_names):
            preset_keys[branches[i][1]] = branch_name

        # Setup config.
        switch_branch(branch_names[0])
        _create_config(flags, config_path, preset_keys=preset_keys)
        log(flags, "Creating initial release commit on branch \'" +
            branch_names[0] + "\'")
        commit_changes(flags, "Initial release commit.")
    except Error as err:
        log_err(flags, err)
        raise OpError()

    # Print success message.
    log_success(flags)


def _create_config(flags, config_path, preset_keys=None):
    """ Creates example config. """
    log(flags, "Creating example config file", TextType.INFO)

    try:
        log(flags, "Config file is written to " + config_path)
        create_ex_config(flags, config_path, preset_keys)
    except Error as err:
        log_err(flags, err)
        raise OpError()

    # Print success message.
    log_success(flags)


############################ Start script ###############################
#########################################################################
if __name__ == '__main__':
    _parse_args_and_execute()
