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

from . import exceptions, io, model
from . import __version__


#: Path to configuration file.
PATH_CONFIGFILE = "~/.ngsgluttonrc"

#: Choices for status update
STATUS_CHOICES = model.STATUSES

#: Choices for status update
STATUS_CAT_CHOICES = ('sequencing', 'conversion', 'delivery')

#: The default message signature
DEFAULT_MESSAGE_SIGNATURE = (
    '\n-- \nThis message was added by Flowcelltool client '
    'ngs-glutton v{}'.format(__version__))


class UrlHelper:
    """Helper class for generating URLs into Flowcelltool"""

    def __init__(self, base_url):
        #: The base URL
        self.base_url = base_url

    def sm_by_vendor_id(self, vendor_id):
        """Return URL to "sequencing machine by vendor ID" API endpoint."""
        tpl = '/flowcells/api/v0/sequencingmachine/by_vendor_id/{vendor_id}/'
        return self.base_url + tpl.format(vendor_id=vendor_id)

    def fc_retrieve_sheet(self, uuid):
        """Retrieve sample sheet."""
        tpl = '/flowcells/api/v0/flowcell/{uuid}/sample_sheet/'
        return self.base_url + tpl.format(uuid=uuid)

    def fc_by_vendor_id(self, vendor_id):
        """Return URL to "flowcell by vendor ID" API endpoint."""
        tpl = '/flowcells/api/v0/flowcell/by_vendor_id/{vendor_id}/'
        return self.base_url + tpl.format(vendor_id=vendor_id)

    def fc_detail(self, uuid):
        """Return URL to "update flowcell" API endpoint."""
        tpl = '/flowcells/api/v0/flowcell/{uuid}/'
        return self.base_url + tpl.format(uuid=uuid)

    def fc_create(self):
        """Return URL to create flowcell" API endpoint."""
        tpl = '/flowcells/api/v0/flowcell/'
        return self.base_url + tpl

    def fc_add_message(self, uuid):
        """Return URL to add message" API endpoint."""
        tpl = '/flowcells/api/v0/flowcell/{uuid}/add_message/'
        return self.base_url + tpl.format(uuid=uuid)


class NgsGluttonAppBase:
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
        #: Headers for authentication in POST request
        self.auth_headers = {
            'Authorization': 'Token {token}'.format(
                token=self.args.flowcelltool_auth_token),
        }

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
                self.args.flowcelltool_url is None):
            self.args.flowcelltool_url = self.config.get('flowcelltool', 'url')
        if (self.config.get('flowcelltool', 'auth_token') and
                self.args.flowcelltool_auth_token is None):
            self.args.flowcelltool_auth_token = self.config.get(
                'flowcelltool', 'auth_token')

    def _check_args(self):
        # Auth token required if URL is given
        if (self.args.flowcelltool_url and
                not self.args.flowcelltool_auth_token):
            raise exceptions.InvalidCommandLineArguments(
                '--flowcelltool-auth-token must be given if '
                '--flowcelltool-url is')

    def _flowcell_by_vendor_id(self, folder):
        # Resolve flowcell vendor ID to UUID
        logging.info(
            'GET %s', self.url_helper.fc_by_vendor_id(
                folder.run_info.flowcell))
        res = requests.get(
            self.url_helper.fc_by_vendor_id(
                folder.run_info.flowcell), headers=self.auth_headers)
        if not res.ok:
            logging.error('Problem with retrieving UUID by vendor ID')
            logging.error('Server said: %s', res.text)
            raise exceptions.UnknownFlowcellException(
                'Could not retrieve flowcell by vendor ID!')
        fc = res.json()
        logging.debug('Flowcell JSON: %s', fc)
        return fc

    def run(self):
        folder = io.parse_run_folder(Path(self.args.run_folder))
        return self._run_impl(folder)

    def _run_impl(self, folder: model.RunFolder):
        raise NotImplementedError('Override me!')


class NgsGluttonExtractApp(NgsGluttonAppBase):
    """Extract information from flow cell directory"""

    def _run_impl(self, folder: model.RunFolder):
        result = {'folder': folder}
        # Sample adapter sequences (called "indexed reads" by Illumina)
        if self.args.extract_adapters:
            result['info_adapters'] = io.sample_indexed_reads(
                result['folder'], num_reads=self.args.num_reads)
        # Read quality score information
        if self.args.extract_quality_scores:
            result['info_quality_scores'] = io.read_quality_scores(
                result['folder'])
        # Extract information about reads
        if self.args.extract_reads:
            result['info_final_reads'] = folder.run_info.read_descriptions
        if self.args.extract_planned_reads:
            result['info_planned_reads'] = (
                folder.run_parameters.planned_read_descriptions)
        # Output the resulting information
        self._output_result(result)

    def _output_result(self, result):
        """Output the resulting information depending on the configuration."""
        if self.args.flowcelltool_url:
            self._update_or_create_flowcell(result)
        if self.args.output_json:
            logging.info('Writing JSON to %s', self.args.output_json)
            with open(self.args.output_json, 'wt') as outputf:
                simplejson.dump(result, outputf, indent=4, cls=io.JsonEncoder)
        if not self.args.flowcelltool_url and not self.args.output_json:
            logging.info('Writing JSON to stdout')
            simplejson.dump(result, sys.stdout, indent=4, cls=io.JsonEncoder)

    def _update_or_create_flowcell(self, result):
        """Update flow cell or create if necessary."""
        logging.info('Retrieving flowcell via API...')
        try:
            fc = self._flowcell_by_vendor_id(result['folder'])
            logging.info('=> UUID=%s', fc['uuid'])
        except exceptions.UnknownFlowcellException as e:
            logging.info('=> unknown, creating new')
            exists = False
        else:
            exists = True
        if exists:
            self._update_flowcell(result, fc)
        else:
            self._create_flowcell(result)

    def _create_flowcell(self, result):
        run_info = result['folder'].run_info
        run_params = result['folder'].run_parameters
        logging.info('Resolving instrument to UUID...')
        res = requests.get(
            self.url_helper.sm_by_vendor_id(run_info.instrument),
            headers=self.auth_headers)
        if not res.ok:
            msg = 'Could not find machine with ID {}'.format(
                run_info.instrument)
            raise exceptions.NgsGluttonException(msg)
        else:
            sm = res.json()
        logging.info('Creating flowcell...')
        data = {
            'run_date': run_info.date.isoformat(),
            'run_number': run_params.run_number,
            'slot': run_params.flowcell_slot,
            'vendor_id': run_info.flowcell,
            'sequencing_machine': sm['uuid'],
            'label': run_params.experiment_name,
            'num_lanes': run_info.lane_count,
            'status_sequencing': io.get_sequencing_status(result['folder']),
            'operator': self.args.operator,
            'rta_version': int(run_params.rta_version.split('.')[0]),
        }
        for key in ('adapters', 'quality_scores', 'planned_reads',
                    'final_reads'):
            if ('info_%s' % key) in result:
                data['info_%s' % key] = simplejson.dumps(
                    result['info_%s' % key], cls=io.JsonEncoder)
        res = requests.post(
            self.url_helper.fc_create(),
            data=data,
            headers=self.auth_headers)
        if not res.ok:
            logging.error('Problem with creating flowcell')
            logging.error('Server said: %s', res.text)
            msg = 'Could not create flowcell: {}'.format(res.text)
            raise exceptions.NgsGluttonException(msg)
            logging.debug('Flowcell JSON: %s', res.json())

    def _update_flowcell(self, result, fc):
        data = {}
        data['status_sequencing'] = io.get_sequencing_status(
            result['folder'], fc['status_sequencing'])
        for key in ('adapters', 'quality_scores', 'planned_reads',
                    'final_reads'):
            k = ('info_%s' % key)
            if k in result and fc[k] != result[k]:
                data[k] = simplejson.dumps(result[k], cls=io.JsonEncoder)
        logging.info('PATCH %s', self.url_helper.fc_detail(fc['uuid']))
        logging.debug('=> data = %s', data)
        res = requests.patch(
            self.url_helper.fc_detail(fc['uuid']),
            data=data,
            headers=self.auth_headers)
        if not res.ok:
            logging.error('Problem with updating flowcell')
            logging.error('Server said: %s', res.text)
            msg = 'Could not update flowcell: {}'.format(res.text)
            raise exceptions.NgsGluttonException(msg)
        else:
            logging.debug('Flowcell JSON: %s', res.json())


class NgsGluttonUpdateStatusApp(NgsGluttonAppBase):
    """Update status from flow cell directory."""

    def _run_impl(self, folder: model.RunFolder):
        if not self.args.flowcelltool_url:
            msg = 'This command requires a flowcelltool URL.'
            raise exceptions.InvalidCommandLineArguments(msg)
        fc = self._flowcell_by_vendor_id(folder)
        data = {}
        for cat, val in zip(self.args.status_category, self.args.status_value):
            data['status_{}'.format(cat)] = val
        logging.info('PATCH %s', self.url_helper.fc_detail(fc['uuid']))
        logging.debug('=> data = %s', data)
        res = requests.patch(
            self.url_helper.fc_detail(fc['uuid']),
            data=data,
            headers=self.auth_headers)


class NgsGluttonRetrieveStatusApp(NgsGluttonAppBase):

    def _run_impl(self, folder: model.RunFolder):
        if not self.args.flowcelltool_url:
            msg = 'This command requires a flowcelltool URL.'
            raise exceptions.InvalidCommandLineArguments(msg)
        fc = self._flowcell_by_vendor_id(folder)
        print(fc['status_%s' % self.args.category])


class NgsGluttonRetrieveDeliveryType(NgsGluttonAppBase):

    def _run_impl(self, folder: model.RunFolder):
        if not self.args.flowcelltool_url:
            msg = 'This command requires a flowcelltool URL.'
            raise exceptions.InvalidCommandLineArguments(msg)
        fc = self._flowcell_by_vendor_id(folder)
        print(fc['delivery_type'])


class NgsGluttonRetrieveLaneCount(NgsGluttonAppBase):

    def _run_impl(self, folder: model.RunFolder):
        if not self.args.flowcelltool_url:
            msg = 'This command requires a flowcelltool URL.'
            raise exceptions.InvalidCommandLineArguments(msg)
        fc = self._flowcell_by_vendor_id(folder)
        print(fc['num_lanes'])


class NgsGluttonRetrieveSampleSheetApp(NgsGluttonAppBase):

    def _run_impl(self, folder: model.RunFolder):
        if not self.args.flowcelltool_url:
            msg = 'This command requires a flowcelltool URL.'
            raise exceptions.InvalidCommandLineArguments(msg)
        fc = self._flowcell_by_vendor_id(folder)
        if not fc['libraries']:
            logging.info(
                'Flow cell has not libraries, write empty sheet file')
            with open(self.args.output_path, 'wt') as outputf:
                print('', file=outputf)
        else:
            res = requests.get(
                self.url_helper.fc_retrieve_sheet(fc['uuid']),
                headers=self.auth_headers)
            with open(self.args.output_path, 'wt') as outputf:
                print(res.text, file=outputf)


class NgsGluttonGetStatusApp(NgsGluttonAppBase):
    """Get status from flow cell directory."""

    def _run_impl(self, folder: model.RunFolder):
        if not self.args.flowcelltool_url:
            msg = 'This command requires a flowcelltool URL.'
            raise exceptions.InvalidCommandLineArguments(msg)
        fc = self._flowcell_by_vendor_id(folder)
        print(io.get_sequencing_status(folder))


class NgsGluttonAddMessageApp(NgsGluttonAppBase):
    """Add message for flowcell."""

    def _run_impl(self, folder: model.RunFolder):
        if not self.args.flowcelltool_url:
            msg = 'This command requires a flowcelltool URL.'
            raise exceptions.InvalidCommandLineArguments(msg)
        fc = self._flowcell_by_vendor_id(folder)
        logging.info('POST %s', self.url_helper.fc_add_message(fc['uuid']))
        res = requests.post(
            self.url_helper.fc_add_message(fc['uuid']),
            data={
                'title': self.args.subject,
                'body': self.args.body.read() + self.args.message_signature,
                'mime_type': self.args.mime_type,
            },
            files=[
                ('attachments', open(fname, 'rb'))
                for fname in self.args.attachments
            ],
            headers=self.auth_headers)
        if not res.ok:
            logging.error('Problem with adding message')
            logging.error('Server said: %s', res.text)
            raise exceptions.NgsGluttonException(
                'Could not add message!')
        logging.debug('Flowcell JSON: %s', fc)


def run(args):
    """Program entry point after parsing arguments."""
    return args.app_class(args).run()


def main(argv=None):
    """Main entry point for parsing command line arguments."""
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(
        dest='command', help='Select the command to execute')
    subparsers.required = True

    parser.add_argument(
        '--version', action='version', version='%(prog)s {}'.format(
            __version__))
    parser.add_argument(
        '--verbose', '-v', dest='verbose', default=False, action='store_true',
        help='Enable verbose logging')
    parser.add_argument(
        '--config-file', default=PATH_CONFIGFILE,
        help='Path to INI-style configuration file'
    )

    group = parser.add_argument_group(
        'Input/Output Options',
        'You can give a JSON file to write to or a URL with a Flowcelltool '
        'instance to write results to.  If neither is given, results will '
        'be written to stdout.')
    group.add_argument(
        '--run-folder', '-r', type=str, required=True,
        help='Path to run folder.')
    group.add_argument(
        '--flowcelltool-url',
        help=('Base URL to Flowcelltool for posting to (enables result '
              'posting).'))
    group.add_argument(
        '--flowcelltool-auth-token',
        help='Authentication token for result posting.')

    # Sub command: ngs-glutton get-status
    parser_extract = subparsers.add_parser(
        'get-status', help='Get sequencing status.')
    parser_extract.set_defaults(app_class=NgsGluttonGetStatusApp)

    # Sub command: ngs-glutton extract

    parser_extract = subparsers.add_parser(
        'extract', help='Extract information from raw flowcell data.')
    parser_extract.set_defaults(app_class=NgsGluttonExtractApp)

    group = parser_extract.add_argument_group(
        'Extraction Options')
    group.add_argument(
        '--extract-planned-reads', default=False, action='store_true',
        help='Extracted planned reads information from RunParameters.xml')
    group.add_argument(
        '--extract-reads', default=False, action='store_true',
        help='Extracted (final) reads information from RunInfo.xml')
    group.add_argument(
        '--extract-adapters', default=False, action='store_true',
        help='Extract adapter sequences from raw output directory')
    group.add_argument(
        '--extract-quality-scores', default=False, action='store_true',
        help='Extract quality scores from raw output directory')

    group = parser_extract.add_argument_group(
        'Sampling-related Options',
        'Configuration of read sampling')
    group.add_argument(
        '--num-reads', type=int, default=10_000_000,
        help='Number of reads to read')

    group = parser_extract.add_argument_group('Labels')
    group.add_argument(
        '--operator', help='Name of the operator to set.')

    group = parser_extract.add_argument_group('Input / Output Options')
    group.add_argument(
        '--output-json', '-o', type=str,
        help='Path to output summary JSON file.')

    # Sub command: ngs-glutton update-status

    parser_update_status = subparsers.add_parser(
        'update-status', help='Update status of flowcell in Flowcelltool')
    parser_update_status.set_defaults(app_class=NgsGluttonUpdateStatusApp)

    parser_update_status.add_argument(
        '--status-category', choices=STATUS_CAT_CHOICES,
        required=True, default=[], action='append', nargs='+',
        help='The status category to set.')
    parser_update_status.add_argument(
        '--status-value', choices=STATUS_CHOICES, required=True,
        default=[], action='append', nargs='+',
        help='The new status to set.')

    # Sub command: ngs-glutton retrieve-sample-sheet

    parser_retrieve_sheet = subparsers.add_parser(
        'retrieve-sample-sheet', help='Retrieve sample sheet')
    parser_retrieve_sheet.set_defaults(
        app_class=NgsGluttonRetrieveSampleSheetApp)

    parser_retrieve_sheet.add_argument(
        '--output-path', required=True, help='Path to write sheet to.')

    # Sub command: ngs-glutton retrieve-sample-sheet

    parser_retrieve_delivery_type = subparsers.add_parser(
        'retrieve-delivery-type', help='Retrieve delivery-type')
    parser_retrieve_delivery_type.set_defaults(
        app_class=NgsGluttonRetrieveDeliveryType)

    # Sub command: ngs-glutton retrieve-sample-sheet

    parser_retrieve_lane_count = subparsers.add_parser(
        'retrieve-lane-count', help='Retrieve the line count')
    parser_retrieve_lane_count.set_defaults(
        app_class=NgsGluttonRetrieveLaneCount)

    # Sub command: ngs-glutton retrieve-status

    parser_retrieve_status = subparsers.add_parser(
        'retrieve-status', help='Retrieve status')
    parser_retrieve_status.set_defaults(
        app_class=NgsGluttonRetrieveStatusApp)
    parser_retrieve_status.add_argument(
        '--status-category', choices=STATUS_CAT_CHOICES,
        required=True, help='The status category to retrieve.')

    # Sub command: ngs-glutton add-message

    parser_add_message = subparsers.add_parser(
        'add-message', help='Add message in Flowcelltool')
    parser_add_message.set_defaults(app_class=NgsGluttonAddMessageApp)

    parser_add_message.add_argument(
        '--subject', required=True, help='Set subject of message')
    parser_add_message.add_argument(
        '--body', required=True, type=argparse.FileType('rt'),
        help='Path to text file with body of message')
    parser_add_message.add_argument(
        '--mime-type', default='text/plain',
        choices=('text/plain', 'text/markdown'),
        help='Mime type of the message')
    parser_add_message.add_argument(
        '--message-signature', default=DEFAULT_MESSAGE_SIGNATURE)
    parser_add_message.add_argument(
        '--attachment', dest='attachments', default=[], action='append',
        nargs='+', help='File to attach to message')

    args = parser.parse_args(argv)

    # Flatten attachment list if any
    if getattr(args, 'attachments', []):
        args.attachments = [
            item for sublist in args.attachments for item in sublist]
    if getattr(args, 'status_value', []):
        args.status_value = [
            item for sublist in args.status_value for item in sublist]
    if getattr(args, 'status_category', []):
        args.status_category = [
            item for sublist in args.status_category for item in sublist]
    if (args.command == 'update-status' and
            len(args.status_value) != len(args.status_category)):
        parser.error('Entry count in --status-category and --status-value '
                     'has to be the same')

    return run(args)


if __name__ == '__main__':
    sys.exit(main())
