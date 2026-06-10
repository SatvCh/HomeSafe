from scapy.all import sniff, IP
import csv, time, os

CSV_FILE = "camera_dataset.csv"
packet_data = []

def packet_handler(packet):
    if IP in packet:
        packet_data.append({
            "dst": packet[IP].dst,
            "len": len(packet)
        })

def extract_features(data):
    if not data:
        return None

    packet_count = len(data)
    avg_size = sum(p["len"] for p in data) / packet_count
    unique_dest = len(set(p["dst"] for p in data))

    return packet_count, avg_size, unique_dest

label = int(input("Enter label (0 = NORMAL, 1 = ATTACK): "))

write_header = not os.path.exists(CSV_FILE)

with open(CSV_FILE, "a", newline="") as f:
    writer = csv.writer(f)

    if write_header:
        writer.writerow([
            "packets_per_min",
            "avg_packet_size",
            "activity_hour",
            "dest_count",
            "label"
        ])

    print("Collecting data... Press Ctrl+C to stop")

    try:
        while True:
            packet_data.clear()

            sniff(timeout=5, prn=packet_handler)

            feats = extract_features(packet_data)

            if feats:
                packets, avg_size, dest = feats
                hour = time.localtime().tm_hour

                writer.writerow([packets, avg_size, hour, dest, label])
                print(f"Saved → packets:{packets}, size:{avg_size:.1f}, dest:{dest}, label:{label}")

    except KeyboardInterrupt:
        print("\nStopped collection.")