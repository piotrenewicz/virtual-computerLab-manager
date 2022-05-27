import service_utils
import argparse
# https://docs.python.org/2/howto/argparse.html#id1

argument_parser = argparse.ArgumentParser(description="Silent tool for non-interactive maintenance of virtual-lab-manager")
argument_parser.add_argument('-l', '--skip-ldap-sync', help='Skip updating user list from ldap', action='store_true', dest='skip_ldap')
argument_parser.add_argument('-p', '--skip-proxmox-sync', help='Skip updating vm template list from proxmox', action='store_true', dest='skip_proxmox')
argument_parser.add_argument('-a', '--skip-alloc-removal', help='Skip removing expired allocations', action='store_true', dest='skip_expired')
argument_parser.add_argument('-q', '--quiet', help='Do not print when skipping', action='store_true', dest='quiet')
args = argument_parser.parse_args()
polite_print = (lambda _: None) if args.quiet else print


with service_utils.db_session() as cursor:
    polite_print('skipping ldap sync!') if args.skip_ldap else service_utils.ldap_sync(cursor=cursor)
    polite_print('skipping proxmox sync!') if args.skip_proxmox else \
        service_utils.sync_proxmox(cursor=cursor, proxmox=service_utils.proxapi_session(cursor=cursor).__enter__())
    polite_print('skipping expired alloc remove!') if args.skip_expired else service_utils.remove_expired_alloc(cursor=cursor)