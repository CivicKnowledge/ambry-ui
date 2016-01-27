"""A contents manager that uses the local file system for storage."""

# Copyright (c) Jupyter Development Team.
# Distributed under the terms of the Modified BSD License.


import io
import os
import shutil
import mimetypes
import nbformat

from tornado import web


from notebook.services.contents.manager import ContentsManager
from notebook.services.contents.checkpoints import Checkpoints, GenericCheckpointsMixin

from ipython_genutils.importstring import import_item
from traitlets import Any, Unicode, Bool, TraitError
from ipython_genutils.py3compat import getcwd, string_types
from notebook.services.contents import tz
from notebook.utils import (
    is_hidden,
    to_api_path,
)

_script_exporter = None


class AmbryCheckpoints(Checkpoints, GenericCheckpointsMixin):

    def restore_checkpoint(self, contents_mgr, checkpoint_id, path):
        pass

    def rename_checkpoint(self, checkpoint_id, old_path, new_path):
        pass

    def list_checkpoints(self, path):
        pass

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

        self._library = self.parent._library

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

        print 'FILE EXISTS?', path

        if path == '':
            # Root
            return False # Isn't a file

        elif path.count('/') == 0:

            return False # Isn't a file

        elif path.count('/') == 1:

            return False # Isn't a file

        elif path.count('/') == 2:


            print '!!!!', path, parts, cache_key, file_name

            b = self._library.bundle_by_cache_key(cache_key)

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

        print 'DIR EXISTS?', path

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

    def _get_os_path(self, path):
        """Return a filesystem path in the build directory. SHould only be used fro checkpoints,
        since notebooks go in the database.
        """
        from ambry.dbexceptions import ConfigurationError

        cp_path = self._library.filesystem.compose('build',path)

        cp_dir = os.path.dirname(cp_path)


        try:
            root = self._library.filesystem.build()
        except ConfigurationError as e:
            raise web.HTTPError(404, e.message)

        return cp_path

    def exists(self, path):
        """Returns True if the path exists, else returns False.

        API-style wrapper for os.path.exists

        Parameters
        ----------
        path : string
            The API path to the file (with '/' as separator)

        Returns
        -------
        exists : bool
            Whether the target exists.
        """
        path = path.strip('/')
        os_path = self._get_os_path(path=path)
        return os.path.exists(os_path)

    def _base_model(self, path):
        """Build the common base of a contents model"""
        from datetime import datetime
        # Create the base model.
        model = {'name': path.rsplit('/', 1)[-1],
                 'path': path,
                 'last_modified': datetime.now(),
                 'created': datetime.now(),
                 'content': None,
                 'format': None,
                 'mimetype': None,
                 'writable': False}

        return model

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

        for b in self._library.bundles:
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

        for b in self._library.bundles:

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

        b = self._library.bundle_by_cache_key(cache_key)

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
        from datetime import datetime

        parts = path.split('/')
        cache_key = os.path.join(*parts[:2])
        file_name = parts[-1]

        b = self._library.bundle_by_cache_key(cache_key)

        model = {'name': file_name,
                 'path': path,
                 'type': 'file',
                 'format': 'text',
                 'mimetype': 'text/plain',
                 'last_modified': datetime.now(),
                 'created': datetime.now(),
                 'writable': False}

        f = b.build_source_files.instance_from_name(file_name)

        model['content'] = f.getcontent()

        return model

    def _file_from_path(self, path):

        parts = path.split('/')
        cache_key = os.path.join(*parts[:2])
        file_name = parts[-1]

        b = self._library.bundle_by_cache_key(cache_key)

        f = b.build_source_files.instance_from_name(file_name)

        return b, f

    def _notebook_model(self, path, content=True):
        """Build a notebook model

        if content is requested, the notebook content will be populated
        as a JSON structure (not double-serialized)
        """

        from datetime import datetime

        b, f = self._file_from_path(path)

        model = {'name': f.file_name,
                 'path': path,
                 'type': 'notebook',
                 'format': None,
                 'mimetype': None,
                 'last_modified': f.record.modified_datetime or datetime.now(),
                 'created': f.record.modified_datetime or datetime.now(),
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

    def _save_directory(self, os_path, model, path=''):
        """create a directory"""
        raise NotImplementedError()
        if is_hidden(os_path, self.root_dir):
            raise web.HTTPError(400, u'Cannot create hidden directory %r' % os_path)
        if not os.path.exists(os_path):
            with self.perm_to_403():
                os.mkdir(os_path)
        elif not os.path.isdir(os_path):
            raise web.HTTPError(400, u'Not a directory: %s' % (os_path))
        else:
            self.log.debug("Directory %r already exists", os_path)

    def save(self, model, path=''):
        """Save the file model and return the model with no content."""
        path = path.strip('/')

        b, f = self._file_from_path(path)

        if 'type' not in model:
            raise web.HTTPError(400, u'No file type provided')
        if 'content' not in model and model['type'] != 'directory':
            raise web.HTTPError(400, u'No file content provided')

        self.run_pre_save_hook(model=model, path=f.record.id)

        f.setcontent(f.default)

        try:
            if model['type'] == 'notebook':

                nb = nbformat.from_dict(model['content'])
                self.check_and_sign(nb, path)

                # One checkpoint should always exist for notebooks.

                #if not self.checkpoints.list_checkpoints(path):
                #    self.create_checkpoint(path)

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

        self.run_post_save_hook(model=model, os_path=f.record.id)

        self._library.commit()

        return model

    def delete_file(self, path):
        """Delete file at path."""
        raise NotImplementedError()
        path = path.strip('/')
        os_path = self._get_os_path(path)
        rm = os.unlink
        if os.path.isdir(os_path):
            listing = os.listdir(os_path)
            # Don't delete non-empty directories.
            # A directory containing only leftover checkpoints is
            # considered empty.
            cp_dir = getattr(self.checkpoints, 'checkpoint_dir', None)
            for entry in listing:
                if entry != cp_dir:
                    raise web.HTTPError(400, u'Directory %s not empty' % os_path)
        elif not os.path.isfile(os_path):
            raise web.HTTPError(404, u'File does not exist: %s' % os_path)

        if os.path.isdir(os_path):
            self.log.debug("Removing directory %s", os_path)
            with self.perm_to_403():
                shutil.rmtree(os_path)
        else:
            self.log.debug("Unlinking file %s", os_path)
            with self.perm_to_403():
                rm(os_path)

    def rename_file(self, old_path, new_path):
        """Rename a file."""

        raise NotImplementedError()

        old_path = old_path.strip('/')
        new_path = new_path.strip('/')
        if new_path == old_path:
            return

        new_os_path = self._get_os_path(new_path)
        old_os_path = self._get_os_path(old_path)

        # Should we proceed with the move?
        if os.path.exists(new_os_path):
            raise web.HTTPError(409, u'File already exists: %s' % new_path)

        # Move the file
        try:
            with self.perm_to_403():
                shutil.move(old_os_path, new_os_path)
        except web.HTTPError:
            raise
        except Exception as e:
            raise web.HTTPError(500, u'Unknown error renaming file: %s %s' % (old_path, e))

    def info_string(self):
        return "Serving notebooks from local directory: %s" % self.root_dir

    def get_kernel_path(self, path, model=None):
        """Return the initial API path of  a kernel associated with a given notebook"""
        if '/' in path:
            parent_dir = path.rsplit('/', 1)[0]
        else:
            parent_dir = ''
        return parent_dir
