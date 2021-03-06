"""
API Views, return javascript rendietions of objects and allowing modification of the database
"""

import os
import logging

from . import app, get_aac

from flask import Flask, g, current_app, send_from_directory, send_file, request, abort, url_for
from flask.json import jsonify
from werkzeug.security import safe_str_cmp

from werkzeug.local import LocalProxy

aac = LocalProxy(get_aac)

app.logger.setLevel(logging.INFO)

def jwt_auth():
    """Extract the Authorization header and validate it against the database"""
    from jose import jwt
    from jose.exceptions import JWSError

    from flask import request
    from ambry.orm.exc import NotFoundError

    auth_header = request.headers.get('Authorization')

    if not auth_header:
        app.logger.info("AuthError: No auth header value")
        abort(401)

    form, auth_str = auth_header.split(' ',1)

    if form != 'JWT':
        app.logger.info("AuthError: Didn't get JWT for auth type")
        abort(401)

    user, token = auth_str.split(':')

    try:
        account = aac.library.account(user)
    except NotFoundError:
        app.logger.info("AuthError: Didn't get user '{}' ".format(user))
        abort(401)

    if account.major_type not in ('user','api'):
        app.logger.info("User '{}' not api service type; got '{}'  ".format(user, account.major_type))
        abort(400)

    assert account.secret

    try:
        claims = jwt.decode(token, account.secret, algorithms='HS256')
    except jwt.JWTError:
        app.logger.info("AuthError: failed to verify token ")
        abort(401)
    except JWSError:
        app.logger.info("AuthError: failed to verify token signature ")
        abort(401)

    if not 'u' in claims:
        app.logger.info("AuthError: no user in claims ")
        abort(400)

    if user != claims['u']:
        app.logger.info("Claimed user does not match")
        abort(401)


    return 0

def jwt_required(fn):
    """View decorator that requires a valid JWT token to be present in the request

    """
    from functools import wraps
    @wraps(fn)
    def decorator(*args, **kwargs):
        r = jwt_auth()
        if r != 0:
            abort(r)
        return fn(*args, **kwargs)
    return decorator


@app.route('/auth-test', methods = ['GET', 'POST', 'PUT'])
@jwt_required
def test_get():

    content = request.get_json(silent=True)

    return aac.json(**content)

#
# Administration Interfaces
#

@app.route('/resolve/<ref>', methods = ['GET'])
def resolve_get(ref):
    """Return remotes configured on the Library"""
    from ambry.orm.exc import NotFoundError


    d = None

    try:
        p = aac.library.partition(ref)
        d = p.dict
        d['_type'] = 'partition'
        d['description'] = p.description
        d['geo_description'] = p.geo_description

        b = p._bundle.dataset.dict
        b['title'] = p._bundle.metadata.about.title
        b['summary'] = p._bundle.metadata.about.summary
        return aac.json(partition=d, bundle=b)

    except NotFoundError:
        pass

    try:
        b = aac.library.bundle(ref)
        d = b.dataset.dict
        d['_type'] = 'bundle'
        d['title'] = b.metadata.about.title
        d['summary'] = b.metadata.about.summary

        return aac.json(
            bundle=d
        )
    except:
        return abort(404)



@app.route('/config/remotes', methods = ['GET'])
@jwt_required
def config_remotes_get():
    """Return remotes configured on the Library"""
    

    return aac.json(
        remotes=[ rmt.dict for rmt in aac.library.remotes]
    )

@app.route('/config/remotes', methods = ['PUT'])
@jwt_required
def config_remotes_put():
    """Replace all of the remotes in the library with new ones"""
    
    l = aac.library

    for r_d in request.get_json():
        rmt = l.find_or_new_remote(r_d['short_name'])

        for k, v in r_d.items():
            if hasattr(rmt,k):
                setattr(rmt, k, v)

    l.commit()

    return aac.json(
        remotes=[ rmt.dict for rmt in aac.library.remotes]
    )


def proc_account(a):
    if 'encrypted_secret' in a:
        del a['encrypted_secret']
    if 'secret' in a:
        del a['secret']
    return a

@app.route('/config/accounts', methods = ['GET'])
@jwt_required
def config_accounts_get():

    return aac.json(
        accounts={ k:proc_account(a) for k, a in aac.library.accounts.items()}
    )


@app.route('/config/accounts', methods = ['PUT'])
@jwt_required
def config_accounts_put():
    from ambry.orm.account import AccountDecryptionError, MissingPasswordError

    from ambry.library.config import LibraryConfigSyncProxy

    l = aac.library

    lsp = LibraryConfigSyncProxy(aac.library)

    try:

        lsp.sync_accounts(request.get_json())
    except MissingPasswordError:
        print 'Missing Password'
        abort(400)
    except AccountDecryptionError:
        print "Decryption Failed"
        abort(400)


    return aac.json(
        accounts={k: proc_account(a) for k, a in aac.library.accounts.items()}
    )

@app.route('/config/services', methods = ['PUT'])
@jwt_required
def config_services_put():
    pass

@app.route('/config/services', methods = ['GET'])
@jwt_required
def config_services_get():
    pass

@app.route('/bundles/<ref>', methods = ['DELETE'])
@jwt_required
def bundle_delete(ref):
    """Returns the file records, excluding the content"""
    from ambry.orm.exc import NotFoundError

    try:
        aac.library.remove(aac.bundle(ref))
    except NotFoundError:
        abort(404)

    return aac.json(
        ok=True
    )

@app.route('/bundles/<vid>/build/files', methods = ['GET'])
@jwt_required
def bundle_build_files(vid):
    """Returns the file records, excluding the content"""



    b = aac.library.bundle(vid)

    def make_dict(f):
        d = f.record.dict
        del d['modified_datetime']
        return d

    return aac.json(
        files=[ make_dict(f) for f in b.build_source_files ]
    )

@app.route('/bundles/<vid>/build/files/<name>', methods = ['GET'])
@jwt_required
def bundle_build_file(vid, name):
    """Returns the file records, excluding the content"""

    b = aac.library.bundle(vid)

    try:
        fs = b.build_source_files.file(name)
    except KeyError:
        abort(404)

    def make_dict(f):
        d = f.record.dict
        del d['modified_datetime']
        return d

    return aac.json(file= make_dict(fs))


@app.route('/bundles/<vid>/build/files/<name>/content', methods = ['GET'])
@jwt_required
def bundle_build_files_get(vid, name):
    from flask import Response

    
    b = aac.library.bundle(vid)

    try:
        fs = b.build_source_files.file(name)
    except KeyError:
        abort(404)

    mt = 'text/csv' if 'csv' in fs.record.path else 'text/plain'

    return Response(fs.getcontent(), mimetype=mt)

@app.route('/bundles/<vid>/build/files/<name>/content', methods = ['PUT'])
@jwt_required
def bundle_build_files_put(vid, name):
    
    b = aac.library.bundle(vid)

    try:
        fs = b.build_source_files.file(name)
    except KeyError:
        abort(404)

    mt = 'text/csv' if 'csv' in fs.record.path else 'text/plain'

    fs.setcontent(request.content)

    return aac.json(
        file=fs.record.dict
    )

@app.route('/bundles/<vid>/checkin', methods = ['POST'])
@jwt_required
def bundle_build_checkin_post(vid):
    """Checkin a bundle to this library, as a sqlite file"""
    from ambry.util.flo import copy_file_or_flo
    import tempfile
    

    fh, path = tempfile.mkstemp()
    os.fdopen(fh).close()

    with open(path, 'wb') as f:
        copy_file_or_flo(request.stream, f)

    def cb(message, number):
        print message, number

    aac.library.checkin_bundle(path, cb)

    return aac.json(
        result='ok'
    )

@app.route('/bundles/<vid>/checkout', methods = ['GET'])
@jwt_required
def bundle_build_checkout_get(vid):
    """Checkout a bundle from this library, as a Sqlite file"""
    pass

@app.route('/bundles/sync/<ref>', methods = ['POST'])
@jwt_required
def bundle_build_sync_post(ref):
    """Command the library to install a bundle. Optionally send information about the remote to use.

    If a payload is included, it is an dict of an Account record, with the encrypted secret encrypted with the
    api token.

    """
    pass