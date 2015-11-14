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
MASTER_BRANCH = "master"

CONFIG = \
[   ('GIT', [ \
        ('releaseBranch', "master", True), \
        ('releaseTagType', "release", True), \
        ('upstreamBranch', "upstream", True), \
        ('upstreamTagType', "upstream", True), \
        ('debianBranch', "debian", True), \
        ('debianTagType', "debian", True), \
        ('packageName', "", False), \
    ]), \
    ('SIGNING', [ \
        ('gpgKeyId', "", False) \
    ]), \
    ('UPLOAD', [ \
        ('ppa', "", False) \
    ]), \
]

######################### Errors / Exceptions ###########################
#########################################################################

class Error(Exception):
    """Base class for exceptions in this module."""
    pass

class CommandError(Error):
    """Error raised when executing a shell command.

    Attributes:
        expr -- input command for which the error occurred
        msg  -- explanation of the error
    """

    def __init__(self, expr, msg):
        self.expr = expr
        self.msg = msg

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
parser.add_argument('--config', \
    help='path to the gbp-helper.conf file')

# The possible sub commands.
parser.add_argument('action', nargs='?', \
    choices=['prepare-release', 'undo-release', 'test-release', \
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
            log(("The git command " + error.opr + "failed\n" \
                        if error.opr else "") + error.msg, TextType.ERR)
        else:
            log(error.msg, TextType.ERR)
    
    elif isinstance(error, CommandError):
        log("An error occured running: " + error.expr + \
                    "\n Output: " + error.msg, TextType.ERR)

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
    log("Success", TextType.SUCCESS)

## Shell commands

# Executes a shell command given as a list of the command followed by the arguments.
# Errors will be raised as CommandError.
# Returns the command output.
def execCmd(cmd):
    PIPE = subprocess.PIPE
    process = subprocess.Popen(cmd, stdout=PIPE, stderr=PIPE)
    stdoutput, stderroutput = process.communicate()

    if 'fatal' in stdoutput or process.returncode == 1:
        # Handle error case
        s = " "
        raise CommandError(s.join(cmd), stderroutput)
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
        raise GitError(pwd + (" or " + args.dir) if args.dir else "" \
                            " is not a git repository", "status")

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

# Retrives the tags for the latest commit (HEAD):
# Errors will be raised as GitError (underlying errors or if no tags exists).
# Returns the list of HEAD tags for the given branch.
def get_head_tags(branchName):
    switch_branch(branchName)
    try: 
        headTags = execCmd(["git", "tag", "--points-at", "HEAD"])

        # Check that some tags exists.    
        if not headTags:
            raise GitError("The HEAD on branch \'" + branchName + "\' has no tags")
        return headTags
    except CommandError as e:
        raise GitError("The tags pointing at \'" + branchName + \
                        "\' HEAD, could not be retrived", "tag")

# Retrives the latest HEAD tag (for tags: <tag_type>/<version>) for a branch.
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

# Retrives the HEAD tag version (for tags: <tag_type>/<version>) for a branch:
# Errors will be raised as GitError (underlying errors or if no correct tags exists). 
def get_tag_version(branchName, tagType):
    # Get the latest HEAD tag.
    headTag = get_head_tag(branchName, tagType)
    
    # Get the version part of the tag.
    tagVersion = re.match(r"^" + tagType + r"/(.*$)", headTag)

    if tagVersion:
        return tagVersion.group(1)
    else:
        raise GitError("A tag version could not be extracted")

# Produces the next logical version from the given version string.
# Errors will be raised as GitError.
def get_next_version(version):
    try:
        verPart = version.split('.')
        verPart[-1] = verPart[-1] + 1
        return '.'.join(verPart)
    except Error:
        raise GitError("Version \'" + version + "\' could not be incremented")

# Retrives the name of the current branch.
# Errors will be raised as GitError.
def get_branch():
    check_git_rep()
    try:
        return execCmd(["git", "rev-parse", "--abrev-ref", "HEAD"])
    except CommandError:
        raise GitError("Could not find the name of the current branch", "rev-parse")

# Retrives the name of the current branch.
# Errors will be raised as GitError.
def get_head_commit(branch):
    switch_branch(branch)
    try:
        return execCmd(["git", "rev-parse", "HEAD"])
    except CommandError:
        raise GitError("Could not find the name of the current branch", "rev-parse")

## Affecting repository / files.

# Resets the given branch to the given commit, (accepts HEAD as commit).
# Errors will be raised as GitError.
def reset_branch(branch, commit):
    switch_branch(debianBranch)
    try:
        execCmd(["git", "reset", "--hard", debianCommit])
    except CommandError:
        raise GitError("Could not reset branch \'" + branch + "\' " + \
                        "to commit \'" + commit + "\'")

# Commits all changes for the current branch.
# Errors will be raised as GitError.
def commit_changes():
    check_git_rep()
    try:    
        execCmd(["git", "add", "-A"])
        execCmd(["git", "commit", "-m", "Temp commit."])
    except CommandError:
        raise GitError("Could not commit changes to current branch")

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
        raise GitError("The tag \'" + tag + "\' could not be created", "tag")

## Config read & write

# Creates an example gbp-helper.conf file.
# Errors will be raised as ConfigError.
def create_ex_config():
    # Set config path.
    configPath = args.config if args.config else DEFAULT_CONFIG_PATH

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
def get_config():
    # Set config path.
    configPath = args.config if args.config else DEFAULT_CONFIG_PATH
    
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
            if entry[2] and not val:    
                raise ConfigError("The value in for " + entry[0] + " in section [" + \
                                    section[0] + "] is missing but required", configPath)
            conf[entry[0]] = val

    # Handle special fields.
    if not conf['packageName']:
        try:
            packageName = execCmd(["basename", "`pwd`"])
            conf['packageName'] = packageName
        except CommandError as e:
            raise ConfigError("The package name could not be determined", configPath)
    
    return conf

############################# IO Tools ##################################
#########################################################################
### This section defines functions useful for file and ui operations.
### Some functions will print progress messages.
### If a failure occurs functions print an error message and terminate.
#########################################################################

# Checks whether the first version string is greater than or equal to the second: 
def is_version_lte(v1, v2):
    versions = [v1, v2]
    matchingTags.sort(key=lambda s: map(int, s.split('~')[0].split('.')))
    return matchingTags[0] == v1

# Cleans or if not existant creates a directory.
# Prints progress messages.
def clean_dir(dirPath):
    remove_dir(dirPath)
    if not args.safemode:
        os.makedirs(dirPath)

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

    log("Cleaning old build")
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
def create_config(conf):
    log("Creating example config file", TextType.INIT)
    try:
        create_ex_config()
    except ConfigError as e:
        log_err(e)
        quit()
    
    # Print success message.    
    log_success()

# Prepares release, committing the latest to 
# upstream and merging with debian. Also tags the upstrem commit.
# Returns the tag name on success.
def prepare_release(conf):

    # Constants
    log("Setting sourcedir")
    tmpPath="/tmp/" + conf['packageName']
    
    # Get the tagged version from the release branch.
    try:
        releaseVersion = get_tag_version(conf['releaseBranch'], \
                                            conf['releaseTagType'])
        upstreamVersion = get_tag_version(conf['upstreamBranch'], \
                                            conf['upstreamTagType'])
        sourceDirName = conf['packageName'] + "-" + releaseVersion
        sourceDirPath = os.path.join(tmpPath, sourceDirName)
        tarPath = os.path.join(tmpPath, conf['packageName'] + "_" + \
                    releaseVersion + ".orig.tar.gz")

        # Check that the release version is greater than the upstream version.
        if not is_version_lte(releaseVersion, upstreamVersion):
            raise GitError("Release version is less than" + \
                            "upstream version, aborting")
    except GitError as e:
        log_err(e)
        quit()

    # Clean build directory.
    log("Cleaning build directory")
    clean_dir(tmpPath)
    if not args.safemode:
        os.makedirs(sourceDirPath)

    # Extract the latest commit to release branch.
    log("Extracting latest commit from release branch: <$releaseBranch>")
    try:
        if not args.safemode:
            execCmd(["git", "archive", conf['releaseBranch'], "|", "tar", "-x", "-C", \
                    sourceDirPath, "--exclude=gbp-helper.conf", "--exclude=README.md", \
                    "--exclude=LICENSE", "--exclude-vcs"])
    except CommandError as e:
        log_err(e)
        quit()        

    # Create the upstream tarball.
    log("Making upstream tarball from release branch: <$releaseBranch>")
    try:
        if not args.safemode:
            execCmd(["tar", "-C", tmpPath, "-czf", tarPath, sourceDirName])
    except CommandError as e:
        log_err(e)
        quit()        

    # Commit tarball to upstream branch and tag.
    log("Importing tarball to upstream branch: <$upstreamBranch>")

    # Check if gpg key is set.
    if not gpgKeyId:
        log("Your gpg key id is not set in your gbp-helper.conf," + \
                     " disabling tag signing.", TextType.WARNING)
        tagCmd = "--no-sign-tags"
    else:
        tagCmd = "--sign-tags --keyid=" + conf['gpgKeyId']
      
    try:
        if not args.safemode:
            execCmd(["gbp", "import-orig", "--merge", "--no-interactive", \
                    tagCmd, "--debian-branch=" + conf['debianBranch'], \
                    "--upstream-branch=" + conf['upstreamBranch'], tarPath])
    except CommandError as e:
        log_err(e)
        quit()        

    # Cleanup.git status
    log("Cleaning up")
    if not args.safemode:
        remove_dir(tmpPath)
    
    # Print success message.    
    log_success()
        
    # Return the name of the upstream tag.
    return upstreamTagType + "/" + releaseVersion

# Tries to undo a previously prepared release
# and possible further commits to the debian branch.
def undo_release(conf): #TODO
    # Ask user for confirmation.
    prompt_user_yn("Do you really want to undo the latest release commit?") or quit()

    try:
        # Find out what the latest merge commit between upstream and debian branches.
        # TODO

        # Reset debian to the previous commit to the merge.
        switch_branch(conf['debianBranch'])
        try:
            if not args.safemode:
                execCmd(["git", "reset", "--hard", "HEAD~1"])
        except CommandError as e:
            log_err(GitError("The debian branch <" + \
                                conf['debianBranch'] + "> could not be reset" + \
                                "to before the last upstream merge", "reset"))
            quit()
    
        # Reset upstream to the previous commit to its HEAD.
        upstreamTag = get_tag(upstreamBranch, upstreamTagType)
        switch_branch(upstreamBranch)
        try:
            if not args.safemode:
                execCmd(["git", "reset", "--hard", "HEAD~1"])
        except CommandError as e:
            log_err(GitError("The upstream branch <" + \
                                upstreamBranch + "> could not be reset" + \
                                "to before the last upstream commit", "reset"))
            quit()
        
        # Remove the latest upstream tag.        
        try:
            if not args.safemode:
                execCmd(["git", "tag", "-d", upstreamTag])
        except CommandError as e:
            log_err(GitError("The latest tag (" + upstreamTag + \
                                ") on upstream branch <" + upstremBranch + \
                                "> cound not be deleted", "tag"))
            quit()

    except GitError as e:
        log_err(e)
        quit()

    # Print success message.    
    log_success()
        
# Prepares a release and builds the package
# but reverts all changes after, leaving the repository unchanged.
def test_release(conf):
    
    # Store debian and upstream commits to later revert to them.
    try:
        debianCommit = get_head_commit(conf['debianBranch'])
        upstreamCommit = get_head_commit(conf['upstreamBranch'])
        releaseCommit = get_head_commit(conf['releaseBranch'])
    except GitError as e:
        log_err(e)
        quit()
    
    # Commit any changes on master and tag.
    try:
        releaseVersion = get_tag_version(conf['releaseBranch'], \
                                            conf['releaseTagType'])
        tmpReleaseTag = conf['releaseTagType'] + "/" + \
                                get_next_version(releaseVersion)
        commit_changes(conf['releaseBranch'])
        tag_head(masterBranch, nextReleaseTag)
    except GitError as e:
        log_err(e)
        quit()
    
    # Prepare release, no tags.
    upstreamTag = prepare_release()
    
    # Test package build.
    build_pkg(False)

    # Revert changes.    
    try:
        # Delete upstream tag.
        delete_tag(upstreamTag)
        delete_tag(tmpReleaseTag)
        
        # Reset debian and upstream branches.
        reset_branch(conf['debianBranch'], debianCommit)
        reset_branch(conf['upstreamBranch'], upstreamCommit)
        reset_branch(conf['releaseBranch'], releaseCommit)
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
        debianTagVersion = get_tag_version(conf['debianBranch'], conf['debianTagType'])
    except GitError as e:
        log_err(e)
        log("The latest debian commit isn't porperly tagged, run gbp-helper -b", \
                TextType.ERR)
        quit()

    # Set the name of the .changes file and upload.
    try:
        if not args.safemode:
            execCmd(["dput", "ppa:" + conf['ppaName'], "../build-area/" + \
                        conf['packageName'] + "_" + conf['debianTagVersion'] + \
                        "_source.changes"])
    except CommandError as e:
        log_err(e)
        log("The package could not be uploaded to ppa:" + conf['ppaName'], \
                TextType.ERR)
    
    # Print success message.    
    log_success()

# Builds package from the latest debian commit.
# Tags the debian commit if arg: "tag" is True.
def build_pkg(tag, conf):
    
    # Prepare build.
    prepare_build(conf)

    # Build and without tagging and do linthian checks.
    log("Building debian package")
    
    # Ceck if tag should be created.
    tagCmd = "--git-tag " if tag else ""
    
    # Check if gpg key is set.
    if not gpgKeyId:
        log("Your gpg key id is not set in your gbp-helper.conf," + \
                     " disabling tag signing.", TextType.WARNING)
        tagCmd += "--no-sign-tags"
    else:
        tagCmd += "--sign-tags --keyid=" + conf['gpgKeyId']

    try:
        if not args.safemode:
            execCmd(["gbp", "buildpackage", tagCmd, \
                    "--git-debian-branch=" + conf['debianBranch'], \
                    "--git-upstream-branch=" + conf['upstreamBranch'], \
                    "--git-export-dir=" + BUILD_DIR, "--git-ignore-new", \
                    "--git-builder=\"debuild -S\"", "--git-postbuild=\'echo " + \
                        "\"Running Lintian...\"\' && lintian -I " + \
                        "$GBP_CHANGES_FILE && echo \"Lintian OK\""])
    except CommandError as e:
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

# Pre load config if not being created.
if args.action != 'create-config':
    log("Reading config file")
    try:
        config = get_config()
        log_success()
    except ConfigError as e:
        log_err(e);
        quit()

## Sub commands ##
print args.action
print args.action == 'test-release'

# Create example config.
if args.action == 'create-config':
    create_config(config)

# Prepare release.
elif args.action == 'prepare-release':
    prepare_release(config)

# Undo commit release.
elif args.action == 'undo-release':
    undo_release(config)

# Build release without commiting.
elif args.action == 'test-release':
    test_release(config)

# Upload latest build.
elif args.action == 'upload':
    upload_pkg(config)

# Build test package.
elif args.action == 'build-pkg':
    build_pkg(False, config)

# Build and commit package.
elif args.action == 'commit-pkg':
    buld_pkg(True, config)
