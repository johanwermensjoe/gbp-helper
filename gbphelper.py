#!/usr/bin/env python

"""
gbphelper module:
Used as a helper script for gbp-buildpackage.
"""

import os
import argparse
import gbputil
from gbputil import Error, GitError, CommandError, ConfigError
from gbputil import log, log_err, log_success, TextType
from gbputil import exec_cmd

__version__ = "0.2"

############################## Constants ################################
#########################################################################

_DEFAULT_CONFIG_PATH = "gbphelper.conf"
_BUILD_DIR = "../build-area"
_BUILD_CMD = "debuild"
_CHANGES_FILE_EXT = ".changes"
_ORIG_TAR_FILE_EXT = ".orig.tar.gz"
_TMP_DIR = "/tmp"
_MASTER_BRANCH = "master"

_CONFIG = \
[('GIT', [\
    ('releaseBranch', "master", True), \
    ('releaseTagType', "release", True), \
    ('upstreamBranch', "upstream", True), \
    ('upstreamTagType', "upstream", True), \
    ('debianBranch', "debian", True), \
    ('debianTagType', "debian", True) \
]), \
('SIGNING', [\
    ('gpgKeyId', None, False) \
]), \
('BUILD', [\
    ('buildFlags', None, False), \
    ('testBuildFlags', None, False) \
]), \
('PACKAGE', [\
    ('packageName', None, False), \
    ('distribution', None, False), \
    ('urgency', "low", False), \
    ('debianVersionSuffix', "-0~ppa1", False) \
]), \
('UPLOAD', [ \
    ('ppa', None, False) \
])]

####################### Sub Command functions ###########################
#########################################################################

def create_config(flags, config_path):
    """ Creates example config. """
    log(flags, "Creating example config file: " + config_path)
    try:
        gbputil.create_ex_config(flags, config_path, _CONFIG)
    except ConfigError as err:
        log_err(flags, err)
        quit()

    # Print success message.
    log_success(flags)

def prepare_release(conf, flags, sign):
    """
    Prepares release, committing the latest to
    upstream and merging with debian. Also tags the upstrem commit.
    Returns the tag name on success.
    """
    # Constants
    log(flags, "Setting build paths")
    tmp_path = os.path.join(_TMP_DIR, conf['packageName'])
    archive_path = os.path.join(tmp_path, conf['releaseBranch'] + "_archive.tar")

    # Get the tagged version from the release branch.
    try:
        release_version = gbputil.get_head_tag_version( \
                            conf['releaseBranch'], conf['releaseTagType'])
        log(flags, "Creating upstream for release version \'" + \
                        release_version + "\'")
        
        upstream_version = gbputil.get_head_tag_version( \
                            conf['upstreamBranch'], conf['upstreamTagType'])
        source_dir = conf['packageName'] + "-" + release_version
        source_dir_path = os.path.join(tmp_path, source_dir)
        tar_path = os.path.join(tmp_path, conf['packageName'] + "_" + \
                    release_version + _ORIG_TAR_FILE_EXT)

        # Check that the release version is greater than the upstream version.
        if not gbputil.is_version_lt(upstream_version, release_version):
            raise GitError("Release version is less than " + \
                            "upstream version, aborting")

        # Clean ignored files.
        log(flags, "Cleaning ignored files from working directory.")
        gbputil.switch_branch(conf['releaseBranch'])
        gbputil.clean_ignored_files(flags)

        # Clean build directory.
        log(flags, "Cleaning build directory")
        gbputil.clean_dir(flags, tmp_path)
        if not flags['safemode']:
            os.makedirs(source_dir_path)

        # Extract the latest commit to release branch.
        log(flags, "Extracting release version \'" + release_version + \
                        "\' from release branch \'" + \
                        conf['releaseBranch'] + "\'")
        if not flags['safemode']:
            exec_cmd(["git", "archive", conf['releaseBranch'], "-o", \
                        archive_path])
            exec_cmd(["tar", "-xf", archive_path, "--directory=" + \
                        source_dir_path, "--exclude=" + \
                            _DEFAULT_CONFIG_PATH, "--exclude=README.md", \
                        "--exclude=LICENSE", "--exclude-vcs"])

        # Create the upstream tarball.
        log(flags, "Making upstream tarball from extracted source files")
        if not flags['safemode']:
            exec_cmd(["tar", "--directory=" + tmp_path, "-czf", tar_path, \
                        source_dir])

        # Commit tarball to upstream branch and tag.
        log(flags, "Importing tarball to upstream branch \'" + \
                conf['upstreamBranch'] + "\'")

        # Check if sould sign and gpg key is set.
        tag_opt = []
        if sign:
            if conf['gpgKeyId']:
                tag_opt = ["--sign-tags", "--keyid=" + str(conf['gpgKeyId'])]
            else:
                log(flags, "Your gpg key id is not set in your " + \
                            "gbp-helper.conf, disabling tag signing.", \
                            TextType.WARNING)

        if not flags['safemode']:
            exec_cmd(["gbp", "import-orig", "--no-interactive", "--merge"] + \
                        tag_opt + ["--debian-branch=" + conf['debianBranch'], \
                        "--upstream-branch=" + conf['upstreamBranch'], tar_path])

    except Error as err:
        log_err(flags, err)
        quit()

    # Cleanup.git status
    log(flags, "Cleaning up temporary files")
    if not flags['safemode']:
        gbputil.remove_dir(flags, tmp_path)

    # Print success message.
    log_success(flags)

    # Return the name of the upstream tag.
    return conf['upstreamTagType'] + "/" + release_version

def test_release(conf, flags):
    """
    Prepares a release and builds the package
    but reverts all changes after, leaving the repository unchanged.
    """
    # Try to get the tag of the master HEAD.
    try:
        release_commit = gbputil.get_head_commit(conf['releaseBranch'])
    except GitError as err:
        log_err(flags, err)
        quit()

    if not gbputil.is_working_dir_clean():
        # Only stash if uncommitted changes are on release branch.
        current_branch = gbputil.get_branch()
        if current_branch == conf['releaseBranch']:
            log(flags, "Stashing uncommited changes on release branch \'" + \
                    conf['releaseBranch'] + "\'")
            reset_release = True
            try:
                # Save changes to tmp stash.
                stash_name = "gbp-helper<" + release_commit + ">"
                gbputil.stash_changes(flags, stash_name)

                # Apply stash and create a tmp commit.
                log(flags, "Creating temporary release commit")
                gbputil.apply_stash(flags, stash_name, False)
                gbputil.commit_changes(flags, "Temp release commit.")
            except GitError as err:
                log_err(flags, err)
        else:
            # Uncommitted changes on another branch, quit
            log(flags, "Uncommitted changes on branch \'" + current_branch + \
                    "\', commit before proceding.", TextType.ERR)
            quit()
    else:
        log(flags, "Working directory clean, no commit needed")
        reset_release = False

    try:
        # Tag the last commit properly.
        # Only tag if no tags exists at HEAD.
        if not gbputil.get_head_tags(conf['releaseBranch']):
            remove_release_tag = True
            latest_release_version = gbputil.get_latest_tag_version( \
                                conf['releaseBranch'], conf['releaseTagType'])
            tmp_version = gbputil.get_next_version(latest_release_version)
            tmp_release_tag = conf['releaseTagType'] + "/" + tmp_version

            log(flags, "Tagging release HEAD as \'" + tmp_release_tag + "\'")
            gbputil.tag_head(flags, conf['releaseBranch'], tmp_release_tag)
        else:
            log(flags, "Release HEAD already tagged, skipping tagging")
            remove_release_tag = False

        # Store debian and upstream commits to later revert to them.
        debian_commit = gbputil.get_head_commit(conf['debianBranch'])
        upstream_commit = gbputil.get_head_commit(conf['upstreamBranch'])

        # Prepare release, no tags.
        upstream_tag = prepare_release(conf, flags, False)

        # Find the HEAD release version.
        release_version = gbputil.get_head_tag_version( \
                                conf['releaseBranch'], conf['releaseTagType'])

        # Update the changlog to match upstream version.
        tmp_debian_version = release_version + conf['debianVersionSuffix']
        update_changelog(conf, flags, version=tmp_debian_version, commit=True)

        # Test package build.
        build_pkg(conf, flags, conf['testBuildFlags'])

        # Revert changes.
        log(flags, "Reverting changes")

        # Delete upstream tag.
        gbputil.delete_tag(flags, upstream_tag)

        # Remove temporary release tag if created.
        if remove_release_tag:
            log(flags, "Removing temporary release tag \'" + \
                    tmp_release_tag + "\'")
            gbputil.delete_tag(flags, tmp_release_tag)

        # Reset master if needed.
        if reset_release:
            log(flags, "Resetting release branch \'" + \
                    conf['releaseBranch'] + "\'to commit \'" + \
                    release_commit + "\'")
            log(flags, "Restoring uncommitted changes from stash to " + \
                    "release branch \'" + conf['releaseBranch'] + "\'")
            gbputil.reset_branch(flags, conf['releaseBranch'], release_commit)
            gbputil.apply_stash(flags, conf['releaseBranch'], stash_name, True)

        # Reset debian and upstream branches.
        log(flags, "Resetting debian branch \'" + conf['debianBranch'] + \
                "\' to commit \'" + debian_commit + "\'")
        log(flags, "Resetting upstream branch \'" + conf['upstreamBranch'] + \
                "\' to commit \'" + upstream_commit + "\'")
        gbputil.reset_branch(flags, conf['debianBranch'], debian_commit)
        gbputil.reset_branch(flags, conf['upstreamBranch'], upstream_commit)

    except GitError as err:
        log_err(flags, err)
        quit()

    # Print success message.
    log_success(flags)

def upload_pkg(conf, flags):
    """ Uploads the latest build to the ppa set in the config file. """
    # Ask user for confirmation
    if not gbputil.prompt_user_yn("Upload the latest build?"):
        quit()

    # Check if ppa name is set in config.
    if not conf['ppaName']:
        log_err(flags, ConfigError("The value ppaName is not set" + \
                                " in the config file, aborting upload"))
        quit()

    # Make sure that the latest debian commit is tagged.
    try:
        gbputil.get_head_tag_version(conf['debianBranch'], \
                                        conf['debianTagType'])
    except GitError as err:
        log_err(flags, err)
        log(flags, "The latest debian commit isn't porperly tagged, " + \
                        "run gbp-helper -b", TextType.ERR)
        quit()

    # Set the name of the .changes file and upload.
    changes_file = gbputil.get_file_with_extension(_BUILD_DIR, \
                                                    _CHANGES_FILE_EXT)
    if changes_file:
        try:
            if not flags['safemode']:
                exec_cmd(["dput", "ppa:" + conf['ppaName'], \
                            os.path.join(_BUILD_DIR, changes_file)])
        except CommandError as err:
            log_err(flags, err)
            log(flags, "The package could not be uploaded to ppa:" + \
                    conf['ppaName'], TextType.ERR)
    else:
        log(flags, "Changefile (" + _CHANGES_FILE_EXT + ") not found in " + \
                    "\'" + _BUILD_DIR + "\', aborting upload", TextType.ERR)
        quit()

    # Print success message.
    log_success(flags)

def build_pkg(conf, flags, build_flags, tag=False, sign_tag=False, \
                upstream_treeish=None, sign_changes=False, sign_source=False):
    """
    Builds package from the latest debian commit.
    Tags the debian commit if arg: "tag" is True.
    Signs the created tag if signTag (and tag) is True.
    Uses a treeish decriptor to create the upstream tarball
    instead of a changelog ref.
    """
    # Check if treeish is used for upstream.
    if not upstream_treeish:
        try:
            upstream_version = gbputil.get_head_tag_version( \
                                conf['upstreamBranch'], conf['upstreamTagType'])
            log(flags, "Building debian package for upstream version \'" + \
                            upstream_version + "\'")
        except GitError as err:
            log_err(err)
            quit()
    else:
       log(flags, "Building debian package for \'" + upstream_treeish + "\'")

    # Prepare build.
    log(flags, "Switching to debian branch \'" + conf['debianBranch'] + "\'")
    gbputil.switch_branch(conf['debianBranch'])

    log(flags, "Cleaning old build files in \'" + _BUILD_DIR + "\'")
    gbputil.clean_dir(flags, _BUILD_DIR)

    # Check if tag should be created.
    tag_opt = ["--git-tag"] if tag else []

    # Prepare tag signing options.
    if sign_tag:
        if conf['gpgKeyId']:
            tag_opt += ["--git-sign-tags", "--git-keyid=" + str(conf['gpgKeyId'])]
        else:
            log(flags, "Your gpg key id is not set in your " + \
                        "gbp-helper.conf, disabling tag signing.", \
                        TextType.WARNING)

    # Prepare treeish identifier option for upstream.
    upstream_opt = (["--git-upstream-tree=" + upstream_treeish] \
                        if upstream_treeish else [""])

    # Prepare build signing options.
    sign_build_opt = []
    sign_build_opt += ["-uc"] if not sign_changes else []
    sign_build_opt += ["-us"] if not sign_source else []
    if sign_changes or sign_source:
        if conf['gpgKeyId']:
            sign_build_opt += ["-k" + conf['gpgKeyId']]
        else:
            log(flags, "Your gpg key id is not set in your " + \
                        "gbp-helper.conf, disabling build signing.", \
                        TextType.WARNING)

    # Prepare build command.
    build_cmd = " ".join([_BUILD_CMD, "--no-lintian"] + sign_build_opt + \
                            ([build_flags] if build_flags else []))

    try:
        if not flags['safemode']:
            exec_cmd(["gbp", "buildpackage"] + tag_opt + upstream_opt + \
                    ["--git-debian-branch=" + conf['debianBranch'], \
                    "--git-upstream-branch=" + conf['upstreamBranch'], \
                    "--git-export-dir=" + _BUILD_DIR, "--git-builder=" + \
                    build_cmd])

            changes_file = gbputil.get_file_with_extension(_BUILD_DIR, \
                                                            _CHANGES_FILE_EXT)
            if changes_file:
                # Let lintian fail without quitting.
                try:
                    log(flags, "Running Lintian...", TextType.INFO)
                    log(flags, exec_cmd(["lintian", "-Iv", "--color", "auto", \
                        os.path.join(_BUILD_DIR, changes_file)]).rstrip())
                    log(flags, "Lintian Done", TextType.INFO)
                except CommandError as err:
                    if err.stderr:
                        # Some other error.
                        log_err(err)
                    else:
                        # Linitan check failed because of bad package.
                        log(flags, err.stdout.rstrip())
                        log(flags, "Lintian finished with errors", \
                                TextType.WARNING)
            else:
                log(flags, "Changes file (" + _CHANGES_FILE_EXT + \
                        ") not found in \'" + _BUILD_DIR + \
                        "\', skipping lintian", TextType.WARNING)
    except CommandError as err:
        log_err(flags, err)
        quit()

    # Print success message.
    log_success(flags)

def update_changelog(conf, flags, version=None, commit=False, release=False):
    """
    Update the changelog with the git commit messsages since last build.
    - version   -- Set to <new version> to be created.
    - commit    -- Set to True will commit the changes.
    - release   -- Set to True will prepare release with review in editor.
    """
    # Build and without tagging and do linthian checks.
    log(flags, "Updating changelog to new version")
    if not version:
        log(flags, "Version not set, using standard format")
        try:
            upstream_version = gbputil.get_head_tag_version( \
                            conf['upstreamBranch'], conf['upstreamTagType'])
            version = upstream_version + conf['debianVersionSuffix']
            log(flags, "Using version \'" + version + "\'")
        except GitError as err:
            log_err(flags, err)
            quit()
    else:
        log(flags, "Updating changelog with version \'" + version + "\'")

    commit_opt = (["--commit"] if commit else [])
    distribution_opt = (["--distribution=" + conf['distribution']] \
                            if conf['distribution'] else [])
    release_opt = (["--release"] if release else [])

    try:
        gbputil.switch_branch(conf['debianBranch'])
        if not flags['safemode']:
            exec_cmd(["gbp", "dch", "--debian-branch=" + \
                    conf['debianBranch'], "--new-version=" + version, \
                    "--urgency=" + conf['urgency'], \
                    "--spawn-editor=snapshot"] + commit_opt + \
                    distribution_opt + release_opt)
        if commit:
            log(flags, "Committing updated debian/changelog to branch \'" + \
                    conf['debianBranch'] + "\'")
    except Error as err:
        log_err(flags, err)
        quit()

    # Print success message.
    log_success(flags)

######################### Command Execution #############################
#########################################################################

def exec_options(args, flags):
    """
    Executs any operations for options specified in args.
    Logs special options set in flags
    """
    # Show version.
    if args.version:
        log(flags, __version__, 1)
        # Always exit after showing version.
        quit()

    # Check safemode.
    if flags['safemode']:
        log(flags, "Safemode enabled, not changing any files", TextType.INFO)

def exec_action(flags, action, config_path, rep_dir):
    """ Executes the given action. """
    # Switch to target directory.
    os.chdir(rep_dir)

    # Prepare if a subcommand is used.
    if action and action != 'create-config':
        # Pre load config if not being created.
        log(flags, "Reading config file", TextType.INFO)
        try:
            # Switch branch to master before trying to read config.
            gbputil.switch_branch(_MASTER_BRANCH)
            conf = gbputil.get_config(config_path, _CONFIG)
        except Error as err:
            log_err(flags, err)
            quit()

        # Save current branch name.
        try:
            initial_branch = gbputil.get_branch()
            log(flags, "Saving initial branch \'" + initial_branch + "\' " + \
                        "to restore after execution", TextType.INFO)
        except GitError as err:
            log_err(flags, err)
            quit()

    ## Sub commands ##
    log(flags, "\nExecuting commad: " + action, TextType.INIT)

    # Create example config.
    if action == 'create-config':
        create_config(flags, config_path)

    # Prepare release.
    elif action == 'prepare-release':
        prepare_release(conf, flags, True)

    # Build release without commiting.
    elif action == 'test-release':
        test_release(conf, flags)

    # Updates the changelog with set options and commits the changes.
    elif action == 'update-changelog':
        update_changelog(conf, flags, commit=True, release=True)

    # Upload latest build.
    elif action == 'upload':
        upload_pkg(conf, flags)

    # Build test package.
    elif action == 'build-pkg':
        build_pkg(conf, flags, conf['testBuildFlags'])

    # Build and commit package.
    elif action == 'commit-pkg':
        build_pkg(conf, flags, conf['buildFlags'], tag=True, \
                    sign_tag=True, sign_changes=True, sign_source=True)

    # Restore branch state.
    try:
        # Only try to switch back if update-changelog hasn't run (leaves changes).
        if initial_branch != gbputil.get_branch() and \
                action != 'update-changelog':
            log(flags, "Restoring active branch to \'" + initial_branch + \
                    "\'", TextType.INFO)
            gbputil.switch_branch(initial_branch)
    except GitError as err:
        log_err(flags, err)

########################## Argument Parsing #############################
#########################################################################

def parse_args_and_execute():
    """ Parses arguments and executes requested operations. """

    parser = argparse.ArgumentParser( \
                description='Helps maintain debian packeges with git.')

    # Optional arguments.
    parser.add_argument('-V', '--version', action='store_true', \
        help='shows the version')
    group_vq = parser.add_mutually_exclusive_group()
    group_vq.add_argument('-v', '--verbose', action='store_true', \
        help='enables verbose mode')
    group_vq.add_argument("-q", "--quiet", action="store_true", \
        help='enables quiet mode')
    parser.add_argument('-c', '--color', action='store_true', \
        help='enables colored text')
    parser.add_argument('-s', '--safemode', action='store_true', \
        help='prevents any file changes')
    parser.add_argument('--config', default=_DEFAULT_CONFIG_PATH, \
        help='path to the gbp-helper.conf file')

    # The possible sub commands.
    parser.add_argument('action', nargs='?', \
        choices=['prepare-release', 'test-release', 'update-changelog', \
                'build-pkg', 'commit-pkg', 'upload', 'create-config'], \
        help="the main action to execute")

    # General args.
    parser.add_argument('dir', nargs='?', default=os.getcwd(), \
        help="path to git repository")

    args = parser.parse_args()

    flags = {'safemode': args.safemode, 'verbose': args.verbose, \
                'quiet': args.quiet, 'color': args.color}

    # Execute requested operations.
    exec_options(args, flags)
    exec_action(flags, args.action, args.config, args.dir)


############################ Start script ###############################
#########################################################################
parse_args_and_execute()

