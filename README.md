# sng-format-python
-----------------------
Python implementation for parsing and handling .sng files. [See the .sng format spec for information](https://github.com/mdsitton/SngFileFormat/tree/main).

It is capable of reading SNG files, extracting metadata, file indexes, and file data. There is a function to write to disk as well.

I have not tested this thoroughly, but I've had zero issues with it so far.

# Instalation
## From pip
``` shell
pip install sng-parser
```

## From repository
``` shell
git clone https://github.com/joshrmcdaniel/sng-format-python.git
cd sng-format-python
pip install -e .
```

# Usage


The only functions a user should use for deconding and encoding is `decode_sng`, and `encode_sng`. The other functions are internal helpers.

`decode_sng` takes the following arguments:
- Keyword or passed arg:
    - `sng_file`: os.PathLike | str | BufferedReader
        - Can be the path to the sng file to parse, or a buffer
- Keyword only:
    - `outdir`: Optional[os.PathLike | str]
        - Output directory to write the song file to, defaults to the working directory
    - `allow_nonsng_files`: bool
        - Allow files encoded not specified by the sng stardard to be decoded, defaults to `False`
    - `sng_dir`: Optional[os.PathLike | str]
        - Directory containing the decoded files when writing to `outdir`, generated from metadata if not specified (`<artist_name> - <song_name> (<charter>)`)
    - `overwrite` : bool
        - Overwrite the existing directory if it already exists, defaults to `False`

`encode_sng` takes the following arguments:
- Keyword or passed arg:
    -  `dir_to_encode (os.PathLike)`: The directory containing files to be encoded into the SNG format
- Keyword only:
    - `output_filename`: Optional[os.PathLike]
        - The path to the output SNG file. Defaults to the md5 sum of the containing files of converted dir.
    - `allow_nonsng_files`: Optional[bool]
        - Allow encoding of files not allowed by the sng standard. Defaults to `False`.
    - `overwrite`: Optional[bool]
        - If `True`, existing files or directories will be overwritten. Defaults to `False`.
    - `version`: Optional[int]
        - The version of the SNG format to use. Defaults to `1`.
    - `xor_mask`: Optional[bytes]
        - XOR mask for encryption. If not provided, a random one is generated.
    - `metadata`: Optional[SngMetadataInfo]: 
        - Metadata for the SNG package. If not provided, it's read from a 'song.ini' file in the directory.

## Example usage

```python

from sng_parser import decode_sng, encode_sng

outdir = 'test'
# Basic usage
## Decoding
decode_sng('example.sng', sng_dir=outdir)

## Encoding
encode_sng(outdir)

# Decode to `/name` with contents under `jeff` (sng files located in /name/jeff/)
decode_sng('example.sng', outdir='/name', sng_dir='jeff')

# Decode with file handler
with open('example.sng', 'rb') as f:
    decode_sng(f)

# Decode ignoring non-standard .sng files
decode_sng('example.sng', allow_nonsng_files=True)

# Encode ignoring non-standard .sng files
encode_sng(outdir, allow_nonsng_files=True)

```