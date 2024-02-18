import hashlib
import logging
import os
import struct

from copy import deepcopy
from configparser import ConfigParser
from io import BufferedWriter
from typing import List, Optional, Tuple


from .common import (
    SNG_RESERVED_FILES,
    mask,
    _with_endian,
    _fail_on_invalid_sng_ver,
    write_and_mask,
    _validate_and_pack,
    _valid_sng_file,
    _illegal_filename,
    SngFileMetadata,
    SngMetadataInfo,
    StructTypes,
)


s = StructTypes
logger = logging.getLogger(__package__)


def write_header(file: BufferedWriter, version: int, xor_mask: bytes) -> None:
    """
    Writes the header information for an SNG file to the given file buffer.

    The header includes a fixed signature ('SNGPKG'), the version of the file
    format as an unsigned integer, and a byte sequence used as an XOR mask
    for encryption.

    Args:
        file (BufferedWriter): The file buffer to write the header to.
        version (int): The version of the SNG file format.
        xor_mask (bytes): The byte sequence used as an XOR mask for file encryption.

    Returns:
        None
    """
    logger.info("Writing sng header")
    file.write(b"SNGPKG")
    _fail_on_invalid_sng_ver(version)
    file.write(_validate_and_pack(_with_endian(s.UINT), version))
    file.write(xor_mask)
    logger.info("Wrote header")


def write_file_meta(
    file: BufferedWriter, file_meta_array: List[SngFileMetadata], convert_to_opus: bool
) -> None:
    """
    Writes metadata for multiple files included in the SNG package.

    Each file's metadata includes its name, content length, and offset within the SNG file.
    The total size of the metadata section and the number of files are also included.

    Args:
        file (BufferedWriter): The file buffer to write the metadata to.
        file_meta_array (List[SngFileMetadata]): A list of metadata objects for each file.

    Returns:
        None
    """
    ret = []
    meta_arr = deepcopy(file_meta_array)
    logger.info("Writing file metadata")
    if convert_to_opus:
        meta_arr = []
        for a in file_meta_array:
            filename, ext = a.filename.split('.')
            if ext in {'ogg', 'mp3', "wav"}:
                meta_arr.append(SngFileMetadata(filename+'.opus', 0, 0))
            else:
                meta_arr.append(a)
    calcd_size = struct.calcsize(_with_endian(s.ULONGLONG))
    print(meta_arr)
    for file_meta in meta_arr:
        filename_len = len(file_meta.filename)
        calcd_size += (
            struct.calcsize(_with_endian(s.UBYTE))
            + struct.calcsize(_with_endian(filename_len, s.CHAR))
            + struct.calcsize(_with_endian(s.ULONGLONG)) * 2
        )

    file.write(_validate_and_pack(_with_endian(s.ULONGLONG), calcd_size))
    file.write(_validate_and_pack(_with_endian(s.ULONGLONG), len(meta_arr)))
    logger.debug("Calculated file metadata section size: %d", calcd_size)

    fileoffset = file.tell() + calcd_size
    logger.debug("File content section start: %d", fileoffset)

    for idx, file_meta in enumerate(meta_arr):
        logger.debug("Writing file metadata for %s", file_meta.filename)
        filename_len = len(file_meta.filename)
        file.write(_validate_and_pack(_with_endian(s.UBYTE), filename_len))
        filename_packed = _validate_and_pack(
            _with_endian(filename_len, s.CHAR), file_meta.filename.encode("utf-8")
        )
        file.write(filename_packed)
        logger.debug("%s content size: %d", file_meta.filename, file_meta.content_len)
        ret.append((file_meta_array[idx].filename,  file.tell()))
        file.write(_validate_and_pack(_with_endian(s.ULONGLONG), file_meta.content_len))
        logger.debug("%s offset: %d", file_meta.filename, fileoffset)
        file.write(_validate_and_pack(_with_endian(s.ULONGLONG), fileoffset))
        fileoffset += file_meta.content_len

    logger.info("Wrote file metadata for %d files", len(meta_arr))
    return ret


def write_metadata(file: BufferedWriter, metadata: SngMetadataInfo) -> None:
    """
    Writes key-value pairs of metadata information for the SNG file.

    The metadata is stored as a series of length-prefixed strings (both for keys and values),
    with the total length of the metadata section prefixed at the start.

    Args:
        file (BufferedWriter): The file buffer to write the metadata to.
        metadata (SngMetadataInfo): A dictionary containing metadata key-value pairs.

    Returns:
        None
    """
    logger.info("Writing song metadata")

    metadata_content = _validate_and_pack(_with_endian(s.ULONGLONG), len(metadata))
    key: str
    value: str
    for key, val in metadata.items():
        key_len: int = len(key)
        key_len_packed = _validate_and_pack(_with_endian(s.UINT), key_len)
        key: bytes = _validate_and_pack(
            _with_endian(key_len, s.CHAR), key.encode("utf-8")
        )

        value_len: int = len(val)
        value_len_packed: bytes = _validate_and_pack(_with_endian(s.UINT), value_len)
        value: bytes = _validate_and_pack(
            _with_endian(value_len, s.CHAR), val.encode("utf-8")
        )
        metadata_content += key_len_packed + key + value_len_packed + value

    file.write(_validate_and_pack(_with_endian(s.ULONGLONG), len(metadata_content)))
    file.write(metadata_content)

    logger.info("Wrote song metadata")

from .audio import to_opus
def write_file_data(
    out: BufferedWriter,
    file_meta_array: List[Tuple[str, SngFileMetadata]],
    xor_mask: bytes,
    offset_ref: List[Tuple],
    convert_to_opus: bool
):
    """
    Writes the actual file data for each file included in the SNG package.

    File data is read from the source files, optionally masked with an XOR mask for encryption,
    and written to the SNG file. Each file's data is preceded by its total length.

    Args:
        out (BufferedWriter): The output file buffer to write the data to.
        file_meta_array (List[Tuple[str, SngFileMetadata]]): A list of tuples containing file paths and their metadata.
        xor_mask (bytes): The byte sequence used as an XOR mask for file data encryption.

    Returns:
        None
    """
    logger.debug("Writing file data")

    size = 0
    data_idx = out.tell()
    out.write(_validate_and_pack(_with_endian(s.ULONGLONG), 0))
    for filename, file_metadata in file_meta_array:
        file, ext = file_metadata.filename.split('.')
        if ext in {'ogg', 'mp3', "wav"} and convert_to_opus:
            print(filename)
            print(os.path.basename(filename))
            print(offset_ref)
            idx = next(y for x, y in offset_ref if x == os.path.basename(filename))
            buf = to_opus(filename)
            before_write = out.tell()
            out.write(mask(buf.read(), xor_mask))
            after_write = out.tell()
            out.truncate()
            opus_size = after_write - before_write
            size += opus_size
            out.seek(idx)
            out.write(_validate_and_pack(_with_endian(s.ULONGLONG), opus_size))
            out.write(_validate_and_pack(_with_endian(s.ULONGLONG), before_write))
            out.seek(after_write)
            out.truncate()
        else:
            bytes_written = write_and_mask(read_from=filename, write_to=out, xor_mask=xor_mask, filesize=file_metadata.content_len)
            size += file_metadata.content_len
    out.truncate()
    out.seek(data_idx)
    out.write(_validate_and_pack(_with_endian(s.ULONGLONG), size))

    logger.debug("Wrote file data")


def encode_sng(
    dir_to_encode: os.PathLike,
    *,
    output_filename: Optional[os.PathLike] = None,
    allow_nonsng_files: bool = False,
    overwrite: bool = False,
    version: int = 1,
    xor_mask: Optional[bytes] = None,
    metadata: Optional[SngMetadataInfo] = None,
) -> None:
    """
    Encodes a directory of files into a single SNG package file.

    This process involves reading metadata, writing a header, encoding file metadata,
    and writing the actual file data, optionally applying an XOR mask for encryption.

    Args:
        dir_to_encode (os.PathLike): The directory containing files to be encoded into the SNG package.
        output_filename (os.PathLike, optional): The output path of the SNG file. Defaults to the md5 sum of the containing files of converted dir.
        allow_nonsng_files (bool, optional): Allow encoding of files not allowed by the sng standard. Defaults to False.
        overwrite (bool, optional): If True, existing files or directories will be overwritten. Defaults to False.
        version (int, optional): The version of the SNG format to use. Defaults to 1.
        xor_mask (bytes, optional): An optional XOR mask for encryption. If not provided, a random one is generated.
        metadata (SngMetadataInfo, optional): Metadata for the SNG package. If not provided, it's read from a 'song.ini' file in the directory.

    Returns:
        None
    """
    if not os.path.exists(dir_to_encode):
        raise FileNotFoundError("%s was not found." % dir_to_encode)
    if metadata is None:
        metadata = read_file_meta(dir_to_encode)
    if xor_mask is None:
        xor_mask = os.urandom(16)
    if (x := len(xor_mask)) != 16:
        raise ValueError(
            "xor mask should be of length 16, found xor_mask of length %d" % x
        )
    if output_filename is None:
        output_filename = create_sng_filename(dir_to_encode) + ".sng"
    if not output_filename.endswith(".sng"):
        output_filename += ".sng"
    if os.path.exists(output_filename) and not overwrite:
        err = FileExistsError("Sng file exists: %s" % output_filename)
        err.filename = output_filename
        raise err
    with open(output_filename, "wb") as file:
        write_header(file, version, xor_mask)
        write_metadata(file, metadata)
        file_meta_array = gather_files_from_directory(
            dir_to_encode, offset=file.tell(), allow_nonsng_files=allow_nonsng_files
        )
        write_refs = write_file_meta(file, list(map(lambda x: x[1], file_meta_array)), convert_to_opus=True)
        print(write_refs)
        write_file_data(file, file_meta_array, xor_mask, write_refs, True)


def _get_file_md5(path: os.PathLike) -> str:
    filehash = hashlib.md5()
    with open(path, "rb") as f:
        size = f.seek(0, os.SEEK_END)
        chunk_size = 1024
        f.seek(0)
        while f.tell() != size:
            if size - f.tell() < chunk_size:
                chunk_size = size - f.tell()
            buf = f.read(chunk_size)
            filehash.update(buf)
    return filehash.hexdigest()


def create_sng_filename(sng_dir: os.PathLike) -> str:
    filehash = hashlib.md5()
    for file_name in sorted(os.listdir(sng_dir)):
        path = os.path.join(sng_dir, file_name)
        filehash.update(file_name.encode("utf-8"))
        filehash.update(_get_file_md5(path).encode())
    return filehash.hexdigest()


def gather_files_from_directory(
    directory: os.PathLike, *, offset: int, allow_nonsng_files: bool
) -> List[Tuple[str, SngFileMetadata]]:
    """
    Gathers and prepares file metadata for all files in a given directory, excluding 'song.ini'.

    Each file's metadata includes its name, size, and offset position within the SNG file.

    Args:
        directory (os.PathLike): The directory to scan for files.
        offset (int): The initial offset where file data will start in the SNG file.
        allow_nonsng_files (bool): Allow encoding of files not allowed by the sng standard.

    Returns:
        List[Tuple[str, SngFileMetadata]]: A list of tuples containing file paths and their corresponding metadata objects.
    """
    file_meta_array = []
    current_index = offset

    for filename in os.listdir(directory):
        if _illegal_filename(filename):
            logger.warn("Illegal filename: %s. Skipping", filename)
            continue
        if not _valid_sng_file(filename):
            if filename in SNG_RESERVED_FILES:
                logger.debug("%s is reserved, skipping", filename)
                continue
            logger.warning(
                "Found encoded file not set by the sng standard: %s", filename
            )
            if not allow_nonsng_files:
                logger.warning(
                    "Allowing non-sng files is set to False, skipping file %s.",
                    filename,
                )
                continue
            logger.warning(
                "Allowing non-sng files is set to True, encoding file %s.", filename
            )

        file, ext = filename.split('.')

        filepath = os.path.join(directory, filename)
        if os.path.isfile(filepath):
            with open(filepath, "rb") as file:
                size = file.seek(0, os.SEEK_END)

            file_meta = SngFileMetadata(filename, size, current_index)
            file_meta_array.append((filepath, file_meta))

            current_index += size

    return file_meta_array


def read_file_meta(filedir: os.PathLike) -> SngMetadataInfo:
    """
    Reads metadata from a 'song.ini' file located in the given directory.

    The metadata is expected to be under a '[Song]' section in the INI file.

    Args:
        filedir (os.PathLike): The directory containing the 'song.ini' file.

    Returns:
        SngMetadataInfo: A dictionary containing the metadata key-value pairs.
    """
    cfg = ConfigParser()
    ini_path = os.path.join(filedir, "song.ini")
    if not os.path.exists(ini_path):
        raise FileNotFoundError(
            "song.ini not found in provided directory '%s'." % filedir
        )
    with open(ini_path) as f:
        cfg.read_file(f)
    if 'song' in cfg:
        return dict(cfg['song'])
    return dict(cfg["Song"])
