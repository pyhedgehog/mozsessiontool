#!/usr/bin/env python
import os
import sys
import stat
import glob
import json
import pwd
import grp
import time
import argparse
import urllib
import datetime
import pprint

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
            l = ext.keys()[0]
            s = ext[l]
            l = l.upper()+l
            res += ['-x',l][mode&s==s][mode&x==x]
        return res
    res += get3mod(mode, stat.S_IRUSR, stat.S_IWUSR, stat.S_IXUSR, s=stat.S_ISUID)
    res += get3mod(mode, stat.S_IRGRP, stat.S_IWGRP, stat.S_IXGRP, s=stat.S_ISGID)
    res += get3mod(mode, stat.S_IROTH, stat.S_IWOTH, stat.S_IXOTH, t=stat.S_ISVTX)
    return res

def simplify(value):
    if type(value) == type(u''):
        try: return str(value)
        except UnicodeError: pass
    if type(value) in (type(0),type(0l)):
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
    return glob.glob(os.path.expanduser('~/.mozilla/firefox/*.default/sessionstore.js'))[0]

class MozDefaults(argparse.Namespace):
    _sessionstore = _default_sessionstore = None
    @property
    def sessionstore(self):
        if self._sessionstore is None:
            if self._default_sessionstore is None:
                self._default_sessionstore = get_default_sessionstore()
            return self._default_sessionstore
        return self._sessionstore

    @sessionstore.setter
    def sessionstore(self, value):
        self._sessionstore = value

    @sessionstore.deleter
    def sessionstore(self):
        del self._sessionstore

def main(argv):
    global args, parser
    parser = argparse.ArgumentParser(description='Process firefox sessionstore.js')
    parser.add_argument('--debug-args', action='store_true', help=argparse.SUPPRESS)
    parser.add_argument('--quiet', action='store_true', help='Be less verbose')
    parser.add_argument('sessionstore', nargs='?', metavar='FILE', help='Path to sessionstore.js')
    parser.add_argument('--window', type=int, help='Use window instead of current')
    parser.add_argument('--tab', type=int, help='Use tab instead of current')
    parser.add_argument('--action', choices='wselect tselect wclose tclose'.split(), help='Do some changes to saved session state (use only if firefox is down)')
    args = parser.parse_args(namespace=MozDefaults())
    want_save = args.action is not None
    if args.debug_args:
        print args
        return

    f = open(args.sessionstore,['rt','r+t'][want_save])
    st = os.fstat(f.fileno())
    sessionstore = json.load(f)
    f.close()
    if args.quiet:
        print '%s:%s %s %d %s' % (getpwuid(st.st_uid), getgrgid(st.st_gid), getstmode(st.st_mode), st.st_size, time.ctime(st.st_ctime))
    else:
        print '%s:%s %s %d %s (%s ago)' % (getpwuid(st.st_uid), getgrgid(st.st_gid), getstmode(st.st_mode), st.st_size, time.ctime(st.st_ctime), simplify(datetime.timedelta(seconds=time.time()-st.st_ctime)))
        print '; '.join(sorted('%s: %s' % (str(k),simplify(v)) for k,v in sessionstore['session'].items()))
        #print 'selected:', sessionstore['selectedWindow']
    for w in range(len(sessionstore['windows'])):
        selected = w+1==max(1,sessionstore['selectedWindow'])
        tabs = sessionstore['windows'][w]
        if args.quiet:
            print 'window %d%s: %d tabs' % (w+1,['',' (selected)'][selected],len(tabs['tabs']))
        elif selected:
            print 'Selected window %d:' % (w+1,)
            tab = tabs['tabs'][tabs['selected']-1]
            url = tab['entries'][tab['index']-1]
            print '  Selected tab (%d/%d):' % (tabs['selected'],len(tabs['tabs']))
            print '    url:', url['url']
            if '%' in url['url']:
                try:
                    print '    qurl:', unicode(urllib.unquote_plus(str(url['url'])),'utf-8')
                except Exception:
                    pass
            print '    title:', url.get('title')
        else:
            tab = tabs['tabs'][tabs['selected']-1]
            url = tab['entries'][tab['index']-1]
            print 'Window %d: Selected tab (%d/%d): %s' % (w+1, tabs['selected'],len(tabs['tabs']),url['url'])

if __name__=='__main__':
    sys.exit(main(sys.argv))
