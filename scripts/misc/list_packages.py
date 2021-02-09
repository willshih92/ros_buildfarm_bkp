#!/usr/bin/env python3

# Copyright 2014 Open Source Robotics Foundation, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import argparse
import sys

from ros_buildfarm.argument import add_argument_cache_dir
from ros_buildfarm.argument import add_argument_debian_repository_urls
from ros_buildfarm.argument import add_argument_os_code_name_and_arch_tuples
from ros_buildfarm.argument import add_argument_os_name_and_os_code_name_and_arch_tuples

from ros_buildfarm.common import package_format_mapping
from ros_buildfarm.common import Target
from ros_buildfarm.common import get_short_os_name
from collections import namedtuple
from distutils.version import LooseVersion
import os
from ros_buildfarm.status_page_input import RosPackage
from ros_buildfarm.package_repo import get_package_repo_data


def _strip_version_suffix(version):
    """
    Remove trailing junk from the version number.

    >>> strip_version_suffix('')
    ''
    >>> strip_version_suffix('None')
    'None'
    >>> strip_version_suffix('1.2.3-4trusty-20140131-1359-+0000')
    '1.2.3-4'
    >>> strip_version_suffix('1.2.3-foo')
    '1.2.3'
    """
    global version_regex
    if not version:
        return version
    match = version_regex.search(version)
    return match.group(0) if match else version


def _strip_os_code_name_suffix(version, target):
    if version:
        if package_format_mapping[target.os_name] == 'rpm':
            delimiter = '.' + get_short_os_name(target.os_name) + target.os_code_name
        else:
            delimiter = target.os_code_name
        index = version.find(delimiter)
        if index != -1:
            version = version[:index]
    return version


def _get_pkg_version(repo_data, target, package_name):
    repo_pkg_descriptor = repo_data.get(target, {}).get(package_name, None)
    return repo_pkg_descriptor.version if repo_pkg_descriptor else None


PackageDescriptor = namedtuple(
    'PackageDescriptor', 'pkg_name debian_pkg_name version source_name')


def get_version_status(
        package_descriptors, targets, repos_data,
        strip_version=False, strip_os_code_name=False):
    """
    For each package and target check if it is affected by a sync.

    This is the case when the package version in the testing repo is different
    from the version in the main repo.

    :return: a dict indexed by package names containing
      dicts indexed by targets containing
      a list of status strings (one for each repo)
    """
    status = {}
    for package_descriptor in package_descriptors.values():
        pkg_name = package_descriptor.pkg_name
        debian_pkg_name = package_descriptor.debian_pkg_name
        source_pkg_name = package_descriptor.source_name
        ref_version = package_descriptor.version
        if strip_version:
            ref_version = _strip_version_suffix(ref_version)

        status[pkg_name] = {}
        for target in targets:
            statuses = []
            for repo_data in repos_data:
                version = _get_pkg_version(repo_data, target, debian_pkg_name)
                if strip_version:
                    version = _strip_version_suffix(version)
                if strip_os_code_name:
                    version = _strip_os_code_name_suffix(version, target)

                if ref_version:
                    if not version:
                        if target.arch == 'source' and \
                                source_pkg_name and debian_pkg_name != source_pkg_name:
                            statuses.append('ignore')
                        else:
                            statuses.append('missing')
                    elif version.startswith(ref_version):  # including equal
                        statuses.append('equal')
                    else:
                        if _version_is_gt_other(version, ref_version):
                            statuses.append('higher')
                        else:
                            statuses.append('lower')
                else:
                    if not version:
                        statuses.append('ignore')
                    else:
                        statuses.append('obsolete')
            status[pkg_name][target] = statuses
    return status


def get_repos_package_descriptors(repos_data, targets):
    descriptors = {}
    # the highest version is the reference
    for target in targets:
        for repo_data in repos_data:
            repo_index = repo_data[target]
            for debian_pkg_name, repo_descriptor in repo_index.items():
                version = _strip_os_code_name_suffix(repo_descriptor.version, target)
                if debian_pkg_name not in descriptors:
                    descriptors[debian_pkg_name] = PackageDescriptor(
                        debian_pkg_name, debian_pkg_name, version, repo_descriptor.source_name)
                    continue
                if not version:
                    continue
                other_version = descriptors[debian_pkg_name].version
                if not other_version:
                    continue
                # update version if higher
                if _version_is_gt_other(version, other_version):
                    descriptors[debian_pkg_name] = PackageDescriptor(
                        debian_pkg_name, debian_pkg_name, version, repo_descriptor.source_name)
    return descriptors


def _version_is_gt_other(version, other_version):
    try:
        # might raise TypeError: http://bugs.python.org/issue14894
        return LooseVersion(version) > LooseVersion(other_version)
    except TypeError:
        loose_version, other_loose_version = \
            _get_comparable_loose_versions(version, other_version)
        return loose_version < other_loose_version


def _get_comparable_loose_versions(version_str1, version_str2):
    loose_version1 = LooseVersion(version_str1)
    loose_version2 = LooseVersion(version_str2)
    if sys.version_info[0] > 2:
        # might raise TypeError in Python 3: http://bugs.python.org/issue14894
        version_parts1 = loose_version1.version
        version_parts2 = loose_version2.version
        for i in range(min(len(version_parts1), len(version_parts2))):
            try:
                version_parts1[i] < version_parts2[i]
            except TypeError:
                version_parts1[i] = str(version_parts1[i])
                version_parts2[i] = str(version_parts2[i])
    return loose_version1, loose_version2


def dump(obj):
    for attr in dir(obj):
        print("obj.%s = %r" % (attr, getattr(obj, attr)))


def main(argv=sys.argv[1:]):
    parser = argparse.ArgumentParser(
        description="Run the 'repos_status_page' job")
    add_argument_debian_repository_urls(parser)
    add_argument_os_code_name_and_arch_tuples(parser, required=False)
    add_argument_os_name_and_os_code_name_and_arch_tuples(parser, required=False)
    add_argument_cache_dir(parser, '/tmp/package_repo_cache')
    args = parser.parse_args(argv)

    # TODO: Remove when --os-code-name-and-arch-tuples is removed
    if not args.os_name_and_os_code_name_and_arch_tuples:
        parser.error(
            'the following arguments are required: --os-name-and-os-code-name-and-arch-tuples')

    # get targets
    targets = []
    for os_name, os_code_name, arch in args.os_name_and_os_code_name_and_arch_tuples:
        targets.append(Target(os_name, os_code_name, arch))

    # get all input data
    repos_data = []
    for repo_url in args.debian_repository_urls:
        repo_data = get_package_repo_data(repo_url, targets, args.cache_dir)
        repos_data.append(repo_data)

    # compute derived attributes
    package_descriptors = get_repos_package_descriptors(repos_data, targets)

    version_status = get_version_status(
        package_descriptors, targets, repos_data, strip_os_code_name=True)
    import pprint
    pprint.pprint(package_descriptors)

    # homogeneous = get_homogeneous(package_descriptors, targets, repos_data)

    # package_counts = get_package_counts(
    #    package_descriptors, targets, repos_data)

    # generate output
    # repo_names = get_url_names(repo_urls)

    ordered_pkgs = []
    for debian_pkg_name in sorted(package_descriptors.keys()):
        pkg = RosPackage(debian_pkg_name)
        pkg.debian_name = debian_pkg_name
        pkg.version = package_descriptors[debian_pkg_name].version

        # set unavailable attributes
        pkg.repository_name = None
        pkg.repository_url = None
        pkg.status = None
        pkg.status_description = None
        pkg.maintainers = []
        pkg.url = None

        #print("--------------------")
        # print(pkg.name)
        #dump(pkg)
        #print("--------------------")
        ordered_pkgs.append(pkg)


if __name__ == '__main__':
    main()
