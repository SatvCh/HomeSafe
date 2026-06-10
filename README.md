# AEIS – AI Driven Edge-Based Cybersecurity for IoT Networks

## Overview

AEIS (Autonomous Edge Immune System) is an AI-powered cybersecurity framework designed to secure IoT networks through real-time threat detection, anomaly identification, and autonomous response mechanisms. Inspired by the human immune system, AEIS continuously learns device behavior, detects suspicious activities, and responds to threats at the network edge without relying on cloud infrastructure. 

## Problem Statement

IoT devices often have limited security capabilities, making them vulnerable to malware, botnets, unauthorized access, and zero-day attacks. Traditional cloud-based security solutions introduce latency, privacy concerns, and delayed response times. AEIS addresses these challenges through intelligent edge-based cybersecurity. 

## Objectives

* Develop an AI-based edge security system for IoT environments.
* Detect both known and unknown cyber threats in real time.
* Enable autonomous threat response and mitigation.
* Preserve user privacy by minimizing cloud dependency.
* Build a self-learning and adaptive security framework. 

## Key Features

### Core Features

* Edge-based real-time threat detection
* Behavioral learning of IoT devices
* Zero-day attack detection using AI
* Autonomous response system
* Privacy-preserving architecture

### Additional Features

* Device-level behavior profiling
* Risk-based threat response
* Self-healing mechanism
* Low-latency processing
* Cloud-independent operation 

## Technologies Used

* Python
* Scikit-learn
* Pandas
* NumPy
* Matplotlib
* Isolation Forest
* Random Forest
* Edge Computing Infrastructure 

## System Architecture

The AEIS framework follows a multi-stage pipeline:

1. **Data Acquisition**

   * Collect network traffic and device metadata.

2. **Preprocessing**

   * Clean and normalize collected data.

3. **Feature Engineering**

   * Extract meaningful network and behavioral features.

4. **Model Training**

   * Isolation Forest for anomaly detection.
   * Random Forest for attack classification.

5. **Edge Deployment**

   * Deploy models on edge devices for local processing.

6. **Detection & Response**

   * Monitor traffic continuously.
   * Generate alerts and restrict suspicious devices.

7. **Recovery & Learning**

   * Restore normal operations.
   * Update models with new threat intelligence. 

## Machine Learning Models

### Isolation Forest

* Unsupervised anomaly detection algorithm.
* Detects unusual network behavior without labeled data.
* Effective for identifying unknown and zero-day threats.

### Random Forest

* Supervised classification algorithm.
* Classifies malicious and benign traffic.
* Provides high detection accuracy with reduced overfitting. 

## Implementation Roadmap

### Phase 1

Data Collection & Preprocessing

### Phase 2

Model Training & Hyperparameter Tuning

### Phase 3

Threat Detection & Autonomous Response

### Phase 4

Performance Optimization & Evaluation 

## Results

| Model            | Accuracy | Precision | Recall  | F1-Score |
| ---------------- | -------- | --------- | ------- | -------- |
| Isolation Forest | 83.33%   | 83.33%    | 100.00% | 90.91%   |
| Random Forest    | 83.33%   | 83.33%    | 100.00% | 90.91%   |

The system demonstrated:

* Effective attack detection
* Strong zero-day threat identification
* Low latency due to edge processing
* Stable performance under noisy conditions 

## Impact

* Enhances security across IoT ecosystems.
* Reduces the risk of botnet and DDoS attacks.
* Preserves privacy through local data processing.
* Supports deployment in smart homes, industries, and low-connectivity environments. 

## Future Enhancements

* Deep Learning-based threat detection.
* Federated Learning for collaborative security.
* Integration with SIEM platforms.
* Automated threat intelligence sharing.
* Support for larger-scale IoT deployments.

## Team

* Nakshatra Rane
* Sai Vinod Patil
* Sanika Mahajan
* Satvik Chaudhari

**Guide:** Prof. Shweta Yadav 

## References

1. Liu, F.T., Ting, K.M., Zhou, Z.H. – *Isolation Forest* (2008)
2. Breiman, L. – *Random Forests* (2001)
3. Meidan, Y. et al. – *N-BaIoT: Network-Based Detection of IoT Botnet Attacks Using Deep Autoencoders* (2018)
4. IEEE IoT Security and Anomaly Detection Research Papers 

---

**AEIS combines Artificial Intelligence and Edge Computing to create a self-learning, privacy-preserving, and autonomous cybersecurity solution for modern IoT networks.** 🚀🔒
