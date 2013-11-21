#!/usr/bin/env python
# encoding: utf-8
from __future__ import print_function
"""
redem - backup personal reddit history for easier local search

- JSON
- Single-File HTML

https://github.com/reddit/reddit/wiki/API
"""
__APPNAME__ = "redem"
__VERSION__ = "0.0.4"
__USER_AGENT__ = '%s (praw)\%s' % (__APPNAME__, __VERSION__)

import datetime
import logging
import os.path
import rfc3987
import praw
from jinja2 import Markup
import collections
from operator import attrgetter, itemgetter

uri_rgx = rfc3987.get_compiled_pattern('URI') # URI_reference
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
    url = _SUBMISSION_PERMALINKS.setdefault(submission.id, submission.permalink)
    return url


def comment_permalink(comment):
    return os.path.join(
            get_submission_permalink(comment.submission),
            comment.id)
    #return (
    #    u"http://reddit.com/r/{subreddit}/comments/{link_id}/{_link_title}/{id}".
    #    format(**comment))


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


def iter_comments(user, limit=None):
    done = False
    while not done:
        comments = user.get_comments(limit=limit)
        for comment in comments:
            yield comment
        done = True


def iter_submissions(user, limit=None):
    done = False
    while not done:
        submissions = user.get_submitted(limit=limit)
        for submission in submissions:
            yield submission
        done = True


def iter_liked(user, limit=None):
    done = False
    while not done:
        likeds = user.get_liked(limit=limit)
        for liked in likeds:
            yield liked
        done = True


def iter_uris(text, filterfunc=None):
    """
    Yield things that look like URIs from the given text

    :param filterfunc: callable to filter urls, defaults to .startswith('http')
    """
    if filterfunc is None:
        filterfunc = lambda uri: uri[4].lower() == 'http'

    for uri in uri_rgx.findall(text):
        if filterfunc(uri):
            yield uri
        else:
            log.debug('filtered_uri: %r' % uri)
            # TODO: URI CURIEs (dbpedia-owl:Thing)
            # assert ':' in uri
            # prefix, rest = uri.split(':',1)[0], rest
            # prefix = uri.schema
            # rest = (uri.host, uri.port, uri.path, uri.query,
            #        uri.fragment)
            # prefix_uri = ONTOLOGY_CONTEXT.get(prefix, None)
            # if prefix_uri:
            #    yield urljoin(prefix_uri, rest)
            #
            # TODO: PIP urls (git+git://, git+https://, hg+https://)


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

    selftext = submission.get("selftext")
    if selftext:
        for uri in iter_uris(selftext):
            yield uri

def canonicalize_uri(uri):
    _uri = None
    _uri_lower = uri[7].lower()
    if _uri_lower.startswith('https:'):
        _uri = uri[6:]
    elif _uri_lower.startswith('http:'):
        _uri = uri[5:]
    else:
        _uri = uri
    if _uri.startswith('//'):
        _uri = _uri[2:]
    if uri.startswith('//en.m.wikipedia.org'):
        _uri = uri.replace('en.m.wikipedia.org', 'en.wikipedia.org')
    # TODO: no path :: trailing slash wrd.nu wrd.nu/
    return _uri


URIThing = collections.namedtuple('URIThing',
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
        return (obj.uri, obj.source_obj) # source_obj_uri TODO

    def push(self, obj, return_count=False, return_reflist=False):
        """
        append a URI to the counter # TODO:
        :param uri: uri(uri, canonical_uri, source)
        """
        #reflist = self.reflist = getattr(self, 'reflist', self.get_default(self.keyfunc(obj), list)
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
        for key, refs in self.iteritems():
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


def redem(username, output_filename='data.json'):
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

    comments = iter_comments(user)
    #comments = list( iter_comments(user) )
    #print(len(comments))
    submissions = iter_submissions(user)
    #submissions = list( iter_submissions(user) )
    #print(len(submissions))
    #liked = iter_liked(user)
    #liked = list( iter_liked(user) )
    #print(len(liked))

    data = {
        '_meta': {
            'date_utc': str(datetime.datetime.utcnow()),
            'username': username,
        },
        'comments': [comment_to_dict(c) for c in comments],
        'submissions': [submission_to_dict(s) for s in submissions],
        #'liked': [liked_to_dict(l) for l in liked]
    }

    uri_iter = iter_all_uris(data)
    uris = sorted(uri_iter)
    # OrderedDefaultDict (OrderedCounter)



    uri_refs = URIRefCounter.group_and_count(uris)

    data['uris'] = sorted(
                        ((x[0], x[1]) for x in uri_refs.counts()),
                        key=itemgetter(0))


    return data

def expand_path(filename):
    return os.path.abspath(os.path.expanduser(filename))

import json
def dump(data, filename=None):
    output_filename = expand_path(filename)
    with codecs.open(output_filename, 'w+', encoding='utf-8') as fp:
        return json.dump(data, fp)


import codecs
def load(fileobj=None, filename=None):
    input_filename = expand_path(filename)
    if fileobj:
        return json.load(fileobj)
    elif filename:
        with codecs.open(input_filename, 'r', encoding='utf-8') as fp:
            return json.load(fp)





def site_frequencies(uri_iterable):
    import urlparse
    from collections import Counter
    from operator import attrgetter


    attrs = attrgetter('netloc','path','query') # TODO: fragment
    url_stemmer = lambda x: attrs(urlparse.urlparse(x))
    url_counts = Counter(url_stemmer(uri) for uri in uri_iterable).items()
    by_freq = sorted(url_counts, key= lambda x: x[1], reverse=True)
    by_site = sorted(url_counts, key= lambda x: x[0])

    return {'by_freq': by_freq,
            'by_site': by_site}


def prepare_context_data(data):
    # TODO: data = data.copy()
    # TODO: data['prov'] = ...
    html_keys = {'body_html':0, 'selftext_html':0}
    link_keys = {'permalink':0, 'link': 0}
    date_keys = {'created':0, 'created_utc':0, 'edited': 0}
    for subset in ('comments', 'submissions'):
        _objs = data[subset]
        for _data in _objs:
            for key in _data.keys():
                if key in html_keys: # XXX TODO FIXME
                    _orig = _data[key]
                    if _orig:
                        _data[key] = Markup(_orig)
                        _data['charcount'] = len(_orig)
                elif key in link_keys:
                    _orig = _data[key]
                    if _orig:
                        _data[key] = Markup(_orig) # plain_link % (_orig, _orig)
                elif key in date_keys:
                    _orig = _data[key]
                    if _orig:
                        _dt = datetime.datetime.fromtimestamp(_orig)
                        _data[key] = _dt.strftime('%Y-%m-%d-%H:%M:%S')
    return data


def redem_summary_context(data, **kwargs):
    context = {}
    context['username'] = data.get('_meta',{}).get('username')
    context['data'] = prepare_context_data(data)
    context['title'] = (
        Markup(u"%s @ reddit -- redem summary") % context['username']
    )
    context.update(kwargs) # TODO, FIXME, XXX
    return context


def get_template_env():
    from jinja2 import Environment, PackageLoader  # FileSystemLoader
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


import unittest
class Test_redem(unittest.TestCase):
    #def test_redem(self):
    #    uris = list( redem('westurner', limit=2000) )
    #    stats = site_frequencies(uris)
    #    from pprint import pprint
    #    print(pprint(stats))

    def test_redem_summary(self):
        data = load(filename='../data/data.json')
        self.assertTrue(data)

        output = redem_summary(data)
        assert '<title>' in output

    def test_iter_uris(self):
        text = u'https://en.wikipedia.org/wiki/Command-line_interface\n\nhttps://en.wikipedia.org/wiki/Command-line_argument_parsing#Python\n\nhttps://en.wikipedia.org/wiki/Python_(programming_language)\n\n\n[Automated testing](http://www.reddit.com/r/Python/comments/1drv59/getting_started_with_automated_testing/c9tfxgd) is much easier when there is a `main` function.\n\nMinimally, in Unix style:\n\n    def main():\n        \'\'\'Prints "Hello World!"\'\'\'\n        print("Hello world!")\n        return 0\n\n    if __name__ == \'__main__\':\n        import sys\n        sys.exit(main())\n\n* http://docs.python.org/2.6/library/optparse.html\n* http://docs.python.org/2.7/library/argparse.html\n* http://docs.python.org/3/library/argparse.html\n\nFrom [the list of PyPi Trove Classifiers](https://pypi.python.org/pypi?%3Aaction=list_classifiers):\n\n    Environment :: Console\n'
        uris = list( iter_uris(text) )
        self.assertTrue(len(uris))


def main():
    import optparse
    import logging
    import datetime

    prs = optparse.OptionParser(usage="./%prog <username>")

    prs.add_option('-b', '--backup',
                    dest='backup',
                    action='store_true')
    prs.add_option('-C', '--no-cache',
                    dest='no_cache',
                    default=False,
                    action='store_true')

    prs.add_option('-r','--html',
                    dest='html_report',
                    action='store_true')
    prs.add_option('-o','--html-output',
                    dest='html_output_filename',
                    action='store',
                   #default='-',
                    default=(
                        'report_%s.html' % (
                            datetime.datetime.now().strftime('%Y%M%D%h%m')
                        ))
                    )
    prs.add_option('--media-url',
                    dest='media_url',
                    default='static/',
                    action='store',
                    )


    prs.add_option('-j','--json',
                   dest='json_filename',
                   action='store',
                   default='data.json',
                   )

    prs.add_option('-v', '--verbose',
                    dest='verbose',
                    action='store_true',)
    prs.add_option('-q', '--quiet',
                    dest='quiet',
                    action='store_true',)
    prs.add_option('-t', '--test',
                    dest='run_tests',
                    action='store_true',)

    (opts, args) = prs.parse_args()

    if not opts.quiet:
        logging.basicConfig()

        if opts.verbose:
            logging.getLogger().setLevel(logging.DEBUG)

    if opts.run_tests:
        import sys
        sys.argv = [sys.argv[0]] + args
        import unittest
        sys.exit(unittest.main())

    username = None
    if (opts.backup):
        if not len(args):
            raise Exception("must specify a username")

    if len(args):
        username = args[0]

    if not opts.no_cache:
        import requests_cache
        requests_cache.install_cache(
                'data/redem',
                backend='sqlite',
                expire_after=60*60,
                fast_save=True)


    data = None
    if opts.backup:
        data = redem(username, opts.backup)
        dump(data, filename=opts.json_filename)

    if data is None:
        data = load(filename=opts.json_filename)

    if opts.html_report:
        output_html = redem_summary(data,
                media_url=opts.media_url,
                username=username)
        if opts.html_output_filename.strip() == '-':
            import sys
            sys.stdout.write(opts.output_html)
        else:
            write_html(opts.html_output_filename, output_html)



if __name__ == "__main__":
    main()

