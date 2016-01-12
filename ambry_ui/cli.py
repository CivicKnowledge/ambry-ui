"""Ambry Library User Administration CLI

Copyright (c) 2015 Civic Knowledge. This file is licensed under the terms of
the Revised BSD License, included in this distribution as LICENSE.txt

"""

__all__ = ['command_name', 'make_parser', 'run_command']
command_name = 'ui'

from ambry.cli import prt, fatal, warn, err

def make_parser(cmd):

    config_p = cmd.add_parser(command_name, help='Manage the user interface')
    config_p.set_defaults(command=command_name)

    cmd = config_p.add_subparsers(title='UI commands', help='UI commands')

    sp = cmd.add_parser('start', help='Run the web user interface')
    sp.set_defaults(command=command_name)
    sp.set_defaults(subcommand=start_ui)
    sp.add_argument('-H', '--host', help="Server host.", default='localhost')
    sp.add_argument('-p', '--port', help="Server port", default=8080)
    sp.add_argument('-P', '--use-proxy', action='store_true',
                    help="Setup for using a proxy in front of server, using werkzeug.contrib.fixers.ProxyFix")
    sp.add_argument('-d', '--debug', action='store_true', help="Set debugging mode", default=False)
    sp.add_argument('-N', '--no-accounts', action='store_true', help="Don't setup remotes and accounts", default=False)

    sp = cmd.add_parser('user', help='Manage users')
    sp.set_defaults(command=command_name)

    ucmd = sp.add_subparsers(title='User Commands', help='Sub-commands for managing users')

    usp = ucmd.add_parser('add', help='Add a user')
    usp.set_defaults(subcommand=add_user)
    usp.add_argument('-a', '--admin', action='store_true', default = False, help="Make the user an administrator")
    usp.add_argument('user_name', help='Name of user')

    usp = ucmd.add_parser('admin', help='Add or remove admin privledges')
    usp.set_defaults(subcommand=user_admin)
    usp.add_argument('-r', '--remove', action='store_true', default = False, help="Remove, rather than add, the privledge")
    usp.add_argument('user_name', help='Name of user')

    usp = ucmd.add_parser('remove', help='Remove a user')
    usp.set_defaults(subcommand=remove_user)
    usp.add_argument('user_name', help='Name of user')

    usp = ucmd.add_parser('list', help='List users')
    usp.set_defaults(subcommand=list_users)

def run_command(args, rc):
    from ambry.library import new_library
    from ambry.cli import global_logger

    try:
        l = new_library(rc)
        l.logger = global_logger
    except Exception as e:
        l = None

    args.subcommand(args, l, rc) # Note the calls to sp.set_defaults(subcommand=...)

def no_command(args, l, rc):
    raise NotImplementedError()

def start_ui(args, l, rc):

    from ambry_ui import app
    import ambry_ui.views
    import ambry_ui.jsonviews
    import ambry_ui.api
    import ambry_ui.user
    import webbrowser
    import socket
    from ambry.orm.exc import NotFoundError
    import os
    from uuid import uuid4
    from ambry.util import random_string, set_url_part

    if args.use_proxy:
        from werkzeug.contrib.fixers import ProxyFix
        app.wsgi_app = ProxyFix(app.wsgi_app)

    if not args.debug:
        webbrowser.open("http://{}:{}".format(args.host, args.port))
    else:
        import logging
        logging.basicConfig(level=logging.DEBUG)
        log = logging.getLogger('werkzeug')
        log.setLevel(logging.DEBUG)
        #prt("Running at http://{}:{}".format(args.host, args.port))

    # Setup remotes and accounts.

    if not args.no_accounts:
        remote = l.find_or_new_remote('localhost', service='ambry')
        remote.url = "http://{}:{}".format(args.host, args.port)

        if not remote.jwt_secret:
            from ambry.util import random_string
            remote.jwt_secret = random_string(16)

        # Create a local user account entry for accessing the API. This one is for the client,
        # which knows the destination URL, so the account id has the form: http://api@localhost:8080/
        username = 'api'
        account_url = set_url_part(remote.url, username=username)
        account = l.find_or_new_account(account_url, major_type='api')
        if not account.access_key:
            account.url = remote.url
            account.access_key = 'api'
            secret = random_string(20)
            account.encrypt_secret(secret)
        else:
            secret = account.decrypt_secret()

        # This one is for the server side, where it doesn't know the destination URL, and the
        # account id is just the username.
        account = l.find_or_new_account(username, major_type='api')
        account.url = remote.url
        account.access_key = 'api'
        account.encrypt_secret(secret)

        # This account is the admin user, which get auto logged in
        # We just need to ensure it exists.
        account = l.find_or_new_account('admin', major_type='user', minor_type='admin')
        if not account.encrypted_secret:
            account.encrypt_secret(random_string(20))


        l.commit()

        app.config['LOGGED_IN_USER'] = 'admin'

        prt('JWT Secret  : {}'.format(app.config['JWT_SECRET']))
        prt('API Password: {}'.format(secret))

        prt('Add Secret to a foreign library: ')
        prt('    ambry remotes add -j {} -u {} {}'.format(remote.jwt_secret,remote.url, remote.short_name))
        prt('    ambry accounts add -v api -s {} {}'.format(secret, account_url))

    try:

        app.config['SECRET_KEY'] = 'secret'  # To Ensure logins persist
        app.config["WTF_CSRF_SECRET_KEY"] = 'secret'
        app.run(host=args.host, port=int(args.port), debug=args.debug)
    except socket.error as e:
        warn("Failed to start ui: {}".format(e))


def add_user(args, l, rc):
    """Add or update a user"""

    from getpass import getpass

    account = l.find_or_new_account(args.user_name)

    account.major_type = 'user'

    account.access_key = args.user_name

    if args.admin:
        account.minor_type = 'admin'

    account.encrypt_secret(getpass().strip())

    account.url = None

    l.commit()

def user_admin(args, l, rc):
    """Add or update a user"""

    from ambry.orm.exc import NotFoundError

    try:
        account = l.account(args.user_name)

        if account.major_type != 'user':
            raise NotFoundError()

        if args.remove:
            account.minor_type = None
        else:
            account.minor_type = 'admin'

        l.commit()

    except NotFoundError:
        warn("No account found for {}".format(args.user_name))

def remove_user(args, l, rc):

    from ambry.orm.exc import NotFoundError

    try:
        account = l.account(args.user_name)

        if account.major_type != 'user':
            raise NotFoundError()

        l.delete_account(account)
        l.commit()

    except NotFoundError:
        warn("No account found for {}".format(args.user_name))


def list_users(args, l, rc):
    from ambry.util import drop_empty
    from tabulate import tabulate

    headers = 'Id User Type'.split()

    records = []

    for k in l.accounts.keys():

        acct = l.account(k)

        if acct.major_type == 'user':
            records.append([acct.account_id, acct.user_id, acct.minor_type])

    if not records:
        return

    records = drop_empty([headers] + records)

    prt(tabulate(records[1:], records[0]))