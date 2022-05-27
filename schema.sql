
-- let's think about this here
-- we have users that we query from ldap
-- we create groups and assign users to them
-- we need to produce a list of users in a group, and we need to check if a user is a part of any groups
-- we need to get a list of groups that user takes part in
-- we have VM templates that we query from proxmox
-- we add those templates to groups, such that a group can have an allocation a few templates.
-- a group can have one template allocated multiple times

-- once we have made an allocation we have clone id's that we need to keep track of
-- each allocation can have as much clone id's under it as many users are in the group that this allocation is for
-- clone id's cannot repeat! we need to produce which id's can be reused. (vmid) job
-- finally each clone id is spawned for one of the users in the group.
-- one user can have many cloneID from different allocations within a group, or from other groups.
-- but one cloneID can only be owned by one user.

-- clone_table: (cloneID) -- owner -- allocationID
-- user_table: (userID) -- userPermission -- Name Surname[cn] -- username -- i guess user details cached here, to limit ldap calls, and write this table only when syncing with ldap
-- group_table: (groupID) -- groupName
-- group_content (userID, groupID)
-- allocation_table: (allocationID), groupID, allocationName, templateID
-- vmid_table: (vmid), type, node
-- config: (option) -- section -- value


-- type == {clone, template}
-- userPermission = {
-- 0 disable proxmox account, we are not dealing with this user,
-- 1 student is part of a group, enable proxmox, and give him his clones.
-- 2 teacher, let him login to the app, and manage students
-- 3 teacher+, give his proxmox account, access to creating new clones, and setting templates
-- 4 admin, let him login to the app, and promote users to other levels.
-- }

-- ok so when i upgrade a template,
-- i full clone it.
-- perform the upgrades
-- leave it as reserved and have people test it.
-- set it as another template.
-- then sync from proxmox, so that a vmid type=template gets created
-- then i give powerUsers using the old version, notice to change their allocations to the new version.
-- powerUsers delete allocations and create ones with the new version( this can be magic'ed away in the post handler )
-- i set a date, where i forcefully delete remaining allocations still using the old version
-- and delete vmid and delete the old template (this should be an admin functionality from app side)

-- security: ssl, or any password can be intercepted.
-- on login, put a session hash in the user cookie,
-- and put that hash, with the login date into the database.
-- on next calls compare to system date to check if session is valid,

-- https://pve.proxmox.com/pve-docs/api-viewer/#/cluster/nextid
-- use this proxmox endpoint to get next vmid when creating clones

drop table if exists clone_table;
drop table if exists allocation_table;
drop table if exists group_content;
drop table if exists group_table;
drop table if exists user_table;
drop table if exists vmid_table;
drop table if exists config;

create table config(
    option TEXT NOT NULL PRIMARY KEY,
    section INTEGER,
    value BLOB
);

CREATE TABLE vmid_table(
    vmid INTEGER NOT NULL PRIMARY KEY,
    type INTEGER DEFAULT 0,
    node TEXT
) without rowid;
-- type 0 is a clone, it is set by this app, while creating a clone.
-- type 1 is a template found while querying proxmox api
-- type 2 is reserved vm created manually through proxmox UI (in current data population design, type 2 has become extinct)

CREATE TABLE user_table(
    userID TEXT NOT NUll PRIMARY KEY,
    userPermission INTEGER DEFAULT 0,
    fullname TEXT NOT NULL
) without rowid;
-- proxmox uses a string for userID,
-- ldap provides unique strings for username,
-- i decided to use those strings as key, and get rid of uidNumber

create table group_table(
    groupID INTEGER PRIMARY KEY,
    groupName TEXT
);

create table group_content(
    groupID INTEGER NOT NULL REFERENCES group_table(groupID) ON DELETE CASCADE ,
    userID TEXT NOT NULL REFERENCES user_table(userID) ON DELETE CASCADE,
    PRIMARY KEY(groupID, userID)
);

create table allocation_table(
    allocationID INTEGER PRIMARY KEY,
    groupID INTEGER NOT NULL REFERENCES group_table(groupID) ON DELETE CASCADE ,
    allocationName TEXT,
    templateID INTEGER NOT NULL REFERENCES vmid_table(vmid) ON DELETE CASCADE,
    author TEXT,
    created  INTEGER NOT NULL DEFAULT (strftime('%s')),
    expires INTEGER DEFAULT 0
);
-- Note that 0 here, in expires, means that it will never expire.
-- Otherwise the number defines duration in seconds to hold the allocation, counted from create timestamp.

create table clone_table(
    cloneID INTEGER NOT NULL PRIMARY KEY REFERENCES vmid_table(vmid) ON DELETE RESTRICT,
    userID TEXT NOT NULL REFERENCES user_table(userID) ON DELETE RESTRICT,
    allocationID INTEGER NOT NULL REFERENCES allocation_table(allocationID) ON DELETE RESTRICT
) without rowid;


-- maybe delete restrict, will throw error, that can be read to
-- handle removing recursively.. ask forgiveness ftw!

--TODAY I LEARNED! do not copy a database, when a server is running that depends on it.
-- transactions may not be fully closed, and it is very possible for the act of reading to copy, to be enough to corrupt both copies.
-- stop the server, then sync the deployment and dev. then restart the server thank you!