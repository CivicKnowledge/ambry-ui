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
logger.setLevel(logging.DEBUG)


@app.route('/partitions/<pvid>/plots')
def get_plots(pvid):

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

    rows = p.measuredim.md_array(measure=measure,
                                 p_dim=p_dim,
                                 s_dim=s_dim,
                                 filtered_dims=filtered_dims)

    rows = [rows[0]] + sorted(rows[1:], key=lambda r: -r[1])

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

    return aac.render('bundle/plots.html', plot_config=plot_config, dumps=json.dumps, **cxt)
