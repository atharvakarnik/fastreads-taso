"""Generated, fictional NIfTI-1 inputs only; no clinical files are read by tests."""
import gzip
from pathlib import Path
import struct


def nifti_bytes(orientation="sform"):
    header = bytearray(352)
    struct.pack_into("<i", header, 0, 348)
    struct.pack_into("<8h", header, 40, 3, 16, 18, 10, 1, 1, 1, 1)
    struct.pack_into("<2h", header, 70, 4, 16)  # int16
    struct.pack_into("<8f", header, 76, 1, 1, 1.5, 2, 0, 0, 0, 0)
    struct.pack_into("<f", header, 108, 352)
    struct.pack_into("<f", header, 112, 1)
    header[123] = 2  # millimetres
    struct.pack_into("<2f", header, 124, 900, 0)
    struct.pack_into("<2h", header, 252, int(orientation == "qform"), int(orientation == "sform"))
    # An axis permutation (voxel Z -> R, X -> A, Y -> S) exercises header orientation.
    if orientation == "sform":
        struct.pack_into("<12f", header, 280, 0, 0, 2, -8, 1, 0, 0, -8, 0, 1.5, 0, -12)
    header[344:348] = b"n+1\0"
    values = [20 + x * 9 + y * 3 + z * 17 + (300 if x < 5 and y > 8 else 0)
              for z in range(10) for y in range(18) for x in range(16)]
    return gzip.compress(bytes(header) + struct.pack(f"<{len(values)}h", *values), mtime=0)


def add(base, subject="INDD001", visit="P1", sequences=("flair2d.nii.gz", "3d_resliced.nii.gz"), orientation="sform"):
    directory = Path(base) / "data" / subject / visit
    directory.mkdir(parents=True, exist_ok=True)
    for sequence in sequences:
        (directory / sequence).write_bytes(nifti_bytes(orientation))
    return directory
