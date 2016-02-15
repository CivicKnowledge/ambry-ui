"""Documentation, file and login server for Ambry warehouses.

Copyright 2014, Civic Knowledge. All Rights Reserved

"""

import os
import templates as tdir
from ambry.util import get_logger
from flask import Flask, g
from flask import Response, url_for, session
from flask.json import JSONEncoder as FlaskJSONEncoder
from flask.json import dumps
from flask_login import LoginManager
from flask_wtf.csrf import CsrfProtect
from jinja2 import Environment, PackageLoader
from session import ItsdangerousSessionInterface

logger = get_logger(__name__)

# Command declarations for `ambry config installcli`
commands = ['ambry_ui.cli']

# Default configuration
app_config = {
    'host': os.getenv('AMBRY_UI_HOST', 'localhost'),
    'port': os.getenv('AMBRY_UI_PORT', 8081),
    'use_proxy': bool(os.getenv('AMBRY_UI_USE_PROXY', False)),
    'DEBUG': bool(os.getenv('AMBRY_UI_DEBUG', False)),

    'MAX_CONTENT_LENGTH': 1024 * 1024 * 512,
    'SESSION_TYPE': 'filesystem',
    'WTF_CSRF_CHECK_DEFAULT': False,  # Turn off CSRF by default. Must enable on specific views.

    'SECRET_KEY': os.getenv('AMBRY_UI_SECRET'),
    'WTF_CSRF_SECRET_KEY': os.getenv('AMBRY_UI_CSRF_SECRET', os.getenv('AMBRY_UI_SECRET')),
    'website_title': os.getenv('AMBRY_UI_TITLE', "Ambry Data Library"),

    'LOGGED_IN_USER': None,  # Name of user to auto-login
}


class JSONEncoder(FlaskJSONEncoder):
    def default(self, o):
        return str(type(o))


class Renderer(object):
    def __init__(self, library, env=None, content_type='html', session=None,
                 blueprints=None):

        self.library = library

        self.env = env if env else Environment(loader=PackageLoader('ambry_ui', 'templates'))

        # Set to true to get Render to return json instead
        self.content_type = content_type

        self.blueprints = blueprints

        self.session = session if session else {}

    def cc(self):
        """Return common context values. These are primarily helper functions
        that can be used from the context. """
        from ambry._meta import __version__ as ambry_version
        from __meta__ import __version__ as ui_version
        from flask import request

        return {
            'ambry_version': ambry_version,
            'ui_version': ui_version,
            'url_for': url_for,
            'from_root': lambda x: x,
            'getattr': getattr,
            'title': app.config.get('website_title'),
            'next_page': request.path,  # Actually last page, for login redirect
            'session': session,
            'autologin_user': app.config['LOGGED_IN_USER']

        }

    def render(self, template, *args, **kwargs):
        from flask import render_template

        context = self.cc()
        context.update(kwargs)

        context['l'] = self.library

        if self.content_type == 'json':
            return Response(dumps(kwargs, cls=JSONEncoder, indent=4), mimetype='application/json')

        else:
            return render_template(template, *args, **context)

    def json(self, **kwargs):
        return Response(dumps(kwargs, cls=JSONEncoder), mimetype='application/json')


class AmbryAppContext(object):
    """Ambry specific objects for the application context"""

    def __init__(self):
        from ambry.library import Library
        from ambry.run import get_runconfig

        rc = get_runconfig()
        self.library = Library(rc, read_only=True, echo=False)
        self.renderer = Renderer(self.library)

    def render(self, template, *args, **kwargs):
        return self.renderer.render(template, *args, **kwargs)

    @property
    def cc(self):
        return self.renderer.cc()

    def bundle(self, ref):
        from flask import abort
        from ambry.orm.exc import NotFoundError

        try:
            return self.library.bundle(ref)
        except NotFoundError:
            abort(404)

    def json(self, *args, **kwargs):
        return self.renderer.json(*args, **kwargs)

    def close(self):
        self.library.close()


def get_aac():  # Ambry Application Context
    """Opens a new database connection if there is none yet for the
    current application context.
    """
    if not hasattr(g, 'aac'):
        g.aac = AmbryAppContext()

    return g.aac


class Application(Flask):
    def __init__(self, app_config, import_name, static_path=None, static_url_path=None, static_folder='static',
                 template_folder='templates', instance_path=None, instance_relative_config=False):

        self._app_config = app_config
        self._initialized = False
        self.csrf = CsrfProtect()
        self.login_manager = LoginManager()

        super(Application, self).__init__(import_name, static_path, static_url_path, static_folder, template_folder,
                                          instance_path, instance_relative_config)

    def __call__(self, environ, start_response):

        if not self._initialized:
            if not app_config['SECRET_KEY']:
                app.logger.error("SECRET_KEY was not set. Setting to an insecure value")
                app_config['SECRET_KEY'] = 'secret'  # Must be the same for all worker processes.

            if not app_config['WTF_CSRF_SECRET_KEY']:
                app_config['WTF_CSRF_SECRET_KEY'] = app_config['SECRET_KEY']

            self.config.update(self._app_config)
            self.secret_key = app.config['SECRET_KEY']

            self.csrf.init_app(self)

            self.session_interface = ItsdangerousSessionInterface()

            self.login_manager.init_app(app)

            self._initialized = True

        return super(Application, self).__call__(environ, start_response)


app = Application(app_config, __name__)


@app.teardown_appcontext
def close_connection(exception):
    aac = getattr(g, 'aac', None)
    if aac is not None:
        aac.close()


# Flask Magic. The views have to be imported for Flask to use them.
import ambry_ui.views
import ambry_ui.jsonviews
import ambry_ui.api
import ambry_ui.user
