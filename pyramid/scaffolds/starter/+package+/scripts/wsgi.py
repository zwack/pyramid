import os
import sys

wsgi_template = """import os

from pyramid.paster import get_app

INIFILE = os.path.join(os.path.dirname(__file__), 'production.ini')
application = get_app(INIFILE, 'main')

"""

apache_template = """### The following configuration can be pasted into apache config.
### Please adjust your DOMAIN, USER and GROUP.

<VirtualHost *:80>
    ServerName DOMAIN.COM

    # Let apache serve the static files
    # Alias /static/ {static}/

    # Use only 1 Python sub-interpreter.  Multiple sub-interpreters
    # play badly with C extensions.
    WSGIApplicationGroup %{{GLOBAL}}
    WSGIPassAuthorization On
    WSGIDaemonProcess pyramid user=USER group=GROUP threads=4 \\
       python-path={virtualenv}/lib/python2.7/site-packages
    WSGIScriptAlias / {root}/app.wsgi
</VirtualHost>
<Directory {root}>
    Order allow,deny
    Options Indexes
    Allow from all
</Directory>

"""


def create_file(argv=sys.argv):
    try:
        wsgi_name = sys.argv[1]
    except IndexError:
        cmd = os.path.basename(argv[0])
        print('usage: {0} <wsgi_file>\n'
              '(example: "{0} app.wsgi")'.format(cmd))
        sys.exit(1)

    wsgi_file = os.path.join(os.getcwd(), wsgi_name)
    f = open(wsgi_file, 'w')
    f.write(wsgi_template)
    f.close()

    if os.name == 'posix':
        os.chmod(wsgi_file, 755)

def stdout_apache_config(argv=sys.argv):
    try:
        virtualenv_dir = os.path.join(os.getcwd(), sys.argv[1])
    except IndexError:
        print('usage: {0} <virtualenv>'.format(os.path.basename(argv[0])))
        sys.exit(1)

    if not os.path.isfile(os.path.join(virtualenv_dir, 'bin/python')):
        print('error: python interpreter not found in {0}!'.format(
            virtualenv_dir))
        sys.exit(1)

    app_dir = os.path.dirname(os.path.dirname(__file__))
    static_dir = os.path.join(app_dir, 'static')
    print apache_template.format(root=os.path.dirname(app_dir),
                                 virtualenv=virtualenv_dir,
                                 static=static_dir)
