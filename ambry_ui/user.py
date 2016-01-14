""" User views

Copyright (c) 2015 Civic Knowledge. This file is licensed under the terms of
the Revised BSD License, included in this distribution as LICENSE.txt
"""

from . import app, get_aac
from werkzeug.local import LocalProxy
from flask import session,  request, flash, redirect, abort, url_for
from flask_login import login_user, logout_user

aac = LocalProxy(get_aac)

import logging

logger = app.logger

logger = logging.getLogger('gunicorn.access')
logger.setLevel(logging.DEBUG)


@app.login_manager.user_loader
def load_user(user_id):
    from ambry.orm.exc import NotFoundError

    try:
        account = aac.library.account(user_id)
    except NotFoundError:
        logger.info("User '{}' not found  ".format(user_id))
        return None

    if account.major_type != 'user':
        logger.info("User '{}' not api service type; got '{}'  ".format(user_id, account.major_type))
        return None

    return User(account)

# This can be implemented to allow logins from URL values, or an Auth header, such as by transfers from
# another application
@app.login_manager.request_loader
def load_user_from_request(request):

    # first, try to login using the api_key url arg
    api_key = request.args.get('api_key')
    if api_key:
        pass

    # next, try to login using Basic Auth
    api_key = request.headers.get('Authorization')
    if api_key:
        pass

    # finally, return None if both methods did not login the user
    return None

class User(object):

    def __init__(self, account_rec):

        self._account_rec = account_rec
        self.name = self._account_rec.account_id

    def validate(self, password):
        self._is_authenticated = self._account_rec.test(password)

    def force_validate(self):
        self._is_authenticated = True

    def is_authenticated(self):
        return self._is_authenticated

    def is_active(self):
        return True

    def is_anonymous(self):
        return False

    def get_id(self):
        return self._account_rec.account_id

@app.csrf.error_handler
def csrf_error(reason):
    logger.info("Got a CSRF error: {}".format(reason))
    return redirect('/')


@app.route('/login', methods=['GET', 'POST'])
def login():

    from .forms import LoginForm


    cxt = {
        'next_page': request.args.get('next_page', '/')
    }

    form = LoginForm()

    app.csrf.protect()

    if request.form['login'] == 'Cancel':
        return redirect(request.args.get('next_page', '/'))

    session['request_count'] = session.get('request_count', 0) + 1

    username = request.form.get('username')
    password = request.form.get('password')

    logger.info("login for '{}'".format(username))

    error = None
    if form.validate_on_submit():

        next = request.args.get('next_page', '/')

        user = load_user(username)

        if not user:
            logger.info("No user '{}'".format(username))
            return abort(403)

        user.validate(password)

        login_user(user)

        if not next[0] == '/':
            return abort(400)

        return redirect(next)
    else:
        logger.info("Login form failed to validate: {}".format(form.errors))
        logger.info(request.form)
        error = 'Invalid username or password'

    return aac.renderer.render('login.html', error=error, request_count= session['request_count'], **cxt)

@app.route('/autologin', methods=['GET'])
def autologin():

    if 'LOGGED_IN_USER' in app.config:
        user = load_user(app.config['LOGGED_IN_USER'])
        user.force_validate()
        login_user(user)

    return redirect('/')

@app.route('/logout', methods=['GET', 'POST'])
def logout():

    logout_user()

    return redirect('/')






