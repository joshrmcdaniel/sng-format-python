import os
import shutil
import struct
from io import BufferedReader
from pathlib import Path
import tempfile


from typing import List, Optional, NoReturn, Tuple

from configparser import ConfigParser

from .common import mask, SngFileMetadata, SngMetadataInfo, calc_and_unpack, SngHeader, calc_and_read_buf
from struct import calcsize

def read_sng_header(buffer: BufferedReader) -> SngHeader:
    xor_mask: bytes
    version: int
    file_identifier: bytes
    file_identifier, version, xor_mask = calc_and_unpack("<6sI16s", buffer)
    return SngHeader(file_identifier, version, xor_mask)


def read_filedata(buffer: BufferedReader) -> Tuple[SngFileMetadata, int]:
    amt_read: int = 0
    
    read_size, content = calc_and_read_buf("<B", buffer)
    amt_read += read_size
    filename_len: int = struct.unpack_from("<B", content)[0]
    
    read_size, content = calc_and_read_buf(f"<{filename_len}s", buffer)
    amt_read += read_size
    filename: str = struct.unpack_from(f"<{filename_len}s", content)[0].decode()

    read_size, content = calc_and_read_buf("<QQ", buffer)
    amt_read += read_size
    contents_len: int
    contents_index: int
    contents_len, contents_index = struct.unpack_from("<QQ", content)
    metadata = SngFileMetadata(filename, contents_len, contents_index)

    return metadata, amt_read


def decode_file_metadata(buffer: BufferedReader) -> List[SngFileMetadata]:
    amt_read: int = 0
    file_meta_len: int
    file_count: int
    file_meta_len, file_count = calc_and_unpack("<QQ", buffer)
    amt_read += calcsize("<Q")
    file_meta_array: List[SngFileMetadata] = []
    for _ in range(file_count):
        file_meta, bytes_read = read_filedata(buffer)
        amt_read += bytes_read
        file_meta_array.append(file_meta)
    if file_meta_len != amt_read:
        raise RuntimeError("File metadata read mismatch. Expected %d, read %d" % (file_meta_len, amt_read))
    return file_meta_array


def decode_metadata(sng_buffer: BufferedReader) -> SngMetadataInfo:
    bytes_read: int = 0
    metadata_len: int
    metadata_count: int
    metadata_len, metadata_count = calc_and_unpack("<QQ", sng_buffer)
    bytes_read += calcsize("<Q")
    metadata = {}
    for _ in range(metadata_count):
        read_size, content = calc_and_read_buf("<I", sng_buffer)
        bytes_read += read_size
        key_len: int = struct.unpack_from("<I", content)[0]

        read_size, content = calc_and_read_buf(f"<{key_len}s", sng_buffer)
        bytes_read += read_size
        key: str = struct.unpack_from(f"<{key_len}s", content)[0].decode()
        
        read_size, content = calc_and_read_buf(f"<I", sng_buffer)
        bytes_read += read_size
        value_len: int = struct.unpack_from("<I", content)[0]

        read_size, content = calc_and_read_buf(f"<{value_len}s", sng_buffer)
        bytes_read += read_size
        value: str = struct.unpack_from(f"<{value_len}s", content)[0].decode()

        metadata[key] = value

    if bytes_read != metadata_len:
        raise RuntimeError("Metadata read mismatch. Expected %d, read %d" % (metadata_len, read_size))

    metadata_attrs_read = len(metadata)
    if metadata_attrs_read != metadata_count:
        raise RuntimeError("Metadata count mismatch. Expected %d, found %d" % (metadata_count, metadata_attrs_read))
    return metadata

def write_file_contents(file_meta_array: List[SngFileMetadata], buffer: BufferedReader, *, xor_mask: bytes, outdir: os.PathLike):
    file_data_len: int = calc_and_unpack("<Q", buffer)[0]
    file_meta_content_size: int = sum(map(lambda x: x.content_len, file_meta_array))
    if file_meta_content_size != file_data_len:
        raise RuntimeError("Length mismatch, %d != %d" % (file_meta_content_size, file_data_len))
    for file_meta in file_meta_array:
        cur_offset = buffer.tell()
        if cur_offset != file_meta.content_idx:
            raise RuntimeError("File offset mismatch. Got %d, expected %d" % (cur_offset, file_meta.content_idx))
        _write_file_contents(file_meta, buffer, xor_mask=xor_mask, outdir=outdir)


def _write_file_contents(
    file_metadata: SngFileMetadata,
    buffer: BufferedReader,
    *,
    xor_mask: bytes,
    outdir: os.PathLike
    ) -> None:
    amt_read = 0
    file_path = os.path.join(outdir, file_metadata.filename)
    with open(file_path, 'wb') as out:
        while file_metadata.content_len > amt_read:
            chunk_size = 1024 if file_metadata.content_len - amt_read > 1023 else file_metadata.content_len - amt_read
            amt_read += chunk_size
            buf = buffer.read(chunk_size)
            out.write(mask(buf, xor_mask))
        if file_metadata.content_len != amt_read:
            raise RuntimeError("File write mismatch. Expected %d, wrote %d" % (file_metadata.content_len, amt_read))


def _as_path_obj(path: str, *, validate: bool=True) -> Path | NoReturn:
    path = Path(path)
    if validate:
        _validate_path(path)
    return path


def _validate_path(path: os.PathLike) -> None | NoReturn:
    if not os.path.exists(path):
        raise RuntimeError("No file located at %s" % path)


def decode_sng(
        sng_file: os.PathLike | str | BufferedReader,
        *,
        outdir: Optional[os.PathLike | str] = None,
        sng_dir: Optional[os.PathLike | str] = None
        ) -> None | NoReturn:
    path_passed = not isinstance(sng_file, BufferedReader)
    if outdir is None:
        outdir = os.curdir
    if isinstance(outdir, str):
        outdir = _as_path_obj(outdir)
    if isinstance(sng_file, str):
        sng_file = _as_path_obj(sng_file)
    
    if isinstance(sng_file, os.PathLike):
        _validate_path(sng_file)
        sng_file = open(sng_file, 'rb')

    header= read_sng_header(sng_file)

    if header.file_identifier.decode() != "SNGPKG":
        raise ValueError("Invalid file identifier")
    
    metadata = decode_metadata(sng_file)
    if sng_dir is None:
        sng_dir = create_dirname(metadata)
    outdir = os.path.join(outdir, sng_dir)
    if os.path.exists(outdir):
        raise RuntimeError("Song already exists at %s" % outdir)
    
    tmp_dir = tempfile.mkdtemp()
    write_metadata(metadata, tmp_dir)

    file_meta_array: List[SngFileMetadata] = decode_file_metadata(sng_file)
    write_file_contents(file_meta_array, sng_file, xor_mask=header.xor_mask, outdir=tmp_dir)

    if path_passed:
        sng_file.close()

    os.makedirs(outdir)
    files_to_move = list(map(lambda x: x.filename, file_meta_array))
    files_to_move.append("song.ini")
    for filename in files_to_move:
        shutil.move(os.path.join(tmp_dir, filename), outdir)


def create_dirname(metadata: SngFileMetadata) -> str:
    artist = metadata.get("artist", "Unknown Artist")
    song = metadata.get("name", "Unknown Song")
    charter = metadata.get("charter", "Unknown Charter")
    return f"{artist} - {song} ({charter})"


def write_metadata(metadata: SngMetadataInfo, outdir: os.PathLike) -> None:
    print("Writing metadata to %s" % outdir)
    cfg = ConfigParser()
    cfg.add_section("Song")
    cfg["Song"] = metadata
    with open(os.path.join(outdir, "song.ini"), "w") as f:
        cfg.write(f)
