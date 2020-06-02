#!/usr/bin/env python

from setuptools import setup

setup(name='RIPE-connector',
    version='1.0',
    description='RPKI-chronicle-RIPE-connector',
    install_requires = [
        'sqlalchemy',
        'fasteners', 
        ],
    packages = ['RIPEValidatoConnector',],
    scripts = [
        'rpkival_save_records.py',
        ],
   )

