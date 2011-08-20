import itertools
import re
from bisect import insort
from urllib import unquote

from pyramid.interfaces import IRoute
from pyramid.interfaces import IRouteGroup
from pyramid.interfaces import IRoutesMapper

from pyramid.compat import all
from pyramid.encode import url_quote
from pyramid.exceptions import URLDecodeError
from pyramid.traversal import traversal_path
from pyramid.traversal import quote_path_segment
from pyramid.util import join_elements

from zope.interface import implements


_marker = object()

class Route(object):
    implements(IRoute)
    def __init__(self, name, pattern, factory=None, predicates=(),
                 pregenerator=None):
        self.pattern = pattern
        self.path = pattern # indefinite b/w compat, not in interface
        self.match, self.generate, self.args = _compile_route(pattern)
        self.name = name
        self.factory = factory
        self.predicates = predicates
        self.pregenerator = pregenerator

    def gen(self, request, elements, kw):
        if self.pregenerator is not None:
            elements, kw = self.pregenerator(request, elements, kw)

        path = self.generate(kw)

        if elements:
            suffix = join_elements(elements)
            if not path.endswith('/'):
                suffix = '/' + suffix
        else:
            suffix = ''

        return path + suffix, kw

class RouteGroup(object):
    implements(IRouteGroup)
    def __init__(self, name):
        self.name = name
        self.counter = itertools.count(1)
        self.routes = []
        self.sorted_routes = []

    def _match_route(self, request, elements, kw):
        """ Compare the provided keys to the required args of a route.

        The selected route is the first one with all required keys satisfied.
        """
        default_keys = frozenset(kw.keys())
        for entry in self.sorted_routes:
            args, route = entry[2:4]
            if route.pregenerator is not None:
                e, k = route.pregenerator(request, elements[:], dict(kw))
                keys = frozenset(k.keys())
            else:
                e, k, keys = elements, kw, default_keys
            if args.issubset(keys):
                return route, e, k
        raise KeyError('Cannot find matching route in group "%s" using '
                       'provided keys "%s"' % (self.name, sorted(keys)))

    def gen(self, request, elements, kw):
        route, elements, kw = self._match_route(request, elements, kw)

        path = route.generate(kw)

        if elements:
            suffix = join_elements(elements)
            if not path.endswith('/'):
                suffix = '/' + suffix
        else:
            suffix = ''

        return path + suffix, kw

    def add(self, route):
        self.routes.append(route)

        args = frozenset(route.args)
        # -len(args) sorts routes in descending order by the number of args
        entry = (-len(args), next(self.counter), args, route)
        insort(self.sorted_routes, entry)

class RoutesMapper(object):
    implements(IRoutesMapper)
    def __init__(self):
        self.routelist = []
        self.routes = {}
        self.groups = {}

    def has_routes(self):
        return bool(self.routelist)

    def get_routes(self):
        return self.routelist

    def get_groups(self):
        return self.groups

    def get_route(self, name):
        return self.routes.get(name)

    def get_group(self, name):
        return self.groups.get(name)

    def connect(self, name, pattern, factory=None, predicates=(),
                pregenerator=None, static=False):
        route = Route(name, pattern, factory, predicates, pregenerator)
        group = self.get_group(name)
        if group is not None:
            group.add(route)
        else:
            oldroute = self.get_route(name)
            if oldroute in self.routelist:
                self.routelist.remove(oldroute)
            self.routes[name] = route
        if not static:
            self.routelist.append(route)
        return route

    def add_group(self, name):
        oldgroup = self.get_group(name)
        oldroute = self.get_route(name)
        if oldgroup is not None:
            for route in oldgroup.routes:
                if route in self.routelist:
                    self.routelist.remove(route)
        elif oldroute is not None:
            if oldroute in self.routelist:
                self.routelist.remove(oldroute)
        group = RouteGroup(name)
        self.groups[name] = group
        self.routes[name] = group
        return group

    def generate(self, name, kw):
        return self.routes[name].generate(kw)

    def __call__(self, request):
        environ = request.environ
        try:
            # empty if mounted under a path in mod_wsgi, for example
            path = environ['PATH_INFO'] or '/' 
        except KeyError:
            path = '/'

        for route in self.routelist:
            match = route.match(path)
            if match is not None:
                preds = route.predicates
                info = {'match':match, 'route':route}
                if preds and not all((p(info, request) for p in preds)):
                    continue
                return info

        return {'route':None, 'match':None}

# stolen from bobo and modified
old_route_re = re.compile(r'(\:[a-zA-Z]\w*)')
star_at_end = re.compile(r'\*\w*$')

# The torturous nature of the regex named ``route_re`` below is due to the
# fact that we need to support at least one level of "inner" squigglies
# inside the expr of a {name:expr} pattern.  This regex used to be just
# (\{[a-zA-Z][^\}]*\}) but that choked when supplied with e.g. {foo:\d{4}}.
route_re = re.compile(r'(\{[a-zA-Z][^{}]*(?:\{[^{}]*\}[^{}]*)*\})')

def update_pattern(matchobj):
    name = matchobj.group(0)
    return '{%s}' % name[1:]

def _compile_route(route):
    if old_route_re.search(route) and not route_re.search(route):
        route = old_route_re.sub(update_pattern, route)

    if not route.startswith('/'):
        route = '/' + route

    star = None
    if star_at_end.search(route):
        route, star = route.rsplit('*', 1)

    pat = route_re.split(route)
    pat.reverse()
    rpat = []
    gen = []
    prefix = pat.pop() # invar: always at least one element (route='/'+route)
    rpat.append(re.escape(prefix))
    gen.append(prefix)
    args = [] # list of placeholder names in the pattern

    while pat:
        name = pat.pop()
        name = name[1:-1]
        if ':' in name:
            name, reg = name.split(':')
        else:
            reg = '[^/]+'
        args.append(name)
        gen.append('%%(%s)s' % name)
        name = '(?P<%s>%s)' % (name, reg)
        rpat.append(name)
        s = pat.pop()
        if s:
            rpat.append(re.escape(s))
            gen.append(s)

    if star:
        args.append(star)
        rpat.append('(?P<%s>.*?)' % star)
        gen.append('%%(%s)s' % star)

    pattern = ''.join(rpat) + '$'

    match = re.compile(pattern).match
    def matcher(path):
        m = match(path)
        if m is None:
            return m
        d = {}
        for k, v in m.groupdict().iteritems():
            if k == star:
                d[k] = traversal_path(v)
            else:
                encoded = unquote(v)
                try:
                    d[k] = encoded.decode('utf-8')
                except UnicodeDecodeError, e:
                    raise URLDecodeError(
                        e.encoding, e.object, e.start, e.end, e.reason
                        )
                        
                        
        return d
                    

    gen = ''.join(gen)
    def generator(dict):
        newdict = {}
        for k, v in dict.items():
            if isinstance(v, unicode):
                v = v.encode('utf-8')
            if k == star and hasattr(v, '__iter__'):
                v = '/'.join([quote_path_segment(x) for x in v])
            elif k != star:
                try:
                    v = url_quote(v)
                except TypeError:
                    pass
            newdict[k] = v
        return gen % newdict

    return matcher, generator, args

def DefaultsPregenerator(defaults, wrapped=None):
    if wrapped is None:
        wrapped = lambda r, e, k: (e, k)
    def generator(request, elements, kwargs):
        newkw = dict(defaults)
        newkw.update(kwargs)
        return wrapped(request, elements, newkw)
    return generator
