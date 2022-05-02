import time
import ldap
from proxmoxer import ProxmoxAPI, ProxmoxResource, ResourceException  # ResourceException from here is used in main
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
    cursor.execute("Create temp table user_sync(userID TEXT PRIMARY KEY, fullname TEXT)without rowid;")
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
        if get_config_value('user', cursor=cursor) == 'root@pam':
            our_realm = get_config_value('realm', cursor=cursor)
            proxmox.access.domains(our_realm).sync.post(**{'enable-new':0})

    cursor.execute('''
        delete from user_table 
        where userID = (select userID from user_table 
                        where userID not in (select userID from user_sync));
    ''')
    cursor.execute('drop table user_sync')

    cursor.execute('replace into config(option, section, value) VALUES ("ldap_usercount", 3, ?)', (usercount,))
    cursor.execute('replace into config(option, section, value) values ("ldap_syncdate", 3, CURRENT_TIMESTAMP)')
# def end ldap_sync


class proxapi_session(object):
    @with_database
    def __init__(self, path: str = '/', *, cursor: sqlite3.Cursor):
        self.params = get_config_section(2, cursor=cursor)
        self.path = path

    def __enter__(self) -> ProxmoxResource:
        self.proxmox = ProxmoxAPI(**self.params)
        return self.proxmox(self.path)

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass


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


def user_enable(userid, realm, enable=True, *, proxmox: ProxmoxResource):
    proxmox.access.users(userid+"@"+realm).put(enable=int(enable))


@with_database
def sync_proxmox(proxmox: ProxmoxResource, cursor: sqlite3.Cursor):
    current_vms = []
    for found_node in proxmox.nodes.get():
        node_name = found_node['node']
        for found_vm in proxmox.nodes(node_name).qemu.get():
            current_vms.append((found_vm['vmid'], found_vm.get('template', 0), node_name))

    cursor.execute('Create temp table vm_sync(vmid INTEGER PRIMARY KEY, type INTEGER, node TEXT)without rowid;')
    cursor.executemany('insert into vm_sync(vmid, type, node) VALUES (?, ?, ?)', current_vms)

    # step1 compare type 0 with db types 0,
    #       if missing in current, remove (with manual 1:1 cascading into clone_table)
    cursor.execute('delete from clone_table where cloneID not in (select vmid from vm_sync where type = 0);')
    cursor.execute('delete from vmid_table where type = 0 and vmid not in (select vmid from vm_sync where type = 0)')

    # step2 compare type 1 with db type 1,
    #       if not found, remove cascade delete clones and template (call template remove, expect KeyError on proxmox call to remove template)
    cursor.execute('select vmid, node from vmid_table where type = 1 and vmid not in (select vmid from vm_sync where type = 1)')
    remove_templates(cursor.fetchall(), inform_proxmox=False, proxmox=proxmox, cursor=cursor)

    # step1 compare type 0 with db types 0,
    #       if found as any type, but node doesn't match update node, but preserve type.
    # step2 compare type 1 with db type 1,
    #       if node doesn't match update,
    cursor.execute('''
        update vmid_table
        set node = (select node from vm_sync where vm_sync.vmid = vmid_table.vmid)
        where node <> (select node from vm_sync where vm_sync.vmid = vmid_table.vmid)
    ''')

    # step2 compare type 1 with db type 1,
    #       if new add as type 1, insert add (in current data population design, collision here is impossible)
    cursor.execute('''insert into vmid_table(vmid, type, node) select vmid, type, node from vm_sync
            where type = 1 and vmid not in (select vmid from vmid_table)''')
    cursor.execute('drop table vm_sync')

    cursor.execute('''replace into config(option, section, value) values 
        ("proxmox_templatecount", 3, (select count(vmid) from vmid_table where type = 1))''')
    cursor.execute('replace into config(option, section, value) values ("proxmox_syncdate", 3, CURRENT_TIMESTAMP)')
# def end sync_proxmox


@with_database
def remove_templates(template_list: list, inform_proxmox=True, *, proxmox: ProxmoxResource, cursor: sqlite3.Cursor):
    cursor.execute('Create temp table template_removal(templateID, node);')
    cursor.executemany('insert into template_removal(templateID, node) VALUES (?, ?)',
                       [(template['vmid'], template['node']) for template in template_list])
    cursor.execute('''
        select vt.vmid, vt.node 
        from vmid_table vt inner join (
            clone_table ct inner join (
                allocation_table at inner join template_removal tr
                on at.templateID = tr.templateID
            ) sq on ct.allocationID=sq.allocationID
        ) sq2 on vt.vmid=sq2.cloneID
    ''')  # as fun as this is, i bet the final version will get atomized to the point where any joining is unthinkable
    remove_clones(cursor.fetchall(), proxmox=proxmox, cursor=cursor)

    if inform_proxmox:
        for template in template_list:
            proxmox.nodes(template['node']).qemu(template['vmid']).delete()

    cursor.execute('delete from vmid_table where vmid = (select templateID from template_removal);')
    cursor.execute('drop table template_removal;')
