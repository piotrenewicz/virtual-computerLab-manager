import ldap
from proxmoxer import ProxmoxAPI
from data_operations import *

def get_ldap_users(kwargs:(None, dict) = None, clean=True):
    if kwargs is None:
        kwargs = get_config_section(1)
    ldap_conn = ldap.initialize(kwargs['url'])
    ldap_conn.set_option(ldap.OPT_REFERRALS, 0)
    ldap_conn.simple_bind_s('', '')
    result = ldap_conn.search_s(kwargs['base'], ldap.SCOPE_SUBTREE, kwargs['filter'], ["uid","cn"])
    ldap_conn.unbind_s()
    if clean:
        return [( user[1]['uid'][0].decode(), user[1]['cn'][0].decode() ) for user in result]
    return result


def attempt_ldap_login(fullname, password, ldap_params=get_config_section(1)):
    ldap_conn = ldap.initialize(ldap_params['url'])
    ldap_conn.set_option(ldap.OPT_REFERRALS, 0)
    try:
        ldap_conn.simple_bind_s(''.join(('cn=', fullname, ',', ldap_params['base'])), password)
        result = True
    except (ldap.INVALID_CREDENTIALS, ldap.UNWILLING_TO_PERFORM):
        result = False
    finally:
        ldap_conn.unbind_s()
    return result


@with_database
def ldap_sync(cursor: sqlite3.Cursor):
    current_users = get_ldap_users()
    usercount = len(current_users)
    cursor.execute("Create temp table user_sync(userID TEXT PRIMARY KEY, fullname TEXT);")
    cursor.executemany('insert into user_sync(userID, fullname) VALUES (?, ?);', current_users)
    cursor.execute('''
        insert into user_table(userID, fullname) select userID, fullname from user_sync 
        where userID not in (select userID from user_table);
    ''')
    cursor.execute('''
        update user_table
        set fullname = (select fullname from user_sync where userID = user_table.userID) 
        where fullname <> (select fullname from user_sync where userID = user_table.userID);
    ''')
    cursor.execute('''
        select cloneID from clone_table 
        where userID = (select userID from user_table 
                        where userID not in (select userID from user_sync));
    ''')
    remove_clones([row['cloneID'] for row in cursor.fetchall()], cursor=cursor)
    cursor.execute('''
        delete from user_table 
        where userID = (select userID from user_table 
                        where userID not in (select userID from user_sync));
    ''')
    cursor.execute('drop table user_sync')

    # TODO call proxmox to synchronize ldap realm
    cursor.execute('replace into config(option, section, value) VALUES ("ldap_usercount", 3, ?)', (usercount,))
    cursor.execute('replace into config(option, section, value) values ("ldap_syncdate", 3, CURRENT_TIMESTAMP)')


@with_database
def remove_clones(vmid_list: list, cursor: sqlite3.Cursor):
    for vmid in vmid_list:
        # TODO call proxmox to shutdown and remove clone vmid
        cursor.execute('delete from clone_table where cloneID = ?;', (vmid,))
        cursor.execute('delete from vmid_table where vmid = ?;', (vmid,))
