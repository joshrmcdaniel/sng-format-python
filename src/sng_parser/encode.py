import io
import os

from configparser import ConfigParser
import struct
from typing import List, Optional, Tuple


from .common import (
    write_uint32,
    write_uint8,
    write_uint64,
    mask,
    SngFileMetadata,
    SngMetadataInfo,
)


def write_header(file: io.FileIO, version: int, xor_mask: bytes) -> None:
    file.write(b"SNGPKG")
    write_uint32(file, version)
    file.write(xor_mask)


def write_file_meta(file: io.FileIO, file_meta_array: List[SngFileMetadata]) -> None:
    filemeta_buf = struct.pack('<Q', len(file_meta_array))

    for file_meta in file_meta_array:
        filename_len = len(file_meta.filename)
        filemeta_buf += struct.pack('<B', filename_len)
        filename_packed = struct.pack(f"<{filename_len}s", file_meta.filename.encode('utf-8'))
        filemeta_buf += filename_packed
        
        filemeta_buf += struct.pack("<Q", file_meta.content_len)
        filemeta_buf += struct.pack("<Q", file_meta.content_idx)
    
    file.write(struct.pack('<Q', len(filemeta_buf)))
    file.write(filemeta_buf)


def write_metadata(file: io.FileIO, metadata: SngMetadataInfo) -> None:
    metadata_content = struct.pack("<Q", len(metadata))

    key: str
    value: str
    for key, val in metadata.items():
        key_len: int = len(key)
        key_len_packed = struct.pack('<I', key_len)
        key: bytes = struct.pack(f"<{key_len}s", key.encode('utf-8'))

        value_len: int = len(val)
        value_len_packed: bytes = struct.pack('<I', value_len)
        value: bytes = struct.pack(f'<{value_len}s', val.encode('utf-8'))
        metadata_content += key_len_packed+key+value_len_packed+value
    file.write(struct.pack("<Q", len(metadata_content)))
    file.write(metadata_content)


def write_file_data(out: io.FileIO, file_meta_array: List[Tuple[str, SngFileMetadata]], xor_mask: bytes):
    total_file_data_length = sum(map(lambda x: x[1].content_len, file_meta_array))
    out.write(struct.pack('<Q', total_file_data_length))

    for filename, file_metadata in file_meta_array:
        amt_read = 0
        with open(filename, 'rb') as f:
            while file_metadata.content_len > amt_read:
                chunk_size = 1024 if file_metadata.content_len - amt_read > 1023 else file_metadata.content_len - amt_read
                amt_read += chunk_size
                buf = f.read(chunk_size)
                out.write(mask(buf, xor_mask))


def to_sng_file(
    output_filename: os.PathLike,
    directory: os.PathLike,
    version: int = 1,
    xor_mask: Optional[bytes] = None,
    metadata: Optional[SngMetadataInfo] = None,
) -> None:
    if metadata is None:
        metadata = read_file_meta(directory)
    if xor_mask is None:
        xor_mask = os.urandom(16)

    with open(output_filename, "wb") as file:
        write_header(file, version, xor_mask)
        write_metadata(file, metadata)
        file_meta_array = gather_files_from_directory(directory, offset=file.tell())
        write_file_meta(file, list(map(lambda x: x[1], file_meta_array)))
        write_file_data(file, file_meta_array, xor_mask)


def gather_files_from_directory(directory: os.PathLike, offset: int) -> List[Tuple[str, SngFileMetadata]]:
    file_meta_array = []
    current_index = offset

    for filename in os.listdir(directory):
        if filename == "song.ini":
            continue

        filepath = os.path.join(directory, filename)
        if os.path.isfile(filepath):
            with open(filepath, "rb") as file:
                size = file.seek(0, os.SEEK_END)

            file_meta = SngFileMetadata(filename, size, current_index)
            file_meta_array.append((filepath, file_meta))

            current_index += size

    return file_meta_array


def read_file_meta(filedir: os.PathLike) -> SngMetadataInfo:
    cfg = ConfigParser()
    with open(os.path.join(filedir, "song.ini")) as f:
        cfg.read_file(f)
    return dict(cfg["Song"])
