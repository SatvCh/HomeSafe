# HomeSafe - AEIS (Autonomous Edge Immune System)

**A real-time network intrusion detection system for IoT devices using machine learning.**

## Overview

HomeSafe is an autonomous edge immune system designed to protect IoT devices (specifically Android cameras) from network-based attacks. It uses a hybrid dual-model approach combining **Isolation Forest** (unsupervised anomaly detection) and **Random Forest** (supervised classification) to detect both known attacks and zero-day threats.

## Features

🛡️ **Real-time Detection** - Continuous network packet monitoring  
🤖 **Dual-Model ML** - Isolation Forest + Random Forest ensemble  
📊 **Live Dashboard** - Web-based monitoring interface  
🔧 **Adaptive Learning** - Retrainable models with new data  
⚡ **Edge Deployment** - Runs on-device without cloud dependency  
🎥 **Camera Focused** - Optimized for IoT camera traffic analysis

## Architecture

```
AEIS_Pipeline/
├── pipeline.py           # Main detection pipeline
├── pipeline_live.py      # Live packet capture
├── detection.py          # Feature extraction & models
├── response.py           # System response logic
├── heal.py              # Quarantine recovery
└── simulation.py         # Attack simulation

AEIS_Server/
├── server.py            # Flask API server
├── index.html           # Web dashboard
├── aeis_utils.py        # Shared utilities
├── aeis_train_isolation_forest.py
├── aeis_train_random_forest.py
└── outputs_*/           # Trained models

Root/
├── collect_data.py      # Data collection script
├── process_data.py      # Feature engineering
├── merge_and_train.py   # Model retraining
└── predict.py           # Standalone prediction
```

## Installation

### Prerequisites
- Python 3.8+
- Virtual environment (recommended)

### Setup

```bash
# Clone repository
git clone https://github.com/yourusername/HomeSafe.git
cd HomeSafe

# Create virtual environment
python -m venv venv
source venv/Scripts/activate  # On Windows

# Install dependencies
pip install -r requirements.txt
```

## Usage

### 1. Start the Detection Server

```bash
python AEIS_Server/server.py
```

The server runs on `http://localhost:5000` with a real-time dashboard.

### 2. Run Live Pipeline

```bash
python AEIS_Pipeline/pipeline_live.py
```

Captures live network packets from your IoT camera and sends them to the server.

### 3. Collect Training Data

```bash
# Collect normal traffic
python collect_normal_traffic.py

# Or collect with labels
python collect_data.py
```

### 4. Retrain Models

```bash
python AEIS_Server/aeis_train_isolation_forest.py
python AEIS_Server/aeis_train_random_forest.py
```

### 5. Make Predictions

```bash
python predict.py
```

## Detection Rules

The system uses 4 primary detection rules:

| Rule | Threat Type | Threshold |
|------|------------|-----------|
| R1 | Packet Flood (DDoS) | ≥1500 pkt/window |
| R2 | Large Payloads | ≥1400 bytes avg |
| R3 | Destination Scan | High dest_count |
| R4 | Off-hours Activity | Activity outside normal hours |

## Model Details

### Isolation Forest
- **Purpose**: Detects novel/zero-day attacks (unsupervised)
- **Input**: 11 engineered features
- **Output**: Anomaly score & binary alert

### Random Forest
- **Purpose**: Detects known attack patterns (supervised)
- **Input**: 11 engineered features (time features removed)
- **Output**: Attack probability & confidence

## API Endpoints

- `POST /data` - Receive features from pipeline
- `GET /alert` - Get current system status
- `GET /traffic` - Get traffic metrics
- `GET /simulate/<attack>` - Simulate attack
- `GET /heal` - Trigger quarantine recovery

## Performance Metrics

- **Detection Latency**: < 100ms per window
- **False Positive Rate**: < 5%
- **Attack Detection Rate**: > 95%

## Project Structure

```
├── requirements.txt          # Dependencies
├── .gitignore               # Git ignore rules
├── README.md                # This file
├── AEIS_Pipeline/           # Core detection logic
├── AEIS_Server/             # Web server & training
└── [data files excluded]    # .csv, .pkl, outputs/
```

## Future Enhancements

- [ ] Multi-camera support
- [ ] Cloud sync option
- [ ] Mobile app
- [ ] Advanced visualization
- [ ] Model explainability (SHAP)

## License

Proprietary - Internal Use Only

## Contact

For questions or contributions, contact the development team.

---

**Last Updated**: April 2026
