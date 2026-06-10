from scapy.all import get_if_list, get_working_ifaces
for i in get_working_ifaces():
    print(i.name, i.ip)