#! /usr/bin/env python
#
# Copyright (C) 2013-2015 S3IT, University of Zurich
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
import json
import os
import sys

from elasticluster.configuration import Configuration
from elasticluster.validate import hostname

# stdlib imports
from abc import ABCMeta, abstractmethod
from fnmatch import fnmatch

# Elasticluster imports
from elasticluster import log
from elasticluster.exceptions import ConfigurationError, NodeNotFound
from elasticluster.utils import confirm_or_abort


class AbstractCommand(object):
    """
    Defines the general contract every command has to fulfill in
    order to be recognized by the arguments list and executed
    afterwards.
    """
    __metaclass__ = ABCMeta

    @abstractmethod
    def __init__(self, subparsers):
        pass

    def parse(self, params):
        self.params = params

    @abstractmethod
    def execute(self):
        """
        This method is executed after a command was recognized and may
        vary in its behavior.
        """
        pass

    def __call__(self):
        return self.execute()

    def pre_run(self):
        """
        Overrides this method to execute any pre-run code, especially
        to check any command line options.
        """
        pass


class Start(AbstractCommand):
    """
    Create a new cluster using the given cluster template.
    """

    def __init__(self, subparsers):
        super(Start, self).__init__(subparsers)
        parser = subparsers.add_parser("start", description=self.__doc__, help="Create a cluster using the "
                                                                               "supplied configuration.")
        parser.set_defaults(func=self)
        parser.add_argument('cluster', help="Type of cluster. It refers to a configuration stanza [cluster/<name>]")
        parser.add_argument('-n', '--name', dest='cluster_name', help="Name of the cluster.")
        parser.add_argument('--nodes', metavar='N1:GROUP[,N2:GROUP2,...]', help="Override the values in of the "
                                                                                "configuration file and starts `N1` "
                                                                                "nodes of group `GROUP`,N2 of GROUP2 "
                                                                                "etc...")
        parser.add_argument('--no-setup', action="store_true", default=False, help="Only start the cluster, "
                                                                                   "do not configure it")

    def pre_run(self):
        self.params.extra_conf = {}
        try:
            if self.params.nodes:
                nodes = self.params.nodes.split(',')
                for nspec in nodes:
                    n, group = nspec.split(':')
                    if not n.isdigit():
                        raise ConfigurationError("Invalid syntax for option `--nodes`: `%s` is not an integer." % n)
                    n = int(n)
                    self.params.extra_conf[group + '_nodes'] = n
        except ValueError:
            raise ConfigurationError("Invalid argument for option --nodes: %s" % self.params.nodes)

    def execute(self):
        """
        Starts a new cluster.
        """
        try:
            if self.params.cluster_name:
                hostname(self.params.cluster_name)
            else:
                hostname(self.params.cluster)
        except ValueError as e:
            if self.params.cluster_name:
                log.error('incorrect hostname given as cluster name: %s', e)
            else:
                log.error('cannot use template name as cluster name, it contains invalid chars: %s', e)
            sys.exit(1)

        log.info('trying to start cluster %s (%s)', self.params.cluster_name, self.params.cluster)
        configuration = Configuration(self.params.config, self.params.storage)
        cluster = next(configuration.get_cluster(self.params.cluster, self.params.cluster_name), None)

        if not cluster:
            log.error('no valid configuration found for %s', self.params.cluster)
            return

        # overwrite configuration
        for option, value in self.params.extra_conf.items():
            cluster.options[option] = value

        if len(cluster.nodes) > 0:
            log.info('cluster %s already started', cluster.name)
            return

        log.info('cluster %s not found, starting it, this may take a while', cluster.name)
        cluster.start()

        if self.params.no_setup:
            log.warn("NOT configuring the cluster as requested.")
        else:
            log.info("Configuring the cluster. this may take a while...")
            ret = cluster.configure()
            if ret:
                log.info("Your cluster is ready!")
            else:
                log.warn("YOUR CLUSTER IS NOT READY YET!")
        print(cluster)


class Stop(AbstractCommand):
    """
    Stop a cluster and terminate all associated virtual machines.
    """

    def __init__(self, subparsers):
        super(Stop, self).__init__(subparsers)
        parser = subparsers.add_parser("stop", description=self.__doc__, help="Stop a cluster and all associated"
                                                                              " VM instances.")
        parser.set_defaults(func=self)
        parser.add_argument('cluster', help='name of the cluster')
        # parser.add_argument('--force', action="store_true", default=False,
        #                     help="Remove the cluster even if not all the nodes"
        #                          " have been terminated properly.")
        # parser.add_argument('--wait', action="store_true", default=False,
        #                     help="Wait for all nodes to be properly terminated.")
        parser.add_argument('--yes', '-y', action="store_true", default=False,
                            help="Assume `yes` to all queries and do "
                                 "not prompt.")

    def execute(self):
        """
        Stops the cluster if it's running.
        """
        log.info('trying to stop cluster %s', self.params.cluster)
        cluster = Configuration.find(self.params.config, self.params.cluster, self.params.storage)
        if not cluster:
            log.error("Cannot stop cluster `%s`, no active configuration found", self.params.cluster)
            return os.EX_NOINPUT

        if not self.params.yes:
            confirm_or_abort("Do you want really want to stop cluster `{cluster_name}`?"
                             .format(cluster_name=self.params.cluster), msg="Aborting upon user request.")
        log.info("Destroying cluster `%s` ...", self.params.cluster)
        cluster.stop()


class ResizeCluster(AbstractCommand):
    """
    Resize the cluster by adding or removing compute nodes.
    """

    def __init__(self, subparsers):
        super(ResizeCluster, self).__init__(subparsers)
        parser = subparsers.add_parser("resize", description=self.__doc__, help="Resize a cluster by adding or "
                                                                                "removing compute nodes.")
        parser.set_defaults(func=self)
        parser.add_argument('cluster', help='name of the cluster')
        parser.add_argument('-a', '--add', metavar='N1:GROUP1[,N2:GROUP2]', help="Add N1 nodes of group GROUP1, "
                                                                                 "N2 of group GROUP2 etc...")
        parser.add_argument('-r', '--remove', metavar='N1:GROUP1[,N2:GROUP2]', help="Remove the highest-numbered N1 "
                                                                                    "nodes of group GROUP1, N2 of group"
                                                                                    " GROUP2 etc...")
        parser.add_argument('--no-setup', action="store_true", default=False, help="Only start the cluster, do not "
                                                                                   "configure it")
        parser.add_argument('--yes', action="store_true", default=False, help="Assume `yes` to all queries and do not "
                                                                              "prompt.")

    def pre_run(self):
        self.params.nodes_to_add = {}
        self.params.nodes_to_remove = {}
        try:
            if self.params.add:
                nodes = self.params.add.split(',')
                for nspec in nodes:
                    n, group = nspec.split(':')
                    if not n.isdigit():
                        raise ConfigurationError("Invalid syntax for option `--nodes`: `%s` is not an integer." % n)
                    self.params.nodes_to_add[group] = int(n)

            if self.params.remove:
                nodes = self.params.remove.split(',')
                for nspec in nodes:
                    n, group = nspec.split(':')
                    self.params.nodes_to_remove[group] = int(n)

        except ValueError as ex:
            raise ConfigurationError("Invalid syntax for argument: %s" % ex)

    def execute(self):
        log.info('trying to resize cluster %s', self.params.cluster)
        cluster = Configuration.find(self.params.config, self.params.cluster, self.params.storage)
        if not cluster:
            log.error("Cannot resize cluster `%s`, no active configuration found", self.params.cluster)
            return os.EX_NOINPUT

        for grp in self.params.nodes_to_add:
            log.info("Adding %d %s node(s) to the cluster", self.params.nodes_to_add[grp], grp)
            cluster.add(node_type=grp, count=self.params.nodes_to_add[grp], wait=True)
            if self.params.no_setup:
                log.warn("NOT configuring the new nodes as requested.")
        if self.params.nodes_to_add:
            cluster.configure()

        for grp in self.params.nodes_to_remove:
            n_to_rm = self.params.nodes_to_remove[grp]
            log.warn("Removing %d %s node(s) from the cluster.", n_to_rm, grp)
            if not self.params.yes:
                confirm_or_abort("Do you really want to remove them?", msg="Aborting upon user request.")
            cluster.remove(node_type=grp, count=n_to_rm)

        print(cluster)


class RemoveNode(AbstractCommand):
    """
    Remove a specific node from the cluster
    """

    def __init__(self, subparsers):
        super(RemoveNode, self).__init__(subparsers)
        parser = subparsers.add_parser("remove-node", description=self.__doc__, help="Remove a specific node "
                                                                                     "from the cluster")
        parser.set_defaults(func=self)
        parser.add_argument('cluster', help='Cluster from which the node must be removed')
        parser.add_argument('node', help='Name of node to be removed')
        parser.add_argument('--yes', action="store_true", default=False, help="Assume `yes` to all queries and do not "
                                                                              "prompt.")

    def execute(self):
        log.info('trying to remove node %s from cluster %s', self.params.node, self.params.cluster)
        cluster = Configuration.find(self.params.config, self.params.cluster, self.params.storage)
        if not cluster:
            log.error("Cannot remove node from cluster `%s`, no active configuration found", self.params.cluster)
            return os.EX_NOINPUT

        if not self.params.yes:
            confirm_or_abort("Do you really want to remove node `{}`?".format(self.params.node),
                             msg="Aborting upon user "
                                 "request.")

        cluster.remove_by_name(self.params.node)


class ListClusters(AbstractCommand):
    """
    Print a list of all clusters that have been started.
    """

    def __init__(self, subparsers):
        super(ListClusters, self).__init__(subparsers)
        parser = subparsers.add_parser("list", description=self.__doc__, help="List all started clusters.")
        parser.set_defaults(func=self)

    def execute(self):
        log.info("The following clusters have been started.\n"
                 "Please note that there's no guarantee that they are fully configured:")
        for cluster in Configuration.parse(self.params.config, self.params.storage):
            print(cluster)


class ListTemplates(AbstractCommand):
    """
    List the available templates defined in the configuration file.
    """

    def __init__(self, subparsers):
        super(ListTemplates, self).__init__(subparsers)
        parser = subparsers.add_parser("list-templates", description=self.__doc__, help="Show the templates "
                                                                                        "defined in the "
                                                                                        "configuration file.")
        parser.set_defaults(func=self)
        parser.add_argument('clusters', nargs="*", help="List only this cluster. Accepts globbing.")

    def execute(self):
        templates = Configuration.templates(self.params.config, self.params.storage)
        log.debug(templates)
        log.info("%d cluster templates found in configuration file.", len(templates))

        running = []
        for clusters in Configuration.parse(self.params.config, self.params.storage):
            if clusters.template not in [r.template for r in running]:
                running.append(clusters)

        if self.params.clusters:
            filtered_templates = {}
            for pattern in self.params.clusters:
                for template in [t for t in templates.keys() if fnmatch(t, pattern)]:
                    filtered_templates[template] = templates[template]
            templates = filtered_templates
            log.info("%d cluster templates found matching pattern(s) '%s'", len(templates),
                     str.join(", ", self.params.clusters))

        for template in templates.keys():
            print('\ntemplate: {}'.format(template))
            for node_type, amount in templates.get(template):
                print('- {} nodes: {}'.format(node_type, amount))
            if len([r for r in running if r.template == template]) > 0:
                print('-- active clusters --')
                for c in [r for r in running if r.template == template]:
                    print(' * {}'.format(c.name))
            else:
                print('-- no active clusters --')
            print('\n')


class ListNodes(AbstractCommand):
    """
    Show some information on all the nodes belonging to a given
    cluster.
    """

    def __init__(self, subparsers):
        super(ListNodes, self).__init__(subparsers)
        parser = subparsers.add_parser("list-nodes", description=self.__doc__, help="Show information about the "
                                                                                    "nodes in the cluster")
        parser.set_defaults(func=self)
        parser.add_argument('cluster', help='name of the cluster')
        parser.add_argument('--json', action='store_true', help="Produce JSON output")
        parser.add_argument('--pretty-json', action='store_true', help="Produce *indented* JSON output (more human "
                                                                       "readable than --json)")

    def execute(self):
        """
        Lists all nodes within the specified cluster with certain
        information like id and ip.
        """
        cluster = Configuration.find(self.params.config, self.params.cluster, self.params.storage)
        if not cluster:
            log.error("Remove node from cluster `%s`, no active configuration found", self.params.cluster)
            return os.EX_NOINPUT

        if self.params.pretty_json:
            log.info(json.dumps(cluster, default=dict, indent=4))
        elif self.params.json:
            log.info(json.dumps(cluster, default=dict))
        else:
            print(cluster)
            print('Details of nodes:')
            print('-------------------------')
            for node in cluster.nodes:
                ips = ', '.join(node.private_ips + node.public_ips)
                print('- name         : {}\n'
                      '  state        : {}\n'
                      '  ip addresses : {}\n'
                      '  id           : {}\n'
                      '  size         : {}\n'
                      '  image        : {}\n'.format(node.name,
                                                     node.state,
                                                     ips,
                                                     node.id,
                                                     node.size,
                                                     node.image))
            print('-------------------------')


class SetupCluster(AbstractCommand):
    """
    Setup the given cluster by calling the setup provider defined for
    this cluster.
    """

    def __init__(self, subparsers):
        super(SetupCluster, self).__init__(subparsers)
        parser = subparsers.add_parser("setup", description=self.__doc__, help="Configure the cluster.")
        parser.set_defaults(func=self)
        parser.add_argument('cluster', help='name of the cluster')
        parser.add_argument('extra', nargs='*', default=[], help=("Extra arguments will be appended (unchanged) to the "
                                                                  "setup provider command-line invocation."))

    def execute(self):
        log.info('trying to setup cluster %s', self.params.cluster)
        cluster = Configuration.find(self.params.config, self.params.cluster, self.params.storage)
        if not cluster:
            log.error("Cannot setup cluster `%s`, no active configuration found", self.params.cluster)
            return os.EX_NOINPUT

        ret = cluster.configure(self.params.extra)
        if ret:
            log.info("Your cluster is ready!")
        else:
            log.warn("SETUP RETURNED FAILURE! YOUR CLUSTER IS NOT READY YET!")

        print(cluster)


class SshFrontend(AbstractCommand):
    """
    Connect to the frontend of the cluster using `ssh`.
    """

    def __init__(self, subparsers):
        super(SshFrontend, self).__init__(subparsers)
        parser = subparsers.add_parser("ssh", description=self.__doc__, help="Connect to the frontend of the "
                                                                             "cluster using the `ssh` command")
        parser.set_defaults(func=self)
        parser.add_argument('cluster', help='name of the cluster')
        parser.add_argument('-n', '--node', metavar='HOSTNAME', dest='ssh_to', help="Name of node you want to ssh to. "
                                                                                    "By default, the first node of the "
                                                                                    "`ssh_to` option group is used.")
        parser.add_argument('ssh_args', metavar='args', nargs='*', help="Execute the following command on the remote "
                                                                        "machine instead of opening an interactive "
                                                                        "shell.")

    def execute(self):
        cluster = Configuration.find(self.params.config, self.params.cluster, self.params.storage)
        if not cluster:
            log.error("Cannot ssh to cluster `%s`, no active configuration found", self.params.cluster)
            return os.EX_NOINPUT

        ssh_to = cluster.ssh_node()
        if self.params.ssh_to:
            target = next(iter(n for n in cluster.nodes if n.name == self.params.ssh_to), None)
            if target:
                ssh_to = target
        try:
            ip, port = cluster.node_ssh_address_and_port(ssh_to.name)
            username = cluster.login.options.get('image_user')
            known_hosts_file = '/dev/null'
            if os.path.exists(cluster.known_host_file):
                known_hosts_file = cluster.known_host_file
            ssh_cmdline = ["ssh",
                           "-i", cluster.login.options.get('user_key_private'),
                           "-o", "UserKnownHostsFile=%s" % known_hosts_file,
                           "-o", "StrictHostKeyChecking=yes",
                           "-p", str(port),
                           '%s@%s' % (username, ip)]
            ssh_cmdline.extend(self.params.ssh_args)
            log.debug("Running command `%s`" % str.join(' ', ssh_cmdline))
            os.execlp("ssh", *ssh_cmdline)
        except NodeNotFound as ex:
            log.error("Unable to connect to the frontend node: %s" % str(ex))
            sys.exit(1)


class SftpFrontend(AbstractCommand):
    """
    Open an SFTP session to the cluster frontend host.
    """

    def __init__(self, subparsers):
        super(SftpFrontend, self).__init__(subparsers)
        parser = subparsers.add_parser("sftp", description=self.__doc__, help="Open an SFTP session to the "
                                                                              "cluster frontend host.")
        parser.set_defaults(func=self)
        parser.add_argument('cluster', help='name of the cluster')
        parser.add_argument('-n', '--node', metavar='HOSTNAME', dest='ssh_to', help="Name of node you want to ssh to. "
                                                                                    "By default, the first node of the "
                                                                                    "`ssh_to` option group is used.")
        parser.add_argument('sftp_args', metavar='args', nargs='*', help="Arguments to pass to ftp, instead of opening "
                                                                         "an interactive shell.")

    def execute(self):
        cluster = Configuration.find(self.params.config, self.params.cluster, self.params.storage)
        if not cluster:
            log.error("Cannot ssh to cluster `%s`, no active configuration found", self.params.cluster)
            return os.EX_NOINPUT

        ssh_to = cluster.ssh_node()
        if self.params.ssh_to:
            target = next(iter(n for n in cluster.nodes if n.name == self.params.ssh_to), None)
            if target:
                ssh_to = target
        try:
            ip, port = cluster.node_ssh_address_and_port(ssh_to.name)
            username = cluster.login.options.get('image_user')
            known_hosts_file = '/dev/null'
            if os.path.exists(cluster.known_host_file):
                known_hosts_file = cluster.known_host_file
            sftp_cmdline = ["sftp",
                            "-o", "UserKnownHostsFile=%s" % known_hosts_file,
                            "-o", "StrictHostKeyChecking=yes",
                            "-o", "IdentityFile=%s" % cluster.login.options.get('user_key_private'),
                            "-P", str(port)]
            sftp_cmdline.extend(self.params.sftp_args)
            sftp_cmdline.append('%s@%s' % (username, ip))
            os.execlp("sftp", *sftp_cmdline)
        except NodeNotFound as ex:
            log.error("Unable to connect to the frontend node: %s" % str(ex))
            sys.exit(1)

# class GC3PieConfig(AbstractCommand):
#     """
#     Print a GC3Pie configuration snippet for a specific cluster
#     """
#
#     def setup(self, subparsers):
#         parser = subparsers.add_parser("gc3pie-config", help="Print a GC3Pie configuration snippet.",
#                                        description=self.__doc__)
#         parser.set_defaults(func=self)
#         parser.add_argument('cluster', help='name of the cluster')
#         parser.add_argument('-a', '--append', metavar='FILE', help='append configuration to file FILE')
#
#     def execute(self):
#         """
#         Load the cluster and build a GC3Pie configuration snippet.
#         """
#         cluster = Configuration.find(self.params.config, self.params.cluster, self.params.storage)
#         if not cluster:
#             log.error("Cannot ssh to cluster `%s`, no active configuration found", self.params.cluster)
#             return os.EX_NOINPUT
#
#         from elasticluster.gc3pie_config import create_gc3pie_config_snippet
#
#         if self.params.append:
#             path = os.path.expanduser(self.params.append)
#             try:
#                 fd = open(path, 'a')
#                 fd.write(create_gc3pie_config_snippet(cluster))
#                 fd.close()
#             except IOError as ex:
#                 log.error("Unable to write configuration to file %s: %s", path, ex)
#         else:
#             print(create_gc3pie_config_snippet(cluster))

# class ExportCluster(AbstractCommand):
#     """Save cluster definition in the given file.  A `.zip` extension is
#     appended if it's not already there.  By default, the output file is
#     named like the cluster.
#     """
#
#     def setup(self, subparsers):
#         parser = subparsers.add_parser(
#             "export", help="Export a cluster as zip file",
#             description=self.__doc__)
#         parser.set_defaults(func=self)
#         parser.add_argument('--overwrite', action='store_true',
#                             help='Overwritep ZIP file if it exists.')
#         parser.add_argument('--save-keys', action='store_true',
#                             help="Also store public and *private* ssh keys. "
#                             "WARNING: this will copy sensible data. Use with "
#                             "caution!")
#         parser.add_argument(
#             '-o', '--output-file', metavar='FILE', dest='zipfile',
#             help="Output file to be used. By default the cluster is exported "
#             "into a <cluster>.zip file where <cluster> is the cluster name.")
#         parser.add_argument('cluster', help='Name of the cluster to export.')
#
#     def pre_run(self):
#         # find proper path to zip file
#         if not self.params.zipfile:
#             self.params.zipfile = self.params.cluster + '.zip'
#
#         if not self.params.zipfile.endswith('.zip'):
#             self.params.zipfile += '.zip'
#
#     def execute(self):
#         creator = make_creator(self.params.config, storage_path=self.params.storage)
#
#         try:
#             cluster = creator.load_cluster(self.params.cluster)
#         except ClusterNotFound:
#             log.error("Cluster `%s` not found in storage dir %s."
#                       % (self.params.cluster, self.params.storage))
#             sys.exit(1)
#
#         if os.path.exists(self.params.zipfile) and not self.params.overwrite:
#             log.error("ZIP file `%s` already exists." % self.params.zipfile)
#             sys.exit(1)
#
#         with ZipFile(self.params.zipfile, 'w') as zipfile:
#             # The root of the zip file will contain:
#             # * the storage file
#             # * the known_hosts file
#             # * ssh public and prived keys, if --save-keys is used
#             #
#             # it will NOT contain the ansible inventory file, as this
#             # is automatically created when needed.
#             #
#             # Also, if --save-keys is used and there is an host with a
#             # different ssh private/public key than the default, they
#             # will be saved in:
#             #
#             #   ./<cluster>/<group>/<nodename>/
#             #
#             def verbose_add(fname, basedir='', comment=None):
#                 zipname = basedir + os.path.basename(fname)
#                 log.info("Adding '%s' as '%s'" % (fname, zipname))
#                 zipfile.write(fname, zipname)
#                 if comment:
#                     info = zipfile.getinfo(zipname)
#                     info.comment = comment
#
#             try:
#                 verbose_add(cluster.storage_file, comment='cluster-file')
#                 verbose_add(cluster.known_hosts_file, comment='known_hosts')
#                 if self.params.save_keys:
#                     # that's sensible stuff, let's ask permission.
#                     print("""
# ==========================
# WARNING! WARNING! WARNING!
# ==========================
# You are about to add your SSH *private* key to the
# ZIP archive. These are sensible data: anyone with
# access to the ZIP file will have access to any host
# where this private key has been deployed.
#
#                     """)
#                     confirm_or_abort(
#                         "Are you sure you still want to copy them?",
#                         msg="Aborting upon user request.")
#
#                     # Also save all the public and private keys we can find.
#
#                     # Cluster keys
#                     verbose_add(cluster.user_key_public)
#                     verbose_add(cluster.user_key_private)
#
#                     # Node keys, if found
#                     for node in cluster.get_all_nodes():
#                         if node.user_key_public != cluster.user_key_public:
#                             verbose_add(node.user_key_public,
#                                         "%s/%s/%s/" % (cluster.name,
#                                                        node.kind,
#                                                        node.name))
#                     for node in cluster.get_all_nodes():
#                         if node.user_key_private != cluster.user_key_private:
#                             verbose_add(node.user_key_private,
#                                         "%s/%s/%s/" % (cluster.name,
#                                                        node.kind,
#                                                        node.name))
#             except OSError as ex:
#                 # A file is probably missing!
#                 log.error("Fatal error: cannot add file %s to zip archive: %s." % (ex.filename, ex))
#                 sys.exit(1)
#
#         print("Cluster '%s' correctly exported into %s" % (cluster.name, self.params.zipfile))
#
#
# class ImportCluster(AbstractCommand):
#     """Import a cluster definition from FILE into local storage.
#     After running this command, it will be possible to operate
#     on the imported cluster as if it had been created locally.
#
#     The FILE to be imported must have been created with
#     `elasticluster export`.
#
#     If a cluster already exists with the same name of the one
#     being imported, the import operation is aborted and
#     `elasticluster` exists with an error.
#     """
#
#     def setup(self, subparsers):
#         parser = subparsers.add_parser(
#             "import", help="Import a cluster from a zip file",
#             description=self.__doc__)
#         parser.set_defaults(func=self)
#         parser.add_argument('--rename', metavar='NAME',
#                             help="Rename the cluster during import.")
#         parser.add_argument("file", help="Path to ZIP file produced by "
#                             "`elasticluster export`.")
#     def execute(self):
#         creator = make_creator(self.params.config, storage_path=self.params.storage)
#         repo = creator.create_repository()
#         tmpdir = tempfile.mkdtemp()
#         log.debug("Using temporary directory %s" % tmpdir)
#         tmpconf = make_creator(self.params.config, storage_path=tmpdir)
#         tmprepo = tmpconf.create_repository()
#
#         rc=0
#         # Read the zip file.
#         try:
#             with ZipFile(self.params.file, 'r') as zipfile:
#                 # Find main cluster file
#                 # create cluster object from it
#                 log.debug("ZIP file %s opened" % self.params.file)
#                 cluster = None
#                 zipfile.extractall(tmpdir)
#                 newclusters = tmprepo.get_all()
#                 cluster = newclusters[0]
#                 cur_clusternames = [c.name for c in repo.get_all()]
#                 oldname = cluster.name
#                 newname = self.params.rename
#                 if self.params.rename:
#                     cluster.name = self.params.rename
#                     for node in cluster.get_all_nodes():
#                         node.cluster_name = cluster.name
#                 if cluster.name in cur_clusternames:
#                     raise Exception(
#                         "A cluster with name %s already exists. Use "
#                         "option --rename to rename the cluster to be "
#                         "imported." % cluster.name)
#
#                         # Save the cluster in the new position
#                 cluster.repository = repo
#                 repo.save_or_update(cluster)
#                 dest = cluster.repository.storage_path
#
#                 # Copy the known hosts
#                 srcfile = os.path.join(tmpdir, oldname+'.known_hosts')
#                 destfile = os.path.join(dest, cluster.name+'.known_hosts')
#                 shutil.copy(srcfile, destfile)
#
#                 # Copy the ssh keys, if present
#                 for attr in ('user_key_public', 'user_key_private'):
#                     keyfile = getattr(cluster, attr)
#                     keybase = os.path.basename(keyfile)
#                     srcfile = os.path.join(tmpdir, keybase)
#                     if os.path.isfile(srcfile):
#                         log.info("Importing key file %s" % keybase)
#                         destfile = os.path.join(dest, keybase)
#                         shutil.copy(srcfile, destfile)
#                         setattr(cluster, attr, destfile)
#
#                     for node in cluster.get_all_nodes():
#                         nodekeyfile = getattr(node, attr)
#                         # Check if it's different from the main key
#                         if nodekeyfile != keyfile \
#                            and os.path.isfile(nodekeyfile):
#                             destdir = os.path.join(dest,
#                                                    cluster.name,
#                                                    node.kind,
#                                                    node.name)
#                             nodekeybase = os.path.basename(nodekeyfile)
#                             log.info("Importing key file %s for node %s" %
#                                      (nodekeybase, node.name))
#                             if not os.path.isdir(destdir):
#                                 os.makedirs(destdir)
#                             # Path to key in zip file
#                             srcfile = os.path.join(tmpdir,
#                                                    oldname,
#                                                    node.kind,
#                                                    node.name,
#                                                    nodekeybase)
#                             destfile = os.path.join(destdir, nodekeybase)
#                             shutil.copy(srcfile, destfile)
#                         # Always save the correct destfile
#                         setattr(node, attr, destfile)
#
#                 repo.save_or_update(cluster)
#                 if not cluster:
#                     log.error("ZIP file %s does not contain a valid cluster." % self.params.file)
#                     rc = 2
#
#                 # Check if a cluster already exists.
#                 # if not, unzip the needed files, and update ssh key path if needed.
#         except Exception as ex:
#             log.error("Unable to import from zipfile %s: %s" % (self.params.file, ex))
#             rc=1
#         finally:
#             if os.path.isdir(tmpdir):
#                 shutil.rmtree(tmpdir)
#             log.info("Cleaning up directory %s" % tmpdir)
#
#         if rc == 0:
#             print("Successfully imported cluster from ZIP %s to %s" % (self.params.file, repo.storage_path))
#         sys.exit(rc)
