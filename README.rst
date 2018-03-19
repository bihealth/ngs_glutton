===========
NGS Glutton
===========

.. image:: https://img.shields.io/pypi/v/ngs_glutton.svg
        :target: https://pypi.python.org/pypi/ngs_glutton

.. image:: https://img.shields.io/travis/bihealth/ngs_glutton.svg
        :target: https://travis-ci.org/bihealth/ngs_glutton

.. image:: https://readthedocs.org/projects/ngs-glutton/badge/?version=latest
        :target: https://ngs-glutton.readthedocs.io/en/latest/?badge=latest
        :alt: Documentation Status

Python app and library for reading Illumina raw instrument output.

- Free software: MIT license
- Documentation: https://ngs-glutton.readthedocs.io.

Features
--------

- Supported Instruments: HiSeq 3000/4000, MiniSeq/NextSeq 500.
- Sample adapter sequences from raw instrument output.
- Read the quality summary information from the raw instrument output.
- Result can be written to JSON or posted to `Flowcelltool <https://github.com/bihealth/flowcelltool>`_.

Configuration File
------------------

You can create a configuration file ``~/.ngsgluttonrc`` for configuration of the tool.
This uses INI-style configuration, see the example below for documentation.

.. code-block:: ini

    # The section "flowcelltool" contains configuration of the Flowcelltool instance
    # to write results to.
    [flowcelltool]
    # The URL to the instance
    url = http://localhost:8000
    # Authentication token obtained from the UI
    auth_token = 255db8819ff8061670c52a0ebcf12a2314fe71544b5c45b43218c9cd04997335
