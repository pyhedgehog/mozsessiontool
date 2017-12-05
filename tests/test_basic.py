import sys
import os.path
import pprint
import pytest

testdir = os.path.dirname(__file__)
sys.path.append(os.path.dirname(testdir))

try:
    import mozsessiontool
except ImportError:
    print(os.getcwd())
    pprint.pprint(sys.path)
    raise


def test_help(capsys):
    saveout, saveerr = sys.stdout, sys.stderr
    for opt in ('-h', '--help'):
        with pytest.raises(SystemExit):
            mozsessiontool.main(['mozsessiontool.py', opt])
        assert sys.stdout is saveout
        assert sys.stderr is saveerr
        assert not sys.stdout.closed
        assert not sys.stderr.closed
        assert not saveout.closed
        assert not saveerr.closed
        out, err = capsys.readouterr()
        assert err == ''
        assert out
        assert out == model_help


def test_info(capsys):
    mozsessiontool.main(['mozsessiontool.py', '--test', testdir])
    out, err = capsys.readouterr()
    assert err == ''
    assert out
    assert out == model_info


def test_quiet(capsys):
    for opt in ('-q', '--quiet'):
        mozsessiontool.main(['mozsessiontool.py', '--test', opt, testdir])
        out, err = capsys.readouterr()
        assert err == ''
        assert out
        assert out == model_quiet


def test_grep(capsys):
    for opt in ('-g', '--grep'):
        mozsessiontool.main(['mozsessiontool.py', '--test', opt, '.', testdir])
        out, err = capsys.readouterr()
        assert err == ''
        assert out
        assert out == model_grep
        mozsessiontool.main(['mozsessiontool.py', '--test', '-q', opt, 'py', testdir])
        out, err = capsys.readouterr()
        assert err == ''
        assert out
        assert out == model_grep_py


def test_tab(capsys):
    for topt in ('-t', '--tab'):
        mozsessiontool.main(['mozsessiontool.py', '--test', topt, '3', testdir])
        out, err = capsys.readouterr()
        assert err == ''
        assert out
        assert out == model_tab
        for wopt in ('-t', '--tab'):
            mozsessiontool.main(['mozsessiontool.py', '--test', wopt, '1', topt, '3', testdir])
            out, err = capsys.readouterr()
            assert err == ''
            assert out
            assert out == model_tab


def test_tab_err(capsys):
    for opt in ('-t', '--tab'):
        with pytest.raises(SystemExit):
            mozsessiontool.main(['mozsessiontool.py', '--test', opt, '4', testdir])
        out, err = capsys.readouterr()
        assert err == model_tab_err
        assert out == ''


def test_win_err(capsys):
    for opt in ('-w', '--win'):
        with pytest.raises(SystemExit):
            mozsessiontool.main(['mozsessiontool.py', '--test', opt, '2', testdir])
        out, err = capsys.readouterr()
        assert err == model_win_err
        assert out == ''


def test_pretend_fix(capsys):
    for qopt in ('-q', '--quiet'):
        for nopt in ('-n', '--pretend', '--dry-run'):
            for fopt in ('-f', '--fix'):
                mozsessiontool.main(['mozsessiontool.py', '--test', qopt, nopt, fopt, testdir])
                out, err = capsys.readouterr()
                assert err == ''
                assert out
                assert out == model_pretend_fix
            for aopt in ('--action', '--do'):
                mozsessiontool.main(['mozsessiontool.py', '--test', qopt, nopt, aopt, 'fix', testdir])
                out, err = capsys.readouterr()
                assert err == ''
                assert out
                assert out == model_pretend_fix


model_help = '''\
usage: mozsessiontool.py [-h] [--quiet] [--pretend] [--window WINDOW]
                         [--tab TAB] [--grep STR]
                         [--action {wselect,tselect,wclose,tclose,fix}]
                         [--wselect] [--tselect] [--wclose] [--tclose] [--fix]
                         [FILE]

Process firefox sessionstore.js

positional arguments:
  FILE                  Path to sessionstore.js or profile itself (path or
                        name)

optional arguments:
  -h, --help            show this help message and exit
  --quiet, -q           Be less verbose
  --pretend, --dry-run, -n
                        Do nothing - only show changes
  --window WINDOW, -w WINDOW
                        Use window instead of current
  --tab TAB, -t TAB     Use tab instead of current
  --grep STR, --find STR, -g STR
                        Find tabs with URL containing STR

actions:
  --action {wselect,tselect,wclose,tclose,fix}, --do {wselect,tselect,wclose,tclose,fix}
                        Do some changes to saved session state (use only if
                        firefox is down)
  --wselect             Change current window to selected (short form for
                        --action=wselect)
  --tselect             Change current tab to selected (short form for
                        --action=tselect)
  --wclose, -W          Close selected (or current) window (short form for
                        --action=wclose)
  --tclose, -T          Close selected (or current) tab (short form for
                        --action=tclose)
  --fix, -f             Fix saved session state (short form for --action=fix)
'''

model_info = u'''\
tests
test:test -rw-rw-rw- 179025 sometimes (ages ago)
lastUpdate: 0; recentCrashes: 0; startTime: 0
checkpoint: Running (sessionstore-windows-restored)
Selected window 1:
  Selected tab (2/3):
    url: https://github.com/pyhedgehog/mozsessiontool
    title: pyhedgehog/mozsessiontool \xb7 GitHub - \u0442\u0435\u0441\u0442
'''
model_quiet = u'''\
tests
test:test -rw-rw-rw- 179025 sometimes
checkpoint: Running (sessionstore-windows-restored)
window 1 (selected): 3 tabs
'''

model_grep = u'''\
tests
test:test -rw-rw-rw- 179025 sometimes (ages ago)
lastUpdate: 0; recentCrashes: 0; startTime: 0
checkpoint: Running (sessionstore-windows-restored)
Selected window 1 (3 tabs):
  tab 1: https://www.google.com/
  tab 2: https://github.com/pyhedgehog/mozsessiontool
  tab 3: https://www.python.org/
'''

model_grep_py = u'''\
tests
test:test -rw-rw-rw- 179025 sometimes
checkpoint: Running (sessionstore-windows-restored)
Selected window 1 (3 tabs):
  tab 2: https://github.com/pyhedgehog/mozsessiontool
  tab 3: https://www.python.org/
'''

model_pretend_fix = u'''\
tests
test:test -rw-rw-rw- 179025 sometimes
checkpoint: Running (sessionstore-windows-restored)
window 1 (selected): 3 tabs
--- sessionstore.js orig
+++ sessionstore.js changed
@@ -2,9 +2,8 @@
 sessionstore['_closedWindows'].len() = 0
 sessionstore['global'].keys() = []
 sessionstore['selectedWindow'] = 1
-sessionstore['session'].keys() = ['lastUpdate', 'recentCrashes', 'startTime']
+sessionstore['session'].keys() = ['lastUpdate', 'startTime']
 sessionstore['session']['lastUpdate'] = 0
-sessionstore['session']['recentCrashes'] = 0
 sessionstore['session']['startTime'] = 0
 sessionstore['windows'].len() = 1
 sessionstore['windows'][0].keys() = ['_closedTabs', 'busy', 'cookies', 'height', 'screenX', 'screenY', 'selected', 'sizemode', 'tabs', 'width']
--- sessionCheckpoints.json orig
+++ sessionCheckpoints.json changed
@@ -1,4 +1,10 @@
-checkpoints.keys() = ['final-ui-startup', 'profile-after-change', 'sessionstore-windows-restored']
+checkpoints.keys() = ['final-ui-startup', 'profile-after-change', 'profile-before-change', 'profile-change-net-teardown', 'profile-change-teardown', 'quit-application', 'quit-application-granted', 'sessionstore-final-state-write-complete', 'sessionstore-windows-restored']
 checkpoints['final-ui-startup'] = True
 checkpoints['profile-after-change'] = True
+checkpoints['profile-before-change'] = True
+checkpoints['profile-change-net-teardown'] = True
+checkpoints['profile-change-teardown'] = True
+checkpoints['quit-application'] = True
+checkpoints['quit-application-granted'] = True
+checkpoints['sessionstore-final-state-write-complete'] = True
 checkpoints['sessionstore-windows-restored'] = True
'''

model_tab = u'''\
tests
test:test -rw-rw-rw- 179025 sometimes (ages ago)
lastUpdate: 0; recentCrashes: 0; startTime: 0
checkpoint: Running (sessionstore-windows-restored)
Selected window 1:
  Selected tab (3/3):
    url: https://www.python.org/
    title: Welcome to Python.org
'''

model_tab_err = u'''\
usage: mozsessiontool.py [-h] [--quiet] [--pretend] [--window WINDOW]
                         [--tab TAB] [--grep STR]
                         [--action {wselect,tselect,wclose,tclose,fix}]
                         [--wselect] [--tselect] [--wclose] [--tclose] [--fix]
                         [FILE]
mozsessiontool.py: error: Invalid -t value (4) - must be in range 1-3
'''

model_win_err = u'''\
usage: mozsessiontool.py [-h] [--quiet] [--pretend] [--window WINDOW]
                         [--tab TAB] [--grep STR]
                         [--action {wselect,tselect,wclose,tclose,fix}]
                         [--wselect] [--tselect] [--wclose] [--tclose] [--fix]
                         [FILE]
mozsessiontool.py: error: Invalid -w value (2) - must be in range 1-1
'''
