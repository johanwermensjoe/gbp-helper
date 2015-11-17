"""
gbputil module:
Contains various io functions for git and packaging.
"""

import os
import shutil
import sys
import string
import subprocess
import re
import ConfigParser

############################# Git Tools #################################
#########################################################################
### This section defines functions useful for build operations.
### No functions will print any progress messages.
### If a failure occurs functions will terminate with GitError.
#########################################################################

class Error(Exception):
    """Base class for exceptions in this module."""
    pass

class CommandError(Error):
    """Error raised when executing a shell command.

    Attributes:
        expr    -- input command for which the error occurred
        stdout  -- command output
        stderr  -- command error output
    """

    def __init__(self, expr, stdout, stderr):
        self.expr = expr
        self.stdout = stdout
        self.stderr = stderr

class GitError(Error):
    """Error raised for git operations.

    Attributes:
        opr  -- attempted operation for which the error occurred
        msg  -- explanation of the error
    """

    def __init__(self, msg, opr=None):
        self.opr = opr
        self.msg = msg

class ConfigError(Error):
    """Error raised for config file operations.

    Attributes:
        file -- the config file
        msg  -- explanation of the error
        line -- the affected line and number (None if N/A)
    """

    def __init__(self, msg, file_=None, line=None):
        self.msg = msg
        self.file = file_
        self.line = line

############################# Git Tools #################################
#########################################################################
### This section defines functions useful for build operations.
### No functions will print any progress messages.
### If a failure occurs functions will terminate with GitError.
#########################################################################

def check_git_rep():
    """
    Checks if the current directory is a git repository.
    Errors will be raised as GitError (if not a rep).
    """
    try:
        exec_cmd(["git", "status"])
    except CommandError:
        raise GitError(os.getcwd() + " is not a git repository", "status")

def switch_branch(branch):
    """
    Switches to git branch.
    Errors will be raised as GitError (if checkout isn't possible).
    """
    # Verify that the current dir is a git repository.
    check_git_rep()
    try:
        # Try to switch branch.
        exec_cmd(["git", "checkout", branch])
    except:
        raise GitError("Please make sure that the branch \'" + \
                            branch + "\' exists and all changes " + \
                            "are commited", "checkout")

def get_head_tags(branch):
    """
    Retrives the tags for the latest commit (HEAD).
    Errors will be raised as GitError (underlying errors).
    Returns the list of HEAD tags for the given branch (can be empty).
    """
    switch_branch(branch)
    try:
        head_tags = exec_cmd(["git", "tag", "--points-at", "HEAD"]).rstrip()
        return head_tags
    except CommandError:
        raise GitError("The tags pointing at \'" + branch + \
                        "\' HEAD, could not be retrived", "tag")

def get_head_tag(branch, tag_type):
    """
    Retrives the latest HEAD tag (<tag_type>/<version>) for a branch.
    Errors will be raised as GitError (underlying errors or if no tags exists).
    """
    # Get the latest HEAD tags.
    head_tags = get_head_tags(branch)

    # Find the matching tags.
    matching_tags = re.findall(r"(?m)^" + tag_type + r"/.*$", head_tags)

    # Make sure atleast some tag follows the right format.
    if matching_tags:
        # Find the "latest tag"
        # Assuming format: <pkg_name>/<upstream_version>~<deb_version>
        matching_tags.sort(key=lambda s: [int(v) for v in \
                                s.split('/')[1].split('~')[0].split('.')])
        return matching_tags[0]
    else:
        raise GitError("The HEAD on branch \'" + branch + \
                            "\' has no tags of type: " + tag_type + "/<version>")

def get_latest_tag(branch, tag_type):
    """
    Retrives the latest tag (<tag_type>/<version>) for a branch.
    Errors will be raised as GitError (underlying errors or if no tags exists).
    """
    # Get the latest tag.
    switch_branch(branch)
    try:
        return exec_cmd(["git", "describe", "--abbrev=0", "--tags", \
                                "--match", tag_type + "/*"]).rstrip()
    except CommandError:
        raise GitError("The branch \'" + branch + \
                            "\' has no tags of type: " + tag_type + "/<version>")

def get_version_from_tag(tag, tag_type):
    """
    Extracts the version string from a tag (<tag_type>/<version>).
    Errors will be raised as GitError.
    """
    # Get the version part of the tag.
    tag_version = re.match(r"^" + tag_type + r"/(.*$)", tag)
    if tag_version:
        return tag_version.group(1)
    else:
        raise GitError("A tag version could not be extracted from tag " + \
                            "\'" + tag + "\'")

def get_head_tag_version(branch, tag_type):
    """
    Retrives the HEAD tag version (<tag_type>/<version>) for a branch.
    Errors will be raised as GitError,
    (underlying errors or if no correct tags exists).
    """
    # Get the latest HEAD tag.
    head_tag = get_head_tag(branch, tag_type)
    return get_version_from_tag(head_tag, tag_type)

def get_latest_tag_version(branch, tag_type):
    """
    Retrives latest tag version (<tag_type>/<version>) for a branch.
    Errors will be raised as GitError,
    (underlying errors or if no correct tags exists).
    """
    # Get the latest tag.
    latest_tag = get_latest_tag(branch, tag_type)
    return get_version_from_tag(latest_tag, tag_type)

def is_version_lt(ver1, ver2):
    """ Checks whether the first version string is greater than second. """
    return ver1 != ver2 and is_version_lte(ver1, ver2)

def is_version_lte(ver1, ver2):
    """
    Checks whether the first version string
    is less than or equal to the second.
    """
    versions = [ver1, ver2]
    versions.sort(key=lambda s: [int(v) for v in s.split('~')[0].split('.')])
    return versions[0] == ver1

def get_next_version(version):
    """
    Produces the next logical version from the given version string.
    Errors will be raised as GitError.
    """
    try:
        ver_part = version.split('.')
        ver_part[-1] = str(int(ver_part[-1]) + 1)
        return '.'.join(ver_part)
    except Error:
        raise GitError("Version \'" + version + "\' could not be incremented")

def is_working_dir_clean():
    """
    Check if working directory is clean.
    Returns True if clean, False otherwise.
    """
    check_git_rep()
    try:
        exec_cmd(["git", "status", "--porcelain"])
        return True
    except CommandError:
        raise GitError("Could not determine if working directory is clean.", "status")
    return False

def get_branch():
    """
    Retrives the name of the current branch.
    Errors will be raised as GitError.
    """
    check_git_rep()
    try:
        return exec_cmd(["git", "rev-parse", "--abbrev-ref", "HEAD"]).rstrip()
    except CommandError:
        raise GitError("Could not find the name of the current branch", "rev-parse")

def get_head_commit(branch):
    """
    Retrives the name of the current branch.
    Errors will be raised as GitError.
    """
    switch_branch(branch)
    try:
        return exec_cmd(["git", "rev-parse", "HEAD"]).rstrip()
    except CommandError:
        raise GitError("Could not find the name of the current branch", "rev-parse")

## Affecting repository / files.

def reset_branch(flags, branch, commit):
    """
    Resets the given branch to the given commit, (accepts HEAD as commit).
    Errors will be raised as GitError.
    """
    switch_branch(branch)
    try:
        if not flags['safemode']:
            exec_cmd(["git", "reset", "--hard", commit])
    except CommandError:
        raise GitError("Could not reset branch \'" + branch + "\' " + \
                        "to commit \'" + commit + "\'")

def commit_changes(flags, msg):
    """
    Commits all changes for the current branch.
    Errors will be raised as GitError.
    """
    check_git_rep()
    try:
        if not flags['safemode']:
            exec_cmd(["git", "add", "-A"])
            exec_cmd(["git", "commit", "-m", msg])
    except CommandError:
        raise GitError("Could not commit changes to current branch")

def stash_changes(flags, name=None):
    """
    Stashes the changes in the working directory with a optional stash name.
    """
    check_git_rep()
    try:
        if not flags['safemode']:
            if name:
                exec_cmd(["git", "stash", "save", name])
            else:
                exec_cmd(["git", "stash"])
    except CommandError:
        raise GitError("Could not stash uncommitted changes", "stash")

def apply_stash(flags, branch, name=None, drop=True):
    """
    Applies stashed changes on the given branch with a optional stash name.
    """
    switch_branch(branch)
    try:
        if not flags['safemode']:
            if name:
                exec_cmd(["git", "stash", "apply", "stash/" + name])
                if drop:
                    exec_cmd(["git", "stash", "drop", "stash/" + name])
            else:
                exec_cmd(["git", "stash", "apply"])
                if drop:
                    exec_cmd(["git", "stash", "drop"])

    except CommandError:
        raise GitError("Could not apply stashed changes" + \
                        (" (stash/" + name + ")" if name else ""), "stash")

def delete_tag(flags, tag):
    """
    Deletes the given tag.
    Errors will be raised as GitError.
    """
    check_git_rep()
    try:
        if not flags['safemode']:
            exec_cmd(["git", "tag", "-d", tag])
    except CommandError:
        raise GitError("The tag \'" + tag + "\' could not be deleted", "tag")

def tag_head(flags, branch, tag):
    """
    Tags the HEAD of the given branch.
    Errors will be raised as GitError.
    """
    switch_branch(branch)
    try:
        if not flags['safemode']:
            exec_cmd(["git", "tag", tag])
    except CommandError:
        raise GitError("The tag \'" + tag + "\' could not be created " + \
                        "and may already exist", "tag")

def clean_ignored_files(flags):
    """ Cleans files matched by a .gitignor file. """
    try:
        if not flags['safemode']:
            exec_cmd(["git", "clean", "-Xf"])
    except CommandError:
        raise GitError("Could not clean ignored files", "clean")

########################### Logging Tools ###############################
#########################################################################
### This section defines functions useful for logging.
#########################################################################

class _ColorCode(object):
    """ Color codes for text. """
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'

class _TextFormat(object):
    """ Text formats. """
    HEADER = _ColorCode.HEADER
    BLUE = _ColorCode.OKBLUE
    GREEN = _ColorCode.OKGREEN
    WARNING = _ColorCode.WARNING
    FAIL = _ColorCode.FAIL
    BOLD = _ColorCode.BOLD
    UNDERLINE = _ColorCode.UNDERLINE

class TextType(object):
    """ Text types with priority for logging. """
    INFO = ([_TextFormat.BLUE], 1)
    SUCCESS = ([_TextFormat.GREEN], 1)
    WARNING = ([_TextFormat.WARNING], 1)
    ERR = ([_TextFormat.FAIL], 2)
    ERR_EXTRA = ([], 2)
    INIT = ([_TextFormat.BOLD], 1)
    STD = ([], 0)

def _print_format(msg, formats):
    """
    Prints the "msg" to stdout using the specified text formats (TextFormat class).
    Prints just standard text if no formats are given.
    """
    if formats:
        # Print format codes., message and end code.
        print string.join(formats) + msg + _ColorCode.ENDC
    else:
        print msg

def log(flags, msg, type_=TextType.STD):
    """
    Prints log messages depending on verbose flag and priority.
    Default priority is 0 which only prints if verbose, 1 always prints.
    """
    # Always print error messages and similar.
    if (type_[1] >= 2) or flags['verbose'] \
            or (not flags['quiet'] and type_[1] == 1):
        if flags['color']:
            _print_format(msg, type_[0])
        else:
            print msg

def log_err(flags, error):
    """
    Prints a formatted string from an error of the Error class.
    """
    log(flags, "\nError:", TextType.ERR)
    if isinstance(error, GitError):
        if error.opr:
            log(flags, ("The git command \'" + error.opr + "\' failed\n" \
                        if error.opr else "") + error.msg, TextType.ERR)
        else:
            log(flags, error.msg, TextType.ERR)

    elif isinstance(error, CommandError):
        log(flags, "An error occured running: " + error.expr, TextType.ERR)
        log(flags, "\nStdOut:\n" + error.stdout, TextType.ERR_EXTRA)
        log(flags, "\nStdErr:\n" + error.stderr, TextType.ERR_EXTRA)

    elif isinstance(error, ConfigError):
        log(flags, ("An error with file: " + error.file + "\n" if error.file else "") + \
                    ("On line: " + error.line + "\n" if error.line else "") + \
                    error.msg, TextType.ERR)

def log_success(flags):
    """ Prints a success message with appropriate color. """
    log(flags, "Success\n", TextType.SUCCESS)

########################### Config Tools ################################
#########################################################################
### This section defines functions for parsing and writing config files.
#########################################################################

def create_ex_config(flags, config_path, template):
    """
    Creates an example gbp-helper.conf file.
    Errors will be raised as ConfigError.
    """
    # Make sure file does not exist.
    if os.path.exists(config_path):
        raise ConfigError("File exists and will not" + \
                            " be replaced by an example file", config_path)
    else:
        try:
            config = ConfigParser.RawConfigParser()

            for section in template:
                config.add_section(section[0])
                for entry in section[1]:
                    config.set(section[0], entry[0], entry[1])

            # Writing configuration file to "configPath".
            if not flags['safemode']:
                with open(config_path, 'wb') as config_file:
                    config.write(config_file)

        except IOError as err:
            raise ConfigError("I/O error({0}): {1}".\
                                format(err.errno, err.strerror), config_path)

def get_config(config_path, template):
    """
    Update the config variables.
    Errors will be raised as ConfigError.
    """
    # Check if config file exists.
    if not os.path.exists(config_path):
        raise ConfigError("The config file could not be found", config_path)

    # Parse config file.
    config = ConfigParser.RawConfigParser(allow_no_value=True)
    config.read(config_path)

    # Make sure the required values are set.
    conf = {}
    for section in template:
        for entry in section[1]:
            # Set conf value even if it's empty.
            val = config.get(section[0], entry[0])
            # Check if required but non existant.
            if not val:
                # Use default value instead (can be None).
                val = entry[1]
                # Check if required in config.
                if entry[2]:
                    raise ConfigError("The value in for " + entry[0] + \
                                        " in section [" + section[0] + \
                                        "] is missing but required", \
                                        config_path)
            conf[entry[0]] = val

    # Handle special fields.
    if not conf['packageName']:
        conf['packageName'] = os.path.basename(os.getcwd())

    return conf

########################### IO/UI Tools #################################
#########################################################################
### This section defines functions useful for file and ui operations.
### Some functions will print progress messages.
### If a failure occurs functions print an error message and terminate.
#########################################################################

def exec_cmd(cmd):
    """
    Executes a shell command given as a list of the command followed by the arguments.
    Errors will be raised as CommandError.
    Returns the command output.
    """
    pipe = subprocess.PIPE
    cmd_delimiter = " "

    try:
        process = subprocess.Popen(cmd, stdout=pipe, stderr=pipe)
        stdoutput, stderroutput = process.communicate()
    except Exception as err:
        raise CommandError(cmd_delimiter.join(cmd), err.msg)

    if ('fatal' in stdoutput) or ('fatal' in stderroutput) or \
            process.returncode >= 1:
        # Handle error case
        raise CommandError(cmd_delimiter.join(cmd), stdoutput, stderroutput)
    else:
        # Success!
        return stdoutput

def clean_dir(flags, dir_path):
    """
    Cleans or if not existant creates a directory.
    Prints progress messages.
    """
    remove_dir(flags, dir_path)
    if not flags['safemode']:
        os.makedirs(dir_path)

def get_file_with_extension(dir_path, extension):
    """ Retrives the first file matching the given extension or None. """
    for file_ in os.listdir(dir_path):
        if file_.endswith(extension):
            return file_
    return None

def remove_dir(flags, dir_path):
    """ Removes a directory. """
    if os.path.isdir(dir_path):
        if not flags['safemode']:
            # Remove directory recursively.
            shutil.rmtree(dir_path)

def prompt_user_yn(question, default="yes"):
    """
    Asks a yes/no question via raw_input() and return their answer.
    "question" the string presented, "default" is the presumed answer
    if the user just hits <Enter>. It must be "yes" (the default),
    "no" or None (meaning an answer is required of the user).
    Returns True if user answers "yes", else False.
    """
    valid = {"yes": True, "y": True, "ye": True,
             "no": False, "n": False}
    if default is None:
        prompt = " [y/n] "
    elif default == "yes":
        prompt = " [Y/n] "
    elif default == "no":
        prompt = " [y/N] "
    else:
        raise ValueError("invalid default answer: '%s'" % default)

    while True:
        sys.stdout.write(question + prompt)
        choice = raw_input().lower()
        if default is not None and choice == '':
            return valid[default]
        elif choice in valid:
            return valid[choice]
        else:
            sys.stdout.write("Please respond with 'yes' or 'no' "
                             "(or 'y' or 'n').\n")
