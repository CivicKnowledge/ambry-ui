""" Public views

Copyright (c) 2015 Civic Knowledge. This file is licensed under the terms of
the Revised BSD License, included in this distribution as LICENSE.txt
"""

import os
from . import app, get_aac
from flask import g, current_app, send_from_directory, send_file, request, abort, url_for
from werkzeug.local import LocalProxy
import logging

aac = LocalProxy(get_aac)
#app.logger.setLevel(logging.DEBUG)

@app.errorhandler(500)
def page_not_found(e):
    return aac.render('500.html', e=e), 500


@app.route('/')
@app.route('/index')
def index():
    cxt = dict(
        bundles=[b for b in aac.library.bundles],
        **aac.cc
    )

    return aac.render('index.html', **cxt)


@app.route('/bundles/<vid>')
def bundle_main(vid):
    cxt = dict(
        vid=vid,
        b=aac.library.bundle(vid),
        sources_header=['name', 'source_table_name', 'ref'],
        **aac.cc
    )

    return aac.render('bundle/about.html', **cxt)


@app.route('/bundles/<vid>/meta')
def bundle_meta(vid):
    def flatten_dict(d):
        def expand(key, value):
            if isinstance(value, dict):
                return [(key + '.' + k, v) for k, v in flatten_dict(value).items()]
            else:
                return [(key, value)]

        items = [item for k, v in d.items() for item in expand(k, v)]

        return dict(items)

    b = aac.library.bundle(vid)

    metadata = {k: sorted(flatten_dict(v).items()) for k, v in b.metadata.dict.items()}

    cxt = dict(
        vid=vid,
        b=b,
        metadata=sorted(metadata.items()),
        **aac.cc
    )

    return aac.render('bundle/meta.html', **cxt)


@app.route('/bundles/<vid>/files')
def bundle_files(vid):
    cxt = dict(
        vid=vid,
        b=aac.library.bundle(vid),
        **aac.cc
    )

    return aac.render('bundle/partitions.html', **cxt)


@app.route('/bundles/<vid>/file/<name>')
def bundle_file(vid, name):
    """Return a file from the bundle"""
    from cStringIO import StringIO
    from ambry.orm.file import File
    from contextlib import closing

    b = aac.library.bundle(vid)

    bs = b.build_source_files.instance_from_name(name)

    return send_file(bs.get_string_io(),
                     cache_timeout=0,
                     as_attachment=True,
                     attachment_filename = b.identity.vname+'-'+name)


@app.route('/bundles/<vid>/notebooks')
def bundle_notebooks(vid):
    """Return a file from the bundle"""
    from ambry.orm.file import File

    b = aac.library.bundle(vid)

    cxt = dict(
        vid=vid,
        b=b,
        notebooks=b.build_source_files.list_records(File.BSFILE.NOTEBOOK),
        **aac.cc

    )

    return aac.render('bundle/notebooks.html', **cxt)


@app.route('/bundles/<vid>/notebooks/<fileid>')
def bundle_notebook(vid, fileid):
    """Return a file from the bundle"""
    from ambry.orm.file import File
    import nbformat
    from traitlets.config import Config
    from nbconvert import HTMLExporter

    b = aac.library.bundle(vid)

    nbfile = b.build_source_files.file_by_id(fileid)

    notebook = nbformat.reads(nbfile.unpacked_contents, as_version=4)

    html_exporter = HTMLExporter()
    html_exporter.template_file = 'basic'

    (body, resources) = html_exporter.from_notebook_node(notebook)

    cxt = dict(
        vid=vid,
        b=b,
        fileid=fileid,
        nbfile=nbfile,
        notebooks=b.build_source_files.list_records(File.BSFILE.NOTEBOOK),
        notebook=notebook,
        notebook_html=body,
        **aac.cc

    )

    return aac.render('bundle/notebook.html', **cxt)


@app.route('/search')
def search():
    """Search for a datasets and partitions, using a structured JSON term."""

    terms = request.args['terms']

    results = list(aac.library.search.search(terms))

    try:
        r =  aac.render('search/results.html', result_count=len(results), results=results[:10],
                          terms=terms, **aac.cc)
    except Exception as e:
        raise

    return r


@app.route('/bundles/<vid>/tables/<tvid>')
def get_table(vid, tvid):
    b = aac.library.bundle(vid)

    cxt = dict(
        vid=vid,
        tvid=tvid,
        b=b,
        t=b.table(tvid),
        **aac.cc

    )

    return aac.render('bundle/table.html', **cxt)


@app.route('/partitions/<pvid>')
def get_partition(pvid):

    p = aac.library.partition(pvid)
    b = p.bundle

    # FIXME This should be cached somewhere.

    source_names = [s.name for s in p.table.sources]

    docs = []

    for k, v in b.metadata.external_documentation.group_by_source().items():
        if k in source_names:
            for d in v:
                docs += v

    cxt = dict(
        vid=b.identity.vid,
        b=b,
        p=p,
        t=p.table,
        docs=docs,
        **aac.cc
    )

    return aac.render('bundle/partition.html', **cxt)

@app.route('/bundles/<bvid>/process')
def bundle_process(bvid):
    b = aac.library.bundle(bvid)

    headers, rows = b.progress.stats()

    cxt = dict(
        vid=bvid,
        b=b,
        exceptions=b.progress.exceptions,
        process=b.progress.bundle_process_logs(show_all=False),
        stats=[[''] + headers] + rows,
        **aac.cc
    )

    return aac.render('bundle/process.html', **cxt)


@app.route('/file/<pvid>.<ct>')
def stream_file(pvid, ct):
    from flask import abort
    from flask.ext.login import current_user
    from ambry.orm.exc import NotFoundError

    try:
        p = aac.library.partition(pvid)
    except NotFoundError as e:
        app.logger.error("Stream file: failed to find partition: {}".format(e))
        return abort(404)

    if p.bundle.metadata.about.access != 'public' and not current_user.is_authenticated:
        from api import jwt_auth
        r = jwt_auth()
        if r != 0:
            return abort(r)

    try:
        if ct == 'csv':
            return stream_csv(pvid)
        elif ct == 'mpack':
            return stream_mpack(pvid)
    except NotFoundError as e:
        app.logger.error("Stream file: failed to get file: {}".format(e))
        pass

    return abort(404)


def stream_csv(pvid):
    from flask import Response
    import cStringIO as StringIO
    import unicodecsv as csv

    p = aac.library.partition(pvid)

    p.localize()

    reader = p.reader

    def yield_csv_row(w, b, row):
        w.writerow(row)
        b.seek(0)
        data = b.read()
        b.seek(0)
        b.truncate()
        return data

    def stream_csv():
        b = StringIO.StringIO()
        writer = csv.writer(b)

        yield yield_csv_row(writer, b, reader.headers)

        for row in reader.rows:
            yield yield_csv_row(writer, b, row)

    return Response(stream_csv(), mimetype='text/csv')


def stream_mpack(pvid):
    from flask import Response
    import cStringIO as StringIO
    import unicodecsv as csv
    import msgpack

    p = aac.library.partition(pvid)

    p.localize()

    reader = p.reader

    def stream_msgp():
        yield msgpack.packb(reader.headers)
        for row in reader.rows:
            yield msgpack.packb(row)

    return Response(stream_msgp(), mimetype='application/msgpack')
