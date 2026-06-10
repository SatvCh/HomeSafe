import joblib, numpy as np, pandas as pd
from aeis_utils import engineer_features, BASE_FEATURES

iso = joblib.load("outputs_if/model_isolation_forest.pkl")
thr_if = float(np.load("outputs_if/iso_threshold.npy"))
rf  = joblib.load("outputs_rf/model_random_forest.pkl")
thr_rf = float(np.load("outputs_rf/rf_threshold.npy"))
RF_DROP = ['activity_hour','hour_sin','hour_cos','high_hour_flag']

def test(label, pkts, size, dest, hour):
    raw = pd.DataFrame([[pkts, size, dest, hour]], columns=BASE_FEATURES)
    fa  = engineer_features(raw)
    fr  = fa.drop(columns=RF_DROP)
    iso_score = float(-iso.score_samples(fa.values)[0])
    rf_prob   = float(rf.predict_proba(fr.values)[0, 1])
    result = "ATTACK" if (iso_score>=thr_if and rf_prob>=thr_rf) else "NORMAL"
    print(f"{label:15} pkts={pkts:5} size={size:6} → ISO={iso_score:.4f} RF={rf_prob:.4f} → {result}")

print(f"\nISO threshold={thr_if:.4f}  RF threshold={thr_rf:.4f}\n")
test("Normal low",    2000, 1500, 2, 18)
test("Normal high",   3200, 2300, 3, 18)
test("Phase 1 atk",  2500, 3000, 5, 18)
test("Phase 2 atk",  9000, 4500, 8, 18)