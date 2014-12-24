# -*- coding: utf-8 -*-

# daemon/runner.py
# Part of ‘python-daemon’, an implementation of PEP 3143.
#
# Copyright © 2009–2014 Ben Finney <ben+python@benfinney.id.au>
# Copyright © 2007–2008 Robert Niederreiter, Jens Klein
# Copyright © 2003 Clark Evans
# Copyright © 2002 Noah Spurrier
# Copyright © 2001 Jürgen Hermann
#
# This is free software: you may copy, modify, and/or distribute this work
# under the terms of the Apache License, version 2.0 as published by the
# Apache Software Foundation.
# No warranty expressed or implied. See the file ‘LICENSE.ASF-2’ for details.

""" Daemon runner library.
    """

from __future__ import (absolute_import, unicode_literals)

import sys
import os
import signal
import errno

from . import pidlockfile
from .daemon import DaemonContext

try:
    # Python 2 has both ‘str’ (bytes) and ‘unicode’.
    basestring
    unicode
except NameError:
    # Python 3 names the Unicode data type ‘str’.
    basestring = str
    unicode = str


class DaemonRunnerError(Exception):
    """ Abstract base class for errors from DaemonRunner. """

class DaemonRunnerInvalidActionError(ValueError, DaemonRunnerError):
    """ Raised when specified action for DaemonRunner is invalid. """

class DaemonRunnerStartFailureError(RuntimeError, DaemonRunnerError):
    """ Raised when failure starting DaemonRunner. """

class DaemonRunnerStopFailureError(RuntimeError, DaemonRunnerError):
    """ Raised when failure stopping DaemonRunner. """


class DaemonRunner(object):
    """ Controller for a callable running in a separate background process.

        The first command-line argument is the action to take:

        * 'start': Become a daemon and call `app.run()`.
        * 'stop': Exit the daemon process specified in the PID file.
        * 'restart': Stop, then start.

        """

    start_message = "started with pid %(pid)d"

    def __init__(self, app):
        """ Set up the parameters of a new runner.

            :param app: The application instance; see below.
            :return: ``None``.

            The `app` argument must have the following attributes:

            * `stdin_path`, `stdout_path`, `stderr_path`: Filesystem paths
              to open and replace the existing `sys.stdin`, `sys.stdout`,
              `sys.stderr`.

            * `pidfile_path`: Absolute filesystem path to a file that will
              be used as the PID file for the daemon. If ``None``, no PID
              file will be used.

            * `pidfile_timeout`: Used as the default acquisition timeout
              value supplied to the runner's PID lock file.

            * `run`: Callable that will be invoked when the daemon is
              started.

            """
        self.parse_args()
        self.app = app
        self.daemon_context = DaemonContext()
        self.daemon_context.stdin = open(app.stdin_path, 'rt')
        self.daemon_context.stdout = open(app.stdout_path, 'w+t')
        self.daemon_context.stderr = open(
                app.stderr_path, 'w+t', buffering=0)

        self.pidfile = None
        if app.pidfile_path is not None:
            self.pidfile = make_pidlockfile(
                    app.pidfile_path, app.pidfile_timeout)
        self.daemon_context.pidfile = self.pidfile

    def _usage_exit(self, argv):
        """ Emit a usage message, then exit.

            :param argv: The command-line arguments used to invoke the
                program, as a sequence of strings.
            :return: ``None``.

            """
        progname = os.path.basename(argv[0])
        usage_exit_code = 2
        action_usage = "|".join(self.action_funcs.keys())
        message = "usage: %(progname)s %(action_usage)s" % vars()
        emit_message(message)
        sys.exit(usage_exit_code)

    def parse_args(self, argv=None):
        """ Parse command-line arguments.

            :param argv: The command-line arguments used to invoke the
                program, as a sequence of strings.
            :return: ``None``.

            The parser expects the first argument as the program name, the
            second argument as the action to perform.

            If the parser fails to parse the arguments, emit a usage
            message and exit the program.

            """
        if argv is None:
            argv = sys.argv

        min_args = 2
        if len(argv) < min_args:
            self._usage_exit(argv)

        self.action = unicode(argv[1])
        if self.action not in self.action_funcs:
            self._usage_exit(argv)

    def _start(self):
        """ Open the daemon context and run the application.

            :return: ``None``.
            :raises DaemonRunnerStartFailureError: If the PID file cannot
                be locked by this process.

            """
        if is_pidfile_stale(self.pidfile):
            self.pidfile.break_lock()

        try:
            self.daemon_context.open()
        except pidlockfile.AlreadyLocked:
            pidfile_path = self.pidfile.path
            raise DaemonRunnerStartFailureError(
                    "PID file %(pidfile_path)r already locked" % vars())

        pid = os.getpid()
        message = self.start_message % vars()
        emit_message(message)

        self.app.run()

    def _terminate_daemon_process(self):
        """ Terminate the daemon process specified in the current PID file.

            :return: ``None``.
            :raises DaemonRunnerStopFailureError: If terminating the daemon
                fails with an OS error.

            """
        pid = self.pidfile.read_pid()
        try:
            os.kill(pid, signal.SIGTERM)
        except OSError, exc:
            raise DaemonRunnerStopFailureError(
                    "Failed to terminate %(pid)d: %(exc)s" % vars())

    def _stop(self):
        """ Exit the daemon process specified in the current PID file.

            :return: ``None``.
            :raises DaemonRunnerStopFailureError: If the PID file is not
                already locked.

            """
        if not self.pidfile.is_locked():
            pidfile_path = self.pidfile.path
            raise DaemonRunnerStopFailureError(
                    "PID file %(pidfile_path)r not locked" % vars())

        if is_pidfile_stale(self.pidfile):
            self.pidfile.break_lock()
        else:
            self._terminate_daemon_process()

    def _restart(self):
        """ Stop, then start.
            """
        self._stop()
        self._start()

    action_funcs = {
            'start': _start,
            'stop': _stop,
            'restart': _restart,
            }

    def _get_action_func(self):
        """ Get the function for the specified action.

            :return: The function object corresponding to the specified
                action.
            :raises DaemonRunnerInvalidActionError: if the action is
               unknown.

            The action is specified by the `action` attribute, which is set
            during `parse_args`.

            """
        try:
            func = self.action_funcs[self.action]
        except KeyError:
            raise DaemonRunnerInvalidActionError(
                    "Unknown action: %(action)r" % vars(self))
        return func

    def do_action(self):
        """ Perform the requested action.

            :return: ``None``.

            The action is specified by the `action` attribute, which is set
            during `parse_args`.

            """
        func = self._get_action_func()
        func(self)


def emit_message(message, stream=None):
    """ Emit a message to the specified stream (default `sys.stderr`). """
    if stream is None:
        stream = sys.stderr
    stream.write("%(message)s\n" % vars())
    stream.flush()


def make_pidlockfile(path, acquire_timeout):
    """ Make a PIDLockFile instance with the given filesystem path. """
    if not isinstance(path, basestring):
        error = ValueError("Not a filesystem path: %(path)r" % vars())
        raise error
    if not os.path.isabs(path):
        error = ValueError("Not an absolute path: %(path)r" % vars())
        raise error
    lockfile = pidlockfile.TimeoutPIDLockFile(path, acquire_timeout)

    return lockfile


def is_pidfile_stale(pidfile):
    """ Determine whether a PID file is stale.

        :return: ``True`` iff the PID file is stale; otherwise ``False``.

        The PID file is “stale” if its contents are
        valid but do not match the PID of a currently-running process.

        """
    result = False

    pidfile_pid = pidfile.read_pid()
    if pidfile_pid is not None:
        try:
            os.kill(pidfile_pid, signal.SIG_DFL)
        except OSError, exc:
            if exc.errno == errno.ESRCH:
                # The specified PID does not exist.
                result = True

    return result


# Local variables:
# coding: utf-8
# mode: python
# End:
# vim: fileencoding=utf-8 filetype=python :
