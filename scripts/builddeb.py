#!/usr/bin/env python3
"""
Summary.

    builddeb (python3):  xlines binary operating system package (.deb, Debian systems)

        - Automatic determination of version to be built
        - Build version can optionally be forced to a specific version
        - Resulting .deb package produced in packaging/deb directory
        - To execute build, from the directory of this module, run:

    .. code-block:: python

        $ cd ../<project dir>
        $ make builddeb

Author:
    Blake Huber
    Copyright 2017-2020, All Rights Reserved.

License:
    General Public License v3
    Additional terms may be found in the complete license agreement:
    https://github.com/fstab50/xlines/blob/master/LICENSE

OS Support:
    - Debian, Ubuntu, Ubuntu variants

Dependencies:
    - Requires python3, developed and tested under python3.6
"""

import argparse
import os
import sys
import json
import inspect
import re
import subprocess
import pdb
import fileinput
import tarfile
from shutil import copy2 as copyfile
from shutil import copytree, rmtree, which
from libtools import Colors, stdout_message
from loggers import logger                 # global logger


try:
    from libtools.oscodes_unix import exit_codes
except Exception:
    from libtools.oscodes_win import exit_codes    # non-specific os-safe codes


# globals
PROJECT = 'python3-xlines'
PROJECT_BIN = 'xlines'
module = os.path.basename(__file__)
TMPDIR = '/tmp/build'
VOLMNT = '/tmp/deb'
CONTAINER_VOLMNT = '/mnt/deb'
PACKAGE_CONFIG = '.debian.json'
DISTRO_LIST = ['ubuntu14.04', 'ubuntu16.04', 'ubuntu18.04']


c = Colors()

# formatting
act = c.ORANGE                          # accent highlight (bright orange)
bd = c.BOLD + c.WHITE                   # title formatting
bdwt = c.BOLD + c.BRIGHT_WHITE          # bold, bright white accent highlight
bn = c.CYAN                             # color for main binary highlighting
lk = c.DARK_BLUE                        # color for filesystem path confirmations
red = c.RED                             # color for failed operations
yl = c.GOLD3                            # color when copying, creating paths
rst = c.RESET                           # reset all color, formatting
arrow = yl + c.BOLD + '-->' + rst       # bold, yellow arrow pointing left to right


def git_root():
    """
    Summary.

        Returns root directory of git repository

    """
    cmd = 'git rev-parse --show-toplevel 2>/dev/null'
    return subprocess.getoutput(cmd).strip()


def help_menu():
    """
    Summary.

        Command line parameter options (Help Menu)

    """
    menu = '''
                          ''' + bd + module + rst + ''' help contents

  ''' + bd + '''DESCRIPTION''' + rst + '''

          Builds an installable package (.deb) for Debian, Ubuntu, and Ubuntu
          variants of the Linux Operatining System

  ''' + bd + '''OPTIONS''' + rst + '''

            $ python3  ''' + act + module + rst + '''  --build  [ --force-version <VERSION> ]

                         -b, --build
                        [-d, --debug  ]
                        [-f, --force  ]
                        [-h, --help   ]
                        [-s, --set-version  <value> ]

        ''' + bd + '''-b''' + rst + ''', ''' + bd + '''--build''' + rst + ''':  Build Operating System package (.deb, Debian systems)
            When given without -S (--set-version) parameter switch, build ver-
            sion is extracted from the project repository information

        ''' + bd + '''-F''' + rst + ''', ''' + bd + '''--force''' + rst + ''':  When given, overwrites any pre-existing build artifacts.
            DEFAULT: False

        ''' + bd + '''-s''' + rst + ''', ''' + bd + '''--set-version''' + rst + '''  (string):  When given, overrides all version infor-
            mation contained in the project to build the exact version speci-
            fied by VERSION parameter

        ''' + bd + '''-d''' + rst + ''', ''' + bd + '''--debug''' + rst + ''': Debug mode, verbose output.

        ''' + bd + '''-h''' + rst + ''', ''' + bd + '''--help''' + rst + ''': Print this help menu
    '''
    print(menu)
    return True


def current_branch(path):
    """
    Returns.

        git repository source url, TYPE: str

    """
    pwd = os.getcwd()
    os.chdir(path)

    try:
        if '.git' in os.listdir('.'):

            branch = subprocess.getoutput('git branch').split('*')[1].split('\n')[0][1:]

        else:
            ex = Exception(
                '%s: Unable to identify current branch - path not a git repository: %s' %
                (inspect.stack()[0][3], path))
            raise ex

        os.chdir(pwd)      # return cursor

    except IndexError:
        logger.exception(
                '%s: problem retrieving git branch for %s' %
                (inspect.stack()[0][3], path)
            )
        return ''
    return branch


def read(fname):
    basedir = os.path.dirname(sys.argv[0])
    return open(os.path.join(basedir, fname)).read()


def masterbranch_version(version_module):
    """
    Returns version denoted in the master branch of the repository
    """
    branch = current_branch(git_root())
    commands = ['git checkout master', 'git checkout {}'.format(branch)]

    try:
        # checkout master
        #stdout_message('Checkout master branch:\n\n%s' % subprocess.getoutput(commands[0]))
        masterversion = read(version_module).split('=')[1].strip().strip('"')

        # return to working branch
        stdout_message(
            'Returning to working branch: checkout %s\n\n%s'.format(branch)
        )
        stdout_message(subprocess.getoutput(f'git checkout {branch}'))
    except Exception:
        return None
    return masterversion


def current_version(binary, version_modpath):
    """
    Summary:
        Returns current binary package version if locally
        installed, master branch __version__ if the binary
        being built is not installed locally
    Args:
        :root (str): path to the project root directory
        :binary (str): Name of main project exectuable
        :version_modpath (str): path to __version__ module
    Returns:
        current version number of the project, TYPE: str
    """
    pkgmgr = 'apt'
    pkgmgr_bkup = 'apt-cache'

    if which(binary):

        if which(pkgmgr):
            cmd = pkgmgr + ' show ' + binary + ' 2>/dev/null | grep Version | head -n1'

        elif which(pkgmgr_bkup):
            cmd = pkgmgr_bkup + ' policy ' + binary + ' 2>/dev/null | grep Installed'

        try:

            installed_version = subprocess.getoutput(cmd).split(':')[1].strip()
            return greater_version(installed_version, __version__)

        except Exception:
            logger.info(
                '%s: Build binary %s not installed, comparing current branch version to master branch version' %
                (inspect.stack()[0][3], binary))
    return greater_version(masterbranch_version(version_modpath), __version__)


def greater_version(versionA, versionB):
    """
    Summary:
        Compares to version strings with multiple digits and returns greater
    Returns:
        greater, TYPE: str
    """
    try:

        list_a = versionA.split('.')
        list_b = versionB.split('.')

    except AttributeError:
        return versionA or versionB    # either A or B is None

    try:

        for index, digit in enumerate(list_a):
            if int(digit) > int(list_b[index]):
                return versionA
            elif int(digit) < int(list_b[index]):
                return versionB
            elif int(digit) == int(list_b[index]):
                continue

    except ValueError:
        return versionA or versionB    # either A or B is ''
    return versionA


def increment_version(current):
    """
    Returns current version incremented by 1 minor version number
    """
    minor = current.split('.')[-1]
    major = '.'.join(current.split('.')[:-1])
    inc_minor = int(minor) + 1
    return major + '.' + str(inc_minor)


def tar_archive(archive, source_dir):
    """
    Summary.

        - Creates .tar.gz compressed archive
        - Checks that file was created before exit

    Returns:
        Success | Failure, TYPE: bool

    """
    try:

        with tarfile.open(archive, "w:gz") as tar:
            tar.add(source_dir, arcname=os.path.basename(source_dir))

        if os.path.exists(archive):
            return True

    except OSError:
        logger.exception(
            '{}: Unable to create tar archive {}'.format(inspect.stack()[0][3], archive))
    except Exception as e:
        logger.exception(
            '%s: Unknown problem while creating tar archive %s:\n%s' %
            (inspect.stack()[0][3], archive, str(e)))
    return False


def create_builddirectory(param_dict, path, version, force):
    """

        - Creates the deb package binary working directory
        - Checks if build artifacts preexist; if so, halts
        - If force is True, continues even if artifacts exist (overwrites)

    Returns:
        builddir, TYPE: str

    """
    try:

        PROJECT = param_dict['Project']
        builddir = PROJECT + '_' + version + '_amd64'
        stdout_message(message='BUILDDIR IS: {}'.format(builddir))

        # rm builddir when force if exists
        if force is True and builddir in os.listdir(path):
            rmtree(os.path.join(path, builddir))

        elif force is False and builddir in os.listdir(path):
            stdout_message(
                'Cannot create build directory {} - preexists. Use --force option to overwrite'.format(builddir),
                prefix='WARN',
                severity='WARNING'
                )
            return None

        # create build directory
        os.mkdir(os.path.join(path, builddir))

    except OSError as e:
        logger.exception(
            '{}: Unable to create build directory {}'.format(inspect.stack()[0][3], builddir)
            )
    return builddir


def operation_status(source, destination):
    """Validates copy operations complete successfully"""
    if os.path.exists(destination):
        stdout_message(
                message='Copied:\t{} {} {}'.format(lk + source + rst, arrow, lk + destination + rst),
                prefix='OK'
            )
        return True
    else:
        stdout_message(
                message='Failure to copy:\t{} to {}'.format(lk + source + rst, lk + destination + rst),
                prefix='WARN'
            )
    return False


def builddir_structure(param_dict, builddir, version):
    """
    Summary.

        - Updates paths in binary exectuable
        - Updates

    Args:
        :root (str): full path to root directory of the git project
        :builddir (str): name of current build directory which we need to populate

    Vars:
        :lib_path (str): src path to library modules in project root
        :builddir_path (str): dst path to root of the current build directory
         (/<path>/xlines-1.X.X dir)

    Returns:
        Success | Failure, TYPE: bool

    """
    def _mapper(venv_dir):
        """Identifies path to python modules in virtual env"""
        for i in (6, 7, 8, 9):
            path = venv_dir + '/lib/python3.' + str(i) + '/site-packages/'
            if os.path.exists(path):
                return path

    def module_search(module, packages_path):
        t = []
        for i in os.listdir(packages_path):
            if re.search(module, i, re.IGNORECASE):
                t.append(i)
        return t

    root = git_root()
    project_dirname = os.path.split(git_root())[1]
    build_root = TMPDIR

    # files
    binary = param_dict['Executable']
    control_file = param_dict['ControlFile']['Name']
    compfile = param_dict['BashCompletion']

    # LIB source files
    env = os.environ.get('VIRTUAL_ENV') or root
    #lib_src = _mapper(env)
    lib_src = os.path.join(root, PROJECT_BIN)

    # full paths
    builddir_path = build_root + '/' + builddir
    deb_src = root + '/packaging/deb'
    debian_dir = 'DEBIAN'
    debian_path = deb_src + '/' + debian_dir
    binary_path = builddir_path + '/usr/bin'
    lib_dst = builddir_path + '/usr/lib/python3/dist-packages'
    comp_src = os.path.join(root, 'bash')
    comp_dst = builddir_path + '/etc/bash_completion.d'

    try:

        # create build directory
        if os.path.exists(builddir_path):
            rmtree(builddir_path)
        os.makedirs(builddir_path)
        stdout_message(
                message='Created:\t{}'.format(yl + builddir_path + rst),
                prefix='OK'
            )

        stdout_message(f'Copying DEBIAN package control files to {bn + builddir + rst}')

        _src = os.path.join(deb_src, debian_dir)
        _dst = os.path.join(builddir_path, debian_dir)
        copytree(_src, _dst)
        operation_status(_src, _dst)

        stdout_message(f'Creating build directory subdirectories in {bn + builddir + rst}')

        # binary exec
        if not os.path.exists(binary_path):
            os.makedirs(binary_path)
            _src_path = os.path.join(deb_src, 'bin', 'xlines')
            _dst_path = os.path.join(binary_path, 'xlines')
            copyfile(_src_path, _dst_path)
            # status msg
            stdout_message(
                    message='Copied:\t{} {} {}'.format(lk + _src_path + rst, arrow, lk + _dst_path + rst),
                    prefix='OK'
                )

        # library components
        if not os.path.exists(lib_dst):
            os.makedirs(lib_dst)

        _src = lib_src
        _dst = os.path.join(lib_dst, PROJECT_BIN)
        copytree(_src, _dst)

        stdout_message(
                message='Copied:\t{} {} {}'.format(lk + _src + rst, arrow, lk + _dst + rst),
                prefix='OK'
            )

        if not os.path.exists(comp_dst):
            # create path
            os.makedirs(comp_dst)
            # copy
            for artifact in list(filter(lambda x: x.endswith('.bash'), os.listdir(comp_src))):
                _src = comp_src + '/' + artifact
                _dst = comp_dst + '/' + artifact
                copyfile(_src, _dst)

                stdout_message(
                        message='Copied:\t{} {} {}'.format(lk + _src + rst, arrow, lk + _dst + rst),
                        prefix='OK'
                    )

        stdout_message(f'Creating config subdirectory in {lk + lib_dst + rst}')

        os.makedirs(os.path.join(lib_dst, PROJECT_BIN, 'config'))
        source = os.path.join(root, 'config')

        for file in list(filter(lambda x: x.endswith('.list'), os.listdir(source))):
            _src = os.path.join(source, file)
            _dst = os.path.join(lib_dst, PROJECT_BIN, 'config', file)
            copyfile(_src, _dst)

    except OSError as e:
        logger.exception(
            '{}: Problem creating dirs on local fs'.format(inspect.stack()[0][3]))
        return False
    return True


def build_package(build_root, builddir):
    """
    Summary.

        Creates final os installable package for current build, build version

    Returns:
        Success | Failure, TYPE: bool

    """
    try:

        pwd = os.getcwd()
        os.chdir(build_root)

        if os.path.exists(builddir):
            cmd = 'dpkg-deb --build ' + builddir + ' 2>/dev/null'
            stdout_message('Building {}...  '.format(bn + builddir + rst))
            stdout_message(subprocess.getoutput(cmd))
            os.chdir(pwd)

        else:
            logger.warning(
                'Build directory {} not found. Failed to create .deb package'.format(builddir))
            os.chdir(pwd)
            return False

    except OSError as e:
        logger.exception(
            '{}: Error during os package creation: {}'.format(inspect.stack()[0][3], e))
        return False
    except Exception as e:
        logger.exception(
            '{}: Unknown Error during os package creation: {}'.format(inspect.stack()[0][3], e))
        return False
    return True


def builddir_content_updates(param_dict, osimage, builddir, version):
    """
    Summary.

        Updates builddir contents:
        - main exectuable has path to libraries updated
        - builddir DEBIAN/control file version is updated to current
        - updates the version.py file if version != to __version__
          contained in the file.  This occurs if user invokes the -S /
          --set-version option

    Args:
        :root (str): project root full fs path
        :builddir (str): dirname of the current build directory
        :binary (str): name of the main exectuable
        :version (str): version label provided with --set-version parameter. None otherwise

    Returns:
        Success | Failure, TYPE: bool

    """

    root = git_root()
    project_dirname = root.split('/')[-1]
    build_root = TMPDIR
    debian_dir = 'DEBIAN'
    control_filename = param_dict['ControlFile']['Name']
    deb_src = root + '/packaging/deb'
    major = '.'.join(version.split('.')[:2])
    minor = version.split('.')[-1]

    # files
    version_module = param_dict['VersionModule']
    issues_url = param_dict['IssuesUrl']
    project_url = param_dict['ProjectUrl']
    buildarch = param_dict['ControlFile']['BuildArch']

    # full paths
    builddir_path = build_root + '/' + builddir
    debian_path = builddir_path + '/' + debian_dir
    control_filepath = debian_path + '/' + control_filename
    lib_dst = builddir_path + '/usr/lib/python3/dist-packages/' + PROJECT_BIN

    # assemble dependencies
    deplist = None
    for dep in param_dict['DependencyList']:
        if deplist is None:
            deplist = str(dep)
        else:
            deplist = deplist + ', ' + str(dep)

    try:

        # debian control files
        with open(control_filepath) as f1:
            f2 = f1.readlines()
            for index, line in enumerate(f2):
                if line.startswith('Version:'):
                    newline = 'Version: ' + version + '\n'
                    f2[index] = newline
            f1.close()

        # rewrite file
        with open(control_filepath, 'w') as f3:
            f3.writelines(f2)
            path = project_dirname + (control_filepath)[len(root):]
            stdout_message(
                'Control file {} version updated: {}.'.format(yl + control_filepath + rst, version)
            )

        ## rewrite version file with current build version in case delta ##

        # orig source version module
        with open(LIB_SRC + '/' + version_module, 'w') as f3:
            f2 = ['__version__ = \"' + version + '\"\n']
            f3.writelines(f2)
            path = os.path.join(root, PROJECT_BIN, version_module)
            stdout_message('Module {} successfully updated: {}.'.format(yl + path + rst, version))

        # package version module
        with open(lib_dst + '/' + version_module, 'w') as f3:
            f2 = ['__version__ = \"' + version + '\"\n']
            f3.writelines(f2)
            path = os.path.join(lib_dst, version_module)
            stdout_message('Module {} successfully updated: {}.'.format(yl + path + rst, version))

    except OSError as e:
        logger.exception(
            '%s: Problem while updating builddir contents: %s' %
            (inspect.stack()[0][3], str(e)))
        return False
    return True


def display_package_contents(build_root, version):
    """
    Summary.

        Output newly built package contents.

    Args:
        :build_root (str):  location of newly built rpm package
        :version (str):  current version string, format:  '{major}.{minor}.{patch num}'

    Returns:
        Success | Failure, TYPE: bool

    """
    pkg_path = None

    for f in os.listdir(build_root):
        if f.endswith('.deb') and re.search(version, f):
            pkg_path = build_root + '/' + f

    if pkg_path is None:
        stdout_message(
            message=f'Unable to locate a build package in {build_root}. Abort build.',
            prefix='WARN'
        )
        return False

    tab = '\t'.expandtabs(2)
    width = 80
    path, package = os.path.split(pkg_path)
    os.chdir(path)
    cmd = 'dpkg-deb --contents ' + package
    r = subprocess.getoutput(cmd)
    formatted_out = r.splitlines()

    # title header and subheader
    header = '\n\t\tPackage Contents:  ' + bd + package + rst + '\n'
    print(header)
    subheader = tab + 'Permission' + tab + 'Owner/Group' + '\t' + 'ctime' \
        + '\t'.expandtabs(8) + 'File'
    print(subheader)

    # divider line
    list(filter(lambda x: print('-', end=''), range(0, width + 1))), print('\r')

    # content
    for line in formatted_out:
        prefix = [tab + x for x in line.split()[:2]]
        raw = line.split()[2:4]
        content_path = line.split()[5]
        fline = ''.join(prefix) + '\t'.join(raw[:4]) + tab + yl + content_path + rst
        print(fline)
    return True


def locate_deb(origin):
    """ Finds rpm file object after creation
    Returns:
        full path to rpm file | None if not found
    """
    for root, dirs, files in os.walk(origin):
        for file in files:
            if file.endswith('.deb'):
                return os.path.abspath(os.path.join(root, file))
    return None


def main(setVersion, environment, force=False, debug=False):
    """
    Summary:
        Create build directories, populate contents, update contents
    Returns:
        Success | Failure, TYPE: bool
    """
    global PROJECT_ROOT
    PROJECT_ROOT = git_root()
    global SCRIPT_DIR
    SCRIPT_DIR = PROJECT_ROOT + '/' + 'scripts'
    DEBIAN_ROOT = PROJECT_ROOT + '/' + 'packaging/deb'
    global BUILD_ROOT
    BUILD_ROOT = TMPDIR
    global LIB_SRC
    LIB_SRC = PROJECT_ROOT + '/' + PROJECT_BIN
    global CURRENT_VERSION
    CURRENT_VERSION = current_version(PROJECT_BIN, LIB_SRC + '/' 'version.py')

    # sort out version numbers, forceVersion is override      #
    # for all info contained in project                       #

    global VERSION
    if setVersion:
        VERSION = setVersion

    elif CURRENT_VERSION:
        VERSION = increment_version(CURRENT_VERSION)

    else:
        stdout_message('Could not determine current {} version'.format(bd + PROJECT + rst))
        sys.exit(exit_codes['E_DEPENDENCY']['Code'])

    # log
    stdout_message(f'Current version of last build: {bdwt + CURRENT_VERSION + rst}')
    stdout_message(f'Version to be used for this build: {bdwt + VERSION + rst}')

    # sub in current values
    parameter_obj = ParameterSet(PROJECT_ROOT + '/' + PACKAGE_CONFIG, VERSION)
    vars = parameter_obj.create()

    VERSION_FILE = vars['VersionModule']

    update_version_module(VERSION, os.path.join(LIB_SRC, VERSION_FILE))

    # create initial binary working dir
    BUILDDIRNAME = create_builddirectory(vars, BUILD_ROOT, VERSION, force)

    if debug:
        print('BUILDDIRNAME returned is: {}'.format(BUILDDIRNAME))
        print(json.dumps(vars, indent=True, sort_keys=True))

    if BUILDDIRNAME:

        r_struture = builddir_structure(vars, BUILDDIRNAME, VERSION)
        r_updates = builddir_content_updates(vars, environment, BUILDDIRNAME, VERSION)

        if r_struture and r_updates and build_package(BUILD_ROOT, BUILDDIRNAME):
            return postbuild(VERSION, VERSION_FILE, BUILD_ROOT + '/' + BUILDDIRNAME, DEBIAN_ROOT)

    return False


def options(parser, help_menu=False):
    """
    Summary.

        parse cli parameter options

    Returns:
        TYPE: argparse object, parser argument set

    """
    parser.add_argument("-b", "--build", dest='build', default=False, action='store_true', required=False)
    parser.add_argument("-D", "--debug", dest='debug', default=False, action='store_true', required=False)
    parser.add_argument("-d", "--distro", dest='distro', default='ubuntu16.04', nargs='?', type=str, required=False)
    parser.add_argument("-F", "--force", dest='force', default=False, action='store_true', required=False)
    parser.add_argument("-s", "--set-version", dest='set', default=None, nargs='?', type=str, required=False)
    parser.add_argument("-h", "--help", dest='help', default=False, action='store_true', required=False)
    return parser.parse_args()


def is_installed(binary):
    """
    Verifies if program installed on Redhat-based Linux system
    """
    cmd = 'dpkg-query -l | grep ' + binary
    return True if subprocess.getoutput(cmd) else False


def ospackages(pkg_list):
    """Summary
        Install OS Package Prerequisites
    Returns:
        Success | Failure, TYPE: bool
    """
    try:
        for pkg in pkg_list:

            if is_installed(pkg):
                logger.info(f'{pkg} binary is already installed - skip')
                continue

            elif which('yum'):
                cmd = 'sudo yum install ' + pkg + ' 2>/dev/null'
                print(subprocess.getoutput(cmd))

            elif which('dnf'):
                cmd = 'sudo dnf install ' + pkg + ' 2>/dev/null'
                print(subprocess.getoutput(cmd))

            else:
                logger.warning(
                    '%s: Dependent OS binaries not installed - package manager not identified' %
                    inspect.stack()[0][3])

    except OSError as e:
        logger.exception('{}: Problem installing os package {}'.format(inspect.stack()[0][3], pkg))
        return False
    return True


def prebuild(builddir, volmnt, parameter_file):
    """
    Summary.

        Prerequisites and dependencies for build execution

    """
    def preclean(dir):
        """ Cleans residual build artifacts """
        try:
            if os.path.exists(dir):
                rmtree(dir)
        except OSError as e:
            logger.exception(
                '%s: Error while cleaning residual build artifacts: %s' %
                (inspect.stack()[0][3], str(e)))
            return False
        return True

    version_module = json.loads(read(parameter_file))['VersionModule']

    if preclean(builddir) and preclean(volmnt):
        stdout_message(f'Removed pre-existing build artifacts ({builddir}, {volmnt})')
    os.makedirs(builddir)
    os.makedirs(volmnt)

    root = git_root()
    lib_relpath = PROJECT_BIN
    lib_path = root + '/' + lib_relpath
    sources = [lib_path]
    illegal = ['__pycache__']
    module = inspect.stack()[0][3]
    fx = inspect.stack()[0][3]

    try:

        global __version__
        sys.path.insert(0, os.path.abspath(git_root() + '/' + lib_relpath))

        from _version import __version__

        # normalize path
        sys.path.pop(0)

    except ImportError as e:
        logger.exception(
                '{}: Problem importing program version module (%s). Error: %s' % (fx, __file__, str(e))
            )
    except Exception as e:
        logger.exception(
            '{}: Failure to import _version module _version'.format(fx)
        )
        return False

    ## clean up source ##
    try:
        for directory in sources:
            for artifact in os.listdir(directory):
                if artifact in illegal:
                    rmtree(directory + '/' + artifact)

    except OSError:
        logger.exception(
            '{}: Illegal file object detected, but unable to remove {}'.format(module, archive))
        return False
    return True


def postbuild(version, version_module, builddir_path, debian_root):
    """
    Summary.

        Post-build clean up

    Returns:
        Success | Failure, TYPE: bool

    """
    root = git_root()
    project_dirname = root.split('/')[-1]
    build_root = os.path.split(builddir_path)[0]
    package = locate_deb(build_root)

    try:

        if package:
            copyfile(package, debian_root)
            package_path = debian_root + '/' + os.path.split(package)[1]

        # remove build directory, residual artifacts
        if os.path.exists(builddir_path):
            rmtree(builddir_path)

        if display_package_contents(BUILD_ROOT, VERSION):
            return package_path

    except OSError as e:
        logger.exception('{}: Postbuild clean up failure'.format(inspect.stack()[0][3]))
        return False
    return package_path


class ParameterSet():
    """Recursion class for processing complex dictionary schema."""

    def __init__(self, parameter_file, version):
        """
        Summary.

            Retains major and minor version numbers + parameters
            in json form for later use

        Args:
            :parameter_file (str): path to json file obj containing
             parameter keys and values
            :version (str): current build version
        """
        self.parameter_dict = json.loads(read(parameter_file))
        self.version = version
        self.major = '.'.join(self.version.split('.')[:2])
        self.minor = self.version.split('.')[-1]
        self.arch = self.parameter_dict['ControlFile']['BuildArch']

    def create(self, parameters=None):
        """
        Summary.

            Update parameter dict with current values appropriate
            for the active build

        Args:
            :parameters (dict): dictionary of all parameters used to gen rpm
            :version (str):  the version of the current build, e.g. 1.6.7

        Returns:
            parameters, TYPE: dict

        """
        if parameters is None:
            parameters = self.parameter_dict

        for k, v in parameters.items():
            if isinstance(v, dict):
                self.create(v)
            else:
                if k == 'Version':
                    parameters[k] = self.major
                elif k == 'Release':
                    parameters[k] = self.minor
                elif k == 'Source':
                    parameters[k] = PROJECT + '-' + self.major + '.' + self.minor + '.tar.gz'
                elif k == 'BuildDirName':
                    parameters[k] = PROJECT + '-' + self.version + '_' + self.arch
        return parameters


def update_version_module(version, module):
    # rewrite version file with current build version
    with open(module, 'w') as f3:
        f2 = ['__version__ =\"' + version + '\"\n']
        f3.writelines(f2)

    fmodule = yl + module + rst
    fx = inspect.stack()[0][3]
    stdout_message(
        '{}: Module {} successfully updated with version {}.'.format(fx, fmodule, version)
        )
    return True


def valid_version(parameter, min=0, max=100):
    """
    Summary.

        User input validation.  Validates version string made up of integers.
        Example:  '1.6.2'.  Each integer in the version sequence must be in
        a range of > 0 and < 100. Maximum version string digits is 3
        (Example: 0.2.3 )

    Args:
        :parameter (str): Version string from user input
        :min (int): Minimum allowable integer value a single digit in version
            string provided as a parameter
        :max (int): Maximum allowable integer value a single digit in a version
            string provided as a parameter

    Returns:
        True if parameter valid or None, False if invalid, TYPE: bool

    """
    # type correction and validation
    if parameter is None:
        return True

    elif isinstance(parameter, int):
        return False

    elif isinstance(parameter, float):
        parameter = str(parameter)

    component_list = parameter.split('.')
    length = len(component_list)

    try:

        if length <= 3:
            for component in component_list:
                if isinstance(int(component), int) and int(component) in range(min, max + 1):
                    continue
                else:
                    return False

    except ValueError as e:
        return False
    return True


def init_cli():
    """Collect parameters and call main """
    try:
        parser = argparse.ArgumentParser(add_help=False)
        args = options(parser)
    except Exception as e:
        help_menu()
        stdout_message(str(e), 'ERROR')
        return exit_codes['E_MISC']['Code']

    if args.debug:
        stdout_message(
                message='forceVersion:\t{}'.format(args.set),
                prefix='DBUG',
                severity='WARNING'
            )
        stdout_message(
                message='build:\t{}'.format(args.build),
                prefix='DBUG',
                severity='WARNING'
            )
        stdout_message(
                message='debug flag:\t{}'.format(args.debug),
                prefix='DBUG',
                severity='WARNING'
            )

    if len(sys.argv) == 1:
        help_menu()
        return exit_codes['EX_OK']['Code']

    elif args.help:
        help_menu()
        return exit_codes['EX_OK']['Code']

    elif args.build:

        if valid_version(args.set) and prebuild(TMPDIR, VOLMNT, git_root() + '/' + PACKAGE_CONFIG):

            package_path = main(
                        setVersion=args.set,
                        environment=args.distro,
                        force=args.force,
                        debug=args.debug
                    )

            if package_path:
                path, package = os.path.split(package_path)
                stdout_message(f'{PROJECT} build package created: {lk + path + rst}/{bn + package + rst}')
                stdout_message(f'Debian build process completed successfully. End', prefix='OK')
                return exit_codes['EX_OK']['Code']
            else:
                stdout_message(
                    '{}: Problem creating os installation package. Exit'.format(inspect.stack()[0][3]),
                    prefix='WARN',
                    severity='WARNING'
                )
                return exit_codes['E_MISC']['Code']

        elif not valid_version(args.set):

            stdout_message(
                'You must enter a valid version when using --set-version parameter. Ex: 1.6.3',
                prefix='WARN',
                severity='WARNING'
                )
            return exit_codes['E_DEPENDENCY']['Code']

        else:
            logger.warning('{} Failure in prebuild stage'.format(inspect.stack()[0][3]))
            return exit_codes['E_DEPENDENCY']['Code']
    return True
sys.exit(init_cli())
