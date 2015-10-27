#!/bin/env python

import argparse
import os

__version__ = "0.2"

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
parser.add_argument('--create-config', '-e', action='store_true', \
    help='creates an example gbp-helper.conf file')
parser.add_argument('--config', \
    help='path to the gbp-helper.conf file')
parser.add_argument('--config', \
    help='path to the gbp-helper.conf file')
parser.add_argument('dir', nargs='?', default=os.getcwd())
    
args = parser.parse_args()

## Constants
configPath = "./gbp-helper.conf"
masterBranch = "master"

############################ Build Tools ################################
#########################################################################
### This section defines functions useful for buil operations.
### If a failure occurs it will terminate with error messages.
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
    if git status >/dev/null 2>&1 && return 0):
        print "Error: The current directory is not a git repository"; \
        print "Please make sure that the script is given the proper path"; return 1)

# Switches to git branch:
# $1=branch_name
# Returns 1 if an error occured and prints message.
def switch_branch (): #TODO
    # Verify that the current dir is agit repository.
    is_git_rep || return 1
    
    # Try to switch branch.
    (git checkout $1 >/dev/null 2>&1 && return 0) || \
        (echo "Error: Could not switch to branch: <$1>"; \
        echo "Please make sure that the branch <$1> exists and all changes are commited"; return 1)

# Retrives the tags for the latest commit (HEAD):
# $1=branch_name
# Returns 1 if an error occured or no tags exist and prints message.
def get_head_tags (): #TODO
    switch_branch $1 || return 1
    local headTags=$(git tag --points-at HEAD)
    ([ ! -z $headTags ] && return 0) || \
        (echo "Error: The latest commit on branch <$1> has no tags"; return 1)

############################## TODO ###################################
# Retrives the latest tag:
# $1=branch_name
#get_latest_tag () {
#   git describe --abbrev=0 --tags
#    
#    switch_branch $1 || return 0
#    local latestTags=$(git tag --points-at HEAD)
#    [ ! -z $latestTags ] && echo $latestTags
#}
############################## TODO ###################################

# Retrives the HEAD tag version (for tags: <tag_type>/<version>) for a branch: 
# $1=branch_name $2=tag_type
def get_tag (): #TODO
    # Get the latest tags.
    headTags=$(get_head_tags $1)
    
    # Make sure atleast some tag follows the right format.
    matchingTag=$(echo $headTags | grep -Eo -m 1 "^$2/.*$")
    
    # Check if empty.
    ([ ! -z $matchingTag ] && (echo $matchingTag; return 0)) || \
        (echo "Error: The latest commit on branch <$1> has no properly formatted tags"; \
        echo "Please properly tag your latest <$1> commit as: $2/<version>"; return 1)

# Retrives the HEAD tag version (for tags: <tag_type>/<version>) for a branch: 
# $1=branch_name $2=tag_type
def get_tag_version: #TODO
    # Get the latest tags.
    headTags=$(get_head_tags $1) || return 1
    
    # Make sure atleast some tag follows the right format.
    tagVersion=$(echo $headTags | grep -Po -m 1 "(?<=$2/).*")

    # Check if empty.
    ([ ! -z $tagVersion ] && (echo $tagVersion; return 0)) || \
        (echo "Error: The latest commit on branch <$1> has no properly formatted tags"; \
        echo "Please properly tag your latest <$1> commit as: $2/<version>"; return 1)

# Checks whether the first version string is greater than or equal to the second: 
# $1=first_version $2=second_version
def is_version_lte ():  #TODO
    [ "$1" = "`echo -e "$1\n$2" | sort -V | head -n1`" ]

# Checks whether the first version string is greater than the second: 
# $1=first_version $2=second_version
def is_version_lt ():  #TODO
    [ "$1" = "$2" ] && return 1 || return is_version_lte $1 $2

# Cleans or if not existant creates it: 
# $1=dir_path
def clean_dir (): #TODO
    echo "Cleaning build directory: $1"
    if [ -d "$1" ]; then
        # Clean old build files.
        rm -r "$1"
    fi
    mkdir -p $1

# Cleans the default build directory and switches to the release branch:
# No args 
def prepare_build ():  #TODO
    # Make sure we are on the debian branch.
    echo "Switching to debian branch: <$debianBranch>"
    switch_branch $debianBranch

    echo "Cleaning old build"
    clean_dir $buildDir

ex_config = 
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

# Creates an example gbp-helper.conf file.
# $1=config_path
def create_ex_config: #TODO
    # Make sure file does not exist.
    if [ -e "$1" ]; then
        echo "$1 exists and will not be replaced by an example file"
        return 0
    fi

    # Create the example file.
    echo "Creating example config file"

# Asks for user confirmation [y/N].
# $1=prompt
def prompt_user_yn: #TODO
    read -r -p "$1 [y/N] " response
    case $response in
        [yY][eE][sS]|[yY]) 
            return 0
            ;;
        *)
            return 1
            ;;
    esac

# Update the config variables.
# $1=config_path
def update_config_vars(): #TODO
    echo "Reading config file"
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

    echo "Setting build variables"
    # Get package name from repository name (parent dir name).
    packageName=$(basename $(pwd))

    # Set build paths.
    tmpPath="/tmp/$packageName"
    buildDir="../build-area"


######################### Command Execution #############################
#########################################################################

## Run the selected commands.

# Show help menu (manpage) (-h)
if [ $showHelp = true ]; then
    man gbp-helper
    # Always exit after help menu.
    exit 0
fi

# Show version (-v)
if [ $showVersion = true ]; then
    echo $version
    # Always exit after showing version.
    exit 0
fi

# Create example config (-e)
if [ $createConfig = true ]; then
    create_ex_config $configPath
    # Always exit after creation.
    exit 0
fi

# Undo commit release (-z)
if [ $undoCommitRelease = true ]; then #TODO
    # Ask user for confirmation.
    prompt_user_yn "Do you really want to undo the latest release commit?" || exit 0

    # Update the build variables.
    update_build_vars
    
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
    exit 0
fi

# Upload latest build (-u)
if [ $uploadBuild = true ]; then #TODO
    # Ask user for confirmation
    prompt_user_yn "Upload the latest build?" || exit 0

    # Update the build variables.
    update_build_vars
    
    # Check if ppa name is set in config.
    if [ "$ppaName" = "" ]; then
        echo "Your ppa name is not set in your gbp-helper.conf, aborting upload"
        exit 1
    fi

    # Make sure that the latest debian commit is tagged.
    debianTagVersion=get_tag_version "debian" $debianTagType ||
        (echo $debianTagVersion; \
        echo "The latest debian commit isn't porperly tagged, run gbp-helper -b"; exit 1)

    # Set the name of the .changes file and upload.
    #dput "ppa:$ppaName" "../build-area/$packageName_$debianTagVersion_source.changes"
    echo "ppa:$ppaName ../build-area/$packageName_$debianTagVersion_source.changes"
    
    # Always exit after creation.
    exit 0
fi

# Commit release (-r)
if [ $commitRelease = true ]; then
    # Update the build variables.
    update_build_vars

    # Constants
    echo "Setting sourcedir"
    sourceDirName="$packageName-$releaseVersion"
    sourceDirPath="$tmpPath/$sourceDirName"
    tarPath="$tmpPath/${packageName}_${releaseVersion}.orig.tar.gz"
    
    # Get the tagged version from the release branch.
    releaseVersion=$(get_tag_version $releaseBranch $releaseTagType) || \
    	(echo $releaseVersion; exit 1)

    # Check that the release version is greater than the upstream version.
    upstreamVersion=$(get_tag_version $upstreamBranch $upstreamTagType) && \
    	is_version_lte $releaseVersion $upstreamVersion && \
            (echo "Error: Release version is less than upstream version, aborting"; exit 1) || \
                (echo $upstreamVersion; echo "No upstream version detected, asuming 0"; exit 0)

    # Clean build directory.
    clean_dir $tmpPath
    mkdir $sourceDirPath

    # Extract the latest commit to release branch.
    echo "Extracting latest commit from release branch: <$releaseBranch>"
    git archive $releaseBranch | tar -x -C $sourceDirPath \
      --exclude='gbp-helper.conf' --exclude='README.md' --exclude='LICENSE' \
      --exclude-vcs

    # Create the upstream tarball.
    echo "Making upstream tarball from release branch: <$releaseBranch>"
    tar -C $tmpPath -czf $tarPath $sourceDirName
    
    # Commit tarball to upstream branch and tag.
    echo "Importing tarball to upstream branch: <$upstreamBranch>"

    # Check if gpg key is set.
    if [ "$gpgKeyId" = "" ]; then
        echo "Your gpg key id is not set in your gbp-helper.conf, disabling tag signing."
        gbp import-orig --merge --no-interactive \
            --debian-branch=$debianBranch --upstream-branch=$upstreamBranch $tarPath
    else
        gbp import-orig --merge --no-interactive --sign-tags --keyid=$gpgKeyId \
            --debian-branch=$debianBranch --upstream-branch=$upstreamBranch $tarPath
    fi

    # Cleanup.git status
    echo "Cleaning up"
    rm -r $tmpPath
fi

# Test build (-t)
if [ $testBuild = true ]; then
    # Update the build variables.
    update_build_vars
    
    # Prepare build.
    prepare_build

    # Build and without tagging and do linthian checks.
    echo "Building debian package"
    gbp buildpackage --git-debian-branch=$debianBranch --git-upstream-branch=$upstreamBranch \
      --git-export-dir=$buildDir --git-ignore-new --git-builder="debuild -S" \
      --git-postbuild='echo "Running Lintian..."' && lintian -I $GBP_CHANGES_FILE && echo "Lintian OK"
fi

# Commit build (-b)
if [ $commitBuild = true ]; then
    # Update the build variables.
    update_build_vars
    
    # Prepare build.
    prepare_build

    # Build and tag the latest debian branch commit and do linthian checks.
    echo "Building debian package and tagging"
    
     # Check if gpg key is set.
    if [ "$gpgKeyId" = "" ]; then
        echo "Your gpg key id is not set in your gbp-helper.conf, disabling tag signing."
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
    fi
fi

# Exit cleanly.
exit 0
