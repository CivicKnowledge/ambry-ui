""" User views

Copyright (c) 2015 Civic Knowledge. This file is licensed under the terms of
the Revised BSD License, included in this distribution as LICENSE.txt
"""

from . import app, get_aac
from werkzeug.local import LocalProxy
from flask import session, request, flash, redirect, abort, url_for
from flask_login import login_user, logout_user, login_required, current_user

aac = LocalProxy(get_aac)

import logging

logger = app.logger

logger = logging.getLogger('gunicorn.access')


def plot_df(pvid, measure_ref, **kwargs):
    """Return a dataframe for a plot"""

    primary_dimension = None
    secondary_dimension = None
    filtered = {}

    p = aac.library.partition(pvid)

    md = p.measuredim

    measure = md.measure(measure_ref)

    for k, v in kwargs.items():

        if k == 'primary':
            primary_dimension = v
        elif k == 'secondary':
            secondary_dimension = v
        else:
            # The filter value need to be of the same data type as the column, or
            # the filtering code may try to, for instance, check equality between a string
            # and an int.
            d = md.dimension(k)
            filtered[k] = d.python_type(v)

    df = md.dataframe(measure.name,primary_dimension,secondary_dimension,filters=filtered)


    # Hack! The dataframe datatype is not preserved across all of the operations below,
    # so we have to manually preserve the metadata.
    _metadata = df._metadata
    metadata = { k:getattr(df, k)  for k in _metadata }

    labels = df.labels

    columns = labels + [df.measure]

    if 'gvid' in list(df.columns):
        columns.append('gvid')

    df = df[columns]

    if secondary_dimension:
        df = df.set_index(labels).unstack()
        df.columns = df.columns.droplevel()
    else:
        df = df.set_index(labels)

    df.reset_index(inplace=True)
    df.set_index(labels[0], inplace=True)

    # Total Hack!
    df._metadata = _metadata
    for k in _metadata:
        setattr(df, k, metadata[k])


    return df



def measure_dict(p, m):
    return dict(
        vid=m.vid,
        name=m.name,
        valuetype=m.valuetype,
        datatype=m.python_type.__name__,
        label=m.label.name if m.label else None,
        labels=m.labels,
        uniques=m.pstats.nuniques,
        length=m.pstats.count,
    )


def dimension_dict(p, d):
    return dict(
        vid=d.vid,
        name=d.name,
        valuetype=d.valuetype,
        datatype=d.python_type.__name__,
        label=d.label.name if d.label else None,
        labels=d.labels,
        uniques=d.pstats.nuniques,
        length=d.pstats.count,
        is_geo=d.valuetype_class.is_geo(),
        is_time=d.valuetype_class.is_time(),
    )



def dimpath(p_dim, s_dim):

    assert p_dim

    return p_dim + ('/'+s_dim if s_dim else '')


def make_plot_json(pvid, measure, dimpath, filters = {}):

    md = aac.library.partition(pvid).measuredim

    ds = md.enumerate_dimension_sets()[dimpath]

    data_csv_url = url_for('get_plot_data_csv',
                           pvid=pvid, measure=measure, dimpath=dimpath,
                           **filters)

    plot_config = {

        'title': "{} vs {}".format(measure,
                                   " and ".join((ds['p_dim'], ds['s_dim']) if ds['s_dim'] else (ds['p_dim'],))),

        'data': {
            'url': data_csv_url,
            'mimeType': 'csv'
        },

        'axis': {

            'x': {
                'height': 130,
                'tick': {
                    'multiline': False,
                    'rotate': 60
                },
                'type': 'category'
            }
        }
    }

    if ds['p_dim_type'] == 'time':
        chart_type = 'line'
    else:

        plot_config['bar'] = {
            'bar': {
                'width': {
                    'ratio': .8
                }
            }
        }
        plot_config['data']['x'] = ds['p_label']
        plot_config['data']['type'] = 'bar'
        plot_config['data']['xSort'] = 'bar'

    plot_config['dimension_set'] = ds

    return plot_config



#@app.cache.memoize(timeout=300)
def measuredim_dict(pvid):

    md = aac.library.partition(pvid).measuredim

    d = md.dict

    return d

@app.route('/plots/<pvid>/config.json')
def get_plot_partition_config(pvid):
    """Return the json configuration for a partition, including all of the
    :param pvid:
    """
    return aac.json(**measuredim_dict(pvid))


@app.route('/plots/<pvid>/plots/<cvid>')
def get_plots(pvid, cvid):
    """A page of plots for a single partition"""
    import json

    p = aac.library.partition(pvid)
    b = p.bundle

    md = p.measuredim

    measure = md.measure(cvid)

    return aac.render('bundle/plots.html',
                      p=p, b=b,
                      measure=measure,
                      md=md.dict,
                      **aac.cc)

@app.route('/plots/<pvid>/data/<path:dimpath>/<measure>.csv')
def get_plot_data_csv(pvid, dimpath, measure):
    """Return the CSV file for the data for a plot
    :param pvid:
    :param cvid: The measure to plot
    """

    from flask import Response
    from cStringIO import StringIO

    buf = StringIO()
    p = aac.library.partition(pvid)

    md = p.measuredim.dict
    dim_set = md['dimension_sets'][dimpath]

    df = plot_df(pvid, measure, primary=dim_set['p_dim'], secondary =dim_set['s_dim'],
                 **dict(request.args.items()))  # Convert from MultiDict to dict

    df.sort_index().to_csv(buf)
    return Response(buf.getvalue(), mimetype='text/csv')


@app.route('/plots/<pvid>/data/<path:dimpath>/<measure>.json')
def get_plot_data_json(pvid, dimpath, measure):
    """Return the CSV file for the data for a plot
    :param pvid:
    :param cvid: The measure to plot
    """

    from flask import Response
    from cStringIO import StringIO

    b = StringIO()

    df = plot_df(pvid, measure, primary=dimpath)  # Assume there is only one component of path, for maps



    df.sort_index().reset_index().to_json(b, orient='records')

    return Response(b.getvalue(), mimetype='application/vnd.geo+json')


@app.route('/plots/<pvid>/config/<path:dimpath>/<measure>.json')
def get_plot_json(pvid, dimpath, measure):
    """Return the json configuration for a plot
    :param pvid:
    :param cvid: The measure to plot
    """

    d = make_plot_json(pvid, measure, dimpath)

    return aac.json(**d)


@app.route('/plots/<pvid>/config/map/measure.json')
def get_map_json(pvid, measure):
    """Return the json configuration for a map
    :param pvid:
    :param cvid: The measure to plot
    """

    d = make_map_json(pvid, cvid,
                      request.args.get('primary'),
                      request.args.get('secondary', None))

    return aac.json(**d)


@app.route('/plots/<pvid>/plot/<path:dimpath>/<measure>')
def get_plot(pvid, dimpath, measure):
    """A single plot page"""
    import json
    import copy

    plot_config = make_plot_json(pvid, measure, dimpath)

    p = aac.library.partition(pvid)
    b = p.bundle

    md = p.measuredim
    ds = plot_config['dimension_set']

    variants = []

    for filter_col, filter_vals in ds['filters'].items():
        for filter_val in filter_vals:
            d = make_plot_json(pvid, measure, dimpath, {filter_col:filter_val})
            d['subtitle'] = "Filter: {}={}".format(filter_col,filter_val)
            variants.append(d)

    return aac.render('bundle/plot.html',
                      config=plot_config,
                      dimension_set=ds,
                      variants=variants,
                      vid=b.identity.vid, b=b, p=p, **aac.cc)


@app.route('/plots/<pvid>/map/<measure>')
def get_map(pvid, measure):
    import json

    app.cache.set('foobar', 'foobtz')

    json_data_url = url_for('get_plot_data_json',
                            pvid=pvid, measure=measure,
                            dimpath='gvid')

    p = aac.library.partition(pvid)
    b = p.bundle

    md = p.measuredim

    measure = md.measure(measure)

    return aac.render('bundle/map.html',
                      measure=measure,

                      json_data_url=json_data_url,
                      vid=b.identity.vid, b=b, p=p, **aac.cc)



@app.route('/boundaries/<gvid>/<sl>')
def get_boundaries(gvid, sl):
    """
    Return a cached, static geojson file of boundaries for a region
    :param gvid:  The GVID of the region
    :param sl:  The summary level of the subdivisions of the region.
    :return:
    """

    from geojson import Feature, Point, FeatureCollection, dumps
    from shapely.wkt import loads
    from geoid.civick import GVid
    from os.path import join, exists
    from flask import send_from_directory

    cache_dir = aac.library.filesystem.cache('ui/geo')

    fn = "{}-{}.geojson".format(str(gvid), sl)
    fn_path = join(cache_dir, fn)

    if not exists(fn_path):

        p = aac.library.partition('census.gov-tiger-2015-counties')

        features = []

        for i, row in enumerate(p):
            if row.statefp == 6:  # In dev, assume counties in California

                gvid = GVid.parse(row.gvid)

                f = Feature(geometry=loads(row.geometry).simplify(0.01),
                            properties={
                                'gvid': row.gvid,
                                'state': gvid.state,
                                'county': gvid.county,
                                'count_name': row.name

                            })

                features.append(f)

        fc = FeatureCollection(features)

        with open(fn_path, 'w') as f:
            f.write(dumps(fc))

    return send_from_directory(cache_dir, fn, as_attachment=False, mimetype='application/vnd.geo+json')

