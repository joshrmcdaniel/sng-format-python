# sng-format-python
-----------------------
Python implementation for parsing and handling .sng files. [See the .sng format spec for information](https://github.com/mdsitton/SngFileFormat/tree/main).

It is capable of reading SNG files, extracting metadata, encoding audio to .opus file indexes, and file data.

I have not tested this end-to-end, but I've had zero issues with it so far.

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

``` console
foo@bar:~$ sng_parser -h
usage: 
sng_parser encode [-h] [-o path/to/encoded.sng] [-i] [-f] [-V sng_version] [-e] song_dir
sng_parser decode [-h] [-o path/to/out/folder] [-i] [-d relative/to/out_dir] [-f] sng_file

Decode/encode sng files

options:
  -h, --help       show this help message and exit
  -v               Logging level to use, more log info is shown by adding more `v`'s

action:
  Encode to or decode from an sng file. For futher usage, run sng_parser {encode|decode} -h

  {encode|decode}

foo@bar:~$ sng_parser encode -h
usage: sng_parser encode [-h] [-o path/to/encoded.sng] [-i] [-f] [-V sng_version] [-e] song_dir

positional arguments:
  song_dir              Directory to encode in the sng format

options:
  -h, --help            show this help message and exit
  -o path/to/encoded.sng, --out-file path/to/encoded.sng
                        The output path of the SNG file. Defaults to the md5 sum of the containing files of the target dir.
  -i, --ignore-nonsng-files
                        Allow encoding of files not allowed by the sng standard. Default: True.
  -f, --force           Overwrite existing files or directories. Default: False.
  -V sng_version, --version sng_version
                        sng format version to use.
  -e, --encode-audio    Encode the audio files to opus. Default: False.
foo@bar:~$ sng_parser decode -h
usage: sng_parser decode [-h] [-o path/to/out/folder] [-i] [-d relative/to/out_dir] [-f] sng_file

positional arguments:
  sng_file              Directory to encode in the sng format

options:
  -h, --help            show this help message and exit
  -o path/to/out/folder, --out-dir path/to/out/folder
                        The output directory of sng file's directory. Default: /your/working/dir (current working dir)
  -i, --ignore-nonsng-files
                        Allow decoding of files not allowed by the sng standard. Default: True
  -d relative/to/out_dir, --sng-dir relative/to/out_dir
                        The output directory containing the decoded sng file contents. Generated from metadata if not specified
  -f, --force           Overwrite existing files or directories. Defaults: False

```

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