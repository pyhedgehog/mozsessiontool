import ast
import os
import sys
import codecs
from setuptools import setup, Command
try:
    from six import StringIO
except ImportError:
    StringIO = None

classifiers = [
    'Development Status :: 2 - Pre-Alpha',
    'Environment :: Console',
    'Intended Audience :: End Users/Desktop',
    'License :: Public Domain',
    'Operating System :: OS Independent',
    'Programming Language :: Python',
    'Programming Language :: Python :: 2',
    # <= 2.6 not supported by pip team
    'Programming Language :: Python :: 2.7',
    'Programming Language :: Python :: 3',
    # <= 3.2 not supported by pip team
    'Programming Language :: Python :: 3.3',
    'Programming Language :: Python :: 3.4',
    'Programming Language :: Python :: 3.5',
    'Programming Language :: Python :: 3.6',
    'Programming Language :: Python :: 3.7',
    'Topic :: Software Development :: Libraries :: Python Modules',
    'Topic :: Internet :: WWW/HTTP :: Session',
    'Topic :: Utilities'
]

current_dir = os.path.abspath(os.path.dirname(__file__))
with codecs.open(os.path.join(current_dir, 'README.rst'), 'r', 'utf8') as readme_file:
    # with codecs.open(os.path.join(current_dir, 'CHANGES.rst'), 'r', 'utf8') as changes_file:
        long_description = readme_file.read()  # + '\n\n\n' + changes_file.read()

version = None
with open("mozsessiontool.py", "rb") as init_file:
    t = ast.parse(init_file.read(), filename="mozsessiontool.py", mode="exec")
    assert isinstance(t, ast.Module)
    assignments = filter(lambda x: isinstance(x, ast.Assign), t.body)
    for a in assignments:
        if not (len(a.targets) != 1 or
                not isinstance(a.targets[0], ast.Name) or
                a.targets[0].id != "__version__" or
                not isinstance(a.value, ast.Str)):
            version = a.value.s

try:
    __file__
except:
    __file__ = os.path.abspath(sys.argv[0])


setup(name='mozsessiontool',
      version=version,
      url='https://github.com/pyhedgehog/mozsessiontool',
      license="UnLicense",
      description='Tool to see/alter firefox session information',
      long_description=long_description,
      classifiers=classifiers,
      maintainer='Michael Dubner',
      maintainer_email='pyhedgehog@list.ru',
      py_modules=['mozsessiontool'],
      entry_points={
          'console_scripts': [
              'mozsessiontool = mozsessiontool:main',
          ],
      },
      install_requires=[
          'six',
          'lz4',
      ],
      )
