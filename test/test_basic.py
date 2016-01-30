import unittest
from flask import Flask
from flask.ext.testing import TestCase
import json

import os
os.environ['AMBRY_DB'] = 'sqlite:////tmp/foo.db'

class MyTestCase(TestCase):

    def create_app(self):
        from ambry_ui import app
        import ambry_ui.views
        import ambry_ui.jsonviews
        import ambry_ui.api
        import ambry_ui.user

        self.username = 'user'
        self.secret = 'secret'

        return app

    def setup_user(self):
        from ambry_ui import get_aac

        l = get_aac().library
        act = l.find_or_new_account(self.username)
        act.secret = self.secret
        act.major_type = 'user'
        l.commit()

    def add_auth_header(self, headers):
        import jwt

        t = jwt.encode({'u': self.username}, self.secret, algorithm='HS256')

        headers['Authorization'] = "JWT {}:{}".format(self.username, t)

    def test_auth(self):
        from werkzeug.datastructures import Headers

        self.setup_user()

        r = self.client.get('/json')
        self.assert200(r)

        headers = Headers()
        self.add_auth_header(headers)

        r = self.client.post('/auth-test',
                             headers = headers,
                             content_type='application/json',
                             data=json.dumps(dict(foo='bar')))
        self.assert200(r)
        self.assertEqual('bar',r.json['content']['foo'])

if __name__ == '__main__':
    unittest.main()
