$ErrorActionPreference = "Stop"

python -m venv .venv
.\.venv\Scripts\Activate.ps1

python -m pip install --upgrade pip
pip install django

python manage.py makemigrations
python manage.py migrate

python manage.py createsuperuser

python manage.py runserver
