import sqlite3
from flask import Flask, render_template, request, url_for, flash, redirect
from werkzeug.exceptions import abort


def get_db_connection():
    conn = sqlite3.connect('database.db')
    conn.row_factory = sqlite3.Row
    return conn


def check_configured():
    conn = get_db_connection()
    try:
        first_run = conn.cursor().execute("SELECT value from config where option == 'first-run'").fetchone()[0]
    except sqlite3.OperationalError:
        first_run = None
    conn.close()
    if first_run is None:
        import init_database
        init_database.init()
        return False
    elif first_run == 1:
        return False
    elif first_run == 0:
        return True
    else:
        raise Exception("Non-binary first-run value!")


app = Flask(__name__)
configured = check_configured()
if configured:
    conn = get_db_connection()
    app.config['SECRET_KEY'] = conn.cursor().execute(
        "SELECT value from config where option == 'SECRET_KEY'"
        ).fetchone()[0]
    conn.close()


@app.route('/')
def entry_point():
    if not configured:
        return redirect(url_for('configuration'))
    else:
        return redirect(url_for('login'))
    # so this will be a redirector, it will usually throw people into /login
    # if we don't have a database it will create one and throw into setup.


@app.route('/config')
def configuration():
    if configured:
        #require login, to protect the settings from tampering
        # we can't login before configured bc ldap is not set.
        pass
    return 'Placeholder'


@app.route('/login')
def login():
    return 'Placeholder'


# when shipping remember to put a block here, we don't want to allow production use of development mode
if __name__ == "__main__":
    def get_ip():
        import socket
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    app.env = "development"
    app.run(host=get_ip(), port=5000, debug=True)
