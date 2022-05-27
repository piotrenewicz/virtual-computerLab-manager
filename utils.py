from service_utils import *
from flask import session, request, flash
configured = None


def check_configured():
    try:
        first_run = get_config_value('first-run')
    except sqlite3.OperationalError:
        first_run = None
    match first_run:
        case None:
            import init_database
            init_database.init()
            return False
        case 1: return False
        case 0: return True
        case _: raise Exception("Non-binary first-run value!")


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
    match section:
        case 1:
            return {
                'url': request.form.get('InputLdapAddress'),
                'base': request.form.get('InputLdapBase'),
                'filter': request.form.get('InputLdapFilter'),
                'realm': request.form.get('InputLdapRealm')
            }
        case 2:
            return {
                'host': request.form.get('InputProxmoxAddress'),
                'user': request.form.get('InputProxmoxUser'),
                'password': request.form.get('InputProxmoxPass'),
                'verify_ssl': 0 if request.form.get('InputProxmoxSSL') is None else 1
            }
        case 4:
            return {
                'userID': request.form.get('InputUser'),
                'perm': int(request.form.get('InputPerm'))
            }
        case 5:
            return {
                'SECRET_KEY': request.form.get('InputSECRETKEY'),
                'first-run': 0 if request.form.get('InputFirstRun') else 1
            }
        case 'login':
            return {
                'login': request.form.get('InputAppLogin'),
                'pass': request.form.get('InputAppPassword')
            }
        case 'search':
            return {
                'search': request.form.get('InputSearch')
            }
        case 'alloc':
            return {
                'alloc_name': request.form.get('InputAllocName'),
                'template': int(request.form.get('InputAllocTemplate')),
                'expire': int(request.form.get('InputAllocExpireN')) * int(request.form.get('InputAllocExpireT'))
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
    match target:
        case 1: return check_ldap(kwargs)
        case 2: return check_proxmox(kwargs)


def perform_login():
    data = form_reader('login')

    with db_session() as cursor:
        cursor.execute('select userPermission from user_table where userID = ?', (data['login'],))
        perm = one_row_fix(cursor.fetchone())
        cursor.execute('select fullname from user_table where userID = ?', (data['login'],))
        cn = one_row_fix(cursor.fetchone())
        ldap_params = get_config_section(1, cursor=cursor)

    match perm:
        case None: flash('Podany login i/lub hasło są nieprawidłowe', 'info')
        case (0 | 1): flash('Brak Uprawnień, Odmowa Dostępu', 'error')
        case (2 | 3 | 4):
            if attempt_ldap_login(cn, data['pass'], ldap_params=ldap_params):
                flash('logged in', 'success')
                session['login'] = data['login']
                session['permLevel'] = perm
                return True
            else:
                flash('Podany login i/lub hasło są nieprawidłowe', 'info')
        case _: flash('login error', 'error')
    return False


@with_database
def auto_disable_users(proxmox: ProxmoxResource, cursor: sqlite3.Cursor):
    realm = get_config_value('realm', cursor=cursor)
    cursor.execute('select userID from user_table where userPermission = -1')
    for user in cursor.fetchall():
        cursor.execute('select count(groupID) from group_content where userID = ?', (user['userID'],))
        account_status = one_row_fix(cursor.fetchone()) > 0
        user_enable(user['userID'], realm, enable=account_status, proxmox=proxmox)
        cursor.execute('update user_table set userPermission = ? where userID = ?',
                       (1 if account_status else 0, user['userID']))
