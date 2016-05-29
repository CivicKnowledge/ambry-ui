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

logger = logging.getLogger('gunicorn.access')

@app.route('/partitions/<pvid>/plots/<cvid>.csv')
def get_plots_csv(pvid, cvid):
    """Return the CSV file for the data for a plot
    :param pvid:
    :param cvid: The measure to plot
    """
    from flask import Response
    from cStringIO import StringIO

    primary_dimension = request.args.get('primary')
    secondary_dimension = request.args.get('secondary', None)

    p = aac.library.partition(pvid)

    md = p.measuredim

    measure = md.measure(cvid)

    b = StringIO()

    md.md_frame(measure=measure.name,
                    p_dim=primary_dimension,
                    s_dim=secondary_dimension).sort_index().to_csv(b)

    return Response(b.getvalue(), mimetype='text/csv')

@app.route('/partitions/<pvid>/plots/<cvid>.json')
def get_plots_json(pvid, cvid):
    """Return the json configuration for a plot
    :param pvid:
    :param cvid: The measure to plot
    """
    from flask import Response
    from cStringIO import StringIO

    primary_dimension = request.args.get('primary')
    secondary_dimension = request.args.get('secondary', None)

    p = aac.library.partition(pvid)

    md = p.measuredim

    measure = md.measure(cvid)

    return aac.json(
        primary_dimension=primary_dimension,
        secondary_dimension=secondary_dimension,
        measure=measure.name
    )

@app.route('/partitions/<pvid>/plots/<cvid>')
def get_plots(pvid, cvid):

    import json

    p = aac.library.partition(pvid)
    b = p.bundle

    cxt = dict(
        vid=b.identity.vid,
        b=b,
        p=p,

        **aac.cc
    )


    measure = 'unemployment_rate'
    p_dim = 'gvid'
    s_dim = 'raceth'
    filtered_dims = {'reportyear': '2006/2010', 'raceth' : 6}

    #rows = p.measuredim.md_array(measure=measure,
    #                             p_dim=p_dim,
    #                             s_dim=s_dim,
    #                             filtered_dims=filtered_dims)

    #rows = [rows[0]] + sorted(rows[1:], key=lambda r: -r[1])

    md = p.measuredim

    for r in md.primary_measures:
        print "MEASURE: ", r.name

    for r in md.primary_dimensions:
        print r.name, r.label, r.labels

    rows = [[1,2,3]]

    plot_config = {
        'chart': {},
        'axis': {

            'x': {
                'height': 130,
                'tick': {
                    'multiline': False,
                    'rotate': 60
                },
                'type': 'category'
            }
        },
        'bar': {
            'width': {
                'ratio': .8
            }
        },
        'data': {
            'xSort': 'true',
            'rows': rows,
            'type': 'bar',
            'x': rows[0][0],
            #'groups': [rows[0][1:]],

        }
    }

    return aac.render('bundle/plots.html',
                      plot_config=plot_config,
                      measures = md.primary_measures,
                      dimensions = md.primary_dimensions,
                      dumps=json.dumps, **cxt)
