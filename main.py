import utils as u
from flask import Flask, render_template, request, url_for, flash, redirect, session
from werkzeug.exceptions import abort


app = Flask(__name__)
configured = u.check_configured()
app.config['SECRET_KEY'] = u.get_config_value('SECRET_KEY') or "DEFAULT SECRET KEY. NOT VERY SECRET"


@app.context_processor
def inject_default_context():
    return dict(
        toast_category_map = {
            'error': 'bg-danger bg-opacity-75 text-light',
            'info': 'bg-warning bg-opacity-75',
            'success': 'bg-success bg-opacity-75 text-light',
        },

    )

@app.before_request
def check_method():
    if request.method not in ('POST', 'GET'):
        request.method = 'POST' if request.method.endswith('POST') else 'GET'


@app.route('/')
def index():
    if not configured:
        return redirect(url_for('configuration'))
    else:
        return redirect(url_for('login'))
    # so this will be a redirector, it will usually throw people into /login
    # if we don't have a database it will create one and throw into setup.


@app.route('/config', methods=('GET', 'POST'))
def configuration():
    if configured:
        #require login, to protect the settings from tampering
        # we can't login before configured bc ldap is not set.
        # deleagate this check to app.before_request
        pass

    # print(request.form)
    with u.db_session() as cursor:
        config_sections = [u.get_config_section(section=section_number, cursor=cursor) for section_number in range(6)]
        config_sections[4]['all_users'] = u.get_users(None, cursor=cursor)
        config_sections[4]['teachers'] = u.get_users(2, cursor=cursor)
        config_sections[4]['maintainers'] = u.get_users(3, cursor=cursor)
        config_sections[4]['admins'] = u.get_users(4, cursor=cursor)
    config_sections[5]['configured'] = configured

    return render_template('config.html', config_sections=config_sections, active_section=u.active_section)


@app.route('/config/check_connection/<int:target>', methods=('POST',))
def check_connection(target):
    session['config/active_section'] = target
    session['check/'+str(target)] = u.validate_connection_params(target)
    return redirect(request.referrer, code=307)


@app.route('/config/save/<int:target>', methods=('POST',))
def save(target):
    if u.validate_connection_params(target):
        data = [(option, target, value) for option, value in u.form_reader(target).items()]
        with u.db_session() as cursor:
            cursor.executemany("replace into config(option, section, value) VALUES (?, ?, ?)", data)
        flash("Settings saved!", 'success')
        session['config/active_section'] = target + 1
    else:
        session['check/'+str(target)] = False
        session['config/active_section'] = target
    return redirect(request.referrer, code=307)

@app.route('/config/sync/<int:target>', methods=('POST',))
def sync_database(target):
    session['config/active_section'] = 3
    if target == 1:
        # proxmox_sync()
        pass
    elif target == 2:
        u.ldap_sync()

    return redirect(request.referrer, code=307)

@app.route('/config/set_permission', methods=('POST',))
def set_permission():
    session['config/active_section'] = 4
    data = u.form_reader(4)
    print(data)
    with u.db_session() as cursror:
        if session['config/setPermType'] == 2:
            cursror.execute('select userID from user_table where fullname = ?', (data['userID'],))
            data['userID'] = u.one_row_fix(cursror.fetchone())

        if data['perm'] == 0:
            cursror.execute('select count(groupID) from group_content where userID = ?', (data['userID'],))
            if u.one_row_fix(cursror.fetchone()) > 0:
                data['perm'] = 1

        cursror.execute('update user_table set userPermission = ? where userID = ?', (data['perm'], data['userID']))

    if data['perm']:
        # TODO call proxmox to enable account data['userID']
        pass
    else:
        # TODO call proxmox to disable account data['userID']
        pass

    return redirect(request.referrer, code=307)

@app.route('/config/set_permission/<int:handle_type>', methods=('POST',))
def set_permission_by(handle_type):
    session['config/active_section'] = 4
    session['config/setPermType'] = handle_type
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
