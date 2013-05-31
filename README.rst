redem
=======

Generates a single-page HTML view of comment and submission history.

A utility for referencing personal comment history.

Templates data received from API and/or JSON.

.. note: Caveat: this approach is very slow, due to API throttling.
   (TODO, FIXME, XXX)

install
--------
::

    python setup.py install


development setup
-------------------
::

    python setup.py develop


requires
--------
* `praw`_ Python Reddit API
* `rfc3987`_ URI regexes
* `Jinja2`_ Templates

.. _praw: https://pypi.python.org/pypi/praw
.. _rfc3987: https://pypi.python.org/pypi/rfc3987
.. _Jinja2: https://pypi.python.org/pypi/Jinja2
