import utils as u
from flask import Blueprint, render_template, request, redirect, session, url_for
from datetime import datetime


core_app = Blueprint('core', __name__, template_folder='templates')


@core_app.route('/group-overview', methods=('GET', 'POST'))
def group_list():
    search = '%'
    if request.method == 'POST':
        search = f'%{u.form_reader("search")["search"]}%'
    with u.db_session() as cursor:
        cursor.execute('select groupID, groupName from group_table where groupName like ?', (search,))
        groups = cursor.fetchall()

    return render_template('core/overview.html', groups=groups)


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

    pwd = [(context['name'], '#')]

    return render_template('core/group.html', context=context, pwd=pwd)


@core_app.route('/group-new/')
def add_group():
    with u.db_session() as cursor:
        cursor.execute("insert into group_table(groupName) values ('Grupa?') returning groupID;")
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
        (context['group_name'], url_for('core.group_edit', group_id=group_id)),
        ("Osoby", '#')
    ]
    return render_template('core/users.html', context=context, pwd=pwd)


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
    if not user_id:
        return redirect(request.referrer or '/')

    with u.db_session() as cursor:
        if not session.get('preferUserQuery'):
            cursor.execute('select userID from user_table where fullname = ?', (user_id,))
            user_id = u.one_row_fix(cursor.fetchone())

        cursor.execute('insert into group_content(groupID, userID) values (?, ?)', (group_id, user_id))
        cursor.execute('update user_table set userPermission = 1 where userID = ? and userPermission = 0', (user_id,))
        cursor.execute('select allocationID from allocation_table where groupID = ?', (group_id,))
        with u.proxapi_session(cursor=cursor) as proxmox:
            for alloc in cursor.fetchall():
                u.alloc_fill(alloc['allocationID'], proxmox=proxmox, cursor=cursor)
            u.user_enable(user_id, realm=u.get_config_value('realm', cursor=cursor), proxmox=proxmox)
    return redirect(request.referrer or '/')


@core_app.route('/group/<int:group_id>/alloc/')
def alloc_list(group_id: int):
    context = dict(group_id=group_id)
    with u.db_session() as cursor:
        cursor.execute('select allocationID, allocationName from allocation_table where groupID = ?', (group_id,))
        context['alloc'] = cursor.fetchall()
        context['group_name'] = u.get_group_name(group_id, cursor=cursor)

    pwd = [
        (context['group_name'], url_for('core.group_edit', group_id=group_id)),
        ("Przydzia??y", '#')
    ]
    return render_template('core/allocations.html', context=context, pwd=pwd)


@core_app.route('/group/<int:group_id>/alloc/<int:alloc_id>/')
def alloc_edit(group_id: int, alloc_id: int):
    context = dict(group_id=group_id, alloc_id=alloc_id)
    with u.db_session() as cursor:
        context['group_name'] = u.get_group_name(group_id, cursor=cursor)
        cursor.execute('select allocationName from allocation_table where allocationID = ?', (alloc_id,))
        context['alloc_name'] = u.one_row_fix(cursor.fetchone())
        cursor.execute('''
            select cloneID, userID, node 
            from clone_table inner join vmid_table on cloneID = vmid 
            where allocationID = ?''', (alloc_id,))
        context['clones'] = [dict(row) for row in cursor.fetchall()]
        if context['clones']:
            with u.proxapi_session(cursor=cursor) as proxmox:
                for clone in context['clones']:
                    clone['status'] = proxmox.nodes(clone['node']).qemu(clone['cloneID']).status.current.get()['status'] == 'running'
                    clone['name'] = proxmox.nodes(clone['node']).qemu(clone['cloneID']).config.get()['name']
    pwd = [
        (context['group_name'], url_for('core.group_edit', group_id=group_id)),
        ("Przydzia??", url_for('core.alloc_list', group_id=group_id)),
        (context['alloc_name'], '#')
    ]
    return render_template('core/clones.html', context=context, pwd=pwd)


@core_app.route('/group/<int:group_id>/alloc/add/', methods=('GET', 'POST'))
def add_alloc(group_id: int):
    def handle_post():
        data = u.form_reader('alloc')
        with u.db_session() as cursor:
            cursor.execute('''
                insert into allocation_table(groupID, allocationName, templateID, expires, author)
                values (?, ?, ?, ?, ?) returning allocationID;
            ''', (group_id, data['alloc_name'], data['template'], data['expire'], session.get('login')))
            alloc_id = u.one_row_fix(cursor.fetchone())
            with u.proxapi_session(cursor=cursor) as proxmox:
                u.alloc_fill(group_id, alloc_id, proxmox=proxmox, cursor=cursor)
        return redirect(url_for('core.alloc_edit', group_id=group_id, alloc_id=alloc_id))

    def handle_get():
        context = dict(group_id=group_id)
        with u.db_session() as cursor:
            context['group_name'] = u.get_group_name(group_id, cursor=cursor)
            cursor.execute('select vmid, node from vmid_table where type = 1')
            context['templates'] = [dict(row) for row in cursor.fetchall()]
            if context['templates']:
                with u.proxapi_session(cursor=cursor) as proxmox:
                    for template in context['templates']:
                        template['name'] = proxmox.nodes(template['node']).qemu(template['vmid']).config.get()['name']
        pwd = [
            (context['group_name'], url_for('core.group_edit', group_id=group_id)),
            ("Przydzia??y", url_for('core.alloc_list', group_id=group_id)),
            ("Nowy Przydzia??", '#')
        ]
        return render_template('core/new_alloc.html', context=context, pwd=pwd)

    return handle_post() if request.method == 'POST' else handle_get()


@core_app.route('/group/<int:group_id>/alloc/<int:alloc_id>/remove/')
def remove_alloc(group_id: int, alloc_id: int):
    with u.db_session() as cursor, u.proxapi_session(cursor=cursor) as proxmox:
        u.alloc_drain(alloc_id, proxmox=proxmox, cursor=cursor)
        cursor.execute('delete from allocation_table where allocationID = ?', (alloc_id,))
    return redirect(url_for('core.alloc_list', group_id=group_id))


@core_app.route('/group/<int:group_id>/alloc/<int:alloc_id>/renew/')
def alloc_reset(group_id: int, alloc_id: int):
    with u.db_session() as cursor, u.proxapi_session(cursor=cursor) as proxmox:
        u.alloc_drain(alloc_id, proxmox=proxmox, cursor=cursor)
        u.alloc_fill(group_id, alloc_id, proxmox=proxmox, cursor=cursor)
    return redirect(request.referrer or '/')


@core_app.route('/group/<int:group_id>/alloc/<int:alloc_id>/details/')
def alloc_detail(group_id: int, alloc_id: int):
    with u.db_session() as cursor:
        cursor.execute("""select author, created, expires, cast(strftime('%s') as integer) as now 
            from allocation_table where allocationID = ?""", (alloc_id,))
        data = u.one_row_fix(cursor.fetchone())
    state = None if not data['expires'] else data['created'] + data['expires'] < data['now']  # expired state?
    result = f"Stan przydzia??u: { {None: 'wieczny', False: 'aktywny', True: 'wygas??y'}[state] }\n" \
             f"Przydzia?? stworzony przez: {data['author']}\n" \
             f"Data stworzenia: { datetime.fromtimestamp(data['created']) }\n" \
             f"""{  
                f'Data wyga??ni??cia: { datetime.fromtimestamp(data["created"] + data["expires"]) }'
                f'{ chr(10)*2 }'
                f'Zegar na serwerze: { datetime.fromtimestamp(data["now"]) }'
                if state is not None else '' 
             }"""
    # I wanted newlines in an optional section.
    # Optional section is gained by putting the whole section as a variable to be formatted in, which could be empty
    # I didn't want to use '''multiline string''' for the variable as that would capture \t chars, from indentation.
    # or force me to drop the indentation.
    # I also couldn't use \n characters becasue '\' symbol is disallowed inside format{ }
    # https://towardsdatascience.com/how-to-add-new-line-in-python-f-strings-7b4ccc605f4a
    # This page talks about such problem and provided basis for my solution,
    # of inserting the newline characters by their ascii number, like so:
    # f'{ chr(10)*2 }' instead of f'<br><br>'
    u.flash(result, 'info')
    return redirect(request.referrer or '/')


@core_app.route('/pwrctrl/single/<int:clone_id>/<int:state>/')
def power_control(clone_id: int, state: int):
    with u.db_session() as cursor, u.proxapi_session(cursor=cursor) as proxmox:
        cursor.execute('select vmid, node from vmid_table where vmid = ?', (clone_id,))
        u.power_clones(cursor.fetchall(), shutdown=not bool(state), block=True, proxmox=proxmox)
    return redirect(request.referrer or '/')


@core_app.route('/pwrctrl/bulk/<int:alloc_id>/<int:state>/')
def power_control_bulk(alloc_id: int, state: int):
    with u.db_session() as cursor, u.proxapi_session(cursor=cursor) as proxmox:
        cursor.execute('''select vmid, node from clone_table ct inner join vmid_table vt 
            on ct.cloneID = vt.vmid where allocationID = ?''', (alloc_id, ))
        u.power_clones(cursor.fetchall(), shutdown=not bool(state), block=True, proxmox=proxmox)
    return redirect(request.referrer or '/')
