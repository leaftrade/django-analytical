"""
In pytest any conftest.py files are invoked before any tests are run.

Taken from: http://engineroom.trackmaven.com/blog/using-pytest-with-django/
"""
import os
import sys
import django

from os.path import abspath, dirname, join

sys.path.insert(0, join(dirname(abspath(__file__)), 'testproject'))

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'testproject.settings')


def pytest_configure():
    django.setup()
