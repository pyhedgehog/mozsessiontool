#!/usr/bin/env python
# This code is in Public Domain (see LICENSE)
import os
import sys
import stat
import glob
import json
import time
import types
import argparse
import urllib
import datetime
import pprint
try: import pwd
except ImportError: pwd = None
try: import grp
except ImportError: grp = None

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
    if stat.S_ISDIR(mode): res = 'd'
    elif stat.S_ISCHR(mode): res = 'c'
    elif stat.S_ISBLK(mode): res = 'b'
    elif stat.S_ISREG(mode): res = '-'
    elif stat.S_ISFIFO(mode): res = 'p'
    elif stat.S_ISLNK(mode): res = 'l'
    elif stat.S_ISSOCK(mode): res = 's'
    else: res = '?'
    def get3mod(mode, r, w, x, **ext):
        res = ''
        res += '-r'[mode&r==r]
        res += '-w'[mode&w==w]
        if not ext:
            res += '-x'[mode&x==x]
        else:
            assert len(ext)==1
            l = list(ext.keys())[0]
            s = ext[l]
            l = l.upper()+l
            res += ['-x',l][mode&s==s][mode&x==x]
        return res
    res += get3mod(mode, stat.S_IRUSR, stat.S_IWUSR, stat.S_IXUSR, s=stat.S_ISUID)
    res += get3mod(mode, stat.S_IRGRP, stat.S_IWGRP, stat.S_IXGRP, s=stat.S_ISGID)
    res += get3mod(mode, stat.S_IROTH, stat.S_IWOTH, stat.S_IXOTH, t=stat.S_ISVTX)
    return res

inttypes = [type(0)]
try: inttypes.append(types.LongType)
except: pass
inttypes = tuple(inttypes)

try: types.UnicodeType
except:
    def u(s): return s
else:
    def u(s): return unicode(s)

def simplify(value):
    if type(value) == getattr(types,'UnicodeType',None):
        try: return str(value)
        except UnicodeError: pass
    if type(value) in inttypes:
        if value >= 946674000000:
            return time.ctime(value/1000.)
        if value >= 946674000:
            return time.ctime(value)
    if isinstance(value, datetime.timedelta):
        s = '%d minute%s' % (value.seconds/60%60,'s'*(value.seconds/60%60>1))
        if value.seconds%60: s += ' %d second%s' % (value.seconds%60,'s'*(value.seconds%60>1))
        if value.seconds/3600: s = '%d hour%s %s' % (value.seconds/3600,'s'*(value.seconds/3600>1),s)
        if value.days: s = '%d day%s %s' % (value.days,'s'*(value.days>1),s)
        return s
    return str(value)

def get_default_sessionstore():
    if 'win' in sys.platform: # darwin not supported yet
        profiles = os.path.join(os.environ['USERPROFILE'],*('Application Data/Mozilla/Firefox/Profiles'.split('/')))
    else:
        profiles = os.path.expanduser('~/.mozilla/firefox')
    #print(profiles)
    l = glob.glob(os.path.join(profiles,"*.default"))
    #print(l)
    profile = l[0]
    #print(profile)
    path = os.path.join(profile,"sessionstore.js")
    if not os.path.exists(path) and os.path.exists(os.path.join(profile,"sessionstore-backups","recovery.js")):
        path = os.path.join(profile,"sessionstore-backups","recovery.js")
    #print(path)
    checkpointPath = None
    if os.path.exists(os.path.join(profile,"sessionCheckpoints.json")):
        checkpointPath = os.path.join(profile,"sessionCheckpoints.json")
    return path,checkpointPath

class MozDefaults(argparse.Namespace):
    _sessionstore = _checkpoints = _default_sessionstore = None
    def __get_default_sessionstore(self):
        if self._default_sessionstore is None:
            self._default_sessionstore = get_default_sessionstore()
        return self._default_sessionstore

    @property
    def sessionstore(self):
        if self._sessionstore is None:
            return self.__get_default_sessionstore()[0]
        return self._sessionstore

    @sessionstore.setter
    def sessionstore(self, value):
        if value is None: return
        if os.path.isdir(value):
            value = os.path.join(value, 'sessionstore.js')
        self._sessionstore = value

    @sessionstore.deleter
    def sessionstore(self):
        del self._sessionstore

    @property
    def checkpoints(self):
        if self._checkpoints is None:
            if self._sessionstore is not None:
                dirname = os.path.dirname(self._sessionstore)
                if os.path.basename(dirname)=="sessionstore-backups":
                    dirname = os.path.dirname(dirname)
                if os.path.exists(os.path.join(dirname,"sessionCheckpoints.json")):
                    return os.path.join(dirname,"sessionCheckpoints.json")
                return None
            return self.__get_default_sessionstore()[1]
        return self._checkpoints

    @checkpoints.setter
    def checkpoints(self, value):
        self._checkpoints = value

    @checkpoints.deleter
    def checkpoints(self):
        del self._checkpoints

checkpoints = ("profile-after-change", "final-ui-startup",
    "sessionstore-windows-restored", "quit-application-granted",
    "quit-application", "sessionstore-final-state-write-complete",
    "profile-change-net-teardown", "profile-change-teardown",
    "profile-before-change"
)
checkpointNames = {
    "profile-after-change":"Starting",
    "final-ui-startup":"Started, Loading session",
    "sessionstore-windows-restored":"Running",
    "quit-application-granted":"Stopping",
    "quit-application":"Hidden",
    "sessionstore-final-state-write-complete":"Session saved",
    "profile-change-net-teardown":"Session saved, Connections closed",
    "profile-change-teardown":"Session saved, Connections closed, Profile closing",
    "profile-before-change":"Stopped",
}

def showcheckpoint(sessionCheckpoints):
    state = "Init"
    sessionCheckpoints = sessionCheckpoints.copy()
    for i in checkpoints:
        if i in sessionCheckpoints and sessionCheckpoints[i]==True:
            state = checkpointNames[i]
            sessionCheckpoints.pop(i)
            continue
        rest = ""
        if sessionCheckpoints:
          rest = "; "+(", ".join(["","not "][not v]+k for k,v in sessionCheckpoints.items()))
        return state+rest
    return state

def main(argv):
    global args, parser
    parser = argparse.ArgumentParser(description='Process firefox sessionstore.js')
    parser.add_argument('--debug-args', '-D', action='store_true', help=argparse.SUPPRESS)
    parser.add_argument('--quiet', '-q', action='store_true', help='Be less verbose')
    parser.add_argument('sessionstore', nargs='?', metavar='FILE', help='Path to sessionstore.js')
    parser.add_argument('--window', '-w', type=int, help='Use window instead of current')
    parser.add_argument('--tab', '-t', type=int, help='Use tab instead of current')
    parser.add_argument('--action', '--do', choices='wselect tselect wclose tclose'.split(), help='Do some changes to saved session state (use only if firefox is down)')
    args = parser.parse_args(namespace=MozDefaults())
    want_save = args.action is not None
    if args.debug_args:
        print(args)
        return

    checkpoints_fd = None
    mode_tail = 't'
    if sys.version_info[:2]>=(3,0):
      open_args = dict(encoding='utf-8')
    else:
      open_args = {}
    sessionstore_fd = open(args.sessionstore,['r','r+'][want_save]+mode_tail,**open_args)
    try:
        st = os.fstat(sessionstore_fd.fileno())
        sessionstore = json.load(sessionstore_fd)
        if args.quiet:
            print('%s:%s %s %d %s' % (getpwuid(st.st_uid), getgrgid(st.st_gid), getstmode(st.st_mode), st.st_size, time.ctime(st.st_ctime)))
        else:
            print('%s:%s %s %d %s (%s ago)' % (getpwuid(st.st_uid), getgrgid(st.st_gid), getstmode(st.st_mode), st.st_size, time.ctime(st.st_ctime), simplify(datetime.timedelta(seconds=time.time()-st.st_ctime))))
            print('; '.join(sorted('%s: %s' % (str(k),simplify(v)) for k,v in sessionstore['session'].items())))
            #print('selected: %s' % (sessionstore['selectedWindow'],))
        if args.checkpoints and os.path.isfile(args.checkpoints):
            checkpoints_fd = open(args.checkpoints,['r','r+'][want_save]+mode_tail,**open_args)
            checkpoints = json.load(checkpoints_fd)
            print('checkpoint: %s' % (showcheckpoint(checkpoints),))
        for w in range(len(sessionstore['windows'])):
            selected = w+1==max(1,sessionstore['selectedWindow'])
            tabs = sessionstore['windows'][w]
            if args.quiet:
                print('window %d%s: %d tabs' % (w+1,['',' (selected)'][selected],len(tabs['tabs'])))
            elif selected:
                print('Selected window %d:' % (w+1,))
                tab = tabs['tabs'][tabs['selected']-1]
                if tab.get('entries'):
                    url = tab['entries'][tab['index']-1]
                else:
                    url = {'url':tab['userTypedValue'],'title':'Loading...'}
                print('  Selected tab (%d/%d):' % (tabs['selected'],len(tabs['tabs'])))
                print('    url: %s' % (url['url'],))
                if '%' in url['url']:
                    try:
                        print('    qurl:' % (unicode(urllib.unquote_plus(str(url['url'])),'utf-8'),))
                    except Exception:
                        pass
                try:
                    print(u('    title: %s') % (url.get('title'),))
                except UnicodeError:
                    print('    title: %r' % (url.get('title'),))
            else:
                tab = tabs['tabs'][tabs['selected']-1]
                url = tab['entries'][tab['index']-1]
                print('Window %d: Selected tab (%d/%d): %s' % (w+1, tabs['selected'],len(tabs['tabs']),url['url']))
    finally:
        sessionstore_fd.close()
        if checkpoints_fd is not None:
            checkpoints_fd.close()

if __name__=='__main__':
    sys.exit(main(sys.argv))
