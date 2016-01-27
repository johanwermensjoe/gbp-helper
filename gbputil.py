"""
gbputil module:
Contains various io functions for git and packaging.
"""

import os
import shutil
import sys
import subprocess
import re
import ConfigParser
import time
import datetime

############################### Errors ##################################
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
        Error.__init__(self)
        self.expr = expr
        self.stdout = stdout
        self.stderr = stderr

class GitError(Error):
    """Error raised for git operations.

    Attributes:
        opr     -- attempted operation for which the error occurred
        msg     -- explanation of the error
    """

    def __init__(self, msg, opr=None):
        Error.__init__(self)
        self.opr = opr
        self.msg = msg

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

def get_head_tags(branch, tag_type):
    """
    Retrives the tags for the HEAD commit on form (<tag_type>/<version>).
    Errors will be raised as GitError (underlying errors).
    Returns the list of HEAD tags for the given branch (can be empty).
    """
    switch_branch(branch)
    try:
        # Get all tags at HEAD.
        head_tags = exec_cmd(["git", "tag", "--points-at", "HEAD"])
        # Find the matching tags.
        matching_tags = re.findall(r"(?m)^" + tag_type + r"/.*$", head_tags)
        return matching_tags
    except CommandError:
        raise GitError("The tags pointing at \'" + branch + \
                        "\' HEAD, could not be retrived", "tag")

def get_head_tag(branch, tag_type):
    """
    Retrives the latest HEAD tag (<tag_type>/<version>) for a branch.
    Errors will be raised as GitError (underlying errors).
    Returns the name of the latest tag (largest version number).
    """
    # Get the latest HEAD tags.
    head_tags = get_head_tags(branch, tag_type)

    # Make sure atleast some tag follows the right format.
    if head_tags:
        # Find the "latest tag"
        # Assuming std format: <tag_type>/<version>(-<deb_version>)
        head_tags.sort(key=lambda s: [int(v) for v in \
                                s.split('/')[1].split('-')[0].split('.')])
        return head_tags[0]
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
                                "--match", tag_type + "/*"])
    except CommandError:
        raise GitError("The branch \'" + branch + \
                            "\' has no tags of type: " + \
                            tag_type + "/<version>")

def get_version_from_tag(tag, tag_type):
    """
    Extracts the version string from a tag (<tag_type>/<version>).
    Errors will be raised as GitError.
    """
    # Get the version part of the tag.
    tag_ver = re.match(r"^" + tag_type + r"/(.*$)", tag)
    if tag_ver:
        return tag_ver.group(1)
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
    return compare_versions(ver1, ver2) < 0

def compare_versions(ver1, ver2):
    """ Compares two versions. """
    ver_s = [ver1, ver2]
    ver_s.sort(key=lambda s: re.findall(r'''\d+''', s))
    if ver1 == ver2:
        return 0
    elif ver_s[0] == ver1:
        return -1
    else:
        return 1

def get_next_version(version):
    """
    Produces the next logical version from the given version string.
    Errors will be raised as GitError.
    """
    try:
        # Split if the version has a 1.0-0ppa1 form.
        base_part = version.split('~', 1)
        ver_part = base_part[0].split('.')
        ver_part[-1] = str(int(ver_part[-1]) + 1)
        return '.'.join(ver_part) + \
                (("-" + base_part[1]) if len(base_part) > 1 else "")
    except Error:
        raise GitError("Version \'" + version + "\' could not be incremented")

def is_working_dir_clean():
    """
    Check if working directory is clean.
    Returns True if clean, False otherwise.
    """
    check_git_rep()
    try:
        return exec_cmd(["git", "status", "--porcelain"]) == ''
    except CommandError:
        raise GitError("Could not determine if working directory is clean.", \
                        "status")

def get_branch():
    """
    Retrives the name of the current branch.
    Errors will be raised as GitError.
    """
    check_git_rep()
    try:
        return exec_cmd(["git", "rev-parse", "--abbrev-ref", "HEAD"])
    except CommandError:
        raise GitError("Could not find the name of the current branch", \
                        "rev-parse")

def get_head_commit(branch):
    """
    Retrives the name HEAD commit on the given branch.
    Errors will be raised as GitError.
    """
    switch_branch(branch)
    try:
        return exec_cmd(["git", "rev-parse", "HEAD"])
    except CommandError:
        raise GitError("Could not find HEAD commit of branch \'" + \
                            branch + "\'", "rev-parse")

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
                exec_cmd(["git", "stash", "save", "--include-untracked", name])
            else:
                exec_cmd(["git", "stash", "save", "--include-untracked"])
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
                exec_cmd(["git", "stash", "apply", "stash^{/\"" + \
                            name + "\"}"])
                if drop:
                    exec_cmd(["git", "stash", "drop", "stash^{/\"" + \
                            name + "\"}"])
            else:
                exec_cmd(["git", "stash", "apply"])
                if drop:
                    exec_cmd(["git", "stash", "drop"])

    except CommandError:
        raise GitError("Could not apply stashed changes" + \
                        (" (" + name + ")" if name else ""), "stash")

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
    """ Cleans files matched by a .gitignore file. """
    try:
        if not flags['safemode']:
            exec_cmd(["git", "clean", "-Xf"])
    except CommandError:
        raise GitError("Could not clean ignored files", "clean")

def get_rep_name_from_url(url):
    """ Exracts a gitrepositori name from a remote URL. """
    match = re.match(r'''(?i)^.*/(.*)\.git$''', url)
    if match:
        return match.group(1)
    else:
        return None
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

def _print_format(msg, format_):
    """
    Prints the "msg" to stdout using the specified text format
    (TextFormat class). Prints just standard text if no formats are given.
    """
    if format_:
        # Print format codes., message and end code.
        print str.join("", format_) + msg + _ColorCode.ENDC
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
    - error -- The instance of Error to print.
    """
    log(flags, "\nError:", TextType.ERR)
    if isinstance(error, OpError):
        if error.msg:
            # Print msg if set.
            log(flags, error.msg, TextType.ERR)
        if error.err:
            # Print causing error if set.
            error = error.err
        else:
            return

    # Print standard errors.
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
        log(flags, ("An error with file: " + error.file + \
                    "\n" if error.file else "") + ("On line: " + error.line + \
                    "\n" if error.line else "") + error.msg, TextType.ERR)
    else:
        log(flags, "Unknown type", TextType.ERR)

def log_success(flags):
    """ Prints a success message with appropriate color. """
    log(flags, "Success\n", TextType.SUCCESS)

########################### Config Tools ################################
#########################################################################
### This section defines functions for parsing and writing config files.
#########################################################################

def create_ex_config(flags, config_path, template, preset_keys=None):
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
                    # Try to find value in preset keys first.
                    if preset_keys and entry[0] in preset_keys:
                        val = preset_keys[entry[0]]
                    else:
                        val = entry[1]
                    config.set(section[0], entry[0], val)

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

def get_config_default(key, template):
    """
    Returns the default configuration value for the given key.
    - key       -- the key
    - template  -- the config template
    """
    for section in template:
        for entry in section[1]:
            if key == entry[0]:
                return entry[1]
    return None

########################### IO/UI Tools #################################
#########################################################################
### This section defines functions useful for file and ui operations.
### Some functions will print progress messages.
### If a failure occurs functions print an error message and terminate.
#########################################################################

CMD_DEL = " "
PIPE = subprocess.PIPE

def exec_cmd(cmd):
    """
    Executes a shell command.
    Errors will be raised as CommandError.
    Returns the command output.
    - cmd   -- list of the executable followed by the arguments.
    """
    try:
        proc = subprocess.Popen(cmd, stdout=PIPE, stderr=PIPE)
        stdoutput, stderroutput = proc.communicate()
    except Exception as err:
        raise CommandError(CMD_DEL.join(cmd), err.msg)

    if ('fatal' in stdoutput) or ('fatal' in stderroutput) or \
            proc.returncode >= 1:
        # Handle error case
        raise CommandError(CMD_DEL.join(cmd), stdoutput, stderroutput)
    else:
        # Success!
        return stdoutput.strip()

def exec_piped_cmds(cmd1, cmd2):
    """
    Executes a two piped shell commands.
    Errors will be raised as CommandError.
    Returns the command output.
    - cmd1, cmd2    -- list of the executable followed by the arguments.
    """
    try:
        proc1 = subprocess.Popen(cmd1, stdout=PIPE)
        proc2 = subprocess.Popen(cmd2, stdin=proc1.stdout, \
                                    stdout=PIPE, stderr=PIPE)
        # Allow p1 to receive a SIGPIPE if p2 exits.
        proc1.stdout.close()
        stdoutput, stderroutput = proc2.communicate()
    except Exception as err:
        raise CommandError(CMD_DEL.join(cmd1) + " | " + CMD_DEL.join(cmd2), \
                            err.msg)

    if ('fatal' in stdoutput) or ('fatal' in stderroutput) or \
            proc2.returncode >= 1:
        # Handle error case
        raise CommandError(CMD_DEL.join(cmd1) + " | " + CMD_DEL.join(cmd2), \
                            stdoutput, stderroutput)
    else:
        # Success!
        return stdoutput.strip()

def exec_editor(editor_cmd, _file):
    """
    Opens a shell text editor.
    - _file   -- File to be opened.
    """
    try:
        subprocess.check_call([editor_cmd, _file])
    except Exception as err:
        raise CommandError(editor_cmd + " " + _file, err.msg)

def clean_dir(flags, dir_path):
    """ Cleans or if not existant creates a directory.
    - dir_path  -- The path of the directory to clean.
    """
    # Remove all files and directories in the given directory.
    if os.path.isdir(dir_path):
        # Remove all files and directories in the given directory.
        for file_ in os.listdir(dir_path):
            if os.path.isdir(file_):
                remove_dir(flags, os.path.join(dir_path, file_))
            else:
                remove_file(flags, os.path.join(dir_path, file_))
    else:
        # Just create the given directory.
        mkdirs(flags, dir_path)

def mkdirs(flags, dir_path):
    """ Creates a directory and required parent directories.
    - dir_path  -- The path of the directory to create.
    """
    # Create directories if neccesary.
    if not os.path.isdir(dir_path):
        if not flags['safemode']:
            os.makedirs(dir_path)

def get_files_with_extension(dir_path, extension):
    """ Retrives the files matching the given file suffix.
    - dir_path  -- The path of the directory search reqursivley.
    - extension -- The file suffix to look for.
    Returns the list of files with full paths based on dir_path.
    """
    ext_files = []
    for path, _, files in os.walk(dir_path):
        for file_ in files:
            if file_.endswith(extension):
                ext_files += [os.path.join(path, file_)]
    return ext_files

def remove_dir(flags, dir_path):
    """ Removes a directory.
    - dir_path  -- The path of the directory to remove.
    """
    if os.path.isdir(dir_path):
        if not flags['safemode']:
            # Remove directory recursively.
            shutil.rmtree(dir_path)

def remove_file(flags, file_path):
    """
    Removes a file.
    - file_path -- The path of the file to remove.
    """
    if os.path.isfile(file_path):
        if not flags['safemode']:
            # Remove the file.
            os.remove(file_path)

def move_file_dir(flags, old_path, new_path):
    """ Moves a file or a dirctory. """
    if old_path != new_path:
        # Calculate the parent directory paths.
        old_dir = os.path.dirname(old_path)
        new_dir = os.path.dirname(new_path)

        # Check if the file/dir is being moved or just renamed.
        if old_dir != new_dir:
            if not flags['safemode']:
                # Make sure parent directory exists.
                if not os.path.isdir(new_dir):
                    os.makedirs(new_dir)
        else:
            # Rename
            if not flags['safemode']:
                # If only case differs, do temp move (Samba compability).
                if old_path.lower() == new_path.lower():
                    os.rename(old_path, old_path + "_temp")
                    old_path += "_temp"
                # Do the move/rename.
                os.rename(old_path, new_path)

def prompt_user_input(prompt, allow_empty=False, default=None):
    """
    Promts the user for input and returns it.
    A space is added after the prompt automatically.
    - allow_empty -- Set to 'True' to allow empty string as input
    - default     -- Set to the default answer if left empty
    """
    prompt_add = ": "
    if allow_empty:
        if not default:
            prompt_add = ": (empty to skip): "
        else:
            prompt_add = ": [" + default + "] "
    while True:
        sys.stdout.write(prompt + prompt_add)
        input_ = raw_input().lower()
        if input_ != '':
            return input_
        elif allow_empty:
            return default
        else:
            sys.stdout.write("Please respond with a non-empty string.\n")

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

def prompt_user_options(question, options, default=0):
    """
    Asks an options based question via raw_input() and returns the choice.
    Returns index of the chosen option or None if aborted by user.
    """
    if default < len(options) and default >= 0:
        prompt = " [0-" + str(len(options) - 1) + \
                    " (" + str(default) + ")] or 'a' to abort: "
    else:
        raise ValueError("invalid default answer: '%s'" % default)

    while True:
        sys.stdout.write("\nOptions:")
        for (i, option) in enumerate(options):
            sys.stdout.write("\n(" + str(i) + ") " + option)
        sys.stdout.write("\n" + question + prompt)
        choice = raw_input().lower()
        if choice == '':
            return default
        elif choice == 'a':
            return None
        elif choice.isdigit() and int(choice) >= 0 and \
                int(choice) < len(options):
            return int(choice)
        else:
            sys.stdout.write("Please respond with a integer in the range " + \
                                "[0-" + (len(options) - 1) + "]\n")

####################### Comnbined Operations ############################
#########################################################################
### This section defines functions combining IO/UI with Git operations.
### Some functions will print progress messages.
### If a failure occurs functions will try to reset any persistant operations
### alreday executed before the error.
### After the reset is attempted, functions terminates with an OpError.
#########################################################################

_BAK_FILE_EXT = ".bak.tar.gz"
_BAK_FILE_DATE_FORMAT = "%Y-%m-%d-%H-%M-%S"
_BAK_DISP_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

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
        # Check that atleast one head tag exists.
        if get_head_tags(branch, tag_type):
            log(flags, "The HEAD commit on barnch \'" + branch + \
                "\' is already tagged, skipping tagging")
            version = get_head_tag_version(branch, tag_type)
            return (version, tag_type + "/" + version, False)
        else:
            log(flags, "The HEAD commit on branch \'" + branch + \
                            "\' is not tagged correctly")
            if not version:
                # Prompt user to tag the HEAD of release branch.
                raw_ver = prompt_user_input("Enter release version to tag", \
                                            False)
                if raw_ver:
                    version = raw_ver
                else:
                    raise OpError(msg="Tagging of HEAD commit on branch " + \
                                        "\'" + branch + "\' aborted by user")

            # Tag using the given version.
            if not flags['safemode']:
                tag = tag_type + "/" + version
                log(flags, "Tagging HEAD commit on branch \'" + branch + \
                            "\' as \'" + tag + "\'")
                tag_head(flags, branch, tag)
            return (version, tag, True)
    except Error as err:
        raise OpError(err)

def create_temp_commit(flags):
    """
    Commits any uncommitted changes on the current
    branch to a temporary commit.
    - branch    -- The branch to tag.
    Returns the a tuple with the branch name, commit id and
    stash name, used to restore the inital state with the
    'restore_temp_commit' function.
    If no changes can be commited the stash name is set to 'None'.
    """
    try:
        # Save the current branch
        current_branch = get_branch()
        log(flags, "Saving current branch name \'" + current_branch + "\' ")

         # Try to get the HEAD commmit id of the current branch.
        head_commit = get_head_commit(current_branch)

        # Check for uncommitted changes.
        if not is_working_dir_clean():
            log(flags, "Stashing uncommited changes on branch \'" + \
                        current_branch + "\'")
            # Save changes to tmp stash.
            stash_name = "gbp-helper<" + head_commit + ">"
            stash_changes(flags, stash_name)

            # Apply stash and create a temporary commit.
            log(flags, "Creating temporary commit on branch \'" + \
                        current_branch + "\'")
            apply_stash(flags, current_branch, stash_name, False)
            commit_changes(flags, "Temp \'" + current_branch + "\' commit.")
        else:
            stash_name = None
            log(flags, "Working directory clean, no commit needed")

        return (current_branch, head_commit, stash_name)
    except Error as err:
        raise OpError(err)

def restore_temp_commit(flags, restore_data):
    """
    Restores the inital state before a temp commit was created.
    - restore_data  -- The restore data returned from the
                        'create_temp_commit' function.
    """
    try:
        # Restore branch.
        if restore_data[0] != get_branch():
            log(flags, "Switching active branch to \'" + restore_data[0] + \
                        "\'")
            switch_branch(restore_data[0])

        # Check if changes have been stashed (and temporary commit created).
        if restore_data[2]:
            log(flags, "Resetting branch \'" + \
                    restore_data[0] + "\'to commit \'" + \
                    restore_data[1] + "\'")
            reset_branch(flags, restore_data[0], restore_data[1])

            log(flags, "Restoring uncommitted changes from stash to " + \
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
        tar_name = name + "_" + time.strftime(_BAK_FILE_DATE_FORMAT) + \
                        _BAK_FILE_EXT
        tar_path = os.path.join(bak_dir, tar_name)

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
        if name:
            bak_name = name

        else:
            # Find all previously backed up states.
            bak_files = get_files_with_extension(bak_dir, _BAK_FILE_EXT)
            if not bak_files:
                raise OpError("No backups exists in directory \'" + \
                                bak_dir + "\'")

            # Sort the bak_files according to date.
            bak_files.sort(key=lambda s: [int(v) for v in \
                                s.split('_')[1].split('.')[0].split('-')], \
                                reverse=True)

            # Set the max tab depth.
            max_tab_depth = max([1 + (len(s.split('_')[0]) / _TAB_WIDTH) \
                                                        for s in bak_files])

            # Prompt user to select a state to restore.
            options = []
            for fname in bak_files:
                option = "\t" + fname.split('_')[0]
                option += "\t" * (max_tab_depth - len(option) / _TAB_WIDTH)
                option += datetime.datetime.strptime( \
                            fname.split('_')[1].split('.')[0], \
                            _BAK_FILE_DATE_FORMAT).strftime( \
                                _BAK_DISP_DATE_FORMAT)
                options += [option]

            # Check if prompt can be skipped.
            if not num is None:
                if num >= len(options) or num < 0:
                    raise OpError("Invalid backup index \'" + \
                                num + "\' is outside [0-" + \
                                str(len(options) - 1) + "]")
            else:
                # Prompt.
                num = prompt_user_options("Select the backup to restore", \
                                            options)
                if num is None:
                    raise OpError(msg="Restore aborted by user")

            # Set the chosen backup name.
            bak_name = bak_files[num]

        # Restore backup.
        try:
            log(flags, "Restoring backup \'" + bak_name + "\'")
            clean_dir(flags, os.getcwd())
            if not flags['safemode']:
                exec_cmd(["tar", "-xf", os.path.join(bak_dir, bak_name)])
        except Error as err:
            log(flags, "Restore failed, the backup can be found in \'" + \
                    bak_dir + "\'", TextType.ERR)
            raise OpError(err)
    except GitError as err:
        log(flags, "Restore could not be completed")
        raise OpError(err)
