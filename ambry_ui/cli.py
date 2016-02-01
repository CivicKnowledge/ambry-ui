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

    sp = cmd.add_parser('info', help='Print information about the UI')
    sp.set_defaults(subcommand=ui_info)

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
    usp.add_argument('-p', '--password', help="Reset the password")
    usp.add_argument('-s', '--secret', action='store_true', default=False, help="Regenerate the API secret")
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

    sp = cmd.add_parser('init', help='Initialize some library database values for the ui')
    sp.set_defaults(subcommand=db_init)
    sp.add_argument('-t', '--title', help="Set the library title")
    sp.add_argument('-v', '--virt-host', help="Set the virtual host name")

    sp = cmd.add_parser('run_args', help='Print evalable environmental vars for running the UI')
    sp.set_defaults(subcommand=run_args)

    sp = cmd.add_parser('notebook', help='Run jupyter notebook')
    sp.set_defaults(subcommand=start_notebook)
    sp.add_argument('-H', '--host', help="Server host.", default='localhost')
    sp.add_argument('-p', '--port', help="Server port.", default=None)
    sp.add_argument('-w', '--no-browser', action='store_true', default = False, help="Don't open the webbrowser")

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
            account.encrypt_password(random_string(20))


        l.commit()

        app.config['LOGGED_IN_USER'] = 'admin'

        prt('API Password: {}'.format(secret))

    db_init(args,l,rc)

    try:

        app.config['SECRET_KEY'] = 'secret'  # To Ensure logins persist
        app.config["WTF_CSRF_SECRET_KEY"] = 'secret'
        app.run(host=args.host, port=int(args.port), debug=args.debug)
    except socket.error as e:
        warn("Failed to start ui: {}".format(e))


def run_args(args, l, rc):

    ui_config = l.ui_config

    db_init(args, l, rc)

    prt('export AMBRY_UI_SECRET={} AMBRY_UI_CSRF_SECRET={} AMBRY_UI_TITLE="{}" '
        .format(ui_config['secret'], ui_config['csrf_secret'], ui_config['website_title'] ))


def db_init(args, l, rc):

    from uuid import uuid4
    import os

    ui_config = l.ui_config

    if not 'secret' in ui_config:
        ui_config['secret'] = str(uuid4())

    if not 'csrf_secret' in ui_config:
        ui_config['csrf_secret'] = str(uuid4())

    if hasattr(args, 'title') and args.title:
        ui_config['website_title'] = args.title
    elif not 'website_title' in ui_config:
        ui_config['website_title'] = os.getenv('AMBRY_UI_TITLE', 'Ambry Data Library')

    if hasattr(args, 'virt_host') and args.virt_host:
        ui_config['virtual_host'] = args.virt_host
    elif not ui_config['virtual_host']:
        ui_config['virtual_host'] = None

    l.database.commit()

def ui_info(args, l, rc):
    from tabulate import tabulate
    from __meta__ import __version__

    records = []
    records.append(['version', __version__])
    records.append(['title', l.ui_config['website_title']])
    records.append(['vhost', l.ui_config['virtual_host']])

    prt(tabulate(records))


def add_user(args, l, rc):
    """Add or update a user"""
    from ambry.util import random_string

    from getpass import getpass

    account = l.find_or_new_account(args.user_name)

    account.major_type = 'user'

    account.access_key = args.user_name

    if args.admin:
        account.minor_type = 'admin'

    if not account.encrypted_secret or args.secret:
        account.secret = random_string(20)
        prt("Secret: {}".format(account.secret))

    if args.password:
        password = args.password
    elif not account.encrypted_password:
        password = getpass().strip()
    else:
        password = None

    if password:
        account.encrypt_password(password)
        assert account.test(password)

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

    headers = 'Id User Type Secret'.split()

    records = []

    for k in l.accounts.keys():

        acct = l.account(k)

        if acct.major_type == 'user':
            try:
                secret = acct.secret
            except Exception as e:
                secret = str(e) # "<corrupt secret>"
            records.append([acct.account_id, acct.user_id, acct.minor_type, secret])

    if not records:
        return

    records = drop_empty([headers] + records)

    prt(tabulate(records[1:], records[0]))


def start_notebook(args, l, rc):

    from notebook.notebookapp import NotebookApp
    import sys

    sys.argv = ['ambry']
    app = NotebookApp.instance()
    app._library = l
    app.contents_manager_class = 'ambry_ui.jupyter.AmbryContentsManager'
    app.open_browser = not args.no_browser
    app.ip = args.host
    if args.port is not None:
        app.port = int(args.port)
    app.initialize(None)

    app.start()
