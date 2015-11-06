#!/bin/env python

import argparse
import os
import shutil
import re
import subprocess
import yaml

__version__ = "0.2"

## Constants
PIPE = subprocess.PIPE
DEFAULT_CONFIG_PATH = "./gbp-helper.conf"
BUILD_DIR = "../build-area"
MASTER_BRANCH = "master"
EX_CONFIG = \
    "## gbp-helper.conf: $(basename $(pwd))\n\n" + \
    "#[REQUIRED]\n\n" + \
    "releaseBranch=master\n" + \
    "releaseTagType=release\n\n" + \
    "debianBranch=debian\n" + \
    "debianTagType=debian\n\n" + \
    "upstreamBranch=upstream\n" + \
    "upstreamTagType=upstream\n\n" + \
    "#[OPTIONAL]\n\n" + \
    "gpgKeyId=\n\n" + \
    "ppaName="

CONFIG = \
[   ('git', [ \
        ('releaseBranch', "master", True), \
        ('releaseTagType', "release", True), \
        ('upstreamBranch', "upstream", True), \
        ('upstreamTagType', "upstream", True), \
        ('debianBranch', "debian", True), \
        ('debianTagType', "debian", True), \
    ]), \
    ('signing', [ \
        ('gpgKeyId', "", False) \
    ]), \
    ('upload', [ \
        ('ppa', "", False) \
    ]), \    
]

########################## Argument Parsing #############################
#########################################################################

'''
# Start
parser = argparse.ArgumentParser(description='Helps maintain debian packeges with git.')

parser.add_argument('--version', '-V', action='store_true', \
    help='shows the version')
parser.add_argument('--safemode', '-s', action='store_true', \
    help='disables any file changes')
parser.add_argument('--verbose', '-v', action='store_true', \
    help='enables verbose mode')
parser.add_argument('--commit-release', '-r', action='store_true', \
    help='commits the latest release to upstream and merges with debian branch')
parser.add_argument('--test-build', '-t', action='store_true', \
    help='builds the latest debian commit')
parser.add_argument('--commit-build', '-b', action='store_true', \
    help='builds and tags the latest debian commit')
parser.add_argument('--undo-release', '-z', action='store_true', \
    help='undo the latest release commit (rollback upstream and debian branches)')
parser.add_argument('--upload-build', '-u', action='store_true', \
    help='uploads the latest build to the configured ppa')
parser.add_argument('--create-config', action='store_true', \
    help='creates an example gbp-helper.conf file')
parser.add_argument('--config', \
    help='path to the gbp-helper.conf file')
parser.add_argument('dir', nargs='?', default=os.getcwd())
    
args = parser.parse_args()
'''

# Start
parser = argparse.ArgumentParser(description='Helps maintain debian packeges with git.')
subparsers = parser.add_subparsers(help='sub-command help')
parser.add_argument('-V', '--version', action='store_true', \
    help='shows the version')

# The create-config subcommand.
parser_c = subparsers.add_parser('create-config', action='store_true', \
    help='creates an example gbp-helper.conf file')

# The commit-release subcommand.
parser_r = subparsers.add_parser('commit-release', action='store_true', \
    help='commits the latest release to upstream and merges with debian branch')
parser_r.add_argument('-z', '--undo', action='store_true', \
    help='undo the latest release commit (rollback upstream and debian branches)')

# The test-build subcommand.
parser_t = subparsers.add_parser('test-build', action='store_true', \
    help='builds the latest debian commit')


# The commit-build subcommand.
parser_b = subparsers.add_parser('commit-build', action='store_true', \
    help='builds and tags the latest debian commit')


# The upload-build subcommand.
parser_u = subparsers.add_parser('upload-build', action='store_true', \
    help='uploads the latest build to the configured ppa')

# General args.
group_vq = parser.add_mutually_exclusive_group()
group_vq.add_argument('-v', '--verbose', action='store_true', \
    help='enables verbose mode')
group_vq.add_argument("-q", "--quiet", action="store_true". \
    help='enables quiet mode')
parser.add_argument('-s', '--safemode', action='store_true', \
    help='disables any file changes')
parser.add_argument('--config', \
    help='path to the gbp-helper.conf file')
parser.add_argument('dir', nargs='?', default=os.getcwd())

args = parser.parse_args()

############################ Build Tools ################################
#########################################################################
### This section defines functions useful for build operations.
### No functions will print any progress messages. 
### If a failure occurs functions will terminate with exeptions.
#########################################################################

## Functions

# Prints log messages depending on verbose flag and priority.
# Default priority is 0 which only prints if verbose, 1 always prints.
def printMsg(msg, priority=0):
    if priority > 1 or args.verbose:
        print msg

# Executes a shell command given as a list of the command followed by the arguments.
# Errors will be raised as CommandError.
# Returns the command output.
def execCmd(cmd):
    process = subprocess.Popen(cmd, stdout=PIPE, stderr=PIPE)
    stdoutput, stderroutput = process.communicate()

    if 'fatal' in stdoutput:
        # Handle error case
        raise CommandError(stderroutput) #TODO
    else:
        # Success!
        return stdoutput

# Checks if the current directory is a git repository.
# Returns False if the current directory isn't a git repository.
def is_git_rep():
    try:
        execCmd(["git", "status"])
        return True
    except CommandError as e: #TODO
        return False

# Switches to git branch.
# Errors will be raised as GitError (if checkout isn't possible).
def switch_branch(branchName):
    # Verify that the current dir is a git repository.
    if is_git_rep():
        try:
            # Try to switch branch.
            execCmd(["git", "checkout", branchName])
        except:
            raise GitError(branchName, "Please make sure that the branch \'" + \
                                        branchName + "\' exists and all changes are commited") #TODO
    else:
        raise GitError(pwd + " or " + arg.dir, \
                            "The current directory is not a git repository") #TODO

# Retrives the tags for the latest commit (HEAD):
# Errors will be raised as GitError (underlying errors or if no tags exists).
# Returns the list of HEAD tags for the given branch.
def get_head_tags(branchName):
    switch_branch(branchName)
    try: 
        headTags = execCmd(["git", "tag", "--points-at", "HEAD"])

        # Check that some tags exists.    
        if not headTags: #TODO OK?
            raise GitError("The HEAD on branch \'" + branchName + "\' has no tags") #TODO
        return headTags
    except CommandError as e:
        raise GitError("The tags pointing at \'" + branchName + "\' HEAD, could not be retrived") #TODO

# Retrives the latest HEAD tag (for tags: <tag_type>/<version>) for a branch. 

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
                            "\' has no tags of type: " + tagType + "/<version>") #TODO

# Retrives the HEAD tag version (for tags: <tag_type>/<version>) for a branch: 
def get_tag_version(branchName, tagType):
    # Get the latest HEAD tag.
    headTag = get_head_tag(branchName, tagType)
    
    # Get the version part of the tag.
    tagVersion = re.match(r"^" + tagType + r"/(.*$)", headTag)

    if tagVersion:
        return tagVersion.group(1)
    else:
        raise GitError("A tag version could not be extracted") #TODO


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
    os.makedirs(dirPath)    

# Removes a directory.
# Prints progress messages.
def remove_dir(dirPath):
    if os.path.isdir(dirPath):
        # Remove directory recursively.
        shutil.rmtree(dirPath)

# Cleans the default build directory and switches to the release branch.
# Prints progress messages.
def prepare_build():
    # Make sure we are on the debian branch.
    printMsg("Switching to debian branch: <$debianBranch>")
    switch_branch(debianBranch)

    printMsg("Cleaning old build")
    clean_dir(BUILD_DIR)

# Creates an example gbp-helper.conf file.
# Prints progress messages.
def create_ex_config():
    # Set config path.
    configPath = args.config if args.config else DEFAULT_CONFIG_PATH

    # Make sure file does not exist.
    if os.path.exists(configPath):
        printMsg(configPath + " exists and will not be replaced by an example file", 1)
    else:
        # Create the example file.
        printMsg("Creating example config file")
        try:
            config = ConfigParser.RawConfigParser()

            for section in CONFIG:
                config.add_section(section[0])            
                for entry in section[1]:
                    config.set(section[0], entry[0], entry[1])
            
            # Writing configuration file to "configPath".
            with open(configPath, 'wb') as configfile:
                config.write(configfile)

        except IOError as e: #TODO Maybe not needed?
            printMsg("I/O error({0}): {1}".format(e.errno, e.strerror), 1)

# Update the config variables.
# Errors will be rised by ConfException
# Prints progress messages.
def get_config():
    # Set config path.
    configPath = args.config if args.config else DEFAULT_CONFIG_PATH

    # Switch branch to master before trying to read config.
    switch_branch(MASTER_BRANCH)

    # Parse config file.
    printMsg("Reading config file")
    config = ConfigParser.RawConfigParser(allow_no_value=True)
    config.readfp(io.BytesIO(configPath))    

    # Make sure the required values are set. #TODO
    conf = {}
    for section in CONFIG:
        for entry in section[1]:
            # Check if required.
            if entry[2]:
                conf = config.get(section[0], entry[0])

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

######################### Command Execution #############################
#########################################################################

## Run the selected commands.

# Show version.
if args.version:
    printMsg(__version__, 1)
    # Always exit after showing version.
    quit()

# Create example config.
if args.create_config:
    create_ex_config(args.config if args.config else DEFAULT_CONFIG_PATH)
    # Always exit after config creation.
    quit()

# Undo commit release.
if args.undo_release:
    # Ask user for confirmation.
    prompt_user_yn("Do you really want to undo the latest release commit?") or quit()

    # Update the build variables.
    update_build_vars()
    
    try:
        # Find out what the latest merge commit between upstream and debian branches.
        # TODO

        # Reset debian to the previous commit to the merge.
        switch_branch(debianBranch)
        try:
            execCmd(["git", "reset", "--hard", "HEAD~1"])
        except CommandError as e:
            printMsg("The debian branch <" + debianBranch + "> could not be reset" + \
                        "to before the last upstream merge.", 1)
            quit()
    
        # Reset upstream to the previous commit to its HEAD.
        upstreamTag = get_tag(upstreamBranch, upstreamTagType)
        switch_branch(upstreamBranch)
        try:
            execCmd(["git", "reset", "--hard", "HEAD~1"])
        except CommandError as e:
            printMsg("The upstream branch <" + upstreamBranch + "> could not be reset" + \
                        "to before the last upstream commit.", 1)
            quit()
        
        # Remove the latest upstream tag.        
        try:
            execCmd(["git", "tag", "-d", upstreamTag])
        except CommandError as e:
            printMsg("The latest tag (" + upstreamTag + ") on upstream branch <" + \
                        upstremBranch + "> cound not be deleted", 1)
            quit()

    except GitError as e:
        # Print the error. #TODO
        printMsg(e.msg, 1)
        quit()        
    
    # Always exit after creation.
    quit()

# Upload latest build.
if args.upload_build: #TODO
    # Ask user for confirmation
    prompt_user_yn("Upload the latest build?") or quit()

    # Update the build variables.
    update_config_vars()

    try:
        packageName = execCmd(["basename", "`pwd`"]) #TODO varList + cmd ok?
    except CommandError as e:
        printMsg("The package name could not be determined", 1)
        quit()
    
    # Check if ppa name is set in config.
    if not ppaName:
        printMsg("Your ppa name is not set in your gbp-helper.conf, aborting upload", 1)
        quit()

    # Make sure that the latest debian commit is tagged.
    try:
        debianTagVersion = get_tag_version(debianBranch, debianTagType)
    except GitError as e:
        printMsg(e.msg, 1)
        printMsg("The latest debian commit isn't porperly tagged, run gbp-helper -b", 1)
        quit()

    # Set the name of the .changes file and upload.
    try:
        execCmd(["dput", "ppa:" + ppaName, "../build-area/" + packageName + "_" + \
                                            debianTagVersion + "_source.changes"])
    except CommandError as e:
        printMsg("The package could not be uploaded to ppa:" + ppaName, 1)

    # Always exit after creation.
    quit()

# Commit release.
if args.commit_release: #TODO
    # Update the build variables.
    update_build_vars()

    # Constants
    printMsg("Setting sourcedir")
    tmpPath="/tmp/" + packageName    
    sourceDirName = packageName + "-" + releaseVersion
    sourceDirPath = os.path.join(tmpPath, sourceDirName)
    tarPath = os.path.join(tmpPath, packageName + "_" + releaseVersion + ".orig.tar.gz")
    
    # Get the tagged version from the release branch.
    try:
        releaseVersion = get_tag_version(releaseBranch, releaseTagType)
        upstreamVersion = get_tag_version(upstreamBranch, upstreamTagType)

        # Check that the release version is greater than the upstream version.
        if not is_version_lte(releaseVersion, upstreamVersion):
            raise GitError("Release version is less than upstream version, aborting")
    except GitError as e:
        printMsg(e.msg, 1)
        quit()

                (echo $upstreamVersion; printMsg("No upstream version detected, asuming 0", 1); quit())

    # Clean build directory.
    printMsg("Cleaning build directory")
    clean_dir(tmpPath)
    os.makedirs(sourceDirPath)

    # Extract the latest commit to release branch.
    printMsg("Extracting latest commit from release branch: <$releaseBranch>")
    git archive releaseBranch | tar -x -C sourceDirPath \
      --exclude='gbp-helper.conf' --exclude='README.md' --exclude='LICENSE' \
      --exclude-vcs

    # Create the upstream tarball.
    printMsg("Making upstream tarball from release branch: <$releaseBranch>")
    tar -C $tmpPath -czf $tarPath $sourceDirName
    
    # Commit tarball to upstream branch and tag.
    printMsg("Importing tarball to upstream branch: <$upstreamBranch>")

    # Check if gpg key is set.
    if not gpgKeyId:
        printMsg("Your gpg key id is not set in your gbp-helper.conf, disabling tag signing.", 1)
        gbp import-orig --merge --no-interactive \
            --debian-branch=$debianBranch --upstream-branch=$upstreamBranch $tarPath
    else:
        gbp import-orig --merge --no-interactive --sign-tags --keyid=$gpgKeyId \
            --debian-branch=$debianBranch --upstream-branch=$upstreamBranch $tarPath

    # Cleanup.git status
    printMsg("Cleaning up")
    remove_dir(tmpPath)

# Test build.
if args.test_build: #TODO
    # Update the build variables.
    update_build_vars()
    
    # Prepare build.
    prepare_build()

    # Build and without tagging and do linthian checks.
    printMsg("Building debian package")
    gbp buildpackage --git-debian-branch=$debianBranch --git-upstream-branch=$upstreamBranch \
      --git-export-dir=$BUILD_DIR --git-ignore-new --git-builder="debuild -S" \
      --git-postbuild='echo "Running Lintian..."' && lintian -I $GBP_CHANGES_FILE && echo "Lintian OK"

# Commit build.
if args.commit_build: #TODO
    # Update the build variables.
    update_build_vars()
    
    # Prepare build.
    prepare_build()

    # Build and tag the latest debian branch commit and do linthian checks.
    printMsg("Building debian package and tagging")
    
     # Check if gpg key is set.
    if not gpgKeyId:
        printMsg("Your gpg key id is not set in your gbp-helper.conf, disabling tag signing.", 1)
        gbp buildpackage --git-tag \
            --git-debian-branch=$debianBranch --git-upstream-branch=$upstreamBranch \
            --git-export-dir=$BUILD_DIR --git-builder="debuild -S" \
            --git-postbuild='echo "Running Lintian..."' \
                && lintian -I $GBP_CHANGES_FILE && echo "Lintian OK"
    else
        gbp buildpackage --git-tag  --git-sign-tags --git-keyid=$gpgKeyId \
            --git-debian-branch=$debianBranch --git-upstream-branch=$upstreamBranch \
            --git-export-dir=$BUILD_DIR --git-builder="debuild -S" \
            --git-postbuild='echo "Running Lintian..."' \
                && lintian -I $GBP_CHANGES_FILE && echo "Lintian OK"

######################### Errors / Exceptions ###########################
#########################################################################

class Error(Exception):
    """Base class for exceptions in this module."""
    pass

class CommandError(Error):
    """Exception raised for errors in the input.

    Attributes:
        expr -- input expression in which the error occurred
        msg  -- explanation of the error
    """

    def __init__(self, expr, msg):
        self.expr = expr
        self.msg = msg

class ConfigError(Error):
    """Exception raised for errors in the input.

    Attributes:
        expr -- input expression in which the error occurred
        msg  -- explanation of the error
    """

    def __init__(self, expr, msg):
        self.expr = expr
        self.msg = msg


class GitError(Error):
    """Raised when an operation attempts a state transition that's not
    allowed.

    Attributes:
        prev -- state at beginning of transition
        next -- attempted new state
        msg  -- explanation of why the specific transition is not allowed
    """

    def __init__(self, prev, next, msg):
        self.prev = prev
        self.next = next
        self.msg = msg
