import argparse

import os
import logging

import sys

from pathlib import Path
from queue import Queue, Empty
from threading import Thread
from typing import Callable, NoReturn


from . import decode_sng, encode_sng


def main():
    parser = create_args()
    args = parse_args(parser)
    args.func(args)


logger = logging.getLogger(__package__)


def _int_range(*,min_val: int | None=None, max_val: int | None=None) -> Callable[[int], int | NoReturn]:
    def _check(val: int) -> int:
        if min_val is not None and val < min_val:
            raise argparse.ArgumentTypeError(f"Value {val} is less than minimum {min_val}.")
        if max_val is not None and val > max_val:
            raise argparse.ArgumentTypeError(f"Value {val} is greater than maximum {max_val}.")
        return val
    return _check

def parse_args(parser: argparse.ArgumentParser) -> argparse.Namespace:
    args = parser.parse_args()
    log_levels = [logging.ERROR, logging.WARNING, logging.INFO, logging.DEBUG]
    log_level = min(args.log_level, max(args.log_level, len(log_levels) - 1))
    log_level: int = log_levels[log_level]
    logging.basicConfig(
        stream=sys.stdout,
        level=log_level,
        format="[%(asctime)s - %(name)s:%(module)s:%(lineno)d] %(levelname)s: %(message)s",
    )
    logger.info("Initialized logging to %s", logging.getLevelName(log_level))
    return args


def create_args() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "-v",
        action="count",
        default=0,
        help="Logging level to use, more log info is shown by adding more `v`'s",
        dest="log_level",
    )
    parser.add_argument(
        "-t",
        "--threads",
        type=_int_range(min_val=1),
        default=1,
        help="Number of threads to use for encoding/decoding. Default: %(default)s",
        metavar="num_threads",
        dest="num_threads",
    )

    subparser = parser.add_subparsers(
        title="action",
        metavar="{encode|decode}",
        description="Encode to or decode from an sng file. For futher usage, run %(prog)s {encode|decode} -h",
        required=True,
    )

    encode = subparser.add_parser("encode")
    encode.add_argument(
        "sng_dir",
        type=Path,
        nargs="+",
        help="Directory to encode in the sng format",
        metavar="song_dir",
    )
    encode.add_argument(
        "-o",
        "--out-file",
        type=Path,
        help="The output path of the SNG file. Defaults to the md5 sum of the containing files of the target dir.",
        default=None,
        metavar="path/to/encoded.sng",
        dest="out_file",
    )
    encode.add_argument(
        "-i",
        "--ignore-nonsng-files",
        action="store_false",
        help="Allow encoding of files not allowed by the sng standard. Default: %(default)s.",
        default=True,
        dest="ignore_nonsng_files",
    )
    encode.add_argument(
        "-f",
        "--force",
        action="store_true",
        help="Overwrite existing files or directories. Default: %(default)s.",
        default=False,
        dest="force",
    )
    encode.add_argument(
        "-V",
        "--version",
        metavar="sng_version",
        type=int,
        help="sng format version to use.",
        default=1,
        dest="version",
    )
    encode.add_argument(
        "-e",
        "--encode-audio",
        help="Encode the audio files to opus. Default: %(default)s.",
        action="store_true",
        default=False,
        dest="encode_audio",
    )
    encode.set_defaults(func=run_encode)

    decode = subparser.add_parser("decode")
    decode.add_argument(
        "sng_file",
        type=Path,
        nargs="+",
        metavar="path/to/sng/file",
        help="SNG file(s) to decode"
    )
    decode.add_argument(
        "-o",
        "--out-dir",
        type=Path,
        metavar="path/to/out/folder",
        help="The output directory of sng file's directory. Default: %(default)s (current working dir)",
        default=Path(os.path.abspath(os.path.curdir)),
        dest="out_dir",
    )
    decode.add_argument(
        "-i",
        "--ignore-nonsng-files",
        action="store_false",
        help="Allow decoding of files not allowed by the sng standard. Default: %(default)s",
        default=True,
        dest="ignore_nonsng_files",
    )
    decode.add_argument(
        "-d",
        "--sng-dir",
        metavar="relative/to/out_dir",
        type=Path,
        help="The output directory containing the decoded sng file contents. Generated from metadata if not specified",
        default=None,
        dest="sng_dir",
    )
    decode.add_argument(
        "-f",
        "--force",
        action="store_true",
        help="Overwrite existing files or directories. Defaults: %(default)s",
        default=False,
        dest="force",
    )

    decode.set_defaults(func=run_decode)
    parser.usage = (
        "\n  " + encode.format_usage()[7:] + "  " + decode.format_usage()[7:] + "\n"
    )
    return parser


def run_encode(args: argparse.Namespace) -> None:
    task_queue: Queue[Path] = Queue()

    def worker():
        while True:
            try:
                sng_dir: Path = task_queue.get(block=False)
            except Empty:
                logger.debug("No more tasks in the queue, exiting worker thread.")
                break
            try:
                logger.info("Encoding %s...", sng_dir)
                encode_sng(
                    dir_to_encode=sng_dir,
                    output_filename=args.out_file if len(args.sng_dir) == 1 else None,
                    version=args.version,
                    overwrite=args.force,
                    allow_nonsng_files=not args.ignore_nonsng_files,
                    encode_audio=args.encode_audio,
                )
                logger.info("Encoded %s successfully.", sng_dir)
            except (FileExistsError, ValueError, RuntimeError) as err:
                logger.error("Failed to encode %s. Error: %s", sng_dir, err)
                logger.debug("Stack trace:", exc_info=sys.exc_info())
                
                break
        task_queue.task_done()
    for sng_dir in args.sng_dir:
        if not sng_dir.is_dir():
            logger.error("The provided path %s is not a directory.", sng_dir)
            continue
        task_queue.put(sng_dir)
    for idx in range(min(len(args.sng_dir), args.num_threads)):
        thread = Thread(target=worker, name=f"Encoder-{idx}")
        thread.start()


def run_decode(args: argparse.Namespace) -> None:
    task_queue: Queue[Path] = Queue()

    def worker():
        while True:
            try:
                sng_file: Path = task_queue.get(block=False)
            except Empty:
                logger.debug("No more tasks in the queue, exiting worker thread.")
                break
            try:
                logger.info("Encoding %s...", sng_file)
                decode_sng(
                    sng_file=sng_file,
                    outdir=args.out_dir,
                    allow_nonsng_files=not args.ignore_nonsng_files,
                    sng_dir=args.sng_dir,
                    overwrite=args.force,
                )
                logger.info("Encoded %s successfully.", sng_file)
            except (FileExistsError, ValueError, RuntimeError) as err:
                logger.error("Failed to encode %s. Error: %s", sng_file, err)
                logger.debug("Stack trace:", exc_info=sys.exc_info())
                
                break
        task_queue.task_done()
    for sng_file in args.sng_file:
        if not sng_file.is_file():
            logger.error("The provided path %s is not a directory.", sng_file)
            continue
        task_queue.put(sng_file)
    for idx in range(min(len(args.sng_file), args.num_threads)):
        thread = Thread(target=worker, name=f"Encoder-{idx}")
        thread.start()


if __name__ == "__main__":
    main()
