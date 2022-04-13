import sqlite3
from flask import Flask, render_template, request, url_for, flash, redirect, session
from werkzeug.exceptions import abort
from proxmoxer import ProxmoxAPI


def one_row_fix(row: (sqlite3.Row, None)):
    if row is None:
        return None
    if len(row.keys()) == 1:
        return row[0]
    return dict(row)


def get_config_section(section: int):
    conn = get_db_connection()
    rowset = conn.cursor().execute('select option, value from config where section == ?', (section,)).fetchall()
    config_section = {row['option']: row['value'] for row in rowset}
    conn.close()
    return config_section


def get_config_value(option: str):
    conn = get_db_connection()
    value = one_row_fix(conn.cursor().execute('select value from config where option == ?', (option,)).fetchone())
    conn.close()
    return value


def get_db_connection():
    conn = sqlite3.connect('database.db')
    conn.row_factory = sqlite3.Row
    return conn


def check_configured():
    try:
        first_run = get_config_value('first-run')
    except sqlite3.OperationalError:
        first_run = None
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
app.config['SECRET_KEY'] = get_config_value('SECRET_KEY') or "DEFAULT SECRET KEY. NOT VERY SECRET"


@app.context_processor
def inject_default_context():
    return dict(
        toast_category_map = {
            'error': 'bg-danger bg-opacity-75 text-light',
            'info': 'bg-info',
            'success': 'bg-success bg-opacity-75 text-light'
        },

    )

@app.route('/')
def index():
    if not configured:
        return redirect(url_for('configuration'))
    else:
        return redirect(url_for('login'))
    # so this will be a redirector, it will usually throw people into /login
    # if we don't have a database it will create one and throw into setup.


@app.route('/config', methods=('GET', 'POST'))
def configuration(**kwargs):
    if configured:
        #require login, to protect the settings from tampering
        # we can't login before configured bc ldap is not set.
        pass

    config_sections = [get_config_section(section=section_number) for section_number in range(4)]

    return render_template('config.html', config_sections=config_sections, more_context=kwargs)


def form_reader(section):
    if section == 1:
        return {
            'host': request.form.get('InputProxmoxAddress'),
            'user': request.form.get('InputProxmoxBotUser'),
            'password': request.form.get('InputProxmoxBotPass'),
            'verify_ssl': False if request.form.get('InputProxmoxSSL') is None else True
        }
    elif section == 2:
        return {}


def check_proxmox(kwargs):
    try:
        ProxmoxAPI(**kwargs)
    except Exception as e:
        flash(e.__repr__(), 'error')
        return False
    return True


def check_ldap(kwargs):
    return False


def check_both(target):
    kwargs = form_reader(target)
    if target == 1:
        return check_proxmox(kwargs)
    elif target == 2:
        return check_ldap(kwargs)


@app.route('/config/check_connection/<int:target>', methods=('POST',))
def check_connection(target):
    session['check/'+str(target)] = check_both(target)
    return redirect(request.referrer, code=307)


@app.route('/config/save/<int:target>', methods=('POST',))
def save(target):
    if check_both(target):
        conn = get_db_connection()
        cur = conn.cursor()
        data = [(option, target, value) for option, value in form_reader(target).items()]
        cur.executemany("replace into config(option, section, value) VALUES (?, ?, ?)", data)
        conn.commit()
        conn.close()
        flash("Settings saved!", 'success')
    else:
        session['check/'+str(target)] = False
    return redirect(request.referrer, code=307)


@app.route('/login')
def login():
    return render_template('login.html')


# when shipping remember to put a block here, we don't want to allow production use of development mode
if __name__ == "__main__":
    def get_ip():
        import socket
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    app.env = "development"
    app.run(host=get_ip(), port=5000, debug=True)
