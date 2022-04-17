import utils as u
from flask import Blueprint, render_template, request, flash, redirect, session
config_app = Blueprint('config', __name__, template_folder='templates')


@config_app.route('/config', methods=('GET', 'POST'))
def configuration():
    with u.db_session() as cursor:
        config_sections = [u.get_config_section(section=section_number, cursor=cursor) for section_number in range(6)]
        config_sections[4]['all_users'] = u.get_users(None, cursor=cursor)
        config_sections[4]['teachers'] = u.get_users(2, cursor=cursor)
        config_sections[4]['maintainers'] = u.get_users(3, cursor=cursor)
        config_sections[4]['admins'] = u.get_users(4, cursor=cursor)
    config_sections[5]['configured'] = u.configured

    return render_template('config.html', config_sections=config_sections, active_section=u.active_section)


@config_app.route('/config/check_connection/<int:target>', methods=('POST',))
def check_connection(target):
    session['config/active_section'] = target
    session['check/'+str(target)] = u.validate_connection_params(target)
    return redirect(request.referrer, code=307)


@config_app.route('/config/save/<int:target>', methods=('POST',))
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

@config_app.route('/config/sync/<int:target>', methods=('POST', 'GET'))  # VM Maintainers, trigger this from account menu, which can't make POST requests.
def sync_database(target):
    session['config/active_section'] = 3
    match target:
        case 1: u.ldap_sync()
        case 2:
            with u.db_session() as cursor, u.proxapi_session(cursor=cursor) as proxmox:
                u.sync_proxmox(cursor=cursor, proxmox=proxmox)

    return redirect(request.referrer, code=307)

@config_app.route('/config/set_permission', methods=('POST',))
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

        with u.proxapi_session(cursor=cursror) as proxmox:
            u.user_enable(data['userID'], realm=u.get_config_value('realm', cursor=cursror), enable=data['perm'] > 0, proxmox=proxmox)

    return redirect(request.referrer, code=307)

@config_app.route('/config/set_permission/<int:handle_type>', methods=('POST',))
def set_permission_by(handle_type):
    session['config/active_section'] = 4
    session['config/setPermType'] = handle_type
    return redirect(request.referrer, code=307)

@config_app.route('/config/finish', methods=('POST',))
def confirm_and_lock():
    if not session.get('permLevel') == 4:
        flash('Permission Missing', 'error')
        return redirect(request.referrer)

    data = u.form_reader(5)
    with u.db_session() as cursor:
        if not data['SECRET_KEY'] in (None,''):
            cursor.execute("replace into config(option, section, value) VALUES ('SECRET_KEY', 5, ?)", (data['SECRET_KEY'],))
            flash('SECRET_KEY updated', 'info')
        cursor.execute("replace into config(option, value) VALUES ('first-run', ?)", (data['first-run'],))

    flash("Settings saved!", 'success')
    session['config/active_section'] = 5
    flash("Restart the web server for settings to take effect!", 'info')
    request.get_data() # clearing form data just in case
    return redirect(request.referrer)