"""
ioutil module:
Contains various io functions for git and packaging.
"""
from os import path, rename, remove, listdir, makedirs, walk
from shutil import rmtree
from subprocess import check_call, Popen, PIPE
from sys import stdout


############################### Errors ##################################
#########################################################################

class Error(Exception):
    """Base class for exceptions in this module."""

    def log(self, flags):
        """ To be implemented by subclass.
        """
        raise NotImplementedError("Please implement this method")


class CommandError(Error):
    """Error raised when executing a shell command.

    Attributes:
        expr    -- input command for which the error occurred
        std_out -- command output
        std_err -- command error output
    """

    def __init__(self, expr, std_out, std_err):
        Error.__init__(self)
        self.expr = expr
        self.std_out = std_out
        self.std_err = std_err

    def log(self, flags):
        """ Log the error """
        log(flags, "An error occurred running: " + self.expr, TextType.ERR)
        log(flags, "\nStdOut:\n" + self.std_out, TextType.ERR_EXTRA)
        log(flags, "\nStdErr:\n" + self.std_err, TextType.ERR_EXTRA)


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


def _print_format(msg, format_=None):
    """
    Prints the "msg" to stdout using the specified text format
    (TextFormat class). Prints just standard text if no formats are given.
    """
    if format_ is not None:
        # Print format codes., message and end code.
        print(str.join("", format_) + msg + _ColorCode.ENDC)
    else:
        print(msg)


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
            print(msg)


def log_err(flags, error):
    """
    Prints a formatted string from an error of the Error class.
    - error -- The instance of Error to print.
    """
    log(flags, "\nError:", TextType.ERR)
    if isinstance(error, Error):
        error.log(flags)
    else:
        log(flags, "Unknown type", TextType.ERR)


def log_success(flags):
    """ Prints a success message with appropriate color. """
    log(flags, "Success\n", TextType.SUCCESS)


########################### IO/UI Tools #################################
#########################################################################
### This section defines functions useful for file and ui operations.
### Some functions will print progress messages.
### If a failure occurs functions print an error message and terminate.
#########################################################################

_CMD_DEL = " "


def exec_cmd(cmd):
    """
    Executes a shell command.
    Errors will be raised as CommandError.
    Returns the command output.
    - cmd   -- list of the executable followed by the arguments.
    """
    std_output, std_err_output = "", ""
    try:
        proc = Popen(cmd, stdout=PIPE, stderr=PIPE)
        std_output, std_err_output = proc.communicate()
        # Decode
        #std_output = std_output.decode("utf-8")
        #std_err_output = std_output.decode("utf-8")
    except (OSError, ValueError) as err:
        proc.kill()
        raise CommandError(_CMD_DEL.join(cmd), std_output,
                           std_err_output + "\nError message:\n" + str(err))

    if (b'fatal' in std_output) or (
                b'fatal' in std_err_output) or proc.returncode >= 1:
        # Handle error case
        raise CommandError(_CMD_DEL.join(cmd), std_output, std_err_output)
    else:
        # Success!
        return std_output.strip()


def exec_piped_cmds(cmd1, cmd2):
    """
    Executes a two piped shell commands.
    Errors will be raised as CommandError.
    Returns the command output.
    - cmd1, cmd2    -- list of the executable followed by the arguments.
    """
    std_output, std_err_output = "", ""
    try:
        proc1 = Popen(cmd1, stdout=PIPE)
        proc2 = Popen(cmd2, stdin=proc1.stdout,
                      stdout=PIPE, stderr=PIPE)
        # Allow p1 to receive a SIGPIPE if p2 exits.
        proc1.stdout.close()
        std_output, std_err_output = proc2.communicate()
        # Decode
        std_output = std_output.decode("utf-8")
        std_err_output = std_output.decode("utf-8")
    except (OSError, ValueError) as err:
        proc1.kill()
        proc2.kill()
        raise CommandError(_CMD_DEL.join(cmd1) + " | " + _CMD_DEL.join(cmd2),
                           std_output,
                           std_err_output + "\nError message:\n" + str(err))

    if ('fatal' in std_output) or (
                'fatal' in std_err_output) or proc2.returncode >= 1:
        # Handle error case
        raise CommandError(_CMD_DEL.join(cmd1) + " | " + _CMD_DEL.join(cmd2),
                           std_output, std_err_output)
    else:
        # Success!
        return std_output.strip()


def exec_editor(editor_cmd, _file):
    """
    Opens a shell text editor.
    - _file   -- File to be opened.
    """
    try:
        check_call([editor_cmd, _file])
    except (OSError, ValueError) as err:
        raise CommandError(editor_cmd + " " + _file, "",
                           "\nError message:\n" + str(err))


def clean_dir(flags, dir_path):
    """ Cleans or if not existent creates a directory.
    - dir_path  -- The path of the directory to clean.
    """
    # Remove all files and directories in the given directory.
    if path.isdir(dir_path):
        # Remove all files and directories in the given directory.
        for file_ in listdir(dir_path):
            if path.isdir(file_):
                remove_dir(flags, path.join(dir_path, file_))
            else:
                remove_file(flags, path.join(dir_path, file_))
    else:
        # Just create the given directory.
        mkdirs(flags, dir_path)


def mkdirs(flags, dir_path):
    """ Creates a directory and required parent directories.
    - dir_path  -- The path of the directory to create.
    """
    # Create directories if necessary.
    if not path.isdir(dir_path):
        if not flags['safemode']:
            makedirs(dir_path)


def get_files_with_extension(dir_path, extension):
    """ Retrieves the files matching the given file suffix.
    - dir_path  -- The path of the directory search recursively.
    - extension -- The file suffix to look for.
    Returns the list of files with full paths based on dir_path.
    """
    ext_files = []
    for path_, _, files in walk(dir_path):
        for file_ in files:
            if file_.endswith(extension):
                ext_files += [path.join(path_, file_)]
    return ext_files


def remove_dir(flags, dir_path):
    """ Removes a directory.
    - dir_path  -- The path of the directory to remove.
    """
    if path.isdir(dir_path):
        if not flags['safemode']:
            # Remove directory recursively.
            rmtree(dir_path)


def remove_file(flags, file_path):
    """
    Removes a file.
    - file_path -- The path of the file to remove.
    """
    if path.isfile(file_path):
        if not flags['safemode']:
            # Remove the file.
            remove(file_path)


def move_file_dir(flags, old_path, new_path):
    """ Moves a file or a directory. """
    if old_path != new_path:
        # Calculate the parent directory paths.
        old_dir = path.dirname(old_path)
        new_dir = path.dirname(new_path)

        # Check if the file/dir is being moved or just renamed.
        if old_dir != new_dir:
            if not flags['safemode']:
                # Make sure parent directory exists.
                if not path.isdir(new_dir):
                    makedirs(new_dir)
        else:
            # Rename
            if not flags['safemode']:
                # If only case differs, do temp move (Samba compatibility).
                if old_path.lower() == new_path.lower():
                    rename(old_path, old_path + "_temp")
                    old_path += "_temp"
                # Do the move/rename.
                rename(old_path, new_path)


def prompt_user_input(prompt, allow_empty=False, default=None):
    """
    Prompts the user for input and returns it.
    A space is added after the prompt automatically.
    - allow_empty -- Set to 'True' to allow empty string as input
    - default     -- Set to the default answer if left empty
    """
    prompt_add = ": "
    if allow_empty:
        if default is None:
            prompt_add = ": (empty to skip): "
        else:
            prompt_add = ": [" + default + "] "
    while True:
        stdout.write(prompt + prompt_add)
        input_ = input().lower()
        if input_ != '':
            return input_
        elif allow_empty:
            return default
        else:
            stdout.write("Please respond with a non-empty string.\n")


def prompt_user_yn(question, default="yes"):
    """
    Asks a yes/no question via input() and return their answer.
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
        stdout.write(question + prompt)
        choice = input().lower()
        if default is not None and choice == '':
            return valid[default]
        elif choice in valid:
            return valid[choice]
        else:
            stdout.write("Please respond with 'yes' or 'no' "
                         "(or 'y' or 'n').\n")


def prompt_user_options(question, options, default=0):
    """
    Asks an options based question via input() and returns the choice.
    Returns index of the chosen option or None if aborted by user.
    """
    if 0 <= default < len(options):
        prompt = " [0-" + str(len(options) - 1) + \
                 " (" + str(default) + ")] or 'a' to abort: "
    else:
        raise ValueError("invalid default answer: '%s'" % default)

    while True:
        stdout.write("\nOptions:")
        for (i, option) in enumerate(options):
            stdout.write("\n(" + str(i) + ") " + option)
        stdout.write("\n" + question + prompt)
        choice = input().lower()
        if choice == '':
            return default
        elif choice == 'a':
            return None
        elif choice.isdigit() and 0 <= int(choice) < len(options):
            return int(choice)
        else:
            stdout.write("Please respond with a integer in the range " +
                         "[0-" + str(len(options) - 1) + "]\n")
