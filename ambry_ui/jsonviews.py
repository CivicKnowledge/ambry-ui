"""
API Views, return javascript renditions of objects and allowing modification of the database
"""

from flask import url_for
from werkzeug.local import LocalProxy
from . import app, get_aac


aac = LocalProxy(get_aac)

@app.route('/json')
def bundle_index_json():

    def augment(b):
        o = b.dataset.dict
        o['bundle_url'] = url_for('bundle_json', vid=o['vid'])
        o['title'] = b.metadata.about.title
        o['summary'] = b.metadata.about.summary
        o['created'] = b.buildstate.new_datetime.isoformat() if b.buildstate.new_datetime else None
        o['updated'] = b.buildstate.last_datetime.isoformat() if b.buildstate.last_datetime else None
        b.close()
        return o

    return aac.json(
        bundles=[augment(b) for b in aac.library.bundles]

    )

@app.route('/json/bundle/<vid>')
def bundle_json(vid):

    b = aac.bundle(vid)

    def aug_dataset(b):
        o = b.dataset.dict
        del o['dataset']
        o['title'] = b.metadata.about.title
        o['summary'] = b.metadata.about.summary
        o['created'] = b.buildstate.new_datetime.isoformat() if b.buildstate.new_datetime else None
        o['updated'] = b.buildstate.last_datetime.isoformat() if b.buildstate.last_datetime else None
        return o

    def aug_partition(o):

        o['csv_url'] = url_for('stream_file', pvid=o['vid'], ct='csv')
        o['details_url'] = url_for('partition_json', vid=o['vid'])
        o['description'] = p.table.description
        o['sub_description'] = p.display.sub_description
        return o

    def partitions():
        from ambry.orm import Partition
        from sqlalchemy.orm import noload, joinedload
        for p in (b.dataset.query(Partition).filter(Partition.d_vid == b.identity.vid)
                          .options(noload('*'), joinedload('table')).all()):
            yield p

    b.close()
    return aac.json(
        dataset=aug_dataset(b),
        partitions = [ aug_partition(p.dict) for p in partitions() ]

    )


@app.route('/json/partition/<vid>')
def partition_json(vid):

    p = aac.library.partition(vid)

    d = p.dict
    d['csv_url'] = url_for('stream_file', pvid=p.vid, ct='csv')

    d['description'] = p.table.description
    d['sub_description'] = p.sub_description

    def aug_col(c):
        d = c.dict
        d['stats'] = [ s.dict for s in c.stats ]
        return d

    d['table'] = p.table.dict
    d['table']['columns'] = [ aug_col(c) for c in p.table.columns ]
    return aac.json(
        partition = d

    )
