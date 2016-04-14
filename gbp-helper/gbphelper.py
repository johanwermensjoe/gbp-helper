#!/usr/bin/env python3
"""
gbphelper module:
Used as a helper script for gbp-buildpackage.
"""
from argparse import ArgumentParser
from glob import glob
from os import path, chdir, getcwd
from re import findall

from gbputil import verify_create_head_tag, OpError, ConfigError, \
    restore_backup, create_ex_config, add_backup, restore_temp_commit, \
    create_temp_commit, get_config, get_config_default
from gitutil import get_head_tag_version, commit_changes, switch_branch, \
    GitError, get_next_version, get_latest_tag_version, is_version_lt, \
    get_rep_name_from_url, clean_ignored_files
from ioutil import Error, log, TextType, prompt_user_input, mkdirs, \
    exec_cmd, get_files_with_extension, clean_dir, \
    log_success, log_err, remove_dir, CommandError, exec_editor, \
    prompt_user_yn, exec_piped_cmds, remove_file

############################## Constants ################################
#########################################################################

__version__ = "0.5"

_DEFAULT_CONFIG_PATH = "gbphelper.conf"
_CHANGELOG_PATH = "debian/changelog"
_BUILD_DIR = "../build-area"
_TMP_DIR = "/tmp"
_TMP_TAR_SUBDIR = "tarball"
_TMP_BAK_SUBDIR = "backup"
_CHANGES_FILE_EXT = "source.changes"
_ORIG_TAR_FILE_EXT = ".orig.tar.gz"
_MASTER_BRANCH = "master"
_BUILD_CMD = "debuild"
_EDITOR_CMD = "editor"
_DEL_EXCLUDE = ","

_CONFIG = \
    [('GIT', [
        ('releaseBranch', "master", True),
        ('releaseTagType', "release", True),
        ('upstreamBranch', "upstream", True),
        ('upstreamTagType', "upstream", True),
        ('debianBranch', "debian", True),
        ('debianTagType', "debian", True)
    ]),
     ('SIGNING', [
         ('gpgKeyId', None, False)
     ]),
     ('BUILD', [
         ('buildFlags', None, False),
         ('testBuildFlags', None, False)
     ]),
     ('PACKAGE', [
         ('packageName', None, False),
         ('distribution', None, False),
         ('urgency', "low", False),
         ('debianVersionSuffix', "-0~ppa1", False),
         ('excludeFiles', _DEFAULT_CONFIG_PATH + ",README.md,LICENCE", False)
     ]),
     ('UPLOAD', [
         ('ppa', None, False)
     ])]


####################### Sub Command functions ###########################
#########################################################################

def test_pkg(conf, flags, bak_dir, bak_name):
    """
    Prepares a release and builds the package
    but reverts all changes after, leaving the repository unchanged.
    """
    log(flags, "\nTesting package", TextType.INFO)

    try:
        # Get the tagged version from the release branch.
        latest_release_ver = get_latest_tag_version(
            conf['releaseBranch'], conf['releaseTagType'])
        next_release_ver = get_next_version(latest_release_ver)
        create_ver = verify_create_head_tag(flags,
                                            conf['releaseBranch'],
                                            conf['releaseTagType'],
                                            next_release_ver)
        release_ver = create_ver[0]

        # Prepare release, no tags.
        commit_release(conf, flags, False)

        # Update the changelog to match upstream version.
        debian_ver = release_ver + conf['debianVersionSuffix']
        update_changelog(conf, flags, version=debian_ver, commit=True)

        # Test package build.
        build_pkg(conf, flags, conf['testBuildFlags'])

        # Revert changes.
        log(flags, "Reverting changes")

        # Restore from backup.
        restore_backup(flags, bak_dir, name=bak_name)
    except Error as err:
        log_err(flags, err)
        raise OpError()

    # Print success message.
    log_success(flags)


def commit_release(conf, flags, sign):
    """
    Prepares release, committing the latest to
    upstream and merging with debian. Also tags the upstrem commit.
    Returns the tag name on success.
    """
    log(flags, "\nCommitting release", TextType.INFO)

    # Constants
    tmp_dir = path.join(_TMP_DIR, conf['packageName'], _TMP_TAR_SUBDIR)
    archive_path = path.join(tmp_dir, conf['releaseBranch'] + "_archive.tar")

    try:
        # Get the tagged version from the release branch.
        create_ver = verify_create_head_tag(flags,
                                            conf['releaseBranch'],
                                            conf['releaseTagType'])
        release_ver = create_ver[0]

        log(flags, "Selected release version \'" +
            release_ver + "\' for upstream commit")

        # Check versions, prepare tarball and import it.
        upstream_ver = get_head_tag_version(
            conf['upstreamBranch'], conf['upstreamTagType'])
        source_dir = conf['packageName'] + "-" + release_ver
        source_dir_path = path.join(tmp_dir, source_dir)
        tar_path = path.join(tmp_dir, conf['packageName'] + "_" +
                             release_ver + _ORIG_TAR_FILE_EXT)

        # Check that the release version is greater than the upstream version.
        if not is_version_lt(upstream_ver, release_ver):
            raise GitError("Release version is less than " +
                           "upstream version, aborting")

        # Clean build directory.
        log(flags, "Cleaning tarball directory")
        clean_dir(flags, tmp_dir)
        mkdirs(flags, source_dir_path)

        # Extract the latest commit to release branch.
        log(flags, "Extracting release version \'" + release_ver +
            "\' from release branch \'" +
            conf['releaseBranch'] + "\'")

        # Prepare exclude list.
        if conf['excludeFiles'] is not None:
            exclude_opts = ["--exclude=" + e for e in
                            conf['excludeFiles'].split(_DEL_EXCLUDE)]
        else:
            exclude_opts = []

        if not flags['safemode']:
            exec_cmd(["git", "archive", conf['releaseBranch'], "-o",
                      archive_path])
            exec_cmd(["tar", "-xf", archive_path, "--directory=" +
                      source_dir_path, "--exclude-vcs"] + exclude_opts)

        # Create the upstream tarball.
        log(flags, "Making upstream tarball from extracted source files")
        if not flags['safemode']:
            exec_cmd(["tar", "--directory=" + tmp_dir, "-czf", tar_path,
                      source_dir])

        # Commit tarball to upstream branch and tag.
        log(flags, "Importing tarball to upstream branch \'" +
            conf['upstreamBranch'] + "\'")

        # Check if should sign and gpg key is set.
        tag_opt = []
        if sign:
            if conf['gpgKeyId'] is not None:
                tag_opt = ["--sign-tags", "--keyid=" + str(conf['gpgKeyId'])]
            else:
                log(flags, "Your gpg key id is not set in your " +
                    "gbp-helper.conf, disabling tag signing.",
                    TextType.WARNING)

        log(flags, "Merging upstream branch \'" + conf['upstreamBranch'] +
            "\' into debian branch \'" + conf['debianBranch'] + "\'")
        if not flags['safemode']:
            exec_cmd(["gbp", "import-orig", "--no-interactive", "--merge"] +
                     tag_opt + ["--debian-branch=" + conf['debianBranch'],
                                "--upstream-branch=" + conf['upstreamBranch'],
                                tar_path])

    except Error as err:
        log_err(flags, err)
        raise OpError()

    # Cleanup tarball directory
    log(flags, "Cleaning up temporary files")
    remove_dir(flags, tmp_dir)

    # Print success message.
    log_success(flags)

    # Return the name of the upstream tag.
    return conf['upstreamTagType'] + "/" + release_ver


def build_pkg(conf, flags, build_flags, **opts):
    """
    Builds package from the latest debian commit.
    - tag               -- Set to True to tag the debian commit after build.
    - sign-tag          -- Set to True to sign the created tag.
    - upstream_treeish  -- Set to <treeish> to set the upstream tarball source.
                           instead of the tag version in the changelog.
    - sign_changes      -- Set to True to sign the .changes file.
    - sign_source       -- Set to True to sign the .source file.
    """
    tag = opts.get('tag', False)
    sign_tag = opts.get('sign-tag', False)
    upstream_treeish = opts.get('upstream_treeish', None)
    sign_changes = opts.get('sign_changes', False)
    sign_source = opts.get('sign_source', False)

    log(flags, "\nBuilding package", TextType.INFO)

    # Check if treeish is used for upstream.
    if upstream_treeish is None:
        try:
            upstream_ver = get_head_tag_version(
                conf['upstreamBranch'], conf['upstreamTagType'])
            log(flags, "Building debian package for upstream version \'" +
                upstream_ver + "\'")
        except Error as err:
            log_err(flags, err)
            raise OpError()
    else:
        log(flags, "Building debian package for \'{}\'".
            format(upstream_treeish))

    # Prepare build.
    log(flags, "Switching to debian branch \'" + conf['debianBranch'] + "\'")
    switch_branch(conf['debianBranch'])

    try:
        version = exec_cmd(["dpkg-parsechangelog", "--show-field", "Version"])
    except Error as err:
        log_err(flags, err)
        raise OpError()

    pkg_build_dir = path.join(_BUILD_DIR, conf['packageName'], version)
    log(flags, "Cleaning old build files in \'" + pkg_build_dir + "\'")
    clean_dir(flags, pkg_build_dir)

    # Check if tag should be created.
    tag_opt = ["--git-tag"] if tag else []

    # Prepare tag signing options.
    if sign_tag:
        if conf['gpgKeyId'] is not None:
            tag_opt += ["--git-sign-tags", "--git-keyid=" +
                        str(conf['gpgKeyId'])]
        else:
            log(flags, "Your gpg key id is not set in your " +
                "gbp-helper.conf, disabling tag signing.",
                TextType.WARNING)

    # Prepare treeish identifier option for upstream.
    upstream_opt = (["--git-upstream-tree={}".format(upstream_treeish)]
                    if upstream_treeish is not None else [""])

    # Prepare build signing options.
    sign_build_opt = []
    sign_build_opt += ["-uc"] if not sign_changes else []
    sign_build_opt += ["-us"] if not sign_source else []
    if sign_changes or sign_source:
        if conf['gpgKeyId'] is not None:
            sign_build_opt += ["-k" + conf['gpgKeyId']]
        else:
            log(flags, "Your gpg key id is not set in your " +
                "gbp-helper.conf, disabling build signing.",
                TextType.WARNING)

    # Prepare build command.
    build_cmd = " ".join([_BUILD_CMD, "--no-lintian"] + sign_build_opt +
                         ([build_flags] if build_flags is not None else []))

    try:
        if not flags['safemode']:
            exec_cmd(["gbp", "buildpackage"] + tag_opt + upstream_opt +
                     ["--git-debian-branch=" + conf['debianBranch'],
                      "--git-upstream-branch=" + conf['upstreamBranch'],
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


def update_changelog(conf, flags, **opts):
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

    log(flags, "\nUpdating changelog", TextType.INFO)

    # Build and without tagging and do lintian checks.
    log(flags, "Updating changelog to new version")
    if version is None:
        log(flags, "Version not set, using standard format")
        try:
            upstream_ver = get_head_tag_version(
                conf['upstreamBranch'], conf['upstreamTagType'])
            debian_ver = upstream_ver + conf['debianVersionSuffix']
            log(flags, "Using version \'" + debian_ver + "\'")
        except Error as err:
            log_err(flags, err)
            raise OpError()
    else:
        debian_ver = version
        log(flags, "Updating changelog with version \'{}\'".format(debian_ver))

    distribution_opt = (["--distribution=" + conf['distribution']]
                        if conf['distribution'] is not None else [])
    release_opt = (["--release"] if release else [])

    try:
        switch_branch(conf['debianBranch'])
        if not flags['safemode']:
            # Update changelog.
            exec_cmd(["gbp", "dch", "--debian-branch=" +
                      conf['debianBranch'], "--new-version=" + debian_ver,
                      "--urgency=" + conf['urgency'],
                      "--spawn-editor=snapshot"] + distribution_opt +
                     release_opt)

            # Check if editor should be opened.
            if editor:
                exec_editor(_EDITOR_CMD, _CHANGELOG_PATH)

        # Check if changes should be committed.
        if commit:
            log(flags, "Committing updated debian/changelog to branch \'" +
                conf['debianBranch'] + "\'")
            commit_changes(flags, "Update changelog for " +
                           debian_ver + " release.")
    except Error as err:
        log_err(flags, err)
        raise OpError()

    # Print success message.
    log_success(flags)


def upload_pkg(conf, flags):
    """
    Uploads the latest build to the ppa set in the config file.
    """
    log(flags, "\nUploading package", TextType.INFO)

    # Check if ppa name is set in config.
    if conf['ppa'] is None:
        log_err(flags, ConfigError("The value ppaName is not set" +
                                   " in the config file, aborting upload"))
        raise OpError()

    # Set the name of the .changes file and upload.
    pkg_build_dir = path.join(_BUILD_DIR, conf['packageName'])
    changes_paths = get_files_with_extension(pkg_build_dir,
                                             _CHANGES_FILE_EXT)

    # Sort the files on version.
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
            if not flags['safemode']:
                exec_cmd(["dput", "ppa:" + conf['ppa'], changes_paths[0]])
        except Error as err:
            log_err(flags, err)
            log(flags, "The package could not be uploaded to ppa:" +
                conf['ppa'], TextType.ERR)
    else:
        log(flags, "Changefile (" + _CHANGES_FILE_EXT + ") not found in " +
            "\'" + pkg_build_dir + "\', aborting upload", TextType.ERR)
        raise OpError()

    # Print success message.
    log_success(flags)


def reset_repository(flags, bak_dir):
    """
    Reset the repository to an earlier backed up state.
    - bak_dir   -- The backup storage directory.
    """
    log(flags, "\nResetting repository", TextType.INFO)

    try:
        restore_backup(flags, bak_dir)
    except Error as err:
        log_err(flags, err)
        raise OpError()

    # Print success message.
    log_success(flags)


def clone_source_repository(flags):
    """ Clones a remote repository and creates the proper branches. """
    log(flags, "\nCloning remote source repository", TextType.INFO)

    # The branch identifiers and keys to create.
    branches = [('release', 'releaseBranch'), ('upstream', 'upstreamBranch'),
                ('debian', 'debianBranch')]
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
            branch_names.append(prompt_user_input("Enter the name " +
                                                  "of the " + entry[
                                                      0] + " branch",
                                                  True,
                                                  get_config_default(
                                                      entry[1], _CONFIG)
                                                  ))
        # Clone repository.
        log(flags,
            "Cloning from url \'{0}\' and checking out source branch \'{1}\'".
            format(url, remote_src_branch))
        if not flags['safemode']:
            exec_cmd(["git", "clone", "-b", remote_src_branch, url])

        # Move into the cloned repository.
        chdir(rep_name)

        # Create all branches.
        for i, branch_name in enumerate(branch_names):
            if branch_name != remote_src_branch:
                log(flags, "Creating " + branches[i][0] + " branch \'" +
                    branch_name + "\' from source branch \'" +
                    remote_src_branch + "\'")
                if not flags['safemode']:
                    exec_cmd(["git", "branch", branch_name])
                switch_branch(remote_src_branch)
            else:
                log(flags, "Not creating " + branches[i][0] + " branch " +
                    "since name conflicts with source branch")

        # Clean upstream branch.
        log(flags, "Cleaning upstream branch \'" + branch_names[1] + "\'")
        switch_branch(branch_names[1])
        if not flags['safemode']:
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
            if not flags['safemode']:
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
        create_config(flags, _DEFAULT_CONFIG_PATH, preset_keys)
        log(flags, "Creating initial release commit on branch \'" +
            branch_names[0] + "\'")
        commit_changes(flags, "Initial release commit.")
    except Error as err:
        log_err(flags, err)
        quit()

    # Print success message.
    log_success(flags)


def create_config(flags, config_path, preset_keys=None):
    """ Creates example config. """
    log(flags, "\nCreating example config file", TextType.INFO)

    try:
        log(flags, "Config file is written to " + config_path)
        create_ex_config(flags, config_path, _CONFIG, preset_keys)
    except Error as err:
        log_err(flags, err)
        quit()

    # Print success message.
    log_success(flags)


######################### Command Execution #############################
#########################################################################

def execute(flags, args):
    """ Executes the main program phases. """
    # Execute requested options.
    exec_options(args, flags)

    # Switch to target directory.
    chdir(args.dir)

    action = args.action

    # Determine if action is repository based.
    rep_action = (action != 'reset' and
                  action != 'clone-src' and
                  action != 'create-config')

    # Create repository backup.
    bak_dir = path.join(_TMP_DIR, path.basename(getcwd()), _TMP_BAK_SUBDIR)
    bak_name = None
    if rep_action:
        try:
            log(flags, "Saving backup of repository", TextType.INFO)
            bak_name = add_backup(flags, bak_dir, action)
        except OpError as err:
            log_err(flags, err)
            quit()

    # Execute initiation phase.
    init_data = exec_init(flags, action, rep_action, args.config)

    # Execute action if allowed.
    if init_data[0]:
        action_ok = exec_action(flags, action, init_data[1],
                                args.config, bak_dir, bak_name)
    else:
        action_ok = False

    # Force a backup restore if command has failed.
    if not action_ok:
        log(flags, "\nError recovery for action \'" + action +
            "\':", TextType.INIT)
        if args.norestore:
            log(flags, "Restore has been disabled (-n), " +
                "try \'gbp-helper reset\' to restore repository to " +
                "previous state", TextType.INFO)
        elif rep_action:
            # Disable branch restore.
            rep_action = False
            try:
                restore_backup(flags, bak_dir, name=bak_name)
            except OpError:
                log(flags, "Restore failed, " +
                    "try \'gbp-helper reset\' to restore repository to " +
                    "previous state", TextType.INFO)

    # Restore initial branch state if action is repository based.
    if rep_action:
        try:
            log(flags, "Restoring initial branch state", TextType.INFO)
            restore_temp_commit(flags, init_data[2])
        except Error:
            log(flags, "Could not switch back to initial branch state",
                TextType.ERR)


def exec_options(args, flags):
    """
    Executes any operations for options specified in args.
    Logs special options set in flags
    """
    # Show version.
    if args.version:
        log(flags, __version__)
        # Always exit after showing version.
        quit()

    # Check safemode.
    if flags['safemode']:
        log(flags, "Safemode enabled, not changing any files", TextType.INFO)


def exec_init(flags, action, rep_action, config_path):
    """
    Executes the initiation phase.
    Returns a tuple of:
        - if the given action can be executed
        - the loaded configuration
        - restore data for the initial branch state
        - repository backup name
    """

    # Initialize return values.
    changes_committed = False
    conf = None
    restore_data = None

    # Prepare if a sub command is used.
    if action and rep_action:
        # Try to clean current branch from ignored files.
        try:
            log(flags, "Cleaning ignored files from working directory.")
            clean_ignored_files(flags)
        except Error:
            # No .gitignore may be available on the current branch.
            pass

        # Save current branch name and any uncommitted changes.
        try:
            log(flags, "Saving initial state to restore after execution",
                TextType.INFO)
            restore_data = create_temp_commit(flags)
            changes_committed = restore_data[2] is not None
        except Error as err:
            log_err(flags, err)
            quit()

        # Pre load config, initialize to 'None' for no-config action.
        log(flags, "Reading config file", TextType.INFO)
        try:
            # Switch branch to master before trying to read config.
            switch_branch(_MASTER_BRANCH)
            conf = get_config(config_path, _CONFIG)
        except Error as err:
            log_err(flags, err)
            quit()

    # Check for command conflicts with uncommitted changes.
    run_action = not changes_committed
    if changes_committed:
        # For debian branch.
        if restore_data[0] == conf['debianBranch'] and \
                (action == 'commit-release' or
                         action == 'update-changelog' or
                         action == 'commit-build'):
            log(flags, "Commit all changes on debian branch \'" +
                conf['debianBranch'] + "\' before running " +
                "action \'" + action + "\'", TextType.ERR)
        # For release branch.
        elif restore_data[0] == conf['releaseBranch'] and \
                (action == 'commit-release'):
            log(flags, "Please commit all changes on release branch \'" +
                conf['releaseBranch'] + "\' before running " +
                "action \'" + action + "\'", TextType.ERR)
        # For upstream branch.
        elif restore_data[0] == conf['upstreamBranch']:
            # Should never happen.
            log(flags, "Uncommitted changes were found on upstream branch " +
                "\'" + conf['upstreamBranch'] + "\'\nThis should " +
                "never happen, please correct before proceeding",
                TextType.ERR)
        else:
            run_action = True

    return run_action, conf, restore_data


def exec_action(flags, action, conf, config_path, bak_dir, bak_name=None):
    """
    Executes the given action.
    Returns True if successful, False otherwise.
    """

    log(flags, "\nExecuting command: " + action, TextType.INIT)
    try:
        # Build release without committing.
        if action == 'test-pkg':
            test_pkg(conf, flags, bak_dir, bak_name)

        # Prepare release.
        elif action == 'commit-release':
            commit_release(conf, flags, True)

        # Updates the changelog with set options and commits the changes.
        elif action == 'update-changelog':
            update_changelog(conf, flags, editor=True,
                             commit=True, release=True)

        # Build test package.
        elif action == 'test-build':
            build_pkg(conf, flags, conf['testBuildFlags'])

        # Build a signed package and tag commit.
        elif action == 'commit-build':
            build_pkg(conf, flags, conf['buildFlags'], tag=True,
                      sign_tag=True, sign_changes=True, sign_source=True)

        # Upload latest build.
        elif action == 'upload-pkg':
            upload_pkg(conf, flags)

        # Restore repository to an earlier state.
        elif action == 'reset':
            reset_repository(flags, bak_dir)

        # Clone a remote repository and setup the necessary branches.
        elif action == 'clone-src':
            clone_source_repository(flags)

        # Create example config.
        elif action == 'create-config':
            create_config(flags, config_path)

        # Action was successful.
        return True

    except OpError:
        return False


########################## Argument Parsing #############################
#########################################################################

def parse_args_and_execute():
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
    parser.add_argument('--config', default=_DEFAULT_CONFIG_PATH,
                        help='path to the gbp-helper.conf file')

    # The possible sub commands.
    parser.add_argument('action', nargs='?',
                        choices=['test-pkg', 'commit-release',
                                 'update-changelog',
                                 'test-build', 'commit-build', 'upload-pkg',
                                 'reset',
                                 'clone-src', 'create-config'],
                        help="the main action (see gbp-helper(1)) for details")

    # General args.
    parser.add_argument('dir', nargs='?', default=getcwd(),
                        help="path to git repository")

    args = parser.parse_args()

    flags = {'safemode': args.safemode, 'verbose': args.verbose,
             'quiet': args.quiet, 'color': args.color}

    # Execute main program.
    execute(flags, args)


############################ Start script ###############################
#########################################################################
parse_args_and_execute()
