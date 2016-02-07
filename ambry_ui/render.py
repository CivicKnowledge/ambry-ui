"""Support for creating web pages and text representations of schemas."""

from csv import reader
import os

from . import app

from pygments import highlight
from pygments.lexers.sql import SqlLexer
from pygments.formatters import HtmlFormatter

from six import StringIO, string_types
import sqlparse

import jinja2.tests
from jinja2 import Environment, PackageLoader

from flask.json import JSONEncoder as FlaskJSONEncoder
from flask.json import dumps
from flask import Response, make_response, url_for, session


from ambry.identity import ObjectNumber, NotObjectNumberError, Identity
from ambry.bundle import Bundle
from ambry.orm.partition import Partition
from ambry.orm import Table
from ambry.orm.exc import NotFoundError
from ambry.util import get_logger
from ambry.util import pretty_time

import templates as tdir

from ambry.util import get_logger

logger = get_logger(__name__)



def resolve(ref):
    if isinstance(ref, string_types):
        return ref
    elif isinstance(ref, (Identity, Table)):
        return ref.vid
    elif isinstance(ref, Bundle):
        return ref.identity.vid
    elif isinstance(ref, Partition):
        return ref.identity.vid
    elif isinstance(ref, dict):
        if 'identity' in ref:
            return ref['identity'].get('vid', None)
        else:
            return ref.get('vid', None)
    else:
        raise Exception("Failed to resolve reference: '{}' ".format(ref))
        return None





def db_download_url(base, s):
    return os.path.join(base, 'download', s + '.db')


def extractor_list(t):
    return ['csv', 'json'] + (['kml', 'geojson'] if t.get('is_geo', False) else [])


class extract_entry(object):
    def __init__(self, extracted, completed, rel_path, abs_path, data=None):
        self.extracted = extracted
        # For deleting files where exception thrown during generation
        self.completed = completed
        self.rel_path = rel_path
        self.abs_path = abs_path
        self.data = data

    def __str__(self):
        return 'extracted={} completed={} rel={} abs={} data={}'.format(
            self.extracted,
            self.completed,
            self.rel_path,
            self.abs_path,
            self.data)


class JSONEncoder(FlaskJSONEncoder):
    def default(self, o):
        return str(type(o))


def format_sql(sql):
    return highlight(
        sqlparse.format(sql, reindent=True, keyword_case='upper'),
        SqlLexer(),
        HtmlFormatter())

def iter_as_dict(itr):
    """Given an iterable, return a comprehension with the dict version of each element"""
    from operator import attrgetter

    ag = attrgetter('dict')

    return [ ag(e) for e in itr if hasattr(e, 'dict') ]


@property
def pygmentize_css(self):
    return HtmlFormatter(style='manni').get_style_defs('.highlight')


class Renderer(object):

    def __init__(self, library, env = None, content_type='html', session=None,
                blueprints=None):

        self.library = library

        self.css_files = ['css/style.css', 'css/pygments.css']

        self.env = env if env else Environment(loader=PackageLoader('ambry_ui', 'templates'))

        # Set to true to get Render to return json instead
        self.content_type = content_type

        self.blueprints = blueprints

        self.session = session if session else {}


    def cts(self, ct, session=None):
        """Return a clone with the content type set, and maybe the session"""

        return Renderer(self.library, env=self.env, content_type = ct, session = session)

    def cc(self):
        """Return common context values. These are primarily helper functions
        that can be used from the context. """
        from functools import wraps
        from ambry._meta import __version__ as ambry_version
        from __meta__ import  __version__ as ui_version
        from .forms import LoginForm
        from flask import request

        # Add a prefix to the URLs when the HTML is generated for the local
        # filesystem.
        def prefix_root(r, f):
            @wraps(f)
            def wrapper(*args, **kwds):
                return os.path.join(r, f(*args, **kwds))

            return wrapper

        return {
            'ambry_version': ambry_version,
            'ui_version': ui_version,
            'url_for': url_for,
            'from_root': lambda x: x,
            'getattr': getattr,
            'title': app.config.get('website_title'),
            'next_page': request.path, # Actually last page, for login redirect
            'session': session,
            'autologin_user': app.config['LOGGED_IN_USER']

        }


    def render(self, template, *args, **kwargs):
        from flask import render_template

        context = self.cc()
        context.update(kwargs)

        context['l'] = self.library

        if self.content_type == 'json':
            return Response(dumps(kwargs, cls=JSONEncoder, indent=4),mimetype='application/json')

        else:
            return render_template(template, *args, **context)

    def json(self, **kwargs):
        return Response(dumps(kwargs, cls=JSONEncoder), mimetype='application/json')


    @property
    def css_dir(self):
        return os.path.join(os.path.abspath(os.path.dirname(tdir.__file__)), 'css')

    def css_path(self, name):
        return os.path.join(os.path.abspath(os.path.dirname(tdir.__file__)), 'css', name)

    @property
    def js_dir(self):
        return os.path.join(os.path.abspath(os.path.dirname(tdir.__file__)), 'js')


