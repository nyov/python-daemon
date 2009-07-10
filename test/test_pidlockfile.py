# -*- coding: utf-8 -*-
#
# test/test_pidlockfile.py
#
# Copyright © 2008–2009 Ben Finney <ben+python@benfinney.id.au>
#
# This is free software: you may copy, modify, and/or distribute this work
# under the terms of the Python Software Foundation License, version 2 or
# later as published by the Python Software Foundation.
# No warranty expressed or implied. See the file LICENSE.PSF-2 for details.

""" Unit test for pidlockfile module.
    """

import __builtin__
import os
import sys
from StringIO import StringIO
import itertools
import tempfile
import errno

import lockfile
import scaffold

from daemon import pidlockfile


class FakeFileDescriptorStringIO(StringIO, object):
    """ A StringIO class that fakes a file descriptor. """

    _fileno_generator = itertools.count()

    def __init__(self, *args, **kwargs):
        self._fileno = self._fileno_generator.next()
        super_instance = super(FakeFileDescriptorStringIO, self)
        super_instance.__init__(*args, **kwargs)

    def fileno(self):
        return self._fileno


def setup_pidfile_fixtures(testcase):
    """ Set up common fixtures for PID file test cases. """
    testcase.mock_tracker = scaffold.MockTracker()

    mock_current_pid = 235
    mock_other_pid = 8642
    mock_pidfile_path = tempfile.mktemp()

    scaffold.mock(
        "os.getpid",
        returns=mock_current_pid,
        tracker=testcase.mock_tracker)

    def mock_pidfile_open_nonexist(filename, mode, buffering):
        if 'r' in mode:
            raise IOError("No such file %(filename)r" % vars())
        else:
            result = testcase.scenario['pidfile']
        return result

    def mock_pidfile_open_exist(filename, mode, buffering):
        result = testcase.scenario['pidfile']
        return result

    def mock_open(filename, mode='r', buffering=None):
        if filename == testcase.scenario['path']:
            result = testcase.scenario['open_func'](filename, mode, buffering)
        else:
            result = FakeFileDescriptorStringIO()
        return result

    scaffold.mock(
        "__builtin__.open",
        returns_func=mock_open,
        tracker=testcase.mock_tracker)

    def mock_pidfile_os_open_nonexist(filename, flags, mode):
        if (flags & os.O_CREAT):
            result = testcase.scenario['pidfile'].fileno()
        else:
            raise OSError(errno.ENOENT, "No such file", filename)
        return result

    def mock_pidfile_os_open_exist(filename, flags, mode):
        result = testcase.scenario['pidfile'].fileno()
        return result

    def mock_os_open(filename, flags, mode=None):
        if filename == testcase.scenario['path']:
            result = testcase.scenario['os_open_func'](filename, flags, mode)
        else:
            result = FakeFileDescriptorStringIO().fileno()
        return result

    scaffold.mock(
        "os.open",
        returns_func=mock_os_open,
        tracker=testcase.mock_tracker)

    def mock_os_fdopen(fd, mode='r', buffering=None):
        if fd == testcase.scenario['pidfile'].fileno():
            result = testcase.scenario['pidfile']
        else:
            raise OSError(errno.EBADF, "Bad file descriptor")
        return result

    scaffold.mock(
        "os.fdopen",
        returns_func=mock_os_fdopen,
        tracker=testcase.mock_tracker)

    testcase.pidlockfile_scenarios = {
        'nonexist': {
            'exists': False,
            'pidfile_pid': None,
            'locking_pid': None,
            'read_pid': None,
            },
        'exist-currentpid': {
            'exists': True,
            'pidfile_pid': mock_current_pid,
            'read_pid': mock_current_pid,
            },
        'exist-otherpid': {
            'exists': True,
            'pidfile_pid': mock_other_pid,
            'read_pid': mock_other_pid,
            },
        'exist-invalid': {
            'exists': True,
            'pidfile_pid': "b0gUs",
            'locking_pid': None,
            'read_pid': None,
            },
        }

    for scenario in testcase.pidlockfile_scenarios.values():
        scenario['path'] = mock_pidfile_path
        pidfile = FakeFileDescriptorStringIO()
        if scenario['exists']:
            pidfile.write("%(pidfile_pid)s\n" % scenario)
            pidfile.seek(0)
        scenario['pidfile'] = pidfile
        pidfile_exists_offset = int(scenario['exists'])
        scenario['pid'] = mock_current_pid
        if not 'locking_pid' in scenario:
            scenario['locking_pid'] = scenario['pidfile_pid']
        scenario['open_func'] = [
            mock_pidfile_open_nonexist, mock_pidfile_open_exist
            ][pidfile_exists_offset]
        scenario['os_open_func'] = [
            mock_pidfile_os_open_nonexist, mock_pidfile_os_open_exist
            ][pidfile_exists_offset]

    testcase.scenario = testcase.pidlockfile_scenarios['nonexist']


def setup_lockfile_method_mocks(testcase, class_name):
    """ Set up common mock methods for lockfile class. """

    def mock_is_locked():
        return testcase.scenario['exists']
    def mock_i_am_locking():
        return (
            testcase.scenario['exists'] and
            testcase.scenario['locking_pid'] == testcase.scenario['pid'])
    def mock_acquire(timeout=None):
        if testcase.scenario['exists']:
            raise lockfile.AlreadyLocked()
        testcase.scenario['locking_pid'] = testcase.scenario['pid']
        testcase.scenario['exists'] = True
    def mock_release():
        if not testcase.scenario['exists']:
            raise lockfile.NotLocked()
        if testcase.scenario['locking_pid'] != testcase.scenario['pid']:
            raise lockfile.NotMyLock()
        testcase.scenario['locking_pid'] = None
        testcase.scenario['exists'] = False
    def mock_break_lock():
        testcase.scenario['locking_pid'] = None
        testcase.scenario['exists'] = False

    for func_name in [
        'is_locked', 'i_am_locking',
        'acquire', 'release', 'break_lock',
        ]:
        mock_func = vars()["mock_%(func_name)s" % vars()]
        lockfile_func_name = "%(class_name)s.%(func_name)s" % vars()
        mock_lockfile_func = scaffold.Mock(
            lockfile_func_name,
            returns_func=mock_func,
            tracker=testcase.mock_tracker)
        scaffold.mock(
            lockfile_func_name,
            mock_obj=mock_lockfile_func,
            tracker=testcase.mock_tracker)


def setup_pidlockfile_fixtures(testcase):
    """ Set up common fixtures for PIDLockFile test cases. """

    setup_pidfile_fixtures(testcase)

    testcase.pidlockfile_args = dict(
        path=testcase.scenario['path'],
        )
    testcase.test_instance = pidlockfile.PIDLockFile(
        **testcase.pidlockfile_args)
    for scenario in testcase.pidlockfile_scenarios.values():
        scenario['lockfile'] = testcase.test_instance

    setup_lockfile_method_mocks(testcase, "lockfile.LinkFileLock")

    scaffold.mock(
        "pidlockfile.write_pid_to_pidfile",
        tracker=testcase.mock_tracker)
    scaffold.mock(
        "pidlockfile.remove_existing_pidfile",
        tracker=testcase.mock_tracker)


class PIDLockFile_TestCase(scaffold.TestCase):
    """ Test cases for PIDLockFile class. """

    def setUp(self):
        """ Set up test fixtures. """
        setup_pidlockfile_fixtures(self)

        self.scenario = self.pidlockfile_scenarios['exist-otherpid']

    def tearDown(self):
        """ Tear down test fixtures. """
        scaffold.mock_restore()

    def test_instantiate(self):
        """ New instance of PIDLockFile should be created. """
        instance = self.test_instance
        self.failUnlessIsInstance(instance, pidlockfile.PIDLockFile)

    def test_inherits_from_linkfilelock(self):
        """ Should inherit from LinkFileLock. """
        instance = self.test_instance
        self.failUnlessIsInstance(instance, lockfile.LinkFileLock)

    def test_has_specified_path(self):
        """ Should have specified path. """
        instance = self.test_instance
        expect_path = self.scenario['path']
        self.failUnlessEqual(expect_path, instance.path)


class PIDLockFile_read_pid_TestCase(scaffold.TestCase):
    """ Test cases for PIDLockFile.read_pid method. """

    def setUp(self):
        """ Set up test fixtures. """
        setup_pidlockfile_fixtures(self)

        self.scenario = self.pidlockfile_scenarios['exist-otherpid']

    def tearDown(self):
        """ Tear down test fixtures. """
        scaffold.mock_restore()

    def test_gets_pid_via_read_pid_from_pidfile(self):
        """ Should get PID via read_pid_from_pidfile. """
        instance = self.test_instance
        test_pid = self.scenario['read_pid']
        expect_pid = test_pid
        result = instance.read_pid()
        self.failUnlessEqual(expect_pid, result)


class PIDLockFile_acquire_TestCase(scaffold.TestCase):
    """ Test cases for PIDLockFile.acquire function. """

    def setUp(self):
        """ Set up test fixtures. """
        setup_pidlockfile_fixtures(self)
        self.mock_tracker.clear()

        self.scenario = self.pidlockfile_scenarios['nonexist']

    def tearDown(self):
        """ Tear down test fixtures. """
        scaffold.mock_restore()

    def test_calls_linkfilelock_acquire(self):
        """ Should first call LinkFileLock.acquire method. """
        instance = self.test_instance
        expect_mock_output = """\
            Called lockfile.LinkFileLock.acquire()
            ...
            """
        instance.acquire()
        self.failUnlessMockCheckerMatch(expect_mock_output)

    def test_calls_linkfilelock_acquire_with_timeout(self):
        """ Should call LinkFileLock.acquire method with specified timeout. """
        instance = self.test_instance
        test_timeout = object()
        expect_mock_output = """\
            Called lockfile.LinkFileLock.acquire(timeout=%(test_timeout)r)
            ...
            """ % vars()
        instance.acquire(timeout=test_timeout)
        self.failUnlessMockCheckerMatch(expect_mock_output)

    def test_writes_pid_to_specified_file(self):
        """ Should request writing current PID to specified file. """
        instance = self.test_instance
        pidfile_path = self.scenario['path']
        expect_mock_output = """\
            ...
            Called pidlockfile.write_pid_to_pidfile(%(pidfile_path)r)
            """ % vars()
        instance.acquire()
        scaffold.mock_restore()
        self.failUnlessMockCheckerMatch(expect_mock_output)

    def test_raises_lock_failed_on_write_error(self):
        """ Should raise LockFailed error if write fails. """
        instance = self.test_instance
        pidfile_path = self.scenario['path']
        mock_error = OSError(errno.EBUSY, "Bad stuff", pidfile_path)
        pidlockfile.write_pid_to_pidfile.mock_raises = mock_error
        expect_error = lockfile.LockFailed
        self.failUnlessRaises(
            expect_error,
            instance.acquire)


class PIDLockFile_release_TestCase(scaffold.TestCase):
    """ Test cases for PIDLockFile.release function. """

    def setUp(self):
        """ Set up test fixtures. """
        setup_pidlockfile_fixtures(self)
        self.mock_tracker.clear()

        self.scenario = self.pidlockfile_scenarios['exist-currentpid']

    def tearDown(self):
        """ Tear down test fixtures. """
        scaffold.mock_restore()

    def test_remove_existing_pidfile_not_called_if_not_locking(self):
        """ Should not request removal of PID file if not locking. """
        instance = self.test_instance
        self.scenario = self.pidlockfile_scenarios['nonexist']
        expect_error = lockfile.NotLocked
        unwanted_mock_output = (
            "..."
            "Called pidlockfile.remove_existing_pidfile"
            "...")
        self.failUnlessRaises(
            expect_error,
            instance.release)
        self.failIfMockCheckerMatch(unwanted_mock_output)

    def test_does_not_remove_existing_pidfile_if_not_my_lock(self):
        """ Should not request removal of PID file if we are not locking. """
        instance = self.test_instance
        self.scenario = self.pidlockfile_scenarios['exist-otherpid']
        expect_error = lockfile.NotMyLock
        unwanted_mock_output = (
            "..."
            "Called pidlockfile.remove_existing_pidfile"
            "...")
        self.failUnlessRaises(
            expect_error,
            instance.release)
        self.failIfMockCheckerMatch(unwanted_mock_output)

    def test_removes_existing_pidfile_if_i_am_locking(self):
        """ Should request removal of specified PID file if lock is ours. """
        instance = self.test_instance
        pidfile_path = self.scenario['path']
        expect_mock_output = """\
            ...
            Called pidlockfile.remove_existing_pidfile(%(pidfile_path)r)
            ...
            """ % vars()
        instance.release()
        self.failUnlessMockCheckerMatch(expect_mock_output)

    def test_calls_linkfilelock_release(self):
        """ Should finally call LinkFileLock.release method. """
        instance = self.test_instance
        expect_mock_output = """\
            ...
            Called lockfile.LinkFileLock.release()
            """
        instance.release()
        self.failUnlessMockCheckerMatch(expect_mock_output)


class PIDLockFile_break_lock_TestCase(scaffold.TestCase):
    """ Test cases for PIDLockFile.break_lock function. """

    def setUp(self):
        """ Set up test fixtures. """
        setup_pidlockfile_fixtures(self)
        self.mock_tracker.clear()

        self.scenario = self.pidlockfile_scenarios['exist-otherpid']

    def tearDown(self):
        """ Tear down test fixtures. """
        scaffold.mock_restore()

    def test_calls_linkfilelock_break_lock(self):
        """ Should first call LinkFileLock.break_lock method. """
        instance = self.test_instance
        expect_mock_output = """\
            Called lockfile.LinkFileLock.break_lock()
            ...
            """
        instance.break_lock()
        self.failUnlessMockCheckerMatch(expect_mock_output)

    def test_removes_existing_pidfile(self):
        """ Should request removal of specified PID file. """
        instance = self.test_instance
        pidfile_path = self.scenario['path']
        expect_mock_output = """\
            ...
            Called pidlockfile.remove_existing_pidfile(%(pidfile_path)r)
            """ % vars()
        instance.break_lock()
        self.failUnlessMockCheckerMatch(expect_mock_output)


class read_pid_from_pidfile_TestCase(scaffold.TestCase):
    """ Test cases for read_pid_from_pidfile function. """

    def setUp(self):
        """ Set up test fixtures. """
        setup_pidfile_fixtures(self)

        self.scenario = self.pidlockfile_scenarios['exist-otherpid']

    def tearDown(self):
        """ Tear down test fixtures. """
        scaffold.mock_restore()

    def test_opens_specified_filename(self):
        """ Should attempt to open specified pidfile filename. """
        pidfile_path = self.scenario['path']
        expect_mock_output = """\
            Called __builtin__.open(%(pidfile_path)r, 'r')
            """ % vars()
        dummy = pidlockfile.read_pid_from_pidfile(pidfile_path)
        scaffold.mock_restore()
        self.failUnlessMockCheckerMatch(expect_mock_output)

    def test_reads_pid_from_file(self):
        """ Should read the PID from the specified file. """
        pidfile_path = self.scenario['path']
        expect_pid = self.scenario['pidfile_pid']
        pid = pidlockfile.read_pid_from_pidfile(pidfile_path)
        scaffold.mock_restore()
        self.failUnlessEqual(expect_pid, pid)

    def test_returns_none_when_file_nonexist(self):
        """ Should return None when the PID file does not exist. """
        self.scenario = self.pidlockfile_scenarios['nonexist']
        pidfile_path = self.scenario['path']
        pid = pidlockfile.read_pid_from_pidfile(pidfile_path)
        scaffold.mock_restore()
        self.failUnlessIs(None, pid)


class remove_existing_pidfile_TestCase(scaffold.TestCase):
    """ Test cases for remove_existing_pidfile function. """

    def setUp(self):
        """ Set up test fixtures. """
        setup_pidfile_fixtures(self)

        self.scenario = self.pidlockfile_scenarios['exist-currentpid']

        scaffold.mock(
            "os.remove",
            tracker=self.mock_tracker)

    def tearDown(self):
        """ Tear down test fixtures. """
        scaffold.mock_restore()

    def test_removes_specified_filename(self):
        """ Should attempt to remove specified PID file filename. """
        pidfile_path = self.scenario['path']
        expect_mock_output = """\
            Called os.remove(%(pidfile_path)r)
            """ % vars()
        pidlockfile.remove_existing_pidfile(pidfile_path)
        scaffold.mock_restore()
        self.failUnlessMockCheckerMatch(expect_mock_output)

    def test_ignores_file_not_exist_error(self):
        """ Should ignore error if file does not exist. """
        pidfile_path = self.scenario['path']
        mock_error = OSError(errno.ENOENT, "Not there", pidfile_path)
        os.remove.mock_raises = mock_error
        expect_mock_output = """\
            Called os.remove(%(pidfile_path)r)
            """ % vars()
        pidlockfile.remove_existing_pidfile(pidfile_path)
        scaffold.mock_restore()
        self.failUnlessMockCheckerMatch(expect_mock_output)

    def test_propagates_arbitrary_oserror(self):
        """ Should propagate any OSError other than ENOENT. """
        pidfile_path = self.scenario['path']
        mock_error = OSError(errno.EACCES, "Denied", pidfile_path)
        os.remove.mock_raises = mock_error
        self.failUnlessRaises(
            type(mock_error),
            pidlockfile.remove_existing_pidfile,
            pidfile_path)


class write_pid_to_pidfile_TestCase(scaffold.TestCase):
    """ Test cases for write_pid_to_pidfile function. """

    def setUp(self):
        """ Set up test fixtures. """
        setup_pidfile_fixtures(self)

        self.scenario = self.pidlockfile_scenarios['nonexist']

    def tearDown(self):
        """ Tear down test fixtures. """
        scaffold.mock_restore()

    def test_opens_specified_filename(self):
        """ Should attempt to open specified PID file filename. """
        pidfile_path = self.scenario['path']
        expect_flags = (os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        expect_mode = 0x644
        expect_mock_output = """\
            Called os.open(%(pidfile_path)r, %(expect_flags)r, %(expect_mode)r)
            ...
            """ % vars()
        pidlockfile.write_pid_to_pidfile(pidfile_path)
        scaffold.mock_restore()
        self.failUnlessMockCheckerMatch(expect_mock_output)

    def test_writes_pid_to_file(self):
        """ Should write the current PID to the specified file. """
        pidfile_path = self.scenario['path']
        self.scenario['pidfile'].close = scaffold.Mock(
            "mock_pidfile.close",
            tracker=self.mock_tracker)
        expect_line = "%(pid)d\n" % self.scenario
        pidlockfile.write_pid_to_pidfile(pidfile_path)
        scaffold.mock_restore()
        self.failUnlessEqual(expect_line, self.scenario['pidfile'].getvalue())

    def test_closes_file_after_write(self):
        """ Should close the specified file after writing. """
        pidfile_path = self.scenario['path']
        self.scenario['pidfile'].write = scaffold.Mock(
            "mock_pidfile.write",
            tracker=self.mock_tracker)
        self.scenario['pidfile'].close = scaffold.Mock(
            "mock_pidfile.close",
            tracker=self.mock_tracker)
        expect_mock_output = """\
            ...
            Called mock_pidfile.write(...)
            Called mock_pidfile.close()
            """ % vars()
        pidlockfile.write_pid_to_pidfile(pidfile_path)
        scaffold.mock_restore()
        self.failUnlessMockCheckerMatch(expect_mock_output)
