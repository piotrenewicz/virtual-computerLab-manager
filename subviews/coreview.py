import utils as u
from flask import Blueprint, render_template, request, redirect, session, url_for


core_app = Blueprint('core', __name__, template_folder='templates')


@core_app.route('/group-overview', methods=('GET', 'POST'))
def group_list():
    search = '%'
    if request.method == 'POST':
        search = f'%{u.form_reader("search")["search"]}%'
    with u.db_session() as cursor:
        cursor.execute('select groupID, groupName from group_table where groupName like ?', (search,))
        groups = cursor.fetchall()

    return render_template('overview.html', groups=groups)


@core_app.route('/group/<int:group_id>/', methods=('POST', 'GET'))
def group_edit(group_id: int):
    context = {'id': group_id}
    with u.db_session() as cursor:
        if request.method == 'POST':
            cursor.execute('update group_table set groupName = ? where groupID = ?',
                           (request.form.get('InputGroupName'), group_id))
        context['name'] = u.get_group_name(group_id, cursor=cursor)
        cursor.execute('select count(groupID) from group_content where groupID = ?', (group_id,))
        context['member_count'] = u.one_row_fix(cursor.fetchone())
        cursor.execute('select count(groupID) from allocation_table where groupID = ?', (group_id,))
        context['alloc_count'] = u.one_row_fix(cursor.fetchone())

    pwd = [("Grupa:"+context['name'], '#')]

    return render_template('group.html', context=context, pwd=pwd)


@core_app.route('/group-new/')
def add_group():
    with u.db_session() as cursor:
        cursor.execute("insert into group_table(groupName) values ('Error') RETURNING groupID;")
        new_id = u.one_row_fix(cursor.fetchone())
        cursor.execute('update group_table set groupName = ? where groupID = ?',
                       (f"Grupa{new_id}", new_id))

    return redirect(url_for('core.group_edit', group_id=new_id))


@core_app.route('/group/<int:group_id>/remove/')
def remove_group(group_id: int):
    with u.db_session() as cursor:
        cursor.execute('''update user_table set userPermission = -1 where userPermission = 1 and userID = (
            select userID from group_content where groupID = ?)''', (group_id,))

        cursor.execute('''
            select vt.vmid, node from vmid_table vt inner join clone_table ct on vt.vmid = ct.cloneID
            where ct.allocationID = (select allocationID from allocation_table where groupID = ?)
        ''', (group_id,))

        with u.proxapi_session(cursor=cursor) as proxmox:
            u.remove_clones(cursor.fetchall(), proxmox=proxmox, cursor=cursor)
            cursor.execute('delete from group_table where groupID = ?', (group_id,))
            u.auto_disable_users(proxmox=proxmox, cursor=cursor)

    return redirect(request.root_url)


@core_app.route('/group/<int:group_id>/members/')
def user_list(group_id: int):
    context = {'group_id': group_id}
    with u.db_session() as cursor:
        context['group_name'] = u.get_group_name(group_id, cursor=cursor)
        cursor.execute('''
            select ut.userID, fullname 
            from user_table ut inner join (
                select userID from group_content where groupID = ?
            ) gc on ut.userID = gc.userID
        ''', (group_id,))

        context['group_members'] = cursor.fetchall()
        cursor.execute('''
            select userID, fullname from user_table where userID not in (
                select userID from group_content where groupID = ?
            )
        ''', (group_id,))
        context['remainder'] = cursor.fetchall()

    pwd = [
        ("Grupa:"+context['group_name'], url_for('core.group_edit', group_id=group_id)),
        ("Osoby", '#')
    ]
    return render_template('users.html', context=context, pwd=pwd)


@core_app.route('/group/<int:group_id>/members/<string:user_id>/remove/')
def remove_user(group_id: int, user_id: str):
    with u.db_session() as cursor:
        cursor.execute('''
            update user_table set userPermission = -1
            where userID = ? and userPermission = 1
        ''', (user_id,))

        cursor.execute('''
            select vt.vmid, node from vmid_table vt inner join clone_table ct on vt.vmid = ct.cloneID
            where ct.allocationID = (select allocationID from allocation_table where groupID = ?)
            and ct.userID = ?
        ''', (group_id, user_id))

        with u.proxapi_session(cursor=cursor) as proxmox:
            u.remove_clones(cursor.fetchall(), proxmox=proxmox, cursor=cursor)
            cursor.execute('delete from group_content where userID = ? and groupID = ?',
                           (user_id, group_id))
            u.auto_disable_users(proxmox=proxmox, cursor=cursor)
    return redirect(request.referrer or '/')


@core_app.route('/group/<int:group_id>/members/add/', methods=('POST',))
def add_user(group_id: int):
    user_id = request.form.get('InputUser')
    if user_id:
        with u.db_session() as cursor:
            if not session.get('preferUserQuery'):
                cursor.execute('select userID from user_table where fullname = ?', (user_id,))
                user_id = u.one_row_fix(cursor.fetchone())

            cursor.execute('insert into group_content(groupID, userID) values (?, ?)', (group_id, user_id))
            cursor.execute('update user_table set userPermission = 1 where userID = ? and userPermission = 0', (user_id,))
            cursor.execute('select allocationID from allocation_table where groupID = ?', (group_id,))
            with u.proxapi_session(cursor=cursor) as proxmox:
                for alloc in cursor.fetchall():
                    u.establish_allocation(alloc['allocationID'], proxmox=proxmox, cursor=cursor)
                u.user_enable(user_id, realm=u.get_config_value('realm', cursor=cursor), proxmox=proxmox)
    return redirect(request.referrer or '/')