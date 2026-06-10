# verify.py — run on Laptop 1 after retraining
import joblib, numpy as np, pandas as pd
from aeis_utils import engineer_features

rf  = joblib.load("outputs_rf/model_random_forest.pkl")
iso = joblib.load("outputs_if/model_isolation_forest.pkl")
thr_rf  = float(np.load("outputs_rf/rf_threshold.npy"))
thr_iso = float(np.load("outputs_if/iso_threshold.npy"))
RF_DROP = ['activity_hour','hour_sin','hour_cos','high_hour_flag']

def check(label, pkts, size, dest, hour):
    raw = pd.DataFrame([[pkts, size, dest, hour]],
        columns=["packets_per_window","avg_packet_size","dest_count","activity_hour"])
    fe = engineer_features(raw)
    rf_prob  = rf.predict_proba(fe.drop(columns=RF_DROP).values)[0,1]
    iso_score = float(-iso.score_samples(fe.values)[0])
    rf_flag  = rf_prob  >= thr_rf
    iso_flag = iso_score >= thr_iso
    if iso_flag and rf_flag and pkts > 6000: status = "QUARANTINED"
    elif iso_flag and rf_flag:               status = "SUSPICIOUS"
    else:                                    status = "NORMAL"
    print(f"{label:25} rf={rf_prob:.2f} iso={iso_score:.2f} → {status}")

check("Normal DroidCam",      pkts=1500, size=1100, dest=2,  hour=10)
check("DoS ramp (suspicious)",pkts=4000, size=60,   dest=1,  hour=10)
check("DoS flood (quarant.)", pkts=15000,size=60,   dest=1,  hour=10)
check("Port scan",            pkts=5000, size=80,   dest=30, hour=10)
check("Exfiltration",         pkts=3000, size=1480, dest=1,  hour=2)
check("Botnet",               pkts=6000, size=120,  dest=2,  hour=3)