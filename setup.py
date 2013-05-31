import os.path
from setuptools import setup

def read(fname):
    return open(os.path.join(os.path.dirname(__file__), fname)).read()

INSTALL_REQUIRES=[
   'praw',
]

setup(
    name = "redem",
    version = "0.0.1",
    #author = "",
    #author_email = "wes@wrd.nu",
    #description = (""),
    license = "BSD",
    #keywords = "reddit backup cache",
    #url = "http://packages.python.org/redem",
    #url = "http://redem.readthedocs.org",
    packages=['redem', 'tests'],
    long_description=read('README.rst'),
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Topic :: Utilities",
        "License :: OSI Approved :: BSD License",
    ],
    entry_points="""\
    [console_scripts]
    redem = redem.redem:main
    """,
    install_requires=INSTALL_REQUIRES,
)
