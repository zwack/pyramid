import os
import pkg_resources
import sys

from zope.interface import implementer

from pyramid.interfaces import IPackageOverrides

from pyramid.exceptions import ConfigurationError
from pyramid.threadlocal import get_current_registry

from pyramid.config.util import action_method

class OverrideProvider(pkg_resources.DefaultProvider):
    def __init__(self, module):
        pkg_resources.DefaultProvider.__init__(self, module)
        self.module_name = module.__name__

    def _get_overrides(self):
        reg = get_current_registry()
        overrides = reg.queryUtility(IPackageOverrides, self.module_name)
        return overrides

    def get_resource_filename(self, manager, resource_name):
        """ Return a true filesystem path for resource_name,
        co-ordinating the extraction with manager, if the resource
        must be unpacked to the filesystem.
        """
        overrides = self._get_overrides()
        if overrides is not None:
            for override in overrides:
                filename = override.get_filename(resource_name)
                if filename is not None:
                    return filename
        return pkg_resources.DefaultProvider.get_resource_filename(
            self, manager, resource_name)

    def get_resource_stream(self, manager, resource_name):
        """ Return a readable file-like object for resource_name."""
        overrides = self._get_overrides()
        if overrides is not None:
            for override in overrides:
                stream =  override.get_stream(resource_name)
                if stream is not None:
                    return stream
        return pkg_resources.DefaultProvider.get_resource_stream(
            self, manager, resource_name)

    def get_resource_string(self, manager, resource_name):
        """ Return a string containing the contents of resource_name."""
        overrides = self._get_overrides()
        if overrides is not None:
            for override in overrides:
                string = override.get_string(resource_name)
                if string is not None:
                    return string
        return pkg_resources.DefaultProvider.get_resource_string(
            self, manager, resource_name)

    def has_resource(self, resource_name):
        overrides = self._get_overrides()
        if overrides is not None:
            for override in overrides:
                result = override.has_resource(resource_name)
                if result is not None:
                    return result
        return pkg_resources.DefaultProvider.has_resource(
            self, resource_name)

    def resource_isdir(self, resource_name):
        overrides = self._get_overrides()
        if overrides is not None:
            for override in overrides:
                result = override.isdir(resource_name)
                if result is not None:
                    return result
        return pkg_resources.DefaultProvider.resource_isdir(
            self, resource_name)

    def resource_listdir(self, resource_name):
        overrides = self._get_overrides()
        if overrides is not None:
            for override in overrides:
                result = override.listdir(resource_name)
                if result is not None:
                    return result
        return pkg_resources.DefaultProvider.resource_listdir(
            self, resource_name)

@implementer(IPackageOverrides)
class PackageOverrides:
    # pkg_resources arg in kw args below for testing
    def __init__(self, package, pkg_resources=pkg_resources):
        if hasattr(package, '__loader__') and not isinstance(package.__loader__,
                                                             self.__class__):
            raise TypeError('Package %s already has a non-%s __loader__ '
                            '(probably a module in a zipped egg)' %
                            (package, self.__class__))
        # We register ourselves as a __loader__ *only* to support the
        # setuptools _find_adapter adapter lookup; this class doesn't
        # actually support the PEP 302 loader "API".  This is
        # excusable due to the following statement in the spec:
        # ... Loader objects are not
        # required to offer any useful functionality (any such functionality,
        # such as the zipimport get_data() method mentioned above, is
        # optional)...
        # A __loader__ attribute is basically metadata, and setuptools
        # uses it as such.
        package.__loader__ = self
        # we call register_loader_type for every instantiation of this
        # class; that's OK, it's idempotent to do it more than once.
        pkg_resources.register_loader_type(self.__class__, OverrideProvider)
        self.overrides = []
        self.overridden_package_name = package.__name__

    def insert(self, path, pkg_or_path, prefix):
        override = make_override(path, pkg_or_path, prefix)
        self.overrides.insert(0, override)
        return override

    def __iter__(self):
        return iter(self.overrides)


def make_override(path, pkg_or_path, prefix):
    if isinstance(pkg_or_path, basestring):
        return FSOverride(path, pkg_or_path)
    return PKGOverride(path, pkg_or_path, prefix)


class PKGOverride:
    def __init__(self, path, package, prefix):
        self.path = path
        self.package = package
        self.prefix = prefix
        self.pathlen = len(self.path)

    def resolve(self, resource_name):
        path = self.path
        if not path or path.endswith('/'):
            if resource_name.startswith(path):
                name = '%s%s' % (self.prefix, resource_name[self.pathlen:])
                if pkg_resources.resource_exists(self.package, name):
                    return self.package, name
        elif resource_name == path:
            return self.package, self.prefix

    def get_filename(self, resource_name):
        resolution = self.resolve(resource_name)
        if resolution:
            package, rname = resolution
            return pkg_resources.resource_filename(package, rname)

    def get_stream(self, resource_name):
        resolution = self.resolve(resource_name)
        if resolution:
            package, rname = resolution
            return pkg_resources.resource_stream(package, rname)

    def get_string(self, resource_name):
        resolution = self.resolve(resource_name)
        if resolution:
            package, rname = resolution
            return pkg_resources.resource_string(package, rname)

    def has_resource(self, resource_name):
        return self.resolve(resource_name) is not None

    def isdir(self, resource_name):
        resolution = self.resolve(resource_name)
        if resolution:
            package, rname = resolution
            return pkg_resources.resource_isdir(package, rname)

    def listdir(self, resource_name):
        resolution = self.resolve(resource_name)
        if resolution:
            package, rname = resolution
            return pkg_resources.resource_listdir(package, rname)


class FSOverride:
    def __init__(self, path, override_path):
        self.path = path
        self.override_path = override_path
        self.pathlen = len(self.path)

    def resolve(self, resource_name):
        path = self.path
        if not path or path.endswith('/'):
            if resource_name.startswith(path):
                fpath = os.path.join(
                    self.override_path, resource_name[self.pathlen:])
                if os.path.exists(fpath):
                    return fpath
        elif resource_name == path:
            return self.override_path

    def get_filename(self, resource_name):
        return self.resolve(resource_name)

    def get_stream(self, resource_name):
        resolution = self.resolve(resource_name)
        if resolution:
            return open(resolution, 'rb')

    def get_string(self, resource_name):
        resolution = self.resolve(resource_name)
        if resolution:
            with open(resolution, 'rb') as f:
                return f.read()

    def has_resource(self, resource_name):
        resolution = self.resolve(resource_name)
        if resolution:
            return True

    def isdir(self, resource_name):
        resolution = self.resolve(resource_name)
        if resolution:
            return os.path.isdir(self.resolve(resource_name))

    def listdir(self, resource_name):
        resolution = self.resolve(resource_name)
        if resolution:
            return os.listdir(resolution)


class AssetsConfiguratorMixin(object):
    def _override(self, package, path, override_package, override_prefix,
                  PackageOverrides=PackageOverrides):
        pkg_name = package.__name__
        if isinstance(override_package, basestring):
            override_pkg_name = override_package
        else:
            override_pkg_name = override_package.__name__
        overrides = self.registry.queryUtility(IPackageOverrides, name=pkg_name)
        if overrides is None:
            overrides = PackageOverrides(package)
            self.registry.registerUtility(overrides, IPackageOverrides,
                                          name=pkg_name)
        overrides.insert(path, override_pkg_name, override_prefix)

    @action_method
    def override_asset(self, to_override, override_with, _override=None):
        """ Add a :app:`Pyramid` asset override to the current
        configuration state.

        ``to_override`` is a :term:`asset specification` to the
        asset being overridden.

        ``override_with`` is a :term:`asset specification` to the
        asset that is performing the override.

        See :ref:`assets_chapter` for more
        information about asset overrides."""
        if to_override == override_with:
            raise ConfigurationError('You cannot override an asset with itself')

        package = to_override
        path = ''
        if ':' in to_override:
            package, path = to_override.split(':', 1)

        override_package = override_with
        override_prefix = ''
        if ':' in override_with:
            override_package, override_prefix = override_with.split(':', 1)
        # *_isdir = override is package or directory
        is_filesystem = override_package.startswith('/')
        overridden_isdir = path=='' or path.endswith('/')
        if is_filesystem:
            override_isdir = override_prefix.endswith('/')
        else:
            override_isdir = (override_prefix=='' or
                              override_prefix.endswith('/'))

        if overridden_isdir and (not override_isdir):
            raise ConfigurationError(
                'A directory cannot be overridden with a file (put a '
                'slash at the end of override_with if necessary)')

        if (not overridden_isdir) and override_isdir:
            raise ConfigurationError(
                'A file cannot be overridden with a directory (put a '
                'slash at the end of to_override if necessary)')

        override = _override or self._override # test jig

        def register():
            __import__(package)
            from_package = sys.modules[package]
            if is_filesystem:
                to_package = override_package
            else:
                __import__(override_package)
                to_package = sys.modules[override_package]
            override(from_package, path, to_package, override_prefix)

        self.action(None, register)

    override_resource = override_asset # bw compat


