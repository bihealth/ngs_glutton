# -*- coding: utf-8 -*-
"""Main entry point"""

import argparse
import configparser
import logging
import os.path
from pathlib import Path
import requests
import simplejson
import sys

from . import io, exceptions

#: Path to configuration file.
PATH_CONFIGFILE = "~/.ngsgluttonrc"


class UrlHelper:
    """Helper class for generating URLs into Flowcelltool"""

    def __init__(self, base_url):
        #: The base URL
        self.base_url = base_url

    def fc_by_vendor_id(self, vendor_id):
        """Return URL to "flowcell by vendor ID" API endpoint."""
        tpl = '/flowcells/api/v0/flowcell/by_vendor_id/{vendor_id}/'
        return self.base_url + tpl.format(vendor_id=vendor_id)

    def fc_update(self, pk):
        """Return URL to "update flowcell" API endpoint."""
        tpl = '/flowcells/api/v0/flowcell/{pk}/update/'
        return self.base_url + tpl.format(pk=pk)


class NgsGluttonApp:
    """The main class of the app."""

    def __init__(self, args):
        #: Command line arguments, some default values can come from
        #: configuration file.
        self.args = args
        # Setup the logging infrastructure
        self._setup_logging()
        #: Configuration from configuration file
        self.config = self._load_config(self.args.config_file)
        # Update arguments from configuration and check
        self._update_args_from_config()
        self._check_args()
        #: Helper for building Flowcelltool URLs
        self.url_helper = UrlHelper(self.args.flowcelltool_url)

    def _setup_logging(self):
        """Setup the logging."""
        FORMAT = '%(asctime)-15s %(levelname)-8s %(message)s'
        logging.basicConfig(format=FORMAT)
        logger = logging.getLogger()
        if self.args.verbose:
            logger.setLevel(logging.DEBUG)
        else:
            logger.setLevel(logging.INFO)

    def _load_config(self, path_configfile):
        """Load configuration from ~/.ngsgluttonrc, if it exists"""
        config = configparser.ConfigParser()
        if not path_configfile:
            logging.info('Config file %s not found', path_configfile)
            return config
        realpath_configfile = os.path.abspath(os.path.expanduser(
            path_configfile))
        if os.path.exists(realpath_configfile):
            logging.info('Loading configuration from %s (realpath: %s)',
                         path_configfile, realpath_configfile)
            config.read(realpath_configfile)
        return config

    def _update_args_from_config(self):
        if (self.config.get('flowcelltool', 'url') and
                not self.args.flowcelltool_url):
            self.args.flowcelltool_url = self.config.get('flowcelltool', 'url')
        if (self.config.get('flowcelltool', 'auth_token') and
                not self.args.flowcelltool_auth_token):
            self.args.flowcelltool_auth_token = self.config.get(
                'flowcelltool', 'auth_token')

    def _check_args(self):
        # Auth token required if URL is given
        if (self.args.flowcelltool_url and
                not self.args.flowcelltool_auth_token):
            raise exceptions.InvalidCommandLineArguments(
                '--flowcelltool-auth-token must be given if '
                '--flowcelltool-url is')

    def run(self):
        """Run the app."""
        result = {}
        # Read basic flowcell meta data
        result['folder'] = io.parse_run_folder(Path(self.args.run_folder))
        # Sample adapter sequences (called "indexed reads" by Illumina)
        if self.args.extract_adapters:
            result['adapter_stats'] = io.sample_indexed_reads(
                result['folder'], num_reads=self.args.num_reads)
        # Read quality score information
        if self.args.extract_quality_scores:
            result['quality_scores'] = io.read_quality_info(result['folder'])
        # Output the resulting information
        self._output_result(result)

    def _output_result(self, result):
        """Output the resulting information depending on the configuration."""
        if self.args.flowcelltool_url:
            logging.info('Updating flowcell via Flowcelltool API')
            auth_headers = {
                'Authorization': 'Token {token}'.format(
                    token=self.args.flowcelltool_auth_token),
            }
            # Resolve flowcell vendor ID to PK
            logging.info(
                'GET %s', self.url_helper.fc_by_vendor_id(
                    result['folder'].run_info.flowcell))
            res = requests.get(
                self.url_helper.fc_by_vendor_id(
                    result['folder'].run_info.flowcell),
                headers=auth_headers)
            if not res.status_code == 200:
                logging.error('Problem with retrieving PK by vendor ID')
                logging.error('Server said: %s', res.text)
                return 1
            fc = res.json()
            logging.debug('Flowcell JSON: %s', fc)
            # Update flowcell information through API if configured so.
            if 'adapter_stats' in result:
                logging.info('POST %s', self.url_helper.fc_update(fc['pk']))
                res = requests.post(
                    self.url_helper.fc_update(fc['pk']),
                    data={
                        'info_adapters': simplejson.dumps(
                            result['adapter_stats'])
                    },
                    headers=auth_headers)
                if not res.status_code == 200:
                    logging.error('Problem with retrieving PK by vendor ID')
                    logging.error('Server said: %s', res.text)
                    return 1
                logging.debug('Flowcell JSON: %s', res.json())
        if self.args.output_json:
            logging.info('Writing JSON to %s', self.args.output_json)
            with open(self.args.output_json, 'wt') as outputf:
                simplejson.dump(result, outputf, indent=4)
        if not self.args.flowcelltool_url and not self.args.output_json:
            logging.info('Writing JSON to stdout')
            simplejson.dump(result, sys.stdout, indent=4)


def run(args):
    """Program entry point after parsing arguments."""
    NgsGluttonApp(args).run()


def main(argv=None):
    """Main entry point for parsing command line arguments."""
    parser = argparse.ArgumentParser()

    parser.add_argument(
        '--verbose', '-v', dest='verbose', default=False, action='store_true',
        help='Enable verbose logging')
    parser.add_argument(
        '--config-file', default=PATH_CONFIGFILE,
        help='Path to INI-style configuration file'
    )

    group = parser.add_argument_group(
        'Extraction Options')
    group.add_argument(
        '--extract-adapters', default=False, action='store_true',
        help='Extract adapter sequences from raw output directory')
    group.add_argument(
        '--extract-quality-scores', default=False, action='store_true',
        help='Extract quality scores from raw output directory')

    group = parser.add_argument_group(
        'Input/Output Options',
        'You can give a JSON file to write to or a URL with a Flowcelltool '
        'instance to write results to.  If neither is given, results will '
        'be written to stdout.')
    group.add_argument(
        '--run-folder', '-r', type=str, required=True,
        help='Path to run folder.')
    group.add_argument(
        '--output-json', '-o', type=str,
        help='Path to output summary JSON file.')
    group.add_argument(
        '--flowcelltool-url',
        help=('Base URL to Flowcelltool for posting to (enables result '
              'posting).'))
    group.add_argument(
        '--flowcelltool-auth-token',
        help='Authentication token for result posting.')

    group = parser.add_argument_group(
        'Sampling-related Options',
        'Configuration of read sampling')
    group.add_argument(
        '--num-reads', type=int, default=10_000,
        help='Number of reads to read')

    args = parser.parse_args(argv)

    return run(args)


if __name__ == '__main__':
    sys.exit(main())
