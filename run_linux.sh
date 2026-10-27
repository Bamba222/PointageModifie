#!/usr/bin/env bash
set -e

python3 -m venv .venv
source .venv/bin/activate

python -m pip install --upgrade pip
pip install django

python manage.py makemigrations
python manage.py migrate

python manage.py createsuperuser

python manage.py runserver
