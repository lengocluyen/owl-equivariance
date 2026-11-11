# Hardware summary without device identifiers

The archived GPU records identify eight NVIDIA Tesla V100-SXM2-32GB devices, each with 32,768 MiB reported memory, and driver 570.211.01. The software environment records Linux 5.15.0-1098-nvidia, 80 logical CPU slots, Python 3.12.13, and OpenJDK 25.0.3.

Original GPU CSVs and detailed `nvidia-smi -q` dumps contain device UUIDs or other machine identifiers unnecessary for interpreting the experiment. Those original files remain local. Their paths and hashes are listed as omissions in the artifact manifest; their contents are not edited and redistributed as if still byte-identical originals. This summary is a packaging addition, not a new hardware measurement.
