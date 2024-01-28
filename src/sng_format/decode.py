import os
import struct


from configparser import ConfigParser

from .common import mask, SngMetadata


def read_filedata(buffer, offset):
    filename_len = struct.unpack_from('<B', buffer, offset)[0]
    offset += 1
    filename = struct.unpack_from(f'<{filename_len}s', buffer, offset)[0].decode()
    offset += filename_len
    contents_len, contents_index = struct.unpack_from('<QQ', buffer, offset)
    offset += 16
    metadata = SngMetadata(filename, contents_len, contents_index)
    return SngMetadata(filename, contents_len, contents_index), offset


def parse_sng(sng_buffer):
    file_identifier, version, xor_mask = struct.unpack('<6sI16s', sng_buffer[:26])
    assert file_identifier in bytes([0x53, 0x4E, 0x47, 0x50, 0x4b, 0x47]), "Not a song file."

    if file_identifier.decode() != "SNGPKG":
        raise ValueError("Invalid file identifier")

    metadata_len, metadata_count = struct.unpack_from('<QQ', sng_buffer, 26)

    offset = 26 + 16

    metadata = {}
    
    for _ in range(metadata_count):
        key_len = struct.unpack_from('<I', sng_buffer, offset)[0]
        offset += 4
        key = struct.unpack_from(f'<{key_len}s', sng_buffer, offset)[0].decode()
        offset += key_len
        value_len = struct.unpack_from('<I', sng_buffer, offset)[0]
        offset += 4
        value = struct.unpack_from(f'<{value_len}s', sng_buffer, offset)[0].decode()
        offset += value_len
        metadata[key] = value

    file_meta_len, file_count = struct.unpack_from('<QQ', sng_buffer, offset)
    offset += 16
    file_meta_array = []
    for _ in range(file_count):
        file_meta, new_offset = read_filedata(sng_buffer, offset)
        file_meta_array.append(file_meta)
        offset = new_offset

    file_data_len = struct.unpack_from('<Q', sng_buffer, offset)[0]
    offset += 8
    file_data_array = []
    for file_meta in file_meta_array:
        file_data = sng_buffer[offset:offset+file_meta.content_len]
        file_data = mask(file_data, xor_mask)
        file_data_array.append(file_data)
        offset += file_meta.content_len

    return {
        'file_identifier': file_identifier.decode(),
        'version': version,
        'xor_mask': xor_mask,
        'metadata': metadata,
        'file_meta_array': file_meta_array,
        'file_data_array': file_data_array
    }


def write_parsed_sng(parsed_data, outdir):
    if not os.path.exists(outdir):
        os.makedirs(outdir)
    cfg = ConfigParser()
    cfg.add_section('Song')
    for k, v in parsed_data['metadata'].items():
        cfg.set('Song', k, v)
    with open(os.path.join(outdir, 'song.ini'), 'w') as f:
        cfg.write(f)

    for index, file_meta in enumerate(parsed_data['file_meta_array']):
        file_data = parsed_data['file_data_array'][index]
        file_path = os.path.join(outdir, file_meta.filename)
        with open(file_path, 'wb') as file:
            file.write(file_data)


def read_sng_file(path: str) -> bytes:
    with open(path, 'rb') as f:
        d = f.read()
    return d
