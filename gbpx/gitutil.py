"""
gitutil module:
Contains various io functions for git.
No functions will print any progress messages.
If a failure occurs functions will terminate with GitError.
"""
from os import getcwd
from re import findall, match

from gbpxargs import Flag
from ioutil import Error, log, TextType, exec_cmd, CommandError


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

    def log(self, flags):
        """ Log the error """
        if self.opr is not None:
            log(flags, ("The git command \'" + self.opr + "\' failed\n"
                        if self.opr is not None else "") + self.msg,
                TextType.ERR)
        else:
            log(flags, self.msg, TextType.ERR)


def check_git_rep():
    """
    Checks if the current directory is a git repository.
    Errors will be raised as GitError (if not a rep).
    """
    try:
        exec_cmd(["git", "status"])
    except CommandError:
        raise GitError(getcwd() + " is not a git repository", "status")


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
        raise GitError("Please make sure that the branch \'" +
                       branch + "\' exists and all changes " +
                       "are commited", "checkout")


def get_head_tags(branch, tag_type):
    """
    Retrieves the tags for the HEAD commit on form (<tag_type>/<version>).
    Errors will be raised as GitError (underlying errors).
    Returns the list of HEAD tags for the given branch (can be empty).
    """
    switch_branch(branch)
    try:
        # Get all tags at HEAD.
        head_tags = exec_cmd(["git", "tag", "--points-at", "HEAD"])
        # Find the matching tags.
        matching_tags = findall(r"(?m)^" + tag_type + r"/.*$", head_tags)
        return matching_tags
    except CommandError:
        raise GitError("The tags pointing at \'" + branch +
                       "\' HEAD, could not be retrieved", "tag")


def get_head_tag(branch, tag_type):
    """
    Retrieves the latest HEAD tag (<tag_type>/<version>) for a branch.
    Errors will be raised as GitError (underlying errors).
    Returns the name of the latest tag (largest version number).
    """
    # Get the latest HEAD tags.
    head_tags = get_head_tags(branch, tag_type)

    # Make sure at least some tag follows the right format.
    if head_tags:
        # Find the "latest tag"
        # Assuming std format: <tag_type>/<version>(-<deb_version>)
        head_tags.sort(key=lambda s: [int(v) for v in
                                      s.split('/')[1].split('-')[0].split('.')])
        return head_tags[0]
    else:
        raise GitError("The HEAD on branch \'" + branch +
                       "\' has no tags of type: " + tag_type + "/<version>")


def get_latest_tag(branch, tag_type):
    """
    Retrieves the latest tag (<tag_type>/<version>) for a branch.
    Errors will be raised as GitError (underlying errors or if no tags exists).
    """
    # Get the latest tag.
    switch_branch(branch)
    try:
        return exec_cmd(["git", "describe", "--abbrev=0", "--tags",
                         "--match", tag_type + "/*"])
    except CommandError:
        raise GitError("The branch \'" + branch +
                       "\' has no tags of type: " +
                       tag_type + "/<version>")


def get_version_from_tag(tag, tag_type):
    """
    Extracts the version string from a tag (<tag_type>/<version>).
    Errors will be raised as GitError.
    """
    # Get the version part of the tag.
    tag_ver = match(r"^" + tag_type + r"/(.*$)", tag)
    if tag_ver is not None:
        return tag_ver.group(1)
    else:
        raise GitError("A tag version could not be extracted from tag " +
                       "\'" + tag + "\'")


def get_head_tag_version(branch, tag_type):
    """
    Retrieves the HEAD tag version (<tag_type>/<version>) for a branch.
    Errors will be raised as GitError,
    (underlying errors or if no correct tags exists).
    """
    # Get the latest HEAD tag.
    head_tag = get_head_tag(branch, tag_type)
    return get_version_from_tag(head_tag, tag_type)


def get_latest_tag_version(branch, tag_type):
    """
    Retrieves latest tag version (<tag_type>/<version>) for a branch.
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
    ver_s.sort(key=lambda s: findall(r'''\d+''', s))
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
        raise GitError("Could not determine if working directory is clean.",
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
        raise GitError("Could not find the name of the current branch",
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
        raise GitError("Could not find HEAD commit of branch \'" +
                       branch + "\'", "rev-parse")


## Affecting repository / files.

def init_repository(flags, dir_path):
    """
    Initiate a git repository.
        :param flags:
        :type flags: dict
        :param dir_path: path of the repository to initiate
        :type dir_path: str
        :raises: GitError
    """
    try:
        if not flags[Flag.SAFEMODE]:
            exec_cmd(["git", "init", dir_path])
    except CommandError:
        raise GitError("Could not initiate repository \'{}\' ".format(dir_path))


def create_branch(flags, branch):
    """
    Create a branch from the current.
        :param flags:
        :type flags: dict
        :param branch: the branch to create
        :type branch: str
        :raises: GitError
    """
    try:
        if not flags[Flag.SAFEMODE]:
            exec_cmd(["git", "branch", branch])
    except CommandError:
        raise GitError("Could not create branch \'{}\' ".format(branch))


def reset_branch(flags, branch, commit):
    """
    Resets the given branch to the given commit, (accepts HEAD as commit).
    Errors will be raised as GitError.
    """
    switch_branch(branch)
    try:
        if not flags[Flag.SAFEMODE]:
            exec_cmd(["git", "reset", "--hard", commit])
    except CommandError:
        raise GitError("Could not reset branch \'" + branch + "\' " +
                       "to commit \'" + commit + "\'")


def commit_changes(flags, msg):
    """
    Commits all changes for the current branch.
    Errors will be raised as GitError.
    """
    check_git_rep()
    try:
        if not flags[Flag.SAFEMODE]:
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
        if not flags[Flag.SAFEMODE]:
            if name is not None:
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
        if not flags[Flag.SAFEMODE]:
            if name is not None:
                exec_cmd(["git", "stash", "apply", "stash^{/\"" +
                          name + "\"}"])
                if drop:
                    exec_cmd(["git", "stash", "drop", "stash^{/\"" +
                              name + "\"}"])
            else:
                exec_cmd(["git", "stash", "apply"])
                if drop:
                    exec_cmd(["git", "stash", "drop"])

    except CommandError:
        raise GitError("Could not apply stashed changes" +
                       (" (" + name + ")" if name is not None else ""), "stash")


def delete_tag(flags, tag):
    """
    Deletes the given tag.
    Errors will be raised as GitError.
    """
    check_git_rep()
    try:
        if not flags[Flag.SAFEMODE]:
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
        if not flags[Flag.SAFEMODE]:
            exec_cmd(["git", "tag", tag])
    except CommandError:
        raise GitError("The tag \'" + tag + "\' could not be created " +
                       "and may already exist", "tag")


def clean_repository(flags):
    """ Cleans untracked files and files matched by a .gitignore file. """
    try:
        if not flags[Flag.SAFEMODE]:
            exec_cmd(["git", "clean", "-fd"])
            exec_cmd(["git", "clean", "-fX"])
    except CommandError:
        raise GitError("Could not clean ignored files", "clean")


def get_rep_name_from_url(url):
    """ Extracts a git repository name from a remote URL. """
    match_ = match(r'''(?i)^.*/(.*)\.git$''', url)
    if match_ is not None:
        return match_.group(1)
    else:
        return None
