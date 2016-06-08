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


def plot_df(pvid, cvid, **kwargs):


    primary_dimension = None
    secondary_dimension = None
    filtered = {}

    p = aac.library.partition(pvid)

    md = p.measuredim

    measure = md.measure(cvid)

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

    return md.md_frame(measure=measure.name,
                     p_dim=primary_dimension,
                     s_dim=secondary_dimension,
                     filtered_dims=filtered,
                     unstack=True
                     )

@app.route('/partitions/<pvid>/plots/<cvid>.csv')
def get_plots_csv(pvid, cvid):
    """Return the CSV file for the data for a plot
    :param pvid:
    :param cvid: The measure to plot
    """

    from flask import Response
    from cStringIO import StringIO

    b = StringIO()

    df = plot_df(pvid, cvid, **dict(request.args.items())) # Convert from MultiDict to dict

    df.sort_index().to_csv(b)

    return Response(b.getvalue(), mimetype='text/csv')


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


@app.route('/partitions/<pvid>/plots.json')
def get_plots_json(pvid):
    """ Return a list of all possible plots.
    """

    p = aac.library.partition(pvid)

    md = p.measuredim

    # Axis dimensions are those that can be presented on an axis.
    # Category dimenions are dimensions that distinguish multiple lines or bars on a single chart.

    return aac.json(
        measures=[measure_dict(p, m) for m in md.primary_measures if p.stats_dict[m.name].nuniques > 1],
        dimensions=[dimension_dict(p, d) for d in md.primary_dimensions if p.stats_dict[d.name].nuniques > 1]
    )


def make_plot_json(pvid, cvid, primary_dimension, secondary_dimension=None):

    p = aac.library.partition(pvid)

    md = p.measuredim

    measure = md.measure(cvid)

    dimensions = [d for d in md.primary_dimensions if p.stats_dict[d.name].nuniques > 1]

    p_dim = md.dimension(primary_dimension)

    s_dim = md.dimension(secondary_dimension) if secondary_dimension else None

    filtered = {}

    for d in dimensions:
        if d.name != p_dim.name and (not s_dim or d.name != s_dim.name):
            filtered[d.name] = sorted(d.pstats.uvalues)[0]

    primary_dimension = dict(
        name=p_dim.name,
        labels=p_dim.label.name if p_dim.label else p_dim.name,
        len=p.stats_dict[p_dim.name].nuniques,
        values=p.stats_dict[p_dim.name].uvalues
    )
    secondary_dimension = dict(
        name=s_dim.name if s_dim else None,
        labels=s_dim.label.name if s_dim and s_dim.label else (s_dim.name if s_dim else None),
        len=p.stats_dict[s_dim.name].nuniques if s_dim else 0,
        values = p.stats_dict[s_dim.name].uvalues if s_dim else 0
    )

    df = plot_df(pvid=p.vid, cvid=measure.vid,
                 primary=p_dim.name,
                 secondary=s_dim.name if s_dim else None,
                 **filtered
                 )


    data = url_for('get_plots_csv', pvid=p.vid, cvid=measure.vid,
                   primary=p_dim.name,
                   secondary=s_dim.name if s_dim else None,
                   **filtered)

    bt_id = "{}-{}-{}-{}".format(pvid, cvid, primary_dimension['name'], secondary_dimension['name'])

    plot_config = {
        'bindto': '#' + bt_id,
        'data': {
            'url': data,
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

    if p_dim.valuetype_class.is_time():
        chart_type = 'line'
    else:
        chart_type = 'bar'
        plot_config['bar'] = {
            'bar': {
                'width': {
                    'ratio': .8
                }
            }
        }
        plot_config['data']['x'] = primary_dimension['labels']
        plot_config['data']['type'] = 'bar'
        plot_config['data']['xSort'] = 'bar'

    return dict(
        primary_dimension=primary_dimension,
        secondary_dimension=secondary_dimension,
        data=data,
        data_len=len(df),
        plot=plot_config
    )


@app.route('/partitions/<pvid>/plots/<cvid>.json')
def get_plot_json(pvid, cvid, return_json=True):
    """Return the json configuration for a plot
    :param pvid:
    :param cvid: The measure to plot
    """

    d = make_plot_json(pvid, cvid, request.args.get('primary'), request.args.get('secondary', None))

    if return_json:
        return aac.json(**d)
    else:
        return d


@app.route('/partitions/<pvid>/plots/<cvid>')
def get_plots(pvid, cvid):
    import json

    p = aac.library.partition(pvid)
    b = p.bundle

    md = p.measuredim

    measure = md.measure(cvid)

    dimension_sets = []

    dimensions = [d for d in md.primary_dimensions if p.stats_dict[d.name].nuniques > 1]

    def add_to_ds(d1, d2):

        if ((d1 != d2) and (not d2 or not d2.valuetype_class.is_geo())):

            if d1.valuetype_class.is_time():
                chart_type = 'line'
            else:
                chart_type = 'bar'

            filtered = {}
            for d in dimensions:
                if d != d1 and d != d2:
                    filtered[d.name] = sorted(d.pstats.uvalues)[0]

            dimension_sets.append([d1, d2, filtered, chart_type])

    for d1 in dimensions:
        add_to_ds(d1, None)

        for d2 in dimensions:
            add_to_ds(d1, d2)

    for i in range(len(dimension_sets)):
        d1, d2, filters, chart = dimension_sets[i]
        dimension_sets[i].append(make_plot_json(pvid, cvid, d1.name, d2.name if d2 else None))

    return aac.render('bundle/plots.html',
                      measure=measure,
                      dimensions=sorted(dimension_sets),
                      dumps=json.dumps,
                      vid=b.identity.vid, b=b, p=p, **aac.cc)


@app.route('/partitions/<pvid>/plot/<cvid>')
def get_plot(pvid, cvid):
    import json


    plot_config = make_plot_json(pvid, cvid, request.args.get('primary'), request.args.get('secondary', None))

    p = aac.library.partition(pvid)
    b = p.bundle

    md = p.measuredim

    measure = md.measure(cvid)

    return aac.render('bundle/plot.html',
                      measure=measure,
                      config=plot_config,
                      dumps=json.dumps,
                      vid=b.identity.vid, b=b, p=p, **aac.cc)
