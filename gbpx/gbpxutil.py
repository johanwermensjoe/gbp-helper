"""
gbpxutil module:
Contains various io functions for git and packaging.
"""
from configparser import ConfigParser
from datetime import datetime
from os import path, getcwd
from time import strftime

from gitutil import get_head_tags, get_head_tag_version, tag_head, \
    get_branch, get_head_commit, is_working_dir_clean, stash_changes, \
    apply_stash, commit_changes, switch_branch, reset_branch, check_git_rep, \
    GitError

from ioutil import Error, log, TextType, prompt_user_input, mkdirs, \
    exec_cmd, get_files_with_extension, prompt_user_options, clean_dir


############################### Errors ##################################
#########################################################################


class ConfigError(Error):
    """Error raised for config file operations.

    Attributes:
        file_   -- the config file
        msg     -- explanation of the error
        line    -- the affected line and number (None if N/A)
    """

    def __init__(self, msg, file_=None, line=None):
        Error.__init__(self)
        self.msg = msg
        self.file = file_
        self.line = line

    def log(self, flags):
        """ Log the error """
        log(flags, ("An error with file: " + self.file +
                    "\n" if self.file is not None else "") + (
                "On line: " + self.line +
                "\n" if self.line is not None else "") + self.msg, TextType.ERR)


class OpError(Error):
    """Error raised for combined operations.

    Attributes:
        err     -- the causing error
        msg     -- explanation of the error
    """

    def __init__(self, err=None, msg=None):
        Error.__init__(self)
        self.err = err
        self.msg = msg

    def log(self, flags):
        """ Log the error """
        if self.msg is not None:
            # Print msg if set.
            log(flags, self.msg, TextType.ERR)

        if self.err is not None:
            # Print causing error if set.
            self.err.log(flags)


########################### Config Tools ################################
#########################################################################
### This section defines functions for parsing and writing config files.
#########################################################################

DEFAULT_CONFIG_PATH = "gbpx.conf"
_DEL_EXCLUDE = ","


class Setting(object):
    """ Setting identifier class.
    """
    RELEASE_BRANCH = 'releaseBranch'
    RELEASE_TAG_TYPE = 'releaseTagType'
    UPSTREAM_BRANCH = 'upstreamBranch'
    UPSTREAM_TAG_TYPE = 'upstreamTagType'
    DEBIAN_BRANCH = 'debianBranch'
    DEBIAN_TAG_TYPE = 'debianTagType'

    GPG_KEY_ID = 'gpgKeyId'

    BUILD_FLAGS = 'buildFlags'
    TEST_BUILD_FLAGS = 'testBuildFlags'

    PACKAGE_NAME = 'packageName'
    DISTRIBUTION = 'distribution'
    URGENCY = 'urgency'
    DEBIAN_VERSION_SUFFIX = 'debianVersionSuffix'
    EXCLUDE_FILES = 'excludeFiles'

    PPA_NAME = 'ppa'


class _BaseSetting(object):
    def __init__(self, default, section, required, convert):
        self.default = default
        self.section = section
        self.required = required
        self.convert = convert


class _Section(object):
    GIT = "GIT"
    SIGNING = "SIGNING"
    BUILD = "BUILD"
    PACKAGE = "PACKAGE"
    UPLOAD = "UPLOAD"


# Settings with default value, section and visibility.
_CONFIG = {
    # Persistent settings.
    Setting.RELEASE_BRANCH: _BaseSetting("master", _Section.GIT, True, str),
    Setting.RELEASE_TAG_TYPE: _BaseSetting("release", _Section.GIT, True, str),
    Setting.UPSTREAM_BRANCH: _BaseSetting("upstream", _Section.GIT, True, str),
    Setting.UPSTREAM_TAG_TYPE: _BaseSetting("upstream", _Section.GIT, True,
                                            str),
    Setting.DEBIAN_BRANCH: _BaseSetting("debian", _Section.GIT, True, str),
    Setting.DEBIAN_TAG_TYPE: _BaseSetting("debian", _Section.GIT, True, str),

    Setting.GPG_KEY_ID: _BaseSetting(None, _Section.SIGNING, False, str),

    Setting.BUILD_FLAGS: _BaseSetting(None, _Section.BUILD, False, str),
    Setting.TEST_BUILD_FLAGS: _BaseSetting(None, _Section.BUILD, False, str),

    Setting.PACKAGE_NAME: _BaseSetting(None, _Section.PACKAGE, False, str),
    Setting.DISTRIBUTION: _BaseSetting(None, _Section.PACKAGE, False, str),
    Setting.URGENCY: _BaseSetting("low", _Section.PACKAGE, False, str),
    Setting.DEBIAN_VERSION_SUFFIX: _BaseSetting("-0~ppa1", _Section.PACKAGE,
                                                False, str),
    Setting.EXCLUDE_FILES: _BaseSetting(
        DEFAULT_CONFIG_PATH + ",README.md,LICENCE", _Section.PACKAGE, False,
        lambda s: [se.strip() for se in str(s).split(_DEL_EXCLUDE)]),

    Setting.PPA_NAME: _BaseSetting(None, _Section.UPLOAD, False, str),
}


def create_ex_config(flags, config_path, preset_keys=None):
    """
    Creates an example gbpx.conf file.
    Errors will be raised as ConfigError.
    """
    # Make sure file does not exist.
    if path.exists(config_path):
        raise ConfigError("File exists and will not" +
                          " be replaced by an example file", config_path)
    else:
        try:
            config = ConfigParser()

            for key, setting in _CONFIG.items():
                if not config.has_section(setting.section):
                    config[setting.section] = {}

                # Try to find value in preset keys first.
                if preset_keys is not None and key in preset_keys:
                    val = preset_keys[key]
                else:
                    val = setting.default
                config[setting.section][key] = str(
                    val) if val is not None else ""

            # Writing configuration file to "configPath".
            if not flags['safemode']:
                with open(config_path, 'w') as config_file:
                    config.write(config_file)

        except IOError as err:
            raise ConfigError("I/O error({0}): {1}".
                              format(err.errno, err.strerror), config_path)


def get_config(config_path):
    """
    Update the config variables.
    Errors will be raised as ConfigError.
    """
    # Check if config file exists.
    if not path.exists(config_path):
        raise ConfigError("The config file could not be found", config_path)

    # Parse config file.
    config = ConfigParser(allow_no_value=True)
    config.read(config_path)

    # Make sure the required values are set.
    conf = {}
    for key, setting in _CONFIG.items():
        # Set conf value even if it's empty.
        try:
            val = setting.convert(config[setting.section][key])
        except KeyError:
            val = None
        # Check if required but non existent.
        if val is None or val == "":
            # Use default value instead (can be None).
            val = setting.default
            # Check if required in config.
            if setting.required:
                raise ConfigError("The value in for " + key +
                                  " in section [" + setting.section +
                                  "] is missing but required",
                                  config_path)
        conf[key] = val

    # Handle special fields.
    if conf[Setting.PACKAGE_NAME] is None:
        conf[Setting.PACKAGE_NAME] = path.basename(getcwd())

    return conf


def get_config_default(key):
    """
    Returns the default configuration value for the given key.
    - key       -- the key
    """
    return _CONFIG[key].default


####################### Combined Operations ############################
#########################################################################
### This section defines functions combining IO/UI with Git operations.
### Some functions will print progress messages.
### If a failure occurs functions will try to reset any persistent operations
### already executed before the error.
### After the reset is attempted, functions terminates with an OpError.
#########################################################################

_BAK_FILE_EXT = ".bak.tar.gz"
_BAK_FILE_DATE_FORMAT = "%Y-%m-%d-%H-%M-%S"
_BAK_DISPLAY_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

_TAB_WIDTH = 8


def verify_create_head_tag(flags, branch, tag_type, version=None):
    """
    Verifies or creates a version tag for a branch HEAD.
    If tag needs to be created and no version is given,
    user will be prompted for version.
    - branch    -- The branch to tag.
    - tag_type  -- The tag type (<tag_type>/<version>).
    - version   -- The version to use.
    Returns the a tuple with version created or found
    and True if created otherwise False. (<version>, <created>)
    """
    try:
        # Check that at least one head tag exists.
        if get_head_tags(branch, tag_type):
            log(flags, "The HEAD commit on branch \'" + branch +
                "\' is already tagged, skipping tagging")
            version = get_head_tag_version(branch, tag_type)
            return version, tag_type + "/" + version, False
        else:
            log(flags, "The HEAD commit on branch \'" + branch +
                "\' is not tagged correctly")
            if version is None:
                # Prompt user to tag the HEAD of release branch.
                raw_ver = prompt_user_input("Enter release version to tag",
                                            True)
                if raw_ver is not None:
                    version = raw_ver
                else:
                    raise OpError(msg="Tagging of HEAD commit on branch " +
                                      "\'" + branch + "\' aborted by user")

            # Tag using the given version.
            tag = tag_type + "/" + version
            if not flags['safemode']:
                log(flags, "Tagging HEAD commit on branch \'" + branch +
                    "\' as \'" + tag + "\'")
                tag_head(flags, branch, tag)
            return version, tag, True
    except Error as err:
        raise OpError(err)


def create_temp_commit(flags):
    """
    Commits any uncommitted changes on the current
    branch to a temporary commit.
    - branch    -- The branch to tag.
    Returns the a tuple with the branch name, commit id and
    stash name, used to restore the initial state with the
    'restore_temp_commit' function.
    If no changes can be committed the stash name is set to 'None'.
    """
    try:
        # Save the current branch
        current_branch = get_branch()
        log(flags, "Saving current branch name \'{0}\' ".format(current_branch))

        # Try to get the HEAD commit id of the current branch.
        head_commit = get_head_commit(current_branch)

        # Check for uncommitted changes.
        if not is_working_dir_clean():
            log(flags, "Stashing uncommitted changes on branch \'{0}\'".
                format(current_branch))
            # Save changes to tmp stash.
            stash_name = "gbpx<{0}>".format(head_commit)
            stash_changes(flags, stash_name)

            # Apply stash and create a temporary commit.
            log(flags, "Creating temporary commit on branch \'{0}\'".
                format(current_branch))
            apply_stash(flags, current_branch, stash_name, False)
            commit_changes(flags, "Temp \'{0}\' commit.".format(current_branch))
        else:
            stash_name = None
            log(flags, "Working directory clean, no commit needed")

        return current_branch, head_commit, stash_name
    except Error as err:
        raise OpError(err)


def restore_temp_commit(flags, restore_data):
    """
    Restores the initial state before a temp commit was created.
    - restore_data  -- The restore data returned from the
                        'create_temp_commit' function.
    """
    try:
        # Restore branch.
        if restore_data[0] != get_branch():
            log(flags, "Switching active branch to \'" + restore_data[0] +
                "\'")
            switch_branch(restore_data[0])

        # Check if changes have been stashed (and temporary commit created).
        if restore_data[2] is not None:
            log(flags, "Resetting branch \'" +
                restore_data[0] + "\'to commit \'" +
                restore_data[1] + "\'")
            reset_branch(flags, restore_data[0], restore_data[1])

            log(flags, "Restoring uncommitted changes from stash to " +
                "branch \'" + restore_data[0] + "\'")
            apply_stash(flags, restore_data[0], restore_data[2], True)
    except Error as err:
        raise OpError(err)


def add_backup(flags, bak_dir, name="unknown"):
    """
    Adds a backup of the git repository.
    - bak_dir   -- The destination directory.
    - name      -- The name of the backup, replaces '_' with '-'.
    Returns the name of the created backup file.
    """
    try:
        check_git_rep()

        # Make sure there are no '_' in the name.
        name.replace('_', '-')

        # Set the path to the new backup file.
        tar_name = "{0}_{1}{2}".format(name,
                                       strftime(_BAK_FILE_DATE_FORMAT),
                                       _BAK_FILE_EXT)
        tar_path = path.join(bak_dir, tar_name)

        # Make a safety backup of the current git repository.
        log(flags, "Creating backup file \'" + tar_path + "\'")
        if not flags['safemode']:
            mkdirs(flags, bak_dir)
            exec_cmd(["tar", "-czf", tar_path, "."])

        return tar_name
    except Error as err:
        log(flags, "Could not add backup in \'" + bak_dir + "\'")
        raise OpError(err)


def restore_backup(flags, bak_dir, num=None, name=None):
    """
    Tries to restore repository to a saved backup.
    Will prompt the user for the requested restore point if
    num is not set.
    - bak_dir   -- The backup storage directory.
    - num       -- The index number of the restore point (latest first).
    """
    try:
        check_git_rep()

        # If name is set just restore that file.
        if name is not None:
            bak_name = name

        else:
            # Find all previously backed up states.
            bak_files = get_files_with_extension(bak_dir, _BAK_FILE_EXT)
            if not bak_files:
                raise OpError("No backups exists in directory \'" +
                              bak_dir + "\'")

            # Sort the bak_files according to date.
            bak_files.sort(key=lambda bak_f: [int(v) for v in
                                              bak_f.split('_')[1].split('.')[
                                                  0].split('-')],
                           reverse=True)

            # Set the max tab depth.
            max_tab_depth = max([1 + (len(s.split('_')[0]) // _TAB_WIDTH)
                                 for s in bak_files])

            # Prompt user to select a state to restore.
            options = []
            for f_name in bak_files:
                option = "\t" + f_name.split('_')[0]
                option += "\t" * (max_tab_depth - len(option) // _TAB_WIDTH)
                option += datetime.strptime(
                    f_name.split('_')[1].split('.')[0],
                    _BAK_FILE_DATE_FORMAT).strftime(_BAK_DISPLAY_DATE_FORMAT)
                options += [option]

            # Check if prompt can be skipped.
            if num is not None:
                if num >= len(options) or num < 0:
                    raise OpError("Invalid backup index \'" +
                                  num + "\' is outside [0-" +
                                  str(len(options) - 1) + "]")
            else:
                # Prompt.
                num = prompt_user_options("Select the backup to restore",
                                          options)
                if num is None:
                    raise OpError(msg="Restore aborted by user")

            # Set the chosen backup name.
            bak_name = bak_files[num]

        # Restore backup.
        try:
            log(flags, "Restoring backup \'" + bak_name + "\'")
            clean_dir(flags, getcwd())
            if not flags['safemode']:
                exec_cmd(["tar", "-xf", path.join(bak_dir, bak_name)])
        except Error as err:
            log(flags, "Restore failed, the backup can be found in \'" +
                bak_dir + "\'", TextType.ERR)
            raise OpError(err)
    except GitError as err:
        log(flags, "Restore could not be completed")
        raise OpError(err)
