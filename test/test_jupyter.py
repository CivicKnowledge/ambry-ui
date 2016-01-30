import unittest
from ambry import get_library

class ContentsManagerTest(unittest.TestCase):

    test_root = None

    @classmethod
    def setUpClass(cls):
        import tempfile

        cls.test_root = tempfile.mkdtemp()

    @classmethod
    def tearDownClass(cls):
        import shutil
        import os

        if os.path.exists(cls.test_root):
            shutil.rmtree(cls.test_root)

    def library(self):
        from ambry import get_library
        l =  get_library(root=self.test_root, db='sqlite:///{root}/library.db')

        if not l.exists:
            l.create()

        print 'Library: {}'.format(l.database.dsn)

        return l

    def test_basic(self):

        from notebook.notebookapp import NotebookApp
        import sys

        l = self.library()
        b = l.new_bundle(source='example.com', dataset='test', assignment_class='self')
        l.commit()

        sys.argv = ['ambry']
        app = NotebookApp.instance()
        app._library = l
        app.contents_manager_class = 'ambry_ui.jupyter.AmbryContentsManager'
        app.initialize(None)

        cm = app.contents_manager

        self.assertEqual('example.com', cm.get('')['content'][0]['path'])

        self.assertEqual('/example.com/test-0.0.1/bundle.yaml',  cm.get(b.identity.cache_key)['content'][0]['path'])




if __name__ == '__main__':
    unittest.main()
