import struct
from io import BufferedWriter, FileIO

from collections import namedtuple

SngMetadata = namedtuple('SngMetadata', ['filename', 'content_len', 'content_idx'])


def write_uint8(byte_io: bytearray | BufferedWriter, value):
    if isinstance(byte_io, bytearray):
        byte_io += struct.pack('<B', value)
    elif isinstance(byte_io, (FileIO, BufferedWriter)):
        byte_io.write(struct.pack('<B', value))


def write_uint32(byte_io: bytearray | BufferedWriter, value):
    if isinstance(byte_io, bytearray):
        byte_io += struct.pack('<I', value)
    elif isinstance(byte_io, (FileIO, BufferedWriter)):
        byte_io.write(struct.pack('<I', value))


def write_uint64(byte_io: bytearray | BufferedWriter, value):
    if isinstance(byte_io, bytearray):
        byte_io += struct.pack('<Q', value)
    elif isinstance(byte_io, (FileIO, BufferedWriter)):
        byte_io.write(struct.pack('<Q', value))


def write_string(byte_io: bytearray | BufferedWriter, value: str):
    if isinstance(byte_io, bytearray):
        byte_io += value.encode('utf-8')
    elif isinstance(byte_io, (FileIO, BufferedWriter)):
        byte_io.write(value.encode('utf-8'))


def mask(data, xor_mask):
    masked_data = bytearray(len(data))
    for i in range(len(data)):
        xor_key = xor_mask[i % 16] ^ (i & 0xFF)
        masked_data[i] = data[i] ^ xor_key
    return masked_data
