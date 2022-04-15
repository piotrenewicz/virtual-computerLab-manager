from service_utils import *
from flask import session, request, flash
configured = None

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



def active_section(section_id, when_active, when_hidden):
    def is_active(section_id):
        if session.get('config/active_section') is None:
            if section_id == 1:
                return True
            return False
        elif session['config/active_section'] == section_id:
            return True
        return False

    if is_active(section_id):
        return when_active
    return when_hidden



def form_reader(section):
    if section == 1:
        return {
            'host': request.form.get('InputProxmoxAddress'),
            'user': request.form.get('InputProxmoxBotUser'),
            'password': request.form.get('InputProxmoxBotPass'),
            'verify_ssl': 0 if request.form.get('InputProxmoxSSL') is None else 1
        }
    elif section == 2:
        return {
            'url': request.form.get('InputLdapAddress'),
            'base': request.form.get('InputLdapBase'),
            'filter': request.form.get('InputLdapFilter')
        }
    elif section == 4:
        return {
            'userID': request.form.get('InputPermUser'),
            'perm': request.form.get('InputPermPerm')
        }
    elif section == 5:
        return {
            'SECRET_KEY': request.form.get('InputSECRETKEY'),
            'first-run': 0 if request.form.get('InputFirstRun') else 1
        }
    elif section == 'login':
        return {
            'login': request.form.get('InputAppLogin'),
            'pass': request.form.get('InputAppPassword')
        }


def check_proxmox(kwargs):
    try:
        ProxmoxAPI(**kwargs)
    except Exception as e:
        flash(e.__repr__(), 'error')
        return False
    return True


def check_ldap(kwargs):
    try:
        user_count = len(get_ldap_users(kwargs, False))
    except Exception as e:
        flash(e.__repr__(), 'error')
        return False
    if user_count == 0:
        flash("Filter returned 0 users!", 'error')
        return False
    flash("Filter returned {} users!".format(user_count), 'info')
    return True


def validate_connection_params(target):
    kwargs = form_reader(target)
    if target == 1:
        return check_proxmox(kwargs)
    elif target == 2:
        return check_ldap(kwargs)


def perform_login():
    data = form_reader('login')

    with db_session() as cursor:
        cursor.execute('select userPermission from user_table where userID = ?', (data['login'],))
        perm = one_row_fix(cursor.fetchone())
        cursor.execute('select fullname from user_table where userID = ?', (data['login'],))
        cn = one_row_fix(cursor.fetchone())
        ldap_params = get_config_section(2, cursor=cursor)

    if perm is None:
        flash('Podany [login] i/lub hasło są nieprawidłowe', 'info')
        return False

    if perm in (0, 1):
        flash('Brak Uprawnień, Odmowa Dostępu', 'error')
        return False

    if perm in (2, 3, 4) and attempt_ldap_login(cn, data['pass'], ldap_params=ldap_params):
        flash('logged in', 'success')
        session['login'] = data['login']
        session['permLevel'] = perm
        return True

    flash('Podany login i/lub [hasło] są nieprawidłowe', 'info')
    return False


