import os
import re
import struct

from enum import Enum
from io import BufferedReader, BufferedWriter
from typing import Final, NamedTuple, NoReturn, Optional, Set, TypedDict, Tuple


# Constants
class StructTypes(Enum):
    """
    Enumerates the structure types used for sng data manipulation,
    ensuring consistent endianness and providing easy
    access to format characters for common data types.
    """

    ENDIAN = "<"  # Little-endian
    UINT = "I"  # Unsigned int
    ULONGLONG = "Q"  # Unsigned long long
    UBYTE = "B"  # Unsigned byte
    CHAR = "s"  # Single character


# Regex for struct format validation
STRUCT_TYPE_RE = re.compile(r"(?:([IQB])|(?:(\d+)(s)))")

# Validation for struct packing
STRUCT_VALIDATION = {
    StructTypes.UINT.value: lambda x: 0
    <= x
    <= ((1 << 32) - 1),  # 2**32-1, 4_294_967_295
    StructTypes.ULONGLONG.value: lambda x: 0
    <= x
    <= ((1 << 64) - 1),  # 2**64-1, 18_446_744_073_709_551_615
    StructTypes.UBYTE.value: lambda x: 0 <= x <= 255,  # ((2<<8)-1), 2**8-1
}

# File format version
SNG_VERSION: Final[int] = 1

# Reserved files not to be encoded
SNG_RESERVED_FILES: Final[Set[str]] = {"song.ini"}

# Note files allowed
SNG_NOTES_FILES: Final[Set[str]] = {"notes.chart", "notes.mid"}

# Audio filenames allowed
SNG_AUDIO_FILES: Final[Set[str]] = {
    "guitar",
    "bass",
    "rhythm",
    "vocals",
    "vocals_1",
    "vocals_2",
    "drums",
    "drums_1",
    "drums_2",
    "drums_3",
    "drums_4",
    "keys",
    "song",
    "crowd",
    "preview",
}

# Audio file extensions allowed
SNG_AUDIO_EXT: Final[Set[str]] = {"mp3", "ogg", "opus", "wav"}

# Image filenames allowed
SNG_IMG_FILES: Final[Set[str]] = {"album", "background", "highway"}

# Image file extensions allowed
SNG_IMG_EXT: Final[Set[str]] = {"png", "jpg", "jpeg"}

# Video filenames allowed
SNG_VIDEO_FILES: Final[Set[str]] = {"video"}

# Video file extensions allowed
SNG_VIDEO_EXT: Final[Set[str]] = {"mp4", "avi", "webm", "vp8", "ogv", "mpeg"}

# Characters not allowed in filenames
SNG_ILLEGAL_CHARS: Final[str] = r'\\<>:"/\|\?\*'

# Illegal filenames
SNG_ILLEGAL_FILENAMES: Final[Set[str]] = {
    "..",
    "CON",
    "PRN",
    "AUX",
    "NUL",
    "COM0",
    "COM1",
    "COM2",
    "COM3",
    "COM4",
    "COM5",
    "COM6",
    "COM7",
    "COM8",
    "COM9",
    "LPT0",
    "LPT1",
    "LPT2",
    "LPT3",
    "LPT4",
    "LPT5",
    "LPT6",
    "LPT7",
    "LPT8",
    "LPT9",
}


def _valid_sng_version(ver: int) -> bool:
    return 0 < ver <= SNG_VERSION


def _fail_on_invalid_sng_ver(ver: int) -> None | NoReturn:
    if not _valid_sng_version(ver):
        raise ValueError(
            f"Invalid sng version specified, must be less than or equal to the number provided (I support versions up to and including {SNG_VERSION})"
        )


def mask(data: bytes, xor_mask: bytes) -> bytearray:
    """
    Applies an XOR mask to the given data byte by byte, with an additional
    operation on the XOR key involving the index.

    The XOR key for each byte is the corresponding byte in the xor_mask,
    XORed with the lower 8 bits of the index, allowing the mask to cycle
    every 16 bytes and vary per byte position.

    Args:
        data (bytes): The input data to be masked.
        xor_mask (bytes): The mask to be applied, typically 16 bytes long.

    Returns:
        bytearray: The masked data as a mutable bytearray.
    """
    masked_data = bytearray(len(data))
    for i in range(len(data)):
        xor_key = xor_mask[i % 16] ^ (i & 0xFF)
        masked_data[i] = data[i] ^ xor_key
    return masked_data


def calc_and_unpack(fmt: str, buf: BufferedReader) -> tuple:
    """
    Calculates the size of the structure described by `fmt`, reads
    that many bytes from `buf`, and unpacks the bytes according to `fmt`.

    Args:
        fmt (str): The format string for unpacking the data.
        buf (BufferedReader): The buffer from which to read the data.

    Returns:
        tuple: The unpacked data.
    """
    read_size = struct.calcsize(fmt)
    buffer = buf.read(read_size)
    return struct.unpack_from(fmt, buffer)


def calc_and_read_buf(fmt: str, buf: BufferedReader) -> Tuple[int, bytes]:
    """
    Calculates the size required for the format `fmt`, reads that many bytes
    from the buffer `buf`, and returns the size read along with the bytes.

    Args:
        fmt (str): The format string representing the data structure to read.
        buf (BufferedReader): The buffer from which to read the data.

    Returns:
        Tuple[int, bytes]: A tuple containing the number of bytes read and the read bytes.
    """
    read_size = struct.calcsize(fmt)
    return read_size, buf.read(read_size)


def _valid_char_arg(content: bytes, pack_len: int) -> bool | NoReturn:
    """
    Validate a character in a string to pack. Internal use

    Args:
        content (bytes): Byte string to check if valid.
        pack_len (int): Length of the byte string

    Returns:
        Whether the byte string is valid or not.

    Raises:
        ValueError: When `pack_len` does not equal the length of `content`
    """
    if (e := len(content)) != pack_len:
        raise ValueError(f"String pack size difference. Expected {e}, got {pack_len}")
    return all(0 <= char <= 255 for char in content)


def _validate_and_pack(fmt: str, content: bytes | int) -> bytes:
    """
    Validate the data being packed, and pack the data if it's valid. Internal function.

    Args:
        fmt (str): Struct format string to use for packing
        content (bytes | int): Data to be packed

    Returns:
        Byte string of the packed data from the struct

    Raises:
        ValueError: When the endian string is not the endian set by the sng standard
        ValueError: When the struct fmt string is invalid
        ValueError: When `fmt` contains a char array and an invalid character is passed
        ValueError: When `fmt` has a numerical value and exceeds the byte requirements of the type
        RuntimeError: When something goes *horribly* wrong
    """
    if fmt[0] != StructTypes.ENDIAN.value:
        raise ValueError(
            f"First character in struct format is not the expected endian. Expected endian: `{StructTypes.ENDIAN.value}`"
        )
    matches = STRUCT_TYPE_RE.findall(fmt[1:])
    if matches is None:
        raise ValueError(
            "No struct characters used by sng format found in passed format."
        )
    for match in matches:
        if match[1] and match[2]:  # is char, we need to convert it.
            if not _valid_char_arg(content, int(match[1])):
                raise ValueError("Invalid byte in character string passed.")
        elif match[0]:
            if not STRUCT_VALIDATION[match[0]](content):
                raise ValueError(f"Invalid byte size for {match[0]}: {content}")
        else:
            raise RuntimeError("Something is wrong")
    return struct.pack(fmt, content)


def _with_endian(*args: Tuple[StructTypes | int]):
    """
    Constructs a format string for struct operations that includes the specified
    endian prefix followed by the format specifiers provided in `args`.

    Args:
        *args (Tuple[StructTypes | int]): A sequence of StructTypes enums or integers
        representing the number of characters.

    Returns:
        str: The format string with endian prefix.
    """
    return StructTypes.ENDIAN.value + "".join(
        map(lambda x: x.value if isinstance(x, StructTypes) else str(x), args)
    )


def _valid_img_file(filename: str, ext: str) -> bool:
    return filename in SNG_IMG_FILES and ext in SNG_IMG_EXT


def _valid_video_file(filename: str, ext: str) -> bool:
    return filename in SNG_VIDEO_FILES and ext in SNG_VIDEO_EXT


def _valid_audio_file(filename: str, ext: str) -> bool:
    return filename in SNG_AUDIO_FILES and ext in SNG_AUDIO_EXT


def _illegal_filename(file: str) -> bool:
    if file == "..":
        return False
    if len(file) > 255:
        return True
    file = file.upper()
    if file.endswith(".") or file.endswith(" "):
        return True
    if any(ord(x) < 31 for x in file):
        return True
    file = file.upper()
    if any(ilgl_chr in file for ilgl_chr in SNG_ILLEGAL_CHARS):
        return True

    filename, ext = file.rsplit(".", 2)
    return any(x in filename or x in ext for x in SNG_ILLEGAL_FILENAMES)


def _filter_illegal_chars(filename: str) -> str:
    return re.sub(rf"[{SNG_ILLEGAL_CHARS}]", "", filename)


def _valid_sng_file(file: str) -> bool:
    filename, ext = file.rsplit(".", 1)
    if file in SNG_RESERVED_FILES:
        return False
    return (
        _valid_audio_file(filename, ext)
        or _valid_img_file(filename, ext)
        or _valid_video_file(filename, ext)
        or file in SNG_NOTES_FILES
    )


def _write_and_mask(
    *,
    outfile: BufferedWriter,
    infile: BufferedReader,
    xor_mask: bytearray,
    filesize: int,
    chunk_size: int,
) -> None:
    cur_offset = infile.tell()
    expected_offset = cur_offset + filesize
    while infile.tell() != expected_offset:
        chunk_size = min(expected_offset - infile.tell(), chunk_size)
        buf = infile.read(chunk_size)
        outfile.write(mask(buf, xor_mask))


def write_and_mask(
    *,
    read_from: os.PathLike | BufferedReader,
    write_to: os.PathLike | BufferedWriter,
    xor_mask: bytearray,
    filesize: Optional[int] = None,
    chunk_size: int = 1024,
) -> int:
    passed_read_buffer = not isinstance(read_from, str)
    passed_write_buffer = not isinstance(write_to, str)

    if not passed_read_buffer:
        if os.path.exists(read_from):
            # pylint: disable=consider-using-with
            read_from = open(read_from, "rb")
        else:
            raise FileNotFoundError(f"No read file found at `{read_from}`")
    if not passed_write_buffer:
        # pylint: disable=consider-using-with
        write_to = open(write_to, "wb")

    if filesize is None:
        filesize = _calc_filesize(read_from)

    _write_and_mask(
        outfile=write_to,
        infile=read_from,
        xor_mask=xor_mask,
        filesize=filesize,
        chunk_size=chunk_size,
    )
    if not passed_read_buffer:
        read_from.close()
    if not passed_write_buffer:
        write_to.close()
    return filesize


def _calc_filesize(file: BufferedReader | BufferedWriter) -> int:

    cur = file.tell()
    size = file.seek(0, os.SEEK_END)
    file.seek(cur)
    return size


class SngFileMetadata(NamedTuple):
    """
    Represents the metadata for a file within an SNG package, including its name,
    content length, and content index (offset within the SNG file).
    """

    filename: str
    content_len: int
    content_idx: int


class SngHeader(NamedTuple):
    """
    Represents the header information of an SNG file, including the file identifier,
    version, and an XOR mask for encryption/decryption.
    """

    file_identifier: bytes
    version: int
    xor_mask: bytes


class FileOffset(NamedTuple):
    filename: str
    offset: int


class SngMetadataInfo(TypedDict):
    """
    A dictionary type that specifies the structure and expected types of metadata
    for an SNG file.
    """

    name: str
    artist: str
    album: str
    genre: str
    year: int
    diff_band: int
    diff_guitar: int
    diff_rhythm: int
    diff_guitar_coop: int
    diff_bass: int
    diff_drums: int
    diff_drums_real: int
    diff_keys: int
    diff_guitarghl: int
    diff_bassghl: int
    diff_guitar_coop_ghl: int
    diff_rhythm_ghl: int
    preview_start_time: int
    playlist_track: int
    modchart: bool
    song_length: int
    pro_drums: bool
    five_lane_drums: bool
    album_track: int
    charter: str
    hopo_frequency: int
    eighthnote_hopo: bool
    multiplier_note: int
    delay: int
    video_start_time: int
    end_events: bool
