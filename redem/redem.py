#!/usr/bin/env python
# encoding: utf-8
from __future__ import print_function
"""
redem - backup personal reddit history for easier local search

- JSON
- Single-File HTML

https://github.com/reddit/reddit/wiki/API
"""
import codecs
import collections
import datetime
import json
import logging
import os.path
import unittest
from urllib.parse import urlparse
from collections import Counter, OrderedDict
from operator import attrgetter, itemgetter

import bs4
import praw
import rfc3987
import urlobject
from jinja2 import Markup, Environment, PackageLoader

__APPNAME__ = "redem"
__VERSION__ = "0.1.2"
__USER_AGENT__ = '%s (praw)\%s' % (__APPNAME__, __VERSION__)

uri_rgx = rfc3987.get_compiled_pattern('URI')  # URI_reference
log = logging.getLogger('%s.cli' % __APPNAME__)

SUBMISSION_ATTRS = (
    'id',
    #'author',
    'num_comments',
    'selftext',
    'selftext_html',
    'subreddit_id',
    'title',
    'url',
    'domain',
    'created',
    'created_utc',
    'ups',
    'downs',
    'score',
    'permalink',
)

COMMENT_ATTRS = (
    'link_id',
    'link_title',
    'id',
    #'author',
    'body',
    'body_html',
    'created',
    'created_utc',
    'edited',
    'score',
    'ups',
    'downs',
    #'permalink', # really slow
    )

_SUBREDDIT_URLS = {}


def get_subreddit_url(subreddit, subreddit_id):
    url = _SUBREDDIT_URLS.setdefault(subreddit_id, subreddit.url)
    return url

_SUBREDDIT_NAMES = {}


def get_subreddit_name(subreddit, subreddit_id):
    name = _SUBREDDIT_NAMES.setdefault(subreddit_id, subreddit.display_name)
    return name

_SUBMISSION_URLS = {}


def get_submission_url(submission):
    url = _SUBMISSION_URLS.setdefault(submission.id, submission.url)
    return url

_SUBMISSION_PERMALINKS = {}


def get_submission_permalink(submission):
    url = _SUBMISSION_PERMALINKS.setdefault(
        submission.id,
        submission.permalink)
    return url


def comment_permalink(comment):
    return os.path.join(
        get_submission_permalink(comment.submission),
        comment.id)
    #return (
    #u"http://reddit.com/r/{subreddit}/comments/{link_id}/{_link_title}/{id}".
    #format(**comment))

_get_comment_attrs = attrgetter(*COMMENT_ATTRS)


def comment_to_dict(comment):
    _comment_attrs = _get_comment_attrs(comment)
    _comment = dict(zip(COMMENT_ATTRS, _comment_attrs))
    _comment['type'] = 'http://reddit.com/ns/comment'
    _comment['author_name'] = comment.author.name
    _comment['subreddit'] = get_subreddit_name(
        comment.subreddit, comment.subreddit_id)
    _comment['permalink'] = comment_permalink(comment)
    return _comment

_get_submission_attrs = attrgetter(*SUBMISSION_ATTRS)


def submission_to_dict(submission):
    _sub_attrs = _get_submission_attrs(submission)
    _sub = dict(zip(SUBMISSION_ATTRS, _sub_attrs))
    _sub['_type'] = 'http://reddit.com/ns/submission'
    _sub['author_name'] = submission.author.name
    _sub['subreddit'] = get_subreddit_name(
        submission.subreddit,
        submission.subreddit_id)
    return _sub


def iter_comments(user, limit=None, pagesize=None):
    comments = user.get_comments(limit=pagesize)
    for i, comment in enumerate(comments):
        if limit and i >= limit:
            break
        yield comment


def iter_submissions(user, limit=None, pagesize=None):
    submissions = user.get_submitted(limit=pagesize)
    for i, submission in enumerate(submissions):
        if limit and i >= limit:
            break
        yield submission


def iter_liked(user, limit=None, pagesize=None):
    likeds = user.get_liked(limit=pagesize)
    for i, liked in enumerate(likeds):
        if limit and i >= limit:
            break
        yield liked


def iter_uris_regex(text, filterfunc=None):
    """
    Yield things that look like URIs from the given text

    :param filterfunc: callable to filter urls, defaults to .startswith('http')
    """
    if filterfunc is None:
        filterfunc = lambda uri: uri[:4].lower() == 'http'

    for uri in uri_rgx.findall(text):
        if filterfunc(uri):
            yield uri
        else:
            log.debug('filtered_uri: %r' % uri)


def iter_uris_bs4(text):
    bs = bs4.BeautifulSoup(text)
    links = bs.find_all('a')
    for link in links:
        yield link.get('href')  # link.text

iter_uris = iter_uris_bs4


def iter_comment_uris(comment):
    #yield '/'.join(comment['permalink'].split('/')[:-1])
    yield comment['permalink']
    for uri in iter_uris(comment['body_html']):
        yield uri


def iter_submission_uris(submission):
    permalink = submission.get("permalink")
    if permalink:
        yield permalink
    url = submission.get('url')
    if url:
        yield url

    selftext = submission.get("selftext_html")
    if selftext:
        for uri in iter_uris(selftext):
            yield uri


def read_https_domains(filename):
    """
    ::

        github.com
        en.wikipedia.org

    """
    https_domains = {}
    if os.path.exists(filename):
        with codecs.open(filename, 'r', encoding='utf8') as f:
            https_domains = {
                domain.rstrip(): 1 for domain in f.read().split('\n')}
    return https_domains


DATADIR = os.path.join(os.path.dirname(__file__), '..', 'data')
https_domains_file = os.path.join(DATADIR, 'https_domains.txt')
ALWAYS_HTTPS = read_https_domains(https_domains_file)


def httpsify(url):
    if url.netloc in ALWAYS_HTTPS:
        url = url.with_scheme('https')
    elif url.netloc.endswith('readthedocs.org'):
        url = url.with_scheme('https')
    return url


def read_netloc_mappings(filename):
    """
    ::

        en.m.wikipedia.org  en.wikipedia.org

    """
    netloc_mappings = {}
    if os.path.exists(filename):
        with codecs.open(filename, 'r', encoding='utf8') as f:
            netloc_mappings = dict(
                tuple(x.rstrip().split()) for x in f.readlines())
    return netloc_mappings


netloc_mappings_file = os.path.join(DATADIR, 'netloc_mappings.txt')
NETLOC_MAPPINGS = read_netloc_mappings(netloc_mappings_file)


def normalize_netloc(url):
    norm_netloc = NETLOC_MAPPINGS.get(url.netloc)
    if norm_netloc:
        url = url.with_netloc(norm_netloc)
    elif url.netloc.endswith('rtfd.org'):
        url = url.with_netloc(
            u'.'.join((url.netloc.split('.')[:-2] + ['readthedocs.org'])))
    elif url.netloc.endswith('github.com'):
        components = url.netloc.split('.')
        if (len(components) == 3 and components[0] not in (
                'help', 'status', 'gist')):
            url = url.with_netloc(u'.'.join(components[:-1] + ['io']))
    return url


def canonicalize_uri(uri):
    url = urlobject.URLObject(uri)

    url = normalize_netloc(url)

    if url.scheme:
        if not url.startswith(url.scheme):
            url = url.with_scheme(url.scheme)

        url = httpsify(url)
    else:
        if url.netloc == '':
            if url.path.startswith('/r/') or url.path.startswith('/u/'):
                url = url.with_netloc('www.reddit.com').with_scheme('http')
    # TODO: no path :: trailing slash wrd.nu wrd.nu/
    return url

URIThing = collections.namedtuple(
    'URIThing',
    ('uri', 'canonical_uri', 'source_obj'))


def iter_all_uris(data):
    """
    :returns: iterator of (uri, canonical_uri, source_obj)
    """
    comments = data['comments']
    submissions = data['submissions']

    for comment in comments:
        for uri in iter_comment_uris(comment):
            yield URIThing(uri, canonicalize_uri(uri), comment)

    for submission in submissions:
        for uri in iter_submission_uris(submission):
            yield URIThing(uri, canonicalize_uri(uri), comment)


class URIRefCounter(collections.OrderedDict):
    @staticmethod
    def keyfunc(obj):
        return obj.canonical_uri

    @staticmethod
    def valuefunc(obj):
        return (obj.uri, obj.source_obj)  # source_obj_uri TODO

    def push(self, obj, return_count=False, return_reflist=False):
        """
        append a URI to the counter # TODO:
        :param uri: uri(uri, canonical_uri, source)
        """
        #reflist = self.reflist = getattr(
        #   self, 'reflist', self.get_default(self.keyfunc(obj), list)
        #reflist.append( self.valuefunc(obj) )

        key = URIRefCounter.keyfunc(obj)      # obj.canonical_uri
        val = URIRefCounter.valuefunc(obj)    # obj.uri, obj.source_obj

        l = self.setdefault(key, default=[])
        l.append(val)
        if return_count:
            return len(l)
        if return_reflist:
            return l

    def counts(self):
        for key, refs in self.items():
            yield (key, len(refs), refs)

    def print(self, counts=None):
        for key, count, refs in counts or self.counts():
            print(key, count, refs)

    @classmethod
    def group_and_count(cls, iterable, keyfunc=None, valuefunc=None):
        self = cls()
        if keyfunc:
            self.keyfunc = keyfunc
        if valuefunc:
            self.valuefunc = valuefunc
        for obj in iterable:
            self.push(obj)
        #return self.counts()
        return self

    @staticmethod
    def site_frequencies(uri_iterable):
        attrs = attrgetter('netloc', 'path', 'query')  # TODO: fragment
        url_stemmer = lambda x: attrs(urlparse.urlparse(x))
        url_counts = Counter(url_stemmer(uri) for uri in uri_iterable).items()
        by_freq = sorted(url_counts, key=lambda x: x[1], reverse=True)
        by_site = sorted(url_counts, key=lambda x: x[0])
        return {'by_freq': by_freq,
                'by_site': by_site}


def redem(username, output_filename='data.json', limit=None):
    """
    fetch reddit comments and submissions, extract URIs,
    serialize to JSON.

    :param username: reddit username
    :type username: str
    :param output_filename: filename to write JSON data to
    :type output_filename: str path (may contain '~')

    :return: dict of comments and submissions
    :rtype: dict
    """

    r = praw.Reddit(user_agent=__USER_AGENT__)
    r.config.decode_html_entities = True  # XXX
    r.login(username)
    user = r.get_redditor(username)
    comments = iter_comments(user, limit=limit)
    submissions = iter_submissions(user, limit=limit)
    data = {
        '_meta': {
            'date_utc': str(datetime.datetime.utcnow()),
            'username': username,
        },
        'comments': [comment_to_dict(c) for c in comments],
        'submissions': [submission_to_dict(s) for s in submissions],
        #'liked': [liked_to_dict(l) for l in liked]
    }
    return data


def process_urls(data):
    uri_iter = list(iter_all_uris(data))
    uris = sorted(uri_iter, key=lambda x: x.canonical_uri)
    uri_refs = URIRefCounter.group_and_count(uris)
    return sorted(
        ((x[0], x[1]) for x in uri_refs.counts()),
        key=itemgetter(0))


def expand_path(filename):
    return os.path.abspath(os.path.expanduser(filename))


def dump(data, filename=None):
    output_filename = expand_path(filename)
    with codecs.open(output_filename, 'w+', encoding='utf-8') as fp:
        return json.dump(data, fp)


def load(fileobj=None, filename=None):
    input_filename = expand_path(filename)
    if fileobj:
        return json.load(fileobj)
    elif filename:
        with codecs.open(input_filename, 'r', encoding='utf-8') as fp:
            return json.load(fp)


def merge_json_files(filenames, data=None):
    """
    hack to merge json data files

    (would be much faster as a merge/concatenation in pandas)
    """

    sections = ('comments', 'submissions')
    all_data = data if data else OrderedDict()
    for section in sections:
        if section not in all_data:
            all_data[section] = OrderedDict()
    if '_meta' not in all_data:
        all_data['_meta'] = {}
    if 'merged_from' not in all_data['_meta']:
        all_data['_meta']['merged_from'] = OrderedDict()
    for filename in filenames:
        log.info("loading: %r" % filename)
        data = load(filename=filename)
        log.info(data.get('_meta'))
        all_data['_meta']['merged_from'][filename] = data.get('_meta')
        for subset in sections:
            all_objects = all_data[subset]
            objects = data[subset]
            log.info("%-14s: %d" % (subset, len(objects)))
            for item in objects:
                _id = item['id']
                if _id not in all_objects:
                    all_objects[_id] = item
                else:  # item exists
                    existing = all_objects[_id]
                    if 'edited' in item and item['edited']:
                        if item['edited'] > existing['edited']:
                            #log.debug("edited: %s" % item)
                            all_objects[_id] = item
                    else:
                        #TODO
                        #print("TODO")
                        pass
        for subset in sections:
            log.info("subtotal      : %d %s" % (len(all_data[subset]), subset))
    final_data = dict.fromkeys(sections, [])
    final_data['_meta'] = all_data['_meta']
    for subset in sections:
        final_data[subset] = sorted(
            all_data[subset].itervalues(),
            key=lambda x: x['created_utc'],
            reverse=True,  # TODO
        )
    return final_data


def prepare_context_data(data):
    # TODO: data = data.copy()
    # TODO: data['prov'] = ...
    html_keys = {'body_html': 0, 'selftext_html': 0}
    link_keys = {'permalink': 0, 'link': 0}
    date_keys = {'created': 0, 'created_utc': 0, 'edited': 0}
    data['uris'] = process_urls(data)
    for subset in ('comments', 'submissions'):
        _objs = data[subset]
        for _data in _objs:
            for key in list(_data.keys()):
                if key in html_keys:  # XXX TODO FIXME
                    _orig = _data[key]
                    if _orig:
                        _data[key] = Markup(_orig)
                        _data['charcount'] = len(_orig)
                elif key in link_keys:
                    _orig = _data[key]
                    if _orig:
                        # plain_link % (_orig, _orig)
                        _data[key] = Markup(_orig)
                elif key in date_keys:
                    _orig = _data[key]
                    if _orig:
                        _dt = datetime.datetime.fromtimestamp(_orig)
                        _data[key] = _dt.strftime('%Y-%m-%d-%H:%M:%S')
    return data


def redem_summary_context(data, **kwargs):
    context = {}
    context['username'] = data.get('_meta', {}).get('username')
    context['data'] = prepare_context_data(data)
    context.update(kwargs)
    context['title'] = context.get(
        'title',
        Markup("%s - redditlog") % context['username'])
    return context


def get_template_env():
    env = Environment(
        #loader=FileSystemLoader(os.path.dirname(__file__)),
        loader=PackageLoader('redem', 'templates'),
        autoescape=True,
        )
    return env


def redem_summary(data, **kwargs):
    context = redem_summary_context(data, **kwargs)
    env = get_template_env()
    template = env.get_template('redem_summary.jinja2')
    return template.render(context)


def write_html(filename, content):
    with codecs.open(filename, 'w+', encoding='utf-8') as fp:
        fp.write(content)


class Test_redem(unittest.TestCase):
    def test_redem_summary(self):
        DATADIR = os.path.join(os.path.dirname(__file__), '..', 'data')
        jsondata_filename = os.path.join(DATADIR, 'data.json')
        data = load(filename=jsondata_filename)
        self.assertTrue(data)
        output = redem_summary(data)
        assert '<title>' in output

    def test_iter_uris_regex(self):
        text = (
            u'https://en.wikipedia.org/wiki/Command-line_interface\n'
            '\nhttps://en.wikipedia.org/wiki/Command-line_argument_'
            'parsing#Python\n\nhttps://en.wikipedia.org/wiki/Python_'
            '(programming_language)\n\n\n[Automated testing]'
            '(http://www.reddit.com/r/Python/comments/1drv59/'
            'getting_started_with_automated_testing/c9tfxgd)'
            'is much easier when there is a `main` function.'
            '\n\nMinimally, in Unix style:\n\n    def main():\n'
            '\'\'\'Prints "Hello World!"\'\'\'\n        '
            'print("Hello world!")\n        return 0\n\n    '
            'if __name__ == \'__main__\':\n        import sys\n'
            'sys.exit(main())\n\n* http://docs.python.org/2.6/library/'
            'optparse.html\n* http://docs.python.org/2.7/library/'
            'argparse.html\n* http://docs.python.org/3/library/argparse'
            '.html\n\nFrom [the list of PyPi Trove Classifiers]'
            '(https://pypi.python.org/pypi?%3Aaction=list_classifiers):'
            '\n\n    Environment :: Console\n')
        uris = list(iter_uris_regex(text))
        self.assertTrue(len(uris))

    def test_iter_uris_bs4(self):
        text = (
            '<a href="http://example.org">example</a>'
            '<a href="example.org">example<>')
        uris = list(iter_uris_bs4(text))
        self.assertEqual(len(uris), 2)


def main(*args):
    import optparse
    import logging
    import sys

    prs = optparse.OptionParser(
        usage="%prog -u <username>  [--backup] [--merge] [--html]")

    prs.add_option(
        '-u', '--username',
        dest='username',
        action='store')
    prs.add_option(
        '-j', '--json',
        dest='json_filename',
        action='store',
        default='redditlog_data.json',
        )

    prs.add_option(
        '-b', '--backup',
        dest='backup',
        action='store_true')
    prs.add_option(
        '-n', '--limit',
        dest='limit',
        type='int',
        action='store',
        default=None)

    prs.add_option(
        '-m', '--merge',
        dest='merge_json',
        action='store_true')
    prs.add_option(
        '-r', '--html',
        dest='html_report',
        action='store_true')

    prs.add_option(
        '-o', '--html-output',
        dest='html_output_filename',
        action='store',
        default='redditlog.html',)
    prs.add_option(
        '--media-url',
        dest='media_url',
        default='static/',
        action='store',
        )

    prs.add_option(
        '-C', '--no-cache',
        dest='no_cache',
        default=False,
        action='store_true')

    prs.add_option(
        '-v', '--verbose',
        dest='verbose',
        action='store_true', )
    prs.add_option(
        '-q', '--quiet',
        dest='quiet',
        action='store_true', )
    prs.add_option(
        '-t', '--test',
        dest='run_tests',
        action='store_true', )

    args = args and list(args) or sys.argv[1:]
    (opts, args) = prs.parse_args(args)

    if not opts.quiet:
        logging.basicConfig()
        if opts.verbose:
            logging.getLogger().setLevel(logging.DEBUG)

    if opts.run_tests:
        sys.argv = [sys.argv[0]] + args
        import unittest
        sys.exit(unittest.main())

    username = None
    if opts.username:
        username = opts.username
    else:
        username = os.environ.get('REDDIT_USERNAME')
        if not opts.merge_json:
            if len(args):
                username = args[0]
    if username is None:
        print(
            "ERROR: Must specify a username with either"
            " -u/--username or by setting REDDIT_USERNAME",
            file=sys.stderr)

    if not any((opts.backup, opts.html_report, opts.merge_json)):
        prs.print_help()
        sys.exit(1)

    if opts.merge_json:
        filenames = args
        data = merge_json_files(filenames)
        dump(data, opts.json_filename)
        sys.exit(0)

    if not opts.no_cache:
        import requests_cache
        requests_cache.install_cache(
            os.path.join(DATADIR, 'cache'),
            backend='sqlite',
            expire_after=60 * 60,
            fast_save=True)

    data = None
    if opts.backup:
        data = redem(username, opts.backup, limit=opts.limit)
        dump(data, filename=opts.json_filename)

    if data is None and opts.json_filename:
        data = load(filename=opts.json_filename)

    if opts.html_report:
        output_html = redem_summary(
            data,
            media_url=opts.media_url,
            username=username)
        if opts.html_output_filename.strip() == '-':
            sys.stdout.write(opts.output_html)
        else:
            write_html(opts.html_output_filename, output_html)


if __name__ == "__main__":
    main()
