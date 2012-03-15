import os
import sys

template = """import os
# when using virtualenv you would need to add it's packages like this:
# import site
# site.addsitedir('venv/lib/python2.7/site-packages')

from pyramid.paster import get_app

INIFILE = os.path.join(os.path.dirname(__file__), 'production.ini')
application = get_app(INIFILE, 'main')

"""


def main(argv=sys.argv):
    try:
        wsgi_name = sys.argv[1]
    except IndexError:
        cmd = os.path.basename(argv[0])
        print('usage: {0} <wsgi_file>\n'
              '(example: "{0} app.wsgi")'.format(cmd, cmd))
        sys.exit(1)

    wsgi_file = os.path.join(os.getcwd(), wsgi_name)
    f = open(wsgi_file, 'w')
    f.write(template)
    f.close()

    if os.name == 'posix':
        os.chmod(wsgi_file, 755)
