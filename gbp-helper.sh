#!/bin/sh -e

version="0.1"

########################## Argument Parsing #############################
#########################################################################

commitRelease=false    
testBuild=false
commitBuild=false
undoCommitRelease=false
createConfig=false
showHelp=false
showVersion=false
configPath="./gbp-helper.conf"
masterBranch="master"

while getopts ":rtbp:ehv" opt; do
    case $opt in
        r)
            echo "Commit release enabled" >&2
            commitRelease=true    
            ;;
        t)
            echo "Test build enabled" >&2
            testBuild=true
            ;;
        b)
            echo "Commit build enabled" >&2
            commitBuild=true
            ;;
        u)
            echo "Undo commit release enabled" >&2
            undoCommitRelease=true
            ;;
        p)
            echo "Config path is set to: $OPTARG"
            configPath=$OPTARG
            ;;
        e)
            createConfig=true
            ;;
        h)
            showHelp=true
            ;;
        v)
            showVersion=true
            ;;
        \?)
            echo "Invalid option: -$OPTARG" >&2
            exit 1
            ;;
        :)
            echo "Option -$OPTARG requires an argument." >&2
            exit 1
            ;;
    esac
done

# Check for optional path argument.
pathArg=$(eval "echo \$$OPTIND")
if [ "" != "$pathArg" ]; then
    # Change directory before running commands.
    cd $pathArg >/dev/null 2>&1 || \
        (echo "Please give a proper path as optional argument"; exit 1)
fi


############################ Build Tools ################################
#########################################################################
### This section defines functions useful for buil operations.
### If a failure occurs it will terminate with error messages.
#########################################################################

## Functions

# Checks if the current directory is a git repository.
# Returns 1 if an error occured and prints message.
is_git_rep () {
    (git status >/dev/null 2>&1 && return 0) || \
        (echo "Error: The current directory is not a git repository"; \
        echo "Please make sure that the script is given the proper path"; return 1)
}

# Switches to git branch:
# $1=branch_name
# Returns 1 if an error occured and prints message.
switch_branch () {
    # Verify that the current dir is agit repository.
    is_git_rep || return 1
    
    # Try to switch branch.
    (git checkout $1 >/dev/null 2>&1 && return 0) || \
        (echo "Error: Could not switch to branch: <$1>"; \
        echo "Please make sure that the branch <$1> exists and all changes are commited"; return 1)
}

# Check for tags for the latest commit (HEAD):
# $1=branch_name
# Returns 1 if an error occured or no tags exist and prints message.
check_head_tags () {
    switch_branch $1 || return 1
    local latestTags=$(git tag --points-at HEAD)
    ([ ! -z $latestTags ] && return 0) || \
        (echo "Error: The latest commit on branch <$1> has no tags"; return 1)
}

# Retrives all tags for the latest commit (HEAD):
# $1=branch_name
get_head_tags () {
    switch_branch $1 || return 0
    local latestTags=$(git tag --points-at HEAD)
    [ ! -z $latestTags ] && echo $latestTags
}

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

# Retrives the latest tag version (for tags: <tag_type>/<version>) for a branch: 
# $1=branch_name $2=tag_type
get_tag () {
    # Get the latest tags.
    check_head_tags $1 || return 1
    local latestTags=$(get_head_tags $1)
    
    # Make sure atleast some tag follows the right format.
    local matchingTags=$(echo $latestTags | grep -Eo -m 1 "^$2/[0-9.]*$")
    
    # Check if empty.
    ([ ! -z $matchingTags ] && (echo $matchingTag; return 0)) || \
        (echo "Error: The latest commit on branch <$1> has no properly formatted tags"; \
        echo "Please properly tag your latest <$1> commit as: $2/<version>"; return 1)
}

# Retrives the latest tag version (for tags: <tag_type>/<version>) for a branch: 
# $1=branch_name $2=tag_type
get_tag_version () {
    # Get the latest tags.
    check_head_tags $1 || return 1
    local latestTags=$(get_head_tags $1)
    
    # Make sure atleast some tag follows the right format.
    local matchingTags=$(echo $latestTags | grep -Eo "^$2/[0-9.]*$")
    local tagVersion=$(echo $matchingTags | grep -Eo -m 1 "[0-9.]*$")
    
    # Check if empty.
    ([ ! -z $matchingTags ] && [ ! -z $tagVersion ] && (echo $tagVersion; return 0)) || \
        (echo "Error: The latest commit on branch <$1> has no properly formatted tags"; \
        echo "Please properly tag your latest <$1> commit as: $2/<version>"; return 1)
}

# Checks whether the first version string is greater than or equal to the second: 
# $1=first_version $2=second_version
is_version_lte () {
    [ "$1" = "`echo -e "$1\n$2" | sort -V | head -n1`" ]
}

# Checks whether the first version string is greater than the second: 
# $1=first_version $2=second_version
is_version_lt () {
    [ "$1" = "$2" ] && return 1 || return is_version_lte $1 $2
}

# Cleans or if not existant creates it: 
# $1=dir_path
clean_dir () {
    echo "Cleaning build directory: $1"
    if [ -d "$1" ]; then
        # Clean old build files.
        rm -r "$1"
    fi
    mkdir -p $1
}

# Cleans the default build directory and switches to the release branch:
# No args 
prepare_build () {
    # Make sure we are on the debian branch.
    echo "Switching to debian branch: <$debianBranch>"
    switch_branch $debianBranch

    echo "Cleaning old build"
    clean_dir $buildDir
}

# Creates an example gbp-helper.conf file.
# $1=config_path
create_ex_config () {
    # Make sure file does not exist.
    if [ -e "$1" ]; then
        echo "$1 exists and will not be replaced by an example file"
        return 0
    fi

    # Create the example file.
    echo "Creating example config file"
    echo "## gbp-helper.conf: $(basename $(pwd))\n"\
"releaseBranch=master\nreleaseTagType=release\n\n"\
"debianBranch=debian\ndebianTagType=debian\n\n"\
"upstreamBranch=upstream\nupstreamTagType=upstream\n\ngpgKeyId="\
 > $1
}

# Update the config variables.
# $1=config_path
update_config_vars () {
    echo "Reading config file"
    # Switch branch to master before trying to read config.
    switch_branch $masterBranch
    eval $(sed '/=/!d;/^ *#/d;s/=/ /;' < "$1" | while read -r key val
    do
        str="$key='$val'"
        echo "$str"
    done)
}

# Updates standard global build variables (release version, package name etc.) and
# values from config file.
# After a successful run it will have (besides setting the variables):
#   - Ensured that the current dir is a git repository.
#   - Switched to the release branch.
#   - Ensured that the latest release commit is propperly tagged.
update_build_vars () {
    # Update from config.    
    update_config_vars $configPath

    echo "Setting build variables"
    # Get package name from repository name (parent dir name).
    packageName=$(basename $(pwd))

    # Set build paths.
    tmpPath="/tmp/$packageName"
    buildDir="../build-area"
}


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

# Undo commit release (-u)
if [ $undoCommitRelease = true ]; then #TODO
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
    gbp import-orig --merge --no-interactive --sign-tags --keyid=$gpgKeyId \
        --debian-branch=$debianBranch --upstream-branch=$upstreamBranch $tarPath

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
      --git-export-dir=$buildDir --git-ignore-new \
      --git-postbuild='echo "Running Lintian..."' && lintian -I $GBP_CHANGES_FILE && echo "Lintian OK"
fi

# Commit build (-c)
if [ $commitBuild = true ]; then
    # Update the build variables.
    update_build_vars
    
    # Prepare build.
    prepare_build

    # Build and tag the latest debian branch commit and do linthian checks.
    echo "Building debian package and tagging"
    gbp buildpackage --git-tag  --git-sign-tags --git-keyid=$gpgKeyId \
      --git-debian-branch=$debianBranch --git-upstream-branch=$upstreamBranch \
      --git-export-dir=$buildDir \
      --git-postbuild='echo "Running Lintian..."' && lintian -I $GBP_CHANGES_FILE && echo "Lintian OK"
fi

exit 0
