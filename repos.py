#!/usr/bin/env python3
#
# Copyright (C) 2011-2015  Codethink Limited
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; version 2 of the License.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License along
# with this program; if not, write to the Free Software Foundation, Inc.,
# 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.
#
# =*= License: GPL-2 =*=

import os
import app
import re
from subprocess import call
from subprocess import check_output
import string
import definitions
import urllib2
import json
import utils
import ConfigParser
import StringIO
import re


def get_repo_url(repo):
    url = repo.replace('upstream:', 'git://git.baserock.org/delta/')
    url = url.replace('baserock:baserock/',
                      'git://git.baserock.org/baserock/baserock/')
    url = url.replace('freedesktop:', 'git://anongit.freedesktop.org/')
    url = url.replace('github:', 'git://github.com/')
    url = url.replace('gnome:', 'git://git.gnome.org')
    if url.endswith('.git'):
        url = url[:-4]
    return url


def get_repo_name(repo):
    ''' Convert URIs to strings that only contain digits, letters, _ and %.

    NOTE: When changing the code of this function, make sure to also apply
    the same to the quote_url() function of lorry. Otherwise the git tarballs
    generated by lorry may no longer be found by morph.

    '''
    valid_chars = string.digits + string.ascii_letters + '%_'
    transl = lambda x: x if x in valid_chars else '_'
    return ''.join([transl(x) for x in get_repo_url(repo)])


def get_upstream_version(repo, ref):
    try:
        gitdir = os.path.join(app.settings['gits'], get_repo_name(repo))
        with app.chdir(gitdir), open(os.devnull, "w") as fnull:
            last_tag = check_output(['git', 'describe', '--abbrev=0',
                                      '--tags', ref], stderr=fnull)[0:-1]
            commits = check_output(['git', 'rev-list', last_tag + '..' + ref,
                                    '--count'])

        result = "%s (%s + %s commits)" % (ref[:8], last_tag, commits[0:-1])
    except:
        result = ref[:8] + " " + "(No tag found)"

    return result


def get_tree(this):
    ref = this['ref']
    gitdir = os.path.join(app.settings['gits'], get_repo_name(this['repo']))
    if not os.path.exists(gitdir):
        try:
            url = (app.settings['cache-server-url'] + 'repo='
                   + get_repo_url(this['repo']) + '&ref=' + ref)
            with urllib2.urlopen(url) as response:
                tree = json.loads(response.read().decode())['tree']
                return tree
        except:
            app.log(this, 'WARNING: no tree from cache-server', ref)
            mirror(this['name'], this['repo'])

    with app.chdir(gitdir), open(os.devnull, "w") as fnull:
        if call(['git', 'rev-parse', ref + '^{object}'], stdout=fnull,
                stderr=fnull):
            # can't resolve this ref. is it upstream?
            call(['git', 'fetch', 'origin'], stdout=fnull, stderr=fnull)

        try:
            tree = check_output(['git', 'rev-parse', ref + '^{tree}'],
                                universal_newlines=True)[0:-1]
            return tree

        except:
            # either we don't have a git dir, or ref is not unique
            # or ref does not exist

            app.log(this, 'ERROR: could not find tree for ref', ref)
            raise SystemExit


def copy_repo(repo, destdir):
    '''Copies a cached repository into a directory using cp.

    This also fixes up the repository afterwards, so that it can contain
    code etc.  It does not leave any given branch ready for use.

    '''

    # core.bare should be false so that git believes work trees are possible
    # we do not want the origin remote to behave as a mirror for pulls
    # we want a traditional refs/heads -> refs/remotes/origin ref mapping
    # set the origin url to the cached repo so that we can quickly clean up
    # by packing the refs, we can then edit then en-masse easily
    call(['cp', '-a', repo, os.path.join(destdir, '.git')])
    call(['git', 'config', 'core.bare', 'false'])
    call(['git', 'config', '--unset', 'remote.origin.mirror'])
    with open(os.devnull, "w") as fnull:
        call(['git', 'config', 'remote.origin.fetch',
              '+refs/heads/*:refs/remotes/origin/*'],
             stdout=fnull,
             stderr=fnull)
    call(['git',  'config', 'remote.origin.url', repo])
    call(['git',  'pack-refs', '--all', '--prune'])

    # turn refs/heads/* into refs/remotes/origin/* in the packed refs
    # so that the new copy behaves more like a traditional clone.
    with open(os.path.join(destdir, ".git", "packed-refs"), "r") as ref_fh:
        pack_lines = ref_fh.read().split("\n")
    with open(os.path.join(destdir, ".git", "packed-refs"), "w") as ref_fh:
        ref_fh.write(pack_lines.pop(0) + "\n")
        for refline in pack_lines:
            if ' refs/remotes/' in refline:
                continue
            if ' refs/heads/' in refline:
                sha, ref = refline[:40], refline[41:]
                if ref.startswith("refs/heads/"):
                    ref = "refs/remotes/origin/" + ref[11:]
                refline = "%s %s" % (sha, ref)
            ref_fh.write("%s\n" % (refline))
    # Finally run a remote update to clear up the refs ready for use.
    with open(os.devnull, "w") as fnull:
        call(['git', 'remote', 'update', 'origin', '--prune'], stdout=fnull,
             stderr=fnull)


def mirror(name, repo):
    # try tarball first
    gitdir = os.path.join(app.settings['gits'], get_repo_name(repo))
    repo_url = get_repo_url(repo)
    try:
        os.makedirs(gitdir)
        tar_file = get_repo_name(repo_url) + '.tar'
        app.log(name, 'Try fetching tarball %s' % tar_file)
        with app.chdir(gitdir), open(os.devnull, "w") as fnull:
            call(['wget', app['tar-url']], stdout=fnull, stderr=fnull)
            call(['tar', 'xf', tar_file], stdout=fnull, stderr=fnull)
            os.remove(tar_file)
            call(['git', 'config', 'remote.origin.url', repo_url],
                 stdout=fnull, stderr=fnull)
            call(['git', 'config', 'remote.origin.mirror', 'true'],
                 stdout=fnull, stderr=fnull)
            if call(['git', 'config', 'remote.origin.fetch',
                     '+refs/*:refs/*'],
                    stdout=fnull, stderr=fnull) != 0:
                raise BaseException('Did not get a valid git repo')
            call(['git', 'fetch', 'origin'], stdout=fnull, stderr=fnull)
    except:
        app.log(name, 'Using git clone from ', repo_url)
        try:
            with open(os.devnull, "w") as fnull:
                call(['git', 'clone', '--mirror', '-n', repo_url, gitdir],
                     stdout=fnull, stderr=fnull)
        except:
            app.log(name, 'ERROR: failed to clone', repo)
            raise SystemExit

    app.log(name, 'Git repo is mirrored at', gitdir)


def fetch(repo):
    with app.chdir(repo), open(os.devnull, "w") as fnull:
        call(['git', 'fetch', 'origin'], stdout=fnull, stderr=fnull)


def checkout(name, repo, ref, checkoutdir):
    # checkout the required version of this from git
    app.log(name, 'Upstream version:', get_upstream_version(repo, ref))
    app.log(name, 'Git checkout %s in %s' % (repo, checkoutdir))
    with app.chdir(checkoutdir), open(os.devnull, "w") as fnull:
        gitdir = os.path.join(app.settings['gits'], get_repo_name(repo))
        if not os.path.exists(gitdir):
            mirror(name, repo)
        copy_repo(gitdir, checkoutdir)
        if call(['git', 'checkout', ref], stdout=fnull, stderr=fnull):
            app.log(name, 'ERROR: git checkout failed for', ref)
            raise SystemExit

        utils.set_mtime_recursively(checkoutdir)


def checkout_submodules(this):
    app.log(this, 'Git submodules')
    with open('.gitmodules', "r") as gitfile:
        # drop indentation in sections, as RawConfigParser cannot handle it
        content = '\n'.join([l.strip() for l in gitfile.read().splitlines()])
    io = StringIO.StringIO(content)
    parser = ConfigParser.RawConfigParser()
    parser.readfp(io)

    for section in parser.sections():
        # validate section name against the 'submodule "foo"' pattern
        name = re.sub(r'submodule "(.*)"', r'\1', section)
        url = parser.get(section, 'url')
        path = parser.get(section, 'path')

        try:
            # list objects in the parent repo tree to find the commit
            # object that corresponds to the submodule
            commit = call(['git', 'ls-tree', this['ref'], path])

            # read the commit hash from the output
            fields = commit.split()
            if len(fields) >= 2 and fields[1] == 'commit':
                submodule_commit = commit.split()[2]

                # fail if the commit hash is invalid
                if len(submodule_commit) != 40:
                    raise Exception
            else:
                app.log(this, 'Skipping submodule "%s" as %s:%s has '
                        'a non-commit object for it' % (name, repo, ref))
        except:
            app.log(this, "ERROR: Git submodules problem")
            raise SystemExit
