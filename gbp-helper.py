#!/usr/bin/env python

import argparse
import os
import io
import shutil
import re
import subprocess
import ConfigParser
import string

__version__ = "0.2"


############################## Constants ################################
#########################################################################

DEFAULT_CONFIG_PATH = "./gbp-helper.conf"
BUILD_DIR = "../build-area"
CHANGES_FILE_EXT = ".changes"
ORIG_TAR_FILE_EXT = ".orig.tar.gz"
TMP_DIR = "/tmp"
MASTER_BRANCH = "master"

CONFIG = \
[   ('GIT', [ \
        ('releaseBranch', "master", True), \
        ('releaseTagType', "release", True), \
        ('upstreamBranch', "upstream", True), \
        ('upstreamTagType', "upstream", True), \
        ('debianBranch', "debian", True), \
        ('debianTagType', "debian", True) \
    ]), \
    ('SIGNING', [ \
        ('gpgKeyId', None, False) \
    ]), \
    ('BUILD', [ \
        ('buildCmd', "debuild -S --no-lintian", False) \
    ]), \
    ('PACKAGE', [ \
        ('packageName', None, False), \
        ('distribution', None, False), \
        ('urgency', "low", False), \
        ('debianVersionSuffix', "-0~ppa1", False) \
    ]), \
    ('UPLOAD', [ \
        ('ppa', None, False) \
    ]) \
]

######################### Errors / Exceptions ###########################
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

    def __init__(self, msg, file=None, line=None):
        self.msg = msg
        self.file = file
        self.line = line

########################## Argument Parsing #############################
#########################################################################

# Start
parser = argparse.ArgumentParser(description='Helps maintain debian packeges with git.')

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
parser.add_argument('--config', default=DEFAULT_CONFIG_PATH, \
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

############################ Build Tools ################################
#########################################################################
### This section defines functions useful for build operations.
### No functions will print any progress messages. 
### If a failure occurs functions will terminate with exeptions.
#########################################################################

## Logging

class _ColorCode:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'

class TextFormat:
    HEADER = _ColorCode.HEADER
    BLUE = _ColorCode.OKBLUE
    GREEN = _ColorCode.OKGREEN
    WARNING = _ColorCode.WARNING
    FAIL = _ColorCode.FAIL
    BOLD = _ColorCode.BOLD
    UNDERLINE = _ColorCode.UNDERLINE

class TextType:
    INFO = ([TextFormat.BLUE], 1)
    SUCCESS = ([TextFormat.GREEN], 1)
    WARNING = ([TextFormat.WARNING], 1)
    ERR = ([TextFormat.FAIL], 2)
    ERR_EXTRA = ([], 2)
    INIT = ([TextFormat.BOLD], 1)
    STD = ([], 0)

# Prints log messages depending on verbose flag and priority.
# Default priority is 0 which only prints if verbose, 1 always prints.
def log(msg, type=TextType.STD):
    # Always print error messages and similar.
    if (type[1] >= 2) or (not args.quiet and type[1] == 1) or args.verbose:
        if args.color:
            print_format(msg, type[0])
        else:
            print msg

# Prints a formatted string from an error of the Error class.
def log_err(error):
    log("\nError:", TextType.ERR)
    if isinstance(error, GitError):
        if error.opr:
            log(("The git command \'" + error.opr + "\' failed\n" \
                        if error.opr else "") + error.msg, TextType.ERR)
        else:
            log(error.msg, TextType.ERR)
    
    elif isinstance(error, CommandError):
        log("An error occured running: " + error.expr, TextType.ERR)
        log("\nStdOut:\n" + error.stdout, TextType.ERR_EXTRA)
        log("\nStdErr:\n" + error.stderr, TextType.ERR_EXTRA)

    elif isinstance(error, ConfigError):
        log(("An error with file: " + error.file + "\n" if error.file else "") + \
                    ("On line: " + error.line + "\n" if error.line else "") + \
                    error.msg, TextType.ERR)

# Prints the "msg" to stdout using the specified text formats (TextFormat class).
# Prints just 
def print_format(msg, formats):
    if formats:
        # Print format codes., message and end code.
        print string.join(formats) + msg + _ColorCode.ENDC
    else:
        print msg

# Prints a success message with appropriate color.
def log_success():
    log("Success\n", TextType.SUCCESS)

## Shell commands

# Executes a shell command given as a list of the command followed by the arguments.
# Errors will be raised as CommandError.
# Returns the command output.
def execCmd(cmd):
    PIPE = subprocess.PIPE
    s = " "
    
    try:
        process = subprocess.Popen(cmd, stdout=PIPE, stderr=PIPE)
        stdoutput, stderroutput = process.communicate()
    except Exception as e:
        raise CommandError(s.join(cmd), e.msg)
    
    if ('fatal' in stdoutput) or ('fatal' in stderroutput) or \
            process.returncode >= 1:
        # Handle error case
        raise CommandError(s.join(cmd), stdoutput, stderroutput)
    else:
        # Success!
        return stdoutput

## Git operations

# Checks if the current directory is a git repository.
# Errors will be raised as GitError (if not a rep).
def check_git_rep():
    try:
        execCmd(["git", "status"])
    except CommandError:
        raise GitError(pwd + " is not a git repository", "status")

# Switches to git branch.
# Errors will be raised as GitError (if checkout isn't possible).
def switch_branch(branchName):
    # Verify that the current dir is a git repository.
    check_git_rep()
    try:
        # Try to switch branch.
        execCmd(["git", "checkout", branchName])
    except:
        raise GitError("Please make sure that the branch \'" + \
                            branchName + "\' exists and all changes " + \
                            "are commited", "checkout")

# Retrives the tags for the latest commit (HEAD).
# Errors will be raised as GitError (underlying errors).
# Returns the list of HEAD tags for the given branch (can be empty).
def get_head_tags(branchName):
    switch_branch(branchName)
    try: 
        headTags = execCmd(["git", "tag", "--points-at", "HEAD"]).rstrip()
        return headTags
    except CommandError as e:
        raise GitError("The tags pointing at \'" + branchName + \
                        "\' HEAD, could not be retrived", "tag")

# Retrives the latest HEAD tag (<tag_type>/<version>) for a branch.
# Errors will be raised as GitError (underlying errors or if no tags exists). 
def get_head_tag(branchName, tagType):
    # Get the latest HEAD tags.
    headTags = get_head_tags(branchName)
        
    # Find the matching tags.
    matchingTags = re.findall(r"(?m)^" + tagType + r"/.*$", headTags)

    # Make sure atleast some tag follows the right format.
    if matchingTags:
        # Find the "latest tag" 
        # Assuming format: <pkg_name>/<upstream_version>~<deb_version>
        matchingTags.sort(key=lambda s: map(int, s.split('/')[1].split('~')[0].split('.')))
        return matchingTags[0]
    else:
        raise GitError("The HEAD on branch \'" + branchName + \
                            "\' has no tags of type: " + tagType + "/<version>")

# Retrives the latest tag (<tag_type>/<version>) for a branch.
# Errors will be raised as GitError (underlying errors or if no tags exists). 
def get_latest_tag(branchName, tagType):
    # Get the latest tag.
    switch_branch(branchName)
    try:
        return execCmd(["git", "describe", "--abbrev=0", "--tags", \
                                "--match", tagType + "/*"]).rstrip()
    except CommandError:
        raise GitError("The branch \'" + branchName + \
                            "\' has no tags of type: " + tagType + "/<version>")

# Extracts the version string from a tag (<tag_type>/<version>).
# Errors will be raised as GitError
def get_version_from_tag(tag, tagType):
    # Get the version part of the tag.
    tagVersion = re.match(r"^" + tagType + r"/(.*$)", tag)
    if tagVersion:
        return tagVersion.group(1)
    else:
        raise GitError("A tag version could not be extracted from tag " + \
                            "\'" + tag + "\'")

# Retrives the HEAD tag version (<tag_type>/<version>) for a branch.
# Errors will be raised as GitError (underlying errors or if no correct tags exists). 
def get_head_tag_version(branchName, tagType):
    # Get the latest HEAD tag.
    headTag = get_head_tag(branchName, tagType)
    return get_version_from_tag(headTag, tagType)
    
# Retrives latest tag version (<tag_type>/<version>) for a branch.
# Errors will be raised as GitError (underlying errors or if no correct tags exists). 
def get_latest_tag_version(branchName, tagType):
    # Get the latest tag.
    latestTag = get_latest_tag(branchName, tagType)
    return get_version_from_tag(latestTag, tagType)

# Checks whether the first version string is greater than second.
def is_version_lt(v1, v2):
    return v1 != v2 and is_version_lte(v1, v2)
    
# Checks whether the first version string is less than or equal to the second.
def is_version_lte(v1, v2):
    versions = [v1, v2]
    versions.sort(key=lambda s: map(int, s.split('~')[0].split('.')))
    return versions[0] == v1

# Produces the next logical version from the given version string.
# Errors will be raised as GitError.
def get_next_version(version):
    try:
        verPart = version.split('.')
        verPart[-1] = str(int(verPart[-1]) + 1)
        return '.'.join(verPart)
    except Error:
        raise GitError("Version \'" + version + "\' could not be incremented")

# Check if working directory is clean.
# Returns True if clean, False otherwise.
def is_working_dir_clean():
    check_git_rep()
    try:
        execCmd(["git", "status", "--porcelain"])
        return True
    except CommandError:
        raise GitError("Could not determine if working directory is clean.", "status")
    return False

# Retrives the name of the current branch.
# Errors will be raised as GitError.
def get_branch():
    check_git_rep()
    try:
        return execCmd(["git", "rev-parse", "--abrev-ref", "HEAD"]).rstrip()
    except CommandError:
        raise GitError("Could not find the name of the current branch", "rev-parse")

# Retrives the name of the current branch.
# Errors will be raised as GitError.
def get_head_commit(branch):
    switch_branch(branch)
    try:
        return execCmd(["git", "rev-parse", "HEAD"]).rstrip()
    except CommandError:
        raise GitError("Could not find the name of the current branch", "rev-parse")

## Affecting repository / files.

# Resets the given branch to the given commit, (accepts HEAD as commit).
# Errors will be raised as GitError.
def reset_branch(branch, commit):
    switch_branch(branch)
    try:
        execCmd(["git", "reset", "--hard", commit])
    except CommandError:
        raise GitError("Could not reset branch \'" + branch + "\' " + \
                        "to commit \'" + commit + "\'")

# Commits all changes for the current branch.
# Errors will be raised as GitError.
def commit_changes(msg):
    check_git_rep()
    try:    
        execCmd(["git", "add", "-A"])
        execCmd(["git", "commit", "-m", msg])
    except CommandError:
        raise GitError("Could not commit changes to current branch")

# Stashes the changes in the working directory with a optional stash name.
def stash_changes(name=None):
    check_git_rep()
    try:
        if name:
            execCmd(["git", "stash", "save", name])
        else:
            execCmd(["git", "stash"])
    except CommandError:
        raise GitError("Could not stash uncommitted changes", "stash")

# Applies stashed changes on the given branch with a optional stash name.
def apply_stash(branch, name=None, drop=True):
    switch_branch(branch)
    try:
        if name:
            execCmd(["git", "stash", "apply", "stash/" + name])
            if drop:
                execCmd(["git", "stash", "drop", "stash/" + name])
        else:
            execCmd(["git", "stash", "apply"])
            if drop:
                execCmd(["git", "stash", "drop"])

    except CommandError:
        raise GitError("Could not apply stashed changes" + \
                        (" (stash/" + name + ")" if name else ""), "stash")

# Deletes the given tag.
# Errors will be raised as GitError.
def delete_tag(tag):
    check_git_rep()
    try:    
        execCmd(["git", "tag", "-d", tag])
    except CommandError:
        raise GitError("The tag \'" + tag + "\' could not be deleted", "tag")

# Tags the HEAD of the given branch..
# Errors will be raised as GitError.
def tag_head(branch, tag):
    switch_branch(branch)
    try:
        execCmd(["git", "tag", tag])
    except CommandError:
        raise GitError("The tag \'" + tag + "\' could not be created " + \
                        "and may already exist", "tag")

## Config read & write

# Creates an example gbp-helper.conf file.
# Errors will be raised as ConfigError.
def create_ex_config(configPath):

    # Make sure file does not exist.
    if os.path.exists(configPath):
        raise ConfigError("File exists and will not" + \
                            " be replaced by an example file", configPath)
    else:
        try:
            config = ConfigParser.RawConfigParser()

            for section in CONFIG:
                config.add_section(section[0])            
                for entry in section[1]:
                    config.set(section[0], entry[0], entry[1])
            
            # Writing configuration file to "configPath".
            if not args.safemode:
                with open(configPath, 'wb') as configfile:
                    config.write(configfile)

        except IOError as e:
            raise ConfigError("I/O error({0}): {1}".format(e.errno, e.strerror), \
                                configPath)

# Update the config variables.
# Errors will be raised as ConfigError.
def get_config(configPath):

    # Check if config file exists.
    if not os.path.exists(configPath):
        raise ConfigError("The config file could not be found", configPath)
        
    # Switch branch to master before trying to read config.
    switch_branch(MASTER_BRANCH)

    # Parse config file.
    config = ConfigParser.RawConfigParser(allow_no_value=True)
    config.read(configPath)    

    # Make sure the required values are set.
    conf = {}
    for section in CONFIG:
        for entry in section[1]:
            # Set conf value even if it's empty.
            val = config.get(section[0], entry[0])
            # Check if required but non existant.
            if not val:
                # Use default value instead (can be None).
                val = entry[1]
                # Check if required in config.
                if entry[2]:
                    raise ConfigError("The value in for " + entry[0] + " in section [" + \
                                        section[0] + "] is missing but required", configPath)
            conf[entry[0]] = val

    # Handle special fields.
    if not conf['packageName']:
        conf['packageName'] = os.path.basename(os.getcwd())
    
    return conf

############################# IO Tools ##################################
#########################################################################
### This section defines functions useful for file and ui operations.
### Some functions will print progress messages.
### If a failure occurs functions print an error message and terminate.
#########################################################################

# Cleans or if not existant creates a directory.
# Prints progress messages.
def clean_dir(dirPath):
    remove_dir(dirPath)
    if not args.safemode:
        os.makedirs(dirPath)
        
# Retrives the first file matching the given extension or None.
def get_file_with_extension(dirPath, extension):
    for file in os.listdir(dirPath):
        if file.endswith(extension):
            return file
    return None

# Removes a directory.
def remove_dir(dirPath):
    if os.path.isdir(dirPath):
        if not args.safemode:
            # Remove directory recursively.
            shutil.rmtree(dirPath)

# Cleans the default build directory and switches to the release branch.
# Prints progress messages.
def prepare_build(conf):
    # Make sure we are on the debian branch.
    log("Switching to debian branch: <" + conf['debianBranch'] + ">")
    switch_branch(conf['debianBranch'])

    log("Cleaning old build files in \'" + BUILD_DIR + "\'")
    clean_dir(BUILD_DIR)

# Asks a yes/no question via raw_input() and return their answer.
# "question" the string presented, "default" is the presumed answer 
# if the user just hits <Enter>. It must be "yes" (the default), 
# "no" or None (meaning an answer is required of the user).
# Returns True if user answers "yes", else False.
def prompt_user_yn(question, default="yes"):
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

####################### Sub Command functions ###########################
#########################################################################

# Creates example config.
def create_config(conf, configPath):
    log("Creating example config file: " + configPath)
    try:
        create_ex_config(configPath)
    except ConfigError as e:
        log_err(e)
        quit()
    
    # Print success message.    
    log_success()

# Prepares release, committing the latest to 
# upstream and merging with debian. Also tags the upstrem commit.
# Returns the tag name on success.
def prepare_release(conf, sign):

    # Constants
    log("Setting build paths")
    tmpPath = os.path.join(TMP_DIR, conf['packageName'])
    archivePath = os.path.join(tmpPath, conf['releaseBranch'] + "_archive.tar")
    
    # Get the tagged version from the release branch.
    try:
        releaseVersion = get_head_tag_version(conf['releaseBranch'], \
                                            conf['releaseTagType'])
        upstreamVersion = get_head_tag_version(conf['upstreamBranch'], \
                                            conf['upstreamTagType'])
        sourceDirName = conf['packageName'] + "-" + releaseVersion
        sourceDirPath = os.path.join(tmpPath, sourceDirName)
        tarPath = os.path.join(tmpPath, conf['packageName'] + "_" + \
                    releaseVersion + ORIG_TAR_FILE_EXT)

        # Check that the release version is greater than the upstream version.
        if not is_version_lt(upstreamVersion, releaseVersion):
            raise GitError("Release version is less than " + \
                            "upstream version, aborting")

        # Clean build directory.
        log("Cleaning build directory")
        clean_dir(tmpPath)
        if not args.safemode:
            os.makedirs(sourceDirPath)

        # Extract the latest commit to release branch.
        log("Extracting latest commit from release branch \'" + \
                conf['releaseBranch'] + "\'")
        if not args.safemode:
            execCmd(["git", "archive", conf['releaseBranch'], "-o", archivePath])
            execCmd(["tar", "-xf", archivePath, "--directory=" + sourceDirPath, \
                        "--exclude=gbp-helper.conf", "--exclude=README.md", \
                        "--exclude=LICENSE", "--exclude-vcs"])

        # Create the upstream tarball.
        log("Making upstream tarball from release branch: \'" + \
                conf['releaseBranch'] + "\'")
        if not args.safemode:
            execCmd(["tar", "--directory=" + tmpPath, "-czf", tarPath, sourceDirName])

        # Commit tarball to upstream branch and tag.
        log("Importing tarball to upstream branch: \'" + \
                conf['upstreamBranch'] + "\'")

        # Check if sould sign and gpg key is set.
        if sign and conf['gpgKeyId']:
            tagCmd = ["--sign-tags", "--keyid=" + str(conf['gpgKeyId'])]
        else:
            tagCmd = []
            if sign:
                log("Your gpg key id is not set in your gbp-helper.conf," + \
                         " disabling tag signing.", TextType.WARNING)
      
        if not args.safemode:
            execCmd(["gbp", "import-orig", "--no-interactive", "--merge"] + \
                        tagCmd + ["--debian-branch=" + conf['debianBranch'], \
                        "--upstream-branch=" + conf['upstreamBranch'], tarPath])
    
    except Error as e:
        log_err(e)
        quit()        

    # Cleanup.git status
    log("Cleaning up")
    if not args.safemode:
        remove_dir(tmpPath)
    
    # Print success message.    
    log_success()
        
    # Return the name of the upstream tag.
    return conf['upstreamTagType'] + "/" + releaseVersion

# Prepares a release and builds the package
# but reverts all changes after, leaving the repository unchanged.
def test_release(conf):
    
    # Try to get the tag of the master HEAD.
    try:
        releaseCommit = get_head_commit(conf['releaseBranch'])
    except GitError as e:
        log_err(e)
        quit()
    
    if not is_working_dir_clean():
        # Only stash if uncommitted changes are on release branch.
        currentBranch = get_branch()
        if currentBranch == conf['releaseBranch']:
            log("Stashing uncommited changes on release branch \'" + \
                    conf['releaseBranch'] + "\'")
            resetRelease = True
            try:
                # Save changes to tmp stash.
                if not args.safemode:
                    stashName = "gbp-helper<" + releaseCommit + ">"
                    stash_changes(stashName)
                
                # Apply stash and create a tmp commit.
                log("Creating temporary release commit")
                if not args.safemode:
                    apply_stash(stashName, False)
                    commit_changes("Temp release commit.")
            except GitError as e:
                log_err(e)
        else:
            # Uncommitted changes on another branch, quit
            log("Uncommitted changes on branch \'" + currentBranch + \
                    "\', commit before proceding.", TextType.ERR)
            quit()
    else:
        log("Working directory clean, no commit needed")
        resetRelease = False
        
    # Tag the last commit properly.
    # Only tag if no tags exists at HEAD.
    if not get_head_tags(conf['releaseBranch']):
        removeReleaseTag = True
        try:
            releaseVersion = get_latest_tag_version(conf['releaseBranch'], \
                                                conf['releaseTagType'])
            tmpVersion = get_next_version(releaseVersion)
            tmpReleaseTag = conf['releaseTagType'] + "/" + tmpVersion
            log("Tagging release HEAD as \'" + tmpReleaseTag + "\'")
            if not args.safemode:
                tag_head(conf['releaseBranch'], tmpReleaseTag)
        except GitError as e:
            log_err(e)
            quit()
    else:
        log("Release HEAD already tagged, skipping tagging")
        removeReleaseTag = False
    
    try:
        # Store debian and upstream commits to later revert to them.
        debianCommit = get_head_commit(conf['debianBranch'])
        upstreamCommit = get_head_commit(conf['upstreamBranch'])
    except GitError as e:
        log_err(e)
        quit()
    
    # Prepare release, no tags.
    upstreamTag = prepare_release(conf, False)
    
    # Update the changlog to match upstream version.
    tmpDebianVersion = tmpVersion + conf['debianVersionSuffix']
    update_changelog(conf, version=tmpDebianVersion, commit=True)
    
    # Test package build.
    build_pkg(conf)

    # Revert changes.    
    try:
        log("Reverting changes")
        # Delete upstream tag.
        if not args.safemode:
            delete_tag(upstreamTag)
        
        # Remove temporary release tag if created.
        if removeReleaseTag:
            log("Removing temporary release tag \'" + tmpReleaseTag + "\'")
            if not args.safemode:
                delete_tag(tmpReleaseTag)
        
        # Reset master if needed.
        if resetRelease:
            log("Resetting release branch \'" + conf['releaseBranch'] + "\'"+ \
                    "to commit \'" + releaseCommit + "\'")
            log("Restoring uncommitted changes from stash to release branch \'" + \
                    conf['releaseBranch'] + "\'")
            if not args.safemode:
                reset_branch(conf['releaseBranch'], releaseCommit)
                apply_stash(conf['releaseBranch'], stashName, True)
        
        # Reset debian and upstream branches.
        log("Resetting debian branch \'" + conf['debianBranch'] + "\'" + \
                "to commit \'" + debianCommit + "\'")
        log("Resetting upstream branch \'" + conf['upstreamBranch'] + "\'" + \
                "to commit \'" + upstreamCommit + "\'")
        if not args.safemode:
            reset_branch(conf['debianBranch'], debianCommit)
            reset_branch(conf['upstreamBranch'], upstreamCommit)
    except GitError as e:
        log_err(e)
        quit()
    
    # Print success message.    
    log_success()

# Uploads the latest build to the ppa set in the config file.
def upload_pkg(conf):
    # Ask user for confirmation
    prompt_user_yn("Upload the latest build?") or quit()
    
    # Check if ppa name is set in config.
    if not ppaName:
        log_err(ConfigError("The value ppaName is not set" + \
                                " in the config file, aborting upload"))
        quit()

    # Make sure that the latest debian commit is tagged.
    try:
        debianTagVersion = get_head_tag_version(conf['debianBranch'], \
                                                conf['debianTagType'])
    except GitError as e:
        log_err(e)
        log("The latest debian commit isn't porperly tagged, run gbp-helper -b", \
                TextType.ERR)
        quit()

    # Set the name of the .changes file and upload.
    changeFile = get_file_with_extension(BUILD_DIR, CHANGES_FILE_EXT)
    if changesFile:
        try:
            if not args.safemode:
                execCmd(["dput", "ppa:" + conf['ppaName'], \
                            os.path.join(BUILD_DIR, changesFile)])
        except CommandError as e:
            log_err(e)
            log("The package could not be uploaded to ppa:" + \
                    conf['ppaName'], TextType.ERR)
    else:
        log("Changefile (" + CHANGES_FILE_EXT + ") not found in \'" + \
                    BUILD_DIR + "'\, aborting upload", TextType.ERR)
        quit()
    
    # Print success message.
    log_success()

# Builds package from the latest debian commit.
# Tags the debian commit if arg: "tag" is True.
# Signs the created tag if sign (and tag) is True.
# Uses a treeish decriptor to create the upstream tarball instead of changelog ref.
def build_pkg(conf, tag=False, sign=False, upstreamTreeish=None):
    
    # Prepare build.
    prepare_build(conf)

    # Build and without tagging and do linthian checks.
    log("Building debian package")
    
    # Check if tag should be created.
    tagOpt = ["--git-tag"] if tag else []
    
    # Check if gpg key is set.
    if sign and conf['gpgKeyId']:
        tagOpt += ["--sign-tags", "--keyid=" + str(conf['gpgKeyId'])]
    else:
        if sign:
            log("Your gpg key id is not set in your gbp-helper.conf," + \
                     " disabling tag signing.", TextType.WARNING)
    # Check if treeish is set.
    upstreamOpt = (["--git-upstream-tree=" + upstreamTreeish] \
                        if upstreamTreeish else [])
    
    try:
        if not args.safemode:
            execCmd(["gbp", "buildpackage"] + tagOpt + upstreamOpt + \
                    ["--git-debian-branch=" + conf['debianBranch'], \
                    "--git-upstream-branch=" + conf['upstreamBranch'], \
                    "--git-export-dir=" + BUILD_DIR, "--git-builder=" + BUILD_CMD])
            changesFile = get_file_with_extension(BUILD_DIR, CHANGES_FILE_EXT)
            if changesFile:
                log("Running Lintian...", TextType.INFO)
                log(execCmd(["lintian", "-I", os.path.join(BUILD_DIR, changesFile)]))
                log("Lintian OK", TextType.INFO)
            else:
                log("Changesfile (" + CHANGES_FILE_EXT + ") not found in \'" + \
                        BUILD_DIR + "'\, skipping lintian", TextType.WARNING)
    except CommandError as e:
        log_err(e)
        quit()
    
    # Print success message.    
    log_success()

# Update the changelog with the git commit messsages since last build.
def update_changelog(conf, version=None, editor=False, commit=False, release=False):

    # Build and without tagging and do linthian checks.
    log("Updating changelog to new version")
    if not version:
        log("Version not set, using standard format")
        try:
            upstreamVersion = get_head_tag_version(config['upstreamBranch'], \
                                                    config['upstreamTagType'])
            version = conf['debianTagType'] + "/" + upstreamVersion + \
                            conf['debianVersionSuffix']
            log("Using version \'" + version + "\'")
        except GitError as e:
            log_err(e)
            quit()
    else:
        log("Updating changelog with version \'" + version + "\'")
    
    commitOpt = (["--commit"] if commit else [])
    editorOpt = (["--spawn-editor=always"] if editor else [])
    distributionOpt = (["--distribution=" + conf['distribution']] \
                            if conf['distribution'] else [])
    releaseOpt = (["--release"] if release else [])
    
    try:
        switch_branch(conf['debianBranch'])
        if not args.safemode:
            execCmd(["gbp", "dch", "--debian-branch=" + conf['debianBranch'], \
                    "--new-version=" + version, "--urgency=" + conf['urgency']] + \
                    commitOpt + editorOpt + distributionOpt + releaseOpt)
    except Error as e:
        log_err(e)
        quit()
    
    # Print success message.    
    log_success()

######################### Command Execution #############################
#########################################################################

## Check optional flags.

# Check safemode.
if args.safemode:
    log("Safemode enabled, not changing any files", TextType.INFO)

# Show version.
if args.version:
    log(__version__, 1)
    # Always exit after showing version.
    quit()

# Switch to target directory.
os.chdir(args.dir)

# Prepare if a subcommand is used.
if args.action and args.action != 'create-config':
    # Pre load config if not being created.
    log("Reading config file", TextType.INFO)
    try:
        config = get_config(args.config)
    except ConfigError as e:
        log_err(e);
        quit()
    
    # Save current branch name.
    log("Saving initial branch to restor after execution", TextType.INFO)
    try:
        oldBranch = get_branch()
    except GitError as e:
        log_err(e)
        quit()

## Sub commands ##
log("Executing commad: " + args.action, TextType.INIT)

# Create example config.
if args.action == 'create-config':
    create_config(config, args.config)

# Prepare release.
elif args.action == 'prepare-release':
    prepare_release(config, True)

# Build release without commiting.
elif args.action == 'test-release':
    test_release(config)

# Updates the changelog with set options, 
# lets user review in editor and commits the changes.
elif args.action == 'update-changelog':
    update_changelog(config, editor=True, commit=True, release=True)

# Upload latest build.
elif args.action == 'upload':
    upload_pkg(config)

# Build test package.
elif args.action == 'build-pkg':
    build_pkg(config)

# Build and commit package.
elif args.action == 'commit-pkg':
    buld_pkg(config, True, True)

# Restore branch state.
try:
    if oldBranch != get_branch():
        log("Restoring active branch to \'" + oldBranch + "\'"q, TextType.INFO)
        switch_branch(oldBranch)
except GitError as e:
    log_err(e)
