""" User views

Copyright (c) 2015 Civic Knowledge. This file is licensed under the terms of
the Revised BSD License, included in this distribution as LICENSE.txt
"""

from . import app, get_aac
from werkzeug.local import LocalProxy
from flask import session,  request, flash, redirect, abort, url_for
from flask_login import login_user, logout_user, login_required, current_user

aac = LocalProxy(get_aac)

import logging

logger = app.logger

#logger = logging.getLogger('gunicorn.access')
#logger.setLevel(logging.DEBUG)


@app.login_manager.user_loader
def load_user(user_id):
    from ambry.orm.exc import NotFoundError

    if user_id == 'admin' and 'AMBRY_ADMIN_PASS' in app.config:
        from ambry.orm import Account

        account = Account(account_id=user_id, major_type='user', minor_type='admin')
        account.encrypt_password(app.config['AMBRY_ADMIN_PASS'])
        logger.info("Got configured password; using fake admin account".format(user_id))

    else:
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
        return self._is_authenticated

    def force_validate(self):
        self._is_authenticated = True

    @property
    def is_admin(self):

        return self._account_rec.minor_type == 'admin'

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


    error = None
    if form.validate_on_submit():

        next = request.args.get('next_page', '/')

        user = load_user(username)

        if not user:
            logger.info("No user '{}'".format(username))
            return abort(403)

        if user.validate(password):

            login_user(user)

            if not next[0] == '/':
                logger.info("Login failed; bad next url parameter'{}'".format(next[0]))
                return abort(400)

            logger.info("Successful login  for '{}'".format(username))
            return redirect(next)

    logger.info("Login form failed to validate: {}".format(form.errors))
    logger.info(request.form)
    error = 'Invalid username or password'

    return aac.render('login.html', error=error, request_count= session['request_count'], **cxt)

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


@app.route('/admin')
@login_required
def admin_index():
    cxt = dict(

        **aac.cc
    )

    return aac.render('admin/index.html', **cxt)

@app.route('/admin/accounts', methods=['GET', 'POST'])
@login_required
def admin_accounts():

    import yaml
    from ambry.library.config import LibraryConfigSyncProxy

    if not current_user.is_admin:
        abort(403)

    if request.method == "POST":
        if request.form['config']:
            try:
                d = yaml.load(request.form['config'])

                if 'accounts' in d:
                    d = d['accounts']

                lcsp = LibraryConfigSyncProxy(aac.library)
                lcsp.sync_accounts(d)

                flash('Loaded {} accounts'.format(len(d)), 'success')

            except Exception as e:
                flash(str(e), 'error')

        if request.form.get('delete'):
            aac.library.delete_account(request.form['delete'])

    cxt = dict(
        accounts=[ a for a in aac.library.accounts.values() if a['major_type'] != 'user'],
        **aac.cc
    )

    return aac.render('admin/accounts.html',  **cxt)

@app.route('/admin/remotes', methods=['GET', 'POST'])
@login_required
def admin_remotes():
    import yaml

    from ambry.library.config import LibraryConfigSyncProxy

    if not current_user.is_admin:
        abort(403)

    if request.method == "POST":

        if request.form['config']:
            try:

                d = yaml.load(request.form['config'])

                if 'remotes' in d:
                    d = d['remotes']

                lcsp = LibraryConfigSyncProxy(aac.library)
                lcsp.sync_remotes(d)

                flash('Loaded {} remotes'.format(len(d)), 'success')

            except Exception as e:
                flash(str(e), 'error')

        if request.form.get('delete'):
            aac.library.delete_remote(request.form['delete'])

        if request.form.get('update'):
            from ambry.orm.remote import RemoteAccessError
            if request.form['update'] == 'all':
                for r in aac.library.remotes:
                    try:
                        r.update()
                        aac.library.commit()
                    except RemoteAccessError as e:
                        flash("Update Error: {}".format(e), 'error')

            else:
                r = aac.library.remote(request.form['update'])
                try:
                    r.update()
                    aac.library.commit()
                except RemoteAccessError as e:
                    flash("Update Error: {}".format(e), 'error')

        if request.form.get('install'):
            aac.library.checkin_remote_bundle(request.form['install'])
            b = aac.library.bundle(request.form['install'])
            flash("Installed bundle {}".format(b.identity.vname), 'success')



    cxt = dict(
        remotes=[r for r in aac.library.remotes],
        **aac.cc
    )

    return aac.render('admin/remotes.html', **cxt)

@app.route('/admin/users', methods=['GET', 'POST'])
@login_required
def admin_users():

    from forms import NewUserForm

    if not current_user.is_admin:
        abort(403)

    new_user_form = NewUserForm()

    if new_user_form.validate_on_submit():
        account = aac.library.find_or_new_account(new_user_form.username.data)
        account.major_type = 'user'
        account.minor_type = new_user_form.account_type.data
        account.encrypt_password(new_user_form.password.data)
        aac.library.commit()
        flash("Created new user: {}".format(new_user_form.username.data), "success")

    if request.method == 'POST' and request.form.get('delete'):
        aac.library.delete_account(request.form['delete'])
        aac.library.commit()

    else:
        for k,v in new_user_form.errors.items():
            flash("{}: {}".format(k, v), "error")

    cxt = dict(
        users=[a for a in aac.library.accounts.values() if a['major_type'] == 'user'],
        new_user_form=NewUserForm(),
        **aac.cc
    )

    return aac.render('admin/users.html', **cxt)

@app.route('/admin/bundles', methods=['GET', 'POST'])
@login_required
def admin_bundles():

    if not current_user.is_admin:
        abort(403)

    print '!!!!', request.form
    if request.method == 'POST' and request.form.get('delete'):
        aac.library.remove(request.form['delete'])
        aac.library.commit()

    cxt = dict(
        bundles=[b for b in aac.library.bundles],
        **aac.cc
    )

    return aac.render('admin/bundles.html', **cxt)




