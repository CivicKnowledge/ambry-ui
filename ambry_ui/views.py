""" Public views

Copyright (c) 2015 Civic Knowledge. This file is licensed under the terms of
the Revised BSD License, included in this distribution as LICENSE.txt
"""

import os
from . import app, get_aac


from flask import g, current_app, send_from_directory, send_file, request, abort, url_for
from flask.json import jsonify

from werkzeug.local import LocalProxy


aac = LocalProxy(get_aac)

@app.errorhandler(500)
def page_not_found(e):

    aac.render('500.html', e=e)

@app.route('/')
@app.route('/index')
def index():
    r = aac.renderer

    cxt = dict(
        bundles=[b for b in r.library.bundles],
        **r.cc()
    )

    return r.render('index.html', **cxt)


@app.route('/bundles')
def bundle_index():

    r = aac.renderer

    cxt = dict(
        bundles=[b for b in r.library.bundles],
        **r.cc()
    )

    return r.render('bundles.html', **cxt)



@app.route('/bundles/<vid>')
def bundle_main(vid):

    r = aac.renderer

    cxt = dict(
        vid=vid,
        b=r.library.bundle(vid),
        sources_header=['name', 'source_table_name', 'ref'],
        **r.cc()
    )

    return r.render('bundle/about.html', **cxt)


@app.route('/bundles/<vid>/meta')
def bundle_meta(vid):

    r = aac.renderer

    def flatten_dict(d):
        def expand(key, value):
            if isinstance(value, dict):
                return [(key + '.' + k, v) for k, v in flatten_dict(value).items()]
            else:
                return [(key, value)]

        items = [item for k, v in d.items() for item in expand(k, v)]

        return dict(items)

    b = r.library.bundle(vid)

    metadata = { k : sorted(flatten_dict(v).items()) for k, v in b.metadata.dict.items() }

    cxt = dict(
        vid=vid,
        b=b,
        metadata=sorted(metadata.items()),
        **r.cc()
    )

    return r.render('bundle/meta.html', **cxt)

@app.route('/bundles/<vid>/files')
def bundle_files(vid):

    r = aac.renderer

    cxt = dict(
        vid=vid,
        b=r.library.bundle(vid),
        **r.cc()
    )

    return r.render('bundle/partitions.html', **cxt)



@app.route('/bundles/<vid>/file/<name>')
def bundle_file(vid,name):
    """Return a file from the bundle"""
    from cStringIO import StringIO
    from ambry.orm.file import File
    from contextlib import closing

    m = { v:k for k,v in File.path_map.items()}

    b = aac.renderer.library.bundle(vid)

    bs = b.build_source_files.file(m[name])

    sio = StringIO()

    bs.record_to_fh(sio)

    with closing(sio):
        return send_file(StringIO(sio.getvalue()))


@app.route('/bundles/<vid>/notebooks')
def bundle_notebooks(vid):
    """Return a file from the bundle"""
    from ambry.orm.file import File

    r = aac.renderer
    b = r.library.bundle(vid)

    cxt = dict(
        vid=vid,
        b=b,
        notebooks=b.build_source_files.list_records(File.BSFILE.NOTEBOOK),
        **r.cc()

    )

    return r.render('bundle/notebooks.html', **cxt)


@app.route('/bundles/<vid>/notebooks/<fileid>')
def bundle_notebook(vid, fileid):
    """Return a file from the bundle"""
    from ambry.orm.file import File
    import nbformat
    from traitlets.config import Config
    from nbconvert import HTMLExporter

    r = aac.renderer
    b = r.library.bundle(vid)

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
        notebook_html = body,

        **r.cc()

    )


    return r.render('bundle/notebook.html', **cxt)


@app.route('/search')
def search():
    """Search for a datasets and partitions, using a structured JSON term."""

    terms = request.args['terms']

    r = aac.renderer

    results = list(r.library.search.search(terms))

    return r.render('search/results.html', result_count=len(results), results=results[:10],
                    terms = terms, **r.cc())


@app.route('/bundles/<vid>/tables/<tvid>')
def get_table(vid, tvid):

    r = aac.renderer
    b = r.library.bundle(vid)

    cxt = dict(
        vid=vid,
        tvid=tvid,
        b=b,
        t=b.table(tvid),
        **r.cc()

    )

    return r.render('bundle/table.html', **cxt)

@app.route('/partitions/<pvid>')
def get_partition(pvid):
    r = aac.renderer
    p = r.library.partition(pvid)
    b = p.bundle

    # FIXME This should be cached somewhere.

    source_names = [ s.name for s in p.table.sources ]

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
        **r.cc()
    )

    return r.render('bundle/partition.html', **cxt)

@app.route('/partitions/<pvid>/recline')
def get_recline(pvid):
    r = aac.renderer
    p = r.library.partition(pvid)
    b = p.bundle



    source_names = [ s.name for s in p.table.sources ]

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
        **r.cc()
    )

    return r.render('bundle/recline.html', **cxt)

@app.route('/bundles/<bvid>/process.<ct>')
def bundle_process(bvid, ct):
    r = aac.renderer.cts(ct)
    b = r.library.bundle(bvid)

    headers, rows = b.progress.stats()

    cxt = dict(
        vid=bvid,
        b=b,
        exceptions = b.progress.exceptions,
        process=b.progress.bundle_process_logs(show_all=False),
        stats= [['']+headers] + rows,
        **r.cc()
    )

    return r.render('bundle/process.html', **cxt)

@app.route('/file/<pvid>.<ct>')
def stream_file(pvid,ct):
    from flask import abort
    from flask.ext.login import current_user
    from ambry.orm.exc import NotFoundError

    r = aac.renderer

    try:
        p = r.library.partition(pvid)
    except NotFoundError:
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
    except NotFoundError:
        pass

    return abort(404)

def stream_csv(pvid):
    from flask import Response
    import cStringIO as StringIO
    import unicodecsv as csv

    r = aac.renderer
    p = r.library.partition(pvid)

    if p.is_local:
        reader = p.reader
    else:
        reader = p.remote_datafile.reader

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

    r = aac.renderer
    p = r.library.partition(pvid)

    if p.is_local:
        reader = p.reader
    else:
        reader = p.remote_datafile.reader

    def stream_msgp():
        yield msgpack.packb(reader.headers)
        for row in reader.rows:
            yield msgpack.packb(row)

    return Response(stream_msgp(), mimetype='application/msgpack')

