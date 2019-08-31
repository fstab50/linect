#!/usr/bin/env bash

#
#   Document: Build script
#   Distribution:  Redhat Enterprise Linux, CentOS 7
#   Author: Blake Huber
#
#   Copyright 2019, Blake Huber
#


# --- declarations ------------------------------------------------------------


function _git_root(){
    ##
    ##  determines full path to current git project root
    ##
    echo "$(git rev-parse --show-toplevel 2>/dev/null)"
}


function _pip_exec(){
    ##
    ##  Finds pip executable for python3 regardless of upgrade
    ##
    if [[ $(which pip3) ]]; then
        echo "$(which pip3)"
        return 0
    elif [[ $(which pip) ]]; then
        echo "$(which pip)"
        return 0
    fi
    return 1
}


function export_package(){
    ##
    ##  Copy newly created rpm package out of container
    ##
    local package
    local external='/mnt/rpm'

    cd "$(_git_root)/dist"

    package=$(find . -name "xlines-[0-9].[0-9].[0-9]-[0-9].noarch.rpm")

    # prefix package name with python3 version
    package=$(echo $package | cut -c 3-30)
    p3_package="python36-$package"

    mv "$package" "$p3_package"
    sudo cp "$p3_package" "$external/$p3_package"

    if [[ -f "$external/$p3_package" ]]; then
        return 0
    fi
    return 1
}


# --- main --------------------------------------------------------------------


ROOT=$(_git_root)
_PYTHON3_PATH=$(which python3)
_YUM=$(which yum)
_SED=$(which sed)
_PIP=$(_pip_exec)
_POSTINSTALL=${ROOT}/packaging/rpm/rpm_postinstall.sh
_REQUIRES='python3,python3-pip,python3-setuptools,bash-completion,which'

# colors; functions
. "$ROOT/scripts/colors.sh"
. "$ROOT/scripts/std_functions.sh"


if lsb_release -sirc | grep -i amazon >/dev/null 2>&1; then

    std_message "Dependency check: validate epel package repository installed" "INFO"

    if [[ $(${_YUM} repolist 2>/dev/null | grep epel) ]]; then
        std_message "epel Redhat extras packages repository installed." "OK"
    else
        std_message "ERROR: epel Redhat extras packages repository NOT installed. Exit" "WARN"
        exit 1
    fi

    # strip out sudo path restrictions
    sudo $_SED -i '/env_reset/d' /etc/sudoers

    std_message "Installing packages" "INFO"
    $_YUM -y install epel-release which sudo rpm-build
    $_YUM -y install python3 python3-pip python3-setuptools python3-devel

    std_message "Upgrade pip, setuptools" "INFO"
    sudo -H $_PIP install -U pip setuptools

    std_message "pip install pygments" "INFO"
    sudo -H $_PIP install -U pygments

    std_message "Coping setuptools lib from /usr/local/lib to /usr/lib/" "INFO"
    sudo cp -r /usr/local/lib/python3.*/site-packages/setuptools* /usr/lib/python3.*/site-packages/

    std_message "Coping pkg_resources lib from /usr/local/lib to /usr/lib/" "INFO"
    sudo cp -r /usr/local/lib/python3.*/site-packages/pkg_resources* /usr/lib/python3.*/site-packages/

    std_message "Coping pygments from /usr/local/lib64 to git_root" "INFO"
    sudo cp -r /usr/local/lib64/python3.*/site-packages/Pygments*  .
	sudo cp -r /usr/local/lib64/python3.*/site-packages/pygments*  .

    # python3 build process
    $_PYTHON3_PATH setup_rpm.py bdist_rpm --requires=${_REQUIRES} \
                                          --python='/usr/bin/python3' \
                                          --post-install=${_POSTINSTALL}

    if export_package; then
        exit 0
    else
        exit 1
    fi
else
    std_message "Not a Redhat-based Linux distribution. Exit" "WARN"
    exit 1
fi

exit 0