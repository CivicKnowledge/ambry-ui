"""A contents manager that uses the ambry database for storage"""

import nbformat
import os
from ipython_genutils.importstring import import_item
from ipython_genutils.py3compat import getcwd, string_types
from notebook.services.contents.checkpoints import Checkpoints, GenericCheckpointsMixin
from notebook.services.contents.manager import ContentsManager
from tornado import web
from traitlets import Any, Unicode, Bool, TraitError

_script_exporter = None


# FIXME. Should actually implement checkpoints
class AmbryCheckpoints(Checkpoints, GenericCheckpointsMixin):

    def restore_checkpoint(self, contents_mgr, checkpoint_id, path):
        pass

    def rename_checkpoint(self, checkpoint_id, old_path, new_path):
        pass

    def list_checkpoints(self, path):
        return []

    def delete_checkpoint(self, checkpoint_id, path):
        pass

    def create_checkpoint(self, contents_mgr, path):
        from datetime import datetime

        return dict(
            id='0',
            last_modified=datetime.now(),
        )


class AmbryContentsManager(ContentsManager):

    def __init__(self, *args, **kwargs):
        super(AmbryContentsManager, self).__init__(*args, **kwargs)

        self._library_args = self.parent._library.ctor_args


    @property
    def library_context(self):

        from ambry.library import LibraryContext
        return LibraryContext(self._library_args)

    root_dir = Unicode(config=True)

    def _root_dir_default(self):
        try:
            return self.parent.notebook_dir
        except AttributeError:
            return getcwd()

    save_script = Bool(False, config=True, help='DEPRECATED, use post_save_hook')
    def _save_script_changed(self):
        self.log.warn("""
        `--script` is deprecated. You can trigger nbconvert via pre- or post-save hooks:

            ContentsManager.pre_save_hook
            FileContentsManager.post_save_hook

        A post-save hook has been registered that calls:

            ipython nbconvert --to script [notebook]

        which behaves similarly to `--script`.
        """)

        pass

    post_save_hook = Any(None, config=True,
        help="""Python callable or importstring thereof

        to be called on the path of a file just saved.

        This can be used to process the file on disk,
        such as converting the notebook to a script or HTML via nbconvert.

        It will be called as (all arguments passed by keyword)::

            hook(os_path=os_path, model=model, contents_manager=instance)

        - path: the filesystem path to the file just written
        - model: the model representing the file
        - contents_manager: this ContentsManager instance
        """
    )
    def _post_save_hook_changed(self, name, old, new):
        if new and isinstance(new, string_types):
            self.post_save_hook = import_item(self.post_save_hook)
        elif new:
            if not callable(new):
                raise TraitError("post_save_hook must be callable")

    def run_post_save_hook(self, model, os_path):
        """Run the post-save hook if defined, and log errors"""
        if self.post_save_hook:
            try:
                self.log.debug("Running post-save hook on %s", os_path)
                self.post_save_hook(os_path=os_path, model=model, contents_manager=self)
            except Exception:
                self.log.error("Post-save hook failed on %s", os_path, exc_info=True)

    def _root_dir_changed(self, name, old, new):
        """Do a bit of validation of the root_dir."""
        if not os.path.isabs(new):
            # If we receive a non-absolute path, make it absolute.
            self.root_dir = os.path.abspath(new)
            return
        if not os.path.isdir(new):
            raise TraitError("%r is not a directory" % new)

    def _checkpoints_class_default(self):
        return AmbryCheckpoints

    def file_exists(self, path):
        """Returns True if the file exists, else returns False.

        API-style wrapper for os.path.isfile

        Parameters
        ----------
        path : string
            The relative path to the file (with '/' as separator)

        Returns
        -------
        exists : bool
            Whether the file exists.
        """
        from ambry.orm.exc import NotFoundError

        path = path.strip('/')
        parts = path.split('/')
        cache_key = os.path.join(*parts[:2])
        file_name = parts[-1]

        if path == '':
            # Root
            return False # Isn't a file

        elif path.count('/') == 0:

            return False # Isn't a file

        elif path.count('/') == 1:

            return False # Isn't a file

        elif path.count('/') == 2:

            with self.library_context as l:

                b = l.bundle_by_cache_key(cache_key)

                try:
                    bs = b.dataset.bsfile(file_name)
                    return True
                except NotFoundError:
                    return False

        else:

            return False

    def is_hidden(self, path):

        return False # We have nothing to hide

    def dir_exists(self, path):
        path = path.strip('/')

        if path == '':
            # Root
            return True # It always exists

        elif path.count('/') == 0:
            # Source
            return True  # HACK, just assume it does exist

        elif path.count('/') == 1:
            # Bundle
            return True # Isn't a file

        elif path.count('/') == 2:

            return False # A bundle file, isn't a directory


    def _root_model(self):

        from datetime import datetime

        model = {'name': '',
                 'path': '',
                 'type': 'directory',
                 'format': 'json',
                 'mimetype': None,
                 'last_modified': datetime.now(),
                 'created': datetime.now(),
                 'writable': False}

        content = {}

        with self.library_context as l:
            for b in l.bundles:
                cm = {'name': b.identity.source,
                      'path': b.identity.source,
                      'type': 'directory',
                      'format': None,
                      'mimetype': None,
                      'content': None,
                      'writable': True}

                content[b.identity.source] = cm

        model['content'] = sorted(content.values())

        return model

    def _source_model(self, source):

        from datetime import datetime

        model = {'name': source,
                 'path': '/' + source,
                 'type': 'directory',
                 'format': 'json',
                 'mimetype': None,
                 'last_modified': datetime.now(),
                 'created': datetime.now(),
                 'writable': False}

        content = []

        with self.library_context as l:
            for b in l.bundles:

                if b.identity.source == source:
                    source, name = b.identity.cache_key.split('/')

                    cm = {'name': name,
                          'path': b.identity.cache_key,
                          'type': 'directory',
                          'format': 'json',
                          'mimetype': None,
                          'content': None,
                          'writable': False}

                    content.append(cm)

        model['content'] = sorted(content)

        return model

    def _bundle_model(self, cache_key):

        from datetime import datetime
        from ambry.orm import File

        with self.library_context as l:
            b = l.bundle_by_cache_key(cache_key)

            model = {'name': b.identity.vname,
                     'path': '/' + cache_key,
                     'type': 'directory',
                     'format': 'json',
                     'mimetype': None,
                     'last_modified': datetime.now(),
                     'created': datetime.now(),
                     'writable': False}

            content = []

            for f in b.build_source_files.list_records():

                    cm = {'name': f.file_name,
                          'path': '/{}/{}'.format(cache_key, f.file_name),
                          'type': 'notebook' if f.file_const == File.BSFILE.NOTEBOOK else 'file',
                          'format': 'json',
                          'mimetype': f.record.mime_type,
                          'content': None,
                          'writable': False}

                    content.append(cm)

        model['content'] = sorted(content)

        return model


    def _file_model(self, path, content=True, format=None):
        """Build a model for a file

        if content is requested, include the file contents.

        format:
          If 'text', the contents will be decoded as UTF-8.
          If 'base64', the raw bytes contents will be encoded as base64.
          If not specified, try to decode as UTF-8, and fall back to base64
        """

        parts = path.split('/')
        cache_key = os.path.join(*parts[:2])
        file_name = parts[-1]

        with self.library_context as l:
            b = l.bundle_by_cache_key(cache_key)

            f = b.build_source_files.instance_from_name(file_name)

            model = {'name': file_name,
                     'path': path,
                     'type': 'file',
                     'format': 'text',
                     'mimetype': 'text/plain',
                     'last_modified': f.record.modified_datetime,
                     'created': f.record.modified_datetime,
                     'writable': False}

            model['content'] = f.getcontent()

        return model

    def _file_from_path(self, l,  path):

        parts = path.split('/')
        cache_key = os.path.join(*parts[:2])
        file_name = parts[-1]

        b = l.bundle_by_cache_key(cache_key)

        f = b.build_source_files.instance_from_name(file_name)

        if not f.record.modified:
            import time
            f.record.modified = int(time.time())

        assert f.record.modified

        return b, f

    def _notebook_model(self, path, content=True):
        """Build a notebook model

        if content is requested, the notebook content will be populated
        as a JSON structure (not double-serialized)
        """

        with self.library_context as l:

            b, f = self._file_from_path(l, path)

            model = {'name': f.file_name,
                     'path': path,
                     'type': 'notebook',
                     'format': None,
                     'mimetype': None,
                     'last_modified': f.record.modified_datetime,
                     'created': f.record.modified_datetime,
                     'writable': True,
                     'content': None
                     }

            if content:
                from cStringIO import StringIO

                sio = StringIO()
                f.record_to_fh(sio)
                sio.seek(0)

                nb = nbformat.read(sio, as_version=4)
                self.mark_trusted_cells(nb, path)
                model['content'] = nb
                model['format'] = 'json'
                self.validate_notebook_model(model)
                pass

        return model

    def get(self, path, content=True, type=None, format=None):
        """ Takes a path for an entity and returns its model

        Parameters
        ----------
        path : str
            the API path that describes the relative path for the target
        content : bool
            Whether to include the contents in the reply
        type : str, optional
            The requested type - 'file', 'notebook', or 'directory'.
            Will raise HTTPError 400 if the content doesn't match.
        format : str, optional
            The requested format for file contents. 'text' or 'base64'.
            Ignored if this returns a notebook or directory model.

        Returns
        -------
        model : dict
            the contents model. If content=True, returns the contents
            of the file or directory as well.
        """

        path = path.strip('/')

        if path == '':

            model = self._root_model()

        elif path.count('/') == 0:

            model = self._source_model(path.strip('/'))

        elif path.count('/') == 1:

            model = self._bundle_model(path)

        elif type == 'notebook' or (type is None and path.endswith('.ipynb')):
            model = self._notebook_model(path, content=content)

        else:
            if type == 'directory':
                raise web.HTTPError(400,
                                u'%s is not a directory' % path, reason='bad type')
            model = self._file_model(path, content=content, format=format)


        return model

    def save(self, model, path=''):
        """Save the file model and return the model with no content."""

        import json

        path = path.strip('/')

        with self.library_context as l:
            b, f = self._file_from_path(l, path)

            if 'type' not in model:
                raise web.HTTPError(400, u'No file type provided')
            if 'content' not in model and model['type'] != 'directory':
                raise web.HTTPError(400, u'No file content provided')

            self.run_pre_save_hook(model=model, path=f.record.id)

            if not f.record.size:
                f.record.update_contents(f.default, 'application/json')
            else:
                f.record.update_contents(json.dumps(model['content']), 'application/json')

            try:
                if model['type'] == 'notebook':

                    nb = nbformat.from_dict(model['content'])
                    self.check_and_sign(nb, path)

                    # One checkpoint should always exist for notebooks.

                    if not self.checkpoints.list_checkpoints(path):
                        self.create_checkpoint(path)

                elif model['type'] == 'file':
                    pass
                elif model['type'] == 'directory':
                    pass
                else:
                    raise web.HTTPError(400, "Unhandled contents type: %s" % model['type'])
            except web.HTTPError:
                raise
            except Exception as e:
                self.log.error(u'Error while saving file: %s %s', path, e, exc_info=True)
                raise web.HTTPError(500, u'Unexpected error while saving file: %s %s' % (path, e))

            validation_message = None
            if model['type'] == 'notebook':
                self.validate_notebook_model(model)
                validation_message = model.get('message', None)

        model = self.get(path, content=False)

        if validation_message:
            model['message'] = validation_message



        return model

    def delete_file(self, path):
        """Delete file at path."""
        from ambry.orm.exc import NotFoundError
        path = path.strip('/')

        if path == '':
            raise web.HTTPError(400, u"Not deletable")

        elif path.count('/') == 0:
            raise web.HTTPError(400, u"Not deletable")

        elif path.count('/') == 1:
            raise web.HTTPError(400, u"Not deletable")

        with self.library_context as l:
            from ambry.orm.exc import CommitTrap

            l.database._raise_on_commit = True
            try:
                b, f = self._file_from_path(l, path)
                f.remove()
                f.remove_record()

            except CommitTrap:
                raise

            except NotFoundError:
                raise web.HTTPError(404, u"Bundle does not exist: {}".format(path))

            finally:
                l.database._raise_on_commit = False

    def rename_file(self, old_path, new_path):
        """Rename a file."""

        from ambry.orm.exc import NotFoundError

        old_path = old_path.strip('/')
        new_path = new_path.strip('/')

        if new_path == old_path:
            return

        with self.library_context as l:
            b, f_old = self._file_from_path(l, old_path)

            parts = new_path.split('/')
            file_name = parts[-1]

            try:
                bs = b.dataset.bsfile(file_name)
                raise web.HTTPError(409, u'File already exists: %s' % new_path)
            except NotFoundError:
                pass

            f_old.record.path = file_name

    def info_string(self):
        return ""

    def get_kernel_path(self, path, model=None):
        """Return the initial API path of  a kernel associated with a given notebook"""
        if '/' in path:
            parent_dir = path.rsplit('/', 1)[0]
        else:
            parent_dir = ''
        return parent_dir

