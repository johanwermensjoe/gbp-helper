#!/usr/bin/env python

import argparse
import os
import shutil
import re
import subprocess
import ConfigParser

__version__ = "0.2"

## Constants
DEFAULT_CONFIG_PATH = "./gbp-helper.conf"
BUILD_DIR = "../build-area"
MASTER_BRANCH = "master"

CONFIG = \
[   ('git', [ \
        ('releaseBranch', "master", True), \
        ('releaseTagType', "release", True), \
        ('upstreamBranch', "upstream", True), \
        ('upstreamTagType', "upstream", True), \
        ('debianBranch', "debian", True), \
        ('debianTagType', "debian", True), \
        ('packageName', "", False), \
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

# Start
parser = argparse.ArgumentParser(description='Helps maintain debian packeges with git.')
subparsers = parser.add_subparsers(help='main actions')
parser.add_argument('-V', '--version', action='store_true', \
    help='shows the version')

# The create-config subcommand.
parser_c = subparsers.add_parser('create-config', \
    help='creates an example gbp-helper.conf file')

# The commit-release subcommand.
parser_r = subparsers.add_parser('commit-release', \
    help='commits the latest release to upstream and merges with debian branch')
parser_r.add_argument('-z', '--undo', action='store_true', \
    help='undo the latest release commit (rollback upstream and debian branches)')

# The test-build subcommand.
parser_t = subparsers.add_parser('test-build', \
    help='builds the latest debian commit')


# The commit-build subcommand.
parser_b = subparsers.add_parser('commit-build', \
    help='builds and tags the latest debian commit')


# The upload-build subcommand.
parser_u = subparsers.add_parser('upload-build', \
    help='uploads the latest build to the configured ppa')

# General args.
group_vq = parser.add_mutually_exclusive_group()
group_vq.add_argument('-v', '--verbose', action='store_true', \
    help='enables verbose mode')
group_vq.add_argument("-q", "--quiet", action="store_true", \
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
    if not args.quiet and priority > 1 or args.verbose:
        print msg

# Executes a shell command given as a list of the command followed by the arguments.
# Errors will be raised as CommandError.
# Returns the command output.
def execCmd(cmd):
    PIPE = subprocess.PIPE
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
def remove_dir(dirPath):
    if os.path.isdir(dirPath):
        # Remove directory recursively.
        shutil.rmtree(dirPath)

# Cleans the default build directory and switches to the release branch.
# Prints progress messages.
def prepare_build(conf):
    # Make sure we are on the debian branch.
    printMsg("Switching to debian branch: <" + conf['debianBranch'] + ">")
    switch_branch(conf['debianBranch'])

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

    # Make sure the required values are set.
    conf = {}
    for section in CONFIG:
        for entry in section[1]:
            # Set conf value even if it's empty.
            val = config.get(section[0], entry[0])
            # Check if required but non existant.
            if entry[2] and not val:    
                printMsg("The value in " + configPath + "for " + entry[0] + " in section [" + \
                            section[0] + "] is missing but required.", 1)
            conf[entry[0]] = val

    # Handle special fields.
    if not conf['packageName']:
        printMsg("The value packageName is not set, defaulting to dirname.")
        try:
            packageName = execCmd(["basename", "`pwd`"])
            conf['packageName'] = packageName
        except CommandError as e:
            printMsg("The package name could not be determined", 1)

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

## Helper commands ##

# Show version.
if args.version:
    printMsg(__version__, 1)
    # Always exit after showing version.
    quit()

# Create example config.
if args.create_config:
    create_ex_config()
    # Always exit after config creation.
    quit()

## Build commands ##

# Load config.
config = getConfig()

'''
# Undo commit release.
if args.undo_release:
    # Ask user for confirmation.
    prompt_user_yn("Do you really want to undo the latest release commit?") or quit()

    try:
        # Find out what the latest merge commit between upstream and debian branches.
        # TODO

        # Reset debian to the previous commit to the merge.
        switch_branch(conf['debianBranch'])
        try:
            execCmd(["git", "reset", "--hard", "HEAD~1"])
        except CommandError as e:
            printMsg("The debian branch <" + conf['debianBranch'] + "> could not be reset" + \
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
'''

# Upload latest build.
if args.upload_build:
    # Ask user for confirmation
    prompt_user_yn("Upload the latest build?") or quit()
    
    # Check if ppa name is set in config.
    if not ppaName:
        printMsg("The value ppaName is not set in the config file, aborting upload", 1)
        quit()

    # Make sure that the latest debian commit is tagged.
    try:
        debianTagVersion = get_tag_version(conf['debianBranch'], conf['debianTagType'])
    except GitError as e:
        printMsg(e.msg, 1)
        printMsg("The latest debian commit isn't porperly tagged, run gbp-helper -b", 1)
        quit()

    # Set the name of the .changes file and upload.
    try:
        execCmd(["dput", "ppa:" + conf['ppaName'], "../build-area/" + conf['packageName'] + "_" + \
                                            conf['debianTagVersion'] + "_source.changes"])
    except CommandError as e:
        printMsg("The package could not be uploaded to ppa:" + conf['ppaName'], 1)

    # Always exit after creation.
    quit()

# Commit release.
if args.commit_release:

    # Constants
    printMsg("Setting sourcedir")
    tmpPath="/tmp/" + conf['packageName']
    
    # Get the tagged version from the release branch.
    try:
        releaseVersion = get_tag_version(conf['releaseBranch'], conf['releaseTagType'])
        upstreamVersion = get_tag_version(conf['upstreamBranch'], conf['upstreamTagType'])
        sourceDirName = conf['packageName'] + "-" + releaseVersion
        sourceDirPath = os.path.join(tmpPath, sourceDirName)
        tarPath = os.path.join(tmpPath, conf['packageName'] + "_" + releaseVersion + ".orig.tar.gz")

        # Check that the release version is greater than the upstream version.
        if not is_version_lte(releaseVersion, upstreamVersion):
            raise GitError("Release version is less than upstream version, aborting")
    except GitError as e:
        printMsg(e.msg, 1)
        quit()

    # Clean build directory.
    printMsg("Cleaning build directory")
    clean_dir(tmpPath)
    os.makedirs(sourceDirPath)

    # Extract the latest commit to release branch.
    printMsg("Extracting latest commit from release branch: <$releaseBranch>")
    try:
        execCmd(["git", "archive", conf['releaseBranch'], "|", "tar", "-x", "-C", sourceDirPath, \
                    "--exclude=gbp-helper.conf", "--exclude=README.md", "--exclude=LICENSE", \
                    "--exclude-vcs"])
    except CommandError as e:
        printMsg(e.msg, 1)
        quit()        

    # Create the upstream tarball.
    printMsg("Making upstream tarball from release branch: <$releaseBranch>")
    try:
        execCmd(["tar", "-C", tmpPath, "-czf", tarPath, sourceDirName])
    except CommandError as e:
        printMsg(e.msg, 1)
        quit()        

    # Commit tarball to upstream branch and tag.
    printMsg("Importing tarball to upstream branch: <$upstreamBranch>")

    # Check if gpg key is set.
    if not gpgKeyId:
        printMsg("Your gpg key id is not set in your gbp-helper.conf," + \
                     " disabling tag signing.", 1)
        try:
            execCmd(["gbp", "import-orig", "--merge", "--no-interactive", \
                        "--debian-branch=" + conf['debianBranch'], \
                        "--upstream-branch=" + conf['upstreamBranch'], tarPath])
        except CommandError as e:
            printMsg(e.msg, 1)
            quit()        
    else:
        try:
            execCmd(["gbp", "import-orig", "--merge", "--no-interactive", \
                        "--sign-tags", "--keyid=" + conf['gpgKeyId'], \
                        "--debian-branch=" + conf['debianBranch'], \
                        "--upstream-branch=" + conf['upstreamBranch'], tarPath])
        except CommandError as e:
            printMsg(e.msg, 1)
            quit()        

    # Cleanup.git status
    printMsg("Cleaning up")
    remove_dir(tmpPath)

# Test build.
if args.test_build:
    
    # Prepare build.
    prepare_build(conf)

    # Build and without tagging and do linthian checks.
    printMsg("Building debian package")
    try:
        execCmd(["gbp", "buildpackage", "--git-debian-branch=" + conf['debianBranch'], \
                    "--git-upstream-branch=" + conf['upstreamBranch'], \
                    "--git-export-dir=" + BUILD_DIR, "--git-ignore-new", \
                    "--git-builder=\"debuild -S\"", "--git-postbuild=\'echo " + \
                        "\"Running Lintian...\"\' && lintian -I " + \
                        "$GBP_CHANGES_FILE && echo \"Lintian OK\""])
    except CommandError as e:
        printMsg(e.msg, 1)
        quit()        

# Commit build.
if args.commit_build:
    
    # Prepare build.
    prepare_build(conf)

    # Build and tag the latest debian branch commit and do linthian checks.
    printMsg("Building debian package and tagging")
    
     # Check if gpg key is set.
    if not conf['gpgKeyId']:
        printMsg("Your gpg key id is not set in your gbp-helper.conf, disabling tag signing.", 1)
        try:
            execCmd(["gbp", "buildpackage", "--git-tag", \
                        "--git-debian-branch=" + conf['debianBranch'], \
                        "--git-upstream-branch=" + conf['upstreamBranch'], \
                        "--git-export-dir=" + BUILD_DIR, "--git-ignore-new", \
                        "--git-builder=\"debuild -S\"", "--git-postbuild=\'echo " + \
                            "\"Running Lintian...\"\' && lintian -I " + \
                            "$GBP_CHANGES_FILE && echo \"Lintian OK\""])
        except CommandError as e:
            printMsg(e.msg, 1)
            quit()
            
    else:
        try:
            execCmd(["gbp", "buildpackage", "--git-tag", "--git-sign-tags", \
                        "--git-keyid=" + conf['gpgKeyId'], \
                        "--git-debian-branch=" + conf['debianBranch'], \
                        "--git-upstream-branch=" + conf['upstreamBranch'], \
                        "--git-export-dir=" + BUILD_DIR, "--git-ignore-new", \
                        "--git-builder=\"debuild -S\"", "--git-postbuild=\'echo " + \
                            "\"Running Lintian...\"\' && lintian -I " + \
                            "$GBP_CHANGES_FILE && echo \"Lintian OK\""])
        except CommandError as e:
            printMsg(e.msg, 1)
            quit()

######################### Errors / Exceptions ###########################
#########################################################################

class Error(Exception):
    """Base class for exceptions in this module."""
    pass

class CommandError(Error):
    """Error raised when executing a shell command.

    Attributes:
        expr -- input expression in which the error occurred
        msg  -- explanation of the error
    """

    def __init__(self, expr, msg):
        self.expr = expr
        self.msg = msg

class GitError(Error):
    """Error raised for git operations.

    Attributes:
        expr -- input expression in which the error occurred
        msg  -- explanation of the error
    """

    def __init__(self, expr, msg):
        self.expr = expr
        self.msg = msg
