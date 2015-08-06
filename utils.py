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
# with this program.  If not, see <http://www.gnu.org/licenses/>.
#
# =*= License: GPL-2 =*=

import contextlib
import os
import shutil
import stat
import calendar

import app

# The magic number for timestamps: 2011-11-11 11:11:11
default_magic_timestamp = calendar.timegm([2011, 11, 11, 11, 11, 11])


def copy_all_files(srcpath, destpath):
    '''Copy every file in the source path to the destination.

    If an exception is raised, the staging-area is indeterminate.

    '''

    def _copyfun(inpath, outpath):
        with open(inpath, "r") as infh:
            with open(outpath, "w") as outfh:
                shutil.copyfileobj(infh, outfh, 1024*1024*4)
        shutil.copystat(inpath, outpath)

    _process_tree(srcpath, destpath, _copyfun)


def hardlink_all_files(srcpath, destpath):
    '''Hardlink every file in the path to the staging-area

    If an exception is raised, the staging-area is indeterminate.

    '''
    _process_tree(srcpath, destpath, os.link)


def _process_tree(srcpath, destpath, actionfunc):
    file_stat = os.lstat(srcpath)
    mode = file_stat.st_mode

    if stat.S_ISDIR(mode):
        # Ensure directory exists in destination, then recurse.
        if not os.path.lexists(destpath):
            os.makedirs(destpath)
        dest_stat = os.stat(os.path.realpath(destpath))
        if not stat.S_ISDIR(dest_stat.st_mode):
            raise IOError('Destination not a directory. source has %s'
                          ' destination has %s' % (srcpath, destpath))

        for entry in os.listdir(srcpath):
            _process_tree(os.path.join(srcpath, entry),
                          os.path.join(destpath, entry),
                          actionfunc)
    elif stat.S_ISLNK(mode):
        # Copy the symlink.
        if os.path.lexists(destpath):
            os.remove(destpath)
        os.symlink(os.readlink(srcpath), destpath)

    elif stat.S_ISREG(mode):
        # Process the file.
        if os.path.lexists(destpath):
            os.remove(destpath)
        actionfunc(srcpath, destpath)

    elif stat.S_ISCHR(mode) or stat.S_ISBLK(mode):
        # Block or character device. Put contents of st_dev in a mknod.
        if os.path.lexists(destpath):
            os.remove(destpath)
        os.mknod(destpath, file_stat.st_mode, file_stat.st_rdev)
        os.chmod(destpath, file_stat.st_mode)

    else:
        # Unsupported type.
        raise IOError('Cannot extract %s into staging-area. Unsupported'
                      ' type.' % srcpath)


def copy_file_list(srcpath, destpath, filelist):
    '''Copy every file in the source path to the destination.

    If an exception is raised, the staging-area is indeterminate.

    '''

    def _copyfun(inpath, outpath):
        with open(inpath, "r") as infh:
            with open(outpath, "w") as outfh:
                shutil.copyfileobj(infh, outfh, 1024*1024*4)
        shutil.copystat(inpath, outpath)

    _process_list(srcpath, destpath, filelist, _copyfun)


def hardlink_file_list(srcpath, destpath, filelist):
    '''Hardlink every file in the path to the staging-area

    If an exception is raised, the staging-area is indeterminate.

    '''
    _process_list(srcpath, destpath, filelist, os.link)


def _copy_directories(srcdir, destdir, target):
    ''' Recursively make directories in target area and copy permissions
    '''
    dir = os.path.dirname(target)
    new_dir = os.path.join(destdir, dir)

    if not os.path.lexists(new_dir):
        if dir:
            _copy_directories(srcdir, destdir, dir)

        old_dir = os.path.join(srcdir, dir)
        if os.path.lexists(old_dir):
            dir_stat = os.lstat(old_dir)
            mode = dir_stat.st_mode

            if stat.S_ISDIR(mode):
                os.makedirs(new_dir)
                shutil.copystats(old_dir, new_dir)
            else:
                raise IOError('Source directory tree has file where '
                              'directory expected: %s' % dir)


def _process_list(srcdir, destdir, filelist, actionfunc):

    for path in sorted(filelist):
        srcpath = os.path.join(srcdir, path)
        destpath = os.path.join(destdir, path)

        # The destination directory may not have been created separately
        _copy_directories(srcdir, destdir, path)

        file_stat = os.lstat(srcpath)
        mode = file_stat.st_mode

        if stat.S_ISDIR(mode):
            # Ensure directory exists in destination, then recurse.
            if not os.path.lexists(destpath):
                os.makedirs(destpath)
            dest_stat = os.stat(os.path.realpath(destpath))
            if not stat.S_ISDIR(dest_stat.st_mode):
                raise IOError('Destination not a directory. source has %s'
                              ' destination has %s' % (srcpath, destpath))
            shutil.copystats(srcpath, destpath)


        elif stat.S_ISLNK(mode):
            # Copy the symlink.
            if os.path.lexists(destpath):
                os.remove(destpath)
            os.symlink(os.readlink(srcpath), destpath)

        elif stat.S_ISREG(mode):
            # Process the file.
            if os.path.lexists(destpath):
                os.remove(destpath)
            actionfunc(srcpath, destpath)

        elif stat.S_ISCHR(mode) or stat.S_ISBLK(mode):
            # Block or character device. Put contents of st_dev in a mknod.
            if os.path.lexists(destpath):
                os.remove(destpath)
            os.mknod(destpath, file_stat.st_mode, file_stat.st_rdev)
            os.chmod(destpath, file_stat.st_mode)

        else:
            # Unsupported type.
            raise IOError('Cannot extract %s into staging-area. Unsupported'
                          ' type.' % srcpath)


def set_mtime_recursively(root, set_time=default_magic_timestamp):
    '''Set the mtime for every file in a directory tree to the same.

    The magic number default is 2011-11-11 11:11:11
    The aim is to make builds more predictable.

    '''

    for dirname, subdirs, basenames in os.walk(root.encode("utf-8"),
                                               topdown=False):
        for basename in basenames:
            pathname = os.path.join(dirname, basename)
            # we need the following check to ignore broken symlinks
            if os.path.exists(pathname):
                os.utime(pathname, (set_time, set_time))
        os.utime(dirname, (set_time, set_time))


def _find_extensions(paths):
    '''Iterate the paths, in order, finding extensions and adding them to
    the return dict.'''

    ret = {}
    extension_kinds = ['check', 'configure', 'write']

    for e in extension_kinds:
        ret[e] = {}

    def scan_path(path):
        for kind in extension_kinds:
            for dirpath, dirnames, filenames in os.walk(path):
                for filename in filenames:
                    if filename.endswith(kind):
                        filepath = os.path.join(dirpath, filename)
                        ret[kind][os.path.splitext(filename)[0]] = filepath

    for p in paths:
        scan_path(p)

    return ret


def find_extensions():
    '''Scan definitions for extensions.'''

    paths = [app.config['extsdir']]

    return _find_extensions(paths)


@contextlib.contextmanager
def monkeypatch(obj, attr, new_value):
    '''Temporarily override the attribute of some object.

    For example, to override the time.time() function, so that it returns a
    fixed timestamp, you could do:

        with monkeypatch(time, 'time', lambda: 1234567):
            print time.time()

    '''
    old_value = getattr(obj, attr)
    setattr(obj, attr, new_value)
    yield
    setattr(obj, attr, old_value)
