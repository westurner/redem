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
__VERSION__ = "0.0.1"
import datetime
import logging
from operator import attrgetter
log = logging.getLogger('%s.cli' % __APPNAME__)

USER_AGENT = '%s (praw)\%s' % (__APPNAME__, __VERSION__)

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

import os.path
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

def iter_comment_uris(comments):
    import rfc3987
    uri_rgx = rfc3987.get_compiled_pattern('URI')

    for comment in comments:
        yield comment['permalink']
        uri_lists = (uri_rgx.findall(c.body) for c in comments)
        for uri_list in uri_lists:
            for uri in uri_list:
                if uri.lower().startswith('http'): # TODO
                    yield uri
                else:
                    log.debug('NOT a URI: %r' % uri)
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


def redem(username='westurner', limit=50, output_filename='data.json'):
    """
    get reddit data for username
    write it to output_filename as json

    return iterator of all URIs found
    """

    import praw

    r = praw.Reddit(user_agent=USER_AGENT)
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
        #'liked': [submission_to_dict(l) for l in liked]
    }

    return data


import json
def dump(data, output_filename=None):
    with codecs.open(output_filename, 'w+', encoding='utf-8') as fp:
        return json.dump(data, fp)

import codecs
def load(_file=None, filename=None):
    if _file:
        return json.load(_file)
    elif filename:
        with codecs.open(filename, 'r', encoding='utf-8') as fp:
            return json.load(fp)


def iter_uris(data):
    comments = data['comments']
    submissions = data['submissions']

    for uri in iter_comment_uris(comments):
        yield uri

    for sub in submissions:
        permalink = sub.get("permalink")
        if permalink:
            yield permalink
        url = sub.get('url')
        if url:
            yield url

    #_comments = (x for x in uri_rgx.findall(c.body) for c in comments)
    #print(list(_comments))

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


def redem_summary(data, **kwargs):
    from jinja2 import Markup
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

    context = {
            'data': data,
            'title': 'redem_summary',
            'username': (
                data.get('_meta',{})
                    .get('username', kwargs.get('username'))),
    }
    context.update(kwargs)

    from jinja2 import Environment, PackageLoader  # FileSystemLoader
    #import os.path
    env = Environment(
        #loader=FileSystemLoader(os.path.dirname(__file__)),
        loader=PackageLoader('redem', 'templates'),
        autoescape=True,
        ) # TODO FIXME XXX

    t = env.get_template('redem_summary.jinja2')
    return t.render(context)


import unittest
class Test_redem(unittest.TestCase):
    #def test_redem(self):
    #    uris = list( redem('westurner', limit=2000) )
    #    stats = site_frequencies(uris)
    #    from pprint import pprint
    #    print(pprint(stats))

    def test_redem_summary(self):
        data = load(filename='../data/data.json')

        print( redem_summary(data).encode('utf8',errors='xmlcharrefreplace') )


def main():
    import optparse
    import logging
    import datetime

    prs = optparse.OptionParser(usage="./%prog : args")

    prs.add_option('-b', '--backup',
                    dest='backup',
                    action='store_true')

    prs.add_option('--html',
                    dest='html_report',
                    action='store_true')
    prs.add_option('-o',
                    dest='html_output_filename',
                    action='store',
                    default=(
                        'report_%s.html' % (
                            datetime.datetime.now().strftime('%YMD%h%m')
                        ))
                    )
    prs.add_option('--media-url',
                    dest='media_url',
                    default='static/',
                    action='store',
                    )


    prs.add_option("--json",
                   dest="json_filename",
                   action="store",
                   default="data.json",
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
    if (opts.backup): # or opts.html_report):
        if not len(args):
            raise Exception("must specify a username")

    if len(args):
        username = args[0]

    data = None
    if opts.backup:
        data = redem(username, opts.backup)
        dump(data, output_filename=opts.json_filename)

    if data is None:
        data = load(filename=opts.json_filename)

    if opts.html_report:
        #uris = redem(username, output_filename=opts.html_output_filename)
        output_html = redem_summary(data,
                media_url=opts.media_url,
                username=username)
        with codecs.open(opts.html_output_filename, 'w+', encoding='utf-8') as fp:
            fp.write(output_html)


if __name__ == "__main__":
    main()

