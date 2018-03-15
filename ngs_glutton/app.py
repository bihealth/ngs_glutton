# -*- coding: utf-8 -*-
"""Main entry point"""

import argparse
import logging
from pathlib import Path
import simplejson
import sys

from . import io


def run(args):
    """Entry point after parsing command line arguments."""
    FORMAT = '%(asctime)-15s %(levelname)-8s %(message)s'
    logging.basicConfig(format=FORMAT)
    logger = logging.getLogger()
    if args.verbose:
        logger.setLevel(logging.DEBUG)
    else:
        logger.setLevel(logging.INFO)

    folder = io.parse_run_folder(Path(args.run_folder))
    stats = io.sample_indexed_reads(folder, num_reads=args.num_reads)
    with open(args.output_json, 'wt') as outputf:
        simplejson.dump(stats, outputf)


def main(argv=None):
    """Main entry point for parsing command line arguments."""
    parser = argparse.ArgumentParser()

    parser.add_argument(
        '--verbose', '-v', dest='verbose', default=False, action='store_true',
        help='Enable verbose logging')

    parser.add_argument(
        '--num-reads', type=int, default=10_000,
        help='Number of reads to read')
    parser.add_argument(
        '--run-folder', '-r', type=str, required=True,
        help='Path to run folder.')
    parser.add_argument(
        '--output-json', '-o', type=str, required=True,
        help='Path to output summary JSON file.')

    args = parser.parse_args(argv)
    return run(args)


if __name__ == '__main__':
    sys.exit(main())
