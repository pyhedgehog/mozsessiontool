#!/usr/bin/env python
# This code is in Public Domain (see LICENSE)
import os
import sys
import stat
import glob
import json
import time
import types
import itertools
import argparse
import urllib
import datetime
import difflib
import abc
import six
from contextlib import closing
try:
    import pwd
except ImportError:
    pwd = None
try:
    import grp
except ImportError:
    grp = None
try:
    import io
except ImportError:
    io = None
try:
    import lz4.block
except ImportError:
    lz4 = None

__version__ = "0.0.1"

try:
    types.UnicodeType
except AttributeError:
    def u(s):
        return s
    unicode = str
else:
    # to make diff prettier
    class u(unicode):
        def __repr__(self):
            res = super(u, self).__repr__()
            if res[:1] == 'u':
                res = res[1:]
            return res

checkpointOrder = (
    "profile-after-change", "final-ui-startup",
    "sessionstore-windows-restored", "quit-application-granted",
    "quit-application", "sessionstore-final-state-write-complete",
    "profile-change-net-teardown", "profile-change-teardown",
    "profile-before-change"
)
checkpointSkippable = frozenset(["sessionstore-windows-restored", "sessionstore-final-state-write-complete"])
checkpointNames = {
    "profile-after-change": "Starting",
    "final-ui-startup": "Started, Loading session",
    "sessionstore-windows-restored": "Running",
    "quit-application-granted": "Stopping",
    "quit-application": "Hidden",
    "sessionstore-final-state-write-complete": "Session saved",
    "profile-change-net-teardown": "Session saved, Connections closed",
    "profile-change-teardown": "Session saved, Connections closed, Profile closing",
    "profile-before-change": "Stopped",
}


def getpwuid(uid):
    try:
        return pwd.getpwuid(uid).pw_name
    except Exception:
        return str(uid)


def getgrgid(gid):
    try:
        return grp.getgrgid(gid).gr_name
    except Exception:
        return str(gid)


def getstmode(mode):
    if stat.S_ISDIR(mode):
        res = 'd'
    elif stat.S_ISCHR(mode):
        res = 'c'
    elif stat.S_ISBLK(mode):
        res = 'b'
    elif stat.S_ISREG(mode):
        res = '-'
    elif stat.S_ISFIFO(mode):
        res = 'p'
    elif stat.S_ISLNK(mode):
        res = 'l'
    elif stat.S_ISSOCK(mode):
        res = 's'
    else:
        res = '?'

    def get3mod(mode, r, w, x, **ext):
        res = ''
        res += '-r'[mode & r == r]
        res += '-w'[mode & w == w]
        if not ext:
            res += '-x'[mode & x == x]
        else:
            assert len(ext) == 1
            l, s = ext.popitem()
            alt = l.upper()+l
            res += ['-x', alt][mode & s == s][mode & x == x]
        return res

    res += get3mod(mode, stat.S_IRUSR, stat.S_IWUSR, stat.S_IXUSR, s=stat.S_ISUID)
    res += get3mod(mode, stat.S_IRGRP, stat.S_IWGRP, stat.S_IXGRP, s=stat.S_ISGID)
    res += get3mod(mode, stat.S_IROTH, stat.S_IWOTH, stat.S_IXOTH, t=stat.S_ISVTX)
    return res


def simplify(value):
    if type(value) == getattr(types, 'UnicodeType', None):
        try:
            return str(value)
        except UnicodeError:
            pass
    if type(value) in six.integer_types:
        if value >= 946674000000:
            return time.ctime(value/1000)
        if value >= 946674000:
            return time.ctime(value)
    if isinstance(value, datetime.timedelta):
        s = '%d minute%s' % (value.seconds/60 % 60, 's'*(value.seconds/60 % 60 > 1))
        if value.seconds % 60:
            s += ' %d second%s' % (value.seconds % 60, 's'*(value.seconds % 60 > 1))
        if value.seconds / 3600:
            s = '%d hour%s %s' % (value.seconds/3600, 's'*(value.seconds/3600 > 1), s)
        if value.days:
            s = '%d day%s %s' % (value.days, 's'*(value.days > 1), s)
        return s
    return str(value)


@six.add_metaclass(abc.ABCMeta)
class MozSessionBase():
    pprint_extra = ''

    def __init__(self):
        self.stat = None
        self.sessionstore = self.checkpoints = None
        self.sessionstore_fd = self.checkpoints_fd = None
        self.sessionstore_fn = self.checkpoints_fn = None

    def __repr__(self):
        return '<%s(%s)>' % (self.__class__.__name__, self.pprint().replace('\n', ','))

    def pprint(self, verbose=False, base=False):
        if verbose:
            res = []
            if self.sessionstore_fn:
                fn = self.sessionstore_fn
                if base:
                    fn = os.path.basename(fn)
                res.append(fn+self.pprint_extra)
            if self.checkpoints_fn:
                fn = self.checkpoints_fn
                if base:
                    fn = os.path.basename(fn)
                res.append(fn)
            return '\n'.join(res)
        fn = self.__class__.__name__
        if self.sessionstore_fn or self.checkpoints_fn:
            fn = self.sessionstore_fn or self.checkpoints_fn
            if base:
                fn = os.path.basename(fn)
        return fn+self.pprint_extra

    @classmethod
    def check(cls, *initargs):
        return all(os.path.isfile(fn) for fn in filter(None, cls._get_filenames(*initargs)))

    def _open(self, fn, binary=False, want_save=False):
        if fn is None:
            return None
        mode_tail = 'tb'[binary]
        if not binary and sys.version_info[:2] >= (3, 0):
            open_args = dict(encoding='utf-8')
        else:
            open_args = {}
        fd = open(fn, ['r', 'r+'][want_save]+mode_tail, **open_args)
        st = os.fstat(fd.fileno())
        if self.stat is None or self.stat.st_ctime < st.st_ctime:
            self.stat = st
        return fd

    def load(self, want_save=False):
        self._open_sessionstore(want_save)
        self._open_checkpoints(want_save)
        self._read_sessionstore()
        self._read_checkpoints()
        return self

    def save(self):
        self._write_sessionstore()
        self._write_checkpoints()

    def close(self):
        self._close_sessionstore()
        self._close_checkpoints()

    @abc.abstractmethod
    def _get_filenames(cls, profile): pass

    @abc.abstractmethod
    def _open_sessionstore(self, want_save=False): pass

    @abc.abstractmethod
    def _open_checkpoints(self, want_save=False): pass

    @abc.abstractmethod
    def _read_sessionstore(self): pass

    @abc.abstractmethod
    def _read_checkpoints(self): pass

    @abc.abstractmethod
    def _write_sessionstore(self): pass

    @abc.abstractmethod
    def _write_checkpoints(self): pass

    def _close_sessionstore(self):
        if self.sessionstore_fd is not None:
            self.sessionstore_fd.close()
            self.sessionstore_fd = None

    def _close_checkpoints(self):
        if self.checkpoints_fd is not None:
            self.checkpoints_fd.close()
            self.checkpoints_fd = None


class MozSessionProfileBase(MozSessionBase):
    def __init__(self, profile):
        MozSessionBase.__init__(self)
        self.profile = profile
        self.sessionstore_fn, self.checkpoints_fn = self._get_filenames(self.profile)

    def __repr__(self):
        return '<%s(%s)>' % (self.__class__.__name__, self.profile)

    def pprint(self, verbose=False, base=False):
        fn = self.profile
        if base:
            fn = os.path.basename(fn)
        return fn+self.pprint_extra


class SessionStoreJsonMixin:
    def _open_sessionstore(self, want_save=False):
        self.sessionstore_fd = self._open(self.sessionstore_fn, want_save=want_save)
        return self.sessionstore_fd

    def _read_sessionstore(self):
        if not self.sessionstore_fd:
            return
        self.sessionstore = json.load(self.sessionstore_fd)
        return self.sessionstore

    def _write_sessionstore(self):
        s = json.dumps(self.sessionstore, ensure_ascii=True, separators=(',', ':'))
        self.sessionstore_fd.seek(0, 0)
        self.sessionstore_fd.truncate()
        self.sessionstore_fd.write(s)


class NoCheckPointsMixin:
    def _open_checkpoints(self, want_save=False): pass

    def _read_checkpoints(self): pass

    def _write_checkpoints(self): pass


class CheckPointsJsonMixin:
    def _open_checkpoints(self, want_save=False):
        self.checkpoints_fd = self._open(self.checkpoints_fn, want_save=want_save)
        return self.checkpoints_fd

    def _read_checkpoints(self):
        if not self.checkpoints_fn:
            return
        self.checkpoints = json.load(self.checkpoints_fd)
        return self.checkpoints

    def _write_checkpoints(self):
        s = json.dumps(self.checkpoints)
        self.checkpoints_fd.seek(0, 0)
        self.checkpoints_fd.truncate()
        self.checkpoints_fd.write(s)


class SessionStoreLZ4Mixin:
    pprint_extra = ' (lz4)'
    magicheader = b'mozLz40\0'

    def _open_sessionstore(self, want_save=False):
        self.sessionstore_fd = self._open(self.sessionstore_fn, binary=True, want_save=want_save)
        check = self.sessionstore_fd.read(8)
        if check != self.magicheader:
            self.sessionstore_fd.close()
            self.sessionstore_fd = None
            raise ValueError("Invalid header %r in %r" % (check, self.sessionstore_fn))
        return self.sessionstore_fd

    def _read_sessionstore(self):
        if not self.sessionstore_fd:
            return
        s = self.sessionstore_fd.read()
        s = lz4.block.decompress(s)
        self.sessionstore = json.loads(s)
        return self.sessionstore

    def _write_sessionstore(self):
        s = json.dumps(self.sessionstore, ensure_ascii=True, separators=(',', ':')).encode('utf-8')
        s = self.magicheader+lz4.block.compress(s)
        self.sessionstore_fd.seek(0, 0)
        self.sessionstore_fd.truncate()
        self.sessionstore_fd.write(s)


class MozSession1(SessionStoreJsonMixin, NoCheckPointsMixin, MozSessionBase):
    def __init__(self, filename):
        MozSessionBase.__init__(self)
        self.filename = filename
        self.sessionstore_fn, self.checkpoints_fn = self._get_filenames(self.filename)

    @classmethod
    def _get_filenames(cls, filename):
        return filename, None


class MozSessionProfile2(SessionStoreJsonMixin, CheckPointsJsonMixin, MozSessionProfileBase):
    @classmethod
    def _get_filenames(cls, profile):
        return os.path.join(profile, "sessionstore.js"), os.path.join(profile, "sessionCheckpoints.json")


class MozSessionProfile3(SessionStoreJsonMixin, CheckPointsJsonMixin, MozSessionProfileBase):
    @classmethod
    def _get_filenames(cls, profile):
        return os.path.join(profile, "sessionstore-backups", "recovery.js"), \
               os.path.join(profile, "sessionCheckpoints.json")


class MozSessionProfile4(SessionStoreLZ4Mixin, CheckPointsJsonMixin, MozSessionProfileBase):
    @classmethod
    def _get_filenames(cls, profile):
        return os.path.join(profile, "sessionstore-backups", "recovery.jsonlz4"), \
               os.path.join(profile, "sessionCheckpoints.json")

    @classmethod
    def check(cls, profile):
        if not MozSessionProfileBase.check.__func__(cls, profile):
            return False
        if lz4 is None:
            err = "Profile %s seems to contains lz4 files, but your python has no support for it" % (profile,)
            raise RuntimeError(err)
        return True


def get_profile_paths(names=['default', 'default-release']):
    if sys.platform in ('win32', 'cygwin'):
        firefox = os.path.join(os.environ['USERPROFILE'], *('Application Data/Mozilla/Firefox'.split('/')))
        profiles = os.path.join(firefox, 'Profiles')
        # profiles_ini = os.path.join(firefox, 'profiles.ini')
    else:  # TODO: darwin not supported yet
        firefox = profiles = os.path.expanduser('~/.mozilla/firefox')
        # profiles_ini = os.path.expanduser('~/.mozilla/firefox/profiles.ini')
    return list(itertools.chain(*(glob.glob(os.path.join(profiles, "*."+name)) for name in names)))


def get_profile_sessionstore(names=['default', 'default-release']):
    profiles = get_profile_paths(names)
    if not profiles:
        return None
    for path in profiles:
        for cls in (MozSessionProfile4, MozSessionProfile3, MozSessionProfile2, MozSession1):
            if cls.check(path):
                return cls(path)
    return None


def get_sessionstore(path=None):
    if path:
        for cls in (MozSessionProfile4, MozSessionProfile3, MozSessionProfile2, MozSession1):
            if cls.check(path):
                return cls(path)
        name = path
        for path in get_profile_paths([name]):
            for cls in (MozSessionProfile4, MozSessionProfile3, MozSessionProfile2, MozSession1):
                if cls.check(path):
                    return cls(path)
    return get_profile_sessionstore()


def showcheckpoint(sessionCheckpoints):
    state = "Init"
    sessionCheckpoints = sessionCheckpoints.copy()
    skipped = []
    for event in checkpointOrder:
        if not sessionCheckpoints:
            break
        if event in sessionCheckpoints and sessionCheckpoints[event] is True:
            state = "%s (%s)" % (checkpointNames[event], event)
            sessionCheckpoints.pop(event)
            continue
        if event in checkpointSkippable:
            if event not in sessionCheckpoints:
                skipped.append(event)
            continue
        break
    rest = ""
    if skipped:
        rest = "; skipped: "+(", ".join(skipped))
    if sessionCheckpoints:
        rest = "; "+(", ".join(["", "not "][not v]+k for k, v in sessionCheckpoints.items()))
    return state+rest


def showstats(st, quiet=False, test=False):
    stpw, stgr = getpwuid(st.st_uid), getgrgid(st.st_gid)
    stmode, stctime = getstmode(st.st_mode), time.ctime(st.st_ctime)
    if test:
        st = type(st)(st[:-3]+(0, 0, 0))
        stpw = stgr = 'test'
        stctime = 'sometimes'
        stmode = '-rw-rw-rw-'
    if quiet:
        print('%s:%s %s %d %s' % (stpw, stgr, stmode, st.st_size, stctime))
    else:
        if test:
            ago = 'ages'
        else:
            ago = simplify(datetime.timedelta(seconds=time.time()-st.st_ctime))
        print('%s:%s %s %d %s (%s ago)' % (stpw, stgr, stmode, st.st_size, stctime, ago))


def tabs_info(tab):
    if tab.get('entries'):
        return tab['entries'][tab['index']-1]
    if 'userTypedValue' not in tab:
        return dict(url='about:blank', title=tab.get('title', 'New tab'))
    return dict(url=tab['userTypedValue'], title=tab.get('title', 'Loading...'))


def dump4diff(obj, name='obj'):
    if isinstance(obj, list):
        yield u("%s.len() = %d\n") % (u(name), len(obj))
        for i, v in enumerate(obj):
            for s in dump4diff(v, "%s[%d]" % (name, i)):
                yield s
    elif isinstance(obj, dict):
        yield u("%s.keys() = %s\n") % (u(name), sorted(map(u, obj.keys())))
        for k, v in sorted(obj.items()):
            try:
                k = str(k)
            except UnicodeError:
                pass
            for s in dump4diff(v, "%s[%r]" % (name, k)):
                yield s
    else:
        yield u("%s = %r\n") % (name, obj)


def stdout_encoding():
    import encodings
    encoding = encodings.normalize_encoding(sys.stdout.encoding)
    return (encodings._aliases.get(encoding) or
            encodings._aliases.get(encoding.replace('.', '_')) or
            encoding).lower()


def main(argv):
    global parser, args, store  # for debugging using `python -i mozsessiontool.py`
    if sys.version_info[:2] > (2, 6) and io is not None and \
       hasattr(sys.stdout, 'errors') and hasattr(sys.stdout, 'buffer') and \
       hasattr(sys.stdout, 'encoding') and stdout_encoding() not in ('utf_8', 'utf_16', 'utf_32') and \
       hasattr(sys.stdout, 'newlines') and hasattr(sys.stdout, 'line_buffering'):
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, sys.stdout.encoding, 'backslashreplace',
                                      sys.stdout.newlines, sys.stdout.line_buffering)
    parser = argparse.ArgumentParser(prog=argv[0], description='Process firefox sessionstore.js')
    parser.add_argument('--debug', '-D', action='store_true', help=argparse.SUPPRESS)
    parser.add_argument('--debug-args', action='store_true', help=argparse.SUPPRESS)
    # Special argument for tests to be reproducable
    parser.add_argument('--test', action='store_true', help=argparse.SUPPRESS)
    parser.add_argument('--quiet', '-q', action='store_true', help='Be less verbose')
    parser.add_argument('--pretend', '--dry-run', '-n', action='store_true', help='Do nothing - only show changes')
    parser.add_argument('path', nargs='?', metavar='FILE',
                        help='Path to sessionstore.js or profile itself (path or name)')
    parser.add_argument('--window', '-w', type=int, help='Use window instead of current')
    parser.add_argument('--tab', '-t', type=int, help='Use tab instead of current')
    parser.add_argument('--grep', '--find', '-g', metavar='STR', help='Find tabs with URL containing STR')
    actions = parser.add_argument_group('actions')
    actions.add_argument('--action', '--do', choices='wselect tselect wclose tclose fix'.split(),
                         help='Do some changes to saved session state (use only if firefox is down)')
    actions.add_argument('--wselect', dest='action', const='wselect', action='store_const',
                         help='Change current window to selected (short form for --action=wselect)')
    actions.add_argument('--tselect', dest='action', const='tselect', action='store_const',
                         help='Change current tab to selected (short form for --action=tselect)')
    actions.add_argument('--wclose', '-W', dest='action', const='wclose', action='store_const',
                         help='Close selected (or current) window (short form for --action=wclose)')
    actions.add_argument('--tclose', '-T', dest='action', const='tclose', action='store_const',
                         help='Close selected (or current) tab (short form for --action=tclose)')
    actions.add_argument('--fix', '-f', dest='action', const='fix', action='store_const',
                         help='Fix saved session state (short form for --action=fix)')
    args = parser.parse_args(argv[1:])
    if args.debug_args or args.debug:
        print('%s %s' % (getattr(sys, 'implementation', argparse.Namespace(name='cpython')).name, sys.version))
    store = get_sessionstore(args.path)
    assert store
    want_save = args.action is not None

    # argument checks
    if args.action == 'wselect' and args.window is None:
        parser.error("For action 'wselect' --window must be specified.")
    if args.action == 'tselect' and args.tab is None:
        parser.error("For action 'tselect' --tab must be specified.")
    if args.pretend and not args.action:
        parser.error("No action selected = no --pretend processed.")
    if args.debug_args:
        print(args)
        print(store)
        print(store.pprint())
        return

    with closing(store):
        store.load(want_save=want_save)

        # data-specific argument checks
        if args.window is None:
            args.window = max(1, store.sessionstore['selectedWindow'])
            args.window = min(args.window, len(store.sessionstore['windows']))
        if not 1 <= args.window <= len(store.sessionstore['windows']):
            parser.error("Invalid -w value (%d) - must be in range 1-%d" %
                         (args.window, len(store.sessionstore['windows'])))
        if args.tab is None:
            args.tab = max(1, store.sessionstore['windows'][args.window-1]['selected'])
            args.tab = min(args.tab, len(store.sessionstore['windows'][args.window-1]['tabs']))
        if not 1 <= args.tab <= len(store.sessionstore['windows'][args.window-1]['tabs']):
            parser.error("Invalid -t value (%d) - must be in range 1-%d" %
                         (args.tab, len(store.sessionstore['windows'][args.window-1]['tabs'])))

        # show generic info
        print(store.pprint(verbose=args.debug, base=args.test))
        if store.checkpoints_fn and args.debug:
            print(store.checkpoints)
        showstats(store.stat, args.quiet, args.test)
        if not args.quiet:
            print('; '.join(sorted('%s: %s' % (str(k), simplify(v)) for k, v in store.sessionstore['session'].items())))
            # print('selected: %s' % (store.sessionstore['selectedWindow'],))
        if store.checkpoints is not None:
            print('checkpoint: %s' % (showcheckpoint(store.checkpoints),))

        # show windows
        for w, window in enumerate(store.sessionstore['windows']):
            selected = w == args.window-1
            if args.quiet and args.grep is not None and not selected:
                pass
            elif args.grep is not None and selected:
                print('Selected window %d (%d tabs):' % (w+1, len(window['tabs'])))
                for i, tab in enumerate(window['tabs']):
                    url = tabs_info(tab)
                    if args.grep in url['url']:
                        print('  tab %d: %s' % (i+1, url['url']))
            elif args.quiet:
                print('window %d%s: %d tabs' % (w+1, ['', ' (selected)'][selected], len(window['tabs'])))
            elif selected:
                print('Selected window %d:' % (w+1,))
                tab = window['tabs'][args.tab-1]
                print('  Selected tab (%d/%d):' % (args.tab, len(window['tabs'])))
                url = tabs_info(tab)
                print('    url: %s' % (url['url'],))
                if '%' in url['url']:
                    try:
                        print('    qurl: %s' % (unicode(urllib.unquote_plus(str(url['url'])), 'utf-8'),))
                    except Exception:
                        pass
                try:
                    print(u('    title: %s') % (url.get('title'),))
                except UnicodeError:
                    print('    title: %s' % (url.get('title').encode(errors='backslashreplace'),))
            else:
                tab = window['tabs'][window['selected']-1]
                url = tabs_info(tab)
                print('Window %d: Selected tab (%d/%d): %s' %
                      (w+1, window['selected'], len(window['tabs']), url['url']))

        saved_sessionstore = list(dump4diff(store.sessionstore, 'sessionstore'))
        if store.checkpoints is not None:
            saved_checkpoints = list(dump4diff(store.checkpoints, 'checkpoints'))
        # proceed action
        if args.action == 'wselect':
            store.sessionstore['selectedWindow'] = args.window
        elif args.action == 'tselect':
            store.sessionstore['windows'][args.window-1]['selected'] = args.tab
        elif args.action == 'wclose':
            window = store.sessionstore['windows'].pop(args.window-1)
            if len(store.sessionstore['windows']) > store.sessionstore['selectedWindow']:
                store.sessionstore['selectedWindow'] = len(store.sessionstore['windows'])
            if 'busy' in window:
                del window['busy']
            window['closedAt'] = int(time.time())
            tab = window['tabs'][window['selected']-1]
            url = tabs_info(tab)
            window['title'] = url['title']
            store.sessionstore['_closedWindows'].append(window)
        elif args.action == 'tclose':
            window = store.sessionstore['windows'][args.window-1]
            tab = window['tabs'].pop(args.tab-1)
            if len(window['tabs']) > window['selected']:
                window['selected'] = len(window['tabs'])
            url = tabs_info(tab)
            closed_tab = dict(closedAt=int(time.time()), pos=args.tab, state=tab)
            if 'title' in url:
                closed_tab['title'] = url['title']
            if 'image' in tab:
                closed_tab['image'] = tab['image']
            window['_closedTabs'].append(closed_tab)
        elif args.action == 'fix':
            if store.checkpoints is not None:
                store.checkpoints.update(dict((k, True) for k in checkpointOrder))
            if 'state' in store.sessionstore['session']:
                store.sessionstore['session']['state'] = 'stopped'
            if 'recentCrashes' in store.sessionstore['session']:
                del store.sessionstore['session']['recentCrashes']
            if 1 and (len(store.sessionstore['windows']) == 1 and  # added for indentation warned by flake8
                      len(store.sessionstore['windows'][0]['tabs']) == 1 and
                      len(store.sessionstore['windows'][0]['tabs'][0]['entries']) == 1 and
                      store.sessionstore['windows'][0]['tabs'][0]['entries'][0]['url'] == 'about:sessionrestore' and
                      store.sessionstore['windows'][0]['tabs'][0]['formdata']['url'] == 'about:sessionrestore'):
                store.sessionstore = store.sessionstore['windows'][0]['tabs'][0]['formdata']['id']['sessionData']

        # save/pretend
        if want_save and args.pretend:
            new_sessionstore = list(dump4diff(store.sessionstore, 'sessionstore'))
            for line in difflib.unified_diff(saved_sessionstore, new_sessionstore,
                                             'sessionstore.js orig', 'sessionstore.js changed'):
                sys.stdout.write(line)
            # print(json.dumps(store.sessionstore, ensure_ascii=True, separators=(',', ':')))
            if store.checkpoints is not None:
                new_checkpoints = list(dump4diff(store.checkpoints, 'checkpoints'))
                for line in difflib.unified_diff(saved_checkpoints, new_checkpoints,
                                                 'sessionCheckpoints.json orig', 'sessionCheckpoints.json changed'):
                    sys.stdout.write(line)
                # print(json.dumps(store.checkpoints))
        elif want_save:
            store.save()
    if args.debug:
        print('Done.')


if __name__ == '__main__':
    sys.exit(main(sys.argv))
