import pandas as pd

input_file = "data/raw/local/normal_capture.csv"

chunk_size = 1000000
rows_to_keep = 2000000

chunks = []
total_rows = 0

for chunk in pd.read_csv(
    input_file,
    chunksize=chunk_size,
    encoding="utf-16",   
    sep="\t"            
):
    chunks.append(chunk)
    total_rows += len(chunk)
    if total_rows >= rows_to_keep:
        break

df_sample = pd.concat(chunks)

df_sample.to_csv(
    "data/raw/local/normal_capture_trimmed.csv",
    index=False
)

print("Trimmed dataset saved.")