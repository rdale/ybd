#!/usr/bin/env python3
#
# Copyright (C) 2014-2015 Codethink Limited
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
import shutil
import app
import re
import hashlib
import json
import definitions
import repos
import buildsystem
import utils
from subprocess import call


def cache_key(this):
    defs = definitions.Definitions()
    definition = defs.get(this)
    if definition is None:
        app.log(this, 'ERROR: No definition found for', this)
        raise SystemExit

    if definition.get('cache'):
        return definition['cache']

    if definition.get('repo') and not definition.get('tree'):
        definition['tree'] = repos.get_tree(definition)

    hash_factors = {'arch': app.settings['arch']}

    for factor in definition.get('build-depends', []):
        hash_factors[factor] = cache_key(factor)

    for factor in definition.get('contents', []):
        hash_factors[factor] = cache_key(factor)

    for factor in ['tree'] + buildsystem.build_steps:
        if definition.get(factor):
            hash_factors[factor] = definition[factor]

    if definition.get('kind') == 'cluster':
        for system in definition.get('systems', []):
            factor = system.get('path', 'BROKEN')
            hash_factors[factor] = cache_key(factor)

    result = json.dumps(hash_factors, sort_keys=True).encode('utf-8')

    safename = definition['name'].replace('/', '-')
    definition['cache'] = safename + "@" + hashlib.sha256(result).hexdigest()
    app.log(definition, 'Cache_key is', definition['cache'])
    return definition['cache']


def cache(this, full_root=False):
    cachefile = os.path.join(app.settings['artifacts'], cache_key(this))
    if full_root:
        shutil.make_archive(cachefile, 'tar', this['assembly'])
        call(['mv', cachefile + '.tar', cachefile + '.tar.gz'])
    else:
        utils.set_mtime_recursively(this['install'])
        shutil.make_archive(cachefile, 'gztar', this['install'])
    app.log(this, 'Now cached as', cache_key(this))


def unpack(this):
    cachefile = get_cache(this)
    if cachefile:
        unpackdir = cachefile + '.unpacked'
        if not os.path.exists(unpackdir):
            os.makedirs(unpackdir)
            if call(['tar', 'xf', cachefile, '--directory', unpackdir]):
                app.log(this, 'ERROR: Problem unpacking', cachefile)
        return unpackdir

    app.log(this, 'ERROR: Cached artifact not found')
    raise SystemExit


def get_cache(this):
    ''' Check if a cached artifact exists for the hashed version of this. '''

    cachefile = os.path.join(app.settings['artifacts'],
                             cache_key(this) + '.tar.gz')

    if os.path.exists(cachefile):
        return cachefile

    return False
