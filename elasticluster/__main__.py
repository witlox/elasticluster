#! /usr/bin/env python
#
#   Copyright (C) 2013-2016 S3IT, University of Zurich
#
#   This program is free software: you can redistribute it and/or modify
#   it under the terms of the GNU General Public License as published by
#   the Free Software Foundation, either version 3 of the License, or
#   (at your option) any later version.
#
#   This program is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#   GNU General Public License for more details.
#
#   You should have received a copy of the GNU General Public License
#   along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
import argparse
import logging
import os
import shutil
import sys
import traceback
import warnings

import coloredlogs
from pkg_resources import resource_filename

import elasticluster.utils as utils
from elasticluster import log
from elasticluster.subcommands import AbstractCommand


DEFAULT_CONFIG_PATH = "~/.elasticluster/config"


def main():
    parser = argparse.ArgumentParser('elasticluster', description='Elasticluster starts, stops, grows, and shrinks '
                                                                  'clusters on a cloud.')
    parser.add_argument('-v', '--verbose', action='count', default=0,
                        help="Increase verbosity. If at least four `-v` option "
                             "are given, elasticluster will create new VMs "
                             "sequentially instead of doing it in parallel.")
    parser.add_argument('-s', '--storage', metavar="PATH",
                        help="Path to the storage folder. (Default: `%(default)s`",
                        default='~/.elasticluster/storage')
    parser.add_argument('-c', '--config', metavar='PATH',
                        help=("Path to the configuration file;"
                              " default: `%(default)s`."
                              " If directory `PATH.d` exists,"
                              " all files matching"
                              " pattern `PATH.d/*.conf` are parsed."),
                        default=os.path.expandvars(os.path.expanduser(DEFAULT_CONFIG_PATH)))
    parser.add_argument('--version', action='store_true', help="Print version information and exit.")

    subparsers = parser.add_subparsers(title="COMMANDS", help=("Available commands. Run `elasticluster cmd --help` "
                                                               "to have information on command `cmd`."))

    if '--version' in sys.argv:
        import pkg_resources
        version = pkg_resources.get_distribution('elasticluster').version
        print('elasticluster version {}'.format(version))
        sys.exit(0)

    commands = []
    for command in AbstractCommand.__subclasses__():
        commands.append(command(subparsers))

    args = parser.parse_args()

    for command in commands:
        command.parse(args)

    # print *all* Python warnings through the logging subsystem
    warnings.resetwarnings()
    warnings.simplefilter('once')
    utils.redirect_warnings(logger='gc3.elasticluster')

    # Set verbosity level
    log_level = max(logging.DEBUG, logging.WARNING - 10 * max(0, args.verbose))
    log.setLevel(log_level)
    if args.verbose > 1:
        coloredlogs.install(logger=log, level=log_level, fmt='%(asctime)s '
                                                             '%(hostname)s '
                                                             '%(name)s[%(process)d] '
                                                             '%(module)s.'
                                                             '%(funcName)s('
                                                             '%(lineno)s) '
                                                             '%(levelname)s %(message)s')
    else:
        coloredlogs.install(logger=log, level=log_level)

    # In debug mode, avoid forking
    if args.verbose > 3:
        log.DO_NOT_FORK = True
        log.raiseExceptions = True
        log.very_verbose = True

    if not os.path.isdir(args.storage):
        # We do not create *all* the parents, but we do create the
        # directory if we can.
        try:
            os.makedirs(args.storage)
        except OSError as ex:
            sys.stderr.write("Unable to create storage directory: %s\n" % (str(ex)))
            sys.exit(1)

    # If no configuration file was specified and default does not exists and the user did not create a config dir...
    if not os.path.isfile(args.config) and not os.path.isdir(args.config + '.d'):
        if args.config == os.path.expandvars(os.path.expanduser(DEFAULT_CONFIG_PATH)):
            # Copy the default configuration file to the user's home
            if not os.path.exists(os.path.dirname(args.config)):
                os.mkdir(os.path.dirname(args.config))
            template = resource_filename('elasticluster', 'share/etc/config.template')
            log.warning("Deploying default configuration file to %s.", args.config)
            shutil.copyfile(template, args.config)
        else:
            # Exit if supplied configuration file does not exists.
            if not os.path.isfile(args.config):
                sys.stderr.write("Unable to read configuration file `%s`.\n" % args.config)
                sys.exit(1)

    try:
        args.func.pre_run()
    except KeyboardInterrupt:
        sys.stderr.write("WARNING: execution interrupted by the user! Your clusters may be in inconsistent state!")
        sys.exit(1)
    except Exception as err:
        log.error("Error: %s", err)
        if args.verbose > 3:
            traceback.print_exc()
        sys.exit(1)

    try:
        args.func.execute()
    except KeyboardInterrupt:
        sys.stderr.write("WARNING: execution interrupted by the user! Your clusters may be in inconsistent state!")
        sys.exit(1)
    except Exception as err:
        log.error("Error: %s", err)
        if args.verbose > 3:
            traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
