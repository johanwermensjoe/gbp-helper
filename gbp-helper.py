#!/bin/env python

import argparse
import os
import shutil
import re

__version__ = "0.2"

## Constants
DEFAULT_CONFIG_PATH = "./gbp-helper.conf"
MASTER_BRANCH = "master"
EX_CONFIG = 
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

########################## Argument Parsing #############################
#########################################################################


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

############################ Build Tools ################################
#########################################################################
### This section defines functions useful for buil operations.
### If a failure occurs it will terminate with exeptions.
#########################################################################

## Functions

# Prints log messages depending on verbose flag and priority.
# Default priority is 0 which only prints if verbose, 1 always prints.
def printMsg(msg, priority=0):
    if priority > 1 or args.verbose:
        print msg

# Checks if the current directory is a git repository.
# Returns 1 if an error occured and prints message.
def is_git_rep(): #TODO
    try:
        git status >/dev/null 2>&1
        return True
    except:
        return False

# Switches to git branch:
# Returns 1 if an error occured and prints message.
def switch_branch(branchName):
    # Verify that the current dir is a git repository.
    if is_git_rep():
        # Try to switch branch.
        try:
            (git checkout $1 >/dev/null 2>&1 && return 0) #TODO
        except:
            raise Exception(branchName, "Please make sure that the branch " \
                                        "<" + branchName + "> exists and all changes are commited"
    else:
        raise Exception(pwd + " or " + arg.dir, \
                            "The current directory is not a git repository")

# Retrives the tags for the latest commit (HEAD):
# Returns 1 if an error occured or no tags exist and prints message.
def get_head_tags(branchName):
    switch_branch(branchName)
    headTags=$(git tag --points-at HEAD) #TODO
    
    # Check that some tags exists.    
    if not headTags:
        raise Exception(branchName, "The HEAD on branch <$1> has no tags")
    
    return headTags

# Retrives the latest HEAD tag (for tags: <tag_type>/<version>) for a branch. 
def get_head_tag(branchName, tagType):
    # Get the latest HEAD tags.
    headTags = get_head_tags(branchName)
        
    # Find the matching tags.
    matchingTags = re.match(r'''^tagType/*$''', headTags) #TODO multiline?

    # Make sure atleast some tag follows the right format.
    if matchingTags:
        # Find the "latest tag". #TODO
    else:
        raise Exception(headTags, "The HEAD on branch \'" + branchName + \
                            "\' has no tags of type: " tagType + "/<version>")

# Retrives the HEAD tag version (for tags: <tag_type>/<version>) for a branch: 
def get_tag_version(branchName, tagType):
    # Get the latest HEAD tag.
    headTag = get_head_tag(branchName, tagType) #TODO
    
    # Get the version part of the tag.
    tagVersion = re.match(r'''^tagType/(*$)''', headTag) #TODO

    if tagVersion:
        return tagVersion
    else:
        raise Exception(headTag, "A tag version could not be extracted")

# Checks whether the first version string is greater than or equal to the second: 
def is_version_lte(v1, v2):  #TODO
    [ "$1" = "`echo -e "$1\n$2" | sort -V | head -n1`" ]

# Checks whether the first version string is greater than the second.
def is_version_lt(v1, v2):  #TODO
    [ "$1" = "$2" ] && return 1 || return is_version_lte $1 $2

# Cleans or if not existant creates a directory.
def clean_dir(dirPath):
    remove_dir(dirPath)
    os.makedirs(dirPath)    

# Removes a directory.
def remove_dir(dirPath):
    if os.path.isdir(dirPath):
        # Remove directory recursively.
        shutil.rmtree(dirPath)

# Cleans the default build directory and switches to the release branch.
def prepare_build():
    # Make sure we are on the debian branch.
    printMsg("Switching to debian branch: <$debianBranch>")
    switch_branch(debianBranch)

    printMsg("Cleaning old build")
    clean_dir(buildDir)

# Creates an example gbp-helper.conf file.
def create_ex_config(configPath):
    # Make sure file does not exist.
    if os.path.exists(configPath):
        printMsg(configPath + " exists and will not be replaced by an example file", 1)
    else:
        # Create the example file.
        printMsg("Creating example config file")
        try:
            file = open(configPath, "w")
            file.write(EX_CONFIG)
            file.close()
        except IOError as e:
            printMsg("I/O error({0}): {1}".format(e.errno, e.strerror), 1)
            

# Asks for user confirmation [y/N].
def prompt_user_yn(promptMsg): #TODO
    read -r -p promptMsg + " [y/N] " response
    case $response in
        [yY][eE][sS]|[yY]) 
            return 0
            ;;
        *)
            return 1
            ;;
    esac

# Update the config variables.
def update_config_vars(configPath): #TODO
    printMsg("Reading config file")
    # Switch branch to master before trying to read config.
    switch_branch $masterBranch
    eval $(sed '/=/!d;/^ *#/d;s/=/ /;' < "$1" | while read -r key val
    do
        str="$key='$val'"
        echo "$str"
    done)

# Updates standard global build variables (release version, package name etc.) and
# values from config file.
# After a successful run it will have (besides setting the variables):
#   - Ensured that the current dir is a git repository.
#   - Switched to the release branch.
#   - Ensured that the latest release commit is propperly tagged.
def update_build_vars(): #TODO
    # Update from config.    
    update_config_vars $configPath

    printMsg("Setting build variables")
    # Get package name from repository name (parent dir name).
    packageName=$(basename $(pwd))

    # Set build paths.
    tmpPath="/tmp/" + packageName
    buildDir="../build-area"


######################### Command Execution #############################
#########################################################################

## Run the selected commands.

# Show version.
if args.version:
    printMsg(__version__, 1)
    # Always exit after showing version.
    quit()

# Create example config.
if args.create_config: #TODO
    create_ex_config $configPath
    # Always exit after config creation.
    quit()

# Undo commit release.
if args.undo_release: #TODO
    # Ask user for confirmation.
    prompt_user_yn("Do you really want to undo the latest release commit?") or quit()

    # Update the build variables.
    update_build_vars()
    
    # Find out what the latest merge commit between upstream and debian branches.
    
    # Reset debian to the previous commit to the merge.
    switch_branch $debianBranch
    git reset --hard HEAD~1
    
    # Reset upstream to the previous commit to its HEAD.
    upstreamTag=get_tag $upstreamBranch $upstreamTagType
    switch_branch $upstreamBranch
    git reset --hard HEAD~1
    git tag -d $upstreamTag
    
    # Always exit after creation.
    quit()

# Upload latest build.
if args.upload_build: #TODO
    # Ask user for confirmation
    prompt_user_yn("Upload the latest build?") or quit()

    # Update the build variables.
    update_build_vars()
    
    # Check if ppa name is set in config.
    if not ppaName:
        printMsg("Your ppa name is not set in your gbp-helper.conf, aborting upload", 1)
        quit()

    # Make sure that the latest debian commit is tagged.
    debianTagVersion=get_tag_version "debian" $debianTagType ||
        echo $debianTagVersion
        printMsg("The latest debian commit isn't porperly tagged, run gbp-helper -b", 1)
        quit

    # Set the name of the .changes file and upload.
    dput "ppa:" + ppaName + " ../build-area/" + packageName + "_" + \
        debianTagVersion + "_source.changes"
    
    # Always exit after creation.
    quit()

# Commit release.
if args.commit_release: #TODO
    # Update the build variables.
    update_build_vars()

    # Constants
    printMsg("Setting sourcedir")
    sourceDirName = packageName + "-" + releaseVersion
    sourceDirPath = os.path.join(tmpPath, sourceDirName)s
    tarPath = os.path.join(tmpPath, packageName + "_" + releaseVersion + ".orig.tar.gz")
    
    # Get the tagged version from the release branch.
    releaseVersion = get_tag_version(releaseBranch, releaseTagType) ||
    	(echo $releaseVersion; exit 1)

    # Check that the release version is greater than the upstream version.
    upstreamVersion = get_tag_version(upstreamBranch, upstreamTagType) && 
    	is_version_lte(releaseVersion, upstreamVersion) && 
            (printMsg("Error: Release version is less than upstream version, aborting", 1); quit()) || \
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
      --git-export-dir=$buildDir --git-ignore-new --git-builder="debuild -S" \
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
            --git-export-dir=$buildDir --git-builder="debuild -S" \
            --git-postbuild='echo "Running Lintian..."' \
                && lintian -I $GBP_CHANGES_FILE && echo "Lintian OK"
    else
        gbp buildpackage --git-tag  --git-sign-tags --git-keyid=$gpgKeyId \
            --git-debian-branch=$debianBranch --git-upstream-branch=$upstreamBranch \
            --git-export-dir=$buildDir --git-builder="debuild -S" \
            --git-postbuild='echo "Running Lintian..."' \
                && lintian -I $GBP_CHANGES_FILE && echo "Lintian OK"
