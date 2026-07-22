"""Generic job processing infrastructure (Agency Tool's processing OS).

MongoDB-backed queue (`data_layer_jobs`) consumed by one or many Supervisor-managed
workers. Fully generic: knows nothing about ingestion or any specific pipeline.
Handlers register themselves; the runner is reusable for ingestion, master rebuild,
entity resolution, signals, embeddings, KG, etc.
"""
