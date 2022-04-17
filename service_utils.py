import time

import ldap
from proxmoxer import ProxmoxAPI, ProxmoxResource
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
        select vmid, node from vmid_table where vmid = (
            select cloneID from clone_table 
            where userID = (
                select userID from user_table 
                where userID not in (
                    select userID from user_sync
                )
            )
        );
    ''')

    with proxapi_session(cursor=cursor) as proxmox:
        remove_clones(cursor.fetchall(), proxmox=proxmox, cursor=cursor)
        our_realm = get_config_value('realm', cursor=cursor)
        proxmox.access.domain(our_realm).sync.post(**{'enable-new':0})

    cursor.execute('''
        delete from user_table 
        where userID = (select userID from user_table 
                        where userID not in (select userID from user_sync));
    ''')
    cursor.execute('drop table user_sync')

    cursor.execute('replace into config(option, section, value) VALUES ("ldap_usercount", 3, ?)', (usercount,))
    cursor.execute('replace into config(option, section, value) values ("ldap_syncdate", 3, CURRENT_TIMESTAMP)')


class proxapi_session(object): # use nesting, have a proxmox security wrapper double with this one throws on enter, external with will catch as exit skip block and flash
    @with_database
    def __init__(self, path = '/', *, cursor:sqlite3.Cursor):
        self.params = get_config_section(2, cursor=cursor)
        self.path = path

    def __enter__(self):
        self.proxmox = ProxmoxAPI(**self.params)
        return self.proxmox(self.path)

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass

#
# # I don't like the following bit of code, proxmoxResource could be of any path, No decoration here, let's just require a session
# def with_proxapi(function_or_path):
#     path = function_or_path if type(function_or_path) == str else '/'
#     def decorator(function):
#         def wrapped(*args, **kwargs):
#             if kwargs.get('proxmox') == ProxmoxResource:
#                 return function(*args, **kwargs)
#
#             with proxapi_session(path) as proxmox:
#                 result = function(*args, **kwargs, proxmox=proxmox)
#             return result
#
#         return wrapped
#
#     return decorator if type(function_or_path) == str else decorator(function_or_path)



@with_database
def remove_clones(clone_list: list, proxmox: ProxmoxResource, cursor: sqlite3.Cursor):
    shutdown_clones(clone_list, block=True, proxmox=proxmox)

    for clone in clone_list:
        proxmox.nodes(clone['node']).qemu(clone['vmid']).delete()

        cursor.execute('delete from clone_table where cloneID = ?;', (clone['vmid'],))
        cursor.execute('delete from vmid_table where vmid = ?;', (clone['vmid'],))


def shutdown_clones(clone_list: list, block=False, *, proxmox: ProxmoxResource):
    for clone in clone_list:
        proxmox.nodes(clone['node']).qemu(clone['vmid']).status.shutdown.post()

    if block:  # if we want to wait for shutdown
        done = False  # assume we are not done, as we haven't checked
        while not done:  # keep trying
            time.sleep(2) # give the clones some time to attempt shutdown.
            done = True  # hope that we are done.
            for clone in clone_list:  # check all clones
                clone_link = proxmox.nodes(clone['node']).qemu(clone['vmid'])
                if clone_link.status.current.get()['status'] == 'running':  # when clones are still running
                    clone_link.status.shutdown.post()  # order shutdown again
                    done = False  # and lose hope that we are done already.


def user_enable(userid, enable = True, *, proxmox: ProxmoxResource):
    proxmox.access.users(userid).put(enable=int(enable))