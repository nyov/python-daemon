# -*- coding: utf-8 -*-

# daemon/pidlockfile.py
#
# Copyright © 2008–2009 Ben Finney <ben+python@benfinney.id.au>
#
# This is free software: you may copy, modify, and/or distribute this work
# under the terms of the Python Software Foundation License, version 2 or
# later as published by the Python Software Foundation.
# No warranty expressed or implied. See the file LICENSE.PSF-2 for details.

""" Lockfile behaviour implemented via Unix PID files.
    """

import os
import errno

from lockfile import (
    LinkFileLock,
    AlreadyLocked, LockFailed,
    NotLocked, NotMyLock,
    )


class PIDLockFile(LinkFileLock, object):
    """ Lockfile implemented as a Unix PID file.

        The PID file is named by the attribute `path`. When locked,
        the file will be created with a single line of text,
        containing the process ID (PID) of the process that acquired
        the lock.

        The lock is acquired and maintained as per `LinkFileLock`.

        """

    def read_pid(self):
        """ Get the PID from the lock file.
            """
        result = read_pid_from_pidfile(self.path)
        return result

    def acquire(self, *args, **kwargs):
        """ Acquire the lock.

            Locks the PID file then creates the PID file for this
            lock. The `timeout` parameter is used as for the
            `LinkFileLock` class.

            """
        super(PIDLockFile, self).acquire(*args, **kwargs)
        try:
            write_pid_to_pidfile(self.path)
        except OSError:
            error = LockFailed()
            raise error

    def release(self):
        """ Release the lock.

            Removes the PID file then releases the lock, or raises an
            error if the current process does not hold the lock.

            """
        if self.i_am_locking():
            remove_existing_pidfile(self.path)
        super(PIDLockFile, self).release()

    def break_lock(self):
        """ Break an existing lock.

            If the lock is held, breaks the lock and removes the PID
            file.

            """
        super(PIDLockFile, self).break_lock()
        remove_existing_pidfile(self.path)


def read_pid_from_pidfile(pidfile_path):
    """ Read the PID recorded in the named PID file.

        Read and return the numeric PID recorded as text in the named
        PID file. If the PID file cannot be read, or if the content is
        not a valid PID, return ``None``.

        """
    pid = None
    try:
        pidfile = open(pidfile_path, 'r')
    except IOError:
        pass
    else:
        line = pidfile.read().strip()
        try:
            pid = int(line)
        except ValueError:
            pass
        pidfile.close()

    return pid


def write_pid_to_pidfile(pidfile_path):
    """ Write the PID in the named PID file.

        Get the numeric process ID (“PID”) of the current process
        and write it to the named file as a line of text.

        """
    pidfile = open(pidfile_path, 'w')

    pid = os.getpid()
    line = "%(pid)d\n" % vars()
    pidfile.write(line)


def remove_existing_pidfile(pidfile_path):
    """ Remove the named PID file if it exists.

        Remove the named PID file. Ignore the condition if the file
        does not exist, since that only means we are already in the
        desired state.

        """
    try:
        os.remove(pidfile_path)
    except OSError, exc:
        if exc.errno == errno.ENOENT:
            pass
        else:
            raise
